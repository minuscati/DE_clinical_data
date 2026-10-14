# Ubuntu VM operation

The active runtime is an Ubuntu 24.04 VMware VM, with the project at
`/home/janice/projects/DE_clinical_data` and Google ADC at
`/home/janice/.config/gcloud/application_default_credentials.json`.
These are deployment-specific paths; use your own username/paths when reproducing.
BigQuery remains in Google Cloud; Power BI Desktop runs on Windows.

## Initial preparation

Docker Engine and Git must be installed in Ubuntu. The demonstrated VM uses
2 CPU cores and 8 GB RAM. It was first configured with less RAM for basic checks;
the host must retain sufficient memory for Windows. Close unused VMs, and adjust
memory only after shutting Ubuntu down normally. 3D acceleration was disabled
while troubleshooting a host freeze; its cause was not established.

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/minuscati/DE_clinical_data.git
cd DE_clinical_data
sudo docker build -t clinical-batch:v1 .
mkdir -p data/processed/breast_cohort logs/dbt data/dbt_target
```

Copy the four prepared cohort CSVs and the two summary JSON files into
`data/processed/breast_cohort/`. They are excluded from Git; cloning alone
does not provide the data. Copy via a VMware shared folder or rebuild using
the snapshot instructions in the README. Full snapshot regeneration also
requires the original AACT ZIP.

Create the ignored dbt configuration:

```bash
cp config/profiles.example.yml config/profiles.yml
sed -i 's/YOUR_GCP_PROJECT_ID/clinical-trials-learning/' config/profiles.yml
mkdir -p ~/.config/gcloud
```

The demonstrated datasets are `clinical_raw` and `clinical_analytics`, both in
EU. Reproducing in another project also requires updating `dbt/models/sources.yml`.

Authenticate using the official gcloud container. Complete browser authorization
and paste the authorization code only into your own terminal:

```bash
sudo docker run --rm -it --mount type=bind,source="$HOME/.config/gcloud",target=/root/.config/gcloud --entrypoint gcloud gcr.io/google.com/cloudsdktool/google-cloud-cli:stable auth application-default login --no-launch-browser --project clinical-trials-learning
sudo docker run --rm --mount type=bind,source="$HOME/.config/gcloud",target=/root/.config/gcloud --entrypoint gcloud gcr.io/google.com/cloudsdktool/google-cloud-cli:stable auth application-default set-quota-project clinical-trials-learning
```

Credentials stay outside Git and images and are mounted read-only into tasks.
Verify configuration/connectivity without rebuilding models:

```bash
sudo docker run --rm --mount type=bind,source="$HOME/.config/gcloud/application_default_credentials.json",target=/root/.config/gcloud/application_default_credentials.json,readonly --mount type=bind,source="$(pwd)/config/profiles.yml",target=/app/config/profiles.yml,readonly --entrypoint dbt clinical-batch:v1 debug --project-dir /app/dbt --profiles-dir /app/config
```

Expected: `All checks passed!`. Git is installed inside the batch image because
dbt debug checks for it; installing Git only on Ubuntu is insufficient.

## Start Kestra

At the repository root:

```bash
sudo docker run -d --name clinical-kestra --restart unless-stopped --user root -p 127.0.0.1:8080:8080 -v clinical_kestra_storage:/app/storage -v clinical_kestra_db:/app/data -v /var/run/docker.sock:/var/run/docker.sock -v /tmp:/tmp --mount type=bind,source="$(pwd)/orchestration/kestra-config.yml",target=/etc/kestra/clinical.yml,readonly kestra/kestra:latest-slim server local --config /etc/kestra/clinical.yml
```

This is the initial creation command, not a daily startup command. Open
`http://localhost:8080` in **Ubuntu's browser**. Ports are bound to the VM's
loopback interface. The Windows browser's localhost refers to Windows instead.
Docker socket access allows Kestra to create project task containers.
The local server uses named volumes for its database/storage. The image uses a
moving tag in this learning deployment; record/pin tested versions for a later
reproducibility upgrade rather than blindly changing a working server image.

Import `orchestration/flows/clinical_daily_updates.yml` in Kestra. Replace the
two trigger path placeholders and supply the same paths for manual executions:

