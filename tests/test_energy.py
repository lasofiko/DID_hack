"""Run: python -m unittest discover -s tests -p 'test_energy.py'."""

import math
import unittest

from did_ml.energy import EnergyModel, TurnEnergyModel


CELL = {"x": 0.5, "y": 0.5}


def measurement(distance=1.0, energy=2.0, cell=None, turning=False):
    return {
        "cell": CELL.copy() if cell is None else cell,
        "distance_m": distance,
        "energy_used": energy,
        "turning": turning,
    }


class EnergyModelTests(unittest.TestCase):
    def test_fallback_and_first_measurement(self):
        model = EnergyModel(7.0)
        self.assertEqual(model.estimate(CELL), {"energy_per_m": 7.0, "uncertainty": None})
        self.assertIsNone(model.update(measurement(distance=2, energy=4)))
        self.assertEqual(model.estimate(CELL), {"energy_per_m": 2.0, "uncertainty": None})

    def test_mean_and_sample_standard_deviation_of_rates(self):
        model = EnergyModel(7)
        # Rates 2, 4 and 6 with different segment lengths. Prior is not a sample.
        for distance, energy in [(2, 4), (1, 4), (3, 18)]:
            model.update(measurement(distance=distance, energy=energy))
        self.assertEqual(model.estimate(CELL), {"energy_per_m": 4.0, "uncertainty": 2.0})

    def test_two_samples_and_constant_samples(self):
        model = EnergyModel(7)
        model.update(measurement(energy=2))
        model.update(measurement(energy=4))
        self.assertAlmostEqual(model.estimate(CELL)["uncertainty"], math.sqrt(2))
        constant = EnergyModel(7)
        for _ in range(3):
            constant.update(measurement())
        self.assertEqual(constant.estimate(CELL)["uncertainty"], 0)

    def test_cells_are_independent_and_centres_are_not_rounded(self):
        model = EnergyModel(7)
        other = {"x": -0.5, "y": 0.5}
        model.update(measurement(energy=2))
        model.update(measurement(energy=8, cell=other))
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 2)
        self.assertEqual(model.estimate(other)["energy_per_m"], 8)
        self.assertEqual(model.estimate({"x": 0.500001, "y": 0.5})["energy_per_m"], 7)

    def test_turns_and_missing_turn_flag_are_ignored(self):
        model = EnergyModel(7)
        model.update(measurement(energy=2))
        for flag in [True, 0, 1, None, "false"]:
            model.update(measurement(energy=100, turning=flag))
        incomplete = measurement(energy=100)
        del incomplete["turning"]
        model.update(incomplete)
        self.assertEqual(model.estimate(CELL), {"energy_per_m": 2.0, "uncertainty": None})

    def test_invalid_measurements_do_not_pollute_statistics(self):
        invalid = [None, [], {}, measurement(cell={}), measurement(cell={"x": True, "y": 0})]
        for value in [None, True, "2", float("nan"), float("inf"), -float("inf"), 10**1000]:
            invalid.extend([
                measurement(distance=value), measurement(energy=value),
                measurement(cell={"x": value, "y": 0}),
                measurement(cell={"x": 0, "y": value}),
            ])
        invalid.extend([
            measurement(distance=0), measurement(distance=-1), measurement(energy=-1),
            measurement(distance=1e-320, energy=1e300),
        ])
        for item in invalid:
            with self.subTest(item=item):
                model = EnergyModel(7)
                model.update(measurement())
                model.update(item)
                self.assertEqual(model.estimate(CELL), {"energy_per_m": 2.0, "uncertainty": None})

    def test_configured_reliability_limits(self):
        model = EnergyModel(2, min_distance_m=0.1, max_energy_per_m=10)
        model.update(measurement(distance=0.09, energy=0.18))
        model.update(measurement(energy=11))
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 2)
        self.assertIsNone(model.estimate(CELL)["uncertainty"])
        model.update(measurement(distance=0.1, energy=1))
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 10)

    def test_zero_energy_is_valid(self):
        model = EnergyModel(2)
        model.update(measurement(energy=0))
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 0)

    def test_overflow_in_statistics_is_rejected_atomically(self):
        model = EnergyModel(2)
        model.update(measurement())
        model.update(measurement(energy=1e308))
        self.assertEqual(model.estimate(CELL), {"energy_per_m": 2.0, "uncertainty": None})
        model.update(measurement(energy=4))
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 3)
        self.assertAlmostEqual(model.estimate(CELL)["uncertainty"], math.sqrt(2))

    def test_invalid_constructor_settings(self):
        for value in [-1, True, None, "1", float("nan"), float("inf")]:
            with self.subTest(initial=value), self.assertRaises(ValueError):
                EnergyModel(value)
        for field in ["min_distance_m", "max_energy_per_m"]:
            for value in [-1, True, "1", float("nan"), float("inf")]:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    EnergyModel(1, **{field: value})
        with self.assertRaises(ValueError):
            EnergyModel(1, min_distance_m=None)
        with self.assertRaises(ValueError):
            EnergyModel(1, max_energy_per_m=0)
        with self.assertRaises(ValueError):
            EnergyModel(2, max_energy_per_m=1)

    def test_invalid_query_and_return_value_is_a_copy(self):
        model = EnergyModel(2)
        for point in [None, {}, {"x": 0}, {"x": "1", "y": 0}, {"x": 0, "y": float("nan")}]:
            with self.subTest(point=point), self.assertRaises(ValueError):
                model.estimate(point)
        model.update(measurement())
        result = model.estimate(CELL)
        result["energy_per_m"] = 100
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 2)


