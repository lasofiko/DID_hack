"""Read-only /cmd_vel capture for Docker graceful shutdown, never publishes motion."""
import argparse
import json
from pathlib import Path
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TwistStamped

def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=30);p.add_argument('--output',default='/workspace/output/shutdown-cmd.jsonl');a=p.parse_args()
    rclpy.init();node=Node('shutdown_cmd_probe')
    with open(a.output,'w') as file:
        def on_cmd(m):
            file.write(json.dumps(dict(wall=time.time(),linear=m.twist.linear.x,angular=m.twist.angular.z))+'\n');file.flush()
        node.create_subscription(TwistStamped,'/cmd_vel',on_cmd,10)
        end=time.monotonic()+a.seconds
        try:
            while time.monotonic()<end and rclpy.ok():rclpy.spin_once(node,timeout_sec=.05)
        except KeyboardInterrupt:pass
        finally:
            node.destroy_node()
            if rclpy.ok():rclpy.shutdown()
if __name__=='__main__':main()
