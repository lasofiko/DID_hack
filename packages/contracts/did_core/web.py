"""Additive browser contract. All spatial data is public agent knowledge in map metres."""
from typing import TypedDict, Literal, NotRequired
from .types import MissionState, Point, JournalEntry

class SessionRequest(TypedDict):
    scenario: Literal['easy','medium','hard']
    seed: int
    mode: Literal['baseline','adaptive']
    planner_mode: NotRequired[Literal['algorithmic','llm']]

class MapData(TypedDict):
    width: int
    height: int
    resolution: float
    origin: Point
    origin_yaw: float
    data: list[int]
    revision: int

class Telemetry(TypedDict):
    state: MissionState
    connection: Literal["online","offline","connecting","error"]
    session: SessionRequest
    robot_pose: Point | None
    robot_yaw: float
    trajectory: list[Point]
    planned_path: list[Point]
    knowledge: list[dict]
    journal: list[JournalEntry]
    planner_source: str
    collected_positions: list[Point]
    events: list[dict]
    error: str | None
    score: dict
    map_revision: int