class TurnEnergyTests(unittest.TestCase):
    def turn(self, angle=math.pi / 2, energy=3.0, distance=0.0, cell=None):
        return {"cell": CELL.copy() if cell is None else cell,
                "distance_m": distance, "angle_rad": angle, "energy_used": energy}

    def test_turn_cost_and_uncertainty(self):
        turns = TurnEnergyModel()
        self.assertEqual(turns.estimate(CELL), {"energy_per_rad": None, "uncertainty": None})
        turns.update(self.turn(angle=math.pi/2, energy=math.pi))  # rate 2
        self.assertEqual(turns.estimate(CELL), {"energy_per_rad": 2, "uncertainty": None})
        turns.update(self.turn(angle=math.pi, energy=4 * math.pi))  # rate 4
        self.assertEqual(turns.estimate(CELL)["energy_per_rad"], 3)
        self.assertAlmostEqual(turns.estimate(CELL)["uncertainty"], math.sqrt(2))

    def test_turns_do_not_change_movement_and_cells_are_independent(self):
        model = EnergyModel(2)
        other = {"x": 1.5, "y": 0.5}
        model.update({**self.turn(angle=1, energy=5), "turning": True})
        model.update_turn(self.turn(angle=1, energy=8, cell=other))
        self.assertEqual(model.estimate(CELL), {"energy_per_m": 2, "uncertainty": None})
        self.assertEqual(model.estimate_turn(CELL)["energy_per_rad"], 5)
        self.assertEqual(model.estimate_turn(other)["energy_per_rad"], 8)
        model.update(measurement(energy=4))
        self.assertEqual(model.estimate_turn(CELL)["energy_per_rad"], 5)

    def test_mixed_segments_are_not_counted_twice(self):
        model = EnergyModel(2, initial_energy_per_rad=3)
        model.update({**self.turn(angle=1, energy=20, distance=1), "turning": True})
        model.update({**measurement(energy=20), "angle_rad": 1})
        model.update_turn(self.turn(angle=1, energy=20, distance=1))
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 2)
        self.assertEqual(model.estimate_turn(CELL)["energy_per_rad"], 3)

    def test_prediction_and_unknown_turn_rate(self):
        model = EnergyModel(2)
        self.assertEqual(model.estimate_energy(CELL, 3, 0), 6)
        self.assertEqual(model.estimate_energy(CELL, 0, 0), 0)
        self.assertIsNone(model.estimate_energy(CELL, 0, math.pi))
        model.update_turn(self.turn(angle=math.pi/2, energy=4))
        self.assertAlmostEqual(model.estimate_energy(CELL, 0, math.pi), 8)
        self.assertAlmostEqual(model.estimate_energy(CELL, 0, math.pi/2), 4)

    def test_prediction_rejects_mixed_actions_before_and_after_calibration(self):
        for initial in [None, 3.0]:
            model = EnergyModel(2, initial_energy_per_rad=initial)
            with self.subTest(initial=initial), self.assertRaises(ValueError):
                model.estimate_energy(CELL, 1, 1)
        model = EnergyModel(2)
        for distance, angle in [(0, 0), (1, 0), (0, 1)]:
            with self.subTest(distance=distance, angle=angle), self.assertRaises(ValueError):
                model.estimate_energy({}, distance, angle)

    def test_prediction_requires_a_known_action_size(self):
        model = EnergyModel(2, initial_energy_per_rad=3)
        for distance, angle in [(None, 0), (0, None)]:
            with self.subTest(distance=distance, angle=angle), self.assertRaises(ValueError):
                model.estimate_energy(CELL, distance, angle)

    def test_separate_predictions_do_not_train_or_mix_components(self):
        model = EnergyModel(2, initial_energy_per_rad=3)
        movement_before = model.estimate(CELL)
        turn_before = model.estimate_turn(CELL)
        self.assertEqual(model.estimate_energy(CELL, 4, 0), 8)
        self.assertEqual(model.estimate_energy(CELL, 0, 2), 6)
        self.assertEqual(model.estimate(CELL), movement_before)
        self.assertEqual(model.estimate_turn(CELL), turn_before)
        self.assertEqual(model.diagnostics()["accepted"], 0)
        self.assertEqual(model.turns.diagnostics()["accepted"], 0)

    def test_total_angle_counts_both_directions_and_multiple_revolutions(self):
        model = EnergyModel(2, initial_energy_per_rad=3)
        # Two 90-degree turns in opposite directions have total travel pi, not 0.
        self.assertAlmostEqual(model.estimate_energy(CELL, 0, math.pi), 3*math.pi)
        model.update_turn(self.turn(angle=4*math.pi, energy=8*math.pi))
        self.assertAlmostEqual(model.estimate_turn(CELL)["energy_per_rad"], 2)

    def test_invalid_turn_measurements(self):
        invalid = [None, {}, self.turn(angle=0), self.turn(angle=-1), self.turn(distance=-1)]
        for value in [True, None, "1", float("nan"), float("inf"), 10**1000]:
            invalid.extend([self.turn(angle=value), self.turn(energy=value), self.turn(distance=value)])
        invalid.extend([self.turn(energy=-1), self.turn(angle=1e-320, energy=1e300)])
        for item in invalid:
            with self.subTest(item=item):
                turns = TurnEnergyModel(3)
                turns.update(item)
                self.assertEqual(turns.estimate(CELL), {"energy_per_rad": 3, "uncertainty": None})

    def test_turn_limits_and_numerical_overflow(self):
        turns = TurnEnergyModel(3, min_angle_rad=0.2, max_energy_per_rad=10)
        turns.update(self.turn(angle=0.1, energy=0.4))
        turns.update(self.turn(angle=1, energy=11))
        self.assertEqual(turns.estimate(CELL)["energy_per_rad"], 3)
        turns.update(self.turn(angle=0.2, energy=2))
        self.assertEqual(turns.estimate(CELL)["energy_per_rad"], 10)
        overflow = TurnEnergyModel()
        overflow.update(self.turn(angle=1, energy=2))
        overflow.update(self.turn(angle=1, energy=1e308))
        self.assertEqual(overflow.estimate(CELL), {"energy_per_rad": 2, "uncertainty": None})

    def test_turn_initial_settings_and_invalid_prediction(self):
        for value in [-1, True, "1", float("nan"), float("inf")]:
            for name in ["initial_energy_per_rad", "min_angle_rad", "max_energy_per_rad"]:
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    EnergyModel(2, **{name: value})
        with self.assertRaises(ValueError):
            TurnEnergyModel(3, max_energy_per_rad=2)
        model = EnergyModel(2, initial_energy_per_rad=3)
        for distance, angle in [(-1, 0), (1, -1), (True, 0), (0, "1"), (0, float("nan"))]:
            with self.subTest(distance=distance, angle=angle), self.assertRaises(ValueError):
                model.estimate_energy(CELL, distance, angle)
        with self.assertRaises(ValueError):
            model.estimate_energy(CELL, 1e308, 0)

    def test_zero_turn_energy_and_estimate_copy(self):
        turns = TurnEnergyModel(3)
        turns.update(self.turn(energy=0))
        self.assertEqual(turns.estimate(CELL)["energy_per_rad"], 0)
        result = turns.estimate(CELL)
        result["energy_per_rad"] = 100
        self.assertEqual(turns.estimate(CELL)["energy_per_rad"], 0)

    def test_legacy_turn_missing_angle_and_straight_invalid_angle(self):
        model = EnergyModel(2)
        model.update(measurement(distance=0, energy=10, turning=True))
        self.assertIsNone(model.estimate_turn(CELL)["energy_per_rad"])
        for angle in [None, True, "0", -1, float("nan")]:
            model.update({**measurement(energy=10), "angle_rad": angle})
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 2)
        model.update({**measurement(energy=4), "angle_rad": 0})
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 4)


