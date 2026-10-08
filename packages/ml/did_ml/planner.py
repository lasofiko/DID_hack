"""One planner per mission. Backend retains final safety and execution authority."""
import asyncio
from collections import deque
from copy import deepcopy
from dataclasses import asdict
from math import hypot
from statistics import median
from time import monotonic
from uuid import uuid4

from did_core.types import Observation, Result, Subgoal
from .context import Candidate, PlannerConfig, PlanningContext, nonnegative
from .provider import TextProvider, ProviderError, build_prompt
from .journal import EventSink, JournalWriteError, prompt_hash
from .research import HypothesisRegistry
from .validation import SubgoalValidationError, PlanningUnavailable, UnsafeObservation, parse_subgoal, validate_observation


class ResearchPlanner:
    def __init__(self, config: PlannerConfig | None = None, provider: TextProvider | None = None,
                 *, journal: EventSink | None = None):
        self.config = config or PlannerConfig()
        self.provider = provider
        self.journal = journal
        self._lock = asyncio.Lock()
        self.reset()

    def reset(self) -> None:
        """New mission or /clock reset: clear memory and supply a new context."""
        if self._lock.locked():
            raise RuntimeError("Cannot reset during a model request")
        self._context = None
        self._latest = None
        self._pending = None
        self._signals = deque(maxlen=self.config.history_size)
        self._history = deque(maxlen=self.config.history_size)
        self._visits = {}
        self._blocked_until = {}
        self._last_collect = float("-inf")
        self._last_result_time = 0.0
        self._provider_resume_at = 0.0
        self._research = HypothesisRegistry()
        self.session_id = uuid4().hex
        self._audit({"kind": "session", "config": asdict(self.config), "schema_version": 1})

    def _audit(self, event: dict) -> None:
        if self.journal is not None:
            try:
                self.journal.write({"session_id": self.session_id, **event})
            except (OSError, ValueError, TypeError):
                raise JournalWriteError() from None

    def _emit(self, event: dict) -> None:
        self._audit(event)
        self._history.append(event)

    @property
    def active_hypothesis_ids(self) -> frozenset[str]:
        """Read-only registry snapshot for backend validation; never invent IDs."""
        return frozenset(self._research.ids)

    def register_hypothesis(self, hypothesis_id: str, statement: str, expected: str, sim_time: float) -> None:
        self._check_research_time(sim_time)
        entry = self._research.register(hypothesis_id, statement, expected, sim_time)
        self._emit({"kind": "research", **entry})

    def conclude_hypothesis(self, hypothesis_id: str, evidence: str, conclusion: str, sim_time: float) -> None:
        self._check_research_time(sim_time)
        for entry in self._research.conclude(hypothesis_id, evidence, conclusion, sim_time):
            self._emit({"kind": "research", **entry})

    def _check_research_time(self, sim_time: float) -> None:
        if self._lock.locked() or self._pending is not None:
            raise PlanningUnavailable("Research updates require no outstanding proposal")
        if self._latest is None or sim_time != self._latest["sim_time"]:
            raise ValueError("Feed the current observation before updating research")

    def set_context(self, context: PlanningContext) -> None:
        """Costs must include reachable outbound and home paths, in energy units."""
        if self._lock.locked():
            raise RuntimeError("Cannot replace context during a model request")
        if not isinstance(context, PlanningContext) or len(context.candidates) > 128:
            raise ValueError("Expected PlanningContext with at most 128 candidates")
        self._context = context

    def observe(self, observation: Observation) -> None:
        """Feed sensor updates even while no new subgoal is requested."""
        if self._lock.locked():
            raise RuntimeError("Serialize planner updates with propose")
        self._observe(observation)

    def _observe(self, obs: Observation) -> None:
        validate_observation(obs, self.config.max_sensor_age)
        if obs["sim_time"] < self._last_result_time:
            raise UnsafeObservation("Observation predates last execution result")
        if self._latest:
            for field in ("sim_time", "pose_time", "battery_time", "signal_time", "scan_time"):
                if obs[field] < self._latest[field]:
                    raise UnsafeObservation("Clock/sensor time moved backwards; reset the mission")
        # Replaying a signal reading cannot create evidence for collection.
        if self._latest is None or obs["signal_time"] > self._latest["signal_time"]:
            self._signals.append((obs["signal_time"], deepcopy(obs["pose"]), obs["signal"]))
        self._latest = deepcopy(obs)

    @property
    def history(self) -> list[dict]:
        """Bounded public decision trace; caller may persist it as JSONL."""
        return deepcopy(list(self._history))

    def record_result(self, goal: Subgoal, result: Result, sim_time: float) -> None:
        """Report execution OR backend rejection before requesting another goal."""
        if self._lock.locked():
            raise RuntimeError("Cannot report execution during a model request")
        nonnegative(sim_time, "sim_time")
        if self._pending is None or goal != self._pending[0]:
            raise ValueError("Result must match the outstanding proposal")
        if not isinstance(result, dict) or set(result) != {"success", "message"}:
            raise ValueError("Expected Result")
        if type(result["success"]) is not bool or not isinstance(result["message"], str):
            raise ValueError("Invalid Result values")
        if sim_time < self._latest["sim_time"]:
            raise ValueError("Result predates observations")
        _, candidate_id = self._pending
        if goal["action"] == "collect":
            self._last_collect = sim_time
            self._signals.clear()
        if candidate_id is not None:
            if result["success"]:
                self._visits[candidate_id] = self._visits.get(candidate_id, 0) + 1
            else:
                self._blocked_until[candidate_id] = sim_time + self.config.failed_target_cooldown
            for cache in (self._visits, self._blocked_until):
                while len(cache) > self.config.history_size * 10:
                    del cache[next(iter(cache))]
        self._emit({"kind": "result", "sim_time": sim_time,
                              "goal": deepcopy(goal), "success": result["success"],
                              "message": result["message"][:1000]})
        self._last_result_time = sim_time
        self._pending = None

    def _collect_allowed(self, obs: Observation) -> bool:
        if obs["obstacle_ahead"] or obs["sim_time"] - self._last_collect < self.config.collect_cooldown:
            return False
        samples = [signal for stamp, pose, signal in self._signals
                   if 0 <= obs["sim_time"] - stamp <= self.config.signal_window
                   and hypot(pose["x"] - obs["pose"]["x"], pose["y"] - obs["pose"]["y"]) <= self.config.signal_radius]
        recent = samples[-self.config.signal_samples:]
        return (len(recent) >= self.config.signal_samples
                and min(recent) >= self.config.collect_threshold
                and median(recent) >= self.config.collect_threshold)

    def _eligible(self, obs: Observation) -> list[Candidate]:
        return [c for c in self._context.candidates
                if self._blocked_until.get(c.id, -1) <= obs["sim_time"]
                and hypot(c.x - obs["pose"]["x"], c.y - obs["pose"]["y"]) > 0.05
                and (c.outbound_energy + c.return_energy) * self.config.energy_factor
                    + self.config.reserve <= obs["battery"]]

    @staticmethod
    def _goal(action, reason, candidate=None) -> Subgoal:
        return {"action": action, "target": {"x": candidate.x, "y": candidate.y} if candidate else None,
                "reason": reason, "hypothesis_id": None}

    async def propose(self, observation: Observation, feedback: str = "") -> Subgoal:
        """Implements did_core.ports.Planner; no LLM is needed for offline mode."""
        if self._lock.locked():
            raise PlanningUnavailable("Only one proposal request may run at a time")
        async with self._lock:
            if self._pending is not None:
                raise PlanningUnavailable("Report execution/rejection with record_result first")
            if not isinstance(feedback, str) or len(feedback) > 2000:
                raise ValueError("Feedback must be a string of at most 2000 characters")
            obs = deepcopy(observation)
            self._observe(obs)
            ctx = self._context
            if ctx is None:
                raise PlanningUnavailable("Backend must supply a PlanningContext")
            if abs(ctx.sim_time - obs["sim_time"]) > 1e-6 or hypot(
                    ctx.pose_x - obs["pose"]["x"], ctx.pose_y - obs["pose"]["y"]) > 1e-6:
                raise UnsafeObservation("Context costs are not anchored to this observation")
            home = ctx.home_energy * self.config.energy_factor
            if obs["battery"] <= 0 or obs["battery"] < home:
                raise PlanningUnavailable("Insufficient estimated energy to return; backend recovery required")
            eligible = self._eligible(obs)
            collect = self._collect_allowed(obs)
            return_required = obs["battery"] <= home + self.config.reserve
            goal, source = None, "offline"
            if obs["obstacle_ahead"]:
                raise PlanningUnavailable("Obstacle ahead: backend must stop and replan")
            if return_required or (not eligible and not collect):
                goal = self._goal("return_to_base", "Возврат: резерв энергии или нет допустимых целей")
            elif self.provider is not None and monotonic() >= self._provider_resume_at:
                public = {"mission": ctx.mission, "observation": obs,
                          "candidates": [asdict(c) for c in eligible],
                          "home_energy": ctx.home_energy, "reserve": self.config.reserve,
                          "energy_factor": self.config.energy_factor,
                          "collect_allowed": collect, "return_required": False,
                          "history": self.history[-10:], "feedback": feedback,
                          "hypotheses": self._research.active}
                for _ in range(self.config.provider_attempts):
                    stage = "provider_request"
                    try:
                        prompt = build_prompt(public)
                        started = monotonic()
                        raw = await asyncio.wait_for(self.provider.complete(prompt),
                                                     timeout=self.config.provider_timeout)
                        self._audit({"kind": "llm_exchange", "sim_time": obs["sim_time"],
                                     "prompt": prompt, "prompt_sha256": prompt_hash(prompt),
                                     "response": raw, "duration_s": round(monotonic() - started, 6)})
                        stage = "subgoal_validation"
                        proposed = parse_subgoal(raw, self._research.ids)
                        if proposed["action"] in ("explore", "go_to"):
                            if not any(proposed["target"] == {"x": c.x, "y": c.y} for c in eligible):
                                raise SubgoalValidationError("Target is not an eligible candidate")
                        elif proposed["action"] == "collect" and not collect:
                            raise SubgoalValidationError("No stable signal evidence for collection")
                        goal, source = proposed, "provider"
                        break
                    except (ValueError, TimeoutError, ConnectionError, OSError) as exc:
                        # Do not retain exception text: provider errors may contain secrets.
                        public["feedback"] = "Response rejected. Use the schema and eligible candidates; " + type(exc).__name__
                        error = {"kind": "provider_error", "sim_time": obs["sim_time"],
                                 "error_type": type(exc).__name__, "stage": stage}
                        if isinstance(exc, SubgoalValidationError):
                            error["reason"] = str(exc)
                            public["feedback"] = str(exc)
                        if isinstance(exc, ProviderError):
                            error.update(code=exc.code, status_code=exc.status_code)
                        self._emit(error)
                        if getattr(exc, "retryable", True) is False:
                            break
                if goal is None:
                    self._provider_resume_at = monotonic() + self.config.provider_cooldown
            elif self.provider is not None:
                self._emit({"kind": "provider_cooldown", "sim_time": obs["sim_time"]})
            if goal is None:
                if collect:
                    goal = self._goal("collect", "Несколько свежих измерений подтверждают высокий сигнал")
                else:
                    best = min(eligible, key=lambda c: (
                        -(c.information_gain / (1 + self._visits.get(c.id, 0))) / (1 + c.outbound_energy), c.id))
                    goal = self._goal("explore", "Достижимая точка с приоритетом информации, цены и предыдущих посещений", best)
            candidate_id = next((c.id for c in eligible if goal["target"] == {"x": c.x, "y": c.y}), None)
            self._pending = (deepcopy(goal), candidate_id)
            self._emit({"kind": "proposal", "sim_time": obs["sim_time"],
                        "source": source, "goal": deepcopy(goal)})
            self._audit({"kind": "decision_context", "sim_time": obs["sim_time"],
                         "observation": obs, "navigation": asdict(ctx)})
            return deepcopy(goal)
