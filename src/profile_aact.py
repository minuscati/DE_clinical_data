"""Inspect AACT table sizes, keys, categories, and relationships."""

import csv
import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "aact_snapshot"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "raw_profile.json"
# Some trial descriptions exceed the csv module's default field-size limit.
csv.field_size_limit(16 * 1024 * 1024)


def profile_table(filename, category_fields, study_ids=None):
    path = INPUT_DIR / filename
    nct_counts = Counter()
    categories = {field: Counter() for field in category_fields}
    row_count = missing_nct = malformed_rows = orphan_rows = 0
    orphan_examples = set()

    print(f"Reading {filename}...", flush=True)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        columns = reader.fieldnames or []
        required = {"nct_id", *category_fields}
        if not required.issubset(columns):
            raise ValueError(f"Missing columns in {filename}: {required - set(columns)}")

        for row in reader:
            row_count += 1
            if None in row or any(value is None for value in row.values()):
                malformed_rows += 1
                continue

            nct_id = row["nct_id"].strip()
            if not nct_id:
                missing_nct += 1
            else:
                nct_counts[nct_id] += 1
                if study_ids is not None and nct_id not in study_ids:
                    orphan_rows += 1
                    if len(orphan_examples) < 5:
                        orphan_examples.add(nct_id)

            for field in category_fields:
                categories[field][row[field].strip() or "(missing)"] += 1

    report = {
        "file": filename,
        "columns": columns,
        "row_count": row_count,
        "distinct_nct_ids": len(nct_counts),
        "missing_nct_id_rows": missing_nct,
        "malformed_rows": malformed_rows,
        "nct_ids_with_multiple_rows": sum(count > 1 for count in nct_counts.values()),
        "extra_rows_beyond_one_per_nct": sum(count - 1 for count in nct_counts.values()),
        "category_counts": {field: dict(counts.most_common()) for field, counts in categories.items()},
    }
    if study_ids is not None:
        report["orphan_rows"] = orphan_rows
        report["orphan_nct_id_examples"] = sorted(orphan_examples)
        report["studies_without_related_rows"] = len(study_ids - nct_counts.keys())

    print(f"  Rows: {row_count:,}; distinct nct_id: {len(nct_counts):,}")
    print(f"  Missing nct_id: {missing_nct:,}; malformed rows: {malformed_rows:,}")
    print(f"  nct_id with multiple rows: {report['nct_ids_with_multiple_rows']:,}")
    if study_ids is not None:
        print(f"  Orphan rows: {orphan_rows:,}")
        print(f"  Studies without related rows: {report['studies_without_related_rows']:,}")
    for field, counts in categories.items():
        print(f"  {field} (top 8): {counts.most_common(8)}")
    print(flush=True)
    return report, set(nct_counts)


def main():
    studies_report, study_ids = profile_table("studies.txt", ("study_type", "overall_status", "phase"))
    sponsors_report, _ = profile_table("sponsors.txt", ("agency_class", "lead_or_collaborator"), study_ids)
    conditions_report, _ = profile_table("browse_conditions.txt", ("mesh_type",), study_ids)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps({"tables": [studies_report, sponsors_report, conditions_report]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Report saved to: {REPORT_PATH}")
    print("Done. This script only inspected the data; it did not clean or filter it.")


if __name__ == "__main__":
    main()
