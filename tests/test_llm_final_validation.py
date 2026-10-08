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
