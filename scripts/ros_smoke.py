"""Real ROS/Gazebo smoke: sensors, TF and optionally measured motion via TwistStamped."""
import argparse
import json
import math
from pathlib import Path
import time
import subprocess
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from rosgraph_msgs.msg import Clock
from geometry_msgs.msg import TwistStamped
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer, TransformListener
from did_agent import AgentConfig, CoordinateTransform
from ament_index_python.packages import get_package_share_directory

class Probe(Node):
    def __init__(self):
        super().__init__('did_runtime_probe',parameter_overrides=[rclpy.parameter.Parameter('use_sim_time',value=True)])
        self.odom=None;self.scan=None;self.clock=None;self.counts={'odom':0,'scan':0,'clock':0};self.edges=set()
        for kind,msg,topic in [('odom',Odometry,'/odom'),('scan',LaserScan,'/scan'),('clock',Clock,'/clock')]:
            self.create_subscription(msg,topic,lambda m,k=kind:self.receive(k,m),qos_profile_sensor_data)
        self.create_subscription(TFMessage,'/tf',self.tf,qos_profile_sensor_data)
        self.create_subscription(TFMessage,'/tf_static',self.tf,QoSProfile(depth=100,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.publisher=self.create_publisher(TwistStamped,'/cmd_vel',10)
        self.buffer=Buffer();self.listener=TransformListener(self.buffer,self)
    def receive(self,kind,msg):
        setattr(self,kind,msg);self.counts[kind]+=1
    def tf(self,msg):
        for t in msg.transforms:self.edges.add((t.header.frame_id,t.child_frame_id))
    def velocity(self,v=0.0):
        msg=TwistStamped();msg.header.stamp=self.get_clock().now().to_msg();msg.header.frame_id='base_link';msg.twist.linear.x=float(v)
        self.publisher.publish(msg)
    def position(self):
        p=self.odom.pose.pose.position
        return [p.x,p.y]

def world_position():
    packet=json.loads(subprocess.check_output(['gz','topic','-e','-n','1','--json-output',
                     '-t','/world/default/dynamic_pose/info'],text=True,timeout=10))
    model=next(p for p in packet['pose'] if p['name']=='burger')
    return [model['position'].get('x',0.0),model['position'].get('y',0.0)]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--move',action='store_true');parser.add_argument('--output',default='/workspace/output/smoke.json');args=parser.parse_args()
    rclpy.init();node=Probe();result={}
    try:
        required={('map','odom'),('odom','base_footprint'),('base_footprint','base_link'),('base_link','base_scan')}
        until=time.monotonic()+60
        while time.monotonic()<until:
            rclpy.spin_once(node,timeout_sec=.1)
            if all(node.counts[k]>=3 for k in node.counts) and required.issubset(node.edges) and node.buffer.can_transform('map','base_scan',rclpy.time.Time()):break
        if not all(node.counts[k]>=3 for k in node.counts):raise RuntimeError('Missing/insufficient sensors: '+str(node.counts))
        result.update(counts=dict(node.counts),odom_frame=node.odom.header.frame_id,odom_child=node.odom.child_frame_id,
                      scan_frame=node.scan.header.frame_id,scan_beams=len(node.scan.ranges),
                      finite_scan_beams=sum(math.isfinite(v) for v in node.scan.ranges),
                      tf_edges=sorted(node.edges),before=node.position(),cmd_type='geometry_msgs/msg/TwistStamped')
        if not result['finite_scan_beams']:raise RuntimeError('Lidar has no finite returns')
        required={('map','odom'),('odom','base_footprint'),('base_footprint','base_link'),('base_link','base_scan')}
        if not required.issubset(node.edges):raise RuntimeError('Disconnected/missing TF: '+str(required-node.edges))
        # Validate composed TF too, not merely that individual edges were published.
        node.buffer.lookup_transform('map','base_scan',rclpy.time.Time())
        config=AgentConfig.load(Path(get_package_share_directory('did_robot'))/'config/agent.json')
        transform=CoordinateTransform(config.odom_x,config.odom_y,config.odom_yaw)
        p,_=transform.apply(*node.position(),0.0)
        result['world_before']=world_position();result['map_before']=[p['x'],p['y']]
        result['coordinate_error_before']=math.dist(result['world_before'],result['map_before'])
        if result['coordinate_error_before']>.06:raise RuntimeError('World/odom transform mismatch')
        if args.move:
            # Require no agent watchdog / competing command publisher during this proof.
            other=[i.node_name for i in node.get_publishers_info_by_topic('/cmd_vel') if i.node_name!=node.get_name()]
            if other:raise RuntimeError('Competing /cmd_vel publishers: '+str(other))
            until=time.monotonic()+4
            while time.monotonic()<until:
                node.velocity(.06);rclpy.spin_once(node,timeout_sec=.05)
            for _ in range(8):node.velocity();rclpy.spin_once(node,timeout_sec=.05)
            result['after']=node.position();result['displacement']=math.dist(result['before'],result['after'])
            if result['displacement']<.025:raise RuntimeError('No measured motion: '+str(result['displacement']))
            result['world_after']=world_position()
            result['physical_displacement']=math.dist(result['world_before'],result['world_after'])
            if result['physical_displacement']<.025:raise RuntimeError('Wheels/odom move but physical robot does not')
        result['passed']=True
    except Exception as exc:
        result.update(passed=False,error=str(exc));raise
    finally:
        for _ in range(3):node.velocity();rclpy.spin_once(node,timeout_sec=.05)
        print(json.dumps(result,indent=2),flush=True)
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n')
        node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
