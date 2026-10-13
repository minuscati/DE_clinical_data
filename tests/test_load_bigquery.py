"""Exercise corrupted inputs and quoted CSV records without cloud access."""

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "loader", Path(__file__).resolve().parents[1] / "src" / "load_bigquery.py"
)
loader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loader)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.headers = {
            "breast_studies": ["nct_id", "study_type", "brief_title"],
            "breast_sponsors": ["nct_id", "lead_or_collaborator"],
            "breast_conditions": ["nct_id", "mesh_term"],
        }
        for table, schema_name, _ in loader.TABLES:
            (self.root / schema_name).write_text(json.dumps([
                {"name": name, "type": "STRING", "mode": "NULLABLE"}
                for name in self.headers[table]
            ]), encoding="utf-8")
        self.write("breast_studies", [["NCT1", "INTERVENTIONAL", "Title, with\na newline"]])
        self.write("breast_sponsors", [["NCT1", "lead"]])
        self.write("breast_conditions", [["NCT1", "Breast Neoplasms"]])
        self.summary(1, 1, 1)

    def write(self, table, rows, header=None):
        with (self.root / f"{table}.csv").open("w", newline="", encoding="utf-8") as target:
            writer = csv.writer(target)
            writer.writerow(header or self.headers[table])
            writer.writerows(rows)

    def summary(self, studies, sponsors, conditions):
        (self.root / "cohort_summary.json").write_text(json.dumps({
            "selected_trials": studies, "sponsor_rows": sponsors, "condition_rows": conditions,
        }), encoding="utf-8")

    def check(self):
        return loader.preflight(self.root, self.root)

    def test_quoted_newlines_count_as_one_record(self):
        self.assertEqual([item["rows"] for item in self.check()], [1, 1, 1])

    def test_orphan_child_is_rejected(self):
        self.write("breast_conditions", [["NCT2", "Breast Neoplasms"]])
        with self.assertRaisesRegex(ValueError, "orphan"):
            self.check()

    def test_multiple_leads_are_rejected(self):
        self.write("breast_sponsors", [["NCT1", "lead"], ["NCT1", "lead"]])
        self.summary(1, 2, 1)
        with self.assertRaisesRegex(ValueError, "exactly one lead"):
            self.check()

    def test_column_order_change_is_rejected(self):
        self.write("breast_studies", [["INTERVENTIONAL", "NCT1", "Title"]],
                   header=["study_type", "nct_id", "brief_title"])
        with self.assertRaisesRegex(ValueError, "header/order"):
            self.check()

    def test_truncated_export_is_rejected(self):
        self.write("breast_conditions", [])
        with self.assertRaisesRegex(ValueError, "summary expects"):
            self.check()


if __name__ == "__main__":
    unittest.main()
