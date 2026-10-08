"""Public ROS bridge and an owned simulator lifecycle. No Docker socket or shell API."""
import asyncio
import copy
import json
import math
import os
from pathlib import Path
import signal
import threading
import time

DEFAULT_SESSION=dict(scenario='easy',seed=1,mode='baseline',planner_mode='algorithmic')

class PublicCache:
    def __init__(self):
        self.lock=threading.RLock();self.clear()
    def clear(self):
        with self.lock:
            self.state=dict(run_id=None,status='idle',observation=None,goal=None,collected=0,delivered=0)
            self.pose=None;self.yaw=0.;self.trajectory=[];self.path=[];self.costs=[];self.journal=[]
            self.planner_source='Algorithmic';self.map=None;self.score={};self.receipts={};self.clock=None
            self.events=[];self.collected_positions=[];self.last_count=0;self.seen=set();self.error=None
    def record(self,kind):self.receipts[kind]=time.monotonic()
    def on_json(self,kind,payload):
        try:value=json.loads(payload)
        except (TypeError,ValueError):return
        with self.lock:
            if kind=='state' and isinstance(value,dict):
                self.state={k:value.get(k) for k in ('run_id','status','observation','goal','collected','delivered')}
                self.record('state')
            elif kind=='journal' and isinstance(value,list):
                for e in value[-50:]:
                    if not isinstance(e,dict):continue
                    public={k:e.get(k) for k in ('sim_time','stage','hypothesis_id','text')}
                    fingerprint=json.dumps(public,sort_keys=True)
                    if fingerprint not in self.seen:
                        self.seen.add(fingerprint);self.journal.append(public)
                self.journal=self.journal[-1000:]
                self.seen={json.dumps(e,sort_keys=True) for e in self.journal}
            elif kind=='knowledge' and isinstance(value,dict):
                self.path=[p for p in value.get('path',[]) if point(p)][:4000]
                self.costs=[]
                for e in value.get('costs',[])[:2000]:
                    if not isinstance(e,dict) or not point(e.get('cell')) or not number(e.get('energy_per_m')) or not 0<=e['energy_per_m']<=30:continue
                    u=e.get('uncertainty')
                    if u is not None and (not number(u) or u<0):continue
                    self.costs.append({k:e.get(k) for k in ('cell','energy_per_m','uncertainty')})
                self.planner_source='LLM' if value.get('planner_source')=='LLM' else 'Algorithmic'
            elif kind=='event' and isinstance(value,dict):
                kind_name=value.get('type',value.get('event'))
                if kind_name in ('sample_collected','false_collect','hazard_hit','collision'):
                    self.events.append(dict(type=kind_name,sim_time=self.clock));self.events=self.events[-100:]
            elif kind=='score' and isinstance(value,dict):
                self.score={}
                for k in ('collected','delivered'):
                    v=value.get(k)
                    if isinstance(v,int) and not isinstance(v,bool) and v>=0:self.score[k]=v
                for k in ('finished','mock'):
                    if isinstance(value.get(k),bool):self.score[k]=value[k]
                v=value.get('battery')
                if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=60:self.score['battery']=v
                count=self.score.get('collected',0)
                if isinstance(count,int) and count>self.last_count and self.pose:
                    self.collected_positions.append(dict(self.pose))
                self.last_count=count if isinstance(count,int) else self.last_count
    def snapshot(self,session=None):
        with self.lock:
            online=all(time.monotonic()-self.receipts.get(k,0)<2 for k in ('odom','scan','clock','state')) and self.map is not None
            value=dict(connection='online' if online else ('error' if self.error else 'connecting'),session=session or DEFAULT_SESSION,
                       state=self.state,robot_pose=self.pose,robot_yaw=self.yaw,trajectory=self.trajectory,planned_path=self.path,
                       knowledge=self.costs,journal=self.journal[-150:],planner_source=self.planner_source,
                       collected_positions=self.collected_positions,events=self.events,score=self.score,map_revision=self.map['revision'] if self.map else 0,error=self.error)
            value.update(self.state)  # Existing WS MissionState fields remain available.
            return copy.deepcopy(value)

def number(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def point(p):return isinstance(p,dict) and set(p)=={'x','y'} and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in p.values())

