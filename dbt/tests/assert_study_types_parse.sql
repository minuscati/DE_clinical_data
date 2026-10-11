-- A dbt SQL data test returns problematic rows; zero rows means PASS.
select nct_id, start_date_raw, completion_date_raw, enrollment_raw
from {{ ref('stg_breast_studies') }}
where
    (nullif(trim(start_date_raw), '') is not null and start_date is null)
    or (nullif(trim(completion_date_raw), '') is not null and completion_date is null)
    or (nullif(trim(enrollment_raw), '') is not null and enrollment is null)
