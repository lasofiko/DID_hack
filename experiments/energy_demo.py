"""Standalone demonstration with artificial data, not robot experiment results."""

import json
import math
from pathlib import Path
import sys

# Allow running from a fresh checkout, without installing backend dependencies.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(REPO_ROOT / "packages" / "contracts"),
    str(REPO_ROOT / "packages" / "ml"),
]

from did_core.ports import EnergyModel as EnergyModelPort
from did_core.types import CostEstimate, EnergyMeasurement, Point, TurnCostEstimate
from did_ml.energy import EnergyModel


def show(label: str, estimate: CostEstimate | TurnCostEstimate) -> None:
    print(f"{label}: {json.dumps(estimate, ensure_ascii=False, allow_nan=False)}")


def main() -> None:
    print("ДЕМОНСТРАЦИОННЫЕ искусственные данные. Это не результаты робота.")
    print("Координаты — центры условных клеток в map; все числа только для примера.")
    cell: Point = {"x": 0.5, "y": 0.5}
    other: Point = {"x": 1.5, "y": 0.5}
    # Both instances use the same existing interface. MissionControl is not used.
    baseline: EnergyModelPort = EnergyModel(initial_energy_per_m=3.0, initial_energy_per_rad=1.0)
    adaptive: EnergyModelPort = EnergyModel(initial_energy_per_m=3.0, initial_energy_per_rad=1.0)
    show("До измерений", adaptive.estimate(cell))

    measurements: list[EnergyMeasurement] = [
        {"cell": cell, "distance_m": 0.2, "energy_used": 0.4, "turning": False},
        {"cell": cell, "distance_m": 0.2, "energy_used": 0.8, "turning": False},
        {"cell": cell, "distance_m": 0.2, "energy_used": 1.2, "turning": False},
    ]
    for index, measurement in enumerate(measurements, start=1):
        print(f"Измерение {index}: {json.dumps(measurement, allow_nan=False)}")
        # The caller chooses the mode: no update of baseline planning costs.
        adaptive.update(measurement)
        show("  baseline", baseline.estimate(cell))
        show("  adaptive", adaptive.estimate(cell))

    before_turn = adaptive.estimate(cell)
    adaptive.update(
        {"cell": cell, "distance_m": 0.2, "energy_used": 4.0, "turning": True}
    )
    assert adaptive.estimate(cell) == before_turn
    show("Смешанный замер без угла пропущен", adaptive.estimate(cell))

    for angle, energy in [(math.pi / 2, math.pi), (math.pi, 4 * math.pi)]:
        adaptive.update({"cell": cell, "distance_m": 0.0, "energy_used": energy,
                         "turning": True, "angle_rad": angle})
        show("После поворота: baseline", baseline.estimate_turn(cell))
        show("После поворота: adaptive", adaptive.estimate_turn(cell))
    movement = adaptive.estimate_energy(cell, 1.0, 0.0)
    turn = adaptive.estimate_energy(cell, 0.0, math.pi / 2)
    print(f"Прогноз только проезда на 1 м: {movement:.4f}")
    print(f"Прогноз только поворота на 90 градусов: {turn:.4f}")
    assert abs(movement - 4) < 1e-12
    assert abs(turn - 3 * math.pi / 2) < 1e-12
    uncalibrated = EnergyModel(initial_energy_per_m=3.0)
    print("Без калибровки поворотов прогноз:", uncalibrated.estimate_energy(cell, 0, math.pi))

    adaptive.update(
        {"cell": other, "distance_m": 0.2, "energy_used": 1.6, "turning": False}
    )
    show("Другая клетка, один замер", adaptive.estimate(other))
    show("Первая клетка не изменилась", adaptive.estimate(cell))
    assert baseline.estimate(cell) == {"energy_per_m": 3.0, "uncertainty": None}
    assert abs(adaptive.estimate(cell)["energy_per_m"] - 4.0) < 1e-12
    assert abs(adaptive.estimate(cell)["uncertainty"] - 2.0) < 1e-12
    print("Пример завершён. Подключение к ROS и выполнение маршрута здесь отсутствуют.")


if __name__ == "__main__":
    main()
