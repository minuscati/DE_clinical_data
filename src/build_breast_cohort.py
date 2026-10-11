"""Build an interventional cohort using the Breast Neoplasms MeSH label."""

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "aact_snapshot"
OUT = ROOT / "data" / "processed" / "breast_cohort"
TERM = "Breast Neoplasms"
MESH_TYPES = {"mesh-list", "mesh-ancestor"}
csv.field_size_limit(16 * 1024 * 1024)


def rows(filename):
    with (RAW / filename).open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle, delimiter="|")


def export(filename, destination, predicate):
    counts = Counter()
    with (RAW / filename).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="|")
        with (OUT / destination).open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                if predicate(row):
                    writer.writerow(row)
                    counts[row["nct_id"]] += 1
    print(f"{destination}: {sum(counts.values()):,} rows; {len(counts):,} trials", flush=True)
    return counts


def main():
    print(f"Finding exact MeSH label: {TERM}...", flush=True)
    matched_ids = {
        row["nct_id"] for row in rows("browse_conditions.txt")
        if row["mesh_term"].strip() == TERM and row["mesh_type"] in MESH_TYPES
    }
    print(f"Matching trials before study-type filter: {len(matched_ids):,}", flush=True)
    selected_ids = {
        row["nct_id"] for row in rows("studies.txt")
        if row["nct_id"] in matched_ids and row["study_type"] == "INTERVENTIONAL"
    }
    if not selected_ids:
        raise ValueError("Empty cohort; check the source fields and labels.")

    # Verify the lead-sponsor relationship before creating outputs.
    leads = Counter(
        row["nct_id"] for row in rows("sponsors.txt")
        if row["nct_id"] in selected_ids and row["lead_or_collaborator"] == "lead"
    )
    invalid_leads = [nct_id for nct_id in selected_ids if leads[nct_id] != 1]
    if invalid_leads:
        raise ValueError(f"Expected one lead per trial. Examples: {invalid_leads[:5]}")

    OUT.mkdir(parents=True, exist_ok=True)
    keep = lambda row: row["nct_id"] in selected_ids
    studies = export("studies.txt", "breast_studies.csv", keep)
    if any(count != 1 for count in studies.values()) or set(studies) != selected_ids:
        raise ValueError("Trial-table uniqueness or cohort coverage check failed.")
    sponsors = export("sponsors.txt", "breast_sponsors.csv", keep)
    conditions = export("browse_conditions.txt", "breast_conditions.csv", keep)

    summary = {
        "definition_version": "v1",
        "exact_mesh_term": TERM,
        "mesh_types_used_for_selection": sorted(MESH_TYPES),
        "study_type": "INTERVENTIONAL",
        "matched_trials_before_study_type_filter": len(matched_ids),
        "selected_trials": len(selected_ids),
        "sponsor_rows": sum(sponsors.values()),
        "condition_rows": sum(conditions.values()),
        "all_selected_trials_have_exactly_one_lead": True,
        "notes": [
            "Operational label-based cohort, not a clinically adjudicated breast-cancer cohort.",
            "No restriction on status, phase, sex, dates, or intervention purpose.",
            "Child exports retain all sponsors and all condition tags of selected trials.",
            "Selection includes ancestor tags to retain trials assigned narrower disease labels.",
        ],
    }
    (OUT / "cohort_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("PASS: unique trial IDs; exactly one lead sponsor per selected trial.", flush=True)
    print(f"Done. Cohort saved to: {OUT}", flush=True)


if __name__ == "__main__":
    main()
