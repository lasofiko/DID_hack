"""Algorithm fixtures with stamped sensor streams, not Gazebo experiments."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap
from did_agent import AgentConfig,NavigationPlanner,RobotState
from did_agent.energy import EnergyObserver
from did_agent.battery import BatteryManager
from did_agent.navigation import MotionController
from did_ml.energy import EnergyModel
from did_ml.factory import make_energy_model

class IntegrationTests(unittest.TestCase):
    def setup_observer(self,adaptive=True):
        grid=NavigationPlanner(30,30,.1,dict(x=0.,y=0.))
        return EnergyObserver(grid,lambda *args:None,adaptive=adaptive)
    def feed(self,e,t,x=.1,y=.1,yaw=0,b=60):
        return e.observe({},0,[('pose',dict(x=x,y=y),t,yaw),('battery',b,t,None)])
    def move(self,e,x=.1,rate=2):
        e.note_command(.1,0,0)
        for i in range(13):self.feed(e,.2+i*.1,x=x+i*.01,b=60-rate*i*.01)
    def test_real_factory_and_unknown_turn(self):
        m=make_energy_model(AgentConfig())
        self.assertIsInstance(m,EnergyModel)
        self.assertIsNone(m.estimate_turn(dict(x=.25,y=.25))['energy_per_rad'])
    def test_baseline_shadow_learning_does_not_change_planning(self):
        e=self.setup_observer(False);before=e.planner.plan(dict(x=.1,y=.1),dict(x=1,y=1))
        self.move(e)
        self.assertGreater(e.accepted,0);self.assertEqual(e.planner.costs,{})
        self.assertEqual(e.planner.turn_costs,{})
        self.assertEqual(before,e.planner.plan(dict(x=.1,y=.1),dict(x=1,y=1)))
    def test_adaptive_uses_direct_measurements(self):
        e=self.setup_observer();self.move(e,rate=10)
        self.assertGreater(e.revision,0)
        self.assertTrue(e.planner.costs)
        self.assertTrue(all(abs(v-10)<1e-6 for v in e.planner.costs.values()))
    def test_changed_local_cost_updates_model_and_only_adaptive_weights(self):
        for adaptive in (False,True):
            e=self.setup_observer(adaptive);events=[];e.log=lambda *args:events.append(args)
            self.move(e,rate=2);revision=e.revision
            e.note_command(0,0,1.5);e.note_command(.1,0,2)
            for i in range(13):self.feed(e,2.2+i*.1,x=.1+i*.01,b=59.76-8*i*.01)
            entry=e.public()[0]
            self.assertEqual(entry['move_samples'],2)
            self.assertAlmostEqual(entry['energy_per_m'],5,places=6)
            self.assertTrue(any('estimate may be stale' in args[0] for args in events))
            if adaptive:
                self.assertGreater(e.revision,revision)
                self.assertTrue(all(abs(v-5)<1e-6 for v in e.planner.costs.values()))
            else:
                self.assertEqual(e.revision,0);self.assertEqual(e.planner.costs,{})
    def test_cell_crossing_never_distributes_delta(self):
        e=self.setup_observer();e.note_command(.1,0,0)
        for i in range(9):self.feed(e,.2+i*.1,x=.46+i*.01,b=60-2*i*.01)
        self.assertEqual(e.accepted,0);self.assertEqual(e.public(),[])
        self.assertGreater(e.rejected.get('cell_crossing',0),0)
    def test_turn_wrap_and_reversals_use_absolute_incremental_yaw(self):
        e=self.setup_observer();e.note_command(0,.5,0)
        a=math.pi-.1
        for i in range(9):
            yaw=a+.05*i
            self.feed(e,.2+i*.1,yaw=math.atan2(math.sin(yaw),math.cos(yaw)),b=60-.03*.05*i)
        count=e.accepted
        for i in range(1,9):
            yaw=a+.4-.05*i
            self.feed(e,1.+i*.1,yaw=yaw,b=60-.012-.03*.05*i)
        self.assertGreater(e.accepted,count)
        self.assertAlmostEqual(e.public()[0]['energy_per_rad'],.03,places=6)
        self.assertEqual(e.public()[0]['move_samples'],0)
    def test_multiple_rotations_do_not_alias_to_zero(self):
        e=self.setup_observer();e.note_command(0,.5,0)
        for i in range(141):self.feed(e,.2+i*.1,yaw=math.atan2(math.sin(i*.05),math.cos(i*.05)),b=60-.03*i*.05)
        self.assertGreater(e.accepted,30)
        self.assertAlmostEqual(e.public()[0]['energy_per_rad'],.03,places=6)
    def test_duplicate_packets_are_not_counted_twice(self):
        e=self.setup_observer();self.move(e)
        n=e.accepted;self.feed(e,1.4,x=.22,b=59.76);self.feed(e,1.4,x=.22,b=59.76)
        self.assertEqual(e.accepted,n)
    def test_mixed_turn_translation_is_rejected(self):
        e=self.setup_observer();e.note_command(0,.5,0)
        for i in range(9):self.feed(e,.2+i*.1,x=.1+i*.01,yaw=i*.05,b=60-i*.05)
        self.assertEqual(e.accepted,0);self.assertGreater(e.rejected.get('mixed_motion',0),0)
    def test_mixed_straight_rotation_is_rejected(self):
        e=self.setup_observer();e.note_command(.1,0,0)
        for i in range(10):self.feed(e,.2+i*.1,x=.1+i*.01,yaw=i*.01,b=60-i*.05)
        self.assertEqual(e.accepted,0);self.assertGreater(e.rejected.get('mixed_motion',0),0)
    def test_sensor_skew_gap_and_overflow_reject_anchor(self):
        e=self.setup_observer();e.note_command(.1,0,0);self.feed(e,.2)
        e.observe({},0,[('battery',59,.5,None)])
        self.assertIn('sensor_skew',e.rejected)
        self.feed(e,2)
        self.assertIn('odom_gap',e.rejected)
        e.observe({},0,[],True);self.assertIn('queue_overflow',e.rejected)
        self.assertEqual(e.accepted,0)
    def test_battery_reset_not_negative_energy(self):
        e=self.setup_observer();e.note_command(.1,0,0);self.feed(e,.2,b=50)
        self.feed(e,.3,x=.11,b=60)
        self.assertIn('battery_reset',e.rejected);self.assertEqual(e.accepted,0)
    def test_maria_rejection_not_reported_as_model_update(self):
        e=self.setup_observer();e.model=EnergyModel(3,min_distance_m=1)
        self.move(e)
        self.assertEqual(e.accepted,0);self.assertIn('model_rejected',e.rejected)
    def test_rotated_grid_uses_exact_energy_cell_center(self):
        e=self.setup_observer();e.planner.origin=dict(x=-2.,y=-3.);e.planner.origin_yaw=math.pi/2
        p=e.center((2,3));self.assertEqual(e.key(p),(2,3))
        self.assertAlmostEqual(p['x'],-3.75);self.assertAlmostEqual(p['y'],-1.75)
    def test_reserve_includes_unknown_turn_even_with_high_movement_bound(self):
        e=self.setup_observer();b=BatteryManager(e.config);b.energy=e;b.rate=10
        path=[dict(x=.1,y=.1),dict(x=.1,y=1.1)]
        expected=(10+math.pi/2*.25)*1.5+8
        self.assertAlmostEqual(b.required(path),expected)
    def test_controller_is_exclusive_and_stops_at_transition(self):
        c=MotionController(AgentConfig());p=dict(x=0,y=0);target=dict(x=1,y=0)
        self.assertEqual(c.command(p,math.pi/2,target)[0],0)
        self.assertEqual(c.command(p,0,target),(0,0))
        v,w=c.command(p,0,target);self.assertGreater(v,0);self.assertEqual(w,0)
    def test_heading_hysteresis_prevents_boundary_chatter(self):
        c=MotionController(AgentConfig());p=dict(x=0,y=0);q=dict(x=1,y=0)
        c.command(p,.1,q)
        self.assertEqual(c.command(p,.039,q)[0],0)
        self.assertEqual(c.command(p,.009,q),(0,0))
        self.assertGreater(c.command(p,.02,q)[0],0)
    def test_state_captures_full_stream_and_clock_reset(self):
        r=RobotState();r.update_clock(1)
        for i in range(5):r.update('pose',dict(x=.1*i,y=0),1+i*.01,yaw=.1*i)
        samples,overflow=r.drain_energy_samples();self.assertEqual(len(samples),5);self.assertFalse(overflow)
        r.update_clock(.1);self.assertTrue(r.drain_energy_samples()[1])
    def test_heading_astar_matches_dijkstra_oracle(self):
        import heapq,random
        from did_agent.navigation import wrap
        moves=((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))
        for seed in range(20):
            rng=random.Random(seed);p=NavigationPlanner(6,6,.1,dict(x=0,y=0),origin_yaw=.3)
            p.start_yaw=rng.uniform(-math.pi,math.pi);p.default_cost=3.;p.default_turn_cost=.25
            p.costs={(x,y):rng.uniform(1,5) for x in range(6) for y in range(6)}
            p.turn_costs={(x,y):rng.uniform(0,2) for x in range(6) for y in range(6)}
            angles=[math.atan2(dy,dx)+p.origin_yaw for dx,dy in moves]+[p.start_yaw]
            queue=[(0.,0,0,8)];best={(0,0,8):0.}
            while queue:
                value,x,y,h=heapq.heappop(queue)
                if value!=best[(x,y,h)]:continue
                if (x,y)==(5,5):expected=value;break
                for nh,(dx,dy) in enumerate(moves):
                    cell=x+dx,y+dy
                    if not p.free(cell):continue
                    step=math.hypot(dx,dy)*p.resolution*(p.costs[(x,y)]+p.costs[cell])/2
                    step+=abs(wrap(angles[nh]-angles[h]))*p.turn_costs[(x,y)]
                    state=(*cell,nh);candidate=value+step
                    if candidate<best.get(state,math.inf):
                        best[state]=candidate;heapq.heappush(queue,(candidate,*state))
            path=p.plan(p.point((0,0)),p.point((5,5)))
            cells=[]
            for q in path:
                cell=p.cell(q)
                if not cells or cells[-1]!=cell:cells.append(cell)
            actual=0.;heading=p.start_yaw
            for a,b in zip(cells,cells[1:]):
                dx,dy=b[0]-a[0],b[1]-a[1];direction=math.atan2(dy,dx)+p.origin_yaw
                actual+=math.hypot(dx,dy)*p.resolution*(p.costs[a]+p.costs[b])/2
                actual+=abs(wrap(direction-heading))*p.turn_costs[a];heading=direction
            self.assertAlmostEqual(actual,expected,places=9,msg=str(seed))
    def test_turn_cost_changes_route_choice(self):
        e=self.setup_observer();p=e.planner
        start=dict(x=.15,y=.15);goal=dict(x=1.15,y=.75)
        before=p.plan(start,goal)
        # Penalise turning on the initially selected path; only observable model
        # costs enter the planner, no judge data enters this fixture.
        p.turn_costs={p.cell(q):20 for q in before[1:-1]}
        self.assertNotEqual(before,p.plan(start,goal))

class JournalTests(unittest.TestCase):
    def test_fixture_cannot_write_to_real_ros_journal_from_environment(self):
        import tempfile
        from unittest.mock import patch
        from demo_easy import KinematicDemo
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'real.jsonl'
            with patch.dict('os.environ',{'DID_AGENT_JOURNAL_LOG':str(p)}):
                d=KinematicDemo();d.mission.log('synthetic fixture')
            self.assertFalse(p.exists())
    def test_full_local_journal_survives_memory_limit(self):
        import tempfile,json
        from demo_easy import KinematicDemo
        d=KinematicDemo()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'journal.jsonl';d.mission.journal_sink=str(p)
            for i in range(1002):d.mission.log(str(i))
            records=[json.loads(s) for s in p.read_text().splitlines()]
            self.assertEqual(len(records),1002);self.assertEqual(len(d.mission.journal),1000)
            self.assertIn('battery=',records[-1]['text'])
            self.assertNotIn('zones',records[-1])

class SensorRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_return_arrival_uses_base_radius_after_safety(self):
        from demo_easy import KinematicDemo
        from did_agent.navigation import distance
        d=KinematicDemo();d.pose=dict(x=-1.86,y=-.5);d.update()
        self.assertGreater(distance(d.pose,d.config.base),d.config.goal_tolerance)
        d.navigator.returning=True
        result=await d.navigator.follow(d.navigator.plan(d.pose,d.config.base))
        self.assertTrue(result['success']);self.assertEqual(d.velocity,(0,0))
        d.safety.reason=lambda **kwargs:'EMERGENCY'
        result=await d.navigator.follow(d.navigator.plan(d.pose,d.config.base))
        self.assertEqual(result['message'],'EMERGENCY');self.assertEqual(d.velocity,(0,0))
    async def test_transient_staleness_stays_zero_until_recovery(self):
        import asyncio
        from demo_easy import KinematicDemo
        d=KinematicDemo();stale=True
        d.safety.reason=lambda **kwargs:'STALE_DATA' if stale else None
        task=asyncio.create_task(d.navigator.follow(d.navigator.plan(d.pose,dict(x=-1.,y=-.5))))
        await asyncio.sleep(.02);self.assertEqual(d.velocity,(0,0))
        stale=False
        await asyncio.sleep(.01);self.assertGreater(abs(d.velocity[0])+abs(d.velocity[1]),0)
        await d.navigator.stop();self.assertEqual((await task)['message'],'CANCELLED')
        self.assertEqual(d.velocity,(0,0))
    async def test_persistent_missing_sensor_is_terminal_and_zero(self):
        from demo_easy import KinematicDemo
        d=KinematicDemo();d.safety.reason=lambda **kwargs:'STALE_DATA'
        result=await d.navigator.follow(d.navigator.plan(d.pose,dict(x=-1.,y=-.5)))
        self.assertEqual(result['message'],'STALE_DATA');self.assertEqual(d.velocity,(0,0))

class ReplanTests(unittest.IsolatedAsyncioTestCase):
    async def test_learning_retries_same_search_objective(self):
        from demo_easy import KinematicDemo
        d=KinematicDemo();targets=[];decisions=[]
        async def choose(obs,search):
            decisions.append(1)
            return dict(action='explore',target=dict(x=-1.7,y=-.5),reason='fixture',hypothesis_id=None)
        async def follow(path):
            targets.append(path[-1])
            if len(targets)==1:return dict(success=False,message='REPLAN')
            d.mission._state['status']='stopped'
            return dict(success=True,message='SUCCESS')
        d.mission.choose=choose;d.navigator.follow=follow
        await d.run()
        self.assertEqual(len(decisions),1);self.assertEqual(targets,[dict(x=-1.7,y=-.5)]*2)
        self.assertTrue(any(e['stage']=='replan' for e in d.mission.journal))

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_discovery_then_calls_once(self):
        import asyncio
        from types import SimpleNamespace as NS
        from did_backend.runtime import RosRuntime
        class Client:
            checks=0;calls=0
            def service_is_ready(self):
                self.checks+=1;return self.checks>=3
            def call_async(self,request):
                self.calls+=1;f=asyncio.get_running_loop().create_future();f.set_result(NS(success=True));return f
        client=Client();r=RosRuntime();r.clients={'start':client};r.trigger=NS(Request=lambda:None)
        await r.trigger_call('start');self.assertEqual(client.calls,1)

if __name__=='__main__':unittest.main()
