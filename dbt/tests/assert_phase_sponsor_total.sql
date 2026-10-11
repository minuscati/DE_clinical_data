with expected as (
    select count(*) as trial_count from {{ ref('fct_breast_trials') }}
), actual as (
    select coalesce(sum(trial_count), 0) as trial_count
    from {{ ref('agg_breast_phase_sponsor') }}
)
select expected.trial_count as expected_trials, actual.trial_count as actual_trials
from expected cross join actual
where expected.trial_count != actual.trial_count
