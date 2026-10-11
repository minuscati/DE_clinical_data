{{ config(materialized='table') }}

-- Grain: one row per (phase, lead sponsor class).
-- Count trials, not sponsor relationships or disease tags.
select
    coalesce(phase, 'MISSING') as phase,
    coalesce(lead_sponsor_class, 'MISSING') as sponsor_class,
    count(*) as trial_count
from {{ ref('fct_breast_trials') }}
group by 1, 2
