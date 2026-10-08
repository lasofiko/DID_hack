"""Thread-safe observations. Source sim timestamps and wall receipt times are distinct."""
from __future__ import annotations
import math
import threading
import time
from copy import deepcopy

class RobotState:
    def __init__(self, obstacle_distance=0.28):
        self.obstacle_distance = obstacle_distance
        self.lock = threading.RLock()
        self.values = {}
        self.received = {}
        self.yaw = 0.0
        self.front_distance = math.inf
        self.nearest_distance = math.inf
        self.events = []
        self.clock = None
        self.clock_received = None
        self.clock_valid = True

    def update_clock(self, sim_time, wall=None):
        wall = time.monotonic() if wall is None else wall
        if not math.isfinite(sim_time) or sim_time < 0:
            return
        with self.lock:
            if self.clock is not None and sim_time < self.clock:
                self.values.clear()
                self.received.clear()
                self.clock_valid = False  # Requires node restart after time reset.
            if self.clock is None or sim_time != self.clock:
                self.clock_received = wall
            self.clock = sim_time

    def update(self, kind, value, stamp, wall=None, yaw=None, nearest=None):
        wall = time.monotonic() if wall is None else wall
        if kind not in ('pose','battery','signal','scan'):
            return False
        try:
            valid = not isinstance(stamp,bool) and math.isfinite(stamp) and stamp >= 0
            if kind == 'pose':
                valid = valid and all(not isinstance(value[k],bool) and math.isfinite(value[k]) for k in ('x','y')) and yaw is not None and math.isfinite(yaw)
            elif kind == 'scan':
                valid = valid and value >= 0 and not math.isnan(value) and nearest is not None and nearest >= 0 and not math.isnan(nearest)
            else:
                valid = valid and not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and value >= 0 and (kind != 'signal' or value <= 1)
        except (TypeError,ValueError,KeyError):
            valid=False
        if not valid:
            # Invalid packets must revoke old data immediately, not refresh it.
            with self.lock:
                self.values.pop(kind,None)
                self.received.pop(kind,None)
            return False
        with self.lock:
            if kind in self.values and stamp < self.values[kind][1]:
                return False
            self.values[kind] = deepcopy(value), stamp
            self.received[kind] = wall
            if yaw is not None:
                self.yaw = yaw
            if kind == 'scan':
                self.front_distance, self.nearest_distance = value, nearest
        return True

    def snapshot(self):
        with self.lock:
            if self.clock is None or any(k not in self.values for k in ('pose','battery','signal','scan')):
                return None
            return dict(sim_time=self.clock, pose=deepcopy(self.values['pose'][0]),
                        battery=self.values['battery'][0], signal=self.values['signal'][0],
                        pose_time=self.values['pose'][1], battery_time=self.values['battery'][1],
                        signal_time=self.values['signal'][1], scan_time=self.values['scan'][1],
                        obstacle_ahead=self.front_distance < self.obstacle_distance)

    def fresh(self, timeout, wall=None):
        wall = time.monotonic() if wall is None else wall
        with self.lock:
            if not self.clock_valid or self.clock_received is None or wall-self.clock_received > timeout:
                return False
            # DDS does not order /clock against independent sensor topics. A
            # sensor packet can arrive just before its matching clock packet.
            # Bound this skew; large future stamps and stale wall data still fail.
            skew=min(0.1,timeout)
            return all(k in self.values and 0 <= wall-self.received[k] <= timeout and
                       -skew <= self.clock-self.values[k][1] <= timeout
                       for k in ('pose','battery','signal','scan'))

    def add_event(self, event):
        with self.lock:
            self.events.append(deepcopy(event))
            del self.events[:-100]


class SafetyManager:
    def __init__(self, state, config):
        self.state, self.config = state, config
        self.emergency = False

    def reason(self, wall=None, linear=0.0):
        with self.state.lock:
            if self.emergency:
                return 'EMERGENCY'
            if not self.state.fresh(self.config.data_timeout, wall):
                return 'STALE_DATA'
            if self.state.values['battery'][0] <= 0:
                return 'LOW_BATTERY'
            age=max(0.0, self.state.clock-self.state.values['scan'][1],
                    (time.monotonic() if wall is None else wall)-self.state.received['scan'])
            if self.state.nearest_distance < 0.16 or (linear > 0 and self.state.front_distance < self.config.obstacle_distance+linear*age):
                return 'BLOCKED'
        return None
