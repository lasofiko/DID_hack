"""Strict boundary checks shared by offline and future LLM decisions."""
import json
from math import isfinite
from did_core.types import Observation, Subgoal
from .context import nonnegative


class SubgoalValidationError(ValueError):
    """Local, safe diagnostic; contains no raw model output."""


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


def validate_subgoal(value, allowed_hypothesis_ids: set[str] | None = None) -> Subgoal:
    fields = {"action", "target", "reason", "hypothesis_id"}
    if not isinstance(value, dict) or set(value) != fields:
        raise SubgoalValidationError("Subgoal must contain exactly the four contract fields")
    if value["action"] not in ("explore", "go_to", "collect", "return_to_base"):
        raise SubgoalValidationError("Unknown action")
    if not isinstance(value["reason"], str) or not 1 <= len(value["reason"].strip()) <= 1000:
        raise SubgoalValidationError("Reason must contain 1..1000 characters")
    if value["hypothesis_id"] is not None:
        if not isinstance(value["hypothesis_id"], str) or value["hypothesis_id"] not in (allowed_hypothesis_ids or set()):
            raise SubgoalValidationError("hypothesis_id must be null or an active registered id")
    if value["action"] in ("explore", "go_to"):
        try:
            point(value["target"])
        except ValueError as exc:
            raise SubgoalValidationError(str(exc)) from None
    elif value["target"] is not None:
        raise SubgoalValidationError("Collect/return target must be null")
    return value


def parse_subgoal(raw: str, allowed_hypothesis_ids: set[str] | None = None) -> Subgoal:
    if not isinstance(raw, str) or len(raw) > 12000:
        raise SubgoalValidationError("Model response must be a bounded JSON string")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SubgoalValidationError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise SubgoalValidationError("Nonfinite JSON number")

    try:
        return validate_subgoal(json.loads(raw, object_pairs_hook=unique_pairs,
                                          parse_constant=invalid_constant), allowed_hypothesis_ids)
    except json.JSONDecodeError:
        raise SubgoalValidationError("Response is not a JSON object: remove Markdown and surrounding text") from None
    except (RecursionError, TypeError) as exc:
        raise SubgoalValidationError("Invalid JSON response") from exc
