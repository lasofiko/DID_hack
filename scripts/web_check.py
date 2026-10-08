"""Real HTTP/WebSocket → ROS → Gazebo verification. Execute INSIDE Docker."""
import argparse
import asyncio
import json
import math
from pathlib import Path
import time
import threading
import urllib.request
import urllib.error
import websockets

URL='http://127.0.0.1:8000'
def request(path,body=None):
    req=urllib.request.Request(URL+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(str(exc.code)+': '+exc.read().decode()) from exc
async def telemetry():
    async with websockets.connect('ws://127.0.0.1:8000/api/telemetry',max_size=2**22) as ws:return json.loads(await ws.recv())
async def main():
    p=argparse.ArgumentParser();p.add_argument('--scenario',choices=['easy','medium','hard'],default='easy');p.add_argument('--seed',type=int,default=1);p.add_argument('--mode',choices=['baseline','adaptive'],default='baseline');p.add_argument('--seconds',type=int,default=900);p.add_argument('--controls',action='store_true');p.add_argument('--expect-safe-failure',action='store_true');p.add_argument('--output',default='/workspace/output/web-check.json');a=p.parse_args()
    session=dict(scenario=a.scenario,seed=a.seed,mode=a.mode,planner_mode='algorithmic')
    report=dict(session=session,harness='REAL HTTP/WebSocket + ROS + Gazebo; mock judge',checks={},timeline=[])
    import bootstrap
    from ament_index_python.packages import get_package_share_directory
    from did_agent import AgentConfig
    from dataclasses import asdict
    report['agent_config']=asdict(AgentConfig.load(Path(get_package_share_directory('did_robot'))/'config/agent.json'))
    commands=[];probe_stop=threading.Event();probe=None;motion_task=None;physical_samples=[]
    def command_probe():
        import rclpy
        from rclpy.context import Context
        from rclpy.node import Node
        from rclpy.executors import SingleThreadedExecutor
        from geometry_msgs.msg import TwistStamped
        context=Context();rclpy.init(context=context)
        node=Node('energy_command_probe',context=context)
        executor=SingleThreadedExecutor(context=context);executor.add_node(node)
        node.create_subscription(TwistStamped,'/cmd_vel',lambda m:commands.append((m.twist.linear.x,m.twist.angular.z)),10)
        try:
            while not probe_stop.is_set():executor.spin_once(timeout_sec=.1)
        finally:executor.shutdown();node.destroy_node();context.shutdown()
    async def sample_physical_motion():
        import bootstrap
        from ros_smoke import world_position
        began=time.monotonic()
        while True:
            try:physical_samples.append(dict(wall_elapsed_s=time.monotonic()-began,pose=await asyncio.to_thread(world_position)))
            except (OSError,ValueError,RuntimeError):pass
            await asyncio.sleep(10)
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
        deadline=time.monotonic()+10
        while True:
            first=await telemetry()
            if first['connection']=='online' and first['score'].get('battery',0)>59.9 and first['state']['observation'] is not None:break
            if time.monotonic()>deadline:raise RuntimeError('Judge/battery telemetry not ready')
            await asyncio.sleep(.2)
        report['reset_observation']=dict(pose=first['robot_pose'],sim_time=first['state']['observation']['sim_time'],battery=first['score']['battery'])
        assert len(first['trajectory'])<10 and not first['knowledge'];report['checks']['reset']=True
        grid=await asyncio.to_thread(request,'/api/map');assert len(grid['data'])==grid['width']*grid['height'];report['checks']['map']=True
        async with websockets.connect('ws://127.0.0.1:8000/api/telemetry',max_size=2**22) as ws:
            t=time.monotonic()
            for _ in range(8):await ws.recv()
            report['checks']['ws_rate_hz']=7/(time.monotonic()-t)
        motion_task=asyncio.create_task(sample_physical_motion())
        probe=threading.Thread(target=command_probe,daemon=True);probe.start()
        await asyncio.sleep(1)
        state=await asyncio.to_thread(request,'/api/missions',session);assert state['status']=='running';report['checks']['start']=True
        report['start_receipt_observation']=state.get('observation')
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
        report['command_counts']=dict(total=len(commands),straight=sum(v!=0 and w==0 for v,w in commands),turn=sum(v==0 and w!=0 for v,w in commands),mixed=sum(v!=0 and w!=0 for v,w in commands),peak_linear=max((abs(v) for v,w in commands),default=0.),peak_angular=max((abs(w) for v,w in commands),default=0.))
        report['checks']['exclusive_commands']=len(commands)>10 and report['command_counts']['mixed']==0
        report['measurements']=dict(straight=sum(e.get('move_samples') or 0 for e in last['knowledge']),turn=sum(e.get('turn_samples') or 0 for e in last['knowledge']))
        report['energy_diagnostics']=last.get('energy_diagnostics')
        import bootstrap
        from ros_smoke import world_position
        physical=await asyncio.to_thread(world_position)
        report['physical_world_pose']=physical
        report['physical_base_distance_m']=math.hypot(physical[0]+2,physical[1]+.5)
        report['physical_samples']=physical_samples
        measured_motion=max((math.dist(s['pose'],physical_samples[0]['pose']) for s in physical_samples),default=0.)
        report['maximum_physical_displacement_m']=measured_motion
        report['checks']['physical_motion']=measured_motion>.05
        def private_keys(value):
            if isinstance(value,dict):
                return any(k in ('true_cost','_samples','_zones','_schedule','private_events','samples','zones','schedule') or private_keys(v) for k,v in value.items())
            if isinstance(value,list):return any(private_keys(v) for v in value)
            return False
        report['checks']['public_truth_absent']=not private_keys(last)
        passed=last['state']['status']=='finished' and last['state']['delivered']>0 and report['physical_base_distance_m']<.18 and not report['checks'].get('manual_return_after_time_limit',False)
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
        passed=passed and report['checks']['exclusive_commands'] and report['checks']['public_truth_absent'] and report['checks']['physical_motion']
        report['passed']=passed
        report['outcome']='delivered_and_finished' if passed and not a.expect_safe_failure else last['state']['status']
        print(json.dumps(dict(outcome=report['outcome'],physical_base_distance_m=report['physical_base_distance_m'],score=last['score'],checks=report['checks'])),flush=True)
    except Exception as exc:
        report['error']=repr(exc);report['passed']=False;print(report['error'],flush=True)
        try:await asyncio.to_thread(request,'/api/command',dict(command='stop'))
        except Exception:pass
    finally:
        probe_stop.set()
        if motion_task:
            motion_task.cancel();await asyncio.gather(motion_task,return_exceptions=True)
        if probe:probe.join(timeout=3)
        Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False))
    if not report.get('passed'):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
