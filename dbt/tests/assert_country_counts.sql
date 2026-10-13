{{ config(tags=['locations']) }}

with expected as (
    select coalesce(country, 'MISSING') as country, count(distinct nct_id) as trials
    from {{ ref('stg_breast_locations') }}
    group by 1
), actual as (
    select country, sum(trial_count) as trials
    from {{ ref('agg_breast_country_status') }}
    group by 1
)
select coalesce(e.country, a.country) as country
from expected e full outer join actual a using (country)
where e.trials is null or a.trials is null or e.trials != a.trials
