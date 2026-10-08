"""Start a fresh own web mission and record commands; host then stops this Compose."""
import json
from pathlib import Path
import time
import urllib.request
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TwistStamped

rclpy.init();node=Node('shutdown_start_probe');first=False
with open('/workspace/output/shutdown-active-cmd.jsonl','w') as handle:
    def receive(m):
        global first
        row=dict(wall=time.time(),linear=m.twist.linear.x,angular=m.twist.angular.z)
        handle.write(json.dumps(row)+'\n');handle.flush()
        if not first and (row['linear'] or row['angular']):
            first=True
            Path('/workspace/output/shutdown-active-marker.json').write_text(json.dumps(row))
            print('NONZERO_CAPTURED',flush=True)
    node.create_subscription(TwistStamped,'/cmd_vel',receive,10)
    end=time.monotonic()+40
    while time.monotonic()<end:
        try:
            req=urllib.request.Request('http://127.0.0.1:8000/api/missions',data=json.dumps(dict(scenario='easy',seed=1,mode='baseline',planner_mode='algorithmic')).encode(),headers={'Content-Type':'application/json'})
            response=urllib.request.urlopen(req,timeout=90)
            print(response.status,json.load(response)['status'],flush=True);break
        except urllib.error.URLError as exc:
            # Only retry connection establishment; never retry an HTTP service rejection.
            if isinstance(exc,urllib.error.HTTPError):raise
            time.sleep(.5)
    try:
        end=time.monotonic()+60
        while time.monotonic()<end and rclpy.ok():rclpy.spin_once(node,timeout_sec=.05)
    except KeyboardInterrupt:pass
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
