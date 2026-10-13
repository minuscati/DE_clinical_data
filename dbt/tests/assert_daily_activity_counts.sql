{{ config(tags=['api_updates']) }}

-- Every counted trial must have at least one captured payload version.
select activity_date
from {{ ref('agg_daily_trial_activity') }}
where updated_trials <= 0
   or captured_payload_versions < updated_trials
