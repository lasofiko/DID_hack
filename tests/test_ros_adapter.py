"""Execute adapter methods with fake messages, NOT an rclpy/DDS integration test."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap
from did_agent import AgentConfig, RobotState, SafetyManager, CoordinateTransform
from did_agent.sensors import quaternion_yaw as decode_yaw, scan_distances

class FakeTwistStamped:
    def __init__(self):
        self.header=NS(stamp=None,frame_id='')
        self.twist=NS(linear=NS(x=0),angular=NS(z=0))

source=ast.parse((bootstrap.ROOT/'ros2/did_robot/did_robot/agent_node.py').read_text())
selected=[n for n in source.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in ('AgentNode','quaternion_yaw','seconds')]
namespace=dict(Node=object,TwistStamped=FakeTwistStamped,math=math,time=time,decode_yaw=decode_yaw,scan_distances=scan_distances)
exec(compile(ast.Module(body=selected,type_ignores=[]),'<ROS adapter methods with fakes>','exec'),namespace)
AgentNode=namespace['AgentNode']

class AdapterTests(unittest.TestCase):
    def node(self):
        node=AgentNode.__new__(AgentNode)
        node.config=AgentConfig();node.robot=RobotState();node.safety=SafetyManager(node.robot,node.config)
        node.transform=CoordinateTransform()
        node.robot.update_clock(1)
        node.robot.update('pose',node.config.base,1,yaw=0)
        node.robot.update('battery',60,1);node.robot.update('signal',0,1)
        node.robot.update('scan',math.inf,1,nearest=math.inf)
        node.command_lock=threading.RLock();node.motion_inhibit=False;node.last_command=(0,0);node.command_time=time.monotonic()
        node.mission=NS(state=lambda:{'status':'running'})
        node.get_logger=lambda:NS(error=lambda x:None)
        node.get_clock=lambda:NS(now=lambda:NS(to_msg=lambda:'sim_stamp'))
        self.messages=[];node.publisher=NS(publish=self.messages.append)
        return node

    def test_twiststamped_type_stamp_frame_and_values(self):
        node=self.node();node.publish_velocity(.1,0)
        msg=self.messages[-1]
        self.assertIsInstance(msg,FakeTwistStamped)
        self.assertEqual(msg.header.stamp,'sim_stamp');self.assertEqual(msg.header.frame_id,'base_link')
        self.assertEqual(msg.twist.linear.x,.1);self.assertEqual(msg.twist.angular.z,0)
        node.publish_velocity(0,-.2)
        self.assertEqual(self.messages[-1].twist.angular.z,-.2)
        node.set_velocity(.1,-.2)
        self.assertEqual(node.last_command,(0,0))
        node.publish_velocity(.1,-.2)
        self.assertEqual(self.messages[-1].twist.linear.x,0)
        node.publish_velocity(0,0)
        self.assertIsInstance(self.messages[-1].twist.linear.x,float)
        self.assertIsInstance(self.messages[-1].twist.angular.z,float)

    def test_nonfinite_command_stops_instead_of_clamping_to_max(self):
        node=self.node();node.set_velocity(math.nan,math.inf)
        self.assertEqual(node.last_command,(0,0));self.assertEqual(self.messages[-1].twist.linear.x,0)
        node.last_command=(math.nan,math.nan);node.watchdog()
        self.assertEqual(self.messages[-1].twist.linear.x,0);self.assertEqual(self.messages[-1].twist.angular.z,0)

    def test_watchdog_missing_data_or_inhibit_zero(self):
        node=self.node();node.robot.values.clear();node.last_command=(.1,.2);node.watchdog()
        self.assertEqual(self.messages[-1].twist.linear.x,0)
        node.motion_inhibit=True;node.watchdog();self.assertEqual(self.messages[-1].twist.angular.z,0)

    def test_wrong_odom_frame_revokes_pose(self):
        node=self.node()
        node.on_odom(NS(header=NS(frame_id='map',stamp=NS(sec=1,nanosec=0)),child_frame_id='base_footprint'))
        self.assertNotIn('pose',node.robot.values)

    def test_valid_odom_explicit_offset_once(self):
        node=self.node()
        pose=NS(position=NS(x=1,y=.2),orientation=NS(x=0,y=0,z=0,w=1))
        node.on_odom(NS(header=NS(frame_id='odom',stamp=NS(sec=1,nanosec=0)),child_frame_id='base_footprint',pose=NS(pose=pose)))
        point=node.robot.values['pose'][0]
        self.assertAlmostEqual(point['x'],-1);self.assertAlmostEqual(point['y'],-.3)

    def test_wrong_lidar_frame_revokes_scan(self):
        node=self.node()
        node.on_scan(NS(header=NS(frame_id='other_lidar',stamp=NS(sec=1,nanosec=0))))
        self.assertNotIn('scan',node.robot.values)

    def test_watchdog_expired_command_and_finished_state(self):
        node=self.node();node.last_command=(.1,.2);node.command_time=0;node.watchdog()
        self.assertEqual(self.messages[-1].twist.linear.x,0)
        node.command_time=time.monotonic();node.mission=NS(state=lambda:{'status':'finished'});node.watchdog()
        self.assertEqual(self.messages[-1].twist.angular.z,0)
