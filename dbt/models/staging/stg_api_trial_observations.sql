{{ config(tags=['api_updates']) }}

select observation_id, nct_id, last_update_posted_date, overall_status,
       observed_at, last_seen_at, source_run_id, payload_sha256, raw_json
from {{ source('clinical_raw', 'api_trial_observations') }}
