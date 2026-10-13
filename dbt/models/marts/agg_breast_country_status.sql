{{ config(materialized='table', tags=['locations']) }}

-- Deduplicate sites before joining: one trial can have many sites in a country.
with trial_countries as (
    select distinct nct_id, coalesce(country, 'MISSING') as country
    from {{ ref('stg_breast_locations') }}
)
select
    tc.country,
    coalesce(t.phase, 'MISSING') as phase,
    coalesce(t.overall_status, 'MISSING') as overall_status,
    coalesce(t.lead_sponsor_class, 'MISSING') as sponsor_class,
    count(*) as trial_count
from trial_countries as tc
join {{ ref('fct_breast_trials') }} as t using (nct_id)
group by 1, 2, 3, 4
