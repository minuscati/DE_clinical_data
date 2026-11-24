# Timeliness of results submission in breast cancer trials

> **Status: exploratory pilot (November 2026).** Not pre-registered. All
> estimates are preliminary and unadjusted.

## Questions

FDAAA 801 and its 2017 Final Rule generally require applicable clinical trials
(ACTs) to submit summary results to ClinicalTrials.gov within one year of
primary completion. Certifications for delayed submission and extensions for
good cause have distinct conditions (42 CFR 11.44); neither implies an automatic
36-month deadline.

In a cohort of interventional breast cancer trials:

1. How promptly are results submitted?
2. How do industry and other lead sponsors compare?
3. How sensitive is that comparison to the treatment of delay-related registry records?

## Data and cohort

- **Source:** AACT snapshot of ClinicalTrials.gov, 2026-10-11 (`studies`,
  `browse_conditions`, `sponsors`, `facilities`). The base cohort of 11,211
  interventional trials indexed with the MeSH term *Breast Neoplasms* is built by
  the [data pipeline](../../README.md) of this repository.
- **Cohort rules** (dbt model [`fct_results_reporting`](../../dbt/models/marts/fct_results_reporting.sql)).
  They define the analytic cohort from registry fields, not a legally
  adjudicated set of ACTs. Each excluded trial is counted at the first rule it fails.

| Rule | Remaining | Excluded |
|---|---:|---:|
| Interventional trials, MeSH *Breast Neoplasms* | 11,211 | |
| 1. Actual primary completion date available | 6,779 | 4,432 |
| 2. Primary completion on or after 2017-01-18 | 3,575 | 3,204 |
| 3. FDA-regulated drug or device flag recorded as true | 1,041 | 2,534 |
| 4. Not phase 1 or early phase 1 (missing phase retained) | 678 | 363 |
| 5. At least one recorded US site | 614 | 64 |
| 6. Primary completion + 12 calendar months before the snapshot | **568** | 46 |

## Outcomes

- **Common benchmark:** first results submission within **365 days** of primary
  completion, irrespective of delay-related records. Missing submissions count as
  not meeting the benchmark. This is distinct from 12 calendar months.
- **Deadline scenario (secondary):** primary completion + 12 calendar months, or
  + 36 calendar months when `disposition_first_submitted_date` is present. The
  field is used only as a delay-related indicator; the analysis does not
  establish the legal basis, validity or applicable deadline of each record. The
  36-month allowance is an assumption, not a verified deadline. Five unsubmitted
  trials still within that allowance are excluded only from scenario-based proportions.
- **Time to first submission** from primary completion, censored at the
  snapshot date (months = days / 30.4375).

Outcomes concern first submission, not public posting, completeness of the
submitted results or journal publication.

**Records needing review:** four in-scope trials have a submission date before
primary completion. They are retained in the binary analyses and given event
time 0 in the time-to-event analysis.

## Methods

Exact (Clopper–Pearson) 95% CIs for single proportions; difference CIs and
two-sided tests from R's `prop.test` with continuity correction; Kaplan–Meier
curves of cumulative submission (1 − S(t)) with an overall log-rank test.
Comparisons use the registry lead sponsor classes `INDUSTRY` (n = 237) and
`OTHER` (n = 310); `OTHER` has not been independently classified as academic.
The remaining 21 government/network trials contribute to cohort totals only.
Code: [`03_compliance_analysis.qmd`](03_compliance_analysis.qmd).

## Results

**Deadline scenario, all 568 trials:** 312 (54.9%) submitted by the scenario
deadline, 163 (28.7%) submitted later, 88 (15.5%) remained unsubmitted beyond
it, and 5 (0.9%) remained unsubmitted within the 36-month allowance. Excluding
those five, the scenario-based share is 312/563 (55.4%).

**By registry lead sponsor class:**

| | Industry | Other | Difference, pp (95% CI) | p |
|---|---:|---:|---:|---:|
| Within 365 days | 117/237 (49.4%) | 152/310 (49.0%) | 0.3 (−8.5 to 9.1) | 1.00 |
| By scenario deadline¹ | 141/232 (60.8%) | 160/310 (51.6%) | 9.2 (0.4 to 17.9) | 0.042 |
| Delay-related record present | 32/237 (13.5%) | 8/310 (2.6%) | 10.9 (5.9 to 16.0) | < 0.001 |
| By 24 months (KM)² | 65.0% | 77.0% | | |
| By 36 months (KM)² | 79.9% | 86.2% | | |

¹ Excludes 5 industry trials still within the assumed allowance; exact CIs
54.2–67.1% and 45.9–57.3%.
² All 237 and 310 trials. The log-rank test compares the full curves
(p = 0.002), not a single time point.

![Cohort selection](figures/01_funnel.png)

![Cumulative first results submission by registry lead sponsor class](figures/02_km_by_sponsor.png)

*The dashed line is a 12-month reference, not a trial-specific legal deadline.*

## Interpretation

At 365 days the two sponsor classes had similar submission proportions; this is
not evidence of equivalence. Sponsor differences were sensitive to the deadline
definition. Both the deadline rule and the denominator change between the
benchmark and the scenario, so these unadjusted comparisons do not establish why
the difference arose. The 365-day benchmark and the submission-time distribution
also answer different questions.

## Limitations

- Deadlines and eligibility are operational approximations. Registry
  missingness (for example empty FDA-regulation flags) may bias selection in an
  unknown direction.
- Comparisons are unadjusted and ignore clustering by sponsor.
- Kaplan–Meier assumes non-informative censoring. Proportional hazards have not
  been tested and would need checking before fitting a Cox model.
- Only registry submission is considered.

## Possible next steps

- Assess how the selection rules, especially the FDA-flag requirement, affect
  the estimates, for example with alternative registry-based ACT approximations.
- Adjusted comparisons (phase, enrollment, product type, completion year) that
  account for clustering by sponsor.
- Review delay-related records and the four pre-completion submissions.

## Reproduce

1. Build the dbt models: `dbt build --select fct_results_reporting agg_results_reporting_by_sponsor`.
   Tests cover grain, accepted values and a warning for trials whose results
   date precedes primary completion (23 in the base cohort, 4 in scope).
2. Run [`02_export_for_r.sql`](02_export_for_r.sql) in BigQuery and save the
   result as `data/results_reporting.csv` in the repository root (git-ignored).
3. Render [`03_compliance_analysis.qmd`](03_compliance_analysis.qmd) with Quarto,
   or run it in RStudio from this folder.

[`01_data_audit.sql`](01_data_audit.sql) holds the data checks used to choose the
cohort rules (fill rates, value spellings, FDA-flag missingness by year, date
consistency). Its draft funnel predates the US-site rule.

## References

- Clinical Trials Registration and Results Information Submission (Final Rule),
  42 CFR Part 11. *Federal Register* 2016;81:64981–65157.
- Curtin M, Wiltshire A, Nilsonne G, Siebert M. Results reporting in
  antimicrobial agent clinical trials: an analysis of compliance and timeliness
  under the 2017 FDA Amendments Act Final Rule. *J Clin Epidemiol.* 2026;196:112307.
- Nilsonne G, Wieschowski S, DeVito NJ, et al. Results reporting for clinical
  trials led by medical universities and university hospitals in the Nordic
  countries was often missing or delayed. *J Clin Epidemiol.* 2025;181:111710.
