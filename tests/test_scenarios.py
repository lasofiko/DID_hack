"""Unit tests: private fixture data is used only to verify the judge, never by the agent."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap
from did_agent import AgentConfig,NavigationPlanner
from did_environment.mock_judge import MockJudge
from did_agent.energy import EnergyObserver
from did_backend.runtime import PublicCache

class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.config=AgentConfig();self.grid=NavigationPlanner.from_occupancy(80,80,.1,{'x':-4.,'y':-4.},[0]*6400,0)
    def test_counts_reproducibility_and_seeds(self):
        for scenario,n,z in [('easy',3,1),('medium',5,3),('hard',7,4)]:
            for seed in (0,1,2,17,2147483647):
                a=MockJudge(self.grid,self.config,seed,scenario);b=MockJudge(self.grid,self.config,seed,scenario)
                self.assertEqual(a._samples,b._samples);self.assertEqual(len(a._samples),n);self.assertEqual(len(a._zones),z)
                self.assertTrue(all(self.grid.free(self.grid.cell(p)) for p in a._samples))
                self.assertFalse({'samples','zones','schedule'}&a.score().keys())
    def test_cost_is_physical_and_medium_static(self):
        j=MockJudge(self.grid,self.config,2,'medium');p=j._zones[0]['center']
        j.observe(p,0,0);before=j.battery;j.observe({'x':p['x']+.1,'y':p['y']},0,200)
        self.assertAlmostEqual(before-j.battery,.2);self.assertEqual(j._applied,set())
    def test_hard_schedule_epoch_sensor_and_private_events(self):
        j=MockJudge(self.grid,self.config,2,'hard');j.observe(self.config.base,0,1000)
        self.assertEqual(j._applied,set());j.start(1000)
        j.observe(self.config.base,0,1030);self.assertEqual(j._zones[0]['cost'],4)
        _,signal=j.observe(self.config.base,0,1090);self.assertTrue(math.isnan(signal))
        self.assertTrue(any(e['kind']=='sensor' for e in j._private_events));self.assertEqual(j.events,[])
        _,signal=j.observe(self.config.base,0,1110);self.assertTrue(math.isfinite(signal))
    def test_hazard_not_announced_before_encounter(self):
        j=MockJudge(self.grid,self.config,1,'hard');j.start(0);j.observe(self.config.base,0,60)
        self.assertEqual(j.events,[]);j.observe(j._hazard,0,61)
        self.assertEqual(j.events,[{'type':'hazard_hit'}])
    def test_bad_collect_low_energy(self):
        j=MockJudge(self.grid,self.config);self.assertFalse(j.collect(self.config.base)['success'])
        j.battery=0;self.assertFalse(j.collect(j._samples[0])['success']);self.assertFalse(j.finish(self.config.base)['success'])

class EnergyTests(unittest.TestCase):
    def setUp(self):
        self.grid=NavigationPlanner.from_occupancy(40,40,.1,{'x':-2.,'y':-2.},[0]*1600,0)
        self.logs=[];self.e=EnergyObserver(self.grid,lambda *args:self.logs.append(args))
    def feed(self,e,x,b,t,yaw=0):
        return e.observe({'pose':{'x':x,'y':.1},'battery':b,'sim_time':t},yaw)
    def move(self,e,rate=2.,x=.02):
        e.note_command(.1,0,0)
        self.feed(e,x,60,.2)
        changed=False
        for i in range(1,11):
            changed=self.feed(e,x+i*.01,60-rate*i*.01,.2+i*.1) or changed
        return changed
    def test_experiment_is_announced_before_motion_and_matches_observation(self):
        self.e.note_command(.1,0,0)
        self.assertEqual([e[1] for e in self.logs],['hypothesis','experiment'])
        self.move(self.e)
        self.assertTrue({'observation','conclusion','model_update'} <= {e[1] for e in self.logs})
        self.assertTrue(all(e[2]==self.logs[0][2] for e in self.logs))
    def test_measure_update_replan_and_no_turn_contamination(self):
        self.assertTrue(self.move(self.e))
        self.assertTrue(self.grid.costs);self.assertAlmostEqual(self.e.public()[0]['energy_per_m'],2)
        values=self.e.public();self.feed(self.e,.13,58,1.3,.2)
        self.assertEqual(values,self.e.public())
    def test_conservation_energy_model_contract(self):
        self.move(self.e)
        m=self.e.last_measurement
        self.assertAlmostEqual(m['energy_used'],2*m['distance_m'])
        self.assertEqual(self.e.accepted,1)
        self.assertFalse(m['turning'])
    def test_external_model_failure_keeps_safe_model(self):
        class Bad:
            def update(self,m):raise ValueError('bad model')
        e=EnergyObserver(self.grid,lambda *args:None,Bad())
        self.assertFalse(self.move(e));self.assertEqual(e.public(),[])
        self.assertEqual(e.rejected.get('model_failure'),1)
    def test_changed_rate_is_detected(self):
        self.move(self.e,1.)
        for i in range(1,11):self.feed(self.e,.12+i*.01,59.90-4*i*.01,1.2+i*.1)
        self.assertTrue(any(e[1]=='hypothesis' and 'stale' in e[0] for e in self.logs))
    def test_astar_avoids_measured_high_cost(self):
        start={'x':-.8,'y':0.};goal={'x':.8,'y':0.}
        direct=self.grid.plan(start,goal)
        self.grid.costs.update({(x,y):10 for x in range(16,24) for y in range(18,23)})
        adapted=self.grid.plan(start,goal);self.assertNotEqual(direct,adapted)

class PublicCacheTests(unittest.TestCase):
    def test_score_whitelist_and_frozen_position(self):
        c=PublicCache();c.pose={'x':1.,'y':2.}
        c.on_json('score','{"collected":1,"battery":59,"samples":[{"x":99,"y":99}],"zones":[1],"schedule":[2]}')
        a=c.snapshot();b=c.snapshot()
        self.assertEqual(a['robot_pose'],b['robot_pose']);self.assertNotEqual(a['connection'],'online')
        self.assertFalse({'samples','zones','schedule'}&a['score'].keys());self.assertEqual(a['collected_positions'],[{'x':1.,'y':2.}])
    def test_only_agent_knowledge_is_projected(self):
        c=PublicCache();c.on_json('knowledge','{"path":[{"x":0,"y":1}],"costs":[{"cell":{"x":0,"y":1},"energy_per_m":2,"uncertainty":null,"true_cost":99}],"planner_source":"fake"}')
        self.assertNotIn('true_cost',c.snapshot()['knowledge'][0]);self.assertEqual(c.snapshot()['planner_source'],'Algorithmic')
    def test_reset_clears_public_history(self):
        c=PublicCache();c.pose={'x':1.,'y':2.};c.trajectory.append(c.pose);c.clear()
        self.assertIsNone(c.snapshot()['robot_pose']);self.assertEqual(c.snapshot()['trajectory'],[])

class PlannerModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_algorithmic_does_not_call_team_planner(self):
        from demo_easy import KinematicDemo
        from did_agent.search import SampleSearch
        d=KinematicDemo()
        class Planner:
            async def propose(self,*args):raise AssertionError('Must not call in algorithmic mode')
        d.mission.planner=Planner();d.mission.planner_mode='algorithmic'
        goal=await d.mission.choose(d.robot.snapshot(),SampleSearch(d.grid,d.config))
        self.assertEqual(goal['action'],'explore');self.assertEqual(d.mission.planner_source,'Algorithmic')
    async def test_valid_team_planner_source(self):
        from demo_easy import KinematicDemo
        from did_agent.search import SampleSearch
        d=KinematicDemo()
        class Planner:
            async def propose(self,*args):return {'action':'return_to_base','target':None,'reason':'Budget','hypothesis_id':None}
        d.mission.planner=Planner();d.mission.planner_mode='llm'
        goal=await d.mission.choose(d.robot.snapshot(),SampleSearch(d.grid,d.config))
        self.assertEqual(goal['action'],'return_to_base');self.assertEqual(d.mission.planner_source,'Algorithmic')
    async def test_external_planner_error_does_not_leak_secret(self):
        from demo_easy import KinematicDemo
        from did_agent.search import SampleSearch
        d=KinematicDemo()
        class Planner:
            async def propose(self,*args):raise RuntimeError('api_key=PRIVATE_TEST_TOKEN')
        d.mission.planner=Planner();d.mission.planner_mode='llm'
        await d.mission.choose(d.robot.snapshot(),SampleSearch(d.grid,d.config))
        self.assertNotIn('PRIVATE_TEST_TOKEN',str(d.mission.journal))
        self.assertEqual(d.mission.planner_source,'Algorithmic')
