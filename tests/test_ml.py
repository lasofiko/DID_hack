import asyncio
from copy import deepcopy
import json
import unittest

from did_ml import Candidate, PlannerConfig, PlanningContext, ResearchPlanner
from did_ml.validation import PlanningUnavailable, UnsafeObservation, parse_subgoal


def observation(t=1, battery=60, signal=0.2, **changes):
    obs = {"sim_time": t, "pose": {"x": 0.0, "y": 0.0}, "battery": battery,
           "signal": signal, "pose_time": t, "battery_time": t, "signal_time": t,
           "scan_time": t, "obstacle_ahead": False}
    return obs | changes


def context(t=1, candidates=None, home=2):
    return PlanningContext(t, 0, 0, home,
        tuple(candidates) if candidates is not None else (
            Candidate("a", 1, 0, 2, 2), Candidate("b", 0, 1, 4, 2)))


def goal(action="explore", x=1, y=0):
    return {"action": action, "target": {"x": x, "y": y} if action in ("explore", "go_to") else None,
            "reason": "test", "hypothesis_id": None}


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    async def complete(self, prompt):
        self.prompts.append(prompt)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_determinism(self):
        outputs = []
        for _ in range(2):
            p = ResearchPlanner()
            p.set_context(context())
            outputs.append(await p.propose(observation()))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0]["target"], {"x": 1, "y": 0})

    async def test_energy_includes_return_and_reserve(self):
        p = ResearchPlanner()
        p.set_context(context(candidates=[Candidate("expensive", 1, 0, 1, 30)]))
        self.assertEqual((await p.propose(observation(battery=20)))["action"], "return_to_base")

    async def test_low_battery_bypasses_model(self):
        provider = FakeProvider([])
        p = ResearchPlanner(provider=provider)
        p.set_context(context())
        self.assertEqual((await p.propose(observation(battery=10)))["action"], "return_to_base")
        self.assertEqual(provider.prompts, [])

    async def test_impossible_return_does_not_invent_safe_action(self):
        p = ResearchPlanner()
        p.set_context(context(home=20))
        with self.assertRaises(PlanningUnavailable):
            await p.propose(observation(battery=10))

    async def test_empty_battery_at_base_requires_backend_recovery(self):
        p = ResearchPlanner()
        p.set_context(context(home=0))
        with self.assertRaises(PlanningUnavailable):
            await p.propose(observation(battery=0))

    async def test_stale_and_invalid_observations(self):
        for bad in (observation(scan_time=-1), observation(scan_time=5),
                    observation(signal=float("nan")), observation(battery=True),
                    observation(signal=1.2), observation(sim_time=3, scan_time=1),
                    observation(secret_samples=[])):
            p = ResearchPlanner()
            p.set_context(context())
            with self.assertRaises(UnsafeObservation):
                await p.propose(bad)

    async def test_missing_and_mismatched_context(self):
        p = ResearchPlanner()
        with self.assertRaises(PlanningUnavailable):
            await p.propose(observation())
        p.set_context(context(0))
        with self.assertRaises(UnsafeObservation):
            await p.propose(observation())

    async def test_obstacle_stops_even_without_candidates(self):
        p = ResearchPlanner()
        p.set_context(context(candidates=[]))
        with self.assertRaises(PlanningUnavailable):
            await p.propose(observation(obstacle_ahead=True))

    async def test_single_peak_does_not_collect(self):
        p = ResearchPlanner()
        for _ in range(5):
            p.observe(observation(signal=0.95))
        p.set_context(context())
        self.assertEqual((await p.propose(observation(signal=0.95)))["action"], "explore")

    async def test_stable_signal_collect_then_cooldown(self):
        p = ResearchPlanner()
        for t in (1, 2, 3):
            p.observe(observation(t, signal=0.95))
        p.set_context(context(3))
        proposal = await p.propose(observation(3, signal=0.95))
        self.assertEqual(proposal["action"], "collect")
        p.record_result(proposal, {"success": True, "message": "collected"}, 3)
        for t in (4, 5, 6):
            p.observe(observation(t, signal=0.95))
        p.set_context(context(6))
        self.assertEqual((await p.propose(observation(6, signal=0.95)))["action"], "explore")

    async def test_distant_signal_readings_do_not_accumulate(self):
        p = ResearchPlanner()
        for t in (1, 2):
            p.observe(observation(t, signal=.99, pose={"x": 5, "y": 0}))
        p.set_context(context(3))
        self.assertEqual((await p.propose(observation(3, signal=.99)))["action"], "explore")

    async def test_execution_ack_required_and_rejection_changes_target(self):
        p = ResearchPlanner()
        p.set_context(context())
        proposal = await p.propose(observation())
        with self.assertRaises(PlanningUnavailable):
            await p.propose(observation())
        with self.assertRaises(ValueError):
            p.record_result(goal("collect"), {"success": True, "message": "bad"}, 1)
        p.record_result(proposal, {"success": False, "message": "blocked"}, 1)
        self.assertEqual((await p.propose(observation()))["target"], {"x": 0, "y": 1})

    async def test_mutating_returned_goal_cannot_mutate_pending(self):
        p = ResearchPlanner()
        p.set_context(context())
        proposal = await p.propose(observation())
        original = deepcopy(proposal)
        proposal["target"]["x"] = 100
        p.record_result(original, {"success": True, "message": "ok"}, 1)
        trace = p.history
        trace.clear()
        self.assertGreater(len(p.history), 0)

    async def test_clock_reset_requires_reset(self):
        p = ResearchPlanner()
        p.observe(observation(10))
        with self.assertRaises(UnsafeObservation):
            p.observe(observation(0))
        p.reset()
        p.set_context(context(0))
        self.assertEqual((await p.propose(observation(0)))["action"], "explore")

    async def test_valid_provider_response(self):
        provider = FakeProvider([json.dumps(goal(x=0, y=1))])
        p = ResearchPlanner(provider=provider)
        p.set_context(context())
        self.assertEqual((await p.propose(observation()))["target"], {"x": 0, "y": 1})
        self.assertEqual(p.history[-1]["source"], "provider")
        self.assertIn('"candidates"', provider.prompts[0])

    async def test_rejected_target_and_collect_fall_back(self):
        provider = FakeProvider([json.dumps(goal(x=999)), json.dumps(goal("collect"))])
        p = ResearchPlanner(provider=provider)
        p.set_context(context())
        self.assertEqual((await p.propose(observation()))["target"], {"x": 1, "y": 0})
        self.assertEqual(len(provider.prompts), 2)
        self.assertEqual(p.history[-1]["source"], "offline")

    async def test_provider_connection_failure_does_not_leak_error(self):
        provider = FakeProvider([ConnectionError("secret-key"), ConnectionError("secret-key")])
        p = ResearchPlanner(provider=provider)
        p.set_context(context())
        await p.propose(observation())
        self.assertNotIn("secret-key", str(p.history) + str(provider.prompts))

    async def test_provider_timeout_falls_back(self):
        class Slow:
            async def complete(self, prompt):
                await asyncio.sleep(10)
        p = ResearchPlanner(PlannerConfig(provider_timeout=.01), Slow())
        p.set_context(context())
        proposal = await asyncio.wait_for(p.propose(observation()), timeout=1)
        self.assertEqual(proposal["action"], "explore")

    async def test_cancellation_is_not_swallowed(self):
        started = asyncio.Event()
        class Slow:
            async def complete(self, prompt):
                started.set()
                await asyncio.sleep(10)
        p = ResearchPlanner(provider=Slow())
        p.set_context(context())
        task = asyncio.create_task(p.propose(observation()))
        await started.wait()
        with self.assertRaises(PlanningUnavailable):
            await p.propose(observation())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        p.reset()


class ValidationTests(unittest.TestCase):
    def test_bad_model_json(self):
        invalid = ['```json\n{}\n```', '[]', '{"action":"collect","action":"explore"}',
                   json.dumps(goal() | {"extra": 1}), json.dumps(goal() | {"hypothesis_id": "invented"}),
                   json.dumps(goal() | {"target": {"x": True, "y": 0}}),
                   json.dumps(goal() | {"target": {"x": float("nan"), "y": 0}})]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_subgoal(raw)

    def test_invalid_configuration(self):
        for kwargs in ({"signal_samples": 1}, {"provider_attempts": 3}, {"reserve": -1}, {"energy_factor": .5}):
            with self.assertRaises(ValueError):
                PlannerConfig(**kwargs)
        with self.assertRaises(ValueError):
            Candidate("bad", 0, 0, float("nan"), 1)


if __name__ == "__main__":
    unittest.main()
