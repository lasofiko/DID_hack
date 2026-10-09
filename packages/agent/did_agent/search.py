"""Bounded signal-guided coverage; knows only public map and observations."""
from collections import deque
import math
import statistics
from .navigation import distance

class SampleSearch:
    def __init__(self, planner, config):
        self.planner, self.config = planner, config
        self.samples = deque(maxlen=5)
        self.visited = set()
        self.attempts = []
        self.failed_targets = set()
        self.local_steps = 0
        stride = max(1, int(config.search_spacing/planner.resolution))
        self.coverage = [planner.point((x,y)) for y in range(0,planner.height,stride)
                         for x in range(0,planner.width,stride) if planner.free((x,y))]
        self.last_pose = None
        self.history = deque(maxlen=80)
        self.last_signal_time = None

    def observe(self, observation):
        stamp = observation.get('signal_time')
        if stamp is not None and self.last_signal_time is not None and stamp <= self.last_signal_time:
            return
        self.last_signal_time = stamp
        pose = observation['pose']
        if self.last_pose is not None and distance(pose,self.last_pose) > 0.12:
            self.samples.clear()
        self.last_pose = dict(pose)
        self.samples.append(observation['signal'])
        self.visited.add(self.key(pose))
        if len(self.samples) >= 3:
            self.history.append((dict(pose), self.signal))

    def key(self, pose):
        return (round(pose['x']/0.20), round(pose['y']/0.20))

    @property
    def signal(self):
        return statistics.median(self.samples) if self.samples else 0.0

    def should_collect(self, pose):
        return len(self.samples) >= 3 and self.signal >= self.config.signal_collect and all(distance(pose,p) >= 0.25 for p in self.attempts)

    def collected(self, pose, success):
        self.attempts.append(dict(pose))
        self.samples.clear()
        self.local_steps = 0
        self.history.clear()

    def next_target(self, pose):
        candidates = []
        if self.signal >= self.config.signal_interest and self.local_steps < 20:
            self.local_steps += 1
            # Fit a local signal gradient from measured points (never judge coordinates).
            nearby = [(p,v) for p,v in self.history if distance(p,pose) < 0.8]
            gx = gy = 0.0
            if len(nearby) >= 3:
                mx = sum(p['x'] for p,v in nearby)/len(nearby)
                my = sum(p['y'] for p,v in nearby)/len(nearby)
                mv = sum(v for p,v in nearby)/len(nearby)
                xx = sum((p['x']-mx)**2 for p,v in nearby)
                yy = sum((p['y']-my)**2 for p,v in nearby)
                xy = sum((p['x']-mx)*(p['y']-my) for p,v in nearby)
                xv = sum((p['x']-mx)*(v-mv) for p,v in nearby)
                yv = sum((p['y']-my)*(v-mv) for p,v in nearby)
                det = xx*yy-xy*xy
                if det > 1e-8:
                    gx, gy = (xv*yy-yv*xy)/det, (yv*xx-xv*xy)/det
                elif xx+yy > 1e-8:
                    gx, gy = xv/(xx+yy), yv/(xx+yy)
            for i in range(8):
                a = i*math.pi/4
                p = {'x':pose['x']+0.22*math.cos(a), 'y':pose['y']+0.22*math.sin(a)}
                if self.key(p) not in self.visited:
                    candidates.append(p)
            candidates.sort(key=lambda p: -(gx*(p['x']-pose['x'])+gy*(p['y']-pose['y'])))
        elif self.signal < self.config.signal_interest:
            self.local_steps = 0
        # Coverage fallback prevents a noisy local maximum causing an infinite loop.
        candidates += sorted((p for p in self.coverage if self.key(p) not in self.visited), key=lambda p:distance(pose,p))
        for target in candidates:
            key = self.key(target)
            if key in self.failed_targets:
                continue
            try:
                self.planner.plan(pose,target)
                return target
            except ValueError:
                self.failed_targets.add(key)
        return None
