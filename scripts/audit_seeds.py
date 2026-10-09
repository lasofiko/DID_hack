"""Audit evidence on multiple EASY seeds; reports failures instead of hiding them."""
import asyncio
import json
from pathlib import Path
from demo_easy import KinematicDemo

async def main():
    results=[]
    for seed in range(1,11):
        demo=KinematicDemo(seed=seed,map_file=Path(__file__).resolve().parents[1]/'configs/maps/map.yaml')
        result=await demo.run()
        row=dict(seed=seed,status=result['state']['status'],delivered=result['state']['delivered'],
                 battery=result['score']['battery'],collisions=result['collisions'])
        row['passed']=row['status']=='finished' and row['delivered']>=1 and row['collisions']==0 and row['battery']>0
        results.append(row)
        print(json.dumps(row),flush=True)
    output=Path(__file__).resolve().parents[1]/'experiments/runs/audit-seeds.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'harness':'kinematic with raw occupancy lidar; NOT ROS/Gazebo','runs':results},indent=2)+'\n')
    if not all(r['passed'] for r in results):raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
