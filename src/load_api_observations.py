"""Load complete API captures as deduplicated observations, preserving the AACT baseline."""

import argparse
import copy
import csv
import hashlib
import io
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from load_bigquery import ROOT, COHORT, file_hash

FIELDS = [
    ("observation_id", "STRING"), ("nct_id", "STRING"),
    ("last_update_posted_date", "DATE"), ("overall_status", "STRING"),
    ("observed_at", "TIMESTAMP"), ("last_seen_at", "TIMESTAMP"),
    ("source_run_id", "STRING"), ("payload_sha256", "STRING"), ("raw_json", "STRING"),
]
CONTENT_TABLE = "api_trial_content_observations"
LEGACY_TABLE = "api_trial_observations"


def content_identity(study):
    """Ignore only the registry refresh marker; retain all study content."""
    content = copy.deepcopy(study)
    misc = content.get("derivedSection", {}).get("miscInfoModule", {})
    misc.pop("versionHolder", None)
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    protocol = study["protocolSection"]
    nct_id = protocol["identificationModule"]["nctId"]
    updated = protocol["statusModule"]["lastUpdatePostDateStruct"]["date"]
    observation_id = hashlib.sha256(f"content-v2|{nct_id}|{updated}|{payload_hash}".encode()).hexdigest()
    return payload_hash, observation_id


