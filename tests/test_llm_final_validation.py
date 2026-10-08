"""Bounded regression checks for late LLM replies after operator interruption."""
import asyncio
from dataclasses import replace
import json
import unittest

from tests.test_planner_integration import fixture, goal
from tests import test_planner_integration as integration


class FinalValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_before_provider_reply_does_not_restore_llm_source(self):
        entered, release = asyncio.Event(), asyncio.Event()

        class DelayedProvider:
            async def complete(self, prompt):
                entered.set()
                await release.wait()
                return json.dumps(goal())

        manager, planner, _, obs = fixture(DelayedProvider())
        planner.config = replace(planner.config, provider_timeout=1)
        integration.PlannerIntegrationTests.fresh_clock(manager, obs)
        await manager.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            await manager.command('stop')
            manager.navigator.stop.assert_awaited()
            manager.navigator.follow.assert_not_awaited()
            release.set()
            await asyncio.wait_for(manager.task, 2)
            self.assertEqual(manager.state()['status'], 'stopped')
            self.assertEqual(manager.planner_source, 'Algorithmic')
            manager.navigator.follow.assert_not_awaited()
            manager.services.collect.assert_not_awaited()
            self.assertIsNone(manager._research.pending)
            results = [e for e in planner.history if e['kind'] == 'result']
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['message'], 'INTERRUPTED')
            self.assertFalse(results[0]['success'])
        finally:
            release.set()
            if not manager.task.done():
                manager.task.cancel()
            await asyncio.gather(manager.task, return_exceptions=True)


    async def test_journal_failure_prevents_fallback_motion(self):
        for kind in ('llm_exchange', 'proposal', 'decision_context'):
            with self.subTest(kind=kind):
                class BrokenSink:
                    def write(self, event):
                        if event['kind'] == kind:
                            raise OSError('PRIVATE_DISK_DETAILS')

                manager, planner, _, obs = fixture(integration.FakeProvider())
                planner.journal = BrokenSink()
                integration.PlannerIntegrationTests.fresh_clock(manager, obs)
                await manager.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
                await asyncio.wait_for(manager.task, 2)
                self.assertEqual(manager.state()['status'], 'failed')
                self.assertEqual(manager.planner_source, 'Algorithmic')
                manager.navigator.follow.assert_not_awaited()
                manager.services.collect.assert_not_awaited()
                manager.services.finish.assert_not_awaited()
                manager.navigator.stop.assert_awaited()
                self.assertNotIn('PRIVATE_DISK_DETAILS', str(manager.journal))

    async def test_result_journal_failure_stops_before_next_action(self):
        class BrokenSink:
            def write(self, event):
                if event['kind'] == 'result':
                    raise OSError('PRIVATE_DISK_DETAILS')

        manager, planner, _, obs = fixture(integration.FakeProvider())
        planner.journal = BrokenSink()
        integration.PlannerIntegrationTests.fresh_clock(manager, obs)
        await manager.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        await asyncio.wait_for(manager.task, 2)
        self.assertEqual(manager.state()['status'], 'failed')
        self.assertEqual(manager.planner_source, 'Algorithmic')
        manager.navigator.follow.assert_awaited_once()
        manager.services.finish.assert_not_awaited()
        manager.navigator.stop.assert_awaited()
        self.assertNotIn('PRIVATE_DISK_DETAILS', str(manager.journal))

    async def test_runtime_refuses_unwritable_journal_without_fallback(self):
        from unittest.mock import patch
        from pathlib import Path
        from did_agent.plugins import PlannerRuntime
        from did_ml.runtime import llm_planner
        from did_ml.settings import LLMSettings

        logs = []
        runtime = PlannerRuntime(logs.append, lambda: llm_planner(
            LLMSettings('test-only-token'), journal_path=Path('unused-probe.jsonl')))
        with patch('pathlib.Path.open', side_effect=OSError('PRIVATE_DISK_DETAILS')):
            with self.assertRaises(RuntimeError) as caught:
                await runtime.open()
        self.assertNotIn('PRIVATE_DISK_DETAILS', str(caught.exception) + str(logs))
        self.assertIsNone(runtime.planner)
        await runtime.close()

    async def test_registered_hypothesis_cycle_through_manager(self):
        from did_ml.validation import PlanningUnavailable
        prompts = []

        class ResearchProvider:
            async def complete(self, prompt):
                prompts.append(json.loads(prompt.split('PUBLIC_CONTEXT_JSON:\n', 1)[1]))
                return json.dumps({**goal(), 'hypothesis_id': 'H1' if len(prompts) == 1 else None})

        manager, planner, search, obs = fixture(ResearchProvider())
        planner.observe(obs)
        planner.register_hypothesis('H1', 'Synthetic signal may rise at candidate',
                                    'Synthetic signal exceeds 0.2', obs['sim_time'])
        answer = await manager.choose(obs, search)
        self.assertEqual(answer['hypothesis_id'], 'H1')
        self.assertEqual(manager.planner_source, 'LLM')
        for invalid in ('H999', [], 1):
            self.assertFalse(manager.valid_goal({**answer, 'hypothesis_id': invalid}))
        with self.assertRaises(PlanningUnavailable):
            planner.conclude_hypothesis('H1', 'No data yet', 'Inconclusive', obs['sim_time'])
        # Simulated backend acknowledgement only; no physical execution is claimed.
        manager._planner_result(True, 'NAVIGATION_SUCCEEDED')
        obs['sim_time'] = 2
        obs['signal'] = 0.1
        for key in ('pose_time', 'battery_time', 'signal_time', 'scan_time'):
            obs[key] = 2
        planner.observe(obs)
        planner.conclude_hypothesis('H1', 'Synthetic observed signal=0.1',
                                    'Expected increase not observed; hypothesis not confirmed', 2)
        self.assertFalse(manager.valid_goal(answer))
        await manager.choose(obs, search)
        self.assertEqual(prompts[-1]['hypotheses'], [])
        trace = prompts[-1]['history']
        self.assertTrue(any(e['kind'] == 'result' and e['message'] == 'NAVIGATION_SUCCEEDED' for e in trace))
        self.assertTrue(any(e.get('stage') == 'conclusion' and 'not confirmed' in e['text'] for e in trace))
        manager._planner_result(False, 'SYNTHETIC_TEST_ENDED')
        planner.reset()
        self.assertFalse(manager.valid_goal(answer))
