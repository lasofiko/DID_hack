"""Общий словарь команды. Только форматы данных, без логики и валидации."""
from typing import Literal, NotRequired, TypedDict

Action = Literal["explore", "go_to", "collect", "return_to_base"]
Status = Literal["idle", "running", "paused", "returning", "finished", "stopped", "failed"]
Command = Literal["pause", "resume", "return", "stop"]


class Point(TypedDict):
    x: float
    y: float


class StartRequest(TypedDict):
    scenario: Literal["easy", "medium", "hard"]
    seed: int
    mode: Literal["baseline", "adaptive"]


class Observation(TypedDict):
    sim_time: float
    pose: Point
    battery: float
    signal: float
    pose_time: float
    battery_time: float
    signal_time: float
    scan_time: float
    obstacle_ahead: bool


class Subgoal(TypedDict):
    action: Action
    target: Point | None
    reason: str
    hypothesis_id: str | None


class Result(TypedDict):
    success: bool
    message: str


class MissionState(TypedDict):
    run_id: str | None
    status: Status
    observation: Observation | None
    goal: Subgoal | None
    collected: int
    delivered: int


class JournalEntry(TypedDict):
    sim_time: float
    hypothesis_id: str
    stage: Literal["hypothesis", "observation", "conclusion"]
    text: str


class EnergyMeasurement(TypedDict):
    cell: Point
    distance_m: float
    energy_used: float
    turning: bool
    # Total absolute angular travel in radians, not signed final heading delta.
    # Required at runtime for turning=True; absent/zero for straight movement.
    angle_rad: NotRequired[float]


class CostEstimate(TypedDict):
    energy_per_m: float
    uncertainty: float | None


class TurnEnergyMeasurement(TypedDict):
    cell: Point
    distance_m: float  # Zero for an isolated in-place turn.
    angle_rad: float  # Non-negative sum of absolute heading increments.
    energy_used: float


class TurnCostEstimate(TypedDict):
    energy_per_rad: float | None  # Unknown until configured or measured.
    uncertainty: float | None  # Standard deviation, energy/radian.
