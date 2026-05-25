# Current Extraction Issues

**Source batch:** `tests/section-extraction-outputs/production-batch-deepseek-v4-flash-20260525/`
**Model:** `bailian/deepseek-v4-flash` · **Papers:** 001–050 (ros_ai_mainstream_parsed_200) · **Date:** 2026-05-25

This batch was run after the prior session's framework fixes (the 9 issues in
`framework-ambiguity-cognitive-load-review-opus.md`). The dominant pre-fix failure
(`method plan has no root item`, 15 papers) is now fully resolved. This document
records the issues that remain.

## Batch outcome

| Metric | Original flash (05-22, pre-fix) | This batch (05-25, post-fix) |
|---|---|---|
| Completed | 34 / 50 | **49 / 50** |
| Failed | 16 | **1** |
| LLM errors | 4 | **0** |
| Validation issues (total) | 309 | **124** |
| Max issues on one paper | 42 | **10** |
| Fully-valid papers (zero issues) | 8 | **20** |
| Wall time | 1031 s | 813 s |

Of the 49 papers that produced output: **20 are fully valid**, 29 have validation
issues, and 1 (`042`) hard-failed at planning.

Two views below: **hard validation failures** (block a paper from being `valid`)
and **silent assembly repairs** (lossy fixes applied to papers that still pass).

---

## A. Hard validation failures (124 issues across 29 papers)

| Count | Papers | Category |
|---|---|---|
| 95 | 21 | Provenance marker not in `§N` format |
| 18 | 10 | `Metric.scores` empty |
| 6 | 5 | Missing / empty provenance |
| 4 | 2 | Dangling id reference |
| 1 | 1 | `Metric.subject_id` issue |

### Issue 1 — Provenance markers outside `§N` format *(dominant: 95 / 21 papers)*

**Severity:** High (single largest cause of invalidity).

The model cites provenance at a granularity the IR rejects. Observed markers and frequency:

- **Appendix sections:** `§A.4` (11×), `§C.1` (7×), `§D.2` (4×), `§B.1` (3×),
  `Appendix G.3` (3×), `§A.1` (3×), `§G.3.1`, `§G.3.2`, `§A.2`, `§C.3`, `§E`, `§F.1`, `§D.4`, `§D.5` …
- **Figure / table refs:** `Figure 2` (5×), `Table 1` (4×), `Table 3` (2×)
- **Bare numbers:** `8` (3×), `§D`

**Root cause:** assembly's `_normalize_provenance_markers` collapses numeric
`§3.2 → §3`, but appendix letters (`§A.*`), figure/table references, and bare
numbers have no top-level `§N` to collapse to, so they are left to fail.

**Suggested fix:** extend the normalizer to map appendix markers to a canonical
form (or accept `§<letter>` as valid), drop/route figure-table-equation references,
and reject bare numbers at the prompt level. Tighten the provenance instruction in
the section prompt to forbid figure/table/bare-number sources.

### Issue 2 — Empty `Metric.scores` *(18 / 10 papers)*

**Severity:** Medium. Also a design question.

The model emits Metric units with `scores: []` (e.g. `met:robustness_check`), which
the validator rejects (`scores must be a non-empty list`). Common on proof/theory
papers that have no numeric score.

**Tension:** either these units should be `Claim`s (qualitative findings), or the
schema is too strict in forbidding empty `scores`. Needs a decision, not just a
prompt patch.

### Issue 3 — Missing / empty provenance *(6 / 5 papers)*

**Severity:** Medium. Every `Claim` and `Metric` requires non-empty provenance; the
model occasionally omits it.

### Issue 4 — Dangling id references *(4 / 2 papers)*

**Severity:** Low–Medium. A `subject_id` / `target_id` / link endpoint references a
unit id that is not defined in the assembled output.

---

## B. Silent assembly repairs (100 lossy fixes; papers still pass)

These do not fail validation but represent lost or mutated information.

| Count | Repair |
|---|---|
| ~50 | Normalized provenance marker `§N.M → §N` (e.g. `§3.2→§3`, `§4.1→§4`, `§5.1→§5`) |
| 12 | Dropped unresolved `covers_entries` in experiment section |
| 14 | Dropped duplicate unit id (`mth` 7×, `met` 4×, `ent` 3×) |
| 2 | Reset experiment section `anchor_id` |

### Issue 5 — Cross-section duplicate IDs *(1 hard-fail + 14 silent dedups)*

**Severity:** High (it is the only hard planning failure).

Planner/extractor reuses an id across sections (e.g. `mth:nmf_mkl` appears in both a
method and an experiment plan). At assembly it is deduped lossily; at **planning** it
hard-fails:

- **`042_ICML_2009_Non-monotonic_feature_selection`** —
  `Plan item mth:nmf_mkl_2 has invalid prefix for experiment: expected one of ['met:', 'cnd:', 'ent:']`.
  The experiment copy was `_2`-suffixed by dedup but kept its illegal `mth:` prefix.

**Suggested fix:** when a duplicate id crosses into a section whose prefix rules
cforbid it, drop/relabel rather than suffix-and-keep. This is a narrower bug than the
prior session's `_collapse_exact_duplicate_plan_items` work (those were verbatim
duplicates; this is a same-id/different-section prefix collision).

### Issue 6 — Unresolved `covers_entries` *(12 / experiment sections)*

**Severity:** Medium. The extractor claims it covered a plan item but produced no
matching unit, so assembly prunes the trace and the item resurfaces as uncovered
(feeds Issue 7).

---

## C. Extraction-quality issue (valid output, low recall)

### Issue 7 — Must-coverage gaps *(53 uncovered must-items across 14 papers)*

**Severity:** High — this is the real quality ceiling, distinct from schema correctness.

The planner marks must-priority items the section extractor never produces. Worst cases:

| must-covered / total | paper |
|---|---|
| 4 / 13 | `022_NeurIPS_2023_Bias_in_Evaluation_Processes` |
| 5 / 9 | `013_NeurIPS_2023_Equal_Opportunity_of_Coverage` |
| 7 / 14 | `050_ICML_2024_Compressible_Dynamics` |
| 8 / 16 | `023_NeurIPS_2024_DiffTOP` |
| 12 / 18 | `019_NeurIPS_2024_Is_Value_Learning_Really_the_Bottleneck` |
| 13 / 16 | `009_NeurIPS_2023_Beyond_Normal` |
| 8 / 10 | `001_NeurIPS_2023_Re-Think_and_Re-Design_GNN` |
| 13/15, 8/9, 18/21, 20/21, 11/14, 13/14, 7/10 | 002, 015, 020, 021, 031, 032, 045 |

Theory-heavy papers are hit hardest — the plan promises structure the section
extractor doesn't deliver. Needs prompt-level work on the planner↔extractor contract,
not a schema patch.

---

## Priority ranking

1. **Issue 1 — provenance granularity** (most invalidity, most tractable: normalizer + prompt).
2. **Issue 7 — must-coverage recall** (highest value for extraction quality; hardest).
3. **Issue 5 — cross-section duplicate IDs** (only hard failure; narrow, fixable).
4. **Issue 2 — empty `Metric.scores`** (needs a Claim-vs-Metric / schema decision).
5. Issues 3, 4, 6 — smaller, mostly downstream of the above.
