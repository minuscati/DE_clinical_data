import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fetch_trial_updates import capture


def study(nct_id):
    return {"protocolSection": {
        "identificationModule": {"nctId": nct_id},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-10-13"}, "overallStatus": "RECRUITING"},
    }}


class CaptureTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "data").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "data")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cohort = self.root / "cohort.csv"
        self.cohort.write_text("nct_id\nNCT1\n", encoding="utf-8")
        self.day = date(2026, 10, 13)

    def run_pages(self, pages):
        responses = iter(pages)
        params = []
        def fetch(values):
            params.append(values)
            return next(responses)
        result = capture(self.day, self.day, self.cohort, self.root / "run", fetch=fetch)
        return result, params

    def test_pagination_and_known_cohort_selection(self):
        result, params = self.run_pages([
            {"totalCount": 2, "studies": [study("NCT9")], "nextPageToken": "second"},
            {"studies": [study("NCT1")]},
        ])
        self.assertEqual(params[1]["pageToken"], "second")
        self.assertEqual(result["unique_api_trials"], 2)
        self.assertEqual(result["matched_cohort_trials"], 1)
        self.assertEqual(len((self.root / "run" / "cohort_updates.jsonl").read_text().splitlines()), 1)

    def test_zero_updates_is_complete(self):
        result, _ = self.run_pages([{"totalCount": 0, "studies": []}])
        self.assertEqual(result["status"], "complete")

    def test_partial_pagination_cannot_produce_completed_output(self):
        with self.assertRaises(StopIteration):
            self.run_pages([{"totalCount": 2, "studies": [study("NCT1")], "nextPageToken": "second"}])
        self.assertFalse((self.root / "run" / "cohort_updates.jsonl").exists())
        self.assertEqual(json.loads((self.root / "run" / "manifest.json").read_text())["status"], "failed")

    def test_api_count_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Expected 2"):
            self.run_pages([{"totalCount": 2, "studies": [study("NCT1")]}])

    def test_repeated_page_token_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Repeated"):
            self.run_pages([
                {"studies": [], "nextPageToken": "loop"},
                {"studies": [], "nextPageToken": "loop"},
            ])


if __name__ == "__main__":
    unittest.main()
