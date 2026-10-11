select studies.nct_id, count(sponsors.sponsor_id) as lead_count
from {{ ref('stg_breast_studies') }} as studies
left join {{ ref('stg_breast_sponsors') }} as sponsors
    on studies.nct_id = sponsors.nct_id
    and sponsors.sponsor_role = 'lead'
group by studies.nct_id
having count(sponsors.sponsor_id) != 1
