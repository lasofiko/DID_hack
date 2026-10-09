import asyncio
from dataclasses import replace
import math
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap
from did_agent import *
from did_agent.navigation import distance
from demo_easy import KinematicDemo

class NavigationTests(unittest.TestCase):
    def test_detour_and_costs(self):
        p=NavigationPlanner(7,7,1,{'x':0,'y':0},{(3,y) for y in range(6)})
        path=p.plan({'x':1.5,'y':1.5},{'x':5.5,'y':1.5})
        self.assertTrue(all(p.free(p.cell(q)) for q in path))
        self.assertTrue(any(q['y']>=6 for q in path))
        p=NavigationPlanner(7,3,1,{'x':0,'y':0},costs={(x,1):20 for x in (2,3,4)})
        path=p.plan({'x':0.5,'y':1.5},{'x':6.5,'y':1.5})
        self.assertFalse(any(p.cell(q) in p.costs for q in path))

    def test_invalid_disconnected_and_corner(self):
        p=NavigationPlanner(3,3,1,{'x':0,'y':0},{(1,0),(0,1)})
        for target in ({'x':2.5,'y':2.5},{'x':-1,'y':0},{'x':math.nan,'y':0}):
            with self.assertRaises(ValueError):p.plan({'x':0.5,'y':0.5},target)

    def test_inflation_unknown_and_rotated_origin(self):
        p=NavigationPlanner.from_occupancy(7,7,0.1,{'x':0,'y':0},[100 if i==24 else 0 for i in range(49)],0.15)
        self.assertFalse(p.free((3,4)))
        self.assertFalse(p.free((0,0)))
        self.assertTrue(p.free((1,1)))
        p=NavigationPlanner.from_occupancy(3,3,1,{'x':0,'y':0},[-1]+[0]*8,0)
        self.assertFalse(p.free((0,0)))
        p=NavigationPlanner(4,4,0.2,{'x':-2,'y':-1},origin_yaw=math.pi/2)
        for c in ((0,0),(2,3)):
            self.assertEqual(p.cell(p.point(c)),c)

    def test_transform_and_controller(self):
        pose,yaw=CoordinateTransform(-2,-.5,math.pi/2).apply(1,0,0)
        self.assertAlmostEqual(pose['x'],-2)
        self.assertAlmostEqual(pose['y'],.5)
        c=MotionController(AgentConfig())
        self.assertEqual(c.command({'x':0,'y':0},0,{'x':0,'y':0}),(0,0))
        v,w=c.command({'x':0,'y':0},math.pi,{'x':1,'y':0})
        self.assertEqual(v,0)
        self.assertLessEqual(abs(w),.8)
        v,w=c.command({'x':0,'y':0},0,{'x':10,'y':0})
        self.assertLessEqual(v,.18)

class StateTests(unittest.TestCase):
    def fresh_state(self):
        r=RobotState();r.update_clock(2,10)
        r.update('pose',{'x':0,'y':0},2,10,yaw=0)
        r.update('battery',60,2,10);r.update('signal',.5,2,10)
        r.update('scan',math.inf,2,10,nearest=math.inf)
        return r

    def test_missing_stale_and_invalid_data(self):
        r=RobotState();self.assertIsNone(r.snapshot())
        r=self.fresh_state();self.assertTrue(r.fresh(1,10.5))
        self.assertFalse(r.fresh(1,12))
        self.assertFalse(r.update('signal',math.nan,2,10))
        self.assertIsNone(r.snapshot())

    def test_frozen_and_reset_clock(self):
        r=self.fresh_state();r.update_clock(2,12)
        self.assertFalse(r.fresh(1,12))
        r.update_clock(1,12);self.assertIsNone(r.snapshot())
        self.assertFalse(r.clock_valid)

    def test_safety_prioritizes_obstacles(self):
        r=self.fresh_state();s=SafetyManager(r,AgentConfig())
        self.assertIsNone(s.reason(wall=10))
        r.update('scan',.2,2,10,nearest=.2)
        self.assertEqual(s.reason(wall=10,linear=.1),'BLOCKED')
        self.assertIsNone(s.reason(wall=10,linear=0))
        r.update('battery',0,2,10)
        self.assertEqual(s.reason(wall=10),'LOW_BATTERY')

