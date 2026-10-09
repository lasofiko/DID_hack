"""Run ONE bounded isolated ROS/Gazebo mission using public HTTP/ROS telemetry.

Execute inside the dedicated DID container. --short is a stop/zero smoke test,
not a delivery experiment. Never launch on a shared ROS domain or live mission.
"""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import signal
import time
import rclpy
from ament_index_python.packages import get_package_share_directory
from did_agent import AgentConfig
from did_agent.navigation import wrap
from ros_mission import Monitor
from ros_smoke import world_position
from web_check import request


class MetricsMonitor(Monitor):
    def __init__(self):
        super().__init__()
        self.rotation = 0.; self.turns = 0; self.previous_yaw = None
        self.last_angular = 0.; self.commands = []; self.measure = False

    def on_odom(self, msg):
        if not self.measure:
            self.odom = msg
            return
        super().on_odom(msg)
        q=msg.pose.pose.orientation
        yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
        if self.previous_yaw is not None:
            self.rotation += abs(wrap(yaw-self.previous_yaw))
        self.previous_yaw=yaw

    def on_command(self, msg):
        super().on_command(msg)
        v,w=msg.twist.linear.x,msg.twist.angular.z
        self.commands.append((time.monotonic(),v,w))
        if self.measure and w and not self.last_angular:
            self.turns += 1
        self.last_angular=w


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario',choices=['easy','medium'],default='easy')
    p.add_argument('--seed',type=int,choices=[1,2],default=1)
    p.add_argument('--mode',choices=['baseline','adaptive'],default='baseline')
    p.add_argument('--seconds',type=float,default=900.)
    p.add_argument('--short',action='store_true')
    p.add_argument('--revision',required=True,help='Git SHA of installed tested code')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not math.isfinite(a.seconds) or not 0<a.seconds<=900:
        p.error('--seconds must be in (0, 900]')
    session=dict(scenario=a.scenario,seed=a.seed,mode=a.mode,planner_mode='algorithmic')
    report=dict(harness='ROS/Gazebo physical simulation with local mock judge; NOT official judge',
                session=session,revision=a.revision,short=a.short,passed=False,
                checks_scope='return/stop and reported events only; independent physical contacts not instrumented')
    node=None;start_wall=start_sim=initial_battery=None
    def interrupt(signum, frame):
        raise KeyboardInterrupt('External signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupt)
    try:
        # API reset owns its Gazebo child; caller must provide a dedicated container/domain.
        request('/api/missions/reset',session)
        rclpy.init()
        config=AgentConfig.load(Path(get_package_share_directory('did_robot'))/'config/agent.json')
        report['config']=asdict(config)
        node=MetricsMonitor()
        until=time.monotonic()+30
        while time.monotonic()<until and (not node.state or not node.state.get('observation') or node.odom is None):
            rclpy.spin_once(node,timeout_sec=.1)
        if not node.state or not node.state.get('observation') or node.odom is None:
            raise RuntimeError('Telemetry unavailable')
        initial_battery=node.state['observation']['battery']
        report['world_start']=world_position()
        response=request('/api/missions',session)
        start_wall=time.monotonic();start_sim=response['observation']['sim_time']
        node.measure=True
        until=start_wall+a.seconds
        while time.monotonic()<until:
            rclpy.spin_once(node,timeout_sec=.1)
            # Require this run's UUID, not the last cached idle state.
            if node.state and node.state.get('run_id')==response['run_id'] and node.state['status'] in ('finished','failed','stopped'):
                break
        else:
            report['external_limit_reached']=True
            if not a.short:report['error']='External mission deadline'
        report['elapsed_wall_s']=time.monotonic()-start_wall
        report['elapsed_sim_s']=(node.state.get('observation') or {}).get('sim_time',start_sim)-start_sim
    except (Exception,KeyboardInterrupt) as exc:
        report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if node:
            try:
                latest=request('/api/state')
                if latest['status'] in ('running','returning','paused'):
                    request('/api/command',dict(command='stop'))
            except Exception as exc:
                report['stop_error']=str(exc)
            # Observe post-stop commands, with bounded settling, never infer zero
            # from absence of telemetry or from a successful HTTP response alone.
            stopped=time.monotonic();until=stopped+2.5
            while time.monotonic()<until:
                rclpy.spin_once(node,timeout_sec=.1)
            zeros=[(v,w) for t,v,w in node.commands if t>=stopped+.5]
            report['zero_command_count']=len(zeros)
            report['zero_verified']=len(zeros)>=5 and all(v==0 and w==0 for v,w in zeros)
            state=node.state or {};obs=state.get('observation') or {}
            delivered=state.get('delivered',0);collected=state.get('collected',0)
            used=initial_battery-obs['battery'] if initial_battery is not None and 'battery' in obs else None
            try:
                report['world_finish']=world_position()
                report['physical_base_distance_m']=math.dist(report['world_finish'],[config.base_x,config.base_y])
                report['world_odom_error_m']=math.dist(report['world_finish'],[obs['pose']['x'],obs['pose']['y']])
            except Exception as exc:report['world_pose_error']=str(exc)
            report.update(final_state=state,score=node.score,journal=node.journal,events=node.events,
                collected=collected,delivered=delivered,delivered_fraction=delivered/collected if collected else None,
                battery_used=used,energy_per_delivered=used/delivered if delivered and used is not None else None,
                route_length_m=node.distance,rotation_rad=node.rotation,turns=node.turns,
                replans=sum(e['stage']=='replan' for e in node.journal),
                elapsed_sim_s=report.get('elapsed_sim_s'),
                collisions=None,  # No independent Gazebo contact instrumentation in this probe.
                reported_collision_events=sum(e.get('type')=='collision' for e in node.events),
                return_success=state.get('status')=='finished' and report.get('physical_base_distance_m',math.inf)<=config.base_tolerance,
                termination_reason=report.get('error') or next((e['text'] for e in reversed(node.journal) if e['text'].startswith('Failure:')),state.get('status')))
            success=report['return_success'] and delivered>0
            if a.short:success=node.distance>.05 and state.get('status') in ('stopped','finished')
            report['passed']=success and report['zero_verified'] and not report['reported_collision_events'] and not report.get('error') and not report.get('stop_error') and not report.get('world_pose_error')
            node.destroy_node();rclpy.shutdown()
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        print('RESULT '+str(a.output)+' passed='+str(report['passed']),flush=True)
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
