-- Known data anomaly, not a pipeline bug: some registrations record results as
-- submitted BEFORE the primary completion date (23 trials at the 2026-10-11
-- snapshot). severity='warn' reports them without failing the build, so a
-- sudden jump in this count is visible but does not block the pipeline.
{{ config(severity='warn') }}

select nct_id, primary_completion_date, results_first_submitted_date, in_scope
from {{ ref('fct_results_reporting') }}
where submitted_before_completion
