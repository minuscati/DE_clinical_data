{{ config(materialized='table') }}

-- Grain: one row per trial in the base cohort (11,211), not only in-scope ones.
-- The rules approximate the analytic cohort from registry fields; they are not
-- a legal adjudication of applicable clinical trial (ACT) status.

with studies as (
    select * from {{ ref('stg_breast_studies') }}
), trials as (
    select nct_id, lead_sponsor_class from {{ ref('fct_breast_trials') }}
), us_sites as (
    -- One row per trial with at least one US facility (distinct before joining).
    select distinct nct_id
    from {{ ref('stg_breast_locations') }}
    where country = 'United States'
), rules as (
    -- Cohort rules. A rule that cannot be evaluated (NULL) counts as not met.
    select
        studies.nct_id,
        studies.trial_title,
        studies.overall_status,
        studies.phase,
        trials.lead_sponsor_class,
        studies.primary_completion_date,
        studies.results_first_submitted_date,
        studies.disposition_first_submitted_date,
        date_add(studies.primary_completion_date, interval 12 month) as due_date,

        coalesce(studies.primary_completion_date is not null
                 and studies.primary_completion_date_type = 'ACTUAL', false) as r1_actual_completion,
        coalesce(studies.primary_completion_date >= date '2017-01-18', false) as r2_after_final_rule,
        -- Empty FDA flags count as not regulated; how this selection affects the
        -- estimates is not known.
        coalesce(studies.is_fda_regulated_drug, false)
            or coalesce(studies.is_fda_regulated_device, false) as r3_fda_regulated,
        -- Exclude phase 1 only; device trials (phase NA) and missing phase are kept.
        coalesce(studies.phase not in ('PHASE1', 'EARLY_PHASE1'), true) as r4_not_phase1,
        -- At least one recorded US site; trials without facility records fail.
        us_sites.nct_id is not null as r6_has_us_site,
        coalesce(date_add(studies.primary_completion_date, interval 12 month)
                 < date '{{ var("snapshot_date", "2026-10-11") }}', false) as r5_deadline_passed
    from studies
    left join trials
        on studies.nct_id = trials.nct_id
    left join us_sites
        on studies.nct_id = us_sites.nct_id
), derived as (
    select
        *,
        r1_actual_completion and r2_after_final_rule and r3_fda_regulated
            and r4_not_phase1 and r6_has_us_site and r5_deadline_passed as in_scope,
        -- Delay-related record: disposition_first_submitted_date is present. The
        -- registry does not say whether it is a certification or an extension
        -- request, or whether it was valid; the column name is kept for
        -- compatibility with the export and the R analysis.
        disposition_first_submitted_date is not null as extension_requested,
        -- Deadline scenario (an analysis assumption, not a verified legal
        -- deadline): primary completion + 12 months, or + 36 months when a
        -- delay-related record is present.
        case when disposition_first_submitted_date is not null
             then date_add(primary_completion_date, interval 36 month)
             else due_date end as effective_due_date,
        date_diff(results_first_submitted_date, primary_completion_date, day) as days_to_submission,
        coalesce(results_first_submitted_date < primary_completion_date, false) as submitted_before_completion,
        case
            when not r1_actual_completion then '1_not_actually_completed'
            when not r2_after_final_rule  then '2_completed_before_2017'
            when not r3_fda_regulated     then '3_not_fda_regulated'
            when not r4_not_phase1        then '4_phase_1'
            -- US-site rule added later; the 4b_ prefix keeps the label order.
            when not r6_has_us_site       then '4b_no_us_site'
            when not r5_deadline_passed   then '5_deadline_not_passed'
        end as exclusion_reason
    from rules
)
select
    *,
    -- Status under the deadline scenario. ON_TIME / LATE / OVERDUE_NOT_REPORTED
    -- are scenario labels; EXTENSION_REQUESTED means unsubmitted and still
    -- within the 36-month allowance.
    case
        when not in_scope then null
        when results_first_submitted_date <= effective_due_date then 'ON_TIME'
        when results_first_submitted_date is not null then 'LATE'
        when extension_requested
             and effective_due_date >= date '{{ var("snapshot_date", "2026-10-11") }}' then 'EXTENSION_REQUESTED'
        else 'OVERDUE_NOT_REPORTED'
    end as reporting_status
from derived
