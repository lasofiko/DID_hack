"""Deterministic kinematic/control-clock regressions, never Gazebo evidence."""
import math
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bootstrap
from did_agent import AgentConfig, NavigationPlanner, RobotState, SafetyManager, WaypointNavigator
from did_agent.navigation import distance


class RouteFixture:
    def __init__(self, length=8.5, wall_rate=1.0):
        self.config = replace(AgentConfig(), max_linear=.12, max_angular=.4,
                              base_x=.025, base_y=.525)
        self.planner = NavigationPlanner(180, 40, .05, dict(x=0., y=0.))
        self.pose = dict(x=.025 + length, y=.525)
        self.yaw = math.pi
        self.wall = self.sim = 0.
        self.wall_rate = wall_rate
        self.command = (0., 0.)
        self.commands = []
        self.robot = RobotState()
        self.safety = SafetyManager(self.robot, self.config)
        self.navigator = WaypointNavigator(self.robot, self.safety, self.config,
                                           self.publish, self.planner)
        self.navigator.returning = True
        self.update()

    def publish(self, v, w):
        self.command = (v, w)
        self.commands.append(self.command)

    def update(self):
        self.robot.update_clock(self.sim)
        self.robot.update('pose', self.pose, self.sim, yaw=self.yaw)
        self.robot.update('battery', 60., self.sim)
        self.robot.update('signal', 0., self.sim)
        self.robot.update('scan', math.inf, self.sim, nearest=math.inf)

    async def tick(self, dt):
        v, w = self.command
        self.yaw += w * dt
        self.pose = dict(x=self.pose['x'] + v * math.cos(self.yaw) * dt,
                         y=self.pose['y'] + v * math.sin(self.yaw) * dt)
        self.sim += dt
        self.wall += dt * self.wall_rate
        self.update()

    async def follow(self, target=None):
        target = target or self.config.base
        path = self.navigator.plan(self.pose, target)
        with patch('did_agent.runtime.time', SimpleNamespace(monotonic=lambda: self.wall)), \
             patch('did_agent.runtime.asyncio.sleep', self.tick):
            result = await self.navigator.follow(path)
        return result


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_straight_return_fits_existing_120_second_budget(self):
        f = RouteFixture()
        result = await f.follow()
        self.assertEqual(result['message'], 'SUCCESS')
        self.assertLess(f.wall, 75.)
        self.assertLessEqual(distance(f.pose, f.config.base), f.config.base_tolerance)
        self.assertEqual(f.commands[-1], (0., 0.))

    async def test_wall_deadline_is_not_sim_time_and_still_stops(self):
        f = RouteFixture(wall_rate=4.)
        result = await f.follow()
        self.assertEqual(result['message'], 'TIMEOUT')
        self.assertLess(f.sim, f.config.motion_timeout)
        self.assertEqual(f.command, (0., 0.))

    async def test_real_corner_remains_and_does_not_cut_obstacle(self):
        f = RouteFixture(length=0.)
        f.pose = f.planner.point((10, 10)); f.yaw = 0.; f.update()
        f.navigator.returning = False
        f.planner.occupied = {(x, y) for x in range(20, 40) for y in range(20)}
        target = f.planner.point((50, 10))
        positions = []
        original_tick = f.tick
        async def tick(dt):
            before = dict(f.pose)
            await original_tick(dt)
            positions.append(dict(f.pose))
            self.assertTrue(f.planner.segment_free(before, f.pose))
        with patch('did_agent.runtime.time', SimpleNamespace(monotonic=lambda: f.wall)), \
             patch('did_agent.runtime.asyncio.sleep', tick):
            result = await f.navigator.follow(f.navigator.plan(f.pose, target))
        self.assertEqual(result['message'], 'SUCCESS')
        self.assertTrue(any(p['y'] >= 1. for p in positions))
        self.assertEqual(f.command, (0., 0.))

    async def test_async_cancellation_always_emits_zero(self):
        import asyncio
        f = RouteFixture()
        async def cancel(dt):
            raise asyncio.CancelledError()
        with patch('did_agent.runtime.asyncio.sleep', cancel):
            with self.assertRaises(asyncio.CancelledError):
                await f.navigator.follow(f.navigator.plan(f.pose, f.config.base))
        self.assertEqual(f.command, (0., 0.))

class AdaptiveRoutingTests(unittest.TestCase):
    def test_observed_energy_changes_adaptive_route_but_not_baseline(self):
        from did_agent.energy import EnergyObserver
        for adaptive in (False, True):
            p = NavigationPlanner(60, 30, .05, dict(x=0., y=0.))
            e = EnergyObserver(p, lambda *args: None, adaptive=adaptive)
            start, goal = dict(x=.125, y=.225), dict(x=2.125, y=.225)
            before = p.plan(start, goal)
            e.note_command(.1, 0., 0.)
            for i in range(13):
                t = .2 + i * .1
                e.observe({}, 0., [('pose', dict(x=1.1 + i*.01, y=.225), t, 0.),
                                   ('battery', 60. - i*.1, t, None)])
            self.assertGreater(e.accepted, 0)
            after = p.plan(start, goal)
            if adaptive:
                self.assertGreater(e.revision, 0)
                self.assertNotEqual(before, after)
                self.assertTrue(any(q['y'] >= .5 for q in after))
            else:
                self.assertEqual(before, after)
                self.assertEqual(p.costs, {})
            self.assertTrue(all(p.segment_free(a, b) for a, b in zip(after, after[1:])))


class AlignmentSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_alignment_skip_checks_entire_compressed_segment(self):
        f = RouteFixture(length=0.)
        f.pose = dict(x=.525, y=.5); f.yaw = 0.; f.update()
        path = [dict(f.pose)] + [f.planner.point((x,10)) for x in range(11,31)]
        safe = f.planner.segment_free
        checked = []
        def segment_free(a, b):
            checked.append((dict(a), dict(b)))
            if a == path[0] and b == path[-1]:
                return False  # Only the long shortcut is unsafe in this guard fixture.
            return safe(a,b)
        f.planner.segment_free = segment_free
        targets = []
        command = f.navigator.controller.command
        def record(pose, yaw, target, tolerance=None):
            targets.append(dict(target))
            return command(pose,yaw,target,tolerance)
        f.navigator.controller.command = record
        async def cancel(dt):
            f.navigator.generation += 1
        with patch('did_agent.runtime.asyncio.sleep', cancel):
            result = await f.navigator.follow(path)
        self.assertIn((path[0], path[-1]), checked)
        self.assertEqual(targets[0], path[1])
        self.assertEqual(result['message'], 'CANCELLED')
        self.assertEqual(f.command, (0., 0.))


if __name__ == '__main__':
    unittest.main()