class ReliabilityTests(unittest.TestCase):
    def test_strict_defaults_and_explicit_noise_tolerances(self):
        turn = {"cell": CELL, "distance_m": 0.001,
                "energy_used": 4.0, "angle_rad": 1.0, "turning": True}
        straight = {**measurement(energy=3), "angle_rad": 0.001}
        strict = EnergyModel(2)
        strict.update(turn)
        strict.update(straight)
        self.assertIsNone(strict.estimate_turn(CELL)["energy_per_rad"])
        self.assertEqual(strict.estimate(CELL)["energy_per_m"], 2)
        tolerant = EnergyModel(2, max_turn_distance_m=0.001, max_straight_angle_rad=0.001)
        tolerant.update(turn)
        tolerant.update(straight)
        self.assertEqual(tolerant.estimate_turn(CELL)["energy_per_rad"], 4)
        self.assertEqual(tolerant.estimate(CELL)["energy_per_m"], 3)
        tolerant.update({**turn, "distance_m": 0.0011, "energy_used": 100})
        tolerant.update({**straight, "angle_rad": 0.0011, "energy_used": 100})
        self.assertEqual(tolerant.estimate_turn(CELL)["energy_per_rad"], 4)
        self.assertEqual(tolerant.estimate(CELL)["energy_per_m"], 3)

    def test_tolerances_do_not_accept_negative_values(self):
        model = EnergyModel(2, max_turn_distance_m=0.01, max_straight_angle_rad=0.01)
        model.update_turn({"cell": CELL, "distance_m": -0.001,
                           "energy_used": 4, "angle_rad": 1})
        model.update({**measurement(energy=4), "angle_rad": -0.001})
        self.assertIsNone(model.estimate_turn(CELL)["energy_per_rad"])
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 2)

    def test_diagnostics_by_component_and_copy(self):
        model = EnergyModel(2, min_distance_m=0.1)
        model.update(measurement(distance=0.01))
        model.update({**measurement(), "angle_rad": 1})
        model.update(measurement())
        self.assertEqual(model.diagnostics(), {"accepted": 1, "rejected": 2,
                                               "last_rejection": "mixed_motion"})
        model.update({"cell": CELL, "distance_m": 0,
                      "energy_used": 4, "angle_rad": 1, "turning": True})
        model.update({"cell": CELL, "distance_m": 0,
                      "energy_used": 4, "turning": True})
        self.assertEqual(model.turns.diagnostics(), {"accepted": 1, "rejected": 1,
                                                     "last_rejection": "invalid_measurement"})
        self.assertEqual(model.diagnostics()["accepted"], 1)
        result = model.diagnostics()
        result["accepted"] = 999
        self.assertEqual(model.diagnostics()["accepted"], 1)

    def test_underflow_is_not_mistaken_for_free_movement(self):
        model = EnergyModel(2)
        model.update(measurement(distance=1e300, energy=1e-300))
        model.update_turn({"cell": CELL, "distance_m": 0,
                           "energy_used": 1e-300, "angle_rad": 1e300})
        self.assertEqual(model.estimate(CELL)["energy_per_m"], 2)
        self.assertIsNone(model.estimate_turn(CELL)["energy_per_rad"])
        self.assertEqual(model.diagnostics()["last_rejection"], "numerical_range")
        self.assertEqual(model.turns.diagnostics()["last_rejection"], "numerical_range")

    def test_invalid_tolerance_settings(self):
        for name in ["max_turn_distance_m", "max_straight_angle_rad"]:
            for value in [-1, None, True, "0", float("nan"), float("inf")]:
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    EnergyModel(2, **{name: value})


if __name__ == "__main__":
    unittest.main()
