-- One row per sponsor relationship, not one row per trial.
select
    nullif(trim(id), '') as sponsor_id,
    nullif(trim(nct_id), '') as nct_id,
    nullif(trim(name), '') as sponsor_name,
    nullif(upper(trim(agency_class)), '') as agency_class,
    nullif(lower(trim(lead_or_collaborator)), '') as sponsor_role
from {{ source('clinical_raw', 'breast_sponsors') }}
