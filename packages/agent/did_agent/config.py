"""Parameters shared by the deterministic agent and ROS adapter."""
from dataclasses import dataclass, fields
import json
import math
from pathlib import Path

@dataclass(frozen=True)
class AgentConfig:
    base_x: float = -2.0
    base_y: float = -0.5
    odom_x: float = -2.0
    odom_y: float = -0.5
    odom_yaw: float = 0.0
    max_linear: float = 0.18
    max_angular: float = 0.8
    goal_tolerance: float = 0.09
    base_tolerance: float = 0.18
    obstacle_distance: float = 0.28
    robot_clearance: float = 0.35
    data_timeout: float = 1.0
    motion_timeout: float = 120.0
    stuck_timeout: float = 12.0
    service_timeout: float = 5.0
    mission_timeout: float = 900.0
    control_period: float = 0.05
    battery_reserve: float = 8.0
    energy_per_m: float = 3.0
    return_factor: float = 1.5
    search_spacing: float = 0.35
    signal_interest: float = 0.25
    signal_collect: float = 0.78
    goal_samples: int = 1
    max_steps: int = 180
    planner_timeout: float = 3.0

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Non-finite/non-numeric config: ' + f.name)
            if f.name not in ('base_x', 'base_y', 'odom_x', 'odom_y', 'odom_yaw') and value <= 0:
                raise ValueError('Config must be positive: ' + f.name)
        if not isinstance(self.goal_samples, int) or not isinstance(self.max_steps, int):
            raise ValueError('Sample/step limits must be integers')
        if not 0 < self.signal_interest < self.signal_collect <= 1:
            raise ValueError('Invalid signal thresholds')
        if self.goal_tolerance >= self.base_tolerance:
            raise ValueError('Goal tolerance must be less than base tolerance')

    @property
    def base(self):
        return {'x': self.base_x, 'y': self.base_y}

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))
