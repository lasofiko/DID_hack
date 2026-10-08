"""Regression tests from the critical audit, including forbidden private access."""
import ast
import asyncio
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap
from demo_easy import KinematicDemo
from did_agent import BatteryManager, SampleSearch, NavigationPlanner, AgentConfig, RobotState
from did_agent.sensors import scan_distances

class AuditAlgorithms(unittest.TestCase):
    def test_mock_scene_independent_of_navigation_clearance(self):
        from did_agent.maps import load_map
        from did_environment.mock_judge import MockJudge
        demo=KinematicDemo(seed=1,map_file=bootstrap.ROOT/'configs/maps/map.yaml')
        scene=load_map(bootstrap.ROOT/'configs/maps/map.yaml',MockJudge.SCENARIO_CLEARANCE)
        reference=MockJudge(scene,demo.config,1)
        self.assertNotEqual(demo.config.robot_clearance,MockJudge.SCENARIO_CLEARANCE)
        self.assertEqual(demo.judge._samples,reference._samples)

    def test_cross_topic_clock_skew_is_bounded(self):
        state=RobotState();state.update_clock(2.0,wall=10.0)
        state.update('pose',{'x':0.0,'y':0.0},2.03,wall=10.0,yaw=0.0)
        state.update('scan',math.inf,2.03,wall=10.0,nearest=math.inf)
        state.update('battery',60.0,2.0,wall=10.0)
        state.update('signal',0.0,2.0,wall=10.0)
        self.assertTrue(state.fresh(1.0,wall=10.05))
        state.update('pose',{'x':0.0,'y':0.0},2.11,wall=10.05,yaw=0.0)
        self.assertFalse(state.fresh(1.0,wall=10.05))
        state.update_clock(2.11,wall=10.05)
        self.assertTrue(state.fresh(1.0,wall=10.05))
        self.assertFalse(state.fresh(1.0,wall=11.2))

    def test_high_frequency_energy_accumulates_anchor(self):
        b=BatteryManager(AgentConfig())
        for i in range(21):
            b.observe({'pose':{'x':i*.01,'y':0},'battery':60-i*.1})
        self.assertAlmostEqual(b.rate,10)

    def test_duplicate_signal_not_confirmation(self):
        d=KinematicDemo();s=SampleSearch(d.grid,d.config)
        obs={'pose':d.pose,'signal':.99,'signal_time':1}
        for _ in range(10):s.observe(obs)
        self.assertFalse(s.should_collect(d.pose))
        s.observe(dict(obs,signal_time=2));s.observe(dict(obs,signal_time=3))
        self.assertTrue(s.should_collect(d.pose))

    def test_invalid_side_beam_rejects_rotation(self):
        values=[math.inf]*9;values[1]=math.nan
        self.assertTrue(math.isnan(scan_distances(values,-math.pi,math.pi/4,.05,10)[1]))

    def test_segment_cannot_cut_corner(self):
        p=NavigationPlanner(4,4,1,{'x':0,'y':0},occupied={(1,0)})
        self.assertFalse(p.segment_free({'x':.9,'y':.9},{'x':1.1,'y':1.1}))
        self.assertTrue(p.segment_free({'x':.5,'y':.5},{'x':.5,'y':2.5}))

    def test_malformed_pose_revokes_old_data(self):
        d=KinematicDemo()
        for value in ({}, {'x':True,'y':0},{'x':'bad','y':0}):
            d.update()
            self.assertFalse(d.robot.update('pose',value,d.sim_time,yaw=0))
            self.assertIsNone(d.robot.snapshot())

    def test_agent_has_no_environment_imports_or_private_targets(self):
        paths=list((bootstrap.ROOT/'packages/agent/did_agent').glob('*.py'))+[bootstrap.ROOT/'ros2/did_robot/did_robot/agent_node.py']
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith('did_environment'))
                if isinstance(node,ast.Import):self.assertFalse(any(n.name.startswith('did_environment') for n in node.names))
                if isinstance(node,ast.Attribute):self.assertNotIn(node.attr,('_samples','_terrain','judge','score'))

    def test_lidar_not_given_added_clearance(self):
        d=KinematicDemo();d.pose={'x':-2.2,'y':-.5};d.yaw=math.pi;d.update()
        # Boundary surface near x=-2.4 is ~0.2m away; old inflated+clearance ray was >0.28.
        self.assertLessEqual(d.robot.front_distance,.25)

