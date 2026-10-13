"""Validate all cohort CSVs, then replace the three BigQuery raw tables."""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
COHORT = ROOT / "data" / "processed" / "breast_cohort"
TABLES = (
    ("breast_studies", "studies_schema.json", "selected_trials"),
    ("breast_sponsors", "sponsors_schema.json", "sponsor_rows"),
    ("breast_conditions", "conditions_schema.json", "condition_rows"),
)
csv.field_size_limit(16 * 1024 * 1024)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preflight(cohort_dir, schema_dir, include_locations=False):
    """Reject inconsistent files before any cloud table is modified."""
    summary = json.loads((cohort_dir / "cohort_summary.json").read_text(encoding="utf-8"))
    if summary.get("selected_trials", 0) <= 0:
        raise ValueError("The cohort summary must contain a positive selected_trials count")
    prepared = []
    study_ids = set()
    tables = list(TABLES)
    if include_locations:
        locations = json.loads((cohort_dir / "locations_summary.json").read_text(encoding="utf-8"))
        if file_hash(cohort_dir / "breast_studies.csv") != locations["study_csv_sha256"]:
            raise ValueError("Locations were built for a different cohort; rebuild locations")
        if file_hash(cohort_dir / "breast_locations.csv") != locations["location_csv_sha256"]:
            raise ValueError("Locations CSV changed since extraction")
        summary["location_rows"] = locations["location_rows"]
        tables.append(("breast_locations", "locations_schema.json", "location_rows"))
    for table_name, schema_name, count_key in tables:
        path = cohort_dir / f"{table_name}.csv"
        schema = json.loads((schema_dir / schema_name).read_text(encoding="utf-8"))
        names = [field["name"] for field in schema]
        if len(names) != len(set(names)) or any(field["type"] != "STRING" for field in schema):
            raise ValueError(f"{table_name}: expected unique, all-STRING raw schema fields")
        ids, leads = Counter(), Counter()
        facility_ids = set()
        count = 0
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if reader.fieldnames != names:
                raise ValueError(f"{table_name}: CSV header/order does not match {schema_name}")
            for row in reader:
                count += 1
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"{table_name}: malformed record {count}")
                nct_id = row["nct_id"].strip()
                if not nct_id:
                    raise ValueError(f"{table_name}: missing trial ID at record {count}")
                ids[nct_id] += 1
                if table_name == "breast_studies":
                    if row["study_type"] != "INTERVENTIONAL":
                        raise ValueError(f"{table_name}: unexpected study type for {nct_id}")
                elif nct_id not in study_ids:
                    raise ValueError(f"{table_name}: orphan trial {nct_id}")
                if table_name == "breast_locations":
                    if not row["id"] or row["id"] in facility_ids:
                        raise ValueError("breast_locations: missing or duplicate facility ID")
                    facility_ids.add(row["id"])
                if table_name == "breast_sponsors":
                    role = row["lead_or_collaborator"]
                    if role not in {"lead", "collaborator"}:
                        raise ValueError(f"{table_name}: invalid sponsor role for {nct_id}")
                    if role == "lead":
                        leads[nct_id] += 1
        if count != summary[count_key]:
            raise ValueError(f"{table_name}: {count} rows, summary expects {summary[count_key]}")
        if table_name == "breast_studies":
            if any(value != 1 for value in ids.values()):
                raise ValueError("breast_studies: duplicate trial IDs")
            study_ids = set(ids)
        elif table_name == "breast_sponsors":
            if any(leads[nct_id] != 1 for nct_id in study_ids):
                raise ValueError("breast_sponsors: expected exactly one lead sponsor per trial")
        prepared.append({
            "table": table_name,
            "path": str(path.resolve()),
            "rows": count,
            "distinct_trials": len(ids),
            "bytes": path.stat().st_size,
            "sha256": file_hash(path),
            "schema": schema,
        })
        print(f"CHECK {table_name}: {count:,} rows; {len(ids):,} trials", flush=True)
    return prepared


def load_tables(client, prepared, project, dataset, location, report):
    from google.cloud import bigquery

    remote_dataset = client.get_dataset(f"{project}.{dataset}", timeout=60)
    if remote_dataset.location.upper() != location.upper():
        raise ValueError(f"Dataset location is {remote_dataset.location}, not {location}")
    for item, result in zip(prepared, report["tables"]):
        if file_hash(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"{item['table']}: source file changed after preflight")
        table_id = f"{project}.{dataset}.{item['table']}"
        config = bigquery.LoadJobConfig(
            schema=[bigquery.SchemaField.from_api_repr(field) for field in item["schema"]],
            source_format=bigquery.SourceFormat.CSV,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            skip_leading_rows=1,
            field_delimiter=",",
            encoding="UTF-8",
            allow_quoted_newlines=True,
            allow_jagged_rows=False,
            ignore_unknown_values=False,
            max_bad_records=0,
            autodetect=False,
        )
        result["status"] = "loading"
        print(f"LOAD {table_id} (replace existing rows)...", flush=True)
        with Path(item["path"]).open("rb") as source:
            job = client.load_table_from_file(
                source, table_id, job_config=config, location=location,
                job_id=f"clinical_load_{report['run_id']}_{item['table']}", timeout=120,
            )
        result["job_id"] = job.job_id
        job.result(timeout=600)
        table = client.get_table(table_id, timeout=60)
        result["loaded_rows"] = table.num_rows
        if table.num_rows != item["rows"]:
            raise ValueError(f"{table_id}: loaded {table.num_rows}, expected {item['rows']} rows")
        result["status"] = "passed"
        print(f"PASS {item['table']}: {table.num_rows:,} loaded rows", flush=True)


def save_report(path, report):
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument("--dataset", default="clinical_raw")
    parser.add_argument("--location", default="EU")
    parser.add_argument("--snapshot-date", required=True, type=date.fromisoformat)
    parser.add_argument("--cohort-dir", type=Path, default=COHORT)
    parser.add_argument("--dry-run", action="store_true", help="Local validation only; no Google login or cloud writes")
    parser.add_argument("--include-locations", action="store_true", help="Also validate and replace breast_locations")
    args = parser.parse_args()
    run_id = uuid4().hex
    report_dir = ROOT / "data" / "processed" / "load_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}.json"
    report = {
        "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": args.snapshot_date.isoformat(),
        "project": args.project, "dataset": args.dataset, "location": args.location,
        "mode": "local_validation" if args.dry_run else "WRITE_TRUNCATE",
        "status": "started", "tables": [],
    }
    try:
        prepared = preflight(args.cohort_dir, ROOT / "config", args.include_locations)
        report["tables"] = [
            {key: value for key, value in item.items() if key != "schema"} | {"status": "validated"}
            for item in prepared
        ]
        save_report(report_path, report)
        if args.dry_run:
            report["status"] = "validated_only"
            print("PASS: all local checks. No cloud connection or writes.")
        else:
            from google.cloud import bigquery

            with bigquery.Client(project=args.project, location=args.location) as client:
                load_tables(client, prepared, args.project, args.dataset, args.location, report)
            report["status"] = "passed"
            print(f"Done: all {len(prepared)} raw tables replaced and row counts verified.")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        print(f"FAILED: {report['error']}", file=sys.stderr)
        print("No three-table transaction: if loading started, rerun all tables successfully before dbt.", file=sys.stderr)
        return 1
    finally:
        save_report(report_path, report)
        print(f"Report: {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
