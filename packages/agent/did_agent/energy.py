"""EnergyModel port adapter from measured motion/battery, not environment ground truth."""
from collections import deque
import math
import statistics
import threading
from .navigation import distance, wrap

class ObservedEnergyModel:
    tile_size=0.5
    def __init__(self):
        self.samples={}
    def key(self,point):return math.floor(point['x']/self.tile_size),math.floor(point['y']/self.tile_size)
    def update(self,measurement):
        if measurement['turning'] or measurement['distance_m']<.025:return
        rate=measurement['energy_used']/measurement['distance_m']
        if not math.isfinite(rate) or not 0<=rate<=30:return
        self.samples.setdefault(self.key(measurement['cell']),deque(maxlen=7)).append(rate)
    def estimate(self,point):
        values=self.samples.get(self.key(point),[])
        return dict(energy_per_m=statistics.median(values) if values else 1.0,
                    uncertainty=statistics.pstdev(values) if len(values)>=2 else None)

class EnergyObserver:
    def __init__(self,planner,log,model=None):
        self.planner=planner;self.log=log;self.model=model or ObservedEnergyModel()
        self.anchor=None;self.values={};self.pending={};self.revision=0;self.lock=threading.RLock()
        self.interval=0;self.interval_id=None
    def _begin_interval(self,obs,yaw,stale=False):
        self.anchor=(obs,yaw);self.interval+=1;self.interval_id='energy-'+str(self.interval)
        text=('Hypothesis: measured cost differs; a local estimate may be stale' if stale else
              'Hypothesis: ordinary safe motion can estimate local energy cost; unknown cost is provisional')
        self.log(text,'hypothesis',self.interval_id)
        self.log('Passive experiment: observe the next ordinary motion interval of at least 0.2 m; safety may interrupt; turns are excluded','experiment',self.interval_id)
    def observe(self,obs,yaw):
        with self.lock:return self._observe(obs,yaw)
    def _observe(self,obs,yaw):
        if self.anchor is None:self._begin_interval(obs,yaw);return
        previous,old_yaw=self.anchor
        d=distance(previous['pose'],obs['pose'])
        if d<.2:return
        used=previous['battery']-obs['battery']
        turning=abs(wrap(yaw-old_yaw))>.2
        if turning or used<0:
            self._begin_interval(obs,yaw);return
        rate=used/d
        if not math.isfinite(rate) or rate>30:
            self._begin_interval(obs,yaw);return
        # Split one measured interval between traversed 0.5m tiles. Each receives
        # a proportional, provisional attribution, not a claim of exact ground cost.
        n=max(1,math.ceil(d/.1));groups={}
        for i in range(n):
            f=(i+.5)/n;p={k:previous['pose'][k]+f*(obs['pose'][k]-previous['pose'][k]) for k in ('x','y')}
            key=(math.floor(p['x']/.5),math.floor(p['y']/.5));groups[key]=groups.get(key,0)+1
        changed=False;stale=False
        for key,count in groups.items():
            cell={'x':(key[0]+.5)*.5,'y':(key[1]+.5)*.5}
            old=self.values.get(key)
            if old and abs(rate-old['energy_per_m'])>max(.6,3*(old['uncertainty'] or .15)):
                stale=True
                self.pending[key]=self.pending.get(key,0)+1
            self.log('Observed '+format(d*count/n,'.2f')+' m in '+str(cell)+'; provisional cost '+format(rate,'.2f')+' energy/m','observation',self.interval_id)
            try:
                self.model.update(dict(cell=cell,distance_m=d*count/n,energy_used=used*count/n,turning=False))
                estimate=self.model.estimate(cell)
                if not isinstance(estimate,dict) or not {'energy_per_m','uncertainty'}.issubset(estimate):raise ValueError('EnergyModel contract')
                if not isinstance(estimate['energy_per_m'],(int,float)) or not math.isfinite(estimate['energy_per_m']) or not 0<=estimate['energy_per_m']<=30:raise ValueError('Invalid cost')
                if estimate['uncertainty'] is not None and (not isinstance(estimate['uncertainty'],(int,float)) or not math.isfinite(estimate['uncertainty']) or estimate['uncertainty']<0):raise ValueError('Invalid uncertainty')
            except Exception:
                self.log('EnergyModel rejected measurement; keeping previous safe estimate')
                continue
            entry=dict(cell=cell,energy_per_m=max(1.0,float(estimate['energy_per_m'])),uncertainty=estimate['uncertainty'])
            self.values[key]=entry
            if (old is None or self.pending.get(key,0)>=2 or abs(entry['energy_per_m']-old['energy_per_m'])>.3):
                # One tile estimate updates all public map cells in that tile.
                for x in range(math.floor(key[0]*.5/self.planner.resolution),math.ceil((key[0]+1)*.5/self.planner.resolution)):
                    for y in range(math.floor(key[1]*.5/self.planner.resolution),math.ceil((key[1]+1)*.5/self.planner.resolution)):
                        point={'x':(x+.5)*self.planner.resolution,'y':(y+.5)*self.planner.resolution}
                        map_cell=self.planner.cell(point)
                        if self.planner.free(map_cell):self.planner.costs[map_cell]=entry['energy_per_m']
                self.log('Provisional inference from measured battery loss; uncertainty retained','conclusion',self.interval_id)
                self.pending.pop(key,None);self.revision+=1;changed=True
                self.log('Model updated from measured intervals; A* revision '+str(self.revision),'model_update',self.interval_id)
        self._begin_interval(obs,yaw,stale)
        return changed
    def public(self):
        with self.lock:return [dict(v) for v in self.values.values()]
