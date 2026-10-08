"""Kinematic algorithm harness. This is explicitly NOT Gazebo/ROS integration."""
import argparse
import asyncio
from dataclasses import replace
import json
import math
from pathlib import Path
import time
import bootstrap
from did_agent import AgentConfig, RobotState, SafetyManager, NavigationPlanner, WaypointNavigator, MissionManager
from did_environment.mock_judge import MockJudge

class KinematicDemo:
    def __init__(self, seed=1, samples=1, map_file=None, scenario="easy", mode="baseline"):
        self.scenario=scenario;self.mode=mode
        self.config = replace(AgentConfig.load(bootstrap.ROOT/'configs/agent.json'),
                              control_period=0.001,data_timeout=3.0,goal_samples=samples)
        data = [0]*50*50
        for y in range(50):
            for x in range(50):
                if x in (0,49) or y in (0,49) or any(math.hypot(x-a,y-b) < 2 for a,b in ((14,14),(25,25),(35,35))):
                    data[y*50+x] = 100
        self.grid = NavigationPlanner.from_occupancy(50,50,0.1,{'x':-2.5,'y':-2.5},data,self.config.robot_clearance)
        if map_file:
            from did_agent.maps import load_map
            self.grid = load_map(map_file,self.config.robot_clearance)
        self.seed = seed
        self.raw_grid = NavigationPlanner.from_occupancy(50,50,0.1,{'x':-2.5,'y':-2.5},data,0)
        self.physical_grid = NavigationPlanner.from_occupancy(50,50,0.1,{'x':-2.5,'y':-2.5},data,0.105)
        if map_file:
            self.raw_grid = load_map(map_file,0)
            self.physical_grid = load_map(map_file,0.105)
        judge_grid=NavigationPlanner.from_occupancy(50,50,0.1,{'x':-2.5,'y':-2.5},data,MockJudge.SCENARIO_CLEARANCE)
        if map_file:
            judge_grid=load_map(map_file,MockJudge.SCENARIO_CLEARANCE)
        self.judge = MockJudge(judge_grid,self.config,seed,scenario)
        self.robot = RobotState(self.config.obstacle_distance)
        self.pose, self.yaw = dict(self.config.base),0.0
        self.velocity = (0.0,0.0)
        self.sim_time = 0.0
        self.safety = SafetyManager(self.robot,self.config)
        self.navigator = WaypointNavigator(self.robot,self.safety,self.config,self.publish,self.grid)
        self.mission = MissionManager(self.robot,self.navigator,self,self.config,self.safety)
        self.collisions = 0
        self.update()

    def publish(self, linear, angular):
        self.velocity = linear, angular

    def update(self):
        self.sim_time += 0.10
        linear, angular = self.velocity
        self.yaw += angular*0.10
        proposed = {'x':self.pose['x']+linear*math.cos(self.yaw)*0.10,
                    'y':self.pose['y']+linear*math.sin(self.yaw)*0.10}
        if self.physical_grid.segment_free(self.pose,proposed):
            self.pose = proposed
        else:
            self.collisions += 1
        battery, signal = self.judge.observe(self.pose,self.yaw,self.sim_time)
        self.robot.update_clock(self.sim_time)
        self.robot.update('pose',self.pose,self.sim_time,yaw=self.yaw)
        self.robot.update('battery',battery,self.sim_time)
        self.robot.update('signal',signal,self.sim_time)
        # Raw occupancy ray distances, with no added clearance or hidden sample access.
        ranges=[]
        for ray in range(16):
            angle=self.yaw+ray*math.pi/8
            dx,dy=math.cos(angle),math.sin(angle)
            hit=math.inf
            for step in range(1,31):
                d=step*0.05
                p={'x':self.pose['x']+d*dx,'y':self.pose['y']+d*dy}
                if not self.raw_grid.free(self.raw_grid.cell(p)):
                    hit=d
                    break
            ranges.append(hit)
        front=min(ranges[0],ranges[1],ranges[-1])
        self.robot.update('scan',front,self.sim_time,nearest=min(ranges))

    async def collect(self):
        return self.judge.collect(self.pose)

    async def finish(self):
        return self.judge.finish(self.pose)

    async def run(self):
        async def tick():
            while True:
                self.update()
                await asyncio.sleep(self.config.control_period)
        ticker = asyncio.create_task(tick())
        try:
            self.judge.start(self.sim_time)
            await self.mission.start(dict(scenario=self.scenario,seed=self.seed,mode=self.mode))
            await asyncio.wait_for(self.mission.task,45)
            return dict(state=self.mission.state(),score=self.judge.score(),collisions=self.collisions,
                        harness='kinematic algorithms only; NOT ROS/Gazebo')
        finally:
            ticker.cancel()
            await asyncio.gather(ticker,return_exceptions=True)
            await self.navigator.stop()

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario',choices=['easy','medium','hard'],default='easy')
    parser.add_argument('--mode',choices=['baseline','adaptive'],default='baseline')
    parser.add_argument('--seed',type=int,default=1)
    parser.add_argument('--samples',type=int,default=1)
    parser.add_argument('--output')
    parser.add_argument('--map',dest='map_file')
    args=parser.parse_args()
    demo=KinematicDemo(args.seed,args.samples,args.map_file,args.scenario,args.mode)
    result=await demo.run()
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    if args.output:
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(dict(result=result,journal=demo.mission.journal),ensure_ascii=False,indent=2,allow_nan=False))
    if result['state']['status']!='finished' or result['state']['collected']<args.samples or result['collisions']:
        raise SystemExit(1)

if __name__=='__main__':
    asyncio.run(main())
