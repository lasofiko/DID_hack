"""Explicit opt-in EASY mock. Do not run beside an official judge."""
import json
import os
import math
from pathlib import Path
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, qos_profile_sensor_data
from nav_msgs.msg import Odometry, OccupancyGrid
from std_msgs.msg import Float32, String
from std_srvs.srv import Trigger
from ament_index_python.packages import get_package_share_directory
from did_agent import AgentConfig, CoordinateTransform, NavigationPlanner
from did_environment.mock_judge import MockJudge
from .agent_node import quaternion_yaw

class JudgeNode(Node):
    def __init__(self):
        super().__init__('did_mock_judge')
        self.declare_parameter('config_file',str(Path(get_package_share_directory('did_robot'))/'config/agent.json'))
        self.declare_parameter('seed',1)
        self.declare_parameter('scenario','easy')
        self.config=AgentConfig.load(self.get_parameter('config_file').value)
        self.transform=CoordinateTransform(self.config.odom_x,self.config.odom_y,self.config.odom_yaw)
        self.private_count=0
        self.pose=None;self.yaw=0.0;self.pose_received=0.0;self.judge=None
        self.battery_pub=self.create_publisher(Float32,'/did/battery',10)
        self.signal_pub=self.create_publisher(Float32,'/did/sample_sensor',10)
        self.score_pub=self.create_publisher(String,'/did/score',10)
        self.event_pub=self.create_publisher(String,'/did/events',10)
        self.create_subscription(Odometry,'/odom',self.on_odom,qos_profile_sensor_data)
        qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(OccupancyGrid,'/map',self.on_map,qos)
        self.create_service(Trigger,'/did/collect',self.collect)
        self.create_service(Trigger,'/did/finish',self.finish)
        self.create_service(Trigger,'/did/mock/start',self.start)
        self.create_timer(0.1,self.tick)
        self.get_logger().warning('LOCAL MOCK rules; pose derived independently from odom. Not official judge/score.')

    def on_odom(self,message):
        p=message.pose.pose.position
        pose,yaw=self.transform.apply(p.x,p.y,quaternion_yaw(message.pose.pose.orientation))
        if not all(math.isfinite(v) for v in (pose['x'],pose['y'],yaw)):
            self.pose=None
            return
        self.pose,self.yaw=pose,yaw
        self.pose_received=time.monotonic()
        # Integrate each odometry segment; sensor noise only generated on tick.
        if self.judge:
            self.judge.observe(self.pose,self.yaw,self.get_clock().now().nanoseconds*1e-9)

    def on_map(self,message):
        if self.judge or message.header.frame_id.lstrip('/')!='map':return
        o=message.info.origin
        try:
            grid=NavigationPlanner.from_occupancy(message.info.width,message.info.height,message.info.resolution,
                   {'x':o.position.x,'y':o.position.y},list(message.data),MockJudge.SCENARIO_CLEARANCE,quaternion_yaw(o.orientation))
            self.judge=MockJudge(grid,self.config,self.get_parameter('seed').value,self.get_parameter('scenario').value)
        except ValueError as exc:self.get_logger().error(str(exc))

    def ready(self):
        return self.judge is not None and self.pose is not None and time.monotonic()-self.pose_received <= self.config.data_timeout

    def tick(self):
        if not self.ready():return
        battery,signal=self.judge.observe(self.pose,self.yaw,self.get_clock().now().nanoseconds*1e-9)
        self.battery_pub.publish(Float32(data=float(battery)))
        self.signal_pub.publish(Float32(data=float(signal)))
        self.score_pub.publish(String(data=json.dumps(self.judge.score(),allow_nan=False)))
        # Private debug artifact is not an HTTP route or ROS topic.
        private_path=os.environ.get('DID_JUDGE_PRIVATE_LOG')
        if private_path and len(self.judge._private_events)>self.private_count:
            with open(private_path,'a') as handle:
                for e in self.judge._private_events[self.private_count:]:handle.write(json.dumps(dict(scenario=self.judge.scenario,seed=self.get_parameter('seed').value,**e))+'\n')
            self.private_count=len(self.judge._private_events)
        while self.judge.events:
            event=self.judge.events.pop(0)
            self.event_pub.publish(String(data=json.dumps(event)))

    def collect(self,request,response):
        result=self.judge.collect(self.pose) if self.ready() else dict(success=False,message='No fresh judge pose/map')
        response.success,response.message=result['success'],result['message']
        return response

    def start(self,request,response):
        response.success=self.ready()
        response.message='Mock clock started' if response.success else 'Mock not ready'
        if response.success:self.judge.start(self.get_clock().now().nanoseconds*1e-9)
        return response

    def finish(self,request,response):
        result=self.judge.finish(self.pose) if self.ready() else dict(success=False,message='No fresh judge pose/map')
        response.success,response.message=result['success'],result['message']
        return response

def main():
    rclpy.init();node=JudgeNode()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
