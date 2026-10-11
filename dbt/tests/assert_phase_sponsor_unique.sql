select phase, sponsor_class, count(*) as row_count
from {{ ref('agg_breast_phase_sponsor') }}
group by phase, sponsor_class
having count(*) > 1