```text
workspace_dir: /home/janice/projects/DE_clinical_data
credential_file: /home/janice/.config/gcloud/application_default_credentials.json
project: clinical-trials-learning
```

For an existing full-payload observation installation, complete the
[content-table migration](content-deduplication.md) before the updated workflow
rebuilds models. A fresh installation can create the content table with its
first observation load. An existing warehouse does not need its four baseline
tables overwritten merely because the runtime changed.

## Dates and scheduling

The repository template is disabled and schedules 08:00 Europe/Stockholm,
querying the three previous days. Manual Execute inputs are literal dates;
they do not automatically use the trigger date expressions.

An alternative for capturing available same-day records is 17:00 Stockholm
time, querying the previous two days through today. To choose that alternative,
edit the deployed trigger's cron and date inputs:

```yaml
cron: "0 17 * * *"
timezone: Europe/Stockholm
recoverMissedSchedules: NONE
inputs:
  workspace_dir: "/home/janice/projects/DE_clinical_data"
  credential_file: "/home/janice/.config/gcloud/application_default_credentials.json"
  project: clinical-trials-learning
  start_date: "{{ trigger.date | dateAdd(-2, 'DAYS') | date('yyyy-MM-dd', timeZone='Europe/Stockholm') }}"
  end_date: "{{ trigger.date | date('yyyy-MM-dd', timeZone='Europe/Stockholm') }}"
```

This is an optional replacement for the matching fields under `triggers`, not a
second trigger to append. The time is a practical choice, not a source-update
guarantee. Set `disabled: false` after a successful manual run. Inspect the next
evaluation date. Source refresh timestamps can be inspected at
`https://clinicaltrials.gov/api/v2/version`; query results can change after a
registry refresh. The daily model groups by source posting date, not run date.

Windows must remain awake and connected, Ubuntu must be running (not suspended),
and Kestra must be up at the scheduled time. Locking Windows or turning off its
screen is compatible with execution, but sleep/hibernation is not.

## Each morning / after reboot

Start Ubuntu and check:

```bash
sudo docker ps
```

If `clinical-kestra` is absent from the running list:

```bash
sudo systemctl start docker
sudo docker start clinical-kestra
sudo docker logs --tail 50 clinical-kestra
```

Do not recreate the container or delete named volumes as a routine startup step.
With `recoverMissedSchedules: NONE`, a missed run does not automatically backfill.
Use Execute with explicit dates. Current API date filtering cannot reconstruct
superseded historical versions; a wider range only captures matching current
records. Avoid running the old Codespaces pipeline concurrently.

## Verify and display results

Inspect Overview and Logs for all three tasks: `fetch_updates`,
`merge_observations`, `dbt_api_models`. A cached browser Running label is not
conclusive; refresh the page and compare server logs:

```bash
sudo docker logs --tail 80 clinical-kestra
```

The observed VM run completed all three tasks in about 44.5 seconds. Retain a
separate trigger-origin execution as evidence of automatic scheduling.

```sql
SELECT activity_date, updated_trials, captured_payload_versions
FROM `clinical-trials-learning.clinical_analytics.agg_daily_trial_activity`
ORDER BY activity_date DESC;
```

Inspect failures before retrying; a merge can succeed even if dbt then fails.
Successful runs need not add new content. Matching captures can update
`last_seen_at` while leaving content/trial counts unchanged.

Power BI Import needs **Home → Refresh** after dbt finishes. The three-page
report's country map remains a baseline view; refreshing it does not substitute
API statuses or locations. Power BI Service refresh is not deployed here.

## Update code and shut down

Disable the trigger temporarily and wait for active tasks to finish before
replacing the task image:

```bash
cd ~/projects/DE_clinical_data
git pull --ff-only
sudo docker build -t clinical-batch:v1 .
```

Run the workflow manually and restore the trigger after validation. Task scripts
and dbt models are baked into this image; git pull alone does not update them.
UI changes to deployed Kestra YAML do not automatically become repository edits.

For normal overnight shutdown, first shut Ubuntu down:

```bash
sudo poweroff
```

Then shut Windows down. Restart before the next scheduled time, or manually
execute a missed date range. Suspending the VM pauses its scheduler.
