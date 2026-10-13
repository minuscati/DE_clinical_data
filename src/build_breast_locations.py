"""Extract facilities for the existing cohort directly from the same AACT ZIP."""

import argparse
import csv
import io
import json
import zipfile
from pathlib import Path

from load_bigquery import COHORT, ROOT, file_hash

FIELDS = ["id", "nct_id", "status", "name", "city", "state", "zip", "country", "latitude", "longitude"]
csv.field_size_limit(16 * 1024 * 1024)


def build(zip_path, cohort_dir=COHORT):
    studies_path = cohort_dir / "breast_studies.csv"
    studies_hash = file_hash(studies_path)
    with studies_path.open(encoding="utf-8-sig", newline="") as source:
        study_ids = {row["nct_id"] for row in csv.DictReader(source)}
    if not study_ids:
        raise ValueError("Empty study cohort")
    destination = cohort_dir / "breast_locations.csv"
    temporary = destination.with_suffix(".csv.part")
    seen, covered = set(), set()
    count = missing_country = 0
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = [item for item in archive.infolist() if Path(item.filename).name == "facilities.txt"]
            if len(members) != 1:
                raise ValueError("Expected exactly one facilities.txt in AACT ZIP")
            with archive.open(members[0]) as stream, temporary.open("w", encoding="utf-8", newline="") as target:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"), delimiter="|", strict=True)
                if reader.fieldnames != FIELDS:
                    raise ValueError("Unexpected facilities schema; inspect source before continuing")
                writer = csv.DictWriter(target, fieldnames=FIELDS)
                writer.writeheader()
                for row in reader:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("Malformed facilities record")
                    if row["nct_id"] not in study_ids:
                        continue
                    if not row["id"] or row["id"] in seen:
                        raise ValueError("Missing or duplicate facility ID")
                    writer.writerow(row)
                    seen.add(row["id"])
                    covered.add(row["nct_id"])
                    count += 1
                    missing_country += not row["country"].strip()
        if not count:
            raise ValueError("No facilities matched; check snapshot and cohort")
        if file_hash(studies_path) != studies_hash:
            raise ValueError("Study cohort changed during extraction")
        temporary.replace(destination)
        summary = {
            "zip": str(zip_path.resolve()), "study_csv_sha256": studies_hash,
            "location_csv_sha256": file_hash(destination),
            "location_rows": count, "trials_with_locations": len(covered),
            "trials_without_locations": len(study_ids - covered),
            "rows_without_country": missing_country,
            "note": "One facility record per row; absence of locations is retained as a coverage limitation.",
        }
        (cohort_dir / "locations_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)
        print(f"Done: {destination}", flush=True)
        return summary
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True, help="Use the same snapshot ZIP as the study cohort")
    args = parser.parse_args()
    build(args.zip)


if __name__ == "__main__":
    main()
