"""Separate movement/metre and in-place turn/radian estimates by cell centre.

No map geometry is inferred: ``estimate`` takes the same cell centre in map
coordinates as ``EnergyMeasurement.cell``. Split multi-cell segments upstream.
The contract has no timestamps or segment endpoints, so freshness and cell
membership must also be checked by the producer of measurements.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import math

from did_core.types import (
    CostEstimate, EnergyMeasurement, Point, TurnCostEstimate, TurnEnergyMeasurement,
)


def _number(value: object) -> float | None:
    """Accept finite JSON numbers, but never booleans or numeric strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _cell_key(point: object) -> tuple[float, float] | None:
    if not isinstance(point, Mapping):
        return None
    x, y = _number(point.get("x")), _number(point.get("y"))
    if x is None or y is None:
        return None
    return x, y


@dataclass
class _Statistics:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, rate: float) -> bool:
        """Welford's sample statistics; reject numerical overflow atomically."""
        count = self.count + 1
        delta = rate - self.mean
        mean = self.mean + delta / count
        m2 = self.m2 + delta * (rate - mean)
        if not math.isfinite(mean) or not math.isfinite(m2):
            return False
        self.count, self.mean, self.m2 = count, mean, max(0.0, m2)
        return True

    def uncertainty(self) -> float | None:
        return math.sqrt(self.m2 / (self.count - 1)) if self.count >= 2 else None


class _Diagnostics:
    """Counters per component; update's public return remains None."""

    def __init__(self) -> None:
        self._accepted = 0
        self._rejected = 0
        self._last_rejection: str | None = None

    def _reject(self, reason: str) -> None:
        self._rejected += 1
        self._last_rejection = reason

    def diagnostics(self) -> dict[str, int | str | None]:
        """Return a copy. last_rejection persists after a subsequent success."""
        return {"accepted": self._accepted, "rejected": self._rejected,
                "last_rejection": self._last_rejection}


class TurnEnergyModel(_Diagnostics):
    """Energy/radian from isolated in-place turns, independent of straight travel.

    Angles are total absolute angular travel in radians (never signed/net angles).
    Translation above an explicitly configured sensor tolerance is rejected:
    one mixed measurement cannot identify both coefficients. Default tolerance
    is zero. No uncalibrated physical cost is assumed.
    """

    def __init__(
        self,
        initial_energy_per_rad: float | None = None,
        *,
        min_angle_rad: float = 0.0,
        max_energy_per_rad: float | None = None,
        max_turn_distance_m: float = 0.0,
    ) -> None:
        super().__init__()
        initial = _number(initial_energy_per_rad) if initial_energy_per_rad is not None else None
        minimum = _number(min_angle_rad)
        maximum = _number(max_energy_per_rad) if max_energy_per_rad is not None else None
        tolerance = _number(max_turn_distance_m)
        if tolerance is None or tolerance < 0:
            raise ValueError("max_turn_distance_m must be finite and non-negative")
        if initial_energy_per_rad is not None and (initial is None or initial < 0):
            raise ValueError("initial_energy_per_rad must be finite and non-negative")
        if minimum is None or minimum < 0:
            raise ValueError("min_angle_rad must be finite and non-negative")
        if max_energy_per_rad is not None and (maximum is None or maximum <= 0):
            raise ValueError("max_energy_per_rad must be finite and positive")
        if maximum is not None and initial is not None and initial > maximum:
            raise ValueError("initial_energy_per_rad exceeds max_energy_per_rad")
        self._initial = initial
        self._minimum = minimum
        self._maximum = maximum
        self._distance_tolerance = tolerance
        self._cells: dict[tuple[float, float], _Statistics] = {}

    def update(self, measurement: TurnEnergyMeasurement) -> None:
        if not isinstance(measurement, Mapping):
            self._reject("invalid_measurement")
            return
        cell = _cell_key(measurement.get("cell"))
        distance = _number(measurement.get("distance_m"))
        angle = _number(measurement.get("angle_rad"))
        energy = _number(measurement.get("energy_used"))
        if (
            cell is None or distance is None or distance < 0
            or angle is None or angle <= 0
            or energy is None or energy < 0
        ):
            self._reject("invalid_measurement")
            return
        if distance > self._distance_tolerance:
            self._reject("mixed_motion")
            return
        if angle < self._minimum:
            self._reject("angle_below_minimum")
            return
        rate = energy / angle
        if not math.isfinite(rate) or (energy > 0 and rate == 0):
            self._reject("numerical_range")
            return
        if self._maximum is not None and rate > self._maximum:
            self._reject("rate_above_maximum")
            return
        stats = self._cells.get(cell, _Statistics())
        if stats.add(rate):
            self._cells[cell] = stats
            self._accepted += 1
        else:
            self._reject("numerical_range")

    def estimate(self, point: Point) -> TurnCostEstimate:
        cell = _cell_key(point)
        if cell is None:
            raise ValueError("point must contain finite numeric x and y")
        stats = self._cells.get(cell)
        if stats is None:
            return {"energy_per_rad": self._initial, "uncertainty": None}
        return {"energy_per_rad": stats.mean, "uncertainty": stats.uncertainty()}


