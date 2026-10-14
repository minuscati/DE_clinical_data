# Excluding registry refresh markers from content identity

An observed trial had two JSON payloads differing only at
`derivedSection.miscInfoModule.versionHolder` (2026-10-13 versus 2026-10-14).
Whole-payload hashes treated this as a second version even though study content
was unchanged. This finding alone does not establish that every duplicate has
the same cause.

The loader now excludes exactly this path from its canonical content hash.
It does not modify input payloads, remove other derived fields, reorder arrays,
or equate genuine status/content changes. A new physical table,
`clinical_raw.api_trial_content_observations`, separates the v2 identity scheme
from the legacy full-payload scheme. Both tables use the same nine-column schema.
`payload_sha256` in the new table is a normalized-content hash. `raw_json`
contains the complete earliest representative payload, including versionHolder.
All capture files and the legacy table remain available for audit.

## Upgrade in the Ubuntu VM

Pause the daily trigger (`disabled: true`) and wait for active executions to
finish. Do not run loaders from another environment concurrently.

```bash
cd ~/projects/DE_clinical_data
git pull --ff-only
sudo docker build -t clinical-batch:v1 .
```

Optional read-only migration preview (requires Google credentials):

```bash
sudo docker run --rm --mount type=bind,source="$(pwd)/data",target=/app/data --mount type=bind,source="$HOME/.config/gcloud/application_default_credentials.json",target=/root/.config/gcloud/application_default_credentials.json,readonly clinical-batch:v1 src/load_api_observations.py --project clinical-trials-learning --import-legacy --dry-run
```

Import all old observations into the new content table:

```bash
sudo docker run --rm --mount type=bind,source="$(pwd)/data",target=/app/data --mount type=bind,source="$HOME/.config/gcloud/application_default_credentials.json",target=/root/.config/gcloud/application_default_credentials.json,readonly clinical-batch:v1 src/load_api_observations.py --project clinical-trials-learning --import-legacy
```

The command prints the legacy row count and the normalized count. It preserves
the earliest `observed_at` and representative raw JSON/source run and the latest
`last_seen_at` for each content key. It leaves the legacy table untouched.
Repeat imports match the same new keys; migration uses the existing sequential
MERGE and presence/uniqueness checks. The importer is an in-memory operation
suited to this small project dataset, not a large historical warehouse.

Only after successful import, rebuild the API models:

```bash
sudo docker run --rm --mount type=bind,source="$(pwd)/config/profiles.yml",target=/app/config/profiles.yml,readonly --mount type=bind,source="$HOME/.config/gcloud/application_default_credentials.json",target=/root/.config/gcloud/application_default_credentials.json,readonly --mount type=bind,source="$(pwd)/logs/dbt",target=/app/dbt/logs --mount type=bind,source="$(pwd)/data/dbt_target",target=/app/dbt/target --entrypoint dbt clinical-batch:v1 build --project-dir /app/dbt --profiles-dir /app/config --select +mart_trial_status_comparison +agg_daily_trial_activity
```

Alternatively execute the existing Kestra daily flow manually after import;
its final task builds these same models. No Kestra restart is needed to use a
rebuilt `clinical-batch:v1` image with pullPolicy NEVER, provided no tasks were
running during replacement. Validate success before enabling the daily trigger.
Refresh Power BI Import afterwards; report table/column names are unchanged.

## Verify in BigQuery

```sql
SELECT observation_id, COUNT(*) AS row_count
FROM `clinical-trials-learning.clinical_raw.api_trial_content_observations`
GROUP BY observation_id
HAVING COUNT(*) > 1;
```

Expected: zero rows. Check the rebuilt activity table:

```sql
SELECT activity_date, updated_trials, captured_payload_versions
FROM `clinical-trials-learning.clinical_analytics.agg_daily_trial_activity`
ORDER BY activity_date;
```

Distinct trial counts should be preserved during migration. Content-version
counts may decrease; they need not equal trial counts if genuine field changes
were captured on the same posting date. Neither metric is a count of clinical
status transitions.

Python regression tests cover marker-only changes, preservation of full raw
JSON, other derived fields, status/date/array changes, legacy integrity failures,
timestamp bounds, deterministic grouping, and repeatable normalization. Actual
BigQuery merge and dbt execution must be verified in the VM.
