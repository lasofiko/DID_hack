import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from did_ml import ResearchPlanner, PlanningContext, Candidate, PlannerConfig
from did_ml.evaluation import cases, evaluate, observation
from did_ml.journal import JsonlJournal, ReplayProvider
from did_ml.provider import ProviderError
from did_ml.validation import PlanningUnavailable


class HandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_offline_acceptance_cases(self):
        for case in cases():
            with self.subTest(case=case.name):
                self.assertTrue((await evaluate(ResearchPlanner(), case))["passed"])

    async def test_registry_rejects_invented_ids_and_closes_real_hypothesis(self):
        class Provider:
            async def complete(self, prompt):
                return json.dumps({"action": "explore", "target": {"x": 1, "y": 0},
                                   "reason": "Probe public frontier", "hypothesis_id": "H1"})
        planner = ResearchPlanner(provider=Provider())
        planner.observe(observation())
        planner.register_hypothesis("H1", "Signal rises near frontier", "Signal above .2 after movement", 1)
        planner.set_context(PlanningContext(1, 0, 0, 0, (Candidate("a", 1, 0, 1, 1),)))
        goal = await planner.propose(observation())
        self.assertEqual(goal["hypothesis_id"], "H1")
        with self.assertRaises(PlanningUnavailable):
            planner.conclude_hypothesis("H1", "data", "not supported", 1)
        planner.record_result(goal, {"success": False, "message": "route rejected"}, 1)
        planner.conclude_hypothesis("H1", "Probe was not executed", "Inconclusive", 1)
        stages = [e["stage"] for e in planner.history if e["kind"] == "research"]
        self.assertEqual(stages, ["hypothesis", "observation", "conclusion"])
        with self.assertRaises(ValueError):
            planner.register_hypothesis("H1", "duplicate", "duplicate", 1)

    async def test_provider_cooldown_across_proposals(self):
        class Provider:
            calls = 0
            async def complete(self, prompt):
                self.calls += 1
                raise ProviderError("rate_limited", retryable=False, status_code=429)
        provider = Provider()
        planner = ResearchPlanner(provider=provider)
        planner.set_context(PlanningContext(1, 0, 0, 0, (Candidate("a", 1, 0, 1, 1),)))
        goal = await planner.propose(observation())
        planner.record_result(goal, {"success": True, "message": "test acknowledgment"}, 1)
        await planner.propose(observation())
        self.assertEqual(provider.calls, 1)
        self.assertTrue(any(e["kind"] == "provider_cooldown" for e in planner.history))

    async def test_trace_and_exact_replay(self):
        # Workspace-local temp root avoids Windows system Temp permissions.
        root = Path(__file__).resolve().parents[1] / "experiments/runs"
        root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=root) as directory:
            path = Path(directory) / "trace.jsonl"
            class Provider:
                async def complete(self, prompt):
                    return json.dumps({"action": "explore", "target": {"x": 1, "y": 0},
                                       "reason": "test", "hypothesis_id": None})
            planner = ResearchPlanner(provider=Provider(), journal=JsonlJournal(path))
            ctx = PlanningContext(1, 0, 0, 0, (Candidate("a", 1, 0, 1, 1),))
            planner.set_context(ctx)
            expected = await planner.propose(observation())
            replay = ResearchPlanner(provider=ReplayProvider(path, session_id=planner.session_id))
            replay.set_context(ctx)
            self.assertEqual(await replay.propose(observation()), expected)
            self.assertEqual(replay.history[-1]["source"], "provider")
            journal = JsonlJournal(path, secrets=("secret-token",))
            journal.write({"kind": "test", "nested": ["secret-token"]})
            self.assertNotIn("secret-token", path.read_text(encoding="utf-8"))

    async def test_journal_failure_is_not_treated_as_model_failure(self):
        class Broken:
            def write(self, event):
                raise OSError("private filesystem details")
        with self.assertRaisesRegex(RuntimeError, "journal write failed"):
            ResearchPlanner(journal=Broken())


if __name__ == "__main__":
    unittest.main()
