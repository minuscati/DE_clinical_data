{{ config(materialized='table', tags=['api_updates']) }}

select
    last_update_posted_date as activity_date,
    count(distinct nct_id) as updated_trials,
    count(*) as captured_payload_versions
from {{ ref('stg_api_trial_observations') }}
group by 1