class SearchEnergyTests(unittest.TestCase):
    def test_no_single_peak_collect(self):
        p=NavigationPlanner(10,10,.2,{'x':0,'y':0})
        s=SampleSearch(p,AgentConfig());o={'pose':{'x':1,'y':1},'signal':1}
        s.observe(o);self.assertFalse(s.should_collect(o['pose']))
        s.observe(dict(o,signal=.2));s.observe(dict(o,signal=.2))
        self.assertFalse(s.should_collect(o['pose']))
        for _ in range(5):s.observe(o)
        self.assertTrue(s.should_collect(o['pose']))
        s.collected(o['pose'],False)
        for _ in range(5):s.observe(o)
        self.assertFalse(s.should_collect(o['pose']))

    def test_path_energy_and_return(self):
        c=AgentConfig();b=BatteryManager(c)
        path=[{'x':0,'y':0},{'x':2,'y':0},{'x':2,'y':2}]
        self.assertEqual(b.required(path),26)
        self.assertFalse(b.can_explore(20,path,path[::-1]))
        b.observe({'pose':{'x':0,'y':0},'battery':60})
        b.observe({'pose':{'x':1,'y':0},'battery':55})
        self.assertEqual(b.rate,5)
        for value in (0,math.nan):
            with self.assertRaises(ValueError):AgentConfig(max_linear=value)
        self.assertEqual(AgentConfig.load(bootstrap.ROOT/'configs/agent.json').base,c.base)

class MissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_easy_multiple_seeds(self):
        for seed in (1,2,3):
            demo=KinematicDemo(seed)
            result=await demo.run()
            self.assertEqual(result['state']['status'],'finished',demo.mission.journal[-3:])
            self.assertGreaterEqual(result['state']['delivered'],1)
            self.assertEqual(result['collisions'],0)
            self.assertGreater(result['score']['battery'],0)
            self.assertEqual(demo.velocity,(0,0))
            self.assertLessEqual(distance(demo.pose,demo.config.base),demo.config.base_tolerance)

    async def test_commands_and_cancellation(self):
        d=KinematicDemo();m=d.mission
        await m.start(dict(scenario='easy',seed=1,mode='baseline'))
        with self.assertRaises(ValueError):await m.start(dict(scenario='easy',seed=1,mode='baseline'))
        await m.command('pause');self.assertEqual(m.state()['status'],'paused');self.assertEqual(d.velocity,(0,0))
        await m.command('resume');self.assertEqual(m.state()['status'],'running')
        await m.command('return');self.assertEqual(m.state()['status'],'returning')
        await m.command('stop');await m.task
        self.assertEqual(m.state()['status'],'stopped')
        with self.assertRaises(ValueError):await m.command('resume')

    async def test_finish_rejected(self):
        d=KinematicDemo()
        async def reject():return dict(success=False,message='no')
        d.finish=reject
        await d.mission.start(dict(scenario='easy',seed=1,mode='baseline'))
        await d.mission.command('return');await d.mission.task
        self.assertEqual(d.mission.state()['status'],'failed')
        self.assertEqual(d.mission.state()['delivered'],0)

    async def test_stale_navigation_and_stop(self):
        d=KinematicDemo();d.robot.received['scan']=0
        result=await d.navigator.follow(d.navigator.plan(d.pose,{'x':-1.8,'y':-.5}))
        self.assertEqual(result['message'],'STALE_DATA');self.assertEqual(d.velocity,(0,0))
        d.update()
        task=asyncio.create_task(d.navigator.follow(d.navigator.plan(d.pose,{'x':-1.2,'y':-.5})))
        await asyncio.sleep(.005);await d.navigator.stop()
        result=await task;self.assertEqual(result['message'],'CANCELLED')

    async def test_planner_failure_fallback(self):
        d=KinematicDemo()
        class BadPlanner:
            calls=0
            async def propose(self,observation,feedback=''):
                self.calls+=1
                return {'action':'go_to','target':{'x':math.nan,'y':0},'reason':'bad','hypothesis_id':None}
        p=BadPlanner();d.mission.planner=p;d.mission.planner_mode="llm"
        s=SampleSearch(d.grid,d.config)
        goal=await d.mission.choose(d.robot.snapshot(),s)
        self.assertEqual(p.calls,2);self.assertEqual(goal['action'],'explore')


class RuntimeFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_low_reserve_mid_navigation(self):
        d=KinematicDemo();d.pose={'x':-1.6,'y':-.5};d.update();d.robot.update('battery',9,d.sim_time)
        result=await d.navigator.follow(d.navigator.plan(d.pose,{'x':-1.0,'y':-.5}))
        self.assertEqual(result['message'],'LOW_RESERVE')
        self.assertEqual(d.velocity,(0,0))

    async def test_navigation_timeout_and_stuck(self):
        for setting,expected in (('motion_timeout','TIMEOUT'),('stuck_timeout','STUCK')):
            d=KinematicDemo()
            d.navigator.config=replace(d.config,**{setting:0.02})
            result=await d.navigator.follow(d.navigator.plan(d.pose,{'x':-1.0,'y':-.5}))
            self.assertEqual(result['message'],expected)
            self.assertEqual(d.velocity,(0,0))

    async def test_service_timeout_uncertain_does_not_retry(self):
        d=KinematicDemo()
        d.mission.config=replace(d.config,service_timeout=.01)
        calls=[]
        async def hang():
            calls.append(1)
            await asyncio.sleep(1)
        with self.assertRaisesRegex(RuntimeError,'result unknown'):
            await d.mission._service(hang)
        self.assertEqual(len(calls),1)

    async def test_planner_timeout_two_attempts(self):
        d=KinematicDemo();d.mission.config=replace(d.config,planner_timeout=.01)
        class Hanging:
            calls=0
            async def propose(self,obs,feedback=''):
                self.calls+=1
                await asyncio.sleep(10)
        p=Hanging();d.mission.planner=p;d.mission.planner_mode="llm"
        goal=await d.mission.choose(d.robot.snapshot(),SampleSearch(d.grid,d.config))
        self.assertEqual(p.calls,2);self.assertEqual(goal['action'],'explore')

    async def test_blocked_and_empty_navigation_stop(self):
        d=KinematicDemo()
        d.robot.update('scan',.10,d.sim_time,nearest=.10)
        result=await d.navigator.follow(d.navigator.plan(d.pose,{'x':-1.0,'y':-.5}))
        self.assertEqual(result['message'],'BLOCKED');self.assertEqual(d.velocity,(0,0))
        result=await d.navigator.follow([])
        self.assertEqual(result['message'],'INVALID_TARGET')

class MockJudgeTests(unittest.TestCase):
    def test_reproducibility_collection_boundary_and_finish(self):
        from did_environment.mock_judge import MockJudge
        d=KinematicDemo();a=MockJudge(d.grid,d.config,19);b=MockJudge(d.grid,d.config,19)
        self.assertEqual(a._samples,b._samples)
        self.assertEqual(len(a._samples),3)
        p=dict(a._samples[0])
        self.assertFalse(a.collect({'x':p['x']+.301,'y':p['y']})['success'])
        self.assertTrue(a.collect(p)['success'])
        self.assertFalse(a.finish(p)['success'])
        self.assertTrue(a.finish(d.config.base)['success'])
        self.assertEqual(a.score()['delivered'],1)
        self.assertFalse(a.collect(p)['success'])

    def test_terrain_energy_and_depletion(self):
        d=KinematicDemo();j=d.judge
        terrain=dict(j._terrain)
        j.observe(terrain,0)
        before=j.battery
        j.observe({'x':terrain['x']+.1,'y':terrain['y']},0)
        self.assertAlmostEqual(before-j.battery,.2)
        j.battery=0
        self.assertFalse(j.finish(d.config.base)['success'])

class SensorTests(unittest.TestCase):
    def test_forward_scan_and_unknown(self):
        from did_agent.sensors import scan_distances
        ranges=[math.inf]*9
        ranges[4]=.2
        front,nearest=scan_distances(ranges,-math.pi,math.pi/4,.05,10)
        self.assertEqual(front,.2);self.assertEqual(nearest,.2)
        ranges[4]=math.nan
        self.assertTrue(math.isnan(scan_distances(ranges,-math.pi,math.pi/4,.05,10)[0]))
        ranges[4]=math.inf
        self.assertEqual(scan_distances(ranges,-math.pi,math.pi/4,.05,10),(math.inf,math.inf))
        self.assertTrue(math.isnan(scan_distances([],0,.1,.05,10)[0]))

    def test_quaternion_validation(self):
        from did_agent.sensors import quaternion_yaw
        self.assertAlmostEqual(quaternion_yaw(0,0,math.sin(.5),math.cos(.5)),1)
        self.assertTrue(math.isnan(quaternion_yaw(0,0,0,0)))
        self.assertTrue(math.isnan(quaternion_yaw(0,0,0,math.nan)))

if __name__=='__main__':unittest.main()
