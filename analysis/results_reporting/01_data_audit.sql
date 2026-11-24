-- =====================================================================
-- Results-reporting analysis — Step 1: data audit
-- Queries A–F are independent and read-only; run each one separately in the
-- BigQuery console.
--
-- Source: clinical_raw.breast_studies (all columns are STRING in the raw
-- layer, so dates and flags are parsed here exactly as dbt will later).
-- =====================================================================


-- ---------------------------------------------------------------------
-- A. Fill and parse rates of the columns the analysis depends on
--    Checks: how many values are empty, and whether any non-empty value
--    fails to parse as a DATE (parse_failures should be 0).
-- ---------------------------------------------------------------------
with s as (
  select * from `clinical-trials-learning.clinical_raw.breast_studies`
)
select 'primary_completion_date' as column_name,
       countif(nullif(trim(primary_completion_date), '') is not null) as non_empty,
       countif(nullif(trim(primary_completion_date), '') is not null
               and safe_cast(trim(primary_completion_date) as date) is null) as parse_failures,
       count(*) as total_trials
from s
union all
select 'results_first_submitted_date',
       countif(nullif(trim(results_first_submitted_date), '') is not null),
       countif(nullif(trim(results_first_submitted_date), '') is not null
               and safe_cast(trim(results_first_submitted_date) as date) is null),
       count(*)
from s
union all
select 'results_first_posted_date',
       countif(nullif(trim(results_first_posted_date), '') is not null),
       countif(nullif(trim(results_first_posted_date), '') is not null
               and safe_cast(trim(results_first_posted_date) as date) is null),
       count(*)
from s
union all
select 'disposition_first_submitted_date',
       countif(nullif(trim(disposition_first_submitted_date), '') is not null),
       countif(nullif(trim(disposition_first_submitted_date), '') is not null
               and safe_cast(trim(disposition_first_submitted_date) as date) is null),
       count(*)
from s;


-- ---------------------------------------------------------------------
-- B. Distinct values of the categorical columns used as filters
--    Checks: the exact spelling of true/false in the FDA flags
--    (e.g. 't' vs 'true'), the phase labels, and the date-type labels.
-- ---------------------------------------------------------------------
with s as (
  select * from `clinical-trials-learning.clinical_raw.breast_studies`
), v as (
  select 'primary_completion_date_type' as column_name, primary_completion_date_type as value from s
  union all select 'is_fda_regulated_drug',   is_fda_regulated_drug   from s
  union all select 'is_fda_regulated_device', is_fda_regulated_device from s
  union all select 'phase',                   phase                   from s
  union all select 'overall_status',          overall_status          from s
  union all select 'delayed_posting',         delayed_posting         from s
)
select column_name, coalesce(nullif(trim(value), ''), '(empty)') as value, count(*) as trials
from v
group by 1, 2
order by 1, 3 desc;


-- ---------------------------------------------------------------------
-- C. Are the FDA-regulation flags filled in only for recent trials?
--    Checks: the year from which the "(empty)" share drops sharply.
--    Informs the choice of the 2017-01-18 cutoff.
-- ---------------------------------------------------------------------
select
  extract(year from safe_cast(trim(primary_completion_date) as date)) as primary_completion_year,
  count(*) as trials,
  countif(nullif(trim(is_fda_regulated_drug), '') is null
          and nullif(trim(is_fda_regulated_device), '') is null) as both_flags_empty,
  round(100 * countif(nullif(trim(is_fda_regulated_drug), '') is null
                      and nullif(trim(is_fda_regulated_device), '') is null) / count(*), 1) as pct_empty
from `clinical-trials-learning.clinical_raw.breast_studies`
where safe_cast(trim(primary_completion_date) as date) is not null
group by 1
order by 1;


-- ---------------------------------------------------------------------
-- D. Draft cohort funnel (early exploration)
--    Each row shows how many trials survive up to that rule.
--    This draft predates the US-site rule and does not reproduce the final
--    568-trial cohort; that cohort is defined in fct_results_reporting.
--    Flag spellings ('t') and phase labels ('PHASE1', 'EARLY_PHASE1') were
--    confirmed with query B.
-- ---------------------------------------------------------------------
with p as (
  select
    nct_id,
    safe_cast(trim(primary_completion_date) as date) as pcd,
    upper(trim(primary_completion_date_type)) as pcd_type,
    upper(trim(is_fda_regulated_drug))   in ('T', 'TRUE', 'YES') as fda_drug,
    upper(trim(is_fda_regulated_device)) in ('T', 'TRUE', 'YES') as fda_device,
    upper(trim(phase)) as phase
  from `clinical-trials-learning.clinical_raw.breast_studies`
), flags as (
  select
    true                                                     as r0_all,
    pcd is not null and pcd_type = 'ACTUAL'                  as r1_actual_completion,
    pcd >= date '2017-01-18'                                 as r2_after_final_rule,
    coalesce(fda_drug, false) or coalesce(fda_device, false) as r3_fda_regulated,
    phase is null or phase not in ('PHASE1', 'EARLY_PHASE1') as r4_not_phase1,
    date_add(pcd, interval 12 month) < date '2026-10-11'     as r5_deadline_passed
  from p
)
select '0 all interventional trials'          as step, countif(r0_all) as trials from flags
union all select '1 + actual primary completion', countif(r1_actual_completion) from flags
union all select '2 + completed on/after 2017-01-18', countif(r1_actual_completion and r2_after_final_rule) from flags
union all select '3 + FDA-regulated drug/device',
  countif(r1_actual_completion and r2_after_final_rule and r3_fda_regulated) from flags
union all select '4 + not phase 1',
  countif(r1_actual_completion and r2_after_final_rule and r3_fda_regulated and r4_not_phase1) from flags
union all select '5 + 12-month deadline passed',
  countif(r1_actual_completion and r2_after_final_rule and r3_fda_regulated and r4_not_phase1
          and r5_deadline_passed) from flags
order by step;


-- ---------------------------------------------------------------------
-- E. Date sanity checks
--    Checks: results submitted BEFORE primary completion (should be rare
--    or zero), and how long submission-to-posting usually takes.
-- ---------------------------------------------------------------------
with d as (
  select
    safe_cast(trim(primary_completion_date) as date)      as pcd,
    safe_cast(trim(results_first_submitted_date) as date) as submitted,
    safe_cast(trim(results_first_posted_date) as date)    as posted
  from `clinical-trials-learning.clinical_raw.breast_studies`
)
select
  countif(submitted is not null)                          as trials_with_results_submitted,
  countif(submitted < pcd)                                as submitted_before_completion,
  countif(posted < submitted)                             as posted_before_submitted,
  approx_quantiles(date_diff(posted, submitted, day), 4)  as submit_to_post_days_quartiles,
  approx_quantiles(date_diff(submitted, pcd, day), 4)     as completion_to_submit_days_quartiles
from d;


-- ---------------------------------------------------------------------
-- F. Extension requests (certification / delayed posting)
--    Checks: how many trials requested a delay, and whether
--    delayed_posting overlaps with disposition dates.
-- ---------------------------------------------------------------------
select
  coalesce(nullif(trim(delayed_posting), ''), '(empty)')              as delayed_posting,
  nullif(trim(disposition_first_submitted_date), '') is not null      as has_disposition_date,
  count(*)                                                            as trials
from `clinical-trials-learning.clinical_raw.breast_studies`
group by 1, 2
order by 3 desc;
