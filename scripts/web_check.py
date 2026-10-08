"""Real HTTP/WebSocket → ROS → Gazebo verification. Execute INSIDE Docker."""
import argparse
import asyncio
import json
import math
from pathlib import Path
import time
import urllib.request
import urllib.error
import websockets

URL='http://127.0.0.1:8000'
def request(path,body=None):
    req=urllib.request.Request(URL+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
async def telemetry():
    async with websockets.connect('ws://127.0.0.1:8000/api/telemetry',max_size=2**22) as ws:return json.loads(await ws.recv())
async def main():
    p=argparse.ArgumentParser();p.add_argument('--scenario',choices=['easy','medium','hard'],default='easy');p.add_argument('--seed',type=int,default=1);p.add_argument('--mode',choices=['baseline','adaptive'],default='baseline');p.add_argument('--seconds',type=int,default=900);p.add_argument('--controls',action='store_true');p.add_argument('--expect-safe-failure',action='store_true');p.add_argument('--output',default='/workspace/output/web-check.json');a=p.parse_args()
    session=dict(scenario=a.scenario,seed=a.seed,mode=a.mode,planner_mode='algorithmic')
    report=dict(session=session,harness='REAL HTTP/WebSocket + ROS + Gazebo; mock judge',checks={},timeline=[])
    try:
        deadline=time.monotonic()+40
        while True:
            try:
                assert await asyncio.to_thread(request,'/api/health')=={'status':'ok'}
                break
            except OSError:
                if time.monotonic()>deadline:raise
                await asyncio.sleep(.5)
        reset=await asyncio.to_thread(request,'/api/missions/reset',session);assert reset['status']=='idle' and reset['collected']==0
        first=await telemetry();assert first['connection']=='online' and first['score']['battery']>59.9
        assert len(first['trajectory'])<10 and not first['knowledge'];report['checks']['reset']=True
        grid=await asyncio.to_thread(request,'/api/map');assert len(grid['data'])==grid['width']*grid['height'];report['checks']['map']=True
        async with websockets.connect('ws://127.0.0.1:8000/api/telemetry',max_size=2**22) as ws:
            t=time.monotonic()
            for _ in range(8):await ws.recv()
            report['checks']['ws_rate_hz']=7/(time.monotonic()-t)
        state=await asyncio.to_thread(request,'/api/missions',session);assert state['status']=='running';report['checks']['start']=True
        if a.controls:
            await asyncio.sleep(5)
            state=await asyncio.to_thread(request,'/api/command',dict(command='pause'));assert state['status']=='paused'
            before=await telemetry();await asyncio.sleep(2);after=await telemetry()
            slip=math.hypot(before['robot_pose']['x']-after['robot_pose']['x'],before['robot_pose']['y']-after['robot_pose']['y']);assert slip<.015
            report['checks']['pause_slip_m']=slip
            state=await asyncio.to_thread(request,'/api/command',dict(command='resume'));assert state['status']=='running';report['checks']['resume']=True
        end=time.monotonic()+a.seconds;last=None
        while time.monotonic()<end:
            last=await telemetry();state=last['state'];row=dict(status=state['status'],collected=state['collected'],battery=(state['observation'] or {}).get('battery'),sim_time=(state['observation'] or {}).get('sim_time'))
            if not report['timeline'] or row['status']!=report['timeline'][-1]['status'] or row['collected']!=report['timeline'][-1]['collected']:
                report['timeline'].append(row);print(json.dumps(row),flush=True)
            if state['status'] in ('failed','finished','stopped'):break
            await asyncio.sleep(2)
        else:
            state=await asyncio.to_thread(request,'/api/command',dict(command='return'));report['checks']['manual_return_after_time_limit']=True
            end=time.monotonic()+120
            while time.monotonic()<end:
                last=await telemetry()
                if last['state']['status'] in ('failed','finished','stopped'):break
                await asyncio.sleep(2)
        report['final']=last
        import bootstrap
        from ros_smoke import world_position
        physical=await asyncio.to_thread(world_position)
        report['physical_world_pose']=physical
        report['physical_base_distance_m']=math.hypot(physical[0]+2,physical[1]+.5)
        report['checks']['physical_motion']=len(last['trajectory'])>10
        report['checks']['public_truth_absent']=all(k not in json.dumps(last) for k in ('true_cost','_samples','_zones','_schedule','private_events'))
        passed=last['state']['status']=='finished' and last['state']['delivered']>0 and report['physical_base_distance_m']<.18
        if last['state']['status'] in ('finished','failed','stopped'):
            def zero_probe():
                import rclpy
                from rclpy.node import Node
                from geometry_msgs.msg import TwistStamped
                rclpy.init();node=Node('web_stop_probe');commands=[]
                node.create_subscription(TwistStamped,'/cmd_vel',lambda m:commands.append((m.twist.linear.x,m.twist.angular.z)),10)
                end=time.monotonic()+2
                try:
                    while time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.1)
                    return len(commands)>=5 and all(v==0 and w==0 for v,w in commands),len(commands)
                finally:node.destroy_node();rclpy.shutdown()
            zero,count=await asyncio.to_thread(zero_probe)
            report['checks']['sustained_zero_cmd_vel']=zero;report['zero_command_count']=count
            passed=passed and zero
            if a.expect_safe_failure:passed=last['state']['status']=='failed' and zero
        report['passed']=passed
        report['outcome']='delivered_and_finished' if passed and not a.expect_safe_failure else last['state']['status']
        print(json.dumps(dict(outcome=report['outcome'],physical_base_distance_m=report['physical_base_distance_m'],score=last['score'],checks=report['checks'])),flush=True)
    except Exception as exc:
        report['error']=repr(exc);report['passed']=False;print(report['error'],flush=True)
        try:await asyncio.to_thread(request,'/api/command',dict(command='stop'))
        except Exception:pass
    finally:Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False))
    if not report.get('passed'):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
