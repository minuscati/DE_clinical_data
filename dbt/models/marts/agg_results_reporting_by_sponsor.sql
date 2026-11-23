{{ config(materialized='table') }}

select
    lead_sponsor_class,
    count(*) as total_trials,
    countif(reporting_status = 'ON_TIME') as on_time_trials,
    countif(reporting_status = 'LATE') as late_trials,
    countif(reporting_status = 'EXTENSION_REQUESTED') as extension_requested_trials,
    countif(reporting_status = 'OVERDUE_NOT_REPORTED') as overdue_not_reported_trials,
    safe_divide(countif(reporting_status = 'ON_TIME'),
            countif(reporting_status != 'EXTENSION_REQUESTED')) as on_time_rate
from {{ ref('fct_results_reporting')}}
where in_scope
group by lead_sponsor_class