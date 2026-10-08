"""Public navigation context supplied by backend; no scenario truth."""
from dataclasses import dataclass
from math import isfinite


def nonnegative(value: float, name: str) -> None:
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")


@dataclass(frozen=True)
class Candidate:
    id: str
    x: float
    y: float
    outbound_energy: float
    return_energy: float
    information_gain: float = 1.0

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Candidate id is required")
        for name in ("x", "y"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError(f"Invalid {name}")
        for name in ("outbound_energy", "return_energy", "information_gain"):
            nonnegative(getattr(self, name), name)


@dataclass(frozen=True)
class PlanningContext:
    """Backend computes reachable candidates and costs from the same observation."""
    sim_time: float
    pose_x: float
    pose_y: float
    home_energy: float
    candidates: tuple[Candidate, ...] = ()
    mission: str = "Find samples and return to base before the battery runs out."

    def __post_init__(self):
        nonnegative(self.sim_time, "sim_time")
        nonnegative(self.home_energy, "home_energy")
        for value in (self.pose_x, self.pose_y):
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError("Context pose must be finite")
        if not isinstance(self.candidates, tuple) or not all(isinstance(c, Candidate) for c in self.candidates):
            raise ValueError("Candidates must be an immutable tuple of Candidate")
        if len({c.id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Candidate ids must be unique")
        if not isinstance(self.mission, str) or not self.mission.strip() or len(self.mission) > 2000:
            raise ValueError("Mission must contain 1..2000 characters")


@dataclass(frozen=True)
class PlannerConfig:
    reserve: float = 8.0
    energy_factor: float = 1.5
    max_sensor_age: float = 1.0
    collect_threshold: float = 0.8
    signal_samples: int = 3
    signal_window: float = 3.0
    signal_radius: float = 0.15
    collect_cooldown: float = 5.0
    failed_target_cooldown: float = 20.0
    provider_timeout: float = 5.0
    provider_attempts: int = 2
    history_size: int = 50

    def __post_init__(self):
        for name in ("reserve", "energy_factor", "max_sensor_age", "collect_threshold",
                     "signal_window", "signal_radius", "collect_cooldown",
                     "failed_target_cooldown", "provider_timeout"):
            nonnegative(getattr(self, name), name)
        if self.energy_factor < 1 or not 0 < self.collect_threshold <= 1:
            raise ValueError("Invalid energy factor or signal threshold")
        if min(self.max_sensor_age, self.signal_window, self.signal_radius, self.provider_timeout) <= 0:
            raise ValueError("Windows, radius and timeout must be positive")
        for name in ("signal_samples", "provider_attempts", "history_size"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.signal_samples < 2 or self.history_size < self.signal_samples or self.provider_attempts > 2:
            raise ValueError("Require >=2 signal samples, sufficient history, and <=2 attempts")
