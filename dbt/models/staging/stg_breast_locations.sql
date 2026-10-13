{{ config(tags=['locations']) }}

select
    nullif(trim(id), '') as facility_id,
    nullif(trim(nct_id), '') as nct_id,
    nullif(trim(name), '') as facility_name,
    nullif(trim(status), '') as facility_status,
    nullif(trim(city), '') as city,
    nullif(trim(state), '') as state,
    nullif(trim(zip), '') as postal_code,
    nullif(trim(country), '') as country,
    safe_cast(nullif(trim(latitude), '') as float64) as latitude,
    safe_cast(nullif(trim(longitude), '') as float64) as longitude
from {{ source('clinical_raw', 'breast_locations') }}
