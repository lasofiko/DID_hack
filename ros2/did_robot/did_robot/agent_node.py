"""ROS 2 Jazzy adapter. Runtime verification still required on Ubuntu."""
import asyncio
import json
import math
import os
from pathlib import Path
import threading
import signal
import time

import rclpy
from rclpy.signals import SignalHandlerOptions
from rclpy.node import Node
from rclpy.clock import Clock, ClockType
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, qos_profile_sensor_data
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry, OccupancyGrid
from sensor_msgs.msg import LaserScan
from rosgraph_msgs.msg import Clock as ClockMsg
from std_msgs.msg import Float32, String
from std_srvs.srv import Trigger
from ament_index_python.packages import get_package_share_directory

from did_agent.sensors import scan_distances, quaternion_yaw as decode_yaw
from did_agent import AgentConfig, RobotState, SafetyManager, CoordinateTransform, NavigationPlanner, WaypointNavigator, MissionManager


def seconds(stamp):
    return stamp.sec + stamp.nanosec*1e-9


def quaternion_yaw(q):
    return decode_yaw(q.x,q.y,q.z,q.w)


class AgentNode(Node):
    def __init__(self):
        super().__init__('did_agent')
        default = str(Path(get_package_share_directory('did_robot'))/'config/agent.json')
        self.declare_parameter('config_file',default)
        self.declare_parameter('coordinates_verified',False)
        self.declare_parameter('autostart',False)
        self.declare_parameter('seed',1)
        self.declare_parameter('scenario','easy')
        self.declare_parameter('mode','baseline')
        self.declare_parameter('planner_mode','algorithmic')
        self.config = AgentConfig.load(self.get_parameter('config_file').value)
        self.transform = CoordinateTransform(self.config.odom_x,self.config.odom_y,self.config.odom_yaw)
        self.robot = RobotState(self.config.obstacle_distance)
        self.safety = SafetyManager(self.robot,self.config)
        self.group = ReentrantCallbackGroup()
        self.sensor_group = MutuallyExclusiveCallbackGroup()
        self.command_group = MutuallyExclusiveCallbackGroup()
        self.publisher = self.create_publisher(TwistStamped,'/cmd_vel',10)
        self.state_publisher = self.create_publisher(String,'/did/agent/state',10)
        self.journal_publisher = self.create_publisher(String,'/did/agent/journal',10)
        self.command_lock = threading.RLock()
        self.last_command = (0.0,0.0)
        self.command_time = 0.0
        self.motion_inhibit = True
        self.navigator = WaypointNavigator(self.robot,self.safety,self.config,self.set_velocity)
        self.collect_client = self.create_client(Trigger,'/did/collect',callback_group=self.group)
        self.finish_client = self.create_client(Trigger,'/did/finish',callback_group=self.group)
        self.mission = MissionManager(self.robot,self.navigator,self,self.config,self.safety)
        self.mission.journal_sink=os.environ.get('DID_AGENT_JOURNAL_LOG')
        from did_agent.plugins import load_plugin
        from did_agent.plugins import PlannerRuntime
        self.planner_runtime = PlannerRuntime(self.get_logger().error)
        from did_ml.factory import make_energy_model
        def energy_factory():
            try:
                if os.environ.get('DID_ENERGY_FACTORY','') in ('','did_ml.factory:create_energy_model'):
                    return make_energy_model(self.config)
                return load_plugin('DID_ENERGY_FACTORY',['update','update_turn','estimate','estimate_turn','estimate_energy']) or make_energy_model(self.config)
            except Exception:
                self.get_logger().error('Energy factory unavailable; using Maria EnergyModel')
                return make_energy_model(self.config)
        self.mission.energy_factory=energy_factory
        self.knowledge_publisher=self.create_publisher(String,'/did/agent/knowledge',10)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever,daemon=True)
        self.thread.start()
        self.start_lock = threading.Lock()
        self.create_subscription(Odometry,'/odom',self.on_odom,qos_profile_sensor_data,callback_group=self.sensor_group)
        self.create_subscription(LaserScan,'/scan',self.on_scan,qos_profile_sensor_data,callback_group=self.sensor_group)
        self.create_subscription(ClockMsg,'/clock',self.on_clock,qos_profile_sensor_data,callback_group=self.sensor_group)
        self.create_subscription(Float32,'/did/battery',lambda m:self.on_scalar('battery',m),10,callback_group=self.sensor_group)
        self.create_subscription(Float32,'/did/sample_sensor',lambda m:self.on_scalar('signal',m),10,callback_group=self.sensor_group)
        self.create_subscription(String,'/did/events',self.on_event,10,callback_group=self.sensor_group)
        self.create_subscription(String,'/did/score',self.on_score,10,callback_group=self.sensor_group)
        map_qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(OccupancyGrid,'/map',self.on_map,map_qos,callback_group=self.sensor_group)
        self.create_service(Trigger,'/did/agent/start',self.start_service,callback_group=self.command_group)
        for command in ('pause','resume','return','stop'):
            self.create_service(Trigger,'/did/agent/'+command,
                                lambda req,res,c=command:self.command_service(c,res),callback_group=self.command_group)
        # Steady clock survives paused /clock: zero velocity is published on stale data.
        self.steady = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(self.config.control_period,self.watchdog,clock=self.steady,callback_group=self.group)
        self.create_timer(0.5,self.telemetry,clock=self.steady,callback_group=self.group)
        self.last_status = None
        self.autostart_attempted = False
        self.get_logger().info('Ready; coordinates_verified=false blocks mission start. Mock judge is separate.')

    def on_clock(self,message):
        self.robot.update_clock(seconds(message.clock))

    def on_odom(self,message):
        if message.header.frame_id.lstrip('/') != 'odom' or message.child_frame_id.lstrip('/') != 'base_footprint':
            self.robot.update('pose',{},seconds(message.header.stamp),yaw=math.nan)
            self.get_logger().error('Unexpected odom frame; explicit transform requires odom/base_footprint')
            return
        position=message.pose.pose.position
        yaw=quaternion_yaw(message.pose.pose.orientation)
        pose,yaw=self.transform.apply(position.x,position.y,yaw)
        self.robot.update('pose',pose,seconds(message.header.stamp),yaw=yaw)

    def on_scalar(self,kind,message):
        with self.robot.lock:
            stamp=self.robot.clock
        if stamp is not None:
            self.robot.update(kind,float(message.data),stamp)

    def on_scan(self,message):
        if message.header.frame_id.lstrip('/') != 'base_scan':
            self.robot.update('scan',math.nan,seconds(message.header.stamp),nearest=math.nan)
            self.get_logger().error('Expected base_scan frame; verify lidar-to-base orientation')
            return
        front, nearest = scan_distances(message.ranges,message.angle_min,message.angle_increment,
                                        message.range_min,message.range_max)
        self.robot.update('scan',front,seconds(message.header.stamp),nearest=nearest)

    def on_map(self,message):
        if message.header.frame_id.lstrip('/') != 'map':
            self.get_logger().error('Map frame must be map')
            return
        if self.mission.state()['status'] in ('running','paused','returning'):
            return  # Static map is fixed during a mission; dynamic obstacles are local.
        origin=message.info.origin
        try:
            planner=NavigationPlanner.from_occupancy(message.info.width,message.info.height,message.info.resolution,
                    {'x':origin.position.x,'y':origin.position.y},list(message.data),self.config.robot_clearance,
                    quaternion_yaw(origin.orientation))
            planner.plan(self.config.base,self.config.base)
        except ValueError as exc:
            self.get_logger().error('Map rejected: '+str(exc))
            return
        self.navigator.planner=planner
        self.get_logger().info('Static occupancy map ready')

    def on_event(self,message):
        try:
            event=json.loads(message.data)
            if not isinstance(event,dict):
                return
            self.robot.add_event(event)
            if event.get('type',event.get('event')) in ('collision','hazard_hit'):
                self.safety.emergency=True
                self.set_velocity(0.0,0.0)
                self.get_logger().error('Emergency: '+message.data)
        except (ValueError,TypeError):
            self.get_logger().warning('Invalid /did/events JSON')

    def on_score(self,message):
        # Score is diagnostic; hidden/extra fields must never reach planner observations.
        try:
            value=json.loads(message.data)
            if isinstance(value,dict) and value.get('finished'):
                self.safety.emergency=True
                self.set_velocity(0.0,0.0)
        except ValueError:
            self.get_logger().warning('Invalid /did/score JSON')

    def set_velocity(self,linear,angular):
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (linear,angular)):
            linear=angular=0.0
        if linear and angular:
            linear=angular=0.0
        with self.command_lock:
            self.last_command=(linear,angular)
            self.command_time=time.monotonic()
            if linear == 0 and angular == 0:
                self.publish_velocity(0.0,0.0)

    def publish_velocity(self,linear,angular):
        if linear and angular:
            linear=angular=0.0
        energy=getattr(getattr(self,'navigator',None),'energy',None)
        if energy:
            energy.note_command(linear,angular,self.robot.clock or 0.)
        message=TwistStamped()
        message.header.stamp=self.get_clock().now().to_msg()
        message.header.frame_id='base_link'
        # Jazzy rosidl's C converter requires Python float, even for numeric 0.
        message.twist.linear.x=float(linear)
        message.twist.angular.z=float(angular)
        self.publisher.publish(message)

    def watchdog(self):
        with self.command_lock:
            linear,angular=self.last_command
            if not all(math.isfinite(v) for v in (linear,angular)):
                linear=angular=0.0
            status=self.mission.state()['status']
            if self.motion_inhibit or status not in ('running','returning') or self.safety.reason(linear=linear) or time.monotonic()-self.command_time > 0.30:
                linear=angular=0.0
            linear=max(0.0,min(self.config.max_linear,linear))
            angular=max(-self.config.max_angular,min(self.config.max_angular,angular))
            self.publish_velocity(linear,angular)

    async def call_service(self,client):
        if not client.service_is_ready():
            return dict(success=False,message='Service unavailable')
        future=client.call_async(Trigger.Request())
        try:
            while not future.done():
                await asyncio.sleep(self.config.control_period)
            result=future.result()
            return dict(success=result.success,message=result.message)
        finally:
            if not future.done():
                # Removal prevents dangling local futures; it cannot undo server execution.
                client.remove_pending_request(future)

    async def collect(self):
        return await self.call_service(self.collect_client)

    async def finish(self):
        return await self.call_service(self.finish_client)

    async def _start_mission(self, request):
        if self.mission.state()['status'] not in ('idle', 'finished', 'stopped', 'failed'):
            raise ValueError('Mission already active')
        # Factory and HTTP client enter on the same loop as propose/cleanup.
        # Algorithmic mode never initializes a client or reads its credentials.
        if request['planner_mode'] == 'llm':
            self.mission.planner = await self.planner_runtime.open()
        else:
            self.mission.planner = None
        return await self.mission.start(request)

    def start_service(self,request,response):
        if not self.get_parameter('coordinates_verified').value:
            response.success=False;response.message='Verify Gazebo pose/odom/map, then set coordinates_verified:=true'
            return response
        if not self.start_lock.acquire(blocking=False):
            response.success=False;response.message='Start already in progress';return response
        future=None
        try:
            future=asyncio.run_coroutine_threadsafe(self._start_mission(dict(scenario=self.get_parameter('scenario').value,mode=self.get_parameter('mode').value,
                                                    seed=self.get_parameter('seed').value,planner_mode=self.get_parameter('planner_mode').value)),self.loop)
            future.result(timeout=3.0)
            with self.command_lock:
                self.motion_inhibit=self.safety.emergency or self.mission.state()['status'] not in ('running','returning')
            response.success=True;response.message='Mission started'
        except Exception as exc:
            if future and not future.done():future.cancel()
            response.success=False;response.message=str(exc)
        finally:
            self.start_lock.release()
        return response

    def command_service(self,command,response):
        # Inhibit in the ROS callback immediately, even if async planning is busy.
        if command in ('pause','stop','return'):
            with self.command_lock:
                self.motion_inhibit=True
                self.last_command=(0.0,0.0)
                self.publish_velocity(0.0,0.0)
        try:
            future=asyncio.run_coroutine_threadsafe(self.mission.command(command),self.loop)
            future.result(timeout=1.0)
            if command in ('resume','return'):
                with self.command_lock:
                    self.motion_inhibit=False
            response.success=True;response.message='Command accepted: '+command
        except Exception as exc:
            response.success=False;response.message=str(exc)
        return response

    def telemetry(self):
        state=self.mission.state()
        self.state_publisher.publish(String(data=json.dumps(state,allow_nan=False)))
        self.journal_publisher.publish(String(data=json.dumps(self.mission.journal[-50:],allow_nan=False)))
        self.knowledge_publisher.publish(String(data=json.dumps(dict(path=list(self.navigator.path),
            costs=self.navigator.energy.public() if self.navigator.energy else [],
            energy_diagnostics=self.navigator.energy.diagnostics() if self.navigator.energy else None,planner_source=self.mission.planner_source),allow_nan=False)))
        if state['status'] != self.last_status:
            self.get_logger().info('[MISSION] state='+state['status'])
            self.last_status=state['status']
        if self.get_parameter('autostart').value and not self.autostart_attempted and self.navigator.planner and self.robot.fresh(self.config.data_timeout):
            self.autostart_attempted=True
            result=self.start_service(None,Trigger.Response())
            if not result.success:
                self.get_logger().error(result.message)

    def close(self):
        with self.command_lock:
            self.motion_inhibit=True
            self.last_command=(0.0,0.0)
            self.publish_velocity(0.0,0.0)
        async def stop():
            if self.mission.task and not self.mission.task.done():
                self.mission.task.cancel()
                await asyncio.gather(self.mission.task,return_exceptions=True)
            await self.navigator.stop()
            await self.planner_runtime.close()
        try:
            asyncio.run_coroutine_threadsafe(stop(),self.loop).result(timeout=2)
        finally:
            self.publish_velocity(0.0,0.0)
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=2)
            if not self.thread.is_alive():
                self.loop.close()


def main():
    # Keep context valid until zero commands are sent on SIGINT/SIGTERM.
    def terminate(signum, frame):
        raise KeyboardInterrupt
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT,terminate)
    signal.signal(signal.SIGTERM,terminate)
    node=AgentNode()
    executor=MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        while rclpy.ok():
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        # Stop while context/publisher still exists.
        if rclpy.ok():
            node.close()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
