"""Kinematic comparisons, explicitly not ROS or Gazebo integration evidence."""
import asyncio
import json
from pathlib import Path
from demo_easy import KinematicDemo
import bootstrap

async def main():
    results=[]
    for scenario in ('easy','medium','hard'):
        for mode in ('baseline','adaptive'):
            for seed in (1,2,7):
                d=KinematicDemo(seed=seed,samples=3,scenario=scenario,mode=mode)
                r=await d.run()
                row=dict(scenario=scenario,mode=mode,seed=seed,status=r['state']['status'],collected=r['state']['collected'],delivered=r['state']['delivered'],battery=r['score']['battery'],collisions=r['collisions'],journal_stages=sorted(set(e['stage'] for e in d.mission.journal)),knowledge=len(d.navigator.energy.public()) if d.navigator.energy else 0)
                results.append(row);print(json.dumps(row),flush=True)
    output=bootstrap.ROOT/'experiments/runs/scenario-verification.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(harness='kinematic only; NOT ROS/Gazebo',runs=results),indent=2))
if __name__=='__main__':asyncio.run(main())
