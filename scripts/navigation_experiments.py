"""Paired public-telemetry kinematic experiments; NOT ROS/Gazebo results."""
import argparse
import asyncio
from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import time
from demo_easy import KinematicDemo
from did_agent.navigation import distance, wrap


class MeasuredDemo(KinematicDemo):
    def __init__(self, **kwargs):
        self.travel = self.rotation = 0.
        self.turns = 0
        self.previous_pose = self.previous_yaw = None
        self.previous_command = (0., 0.)
        super().__init__(**kwargs)

    def update(self):
        super().update()
        if self.previous_pose is not None:
            self.travel += distance(self.previous_pose, self.pose)
            self.rotation += abs(wrap(self.yaw - self.previous_yaw))
        self.previous_pose, self.previous_yaw = dict(self.pose), self.yaw

    def publish(self, linear, angular):
        if angular and not self.previous_command[1]:
            self.turns += 1
        self.previous_command = (linear, angular)
        super().publish(linear, angular)


async def run_pair_member(scenario, seed, mode, timeout):
    d = MeasuredDemo(seed=seed, samples=3, scenario=scenario, mode=mode,
                     map_file=Path(__file__).resolve().parents[1]/'configs/maps/map.yaml')
    initial_battery = d.robot.snapshot()['battery']
    start_sim = d.sim_time
    started = time.monotonic()
    error = None
    try:
        result = await asyncio.wait_for(d.run(), timeout)
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        result = dict(state=d.mission.state(), collisions=d.collisions)
    finally:
        await d.navigator.stop()
    state = result['state']; obs = d.robot.snapshot()
    collected, delivered = state['collected'], state['delivered']
    battery = obs['battery'] if obs else None
    used = initial_battery - battery if battery is not None else None
    failures = [e['text'] for e in d.mission.journal if e['text'].startswith(('Failure:', 'Navigation:'))]
    row = dict(scenario=scenario, seed=seed, mode=mode, planner_mode='algorithmic',
        config=asdict(d.config), status=state['status'], collected=collected, delivered=delivered,
        delivered_fraction=delivered/collected if collected else None,
        initial_battery=initial_battery, final_battery=battery, battery_used=used,
        energy_per_delivered=used/delivered if delivered and used is not None else None,
        route_length_m=d.travel, elapsed_wall_s=time.monotonic()-started,
        elapsed_sim_s=d.sim_time-start_sim, turns=d.turns, rotation_rad=d.rotation,
        replans=sum(e['stage']=='replan' for e in d.mission.journal),
        return_success=state['status']=='finished' and obs is not None and
                       distance(obs['pose'],d.config.base)<=d.config.base_tolerance,
        collisions=d.collisions, errors=failures+([error] if error else []),
        termination_reason=error or (failures[-1] if failures else state['status']),
        final_command=list(d.velocity))
    return row, d.mission.journal


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--medium', action='store_true')
    parser.add_argument('--timeout', type=float, default=45.)
    parser.add_argument('--output', type=Path, default=Path('experiments/runs/navigation-matrix.json'))
    args=parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be finite and positive')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report=dict(harness='kinematic fixture with local mock judge; NOT ROS/Gazebo or official judge',
                revision=revision, dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
                runs=[])
    for scenario in (('easy','medium') if args.medium else ('easy',)):
        for seed in (1,2):
            for mode in ('baseline','adaptive'):
                row,journal=await run_pair_member(scenario,seed,mode,args.timeout)
                report['runs'].append(row)
                args.output.with_name(f'{args.output.stem}-{scenario}-{seed}-{mode}-journal.json').write_text(
                    json.dumps(journal,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
                args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
                print(json.dumps({k:v for k,v in row.items() if k!='config'},ensure_ascii=False),flush=True)
    if any(r['errors'] or r['collisions'] or not r['return_success'] or r['final_command']!=[0.,0.]
           for r in report['runs']):
        raise SystemExit(1)


if __name__=='__main__':
    asyncio.run(main())