def normalize_legacy(rows):
    """Collapse refresh-only versions without changing/deleting the legacy table."""
    grouped = {}
    for original in rows:
        row = dict(original)
        study = json.loads(row["raw_json"])
        protocol = study["protocolSection"]
        status = protocol["statusModule"]
        if (row["nct_id"] != protocol["identificationModule"]["nctId"]
                or str(row["last_update_posted_date"]) != status["lastUpdatePostDateStruct"]["date"]
                or row["overall_status"] != status["overallStatus"]):
            raise ValueError("Legacy observation fields disagree with raw JSON")
        full_raw = json.dumps(study, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if hashlib.sha256(full_raw.encode("utf-8")).hexdigest() != row["payload_sha256"]:
            raise ValueError("Legacy full-payload checksum mismatch")
        row["payload_sha256"], row["observation_id"] = content_identity(study)
        row["last_update_posted_date"] = str(row["last_update_posted_date"])
        for field in ("observed_at", "last_seen_at"):
            value = row[field]
            timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(value)
            if timestamp.tzinfo is None:
                raise ValueError("Legacy capture timestamp must include timezone")
            row[field] = timestamp.astimezone(timezone.utc).isoformat()
        key = row["observation_id"]
        if key not in grouped:
            grouped[key] = row
        else:
            previous = grouped[key]
            last_seen = max(previous["last_seen_at"], row["last_seen_at"])
            # Keep raw JSON and source run from the earliest captured content.
            if (row["observed_at"], row["source_run_id"]) < (previous["observed_at"], previous["source_run_id"]):
                grouped[key] = row
            grouped[key]["last_seen_at"] = last_seen
    return list(grouped.values())


def prepare(run_dir, cohort_file=COHORT / "breast_studies.csv"):
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("Only a complete API capture can be loaded")
    if file_hash(cohort_file) != manifest["cohort_sha256"]:
        raise ValueError("Capture was built against a different cohort; inspect before loading")
    with cohort_file.open(encoding="utf-8-sig", newline="") as source:
        cohort_ids = {row["nct_id"] for row in csv.DictReader(source)}
    input_path = run_dir / "cohort_updates.jsonl"
    if manifest.get("output_sha256") and file_hash(input_path) != manifest["output_sha256"]:
        raise ValueError("Captured JSONL checksum mismatch")
    # Older complete captures did not record output_sha256; counts and fields
    # are still validated, but their original byte integrity cannot be proven.
    if not manifest.get("output_sha256"):
        print("NOTE: legacy capture has no output checksum; validating count, cohort and fields")
    observed_at = datetime.fromisoformat(manifest["finished_at"])
    if observed_at.tzinfo is None:
        raise ValueError("Capture timestamp must include its timezone")
    start = date.fromisoformat(manifest["start_date"])
    end = date.fromisoformat(manifest["end_date"])
    rows, seen_ids = [], set()
    with input_path.open(encoding="utf-8") as source:
        for line in source:
            study = json.loads(line)
            protocol = study["protocolSection"]
            nct_id = protocol["identificationModule"]["nctId"]
            status = protocol["statusModule"]
            updated = status["lastUpdatePostDateStruct"]["date"]
            if nct_id not in cohort_ids or nct_id in seen_ids:
                raise ValueError("Capture contains an unknown or duplicate trial ID")
            if not start <= date.fromisoformat(updated) <= end:
                raise ValueError("Capture contains update date outside its range")
            if not status.get("overallStatus"):
                raise ValueError("Capture study is missing overallStatus")
            seen_ids.add(nct_id)
            raw = json.dumps(study, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            payload_hash, observation_id = content_identity(study)
            rows.append({
                "observation_id": observation_id, "nct_id": nct_id,
                "last_update_posted_date": updated, "overall_status": status["overallStatus"],
                "observed_at": observed_at.isoformat(), "last_seen_at": observed_at.isoformat(),
                "source_run_id": run_dir.name, "payload_sha256": payload_hash, "raw_json": raw,
            })
    if len(rows) != manifest["matched_cohort_trials"]:
        raise ValueError("JSONL row count does not match capture manifest")
    return rows


def merge(client, rows, project, location, report):
    from google.cloud import bigquery

    dataset = client.get_dataset(f"{project}.clinical_raw", timeout=60)
    if dataset.location.upper() != location.upper():
        raise ValueError("Dataset location mismatch")
    schema = [bigquery.SchemaField(name, type_, mode="REQUIRED") for name, type_ in FIELDS]
    destination = f"{project}.clinical_raw.{CONTENT_TABLE}"
    report["destination_table"] = destination
    table = bigquery.Table(destination, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="last_update_posted_date")
    table.clustering_fields = ["nct_id"]
    existing = client.create_table(table, exists_ok=True, timeout=60)
    if [(f.name, f.field_type) for f in existing.schema] != FIELDS:
        raise ValueError("Existing observation table schema differs; no rows loaded")
    if not rows:
        report.update(status="passed", input_rows=0, affected_rows=0)
        print("PASS: zero observations; empty destination exists")
        return
    staging_id = f"{project}.clinical_raw._api_stage_{uuid4().hex}"
    report["staging_table"] = staging_id
    staging = bigquery.Table(staging_id, schema=schema)
    staging.expires = datetime.now(timezone.utc) + timedelta(hours=24)
    client.create_table(staging, timeout=60)
    data = io.BytesIO(("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode("utf-8"))
    load = client.load_table_from_file(data, staging_id, location=location,
        job_config=bigquery.LoadJobConfig(schema=schema, source_format="NEWLINE_DELIMITED_JSON", write_disposition="WRITE_TRUNCATE"))
    report["load_job_id"] = load.job_id
    load.result(timeout=600)
    columns = ", ".join(name for name, _ in FIELDS)
    values = ", ".join(f"S.{name}" for name, _ in FIELDS)
    sql = f"""
        MERGE `{destination}` T USING `{staging_id}` S
        ON T.observation_id = S.observation_id
        WHEN MATCHED AND (S.last_seen_at > T.last_seen_at OR S.observed_at < T.observed_at) THEN
          UPDATE SET last_seen_at = GREATEST(S.last_seen_at, T.last_seen_at),
            raw_json = IF(S.observed_at < T.observed_at, S.raw_json, T.raw_json),
            source_run_id = IF(S.observed_at < T.observed_at, S.source_run_id, T.source_run_id),
            observed_at = LEAST(S.observed_at, T.observed_at)
        WHEN NOT MATCHED THEN
          INSERT ({columns}) VALUES ({values})
    """
    job = client.query(sql, location=location)
    report["merge_job_id"] = job.job_id
    job.result(timeout=600)
    report["affected_rows"] = job.num_dml_affected_rows
    validation = client.query(f"""
        SELECT COUNT(*) AS problems FROM (
          SELECT S.observation_id FROM `{staging_id}` S
          LEFT JOIN `{destination}` T ON S.observation_id = T.observation_id
          GROUP BY S.observation_id HAVING COUNT(T.observation_id) != 1
        )
    """, location=location)
    report["validation_job_id"] = validation.job_id
    if next(iter(validation.result(timeout=600))).problems:
        raise ValueError("Observation presence/uniqueness validation failed")
    report["status"] = "passed"
    try:
        client.delete_table(staging_id, timeout=60)
    except Exception as error:
        report["cleanup_warning"] = str(error)
    print(f"PASS: {len(rows)} observations verified; {job.num_dml_affected_rows} rows inserted/updated")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-dir", type=Path)
    mode.add_argument("--import-legacy", action="store_true",
                      help="Read old full-payload observations into the new content table; keep old table untouched")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="EU")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", args.project):
        parser.error("Invalid project ID")
    report_dir = ROOT / "data" / "processed" / "api_load_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{uuid4().hex}.json"
    report = {"status": "started", "project": args.project, "capture_dir": str(args.run_dir),
              "identity_version": "content-v2", "import_legacy": args.import_legacy,
              "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        if args.import_legacy:
            from google.cloud import bigquery
            with bigquery.Client(project=args.project, location=args.location) as client:
                job = client.query(f"SELECT * FROM `{args.project}.clinical_raw.{LEGACY_TABLE}`", location=args.location)
                report["legacy_read_job_id"] = job.job_id
                legacy = list(job.result(timeout=600))
                rows = normalize_legacy(legacy)
                report["legacy_rows"] = len(legacy)
                print(f"Legacy migration: {len(legacy)} raw versions -> {len(rows)} distinct content observations")
        else:
            rows = prepare(args.run_dir)
        report["input_rows"] = len(rows)
        if args.dry_run:
            report["status"] = "validated_only"
            print(f"PASS: {len(rows)} observations validated; no cloud writes")
        else:
            from google.cloud import bigquery
            with bigquery.Client(project=args.project, location=args.location) as client:
                merge(client, rows, args.project, args.location, report)
        return 0
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        print(f"FAILED: {error}", file=sys.stderr)
        print("After a timeout, check the reported cloud job IDs before retrying.", file=sys.stderr)
        return 1
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {path}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
