"""Synthetic acceptance cases, explicitly separate from Gazebo experiments."""
from dataclasses import dataclass
from time import perf_counter
from .context import Candidate, PlanningContext
from .validation import PlanningUnavailable, UnsafeObservation


def observation(t=1, battery=60, signal=.2, **changes):
    return {"sim_time": t, "pose": {"x": 0, "y": 0}, "battery": battery,
            "signal": signal, "pose_time": t, "battery_time": t,
            "signal_time": t, "scan_time": t, "obstacle_ahead": False} | changes


@dataclass(frozen=True)
class Case:
    name: str
    obs: dict
    candidates: tuple[Candidate, ...]
    expected: tuple[str, ...]
    warmup: tuple[dict, ...] = ()
    home: float = 2


def cases() -> list[Case]:
    targets = (Candidate("near", 1, 0, 2, 2), Candidate("far", 0, 2, 4, 2))
    return [
        Case("ordinary_exploration", observation(), targets, ("explore", "go_to")),
        Case("return_reserve", observation(battery=10), targets, ("return_to_base",)),
        Case("single_peak_is_not_collection", observation(signal=.99), targets, ("explore", "go_to")),
        Case("sustained_signal", observation(3, signal=.95), targets, ("collect",),
             (observation(1, signal=.95), observation(2, signal=.95))),
        Case("no_targets", observation(), (), ("return_to_base",)),
        Case("expensive_roundtrip", observation(battery=20), (Candidate("a", 1, 0, 1, 30),), ("return_to_base",)),
        Case("stale_scan", observation(3, scan_time=0), targets, ("stop",)),
        Case("obstacle", observation(obstacle_ahead=True), targets, ("stop",)),
        Case("unreachable_energy_budget", observation(battery=1), targets, ("stop",)),
    ]


async def evaluate(planner, case: Case) -> dict:
    planner.reset()
    for obs in case.warmup:
        planner.observe(obs)
    obs = case.obs
    planner.set_context(PlanningContext(obs["sim_time"], obs["pose"]["x"], obs["pose"]["y"],
                                       case.home, case.candidates))
    started = perf_counter()
    try:
        result = await planner.propose(obs)
        action = result["action"]
        source = planner.history[-1]["source"]
    except (PlanningUnavailable, UnsafeObservation):
        action, source = "stop", "safety"
    return {"case": case.name, "session_id": planner.session_id,
            "expected": list(case.expected), "action": action, "source": source,
            "passed": action in case.expected,
            "duration_s": round(perf_counter() - started, 4),
            "rejections": sum(e["kind"] == "provider_error" for e in planner.history)}
