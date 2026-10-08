"""Single-agent MissionControl with bounded planner calls and deterministic fallback."""
from __future__ import annotations
import asyncio
from copy import deepcopy
import math
import time
import uuid
from did_core.types import MissionState, StartRequest, Command, Subgoal
from .battery import BatteryManager, ReturnToBase
from .search import SampleSearch

class RejectedSubgoal(ValueError):
    """Safe validation feedback; external exception messages are never published."""

class MissionManager:
    def __init__(self, robot, navigator, services, config, safety, planner=None):
        self.robot, self.navigator, self.services = robot, navigator, services
        self.config, self.safety, self.planner = config, safety, planner
        self._state = dict(run_id=None,status='idle',observation=None,goal=None,collected=0,delivered=0)
        self.journal = []
        self.task = None
        self.resume_status = 'running'
        self.mode='baseline';self.planner_mode='llm' if planner else 'algorithmic';self.planner_source='Algorithmic'

    def state(self) -> MissionState:
        state = deepcopy(self._state)
        state['observation'] = self.robot.snapshot()
        return state

    def log(self, text, stage='observation', hypothesis_id=''):
        obs = self.robot.snapshot()
        if obs:
            text += ' | pose='+str(obs['pose'])+' battery='+format(obs['battery'],'.3f')+' signal='+format(obs['signal'],'.3f')
        self.journal.append(dict(sim_time=obs['sim_time'] if obs else 0,
                                 hypothesis_id=hypothesis_id,stage=stage,text=text))
        del self.journal[:-1000]

    async def start(self, request: StartRequest) -> MissionState:
        if self._state['status'] not in ('idle','finished','stopped','failed'):
            raise ValueError('Mission already active')
        if set(request)-{'scenario','seed','mode','planner_mode'} or not {'scenario','seed','mode'}.issubset(request) or request['scenario'] not in ('easy','medium','hard') or request['mode'] not in ('baseline','adaptive') or request.get('planner_mode','algorithmic') not in ('algorithmic','llm'):
            raise ValueError('Invalid mission configuration')
        if isinstance(request['seed'],bool) or not isinstance(request['seed'],int) or not 0 <= request['seed'] <= 2147483647:
            raise ValueError('Invalid seed')
        if not self.robot.fresh(self.config.data_timeout) or self.navigator.planner is None:
            raise RuntimeError('ROS/data/map unavailable')
        if self.task and not self.task.done():
            await self.task
        if self.safety.reason():
            raise RuntimeError(self.safety.reason())
        self._state = dict(run_id=uuid.uuid4().hex,status='running',observation=None,goal=None,collected=0,delivered=0)
        self.journal.clear()
        self.navigator.returning = False
        self.navigator.battery = BatteryManager(self.config)
        self.mode=request['mode'];self.planner_mode=request.get('planner_mode','llm' if self.planner else 'algorithmic')
        self.goal_samples=self.config.goal_samples if request['scenario']=='easy' else {'medium':5,'hard':7}[request['scenario']]
        from .energy import EnergyObserver
        self.navigator.energy=EnergyObserver(self.navigator.planner,self.log,getattr(self,'energy_model',None)) if self.mode=='adaptive' else None
        self.navigator.planner.costs.clear()
        if self.planner_mode=='llm' and self.planner is None:self.log('LLM unavailable: using Algorithmic fallback')
        self.task = asyncio.create_task(self._run())
        return self.state()

    async def command(self, command: Command) -> MissionState:
        status = self._state['status']
        allowed = {'pause':('running','returning'),'resume':('paused',),
                   'return':('running','paused','returning'),'stop':('running','paused','returning')}
        if command not in allowed or status not in allowed[command]:
            raise ValueError('Command unavailable in current state')
        if command == 'pause':
            self.resume_status = status
            self._state['status'] = 'paused'
        elif command == 'resume':
            if self.safety.reason() is not None:
                raise RuntimeError('Unsafe to resume')
            self._state['status'] = self.resume_status
        else:
            self._state['status'] = 'returning' if command == 'return' else 'stopped'
        if command != 'resume':
            await self.navigator.stop()
        self.log('Command: '+command)
        return self.state()

    def valid_goal(self, goal):
        if not isinstance(goal,dict) or set(goal) != {'action','target','reason','hypothesis_id'}:
            return False
        if goal['action'] not in ('explore','go_to','collect','return_to_base') or not isinstance(goal['reason'],str):
            return False
        if goal['hypothesis_id'] is not None:  # No hypothesis registry in this MVP.
            return False
        target = goal['target']
        if goal['action'] in ('collect','return_to_base'):
            return target is None
        return isinstance(target,dict) and set(target) == {'x','y'} and all(
            isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in target.values())

    async def choose(self, obs, search) -> Subgoal:
        feedback = ''
        self.planner_source='Algorithmic'
        if self.planner is not None and self.planner_mode=='llm':
            for _ in range(2):
                try:
                    goal = await asyncio.wait_for(self.planner.propose(deepcopy(obs),feedback),self.config.planner_timeout)
                    if not self.valid_goal(goal):
                        raise RejectedSubgoal('Invalid Subgoal')
                    if goal['action'] in ('go_to','explore'):
                        try:self.navigator.plan(obs['pose'],goal['target'])
                        except ValueError as exc:raise RejectedSubgoal('Target unreachable') from exc
                    if goal['action'] == 'collect' and not search.should_collect(obs['pose']):
                        raise RejectedSubgoal('Collect signal unconfirmed')
                    self.planner_source='LLM'
                    return goal
                except Exception as exc:
                    feedback = str(exc) if isinstance(exc,RejectedSubgoal) else type(exc).__name__
                    self.log('Planner rejected: '+feedback)
        if search.should_collect(obs['pose']):
            action, target, reason = 'collect', None, 'Confirmed median signal'
        else:
            target = search.next_target(obs['pose'])
            action = 'explore' if target else 'return_to_base'
            reason = 'Signal-guided coverage' if target else 'Coverage exhausted'
        return dict(action=action,target=target,reason=reason,hypothesis_id=None)

    async def _service(self, function):
        try:
            result = await asyncio.wait_for(function(),self.config.service_timeout)
            if not isinstance(result,dict) or not isinstance(result.get('success'),bool) or not isinstance(result.get('message'),str):
                raise ValueError('Invalid service response')
            return result
        except asyncio.TimeoutError:
            # Request may already have executed: never retry uncertain collect/finish.
            raise RuntimeError('Service timeout: result unknown')

    async def _run(self):
        search = SampleSearch(self.navigator.planner,self.config)
        battery = self.navigator.battery
        home = ReturnToBase(self.navigator.planner,self.config)
        deadline = time.monotonic()+self.config.mission_timeout
        steps, failures = 0, 0
        try:
            while self._state['status'] in ('running','returning','paused'):
                if self._state['status'] == 'paused':
                    await asyncio.sleep(self.config.control_period)
                    continue
                if time.monotonic() >= deadline:
                    if self._state['status'] == 'returning':
                        raise RuntimeError('Mission timeout during return')
                    self._state['status'] = 'returning'
                    deadline = time.monotonic()+self.config.motion_timeout
                if self._state['status'] == 'paused':
                    await asyncio.sleep(self.config.control_period)
                    continue
                reason = self.safety.reason()
                if reason:
                    raise RuntimeError(reason)
                obs = self.robot.snapshot()
                battery.observe(obs)
                if self._state['status'] == 'returning':
                    self._state['goal'] = dict(action='return_to_base',target=None,reason='Return priority',hypothesis_id=None)
                    if not home.arrived(obs['pose']):
                        self.navigator.returning = True
                        result = await self.navigator.follow(home.plan(obs['pose']))
                        if result['success'] or result['message']=='REPLAN':
                            if result['message']=='REPLAN':self.log('Return path recomputed after measured cost update','replan')
                            continue
                        if self._state['status'] in ('paused','stopped') or result['message'] == 'CANCELLED':
                            continue
                        raise RuntimeError('Return failed: '+result['message'])
                    await self.navigator.stop()
                    result = await self._service(self.services.finish)
                    self.log('Finish: '+str(result))
                    if self._state['status'] != 'returning':
                        continue
                    if not result['success']:
                        raise RuntimeError('Finish rejected: '+result['message'])
                    self._state.update(status='finished',delivered=self._state['collected'])
                    break
                if self._state['collected'] >= self.goal_samples or steps >= self.config.max_steps:
                    self._state['status'] = 'returning'
                    continue
                # Several distinct sensor packets at a stationary observation point.
                search.observe(obs)
                old_stamp = obs['signal_time']
                for _ in range(2):
                    until = time.monotonic()+self.config.data_timeout
                    while time.monotonic() < until:
                        await asyncio.sleep(self.config.control_period)
                        sample = self.robot.snapshot()
                        if sample and sample['signal_time'] > old_stamp:
                            search.observe(sample)
                            old_stamp = sample['signal_time']
                            break
                if self._state['status'] != 'running':
                    continue
                if self.safety.reason():
                    raise RuntimeError(self.safety.reason())
                obs = self.robot.snapshot()
                home_path = home.plan(obs['pose'])
                if obs['battery'] <= battery.required(home_path):
                    self._state['status'] = 'returning'
                    self.log('Energy reserve: return')
                    continue
                goal = await self.choose(obs,search)
                if self._state['status'] != 'running':
                    continue
                self._state['goal'] = goal
                self.log('Decision: '+str(goal))
                steps += 1
                if goal['action'] == 'return_to_base':
                    self._state['status'] = 'returning'
                elif goal['action'] == 'collect':
                    await self.navigator.stop()
                    result = await self._service(self.services.collect)
                    search.collected(obs['pose'],result['success'])
                    if result['success']:
                        self._state['collected'] += 1
                    self.log('Collect: '+str(result))
                else:
                    outgoing = self.navigator.plan(obs['pose'],goal['target'])
                    return_path = home.plan(goal['target'])
                    if not battery.can_explore(obs['battery'],outgoing,return_path):
                        self._state['status'] = 'returning'
                        continue
                    self.navigator.returning = False
                    result = await self.navigator.follow(outgoing)
                    if self._state['status'] != 'running':
                        continue
                    if not result['success']:
                        if result['message']=='REPLAN':
                            self.log('Measured cost update: recompute A* route','replan')
                            continue
                        self.log('Navigation: '+result['message'])
                        search.failed_targets.add(search.key(goal['target']))
                        failures += 1
                        if result['message'] == 'LOW_RESERVE':
                            self._state['status'] = 'returning'
                        if result['message'] in ('STALE_DATA','LOW_BATTERY','EMERGENCY'):
                            raise RuntimeError(result['message'])
                        if failures >= 3:
                            self._state['status'] = 'returning'
                    else:
                        search.visited.add(search.key(goal['target']))
                        failures = 0
        except asyncio.CancelledError:
            self._state['status'] = 'stopped'
            raise
        except Exception as exc:
            self._state['status'] = 'failed'
            self.log('Failure: '+str(exc))
        finally:
            await self.navigator.stop()
            self.log('Mission: '+self._state['status'])
