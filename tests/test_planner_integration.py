"""Real ResearchPlanner/MissionManager on a small map; fake IO/provider only."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bootstrap
from did_agent import AgentConfig, NavigationPlanner, BatteryManager, SampleSearch
from did_agent.energy import EnergyObserver
from did_agent.mission import MissionManager
from did_agent.planner_bridge import ResearchBridge, public_observation
from did_ml.integration import create_planner
from did_ml.planner import ResearchPlanner
from did_ml.context import PlannerConfig


def goal(action='explore'):
    return dict(action=action, target={'x': 1.5, 'y': .5} if action=='explore' else None,
                reason='Test public goal', hypothesis_id=None)


class FakeProvider:
    def __init__(self, action='explore', error=None, delay=0):
        self.prompts = []
        self.action, self.error, self.delay = action, error, delay

    async def complete(self, prompt):
        self.prompts.append(prompt)
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return json.dumps(goal(self.action))


def fixture(provider=None):
    config = replace(AgentConfig(), base_x=.5, base_y=.5, search_spacing=1,
                     control_period=.001, max_steps=1)
    nav = NavigationPlanner(4, 3, 1, {'x': 0, 'y': 0})
    obs = dict(sim_time=1., pose={'x': .5, 'y': .5}, battery=60., signal=0.,
               pose_time=1., battery_time=1., signal_time=1., scan_time=1., obstacle_ahead=False)
    robot = SimpleNamespace(yaw=0., snapshot=lambda: deepcopy(obs), fresh=lambda *_: True,
                            drain_energy_samples=lambda: None)
    navigator = SimpleNamespace(planner=nav, plan=nav.plan, stop=AsyncMock(),
                                follow=AsyncMock(return_value={'success': True, 'message': 'ok'}))
    navigator.battery = BatteryManager(config)
    navigator.battery.energy = EnergyObserver(nav, lambda *_: None, config=config)
    planner = ResearchPlanner(PlannerConfig(provider_timeout=.01), provider)
    services = SimpleNamespace(collect=AsyncMock(return_value={'success': True, 'message': 'PRIVATE_JUDGE'}),
                               finish=AsyncMock(return_value={'success': True, 'message': 'PRIVATE_JUDGE'}))
    manager = MissionManager(robot, navigator, services, config, SimpleNamespace(reason=lambda: None), planner)
    search = SampleSearch(nav, config)
    search.coverage = [{'x': 1.5, 'y': .5}]
    return manager, planner, search, obs


class PlannerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_is_offline_and_contract_callable(self):
        self.assertIsNone(create_planner().provider)
        m, p, search, obs = fixture()
        first = await m.choose(obs, search)
        self.assertEqual(first['action'], 'explore')
        self.assertEqual(m.planner_source, 'Algorithmic')
        m._planner_result(True, 'NAVIGATION_SUCCEEDED')
        second = await m.choose(obs, search)
        self.assertEqual(second['action'], 'explore')
        self.assertEqual(sum(e['kind']=='result' for e in p.history), 1)

    async def test_provider_source_and_private_data_whitelist(self):
        provider = FakeProvider()
        m, p, search, obs = fixture(provider)
        obs['private_judge'] = 'HIDDEN_SAMPLE'; obs['api_key'] = 'SECRET_TEST'
        obs['pose']['terrain'] = 'TRUE_COST'
        search.private_judge = 'HIDDEN_SAMPLE'
        await m.choose(obs, search)
        self.assertEqual(m.planner_source, 'LLM')
        self.assertTrue(provider.prompts)
        for secret in ('HIDDEN_SAMPLE', 'SECRET_TEST', 'TRUE_COST', 'private_judge', 'api_key'):
            self.assertNotIn(secret, ''.join(provider.prompts))
            self.assertNotIn(secret, str(p.history))
        self.assertEqual(set(public_observation(obs)['pose']), {'x', 'y'})

    async def test_raw_costs_include_turnaround_without_double_reserve(self):
        m, p, search, obs = fixture()
        await m.choose(obs, search)
        ctx = p._context
        c = ctx.candidates[0]
        self.assertEqual(ctx.home_energy, 0)
        self.assertAlmostEqual(c.outbound_energy, 3)
        self.assertAlmostEqual(c.return_energy, 3 + math.pi * .25)
        expected = (c.outbound_energy+c.return_energy)*p.config.energy_factor+p.config.reserve
        self.assertAlmostEqual(expected, m.navigator.battery.required([
            obs['pose'], {'x': 1.5, 'y': .5}, obs['pose']]))
        self.assertEqual(m.navigator.planner.start_yaw, 0)

    async def test_unreachable_candidate_omitted(self):
        m, p, search, obs = fixture()
        m.navigator.planner.occupied.add((1, 0))
        answer = await m.choose(obs, search)
        self.assertEqual(answer['action'], 'return_to_base')
        self.assertEqual(p._context.candidates, ())

    async def test_backend_rejection_records_result_before_retry(self):
        m, p, search, obs = fixture()
        m.valid_goal = lambda _: False
        await m.choose(obs, search)
        results = [e for e in p.history if e['kind']=='result']
        self.assertEqual(len(results), 2)
        self.assertTrue(all(not e['success'] for e in results))
        self.assertIsNone(m._research.pending)

    async def test_provider_errors_and_timeout_use_honest_fallback(self):
        for provider in (FakeProvider(error=ValueError('SECRET_TEST')), FakeProvider(delay=.1)):
            m, p, search, obs = fixture(provider)
            answer = await m.choose(obs, search)
            self.assertEqual(answer['action'], 'explore')
            self.assertEqual(m.planner_source, 'Algorithmic')
            self.assertNotIn('SECRET_TEST', str(p.history)+str(m.journal))

    async def test_future_sensor_not_retimestamped_or_sent_to_provider(self):
        provider = FakeProvider()
        m, p, search, obs = fixture(provider)
        obs['pose_time'] += .03
        await m.choose(obs, search)
        self.assertFalse(provider.prompts)
        self.assertEqual(obs['pose_time'], 1.03)
        self.assertEqual(m.planner_source, 'Algorithmic')

    async def test_low_budget_never_requests_provider(self):
        provider = FakeProvider()
        m, p, search, obs = fixture(provider)
        obs['battery'] = 8
        answer = await m.choose(obs, search)
        self.assertEqual(answer['action'], 'return_to_base')
        self.assertFalse(provider.prompts)

    async def test_new_mission_resets_memory_and_finalizes_return(self):
        m, p, search, obs = fixture(FakeProvider('return_to_base'))
        await m.choose(obs, search)
        session = p.session_id
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        self.assertNotEqual(session, p.session_id)
        self.assertFalse(p.history)
        await m.command('return')
        await m.task
        self.assertEqual(m.state()['status'], 'finished')
        self.assertIsNone(m._research.pending)

    async def test_control_loop_collect_result_has_no_service_private_message(self):
        m, p, search, obs = fixture()
        obs['signal'] = .99
        def snapshot():
            obs['sim_time'] += .01
            for key in ('pose_time','battery_time','signal_time','scan_time'):
                obs[key] = obs['sim_time']
            return deepcopy(obs)
        m.robot.snapshot = snapshot
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        await asyncio.wait_for(m.task, 2)
        self.assertEqual(m.state()['status'], 'finished')
        results = [e for e in p.history if e['kind']=='result']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['success'])
        self.assertNotIn('PRIVATE_JUDGE', str(p.history))

    async def test_safety_rechecked_after_proposal(self):
        m, p, search, obs = fixture()
        def snapshot():
            obs['sim_time'] += .01
            for key in ('pose_time','battery_time','signal_time','scan_time'):
                obs[key] = obs['sim_time']
            return deepcopy(obs)
        m.robot.snapshot = snapshot
        original = m.choose
        async def choose(*args):
            result = await original(*args)
            m.safety.reason = lambda: 'EMERGENCY'
            return result
        m.choose = choose
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        await asyncio.wait_for(m.task, 2)
        self.assertEqual(m.state()['status'], 'failed')
        m.navigator.follow.assert_not_awaited()
        self.assertIsNone(m._research.pending)
        self.assertEqual([e for e in p.history if e['kind']=='result'][0]['message'], 'SAFETY_REJECTED')

    async def test_context_worker_does_not_block_event_loop(self):
        m, p, search, obs = fixture()
        bridge = ResearchBridge(p, m.config)
        started, release = threading.Event(), threading.Event()
        def slow(*args):
            started.set()
            release.wait(1)
            raise TimeoutError()
        bridge._context = slow
        task = asyncio.create_task(bridge.propose(obs, search, m.navigator, 0, ''))
        try:
            async def wait_started():
                while not started.is_set():
                    await asyncio.sleep(.01)
            await asyncio.wait_for(wait_started(), .5)
            self.assertFalse(task.done())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertIsNone(bridge.pending)
        finally:
            release.set()

    async def test_pause_during_proposal_completes_pending_without_motion(self):
        m, p, search, obs = fixture()
        self.fresh_clock(m, obs)
        original = m.choose
        async def choose(*args):
            result = await original(*args)
            await m.command('pause')
            return result
        m.choose = choose
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        async def paused():
            while m.state()['status'] != 'paused' or m._research.pending is not None:
                await asyncio.sleep(.001)
        await asyncio.wait_for(paused(), 2)
        m.navigator.follow.assert_not_awaited()
        self.assertEqual([e for e in p.history if e['kind']=='result'][0]['message'], 'INTERRUPTED')
        await m.command('stop')
        await m.task

    @staticmethod
    def fresh_clock(m, obs):
        def snapshot():
            obs['sim_time'] += .01
            for key in ('pose_time','battery_time','signal_time','scan_time'):
                obs[key] = obs['sim_time']
            return deepcopy(obs)
        m.robot.snapshot = snapshot

    async def test_changed_battery_rejects_outgoing_motion(self):
        m, p, search, obs = fixture()
        self.fresh_clock(m, obs)
        original = m.choose
        async def choose(*args):
            result = await original(*args)
            obs['battery'] = 8
            return result
        m.choose = choose
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        await asyncio.wait_for(m.task, 2)
        m.navigator.follow.assert_not_awaited()
        self.assertEqual([e for e in p.history if e['kind']=='result'][0]['message'], 'ENERGY_REJECTED')

    async def test_replan_keeps_one_pending_goal_until_navigation_finishes(self):
        m, p, search, obs = fixture()
        self.fresh_clock(m, obs)
        calls = []
        async def follow(path):
            calls.append(deepcopy(m._research.pending))
            if len(calls) == 1:
                self.assertFalse(any(e['kind']=='result' for e in p.history))
                return {'success': False, 'message': 'REPLAN'}
            obs['pose'] = dict(path[-1])
            return {'success': True, 'message': 'ok'}
        m.navigator.follow = follow
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        await asyncio.wait_for(m.task, 2)
        self.assertEqual(calls[0], calls[1])
        self.assertIsNotNone(calls[0])
        results = [e for e in p.history if e['kind']=='result']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['message'], 'NAVIGATION_SUCCEEDED')

    async def test_forced_return_does_not_keep_last_llm_label(self):
        m, p, search, obs = fixture()
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        m.planner_source = 'LLM'
        m._state['collected'] = m.goal_samples
        await m.task
        self.assertEqual(m.planner_source, 'Algorithmic')

    async def test_cancellation_records_failure_once(self):
        m, p, search, obs = fixture()
        self.fresh_clock(m, obs)
        moving = asyncio.Event()
        async def follow(path):
            moving.set()
            await asyncio.sleep(5)
        m.navigator.follow = follow
        await m.start(dict(scenario='easy', seed=1, mode='baseline', planner_mode='llm'))
        await asyncio.wait_for(moving.wait(), 2)
        m.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await m.task
        results = [e for e in p.history if e['kind']=='result']
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['success'])
        self.assertIsNone(m._research.pending)
        self.assertEqual(m.state()['status'], 'stopped')
