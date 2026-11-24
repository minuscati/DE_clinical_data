-- =====================================================================
-- Results-reporting analysis — Step 2: export for R
-- Run in the BigQuery console, then: Save results -> CSV (local file).
-- Save it as data/results_reporting.csv in the repository root (data/ is
-- git-ignored); 03_compliance_analysis.qmd reads it from there. All 11,211
-- trials are exported, not only the in-scope ones, because the cohort funnel
-- needs the excluded trials too.
-- =====================================================================
select
  nct_id,
  lead_sponsor_class,
  phase,
  overall_status,
  in_scope,
  r6_has_us_site,
  exclusion_reason,
  reporting_status,
  primary_completion_date,
  results_first_submitted_date,
  effective_due_date,
  extension_requested,
  submitted_before_completion
from `clinical-trials-learning.clinical_analytics.fct_results_reporting`
order by nct_id;
