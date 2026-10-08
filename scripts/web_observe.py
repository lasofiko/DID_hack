"""Read-only capture of a mission controlled from the browser."""
import argparse
import asyncio
import json
from pathlib import Path
import time
import websockets
async def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=180);p.add_argument('--output',default='/workspace/output/web-browser.json');a=p.parse_args();history=[];last=None
    async with websockets.connect('ws://127.0.0.1:8000/api/telemetry',max_size=2**22) as ws:
        end=time.monotonic()+a.seconds
        while time.monotonic()<end:
            last=json.loads(await ws.recv());s=last['state'];row=dict(status=s['status'],collected=s['collected'],delivered=s['delivered'],planner_source=last['planner_source'])
            if not history or history[-1]!=row:history.append(row);print(json.dumps(row),flush=True)
            if s['status'] in ('finished','failed','stopped'):break
    Path(a.output).write_text(json.dumps(dict(harness='Real browser-controlled ROS/Gazebo capture',history=history,final=last),indent=2))
if __name__=='__main__':asyncio.run(main())
