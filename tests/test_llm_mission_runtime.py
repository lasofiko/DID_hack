"""Existing MAI client through MissionManager, with HTTP MockTransport only."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_planner_integration import fixture, goal
from tests.test_ros_adapter import AgentNode
from did_agent.plugins import PlannerRuntime
from did_ml.integration import create_llm_planner, create_planner
from did_ml.mai_provider import MAIProvider
from did_ml.planner import ResearchPlanner
from did_ml.settings import LLMSettings
import httpx


class LLMRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_client_to_manager_and_cleanup(self):
        requests, clients = [], []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps(goal())}}]})
        def provider(settings):
            result = MAIProvider(settings, transport=httpx.MockTransport(handler))
            clients.append(result)
            return result
        with tempfile.TemporaryDirectory() as directory:
            env = {'DID_LLM_API_KEY': 'test-only-token', 'DID_LLM_JOURNAL_DIR': directory,
                   'DID_PLANNER_FACTORY': 'did_ml.integration:create_llm_planner'}
            with patch.dict(os.environ, env, clear=True), patch('did_ml.runtime.MAIProvider', provider):
                logs = []
                runtime = PlannerRuntime(logs.append)
                planner = await runtime.open()
                self.assertIsInstance(planner, ResearchPlanner)
                self.assertFalse(requests)  # No HTTP at factory/client startup.
                self.assertIs(await runtime.open(), planner)
                manager, _, search, obs = fixture()
                manager.planner = planner
                answer = await manager.choose(obs, search)
                self.assertEqual(answer, goal())
                self.assertEqual(manager.planner_source, 'LLM')
                manager._planner_result(True, 'NAVIGATION_SUCCEEDED')
                self.assertEqual(planner.history[-1]['kind'], 'result')
                await runtime.close()
                await runtime.close()
                self.assertTrue(clients[0]._client.is_closed)
                self.assertEqual(len(clients), 1)
                self.assertEqual(len(requests), 1)
                public = requests[0]['messages'][1]['content']
                self.assertNotIn('test-only-token', public)
                journal = ''.join(p.read_text(encoding='utf-8') for p in Path(directory).glob('*.jsonl'))
                self.assertIn('llm_exchange', journal)
                self.assertNotIn('test-only-token', journal)
                self.assertFalse(logs)

    async def test_missing_credentials_falls_back_and_can_retry_initialization(self):
        logs = []
        with patch.dict(os.environ, {}, clear=True):
            runtime = PlannerRuntime(logs.append, create_llm_planner)
            self.assertIsNone(await runtime.open())
        self.assertIn('ValueError', logs[0])
        runtime.factory = create_planner
        self.assertIsInstance(await runtime.open(), ResearchPlanner)
        await runtime.close()

    async def test_invalid_managed_plugin_is_closed_and_error_sanitized(self):
        closed = []
        @asynccontextmanager
        async def bad():
            try:
                yield object()
            finally:
                closed.append(True)
        logs = []
        runtime = PlannerRuntime(logs.append, bad)
        self.assertIsNone(await runtime.open())
        self.assertEqual(closed, [True])
        def raises():
            raise ValueError('SECRET_FROM_CONFIG')
        runtime.factory = raises
        await runtime.open()
        self.assertNotIn('SECRET_FROM_CONFIG', str(logs))

    async def test_cancelled_initialization_releases_context(self):
        entered, cleaned = asyncio.Event(), []
        @asynccontextmanager
        async def resource():
            try:
                entered.set()
                await asyncio.sleep(10)
                yield create_planner()
            finally:
                cleaned.append(True)
        runtime = PlannerRuntime(lambda _: None, resource)
        task = asyncio.create_task(runtime.open())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(cleaned, [True])
        self.assertIsNone(runtime.planner)
        await runtime.close()

    async def test_http_failure_uses_algorithmic_fallback(self):
        for status in (401, 429, 503):
            client = MAIProvider(LLMSettings('test-only-token'),
                transport=httpx.MockTransport(lambda request: httpx.Response(status, text='PRIVATE_RESPONSE')))
            @asynccontextmanager
            async def factory():
                async with client:
                    yield ResearchPlanner(provider=client)
            runtime = PlannerRuntime(lambda _: None, factory)
            manager, _, search, obs = fixture()
            manager.planner = await runtime.open()
            result = await manager.choose(obs, search)
            self.assertEqual(result['action'], 'explore')
            self.assertEqual(manager.planner_source, 'Algorithmic')
            self.assertNotIn('PRIVATE_RESPONSE', str(manager.planner.history))
            manager._planner_result(True, 'NAVIGATION_SUCCEEDED')
            await runtime.close()
            self.assertTrue(client._client.is_closed)

    async def test_provider_deadline_fits_manager_and_config_restored(self):
        manager, planner, search, obs = fixture()
        manager.config = replace(manager.config, planner_timeout=1)
        seen = []
        class Hanging:
            async def complete(self, prompt):
                seen.append(planner.config.provider_timeout)
                await asyncio.sleep(5)
        planner.provider = Hanging()
        planner.config = replace(planner.config, provider_timeout=5)
        result = await manager.choose(obs, search)
        self.assertEqual(result['action'], 'explore')
        self.assertEqual(manager.planner_source, 'Algorithmic')
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(0 < t < .5 for t in seen))
        self.assertEqual(planner.config.provider_timeout, 5)
        self.assertEqual([e['source'] for e in planner.history if e['kind']=='proposal'], ['offline'])

    async def test_ros_start_method_uses_managed_planner_only_in_llm_mode(self):
        manager, _, _, _ = fixture()
        calls = []
        def factory():
            calls.append(asyncio.get_running_loop())
            return create_planner()
        node = AgentNode.__new__(AgentNode)
        node.mission = manager
        node.planner_runtime = PlannerRuntime(lambda _: None, factory)
        for mode in ('algorithmic', 'llm', 'llm'):
            await node._start_mission(dict(scenario='easy', seed=1, mode='baseline', planner_mode=mode))
            if mode == 'algorithmic':
                self.assertFalse(calls)
            else:
                self.assertIs(manager.planner, node.planner_runtime.planner)
            await manager.command('stop')
            await manager.task
        self.assertEqual(calls, [asyncio.get_running_loop()])
        await node.planner_runtime.close()

    async def test_active_mission_does_not_swap_planner(self):
        manager, planner, _, _ = fixture()
        manager._state['status'] = 'running'
        node = AgentNode.__new__(AgentNode)
        node.mission = manager
        with self.assertRaises(ValueError):
            await node._start_mission({'planner_mode': 'algorithmic'})
        self.assertIs(manager.planner, planner)

    async def test_cancel_inflight_http_then_close_client(self):
        entered = asyncio.Event()
        async def handler(request):
            entered.set()
            await asyncio.sleep(10)
            return httpx.Response(200, json={})
        client = MAIProvider(LLMSettings('test-only-token'), transport=httpx.MockTransport(handler))
        @asynccontextmanager
        async def factory():
            async with client:
                yield ResearchPlanner(provider=client)
        runtime = PlannerRuntime(lambda _: None, factory)
        manager, _, search, obs = fixture()
        manager.planner = await runtime.open()
        original_timeout = manager.planner.config.provider_timeout
        task = asyncio.create_task(manager.choose(obs, search))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(manager.planner.config.provider_timeout, original_timeout)
            self.assertIsNone(manager._research.pending)
        finally:
            await runtime.close()
        self.assertTrue(client._client.is_closed)