class AuditMission(unittest.IsolatedAsyncioTestCase):
    async def test_official_map_corner_return_after_early_signal_search(self):
        from did_agent.maps import load_map
        demo=KinematicDemo(seed=1,map_file=bootstrap.ROOT/'configs/maps/map.yaml')
        # Retain the narrow legacy route that reproduced the skipped-corner bug,
        # independently of today's larger navigation margin and fixed scene.
        demo.grid=load_map(bootstrap.ROOT/'configs/maps/map.yaml',0.20)
        demo.navigator.planner=demo.grid
        result=await demo.run()
        self.assertEqual(result['state']['status'],'finished')
        self.assertEqual(result['state']['delivered'],1)
        self.assertEqual(result['collisions'],0)

    async def test_emergency_start_cannot_clear_latch(self):
        d=KinematicDemo();d.safety.emergency=True
        with self.assertRaisesRegex(RuntimeError,'EMERGENCY'):
            await d.mission.start({'scenario':'easy','mode':'baseline','seed':1})
        self.assertTrue(d.safety.emergency)

    async def test_no_sensors_and_empty_battery(self):
        for kind in ('pose','scan','signal','battery'):
            d=KinematicDemo();d.robot.values.pop(kind)
            with self.assertRaises(RuntimeError):
                await d.mission.start({'scenario':'easy','mode':'baseline','seed':1})
            self.assertEqual(d.velocity,(0,0))
        d=KinematicDemo();d.robot.update('battery',0,d.sim_time)
        result=await d.navigator.follow(d.navigator.plan(d.pose,{'x':-1.8,'y':-.5}))
        self.assertEqual(result['message'],'LOW_BATTERY');self.assertEqual(d.velocity,(0,0))

    async def test_stop_after_battery_drops_to_zero(self):
        d=KinematicDemo()
        task=asyncio.create_task(d.navigator.follow(d.navigator.plan(d.pose,{'x':-1.0,'y':-.5})))
        await asyncio.sleep(.005);d.robot.update('battery',0,d.sim_time)
        self.assertEqual((await task)['message'],'LOW_BATTERY');self.assertEqual(d.velocity,(0,0))

    async def test_pause_resume_during_return_replans(self):
        d=KinematicDemo();d.pose={'x':-1.6,'y':-.5};d.update()
        entered=asyncio.Event();calls=[]
        async def follow(path):
            calls.append(1)
            if len(calls)==1:
                token=d.navigator.generation;entered.set()
                while token==d.navigator.generation:await asyncio.sleep(.001)
                return {'success':False,'message':'CANCELLED'}
            d.pose=dict(d.config.base);d.update()
            return {'success':True,'message':'SUCCESS'}
        d.navigator.follow=follow
        await d.mission.start({'scenario':'easy','mode':'baseline','seed':1})
        await d.mission.command('return');await entered.wait()
        await d.mission.command('pause');await d.mission.command('resume')
        await asyncio.wait_for(d.mission.task,1)
        self.assertEqual(d.mission.state()['status'],'finished');self.assertEqual(len(calls),2)

    async def test_failed_collect_not_counted_and_not_spammed(self):
        d=KinematicDemo();d.mission.config=replace(d.config,max_steps=4)
        update=d.update;calls=[]
        def high_signal():
            update();d.robot.update('signal',.99,d.sim_time)
        d.update=high_signal
        async def reject():
            calls.append(dict(d.pose));return {'success':False,'message':'No sample'}
        d.collect=reject
        result=await d.run()
        self.assertGreater(len(calls),0)
        self.assertEqual(result['state']['collected'],0)
        for a,b in zip(calls,calls[1:]):
            self.assertGreaterEqual(math.hypot(a['x']-b['x'],a['y']-b['y']),.25)

    async def test_services_proxy_forbids_private_access(self):
        d=KinematicDemo(seed=4)
        class PublicServices:
            async def collect(self):return await d.collect()
            async def finish(self):return await d.finish()
            def __getattr__(self,name):raise AssertionError('Forbidden services access: '+name)
        d.mission.services=PublicServices()
        result=await d.run()
        self.assertEqual(result['state']['delivered'],1)

    async def test_no_signal_cannot_use_hidden_targets_to_collect(self):
        d=KinematicDemo();d.mission.config=replace(d.config,max_steps=4)
        original=d.update
        def zero_signal():original();d.robot.update('signal',0,d.sim_time)
        d.update=zero_signal
        async def forbidden_collect():raise AssertionError('No signal but collect called')
        d.collect=forbidden_collect
        result=await d.run()
        self.assertEqual(result['state']['collected'],0)
        self.assertEqual(result['state']['status'],'finished')

class AdditionalBoundaryTests(unittest.TestCase):
    def test_invalid_map_metadata_is_valueerror(self):
        for resolution,clearance in ((0,.2),(.1,-1),(.1,math.nan)):
            with self.assertRaises(ValueError):
                NavigationPlanner.from_occupancy(3,3,resolution,{'x':0,'y':0},[0]*9,clearance)

    def test_safety_accounts_for_scan_age(self):
        d=KinematicDemo();wall=100.0
        d.robot.update_clock(2,wall)
        d.robot.update('pose',d.pose,2,wall,yaw=0)
        d.robot.update('battery',60,2,wall);d.robot.update('signal',0,2,wall)
        d.robot.update('scan',.32,1.5,wall-.5,nearest=.32)
        self.assertEqual(d.safety.reason(wall=wall,linear=.18),'BLOCKED')
        self.assertIsNone(d.safety.reason(wall=wall,linear=0))

class JudgeBoundaryTests(unittest.TestCase):
    def test_nan_pose_cannot_finish(self):
        d=KinematicDemo()
        for pose in ({'x':math.nan,'y':0},{'x':math.inf,'y':0},{}):
            self.assertFalse(d.judge.finish(pose)['success'])
            self.assertFalse(d.judge.collect(pose)['success'])
        self.assertFalse(d.judge.finished)

    def test_samples_not_on_disconnected_island(self):
        from did_environment.mock_judge import MockJudge
        blocked={(6,y) for y in range(12)}
        p=NavigationPlanner(12,12,.5,{'x':-2.5,'y':-2.5},blocked)
        j=MockJudge(p,AgentConfig(),4)
        for sample in j._samples:
            self.assertLess(p.cell(sample)[0],6)
            self.assertTrue(p.plan(AgentConfig().base,sample))
