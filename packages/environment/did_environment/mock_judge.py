"""Seeded local judge. Private scene/events never enter agent telemetry."""
import math
import random
from collections import deque
from did_agent.navigation import distance
from did_core.scenarios import SCENARIOS

class MockJudge:
    SCENARIO_CLEARANCE=0.20
    def __init__(self,planner,config,seed=1,scenario='easy'):
        if scenario not in SCENARIOS:raise ValueError('Unknown scenario')
        self.config=config;self.scenario=scenario;self.random=random.Random(seed)
        self.battery=60.0;self.collected=0;self.finished=False;self.events=[];self.previous=None
        self._samples=[];self._epoch=None;self._private_events=[];self._applied=set();self._fault=False
        start=planner.cell(config.base)
        if not planner.free(start):raise ValueError('Base is blocked')
        reachable={start};queue=deque([start])
        while queue:
            x,y=queue.popleft()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                cell=(x+dx,y+dy)
                if cell not in reachable and planner.free(cell):reachable.add(cell);queue.append(cell)
        free=[planner.point((x,y)) for y in range(planner.height) for x in range(planner.width) if (x,y) in reachable]
        self.random.shuffle(free)
        for p in free:
            if distance(p,config.base)>.65 and all(distance(p,q)>.60 for q in self._samples):
                self._samples.append(p)
                if len(self._samples)==SCENARIOS[scenario]['samples']:break
        if len(self._samples)!=SCENARIOS[scenario]['samples']:raise ValueError('Map cannot fit scenario samples')
        self._terrain=dict(self._samples[-1])
        self._zones=[dict(center=dict(self._terrain),radius=.55,cost=2.0)]
        if scenario!='easy':
            self._zones=[]
            for i,p in enumerate(self._samples[:SCENARIOS[scenario]['zones']]):
                self._zones.append(dict(center=dict(p),radius=.5,cost=2.0+i*.75))
        self._hazard=next(dict(p) for p in free if distance(p,config.base)>.9)
        self._schedule={'cost':25+seed%5,'hazard':55+seed%7,'sensor':85+seed%9}
        self._last_time=None;self._hazard_seen=False
    def start(self,sim_time):
        if self._epoch is None:self._epoch=sim_time
    @staticmethod
    def valid_pose(pose):
        try:return all(not isinstance(pose[k],bool) and math.isfinite(pose[k]) for k in ('x','y'))
        except (TypeError,KeyError):return False
    def _advance(self,sim_time):
        if self.scenario!='hard' or self._epoch is None:return
        age=sim_time-self._epoch
        for kind,at in self._schedule.items():
            if age>=at and kind not in self._applied:
                self._applied.add(kind);self._private_events.append(dict(kind=kind,sim_time=sim_time))
                if kind=='cost':self._zones[0]['cost']*=2.0
        self._fault=self._schedule['sensor']<=age<self._schedule['sensor']+15
    def observe(self,pose,yaw,sim_time=None):
        if not self.valid_pose(pose) or not math.isfinite(yaw):return self.battery,0.0
        if sim_time is not None:self._advance(sim_time)
        if self.previous is not None and not self.finished:
            before,old_yaw=self.previous;d=distance(pose,before)
            angle=abs(math.atan2(math.sin(yaw-old_yaw),math.cos(yaw-old_yaw)))
            midpoint={k:(pose[k]+before[k])/2 for k in ('x','y')}
            rate=max([1.0]+[z['cost'] for z in self._zones if distance(midpoint,z['center'])<z['radius']])
            self.battery=max(0.0,self.battery-d*rate-.03*angle)
            if 'hazard' in self._applied and distance(pose,self._hazard)<.35:
                dt=max(0,min(1,sim_time-(self._last_time if self._last_time is not None else sim_time))) if sim_time is not None else 0
                self.battery=max(0.0,self.battery-.8*dt)
                if not self._hazard_seen:self.events.append(dict(type='hazard_hit'));self._hazard_seen=True
        self.previous=dict(pose),yaw
        if sim_time is not None:self._last_time=sim_time
        nearest=min((distance(pose,p) for p in self._samples),default=math.inf)
        signal=math.exp(-nearest/.9) if math.isfinite(nearest) else 0.0
        measured=max(0.0,min(1.0,signal+self.random.gauss(0,.015)))
        return self.battery, math.nan if self._fault else measured
    def collect(self,pose):
        if not self.valid_pose(pose):return dict(success=False,message='Invalid pose')
        if self.finished or self.battery<=0:return dict(success=False,message='Inactive mission')
        for p in self._samples:
            if distance(pose,p)<.30:
                self._samples.remove(p);self.collected+=1;self.events.append(dict(type='sample_collected'))
                return dict(success=True,message='Sample collected')
        self.events.append(dict(type='false_collect'));self.battery=max(0,self.battery-.2)
        return dict(success=False,message='No sample within 0.30 m')
    def finish(self,pose):
        if not self.valid_pose(pose):return dict(success=False,message='Invalid pose')
        if self.battery<=0 or distance(pose,self.config.base)>self.config.base_tolerance:return dict(success=False,message='Not safely at base')
        self.finished=True;return dict(success=True,message='Returned to base')
    def score(self):
        return dict(collected=self.collected,delivered=self.collected if self.finished else 0,battery=self.battery,finished=self.finished,mock=True)
