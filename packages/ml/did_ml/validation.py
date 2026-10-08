"""Strict boundary checks shared by offline and future LLM decisions."""
import json
from math import isfinite
from did_core.types import Observation, Subgoal
from .context import nonnegative


class UnsafeObservation(ValueError):
    """Backend must stop motion and obtain fresh observations/context."""


class PlanningUnavailable(RuntimeError):
    """No feasible proposal. Backend must stop/recover, never blindly execute."""


def validate_observation(obs: Observation, max_age: float) -> None:
    try:
        required = {"sim_time", "pose", "battery", "signal", "pose_time", "battery_time",
                    "signal_time", "scan_time", "obstacle_ahead"}
        if not isinstance(obs, dict) or set(obs) != required:
            raise ValueError("Observation fields do not match contract")
        point(obs["pose"])
        for field in required - {"pose", "obstacle_ahead"}:
            nonnegative(obs[field], field)
        if obs["signal"] > 1 or type(obs["obstacle_ahead"]) is not bool:
            raise ValueError("Invalid signal or obstacle flag")
        for field in ("pose_time", "battery_time", "signal_time", "scan_time"):
            if not 0 <= obs["sim_time"] - obs[field] <= max_age:
                raise ValueError(f"Stale or future {field}")
    except (ValueError, TypeError, KeyError) as exc:
        raise UnsafeObservation(str(exc)) from exc


def point(value):
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise ValueError("Expected point {x, y}")
    if any(type(v) not in (int, float) or not isfinite(v) for v in value.values()):
        raise ValueError("Coordinates must be finite numbers")


def validate_subgoal(value) -> Subgoal:
    fields = {"action", "target", "reason", "hypothesis_id"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Subgoal must contain exactly the four contract fields")
    if value["action"] not in ("explore", "go_to", "collect", "return_to_base"):
        raise ValueError("Unknown action")
    if not isinstance(value["reason"], str) or not 1 <= len(value["reason"].strip()) <= 1000:
        raise ValueError("Reason must contain 1..1000 characters")
    if value["hypothesis_id"] is not None:
        # No hypothesis registry is connected yet: never accept fabricated ids.
        raise ValueError("hypothesis_id must be null until the research journal is connected")
    if value["action"] in ("explore", "go_to"):
        point(value["target"])
    elif value["target"] is not None:
        raise ValueError("Collect/return target must be null")
    return value


def parse_subgoal(raw: str) -> Subgoal:
    if not isinstance(raw, str) or len(raw) > 12000:
        raise ValueError("Model response must be a bounded JSON string")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Invalid JSON number: {value}")

    try:
        return validate_subgoal(json.loads(raw, object_pairs_hook=unique_pairs,
                                          parse_constant=invalid_constant))
    except (RecursionError, TypeError) as exc:
        raise ValueError("Invalid JSON response") from exc
