import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from load_api_observations import prepare, content_identity, normalize_legacy
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

    def test_refresh_marker_does_not_change_identity_or_strip_raw_json(self):
        self.payload["derivedSection"] = {"miscInfoModule": {"versionHolder": "2026-10-13"}}
        first = prepare(self.capture("first"), self.cohort)[0]
        self.payload["derivedSection"]["miscInfoModule"]["versionHolder"] = "2026-10-14"
        original = copy.deepcopy(self.payload)
        second = prepare(self.capture("second"), self.cohort)[0]
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])
        self.assertEqual(first["observation_id"], second["observation_id"])
        self.assertNotEqual(first["raw_json"], second["raw_json"])
        self.assertEqual(original, self.payload)

    def test_other_derived_fields_still_change_identity(self):
        self.payload["derivedSection"] = {"miscInfoModule": {"versionHolder": "2026-10-13", "other": "a"}}
        first = content_identity(self.payload)
        self.payload["derivedSection"]["miscInfoModule"]["other"] = "b"
        self.assertNotEqual(first, content_identity(self.payload))

    def test_posting_date_and_array_order_are_not_ignored(self):
        self.payload["protocolSection"]["conditionsModule"] = {"conditions": ["A", "B"]}
        first = content_identity(self.payload)
        self.payload["protocolSection"]["conditionsModule"]["conditions"].reverse()
        self.assertNotEqual(first, content_identity(self.payload))
        self.payload["protocolSection"]["conditionsModule"]["conditions"].reverse()
        self.payload["protocolSection"]["statusModule"]["lastUpdatePostDateStruct"]["date"] = "2026-10-14"
        self.assertNotEqual(first, content_identity(self.payload))

    def legacy_row(self, name, finished, marker):
        self.payload["derivedSection"] = {"miscInfoModule": {"versionHolder": marker}}
        row = prepare(self.capture(name, finished=finished), self.cohort)[0]
        row["payload_sha256"] = hashlib.sha256(row["raw_json"].encode("utf-8")).hexdigest()
        row["observation_id"] = "legacy-" + name
        return row

    def test_legacy_migration_collapses_marker_and_preserves_capture_bounds(self):
        first = self.legacy_row("first", "2026-10-13T10:00:00+00:00", "2026-10-13")
        second = self.legacy_row("second", "2026-10-14T12:00:00+02:00", "2026-10-14")
        original = copy.deepcopy([first, second])
        result = normalize_legacy([second, first])
        self.assertEqual(1, len(result))
        self.assertEqual(first["observed_at"], result[0]["observed_at"])
        self.assertEqual("2026-10-14T10:00:00+00:00", result[0]["last_seen_at"])
        self.assertEqual(first["source_run_id"], result[0]["source_run_id"])
        self.assertEqual(first["raw_json"], result[0]["raw_json"])
        self.assertEqual(original, [first, second])
        self.assertEqual(result, normalize_legacy([first, second]))

    def test_legacy_migration_keeps_real_status_change(self):
        first = self.legacy_row("first", "2026-10-13T10:00:00+00:00", "2026-10-13")
        self.payload["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
        second = self.legacy_row("second", "2026-10-14T10:00:00+00:00", "2026-10-14")
        self.assertEqual(2, len(normalize_legacy([first, second])))

    def test_legacy_migration_rejects_inconsistent_or_modified_rows(self):
        row = self.legacy_row("first", "2026-10-13T10:00:00+00:00", "2026-10-13")
        modified = dict(row, overall_status="COMPLETED")
        with self.assertRaisesRegex(ValueError, "disagree"):
            normalize_legacy([modified])
        with self.assertRaisesRegex(ValueError, "checksum"):
            normalize_legacy([dict(row, payload_sha256="bad")])

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
