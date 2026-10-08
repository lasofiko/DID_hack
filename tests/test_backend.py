"""Direct ASGI checks (no server socket, no claim of ROS/backend integration)."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap

@unittest.skipUnless(importlib.util.find_spec('fastapi'),'Backend dependencies not installed')
class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_asgi(self):
        from did_backend.main import app
        events=[]
        async def send(message):events.append(message)
        async def receive():return {'type':'http.request','body':b'','more_body':False}
        scope=dict(type='http',asgi={'version':'3.0'},http_version='1.1',method='GET',
                   scheme='http',path='/api/health',raw_path=b'/api/health',query_string=b'',
                   root_path='',headers=[],client=('127.0.0.1',1234),server=('127.0.0.1',8000))
        await app(scope,receive,send)
        self.assertEqual(events[0]['status'],200)
        self.assertEqual(events[-1]['body'],b'{"status":"ok"}')

@unittest.skipUnless(importlib.util.find_spec('fastapi'),'Backend dependencies not installed')
class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def request(self,method,path,body=None):
        import json
        from did_backend.main import app
        events=[];sent=False
        async def send(e):events.append(e)
        async def receive():
            nonlocal sent
            if sent:return {'type':'http.disconnect'}
            sent=True;return {'type':'http.request','body':json.dumps(body).encode() if body is not None else b'','more_body':False}
        scope=dict(type='http',asgi={'version':'3.0'},http_version='1.1',method=method,scheme='http',path=path,raw_path=path.encode(),query_string=b'',root_path='',headers=[(b'content-type',b'application/json')],client=('127.0.0.1',1),server=('127.0.0.1',8000))
        await app(scope,receive,send)
        return events[0]['status'],json.loads(b''.join(e.get('body',b'') for e in events))
    async def asyncSetUp(self):
        from did_backend.main import app
        from did_backend.runtime import RosRuntime
        app.state.runtime=RosRuntime();app.state.runtime.cache.error='ROS unavailable in unit test'
    async def test_invalid_seeds_and_modes(self):
        for seed in (True,-1,2147483648,1.5,'1'):
            code,_=await self.request('POST','/api/missions',{'scenario':'easy','mode':'baseline','seed':seed});self.assertEqual(code,422)
        for body in ({'scenario':'oops'},{'mode':'oops'},{'planner_mode':'oops'},{'shell':'rm'}):
            code,_=await self.request('POST','/api/missions',{'scenario':'easy','mode':'baseline','seed':1,**body});self.assertEqual(code,422)
    async def test_no_ros_reset_start_and_command(self):
        for path in ('/api/missions','/api/missions/reset'):
            code,_=await self.request('POST',path,{'scenario':'easy','seed':1,'mode':'baseline'});self.assertEqual(code,503)
        code,_=await self.request('POST','/api/command',{'command':'pause'});self.assertEqual(code,409)
        code,_=await self.request('GET','/api/map');self.assertEqual(code,503)
    async def test_real_command_mapping_with_fake_port(self):
        from did_backend.main import app
        called=[]
        app.state.runtime.cache.state['status']='running'
        async def command(name):called.append(name);return {'state':{'status':'paused'}}
        app.state.runtime.command=command
        code,body=await self.request('POST','/api/command',{'command':'pause'})
        self.assertEqual(code,200);self.assertEqual(called,['pause']);self.assertEqual(body['status'],'paused')
    async def test_public_routes(self):
        for path in ('/api/scenarios','/api/state','/api/journal','/api/trajectory'):
            code,_=await self.request('GET',path);self.assertEqual(code,200)
    async def test_websocket_offline_snapshot(self):
        from did_backend.main import telemetry
        class Socket:
            values=[]
            async def accept(self):pass
            async def send_json(self,value):
                self.values.append(value)
                if len(self.values)==2:raise RuntimeError('disconnected')
        ws=Socket();await telemetry(ws)
        self.assertEqual(ws.values[0]['connection'],'error');self.assertIsNone(ws.values[0]['robot_pose'])
    async def test_concurrent_session_mutations_are_serialized(self):
        from did_backend.main import app
        running=0;maximum=0
        async def start(session):
            nonlocal running,maximum
            running+=1;maximum=max(maximum,running)
            await asyncio.sleep(.04);running-=1
            return {'state':{'status':'running'}}
        app.state.runtime.start=start
        a,b=await asyncio.gather(self.request('POST','/api/missions',{'scenario':'easy','seed':1,'mode':'baseline'}),self.request('POST','/api/missions',{'scenario':'medium','seed':2,'mode':'adaptive'}))
        self.assertEqual((a[0],b[0]),(201,201));self.assertEqual(maximum,1)
    async def test_legacy_command_route(self):
        from did_backend.main import app
        app.state.runtime.cache.state['status']='running'
        async def command(name):return {'state':{'status':'paused'}}
        app.state.runtime.command=command
        code,body=await self.request('POST','/api/missions/command',{'command':'pause'})
        self.assertEqual(code,200);self.assertEqual(body['status'],'paused')

@unittest.skipUnless(importlib.util.find_spec('fastapi'),'Backend dependencies not installed')
class StartFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_judge_epoch_starts_after_agent_and_failure_requires_reset(self):
        from did_backend.runtime import RosRuntime,DEFAULT_SESSION
        r=RosRuntime();calls=[]
        async def noop():pass
        async def trigger(name):
            calls.append(name)
            if name=='mock_start':raise RuntimeError('Judge not ready')
        r.ready=noop;r.verify_coordinates=noop;r.trigger_call=trigger
        with self.assertRaisesRegex(RuntimeError,'Judge not ready'):await r.start(dict(DEFAULT_SESSION))
        self.assertEqual(calls,['start','mock_start','stop']);self.assertTrue(r.reset_required)
    async def test_score_and_knowledge_reject_nested_private_values(self):
        from did_backend.runtime import PublicCache
        c=PublicCache();c.on_json('score','{"battery":{"samples":[1]},"collected":true,"finished":{"schedule":[2]}}')
        c.on_json('knowledge','{"costs":[{"cell":{"x":0,"y":1},"energy_per_m":2,"uncertainty":{"zones":[3]}}]}')
        self.assertEqual(c.snapshot()['score'],{});self.assertEqual(c.snapshot()['knowledge'],[])