class EnergyModel(_Diagnostics):
    """Arithmetic mean of accepted energy/metre measurements for each cell.

    ``initial_energy_per_m`` is required and comes from the caller's calibration
    or configuration. It is a fallback, not an extra measured sample.
    ``min_distance_m`` defaults to zero (only positive distances are accepted);
    set a larger threshold according to sensor resolution. Optionally configure
    ``max_energy_per_m`` using known measurement limits. There is deliberately
    no automatic outlier filter: a changed rate may be a real environment change.

    ``update`` routes isolated turning segments with angle_rad to the separate
    turn model. Mixed travel/turn segments are rejected to avoid double counting.
    ``estimate`` still returns only the movement estimate; use ``estimate_turn``
    for rotation and ``estimate_energy`` for one exclusive action.
    Invalid/unreliable measurements are ignored; invalid queries raise ValueError.
    Uncertainty is sample standard deviation of observed rates, not standard
    error of the mean. Unobserved cells and single samples have uncertainty=None.
    """

    def __init__(
        self,
        initial_energy_per_m: float,
        *,
        min_distance_m: float = 0.0,
        max_energy_per_m: float | None = None,
        initial_energy_per_rad: float | None = None,
        min_angle_rad: float = 0.0,
        max_energy_per_rad: float | None = None,
        max_turn_distance_m: float = 0.0,
        max_straight_angle_rad: float = 0.0,
    ) -> None:
        super().__init__()
        initial = _number(initial_energy_per_m)
        minimum = _number(min_distance_m)
        maximum = _number(max_energy_per_m) if max_energy_per_m is not None else None
        tolerance = _number(max_straight_angle_rad)
        if tolerance is None or tolerance < 0:
            raise ValueError("max_straight_angle_rad must be finite and non-negative")
        if initial is None or initial < 0:
            raise ValueError("initial_energy_per_m must be finite and non-negative")
        if minimum is None or minimum < 0:
            raise ValueError("min_distance_m must be finite and non-negative")
        if max_energy_per_m is not None and (maximum is None or maximum <= 0):
            raise ValueError("max_energy_per_m must be finite and positive")
        if maximum is not None and initial > maximum:
            raise ValueError("initial_energy_per_m exceeds max_energy_per_m")
        self._initial = initial
        self._minimum = minimum
        self._maximum = maximum
        self._angle_tolerance = tolerance
        self._cells: dict[tuple[float, float], _Statistics] = {}
        self.turns = TurnEnergyModel(
            initial_energy_per_rad,
            min_angle_rad=min_angle_rad,
            max_energy_per_rad=max_energy_per_rad,
            max_turn_distance_m=max_turn_distance_m,
        )

    def update(self, measurement: EnergyMeasurement) -> None:
        if not isinstance(measurement, Mapping):
            self._reject("invalid_measurement")
            return
        turning = measurement.get("turning")
        if type(turning) is not bool:
            self._reject("invalid_turning_flag")
            return
        if measurement.get("turning") is True:
            self.update_turn({
                "cell": measurement.get("cell"),
                "distance_m": measurement.get("distance_m"),
                "energy_used": measurement.get("energy_used"),
                "angle_rad": measurement.get("angle_rad"),
            })
            return
        # Legacy straight measurements without an angle remain supported.
        if "angle_rad" in measurement:
            angle = _number(measurement["angle_rad"])
            if angle is None or angle < 0:
                self._reject("invalid_measurement")
                return
            if angle > self._angle_tolerance:
                self._reject("mixed_motion")
                return
        cell = _cell_key(measurement.get("cell"))
        distance = _number(measurement.get("distance_m"))
        energy = _number(measurement.get("energy_used"))
        if (
            cell is None
            or measurement.get("turning") is not False
            or distance is None
            or distance <= 0
            or energy is None
            or energy < 0
        ):
            self._reject("invalid_measurement")
            return
        if distance < self._minimum:
            self._reject("distance_below_minimum")
            return
        rate = energy / distance
        if not math.isfinite(rate) or (energy > 0 and rate == 0):
            self._reject("numerical_range")
            return
        if self._maximum is not None and rate > self._maximum:
            self._reject("rate_above_maximum")
            return
        stats = self._cells.get(cell)
        if stats is None:
            stats = _Statistics()
        if stats.add(rate):
            self._cells[cell] = stats
            self._accepted += 1
        else:
            self._reject("numerical_range")

    def estimate(self, point: Point) -> CostEstimate:
        cell = _cell_key(point)
        if cell is None:
            raise ValueError("point must contain finite numeric x and y")
        stats = self._cells.get(cell)
        if stats is None:
            return {"energy_per_m": self._initial, "uncertainty": None}
        return {"energy_per_m": stats.mean, "uncertainty": stats.uncertainty()}

    def update_turn(self, measurement: TurnEnergyMeasurement) -> None:
        self.turns.update(measurement)

    def estimate_turn(self, point: Point) -> TurnCostEstimate:
        return self.turns.estimate(point)

    def estimate_energy(self, point: Point, distance_m: float, angle_rad: float) -> float | None:
        """Predict one action in a cell: straight travel OR an in-place turn.

        Pass zero for the inactive quantity. Two positive quantities are invalid.
        The requested distance or total turn angle must already be known.
        This method does not predict a route or the robot's future choices.
        None means the required turn coefficient has not been calibrated.
        Zero distance and angle return zero; idle energy is not modelled.
        """
        distance, angle = _number(distance_m), _number(angle_rad)
        if distance is None or distance < 0 or angle is None or angle < 0:
            raise ValueError("distance_m and angle_rad must be finite and non-negative")
        if distance > 0 and angle > 0:
            raise ValueError("predict either movement or a turn, not both")
        if _cell_key(point) is None:
            raise ValueError("point must contain finite numeric x and y")
        if distance > 0:
            energy = self.estimate(point)["energy_per_m"] * distance
        elif angle > 0:
            rate = self.estimate_turn(point)["energy_per_rad"]
            if rate is None:
                return None
            energy = rate * angle
        else:
            energy = 0.0
        if not math.isfinite(energy):
            raise ValueError("predicted energy overflows")
        return energy
