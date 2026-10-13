"""Verify the batch never starts downstream steps after a failure."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("batch", ROOT / "src" / "run_batch.py")
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


class BatchTests(unittest.TestCase):
    def setUp(self):
        # Keep all temporary outputs inside the project's ignored data directory.
        (ROOT / "data").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "data")
        self.addCleanup(temporary.cleanup)
        self.run_dir = Path(temporary.name) / "run"

    def test_failed_load_prevents_dbt_and_records_failure(self):
        steps = [("cohort", ["cohort"]), ("load", ["load"]), ("dbt_build", ["dbt"])]
        with patch.object(batch, "execute_step", side_effect=[0, 1]) as execute:
            self.assertEqual(batch.run_steps(steps, self.run_dir, {}), 1)
        self.assertEqual(execute.call_count, 2)
        report = json.loads((self.run_dir / "report.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertEqual([step["status"] for step in report["steps"]], ["passed", "failed"])

    def test_success_requires_every_step(self):
        with patch.object(batch, "execute_step", return_value=0) as execute:
            self.assertEqual(batch.run_steps([("load", ["load"]), ("dbt_build", ["dbt"])], self.run_dir, {}), 0)
        self.assertEqual(execute.call_count, 2)
        report = json.loads((self.run_dir / "report.json").read_text())
        self.assertEqual(report["status"], "passed")


if __name__ == "__main__":
    unittest.main()
