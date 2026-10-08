"""Measured single-cell exclusive-action intervals; no terrain ground truth.

Battery Float32 has no source stamp: use its ROS receipt-clock stamp and reject
large odom/receipt skew. Never divide a battery delta between cells/actions.
"""
import math
import threading
from .config import AgentConfig
from .navigation import distance, wrap

class EnergyObserver:
    def __init__(self,planner,log,model=None,config=None,adaptive=True):
        self.planner=planner;self.log=log;self.config=config or AgentConfig()
        if model is None:
            from did_ml.factory import make_energy_model
            model=make_energy_model(self.config)
        self.model=model;self.adaptive=adaptive;self.lock=threading.RLock()
        self.values={};self.revision=0;self.anchor=None;self.pose=None;self.pose_time=None
        self.length=0.;self.angle=0.;self.cells=set();self.last_battery_time=None
        self.mode='idle';self.mode_time=0.;self.interval=0;self.interval_id=''
        self.accepted=0;self.rejected={};self.last_measurement=None
        planner.default_cost=max(1.,self.config.energy_per_m)
        planner.default_turn_cost=self.config.energy_per_rad

    def key(self,p):
        # Energy grid has explicit 0.5m resolution and same origin/yaw as map;
        # it is not the navigation grid and is not a segmentation of ground truth.
        x=p['x']-self.planner.origin['x'];y=p['y']-self.planner.origin['y']
        c=math.cos(self.planner.origin_yaw);s=math.sin(self.planner.origin_yaw)
        r=self.config.energy_cell_size
        return math.floor((c*x+s*y)/r),math.floor((-s*x+c*y)/r)

    def center(self,key):
        r=self.config.energy_cell_size;x=(key[0]+.5)*r;y=(key[1]+.5)*r
        c=math.cos(self.planner.origin_yaw);s=math.sin(self.planner.origin_yaw)
        return dict(x=self.planner.origin['x']+c*x-s*y,y=self.planner.origin['y']+s*x+c*y)

    def note_command(self,v,w,t):
        with self.lock:
            mode='mixed' if v and w else 'move' if v else 'turn' if w else 'idle'
            if mode==self.mode:return
            self.mode=mode;self.mode_time=t;self.anchor=None;self.cells.clear()
            if mode in ('move','turn'):
                self.interval+=1;self.interval_id='energy-'+str(self.interval)
                self.log('Hypothesis: isolated '+mode+' interval can measure local energy cost','hypothesis',self.interval_id)
                self.log('Passive bounded experiment during ordinary safe '+mode+'; reject transitions and cell crossings','experiment',self.interval_id)

    def _reject(self,reason):
        self.rejected[reason]=self.rejected.get(reason,0)+1
        self.anchor=None;self.cells.clear()

    def _pose(self,p,t,yaw):
        if self.pose_time is not None:
            if t<=self.pose_time:return
            dt=t-self.pose_time
            if dt>.25:
                self._reject('odom_gap')
            else:
                d=distance(p,self.pose);a=abs(wrap(yaw-self.yaw))
                # Bound sampling so a >pi revolution cannot alias to zero.
                if d>self.config.max_linear*dt+.03 or a>self.config.max_angular*dt+.05:
                    self._reject('odom_jump')
                else:self.length+=d;self.angle+=a
        self.pose=dict(p);self.yaw=yaw;self.pose_time=t
        if self.anchor:self.cells.add(self.key(p))
        self.planner.start_yaw=yaw

    def _battery(self,b,t):
        if self.last_battery_time is not None and t<=self.last_battery_time:return False
        if self.last_battery_time is not None and t-self.last_battery_time>.3:self._reject('battery_gap')
        self.last_battery_time=t
        if self.pose is None or abs(t-self.pose_time)>self.config.energy_max_skew:
            self._reject('sensor_skew');return False
        if self.mode not in ('move','turn') or t-self.mode_time<self.config.energy_settle_time:
            self.anchor=None;return False
        key=self.key(self.pose)
        current=dict(battery=b,time=t,length=self.length,angle=self.angle,key=key)
        if self.anchor is None:
            self.anchor=current;self.cells={key};return False
        previous=self.anchor;self.cells.add(key)
        if len(self.cells)!=1 or previous['key']!=key:
            self._reject('cell_crossing');self.anchor=current;self.cells={key};return False
        d=self.length-previous['length'];a=self.angle-previous['angle'];used=previous['battery']-b
        if used<0:
            self._reject('battery_reset');return False
        if self.mode=='move':
            if a>self.config.straight_angle_tolerance:
                self._reject('mixed_motion');return False
            if d<self.config.energy_min_distance:return False
            measurement=dict(cell=self.center(key),distance_m=d,energy_used=used,turning=False,angle_rad=a)
            rate=used/d
        else:
            if d>self.config.turn_translation_tolerance:
                self._reject('mixed_motion');return False
            if a<self.config.energy_min_angle:return False
            measurement=dict(cell=self.center(key),distance_m=d,energy_used=used,angle_rad=a)
            rate=used/a
        # Consume interval before any model call, including rejection or exception.
        self.anchor=current;self.cells={key}
        if not math.isfinite(rate) or not 0<=rate<=30:
            self._reject('rate_limit');return False
        component='movement' if self.mode=='move' else 'turn'
        self.log('Measured '+component+': '+str(measurement)+'; battery receipt-clock skew bounded, odom approximation','observation',self.interval_id)
        try:
            diagnostics=self.model if self.mode=='move' else getattr(self.model,'turns',None)
            before=diagnostics.diagnostics()['accepted'] if callable(getattr(diagnostics,'diagnostics',None)) else None
            if self.mode=='move':self.model.update(measurement)
            else:self.model.update_turn(measurement)  # Exactly one component, once.
            if before is not None and diagnostics.diagnostics()['accepted']!=before+1:
                self._reject('model_rejected');return False
            move=self.model.estimate(measurement['cell']);turn=self.model.estimate_turn(measurement['cell'])
            for result,field in ((move,'energy_per_m'),(turn,'energy_per_rad')):
                value=result[field];u=result['uncertainty']
                if value is not None and (isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=30):raise ValueError('Invalid model estimate')
                if u is not None and (isinstance(u,bool) or not math.isfinite(u) or u<0):raise ValueError('Invalid model uncertainty')
            if move['energy_per_m'] is None:raise ValueError('Unknown movement prior')
        except Exception:
            self._reject('model_failure');self.log('EnergyModel rejected interval; retaining conservative route costs');return False
        old=self.values.get(key);self.accepted+=1;self.last_measurement=dict(component=component,**measurement)
        entry=dict(cell=self.center(key),energy_per_m=move['energy_per_m'],uncertainty=move['uncertainty'],
            energy_per_rad=turn['energy_per_rad'],turn_uncertainty=turn['uncertainty'],
            move_samples=(old or {}).get('move_samples',0)+(self.mode=='move'),
            turn_samples=(old or {}).get('turn_samples',0)+(self.mode=='turn'))
        self.values[key]=entry
        prior=(old or {}).get('energy_per_m' if self.mode=='move' else 'energy_per_rad')
        if prior is not None and abs(rate-prior)>max(.5,3*((old or {}).get('uncertainty' if self.mode=='move' else 'turn_uncertainty') or .05)):
            self.log('Measured cost disagrees with previous prediction; hypothesis: estimate may be stale','hypothesis',self.interval_id)
        self.log('Single-cell '+component+' estimate from actual battery/path/yaw; sample spread retained','conclusion',self.interval_id)
        self.log('Maria EnergyModel updated; '+('adaptive route costs enabled' if self.adaptive else 'baseline planning priors unchanged'),'model_update',self.interval_id)
        changed=self.adaptive and (old is None or any(abs((entry[k] if entry[k] is not None else self.config.energy_per_rad)-(old[k] if old[k] is not None else self.config.energy_per_rad))>.05 for k in ('energy_per_m','energy_per_rad')))
        if changed:
            # Only the directly measured energy cell is assigned its estimate.
            r=self.config.energy_cell_size;lo=(math.floor(key[0]*r/self.planner.resolution),math.floor(key[1]*r/self.planner.resolution))
            hi=(math.ceil((key[0]+1)*r/self.planner.resolution),math.ceil((key[1]+1)*r/self.planner.resolution))
            for x in range(lo[0],hi[0]):
                for y in range(lo[1],hi[1]):
                    cell=(x,y)
                    if self.planner.free(cell):
                        self.planner.costs[cell]=max(1.,entry['energy_per_m'])
                        self.planner.turn_costs[cell]=entry['energy_per_rad'] if entry['energy_per_rad'] is not None else self.config.energy_per_rad
            self.revision+=1
        return changed

    def observe(self,obs,yaw,samples=None,overflow=False):
        with self.lock:
            if overflow:self._reject('queue_overflow')
            if samples is None:
                # Endpoint-only adapter for explicit algorithm fixtures. ROS passes
                # the complete source odom/battery stream from RobotState instead.
                t=obs.get('pose_time',obs.get('sim_time',0.))
                samples=[('pose',obs['pose'],t,yaw),('battery',obs['battery'],obs.get('battery_time',t),None)]
            changed=False
            for kind,value,t,angle in samples:
                if kind=='pose':self._pose(value,t,angle)
                else:changed=self._battery(value,t) or changed
            return changed

    def public(self):
        with self.lock:return [dict(v) for v in self.values.values()]
    def diagnostics(self):
        with self.lock:return dict(accepted=self.accepted,rejected=dict(self.rejected),model='Maria EnergyModel',adaptive=self.adaptive)

    def predict_route(self,path,yaw=None):
        movement,turns=self.predict_components(path,yaw)
        return movement+turns

    def predict_components(self,path,yaw=None):
        # Known route segments and turns, not guesses about future mission actions.
        movement=0.;turns=0.;heading=self.planner.start_yaw if yaw is None else yaw
        for start,end in zip(path,path[1:]):
            d=distance(start,end)
            if d<1e-9:continue
            direction=math.atan2(end['y']-start['y'],end['x']-start['x']);a=abs(wrap(direction-heading))
            key=self.key(start);entry=self.values.get(key) if self.adaptive else None
            turn=(entry or {}).get('energy_per_rad')
            # Unknown is explicitly reserved, never interpreted as free rotation.
            turns+=a*(max(self.config.energy_per_rad,turn) if turn is not None else self.config.energy_per_rad)
            steps=max(1,math.ceil(d/(self.config.energy_cell_size*.2)))
            for i in range(steps):
                p={k:start[k]+(i+.5)/steps*(end[k]-start[k]) for k in ('x','y')}
                estimate=self.values.get(self.key(p)) if self.adaptive else None
                movement+=d/steps*max(self.config.energy_per_m,(estimate or {}).get('energy_per_m',self.config.energy_per_m))
            heading=direction
        return movement,turns
