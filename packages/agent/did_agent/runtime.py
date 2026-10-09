"""Async waypoint execution shared by ROS and kinematic tests."""
from __future__ import annotations
import asyncio
import math
import time
from did_core.types import Point, Result
from .navigation import MotionController, distance
from .battery import BatteryManager

class WaypointNavigator:
    def __init__(self, robot, safety, config, publish, planner=None):
        self.robot, self.safety, self.config, self.publish = robot, safety, config, publish
        self.planner = planner
        self.controller = MotionController(config)
        self.generation = 0
        self.returning = False
        self.battery = BatteryManager(config)
        self.energy=None;self.path=[]

    def plan(self, start: Point, target: Point) -> list[Point]:
        if self.planner is None:
            raise ValueError('Map unavailable')
        self.planner.start_yaw = self.robot.yaw
        return self.planner.plan(start,target)

    def emit(self, linear, angular):
        if self.energy:
            self.energy.note_command(linear,angular,self.robot.clock or 0.)
        self.publish(linear,angular)

    async def stop(self):
        self.generation += 1
        self.emit(0.0,0.0)

    async def follow(self, path: list[Point]) -> Result:
        self.path=list(path)
        token = self.generation
        deadline = time.monotonic()+self.config.motion_timeout
        progress_time = time.monotonic()
        best = math.inf
        next_energy_check = 0.0
        try:
            if not path or self.planner is None:
                return dict(success=False,message='INVALID_TARGET')
            try:
                cells = [self.planner.cell(point) for point in path]
                if not all(self.planner.free(cell) for cell in cells):
                    return dict(success=False,message='INVALID_TARGET')
                for a,b in zip(cells,cells[1:]):
                    dx,dy=b[0]-a[0],b[1]-a[1]
                    if abs(dx)>1 or abs(dy)>1 or (dx and dy and
                        (not self.planner.free((a[0]+dx,a[1])) or not self.planner.free((a[0],a[1]+dy)))):
                        return dict(success=False,message='INVALID_TARGET')
                current=self.robot.snapshot()
                if current is None:
                    return dict(success=False,message='STALE_DATA')
                if distance(current['pose'],path[0])>self.config.goal_tolerance*2:
                    return dict(success=False,message='INVALID_TARGET')
            except (KeyError,TypeError,ValueError):
                return dict(success=False,message='INVALID_TARGET')
            # Adjacent A* centres describe the safe corridor. Execute long
            # collinear segments so cell spacing does not create artificial
            # braking/steering at every 5cm point. Keep every actual bend.
            execution=[path[0]]
            for a,b,c in zip(path,path[1:],path[2:]):
                ux,uy=b['x']-a['x'],b['y']-a['y']
                vx,vy=c['x']-b['x'],c['y']-b['y']
                # Distance alone is not a bend. Artificial 30cm waypoints
                # force centimetre convergence and repeated braking on a
                # straight corridor, exhausting the wall-clock route budget.
                if abs(ux*vy-uy*vx)>1e-10 or ux*vx+uy*vy<0:
                    execution.append(b)
            execution.append(path[-1])
            # Check the whole compressed leg before skipping an off-centre
            # alignment stub; checking only the next adjacent centre does not
            # certify a longer segment near obstacles.
            if len(execution)>2 and distance(execution[0],execution[1])<=self.config.goal_tolerance*2 and self.planner.segment_free(execution[0],execution[2]):
                del execution[1]
            for index,target in enumerate(execution[1:],start=1):
                best = math.inf
                progress_time = time.monotonic()
                while True:
                    if token != self.generation:
                        return dict(success=False,message='CANCELLED')
                    obs = self.robot.snapshot()
                    reason = self.safety.reason()
                    if reason=='STALE_DATA':
                        # Stop immediately; a short DDS/rendering interruption
                        # may recover. Never move using the old observation.
                        self.emit(0.0,0.0)
                        recovery_deadline=min(deadline,time.monotonic()+.5)
                        if self.energy:self.energy.log('Sensor freshness lost: stopped; bounded wait for valid data')
                        while reason=='STALE_DATA' and time.monotonic()<recovery_deadline and token==self.generation:
                            await asyncio.sleep(self.config.control_period)
                            reason=self.safety.reason()
                        if token!=self.generation:return dict(success=False,message='CANCELLED')
                        if reason is None:
                            progress_time=time.monotonic()
                            continue  # Re-read every sensor before calculating motion.
                    if reason or obs is None:
                        return dict(success=False,message=reason or 'STALE_DATA')
                    # Returning has its own established arrival radius. Do not
                    # time out pursuing ordinary waypoints after reaching base.
                    # Freshness and safety must pass before reporting arrival.
                    if self.returning and distance(path[-1],self.config.base)<1e-9 and distance(obs['pose'],self.config.base)<=self.config.base_tolerance:
                        return dict(success=True,message='SUCCESS')
                    self.battery.observe(obs)
                    samples,overflow = self.robot.drain_energy_samples()
                    if self.energy and self.energy.observe(obs,self.robot.yaw,samples,overflow):
                        return dict(success=False,message='REPLAN')
                    if not self.returning and self.planner and time.monotonic() >= next_energy_check:
                        next_energy_check = time.monotonic()+0.5
                        try:
                            home = self.planner.plan(obs['pose'],self.config.base)
                        except ValueError:
                            return dict(success=False,message='NO_RETURN_PATH')
                        if obs['battery'] <= self.battery.required(home):
                            return dict(success=False,message='LOW_RESERVE')
                    remaining = distance(obs['pose'],target)
                    tolerance=self.config.goal_tolerance
                    # A broad waypoint tolerance must not skip a corner whose
                    # next segment cuts occupied cells. Converge to this centre
                    # before turning; keep the actual-segment safety check below.
                    if index < len(execution)-1:
                        tolerance=min(tolerance,self.planner.resolution*0.2)
                    if remaining <= tolerance:
                        break
                    now = time.monotonic()
                    if now >= deadline:
                        return dict(success=False,message='TIMEOUT')
                    if remaining < best-0.01:
                        best, progress_time = remaining, now
                    if now-progress_time > self.config.stuck_timeout:
                        return dict(success=False,message='STUCK')
                    with self.robot.lock:
                        yaw = self.robot.yaw
                    linear, angular = self.controller.command(obs['pose'],yaw,target,tolerance=tolerance)
                    reason = self.safety.reason(linear=linear)
                    if reason:
                        return dict(success=False,message=reason)
                    if linear > 0 and not self.planner.segment_free(obs['pose'],target):
                        return dict(success=False,message='BLOCKED')
                    self.emit(linear,angular)
                    await asyncio.sleep(self.config.control_period)
            return dict(success=True,message='SUCCESS')
        finally:
            self.emit(0.0,0.0)
