import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "results.py"


class ResultsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="did-results-test-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "test-runs.json"

    def run_cli(self, *args, test=True, input=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--file", str(self.path),
             *(["--test-data"] if test else []), *args],
            input=input, capture_output=True, text=True,
        )

    def add(self, *args):
        result = self.run_cli("add", *args)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknowns_zeroes_and_summary_denominator(self):
        self.add("--run-id", "test-ok", "--success", "yes", "--duration-s", "4", "--seed", "0", "--energy-used", "0")
        self.add("--run-id", "test-fail", "--success", "no", "--duration-s", "100", "--error", "TEST obstacle")
        self.add("--run-id", "test-unknown")
        self.add("--run-id", "test-ok-no-duration", "--success", "yes")
        records = json.loads(self.path.read_text())["runs"]
        self.assertEqual(records[0]["seed"], 0)
        self.assertEqual(records[0]["energy_used"], 0)
        self.assertIsNone(records[2]["duration_s"])
        self.assertIsNone(records[2]["success"])
        summary = json.loads(self.run_cli("summary").stdout)
        self.assertEqual(summary["runs_total"], 4)
        self.assertAlmostEqual(summary["success_rate_known_outcomes"], 2/3)
        self.assertEqual(summary["unknown_outcome"], 1)
        self.assertEqual(summary["successful_duration_s"], {"available": 1, "missing": 1, "mean": 4, "min": 4, "max": 4})
        self.assertEqual(summary["failures"][0]["error"], "TEST obstacle")

    def test_mixing_datasets_and_duplicates_are_rejected(self):
        self.add("--run-id", "test-1")
        before = self.path.read_bytes()
        for result in [self.run_cli("add", "--run-id", "test-2", test=False), self.run_cli("add", "--run-id", "test-1")]:
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_values_are_not_saved(self):
        for args in [("--duration-s", "nan"), ("--energy-used", "inf"), ("--duration-s", "-1"), ("--seed", "2147483648"), ("--collected", "-1"), ("--goal", "inf", "0"), ("--collected", "1", "--delivered", "2")]:
            with self.subTest(args=args):
                result = self.run_cli("add", "--run-id", "test-invalid", *args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.path.exists())

    def test_empty_summary_does_not_create_file(self):
        result = self.run_cli("summary")
        self.assertEqual(result.returncode, 0)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["runs_total"], 0)
        self.assertIsNone(summary["success_rate_known_outcomes"])
        self.assertIsNone(summary["successful_duration_s"]["mean"])
        self.assertFalse(self.path.exists())

    def test_interactive_blank_fields_become_null(self):
        result = self.run_cli("add", input="\n" * 12)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(self.path.read_text())["runs"][0]
        self.assertTrue(record["run_id"])
        for name in ("scenario", "seed", "mode", "initial_position", "goal", "success", "duration_s", "error", "energy_used", "collected", "delivered"):
            self.assertIsNone(record[name])

    def test_broken_file_is_not_overwritten(self):
        self.path.write_text("not json")
        result = self.run_cli("add", "--run-id", "test-1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.path.read_text(), "not json")


if __name__ == "__main__":
    unittest.main()
