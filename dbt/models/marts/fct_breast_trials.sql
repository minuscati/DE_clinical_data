{{ config(materialized='table') }}

-- Grain: one row per trial. Collaborators remain in the sponsor staging model.
with studies as (
    select * from {{ ref('stg_breast_studies') }}
), lead_sponsors as (
    select nct_id, sponsor_id, sponsor_name, agency_class
    from {{ ref('stg_breast_sponsors') }}
    where sponsor_role = 'lead'
)
select
    studies.nct_id,
    studies.trial_title,
    studies.study_type,
    studies.overall_status,
    studies.phase,
    studies.start_date,
    studies.start_date_type,
    extract(year from studies.start_date) as start_year,
    studies.completion_date,
    studies.completion_date_type,
    studies.enrollment,
    studies.enrollment_type,
    studies.last_update_posted_date,
    lead_sponsors.sponsor_id as lead_sponsor_id,
    lead_sponsors.sponsor_name as lead_sponsor_name,
    lead_sponsors.agency_class as lead_sponsor_class
from studies
left join lead_sponsors
    on studies.nct_id = lead_sponsors.nct_id
