-- A dbt SQL data test returns problematic rows; zero rows means PASS.
-- A non-empty raw value whose parsed value is NULL means the conversion failed.
select nct_id, start_date_raw, completion_date_raw, enrollment_raw,
       primary_completion_date_raw, results_first_submitted_date_raw,
       results_first_posted_date_raw, disposition_first_submitted_date_raw,
       is_fda_regulated_drug_raw, is_fda_regulated_device_raw
from {{ ref('stg_breast_studies') }}
where
    (nullif(trim(start_date_raw), '') is not null and start_date is null)
    or (nullif(trim(completion_date_raw), '') is not null and completion_date is null)
    or (nullif(trim(enrollment_raw), '') is not null and enrollment is null)
    or (nullif(trim(primary_completion_date_raw), '') is not null and primary_completion_date is null)
    or (nullif(trim(results_first_submitted_date_raw), '') is not null and results_first_submitted_date is null)
    or (nullif(trim(results_first_posted_date_raw), '') is not null and results_first_posted_date is null)
    or (nullif(trim(disposition_first_submitted_date_raw), '') is not null and disposition_first_submitted_date is null)
    or (nullif(trim(is_fda_regulated_drug_raw), '') is not null and is_fda_regulated_drug is null)
    or (nullif(trim(is_fda_regulated_device_raw), '') is not null and is_fda_regulated_device is null)
