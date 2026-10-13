{{ config(materialized='table', tags=['api_updates']) }}

with latest as (
    select * from {{ ref('stg_api_trial_observations') }}
    qualify row_number() over (
        partition by nct_id
        order by last_update_posted_date desc, last_seen_at desc, observation_id desc
    ) = 1
)
select
    a.nct_id, b.trial_title,
    b.overall_status as baseline_status,
    a.overall_status as api_status,
    b.last_update_posted_date as baseline_last_update_posted_date,
    a.last_update_posted_date as api_last_update_posted_date,
    a.observed_at, a.last_seen_at, a.observation_id,
    a.last_update_posted_date >= b.last_update_posted_date as api_is_at_least_as_recent,
    case when b.overall_status is null or b.last_update_posted_date is null
              or a.last_update_posted_date < b.last_update_posted_date then null
         else a.overall_status != b.overall_status end as status_differs_from_baseline
from latest a
join {{ ref('stg_breast_studies') }} b using (nct_id)
