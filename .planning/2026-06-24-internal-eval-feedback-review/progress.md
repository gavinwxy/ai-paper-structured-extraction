# Progress Log

## Session: 2026-06-24

### Phase 1: Feedback Discovery
- **Status:** in_progress
- **Started:** 2026-06-24
- Actions taken:
  - Read `/Users/wxy/.codex/RTK.md`; learned shell commands must be prefixed with `rtk`.
  - Read `planning-with-files` skill instructions and templates.
  - Checked for prior session catchup; no output was produced.
  - Listed repository top-level structure and key files.
  - Created scoped planning files for this review.
  - Read `/Users/wxy/Downloads/内部评测结果.md` with line numbers.
  - Extracted the main actionable feedback themes into `findings.md`.
  - Ran targeted repository searches for metadata fallback, truncation, relation validation, and score/baseline handling.
  - Recorded initial code search discoveries in `findings.md`.
  - Inspected metadata enrichment, production worker calls, relation pruning, score repair, evidence/method prompts, schema generator, and relevant tests.
  - Identified two low-risk code fixes to implement: broaden dirname metadata parsing and align Measure setup-id validation/schema.
  - Implemented metadata dirname parser broadening in `section_pipeline.py`.
  - Implemented Measure `setup_ids` validator/schema wording alignment in `section_pipeline.py`, `tools/generate_section_schemas.py`, and regenerated `schemas/section-evidence.schema.json`.
  - Added focused tests in ignored local test files and ran targeted + broader related pytest suites through `uv`.
- Files created/modified:
  - `.planning/2026-06-24-internal-eval-feedback-review/task_plan.md`
  - `.planning/2026-06-24-internal-eval-feedback-review/findings.md`
  - `.planning/2026-06-24-internal-eval-feedback-review/progress.md`
  - `.planning/2026-06-24-internal-eval-feedback-review/findings.md` (updated)
  - `section_pipeline.py`
  - `tools/generate_section_schemas.py`
  - `schemas/section-evidence.schema.json`
  - `tests/test_agent_artifacts.py` (ignored by git)
  - `tests/test_section_pipeline.py` (ignored by git)

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Session catchup | planning-with-files catchup script | Report unsynced context if present | No output | ok |
| Targeted pytest | `uv run pytest tests/test_agent_artifacts.py::EnrichMetadataTests tests/test_schema_generator_descriptions.py::GeneratorByteStabilityTests tests/test_section_pipeline.py::FrameworkEvalFixTests::test_released_dataset_contribution_can_scope_measure_setup_ids` | Pass | 15 passed | ok |
| Related full pytest | `uv run pytest tests/test_agent_artifacts.py tests/test_schema_generator_descriptions.py tests/test_section_pipeline.py` | Pass | 402 passed | ok |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-06-24 | `rtk find` rejected compound predicates/actions | 1 | Used `rg --files` and `ls` instead. |
| 2026-06-24 | Broad `rg` across tests emitted very large fixture output | 1 | Narrowed searches to specific test files and patterns. |
| 2026-06-24 | Default Python had no `pytest` module | 1 | Used `uv run pytest`. |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Complete |
| Where am I going? | Final summary to user |
| What's the goal? | Review internal evaluation feedback and identify actionable code changes |
| What have I learned? | See findings.md |
| What have I done? | Reviewed feedback, mapped it to code, implemented two low-risk fixes, and verified related tests |

### Citation Tail Trim Follow-up
- **Status:** in_progress
- User requested implementing the citation-stage trim and running an A/B on the citation fail cases.
- Confirmed current code still feeds full `paper_content` to citation Pass 1 in both `production/worker.py` and `section_pipeline.run_pipeline`.
- Confirmed `slice_body_content` drops the detected bibliography and everything after it, while `_slice_references_blob` keeps only the bibliography section from the original full paper.
- Planned experiment: use the old production output as baseline for the 21 `citations` truncation failures, then rerun those papers with current code and compare result/cost metrics.
- Implemented citation Pass 1 body slicing in `production/worker.py` and `section_pipeline.py`; updated CLI/config comments so `--keep-references-in-body` is the explicit old-behavior opt-out.
- Updated local tests so default citation input no longer contains the bibliography token, while reference metadata still receives the bibliography slice and keep-flag runs still pass the full paper to citation.
- Test selector mistake: `tests/test_section_pipeline.py::BodyReferenceCutTests` does not exist; corrected to `PipelineEndToEndTests`.
- Targeted tests passed: `uv run pytest tests/test_production_worker.py::BodyReferenceCutTests tests/test_section_pipeline.py::PipelineEndToEndTests::test_run_pipeline_trims_bibliography_for_own_content_stages tests/test_section_pipeline.py::PipelineEndToEndTests::test_run_pipeline_keep_flag_feeds_full_paper_to_own_content_stages tests/test_body_slice.py` -> 10 passed.
- Prepared symlink input dir `production-outputs/citation_tail_trim_failcases_input_20260624` with the 21 baseline citation truncation cases.
- Baseline over those 21: citation truncation 21/21; citation-stage eff-cost proxy 2,925,584; full-run eff-cost proxy 5,383,410.
- Ran treatment: `python -m production ... --model deepseek-v4-pro --base-url http://35.220.164.252:3888/v1 --paper-concurrency 8 --llm-concurrency 16 --max-tokens 32768 --planning-max-tokens 24576 --force`.
- Treatment output `production-outputs/citation_tail_trim_failcases_deepseek_v4pro_20260624_1155`: 21/21 completed, 0 failed, 0 validation issues, 1 citation truncation.
- Treatment citation artifacts: 20 papers with citations, 1,012 cited works, 1,040 citation relations, 694 references.
- Treatment cost: citation-stage eff-cost proxy 671,058; full-run eff-cost proxy 2,698,866.
- Residual citation truncation: `NAACL_2025_0224-c8cbba9aead9`; body-only citation input is only 42,085 chars, so this is dense-body output explosion rather than appendix-tail leakage.
- Broader related tests passed: `uv run pytest tests/test_production_worker.py tests/test_section_pipeline.py tests/test_body_slice.py tests/test_schema_generator_descriptions.py tests/test_agent_artifacts.py` -> 430 passed.
- User requested updating related docs and committing code.
- Updated `README.md` current behavior docs for body-fed citation Pass 1, `--keep-references-in-body`, blob-scoped reference metadata, and Measure setup-host validation.
- Updated `CHANGELOG.md` with the 2026-06-24 internal-eval fix note and A/B results.
- Re-ran `git diff --check` and the 430-test related suite; both passed.
