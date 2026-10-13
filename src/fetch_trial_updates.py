"""Capture current CT.gov records updated in a date range; keep known-cohort matches."""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from load_bigquery import COHORT, ROOT, file_hash

API = "https://clinicaltrials.gov/api/v2/studies"


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def request_page(params):
    request = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={
        "Accept": "application/json", "User-Agent": "clinical-trial-learning-project/1.0",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
            retry_after = error.headers.get("Retry-After", "")
            delay = min(int(retry_after), 30) if retry_after.isdigit() else 2 ** (attempt + 1)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            delay = 2 ** (attempt + 1)
        print(f"Transient API error; retrying in {delay}s", flush=True)
        time.sleep(delay)


def capture(start_date, end_date, cohort_path, run_dir, page_size=250, fetch=request_page):
    """Return a complete run only after all pages and counts are validated."""
    with cohort_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "nct_id" not in reader.fieldnames:
            raise ValueError("Cohort file must have nct_id")
        ids = [row["nct_id"].strip() for row in reader]
    if not ids or any(not nct_id for nct_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Cohort must contain nonempty, unique trial IDs")
    cohort_ids = set(ids)
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    output = run_dir / "cohort_updates.jsonl"
    temporary_output = output.with_suffix(".jsonl.part")
    manifest = {
        "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
        "api": API, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
        "cohort_trials": len(ids), "cohort_sha256": file_hash(cohort_path),
        "pages": 0, "api_total_count": None, "unique_api_trials": 0,
        "matched_cohort_trials": 0, "duplicate_records": 0,
        "scope": "Existing snapshot cohort only; new trial admission is not implemented.",
        "note": "API returns current records, not historical versions. Date range refers to latest update posting dates.",
    }
    write_json(manifest_path, manifest)
    params = {
        "format": "json", "pageSize": page_size, "countTotal": "true",
        "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{start_date},{end_date}]",
    }
    seen = {}
    tokens = set()
    try:
        with temporary_output.open("w", encoding="utf-8", newline="\n") as target:
            while True:
                payload = fetch(params.copy())
                manifest["pages"] += 1
                page = manifest["pages"]
                write_json(run_dir / f"page_{page:05d}.json", payload)
                write_json(run_dir / f"request_{page:05d}.json", {
                    "params": params.copy(), "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
                if not isinstance(payload, dict) or not isinstance(payload.get("studies"), list):
                    raise ValueError("API response is missing the studies array")
                if page == 1:
                    manifest["api_total_count"] = payload.get("totalCount")
                for study in payload["studies"]:
                    protocol = study.get("protocolSection", {})
                    nct_id = protocol.get("identificationModule", {}).get("nctId")
                    updated = protocol.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date")
                    if not nct_id or not updated:
                        raise ValueError("API study missing nctId or last update date")
                    if not start_date <= date.fromisoformat(updated) <= end_date:
                        raise ValueError(f"{nct_id}: returned update date outside requested range")
                    fingerprint = json.dumps(study, sort_keys=True, ensure_ascii=False)
                    if nct_id in seen:
                        manifest["duplicate_records"] += 1
                        if seen[nct_id] != fingerprint:
                            raise ValueError("Record changed during pagination; retry the whole capture")
                        continue
                    seen[nct_id] = fingerprint
                    if nct_id in cohort_ids:
                        target.write(json.dumps(study, ensure_ascii=False) + "\n")
                        manifest["matched_cohort_trials"] += 1
                manifest["unique_api_trials"] = len(seen)
                write_json(manifest_path, manifest)
                print(f"Page {page}: {len(payload['studies'])} records; {manifest['matched_cohort_trials']} cohort matches", flush=True)
                token = payload.get("nextPageToken")
                if not token:
                    break
                if token in tokens:
                    raise ValueError("Repeated API page token; aborting incomplete capture")
                tokens.add(token)
                params["pageToken"] = token
                params["countTotal"] = "false"
        expected = manifest["api_total_count"]
        if expected is not None and expected != len(seen):
            raise ValueError(f"Expected {expected} unique API trials, received {len(seen)}; retry if source changed")
        if file_hash(cohort_path) != manifest["cohort_sha256"]:
            raise ValueError("Cohort changed during capture")
        temporary_output.replace(output)
        manifest["status"] = "complete"
        manifest["output_file"] = str(output)
        manifest["output_sha256"] = file_hash(output)
        print(f"PASS: {len(seen)} API trials; {manifest['matched_cohort_trials']} known-cohort updates", flush=True)
        return manifest
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        temporary_output.unlink(missing_ok=True)
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(manifest_path, manifest)
        print(f"Manifest: {manifest_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, help="Defaults to start-date")
    parser.add_argument("--page-size", type=int, default=250)
    parser.add_argument("--cohort-file", type=Path, default=COHORT / "breast_studies.csv")
    args = parser.parse_args()
    end_date = args.end_date or args.start_date
    if end_date < args.start_date or not 1 <= args.page_size <= 1000:
        parser.error("Invalid date range or page size (must be 1..1000)")
    run_dir = ROOT / "data" / "raw" / "ctgov_updates" / f"{args.start_date}_{end_date}" / uuid4().hex
    try:
        capture(args.start_date, end_date, args.cohort_file, run_dir, args.page_size)
        return 0
    except Exception as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
