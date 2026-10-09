import json
import unittest

from did_ml import Candidate, PlanningContext, ResearchPlanner
from did_ml.validation import SubgoalValidationError, parse_subgoal


class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_target_error_becomes_feedback_and_retry_can_succeed(self):
        prompts = []
        class Provider:
            async def complete(self, prompt):
                prompts.append(prompt)
                return json.dumps({"action": "explore", "target": "a" if len(prompts) == 1 else {"x": 1, "y": 0},
                                   "reason": "test", "hypothesis_id": None})
        planner = ResearchPlanner(provider=Provider())
        planner.set_context(PlanningContext(1, 0, 0, 0, (Candidate("a", 1, 0, 2, 2),)))
        obs = {"sim_time": 1, "pose": {"x": 0, "y": 0}, "battery": 60, "signal": .2,
               "pose_time": 1, "battery_time": 1, "signal_time": 1, "scan_time": 1, "obstacle_ahead": False}
        output = await planner.propose(obs)
        self.assertEqual(output["target"], {"x": 1, "y": 0})
        self.assertEqual(planner.history[-1]["source"], "provider")
        self.assertEqual(planner.history[0]["stage"], "subgoal_validation")
        self.assertEqual(planner.history[0]["reason"], "Expected point {x, y}")
        self.assertIn("Expected point {x, y}", prompts[1])

    def test_malformed_output_does_not_leak_raw_text(self):
        for raw in ('secret-text', '{"private-secret":1,"private-secret":2}'):
            with self.assertRaises(SubgoalValidationError) as caught:
                parse_subgoal(raw)
            self.assertNotIn("secret", str(caught.exception))