class RosRuntime:
    def __init__(self):
        self.cache=PublicCache();self.session=dict(DEFAULT_SESSION);self.process=None;self.log=None;self.thread=None;self.node=None
        self.lock=asyncio.Lock();self.operation_lock=asyncio.Lock();self.closed=False;self.reset_required=False
    async def open(self):
        # Imports are deliberately lazy: health/API remain usable without ROS installed.
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.signals import SignalHandlerOptions
            from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy,ReliabilityPolicy
            from nav_msgs.msg import Odometry,OccupancyGrid
            from sensor_msgs.msg import LaserScan
            from rosgraph_msgs.msg import Clock
            from std_msgs.msg import String
            from std_srvs.srv import Trigger
            from did_agent.config import AgentConfig
            from did_agent.navigation import CoordinateTransform
            from did_agent.sensors import quaternion_yaw
            self.rclpy=rclpy;rclpy.init(signal_handler_options=SignalHandlerOptions.NO);self.node=Node('did_web_bridge')
            cfg=AgentConfig.load(Path('/workspace/DID_hack/configs/agent.json'))
            transform=CoordinateTransform(cfg.odom_x,cfg.odom_y,cfg.odom_yaw)
            def odom(m):
                if m.header.frame_id.lstrip('/')!='odom' or m.child_frame_id.lstrip('/')!='base_footprint':return
                p=m.pose.pose.position;q=m.pose.pose.orientation
                try:pose,yaw=transform.apply(p.x,p.y,quaternion_yaw(q.x,q.y,q.z,q.w))
                except ValueError:return
                if not point(pose) or not math.isfinite(yaw):return
                with self.cache.lock:
                    self.cache.pose=pose;self.cache.yaw=yaw;self.cache.record('odom')
                    if not self.cache.trajectory or math.hypot(pose['x']-self.cache.trajectory[-1]['x'],pose['y']-self.cache.trajectory[-1]['y'])>.03:
                        self.cache.trajectory.append(dict(pose));self.cache.trajectory=self.cache.trajectory[-4000:]
            def scan(m):
                if m.header.frame_id.lstrip('/')=='base_scan' and any(math.isfinite(v) for v in m.ranges):
                    with self.cache.lock:self.cache.record('scan')
            def clock(m):
                t=m.clock.sec+m.clock.nanosec*1e-9
                with self.cache.lock:
                    if self.cache.clock is None or t>self.cache.clock:self.cache.record('clock')
                    self.cache.clock=t
            def map_message(m):
                if m.header.frame_id.lstrip('/')!='map':return
                q=m.info.origin.orientation
                with self.cache.lock:self.cache.map=dict(width=m.info.width,height=m.info.height,resolution=m.info.resolution,
                    origin=dict(x=m.info.origin.position.x,y=m.info.origin.position.y),origin_yaw=quaternion_yaw(q.x,q.y,q.z,q.w),data=list(m.data),revision=1)
            n=self.node
            n.create_subscription(Odometry,'/odom',odom,qos_profile_sensor_data)
            n.create_subscription(LaserScan,'/scan',scan,qos_profile_sensor_data)
            n.create_subscription(Clock,'/clock',clock,qos_profile_sensor_data)
            n.create_subscription(OccupancyGrid,'/map',map_message,QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE))
            for kind,topic in [('state','/did/agent/state'),('journal','/did/agent/journal'),('knowledge','/did/agent/knowledge'),('score','/did/score'),('event','/did/events')]:
                n.create_subscription(String,topic,lambda m,k=kind:self.cache.on_json(k,m.data),10)
            self.clients={c:n.create_client(Trigger,'/did/agent/'+c) for c in ('start','pause','resume','return','stop')}
            self.clients['mock_start']=n.create_client(Trigger,'/did/mock/start');self.trigger=Trigger
            def spin():
                while not self.closed and rclpy.ok():rclpy.spin_once(n,timeout_sec=.1)
            self.thread=threading.Thread(target=spin,daemon=True);self.thread.start()
            await self._launch()
        except Exception as exc:
            self.cache.error='ROS unavailable: '+str(exc)
    async def _launch(self):
        self.cache.clear();self.reset_required=False
        root=Path('/workspace/output');root.mkdir(parents=True,exist_ok=True)
        self.log=open(root/'web-runtime.log','a')
        args=['ros2','launch','did_robot','easy.launch.py','headless:=true','mock_judge:=true','coordinates_verified:=false','autostart:=false']
        args += [k+':='+str(v) for k,v in self.session.items()]
        self.process=await asyncio.create_subprocess_exec(*args,stdout=self.log,stderr=self.log,start_new_session=True)
    async def _stop_process(self):
        if self.process and self.process.returncode is None:
            os.killpg(self.process.pid,signal.SIGINT)
            try:await asyncio.wait_for(self.process.wait(),15)
            except asyncio.TimeoutError:
                os.killpg(self.process.pid,signal.SIGTERM)
                try:await asyncio.wait_for(self.process.wait(),5)
                except asyncio.TimeoutError:os.killpg(self.process.pid,signal.SIGKILL);await self.process.wait()
        self.process=None
        if self.log:self.log.close();self.log=None
    def snapshot(self):
        if self.process and self.process.returncode is not None:self.cache.error='ROS/Gazebo process exited'
        return self.cache.snapshot(self.session)
    async def ready(self,timeout=65):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if self.snapshot()['connection']=='online':return
            if self.cache.error:raise RuntimeError(self.cache.error)
            await asyncio.sleep(.25)
        raise RuntimeError('ROS sensors/map did not become ready')
    async def reset(self,session):
        async with self.lock:
            if self.node is None:raise RuntimeError(self.cache.error or 'ROS unavailable')
            await self._stop_process();await asyncio.sleep(1)
            self.session=dict(session);await self._launch();await self.ready()
            return self.snapshot()
    async def trigger_call(self,name):
        client=self.clients[name]
        if not client.service_is_ready():raise RuntimeError('ROS service unavailable: '+name)
        f=client.call_async(self.trigger.Request());deadline=time.monotonic()+5
        try:
            while not f.done():
                if time.monotonic()>deadline:raise RuntimeError('Service result unknown; reset before retry')
                await asyncio.sleep(.025)
            response=f.result()
            if not response.success:raise RuntimeError(response.message)
        finally:
            if not f.done():client.remove_pending_request(f)
    async def verify_coordinates(self):
        # Only robot world pose is read, never hidden sample/terrain data.
        from rcl_interfaces.srv import SetParameters
        from rcl_interfaces.msg import Parameter,ParameterValue,ParameterType
        from did_agent.config import AgentConfig
        proc=await asyncio.create_subprocess_exec('gz','topic','-e','-t','/world/default/dynamic_pose/info','-n','1','--json-output',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:out,_=await asyncio.wait_for(proc.communicate(),10)
        except asyncio.TimeoutError:
            proc.kill();await proc.wait();raise RuntimeError('Gazebo robot pose unavailable')
        packet=json.loads(out)
        robot=next((p for p in packet.get('pose',[]) if p.get('name')=='burger'),None)
        pose=self.snapshot()['robot_pose'];cfg=AgentConfig.load('/workspace/DID_hack/configs/agent.json')
        if robot is None or pose is None or math.hypot(robot.get('position',{}).get('x',math.inf)-pose['x'],robot.get('position',{}).get('y',math.inf)-pose['y'])>.15 or math.hypot(pose['x']-cfg.base_x,pose['y']-cfg.base_y)>.15:
            raise RuntimeError('Gazebo robot pose disagrees with map/odom/base')
        client=self.node.create_client(SetParameters,'/did_agent/set_parameters')
        try:
            if not client.wait_for_service(timeout_sec=2):raise RuntimeError('Agent parameters unavailable')
            req=SetParameters.Request(parameters=[Parameter(name='coordinates_verified',value=ParameterValue(type=ParameterType.PARAMETER_BOOL,bool_value=True))])
            f=client.call_async(req);end=time.monotonic()+3
            while not f.done() and time.monotonic()<end:await asyncio.sleep(.025)
            if not f.done() or not all(r.successful for r in f.result().results):raise RuntimeError('Coordinate gate rejected')
        finally:self.node.destroy_client(client)
    async def start(self,session):
        if self.snapshot()['state']['status'] not in ('idle','finished','stopped','failed'):raise ValueError('Mission already active')
        if self.session!=session or self.snapshot()['state']['status']!='idle' or self.reset_required:await self.reset(session)
        async with self.lock:
            try:
                await self.ready();await self.verify_coordinates();await self.trigger_call('start');await self.trigger_call('mock_start')
            except Exception:
                self.reset_required=True
                try:await self.trigger_call('stop')
                except Exception:pass
                raise
            await asyncio.sleep(.6);return self.snapshot()
    async def command(self,name):
        async with self.lock:
            if self.snapshot()['connection']!='online' and name!='stop':raise RuntimeError('ROS telemetry stale')
            await self.trigger_call(name);await asyncio.sleep(.6);return self.snapshot()
    async def close(self):
        await self._stop_process();self.closed=True
        if self.thread:self.thread.join(timeout=2)
        if self.node:self.node.destroy_node();self.rclpy.shutdown()
