"""Run the snapshot batch sequentially, with logs and failure propagation."""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(timezone.utc).isoformat()


def execute_step(command, log_path):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUNBUFFERED"] = "1"
    environment["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    with log_path.open("w", encoding="utf-8") as log:
        with subprocess.Popen(
            command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        ) as process:
            try:
                for line in process.stdout:
                    print(line, end="", flush=True)
                    log.write(line)
                    log.flush()
                return process.wait()
            except KeyboardInterrupt:
                process.terminate()
                process.wait()
                raise


def run_steps(steps, run_dir, metadata):
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / "report.json"
    report = {**metadata, "started_at": now(), "status": "running", "steps": []}

    def save():
        temporary = report_path.with_suffix(".json.part")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temporary.replace(report_path)

    save()
    try:
        for index, (name, command) in enumerate(steps, start=1):
            log_path = run_dir / f"{index:02d}_{name}.log"
            result = {"name": name, "command": command, "log": str(log_path),
                      "started_at": now(), "status": "running"}
            report["steps"].append(result)
            save()
            print(f"\n[{index}/{len(steps)}] {name}", flush=True)
            code = execute_step(command, log_path)
            result.update(exit_code=code, finished_at=now(), status="passed" if code == 0 else "failed")
            save()
            if code != 0:
                raise RuntimeError(f"{name} exited with code {code}; later steps were not started")
        report["status"] = "passed"
        return 0
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        if report["steps"] and report["steps"][-1]["status"] == "running":
            report["steps"][-1]["status"] = "interrupted"
        print("Batch interrupted; check cloud job status before rerunning.", file=sys.stderr)
        return 130
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        if report["steps"] and report["steps"][-1]["status"] == "running":
            report["steps"][-1]["status"] = "failed"
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        report["finished_at"] = now()
        save()
        print(f"Batch report: {report_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, required=True)
    parser.add_argument("--zip", type=Path, help="Optionally extract a downloaded snapshot first")
    parser.add_argument("--with-locations", action="store_true", help="Also build/load facilities; requires --zip")
    parser.add_argument("--validate-only", action="store_true",
                        help="Prepare/validate local data; no BigQuery loads or dbt build")
    args = parser.parse_args()
    try:
        if args.with_locations and not args.zip:
            raise ValueError("--with-locations requires --zip from the same snapshot")
        raw_dir = ROOT / "data" / "raw" / "aact_snapshot"
        if args.zip:
            args.zip = args.zip.resolve()
            if not args.zip.is_file():
                raise FileNotFoundError(args.zip)
        else:
            for filename in ("studies.txt", "sponsors.txt", "browse_conditions.txt"):
                if not (raw_dir / filename).is_file():
                    raise FileNotFoundError(f"Missing {filename}; supply --zip to extract first")
        dbt_executable = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
        if not args.validate_only:
            import yaml

            if not dbt_executable.is_file():
                raise FileNotFoundError("dbt not installed in this Python environment")
            profile = yaml.safe_load((ROOT / "config" / "profiles.yml").read_text(encoding="utf-8"))["clinical_trials"]
            output = profile["outputs"][profile["target"]]
            sources = yaml.safe_load((ROOT / "dbt" / "models" / "sources.yml").read_text(encoding="utf-8"))["sources"]
            raw_source = next(source for source in sources if source["name"] == "clinical_raw")
            if output["project"] != args.project or raw_source["database"] != args.project:
                raise ValueError("--project must match config/profiles.yml and dbt/models/sources.yml")
            if output.get("location", "").upper() != "EU" or raw_source["schema"] != "clinical_raw":
                raise ValueError("This batch expects the existing EU datasets and clinical_raw source")
    except Exception as error:
        print(f"Precheck failed: {error}", file=sys.stderr)
        return 1

    def python_step(script, *arguments):
        return [sys.executable, str(ROOT / "src" / script), *arguments]

    steps = []
    if args.zip:
        steps.append(("extract", python_step("extract_aact.py", "--zip", str(args.zip))))
    steps.extend([
        ("profile", python_step("profile_aact.py")),
        ("cohort", python_step("build_breast_cohort.py")),
    ])
    if args.with_locations:
        steps.append(("locations", python_step("build_breast_locations.py", "--zip", str(args.zip))))
    steps.append(("load", python_step("load_bigquery.py", "--project", args.project,
                             "--snapshot-date", args.snapshot_date.isoformat(),
                             *(["--dry-run"] if args.validate_only else []),
                             *(["--include-locations"] if args.with_locations else []))))
    if not args.validate_only:
        steps.append(("dbt_build", [str(dbt_executable), "build", "--project-dir", str(ROOT / "dbt"),
                                    "--profiles-dir", str(ROOT / "config"),
                                    *([] if args.with_locations else ["--exclude", "tag:locations"])]))
    run_dir = ROOT / "logs" / "batch" / uuid4().hex
    code = run_steps(steps, run_dir, {
        "project": args.project, "snapshot_date": args.snapshot_date.isoformat(),
        "mode": "local_validation" if args.validate_only else "full_batch",
    })
    if code == 0:
        print("PASS: local preparation and validation." if args.validate_only
              else "PASS: batch complete, including BigQuery loading and dbt tests. Refresh Power BI next.")
    return code


if __name__ == "__main__":
    sys.exit(main())
