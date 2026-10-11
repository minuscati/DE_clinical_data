"""Extract the three AACT tables needed for our first batch pipeline."""

import argparse
import csv
import shutil
import zipfile
from pathlib import Path


# Resolve paths from this script, so the working directory does not matter.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = PROJECT_ROOT / "data" / "raw" / "m7ahzbr4vk8tihch7slbtefvaap4.zip"
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "aact_snapshot"
TABLES = ("studies.txt", "sponsors.txt", "browse_conditions.txt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=ZIP_PATH, help="Path to the downloaded AACT flat-file ZIP")
    zip_path = parser.parse_args().zip
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()
        selected = {}
        # Match filenames even if the archive includes a parent directory.
        for table in TABLES:
            matches = [item for item in members if Path(item.filename).name == table]
            if len(matches) != 1:
                raise ValueError(f"Expected one {table}; found {len(matches)}")
            selected[table] = matches[0]

        print(f"ZIP: {zip_path.name}", flush=True)
        print(f"Archive entries: {len(members)}", flush=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        for table, member in selected.items():
            destination = OUTPUT_DIR / table
            # Write to a temporary file; replace only after extraction succeeds.
            temporary = destination.with_suffix(".txt.part")
            print(f"Extracting {table} ({member.file_size / 1_000_000:.1f} MB)...", flush=True)
            with archive.open(member) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            temporary.replace(destination)

            # Read just the header and first record, not the entire table.
            with destination.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="|")
                columns = reader.fieldnames or []
                if "nct_id" not in columns:
                    raise ValueError(f"Missing nct_id in {table}")
                first_record = next(reader, None)
                if first_record is None:
                    raise ValueError(f"No data records in {table}")
                print(f"  Columns: {len(columns)}; first five: {', '.join(columns[:5])}")
                print(f"  First nct_id: {first_record['nct_id']}", flush=True)

    print(f"Done. Files saved to: {OUTPUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
