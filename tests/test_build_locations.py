import csv
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from build_breast_locations import FIELDS, build


class LocationTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "data").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "data")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "breast_studies.csv").write_text("nct_id\nNCT1\nNCT2\n", encoding="utf-8")

    def archive(self, ids):
        text = io.StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=FIELDS, delimiter="|")
        writer.writeheader()
        for facility_id, nct_id in ids:
            row = dict.fromkeys(FIELDS, "")
            row.update(id=facility_id, nct_id=nct_id, country="Sweden", name="Hospital")
            writer.writerow(row)
        path = self.root / "snapshot.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("nested/facilities.txt", text.getvalue())
        return path

    def test_keeps_multiple_sites_and_reports_trials_without_locations(self):
        summary = build(self.archive([("1", "NCT1"), ("2", "NCT1"), ("3", "NCT9")]), self.root)
        self.assertEqual(summary["location_rows"], 2)
        self.assertEqual(summary["trials_with_locations"], 1)
        self.assertEqual(summary["trials_without_locations"], 1)

    def test_duplicate_facility_does_not_replace_previous_export(self):
        destination = self.root / "breast_locations.csv"
        destination.write_text("previous valid export", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build(self.archive([("1", "NCT1"), ("1", "NCT1")]), self.root)
        self.assertEqual(destination.read_text(), "previous valid export")


if __name__ == "__main__":
    unittest.main()
