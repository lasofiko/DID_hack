"""Real DDS regression: freeze Gazebo clock during motion, require watchdog zero."""
import json
import math
from pathlib import Path
import subprocess
import time
import rclpy
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
from std_srvs.srv import Trigger
from did_agent import AgentConfig, CoordinateTransform
from ament_index_python.packages import get_package_share_directory
from ros_mission import Monitor
from ros_smoke import world_position

class SafetyProbe(Monitor):
    def __init__(self):
        self.commands=[]
        super().__init__()
    def on_command(self,msg):
        super().on_command(msg)
        self.commands.append((msg.twist.linear.x,msg.twist.angular.z))
        self.commands=self.commands[-200:]

def pause(value):
    output=subprocess.check_output(['gz','service','-s','/world/default/control',
        '--reqtype','gz.msgs.WorldControl','--reptype','gz.msgs.Boolean','--timeout','5000',
        '--req','pause: '+str(value).lower()],text=True,timeout=10)
    if 'data: true' not in output:raise RuntimeError('Gazebo pause rejected: '+output)

def main():
    rclpy.init();node=SafetyProbe();result={};paused=False
    try:
        until=time.monotonic()+90
        while time.monotonic()<until and (node.state is None or node.odom is None or node.state.get('observation') is None):
            rclpy.spin_once(node,timeout_sec=.1)
        if node.odom is None:raise RuntimeError('Odom unavailable')
        config=AgentConfig.load(Path(get_package_share_directory('did_robot'))/'config/agent.json')
        p=node.odom.pose.pose.position
        mapped,_=CoordinateTransform(config.odom_x,config.odom_y,config.odom_yaw).apply(p.x,p.y,0.0)
        if math.dist([mapped['x'],mapped['y']],world_position())>.06:raise RuntimeError('Coordinate mismatch')
        param=Parameter(name='coordinates_verified',value=ParameterValue(type=ParameterType.PARAMETER_BOOL,bool_value=True))
        response=node.call('/did_agent/set_parameters',SetParameters,SetParameters.Request(parameters=[param]))
        if not all(r.successful for r in response.results):raise RuntimeError('Parameter rejected')
        response=node.call('/did/agent/start',Trigger,Trigger.Request())
        if not response.success:raise RuntimeError(response.message)
        until=time.monotonic()+20
        while not node.moving_commands and time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.1)
        if not node.moving_commands:raise RuntimeError('Agent never commanded motion')
        pause(True);paused=True;node.commands.clear()
        until=time.monotonic()+3
        while time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.1)
        result.update(state=node.state,commands_after_freeze=node.commands,nonzero_before_freeze=node.moving_commands)
        if len(node.commands)<10 or any(abs(v)+abs(w)>.00001 for v,w in node.commands[-10:]):
            raise RuntimeError('Watchdog did not publish sustained zero')
        if not node.state or node.state['status']!='failed':raise RuntimeError('Mission did not reject frozen sensors')
        result['passed']=True
    except Exception as exc:result.update(passed=False,error=str(exc))
    finally:
        if paused:
            try:pause(False)
            except Exception as exc:result['resume_error']=str(exc)
        result['journal']=node.journal
        Path('/workspace/output/clock-safety.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True);node.destroy_node();rclpy.shutdown()
    if not result.get('passed'):raise SystemExit(1)
if __name__=='__main__':main()
