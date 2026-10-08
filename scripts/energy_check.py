"""Reproducible multi-seed algorithm fixtures; never labelled ROS/Gazebo results."""
import argparse
import asyncio
import json
from pathlib import Path
from demo_easy import KinematicDemo

async def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seeds',nargs='+',type=int,default=[1,2])
    p.add_argument('--output',default='experiments/runs/maria-kinematic-matrix.json')
    a=p.parse_args();rows=[]
    for scenario in ('easy','medium','hard'):
        for mode in ('baseline','adaptive'):
            for seed in a.seeds:
                d=KinematicDemo(seed=seed,samples=3,scenario=scenario,mode=mode)
                r=await d.run();state=r['state'];values=d.navigator.energy.public()
                delivered=state['status']=='finished' and state['delivered']>0
                stopped=d.velocity==(0.,0.) and r['collisions']==0
                row=dict(scenario=scenario,mode=mode,seed=seed,status=state['status'],
                    collected=state['collected'],delivered=state['delivered'],battery=r['score']['battery'],
                    collisions=r['collisions'],delivered_and_finished=delivered,safely_stopped=stopped,
                    energy=d.navigator.energy.diagnostics(),straight=sum(e['move_samples'] for e in values),
                    turn=sum(e['turn_samples'] for e in values),costs=values)
                rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='costs'}),flush=True)
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(harness='kinematic fixtures ONLY; NOT ROS/Gazebo',runs=rows),indent=2)+'\n')
    if any(not r['safely_stopped'] or (r['scenario']!='hard' and not r['delivered_and_finished']) for r in rows):raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
