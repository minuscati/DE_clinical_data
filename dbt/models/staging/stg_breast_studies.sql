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
    safe_cast(nullif(trim(last_update_posted_date), '') as date) as last_update_posted_date,

    -- Results-reporting fields. Raw values are kept so parse failures stay testable.
    primary_completion_date as primary_completion_date_raw,
    safe_cast(nullif(trim(primary_completion_date), '') as date) as primary_completion_date,
    nullif(upper(trim(primary_completion_date_type)), '') as primary_completion_date_type,
    results_first_submitted_date as results_first_submitted_date_raw,
    safe_cast(nullif(trim(results_first_submitted_date), '') as date) as results_first_submitted_date,
    results_first_posted_date as results_first_posted_date_raw,
    safe_cast(nullif(trim(results_first_posted_date), '') as date) as results_first_posted_date,
    disposition_first_submitted_date as disposition_first_submitted_date_raw,
    safe_cast(nullif(trim(disposition_first_submitted_date), '') as date) as disposition_first_submitted_date,

    -- FDA flags: 't' -> true, 'f' -> false, empty -> NULL ("not reported").
    -- NULL must stay distinct from false: empty flags are common before ~2020.
    is_fda_regulated_drug as is_fda_regulated_drug_raw,
    case lower(trim(is_fda_regulated_drug)) when 't' then true when 'f' then false end as is_fda_regulated_drug,
    is_fda_regulated_device as is_fda_regulated_device_raw,
    case lower(trim(is_fda_regulated_device)) when 't' then true when 'f' then false end as is_fda_regulated_device,

    nullif(trim(why_stopped), '') as why_stopped
from {{ source('clinical_raw', 'breast_studies') }}
