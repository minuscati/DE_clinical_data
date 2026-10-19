# Checkpoint history

## 2026-10-19 — Implementation review and current report synchronization

- Compared the GitHub README with local scripts, dbt SQL, Kestra definitions,
  historical batch/load reports and the saved Power BI artifact.
- Added an implementation-status overview covering snapshot preparation,
  validated BigQuery loading, nine dbt models, API capture/content deduplication,
  Docker/Kestra workflows and three Power BI pages.
- Synchronized the current local `.pbix` save. Archive integrity passed and its
  three page definitions are unchanged from the previous committed report;
  the embedded DataModel and save metadata changed. Power BI Desktop rendering
  and the contents/freshness of the embedded data were not verified in this review.
- Reran all **25 Python tests** successfully and parsed dbt successfully;
  the manifest contains **9 models and 42 data tests**. Local test execution
  used a workspace temporary directory to accommodate sandbox permissions.
- Corrected the location batch instructions: the snapshot runner excludes
  API-tagged dbt models/tests.
- Kept unattended scheduling, post-migration cloud-build evidence and final
  report screenshots pending. No new VM/cloud execution, baseline snapshot,
  automatic Power BI refresh or additional pipeline feature is claimed.

## 2026-10-14 — Ubuntu runtime and three-page report

- Final Power BI artifact includes Phase & Sponsor, Country & Recruitment,
  and Daily Updates pages. The report archive passed a ZIP integrity check;
  its three page names were verified from report definitions.
- Docker and BigQuery/dbt connectivity verified in an Ubuntu VMware VM.
  The manually executed API flow completed capture, merge, and dbt in about
  44.5 seconds according to supplied VM logs.
- Fixed false content-version growth caused by
  `derivedSection.miscInfoModule.versionHolder`. Only that refresh marker is
  excluded from content identity; genuine changes and complete raw captures
  remain traceable.
- Added a non-destructive importer and a separate physical content-observation
  table. The reported migration verified **98 legacy rows → 57 content rows**.
- Updated dbt source mapping without changing downstream Power BI table names.
- Validation after the fix: **25 Python tests passed**, dbt parse passed;
  current manifest contains **9 models and 42 tests**. The cloud rebuild after
  migration must be checked independently from local parsing.
- Added Ubuntu startup, shutdown, manual date-window, upgrade and scheduling
  documentation. Existing README images are explicitly labeled older previews.

Remaining evidence: an unattended trigger-origin execution, final full-page
screenshots and post-migration cloud-build verification. Scheduling is configured,
not an always-on deployment. Power BI refresh is manual; geography remains the
2026-10-11 baseline; cohort discovery, full source history, Terraform and
Kafka/Flink are outside this checkpoint.
