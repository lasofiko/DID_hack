"""Public-data/lifecycle adapter for ResearchPlanner; no ROS or provider creation."""
import asyncio
from copy import copy, deepcopy
from dataclasses import replace
import math
import time

from did_ml.context import Candidate, PlanningContext
from did_ml.planner import ResearchPlanner
from did_ml.validation import validate_observation
from .navigation import distance, NavigationPlanner


def public_observation(obs):
    """Whitelist the wire contract, including the nested pose."""
    return {**{k: obs[k] for k in (
        'sim_time', 'battery', 'signal', 'pose_time', 'battery_time',
        'signal_time', 'scan_time', 'obstacle_ahead')},
        'pose': {k: obs['pose'][k] for k in ('x', 'y')}}


class ResearchBridge:
    def __init__(self, planner, config):
        self.planner = planner
        self.config = config
        self.pending = None
        # Keep custom ML safety margins if they are stricter than the backend.
        planner.config = replace(planner.config,
            reserve=max(planner.config.reserve, config.battery_reserve),
            energy_factor=max(planner.config.energy_factor, config.return_factor),
            max_sensor_age=min(planner.config.max_sensor_age, config.data_timeout))

    def reset(self):
        self.planner.reset()
        self.pending = None

    def observe(self, obs):
        obs = public_observation(obs)
        self.planner.observe(obs)

    async def propose(self, obs, search, navigator, yaw, feedback):
        started = time.monotonic()
        obs = public_observation(obs)
        validate_observation(obs, self.planner.config.max_sensor_age)
        # Isolated public snapshots: cancelled background work cannot mutate A*,
        # learned costs, search memory, or a subsequent mission.
        nav = deepcopy(navigator.planner)
        battery = copy(navigator.battery)
        if battery.energy is not None:
            energy = copy(battery.energy)
            with battery.energy.lock:
                energy.values = deepcopy(battery.energy.values)
            energy.planner = nav
            battery.energy = energy
        coverage = [dict(p) for p in search.coverage
                    if search.key(p) not in search.visited | search.failed_targets]
        points = sorted(coverage, key=lambda p: distance(obs['pose'], p))[:8]
        if search.signal >= self.config.signal_interest and search.local_steps < 20:
            local = [{'x': obs['pose']['x'] + .22 * math.cos(i * math.pi / 4),
                      'y': obs['pose']['y'] + .22 * math.sin(i * math.pi / 4)}
                     for i in range(8)]
            points = [p for p in local if search.key(p) not in
                      search.visited | search.failed_targets] + points
        deadline = time.monotonic() + self.config.planner_timeout / 2
        context = await asyncio.to_thread(self._context, obs, points[:8], nav, battery, yaw, deadline)
        self.planner.set_context(context)
        # Context building consumes the same manager deadline as provider calls.
        # Leave validation time; bound all provider attempts within what remains.
        remaining = self.config.planner_timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError('Planner budget exhausted')
        original = self.planner.config
        self.planner.config = replace(original, provider_timeout=min(
            original.provider_timeout, remaining * .8 / original.provider_attempts))
        try:
            goal = await self.planner.propose(obs, feedback)
        finally:
            self.planner.config = original
        self.pending = deepcopy(goal)
        return goal

    def _context(self, obs, points, nav, battery, yaw, deadline):
        def path(start, target, heading):
            if time.monotonic() >= deadline:
                raise TimeoutError('Context budget exceeded')
            nav.start_yaw = heading
            return nav.plan(start, target)

        def raw(route, heading):
            movement = NavigationPlanner.length(route) * battery.rate
            turns = 0.0
            if battery.energy is not None:
                estimate, turns = battery.energy.predict_components(route, heading)
                movement = max(movement, estimate)
            return movement + turns

        home = path(obs['pose'], self.config.base, yaw)
        home_energy = raw(home, yaw)
        candidates = []
        seen = set()
        for target in points:
            key = (target['x'], target['y'])
            if key in seen or distance(obs['pose'], target) <= .05:
                continue
            seen.add(key)
            try:
                outgoing = path(obs['pose'], target, yaw)
                heading = yaw
                for a, b in zip(outgoing, outgoing[1:]):
                    if distance(a, b) > 1e-9:
                        heading = math.atan2(b['y']-a['y'], b['x']-a['x'])
                returning = path(target, self.config.base, heading)
            except ValueError:
                continue
            candidates.append(Candidate(f'{key[0]:.9f}:{key[1]:.9f}', *key,
                raw(outgoing, yaw), raw(returning, heading)))
        return PlanningContext(obs['sim_time'], obs['pose']['x'], obs['pose']['y'],
                               home_energy, tuple(candidates))

    def source(self):
        for event in reversed(self.planner.history):
            if event.get('kind') == 'proposal' and event.get('goal') == self.pending:
                return 'LLM' if event.get('source') == 'provider' else 'Algorithmic'
        return 'Algorithmic'

    def complete(self, success, code, sim_time):
        if self.pending is not None:
            # Only backend-authored codes, never raw judge/service/error messages.
            self.planner.record_result(self.pending, {'success': bool(success), 'message': code}, sim_time)
            self.pending = None
