"""Bounded real Gazebo EASY run; public telemetry only, no judge sample coordinates."""
import argparse
import json
import math
from pathlib import Path
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
from std_srvs.srv import Trigger
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TwistStamped
from ros_smoke import world_position
from did_agent import AgentConfig, CoordinateTransform
from ament_index_python.packages import get_package_share_directory

class Monitor(Node):
    def __init__(self):
        super().__init__('did_mission_probe')
        self.state=None;self.score=None;self.journal=[];self.events=[];self.states=[]
        self.odom=None;self.previous=None;self.distance=0.0;self.moving_commands=0
        self.create_subscription(String,'/did/agent/state',self.on_state,10)
        self.create_subscription(String,'/did/agent/journal',lambda m:setattr(self,'journal',json.loads(m.data)),10)
        self.create_subscription(String,'/did/score',lambda m:setattr(self,'score',json.loads(m.data)),10)
        self.create_subscription(String,'/did/events',lambda m:self.events.append(json.loads(m.data)),10)
        self.create_subscription(Odometry,'/odom',self.on_odom,qos_profile_sensor_data)
        self.create_subscription(TwistStamped,'/cmd_vel',self.on_command,10)
    def on_state(self,msg):
        self.state=json.loads(msg.data)
        status=self.state['status']
        if not self.states or self.states[-1]!=status:
            self.states.append(status);print('MISSION '+status,flush=True)
    def on_odom(self,msg):
        self.odom=msg;point=[msg.pose.pose.position.x,msg.pose.pose.position.y]
        if self.previous:self.distance+=math.dist(point,self.previous)
        self.previous=point
    def on_command(self,msg):
        if abs(msg.twist.linear.x)+abs(msg.twist.angular.z)>0.001:self.moving_commands+=1
    def call(self,name,srv,request,timeout=10):
        client=self.create_client(srv,name)
        try:
            if not client.wait_for_service(timeout_sec=timeout):raise RuntimeError('Unavailable: '+name)
            future=client.call_async(request);until=time.monotonic()+timeout
            while not future.done() and time.monotonic()<until:rclpy.spin_once(self,timeout_sec=.1)
            if not future.done():raise RuntimeError('Service timeout: '+name)
            return future.result()
        finally:self.destroy_client(client)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--timeout',type=float,default=900)
    parser.add_argument('--output',default='/workspace/output/mission.json');args=parser.parse_args()
    rclpy.init();node=Monitor();result={};started=False
    try:
        until=time.monotonic()+90
        while time.monotonic()<until and (node.state is None or node.odom is None or node.state.get('observation') is None):
            rclpy.spin_once(node,timeout_sec=.1)
        if node.odom is None or node.state is None:raise RuntimeError('Agent/odom not ready')
        config=AgentConfig.load(Path(get_package_share_directory('did_robot'))/'config/agent.json')
        pos=node.odom.pose.pose.position
        mapped,_=CoordinateTransform(config.odom_x,config.odom_y,config.odom_yaw).apply(pos.x,pos.y,0.0)
        physical=world_position();error=math.dist([mapped['x'],mapped['y']],physical)
        result.update(coordinate_error=error,world_start=physical)
        if error>.06:raise RuntimeError('Coordinate verification failed')
        parameter=Parameter(name='coordinates_verified',value=ParameterValue(type=ParameterType.PARAMETER_BOOL,bool_value=True))
        response=node.call('/did_agent/set_parameters',SetParameters,SetParameters.Request(parameters=[parameter]))
        if not all(r.successful for r in response.results):raise RuntimeError('Coordinate gate rejected')
        response=node.call('/did/agent/start',Trigger,Trigger.Request())
        result['start_response']={'success':response.success,'message':response.message}
        if not response.success:raise RuntimeError(response.message)
        started=True;until=time.monotonic()+args.timeout;next_print=0
        while time.monotonic()<until:
            rclpy.spin_once(node,timeout_sec=.1)
            if node.state and node.state['status'] in ('finished','failed','stopped'):break
            if time.monotonic()>next_print and node.state:
                next_print=time.monotonic()+20
                obs=node.state.get('observation') or {}
                print(json.dumps({'status':node.state['status'],'pose':obs.get('pose'),'battery':obs.get('battery'),
                                 'signal':obs.get('signal'),'goal':node.state.get('goal')}),flush=True)
        if not node.state or node.state['status']!='finished':raise RuntimeError('Mission did not finish: '+str(node.state))
        # Receive final score and journal after finish callback.
        until=time.monotonic()+2
        while time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.1)
        if node.state['delivered']<1 or not node.score or not node.score.get('finished') or node.score['delivered']<1:
            raise RuntimeError('Finish without sample delivery')
        if node.distance<.5 or node.moving_commands<10:raise RuntimeError('Insufficient physical motion evidence')
        result['world_finish']=world_position()
        result['physical_base_distance']=math.dist(result['world_finish'],[config.base_x,config.base_y])
        if result['physical_base_distance']>config.base_tolerance:raise RuntimeError('Physical robot outside base at finish')
        result['passed']=True
    except Exception as exc:
        result.update(passed=False,error=str(exc));print('ERROR '+str(exc),flush=True)
    finally:
        if started and (not node.state or node.state['status'] not in ('finished','stopped')):
            try:node.call('/did/agent/stop',Trigger,Trigger.Request())
            except Exception as exc:result['stop_error']=str(exc)
        result.update(states=node.states,final_state=node.state,score=node.score,journal=node.journal,
                      events=node.events,odom_distance=node.distance,moving_commands=node.moving_commands)
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,indent=2)+'\n');print('RESULT '+str(path)+' passed='+str(result.get('passed')),flush=True)
        node.destroy_node();rclpy.shutdown()
    if not result.get('passed'):raise SystemExit(1)
if __name__=='__main__':main()
