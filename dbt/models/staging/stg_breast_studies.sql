-- One row per trial. Keep the raw values alongside parsed dates/numbers.
select
    nullif(trim(nct_id), '') as nct_id,
    nullif(trim(brief_title), '') as trial_title,
    nullif(trim(study_type), '') as study_type,
    nullif(trim(overall_status), '') as overall_status,
    nullif(trim(phase), '') as phase,
    start_date as start_date_raw,
    safe_cast(nullif(trim(start_date), '') as date) as start_date,
    start_date_type,
    completion_date as completion_date_raw,
    safe_cast(nullif(trim(completion_date), '') as date) as completion_date,
    completion_date_type,
    enrollment as enrollment_raw,
    safe_cast(nullif(trim(enrollment), '') as int64) as enrollment,
    nullif(trim(enrollment_type), '') as enrollment_type,
    safe_cast(nullif(trim(last_update_posted_date), '') as date) as last_update_posted_date
from {{ source('clinical_raw', 'breast_studies') }}
