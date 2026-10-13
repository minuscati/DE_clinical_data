import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from load_api_observations import prepare
from load_bigquery import file_hash


class ObservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "data")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cohort = self.root / "cohort.csv"
        self.cohort.write_text("nct_id\nNCT1\n", encoding="utf-8")
        self.payload = {"protocolSection": {
            "identificationModule": {"nctId": "NCT1"},
            "statusModule": {"overallStatus": "RECRUITING", "lastUpdatePostDateStruct": {"date": "2026-10-13"}},
        }}

    def capture(self, name, finished="2026-10-13T10:00:00+00:00", status="complete", count=1):
        path = self.root / name
        path.mkdir()
        output = path / "cohort_updates.jsonl"
        output.write_text(json.dumps(self.payload) + "\n", encoding="utf-8")
        (path / "manifest.json").write_text(json.dumps({
            "status": status, "cohort_sha256": file_hash(self.cohort),
            "output_sha256": file_hash(output), "finished_at": finished,
            "start_date": "2026-10-13", "end_date": "2026-10-13", "matched_cohort_trials": count,
        }), encoding="utf-8")
        return path

    def test_same_payload_on_later_capture_has_same_key(self):
        first = prepare(self.capture("first"), self.cohort)[0]
        second = prepare(self.capture("second", finished="2026-10-14T10:00:00+00:00"), self.cohort)[0]
        self.assertEqual(first["observation_id"], second["observation_id"])
        self.assertNotEqual(first["last_seen_at"], second["last_seen_at"])

    def test_changed_status_on_same_posting_date_has_new_key(self):
        first = prepare(self.capture("first"), self.cohort)[0]
        self.payload["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
        second = prepare(self.capture("second"), self.cohort)[0]
        self.assertNotEqual(first["observation_id"], second["observation_id"])

    def test_failed_capture_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "complete"):
            prepare(self.capture("failed", status="failed"), self.cohort)

    def test_modified_payload_is_rejected(self):
        path = self.capture("modified")
        (path / "cohort_updates.jsonl").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum"):
            prepare(path, self.cohort)

    def test_wrong_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "row count"):
            prepare(self.capture("wrong_count", count=2), self.cohort)


if __name__ == "__main__":
    unittest.main()
