# Findings & Decisions

## Requirements
- Review `/Users/wxy/Downloads/内部评测结果.md` carefully.
- Understand feedback on extraction results.
- Think through what code, prompt, schema, or eval changes could improve the system.
- Provide grounded recommendations, ideally with file references.

## Research Findings
- Feedback report covers `section-ir-0.17` extraction for 2,000 papers; 1,998 passed project validation, all required JSON files exist and parse.
- Main data source is `06_extraction.json`; report explicitly limits conclusions to structural integrity, field availability, graph connectivity, numeric traceability, and cost logs, not semantic faithfulness.
- Repeated/actionable defects:
  - 2 invalid papers with 5 validator issues.
  - 21 papers had citation/reference stage output truncation; main extraction usable but citation layer incomplete.
  - `02_metadata.json` year and venue coverage are low because many values are only available from directory/corpus metadata.
  - 415 strict placement deviations: content that may belong to method/contribution appears in evidence, especially dataset/benchmark-as-contribution cases.
  - 11 relation edges have invalid endpoint type combinations.
  - Measure/Score extraction is strong overall, but score `system_id` resolves for only 80.63%, usually because table-only baselines are not created as method/system nodes.
  - 30 papers did not get score fidelity checks; 4,714 flags exist in score fidelity.
- Most promising code-level improvements from feedback:
  - Add/review deterministic metadata fallback for year/venue at import or reassembly time.
  - Add retry/continuation or low-confidence marking for citation/reference truncation.
  - Add deterministic post-processing for invalid relation endpoint type combinations.
  - Add weak node/alias generation for table-only baselines referenced by scores.
  - Add schema routing/post-processing for dataset or benchmark contributions found in evidence.
- Initial code search discoveries:
  - `section_pipeline.py` already has `enrich_metadata()` for dirname/default venue backfill, and `tools/build_agent_index.py` can retrofit this into `02_metadata.json`; the low coverage in the report may reflect either not running retrofit/index build, or a filename regex mismatch for IDs like `ACL_2025_...`.
  - Truncation is treated as a fast-fail `TruncatedResponseError`; `production/llm.py` records truncated stage usage and `production/runner.py` counts `truncated_papers`, but there is no visible continuation/chunking strategy for citation/reference stages.
  - `section_pipeline.py` has `_drop_invalid_relations()` to prune invalid endpoint type pairings during assembly, suggesting the 11 invalid endpoint-type edges may be coming from artifacts not passed through the latest assembly/retrofit path or from relation classes not covered by that pruning path.
  - `section_pipeline.py` has `_repair_score_refs()` that blanks dangling/wrong-type `system_id`, `opponent_id`, `setup_id`, and `judge_id`; this explains the report's lower score `system_id` resolution without treating it as a fatal validator error.
  - `tools/build_agent_index.py` already emits `_result_rows.jsonl` with deterministic baseline table rows (`source='table_blob'`, `system_id=None`), which partly addresses table-only baseline analysis but does not create weak entity nodes or aliases.
- More precise code findings:
  - Current metadata dirname regex in `section_pipeline.py` only matches `NNN_VENUE_YYYY_...` and `NNN_YYYY_...`, but the evaluated examples use `ACL_2025_0998-...` and `NeurIPS_2024_4166-...`; this likely explains why year/venue backfill did not lift coverage in the report.
  - `production/worker.py` calls `enrich_metadata(metadata, paper_id)` before writing `02_metadata.json`, and `tools/build_agent_index.py` retrofits the same function, so fixing that regex benefits both fresh runs and existing corpus retrofit.
  - Evidence prompt deliberately materializes dataset/benchmark/finding Contributions in evidence and allows dataset/benchmark Contribution roots to host score rows.
  - `_repair_score_refs()` already treats Measure-level `setup_ids[]` as valid when pointing to a local dataset/benchmark Contribution, but `_validate_unit_fields()` still rejects Measure-level `setup_ids[]` unless they point to ExperimentSetup. This is an internal contract mismatch.
  - Schema generator still describes `setup_ids` as local ExperimentSetup-only, while score-row `setup_id` description and runtime repair mention dataset/benchmark Contribution support. Schema text should be aligned so json_object models are less likely to emit inconsistent structures.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Start with failure-mode taxonomy, then inspect code | This reduces the chance of chasing irrelevant implementation details. |
| Broaden dirname metadata parsing | Evaluation examples use `ACL_2025_...` / `NeurIPS_2024_...`, while existing regex only handled `NNN_VENUE_YYYY_...`; this is a likely cause of low year/venue fallback coverage. |
| Align Measure `setup_ids` validator/schema with resource Contribution semantics | Runtime repair and prompt allow dataset/benchmark Contributions to host score rows; validator/schema should not contradict that. |
| Keep truncation continuation and weak baseline nodes as recommendations | They are larger behavioral changes with cost/output-shape implications, not small deterministic fixes. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| RTK `find` proxy does not support compound predicates | Use `rg --files`, simple `ls`, or `rtk proxy find` if a full find expression is needed. |
| Broad `rg` over `tests/` produced huge fixture output | Switch to targeted files and narrower patterns. |
| Default `python -m pytest` had no pytest module | Used `uv run pytest` for the project environment. |

## Implemented Changes
- `section_pipeline.py`
  - Replaced narrow dirname metadata regex with a single optional-prefix parser that supports `NNN_VENUE_YYYY_...`, `VENUE_YYYY_...`, `NNN_YYYY_...`, and `YYYY_...`.
  - Updated `enrich_metadata()` to use named regex groups.
  - Updated Measure-level `setup_ids[]` validation to accept local dataset/benchmark Contribution units, matching row-level `setup_id` and `_repair_score_refs()`.
- `tools/generate_section_schemas.py`
  - Updated Measure `setup_ids` and score-row `setup_id` descriptions to mention setup hosts, including dataset/benchmark Contributions.
- `schemas/section-evidence.schema.json`
  - Regenerated from the schema generator.
- Ignored local tests under `tests/`
  - Added/used focused tests for prefix-less venue/year dirname fallback and dataset/benchmark Contribution setup scoping. The `tests/*` tree is git-ignored in this repo.

## Remaining Recommendations
- Add citation/reference continuation or chunking for truncation-prone stages, or at minimum an explicit low-confidence artifact listing the exact failed stage and missing layer.
- Add a corpus-level weak baseline alias/entity artifact over `_result_rows.jsonl` `source='table_blob'` rows instead of forcing table-only baselines into internal method nodes.
- Add an eval/reporting pass that emits invalid relation endpoint examples and strict placement deviations as machine-readable JSONL, not only prose counts.
- Consider a post-processing report for dataset/benchmark-as-contribution routing so downstream import can decide whether to keep as evidence Contribution or transform for KG use.

## Citation Tail Trim A/B (2026-06-24)

### Setup
- Baseline: existing production run `production-outputs/large_models_llm_selected_2000_deepseek_v4pro_thinkoff_20260622_205455`.
- Treatment: current working tree (metadata dirname fix + Measure setup-id schema/validator fix + citation Pass 1 body trim), run on the 21 baseline papers whose citation stage truncated.
- Treatment output: `production-outputs/citation_tail_trim_failcases_deepseek_v4pro_20260624_1155`.
- Model/base URL: `deepseek-v4-pro` at `http://35.220.164.252:3888/v1`.
- Cost metric: `eff-cost proxy = uncached_prompt + 4 * completion`, matching `tools/token_cost_report.py`.

### Result
- Batch status: 21/21 completed, 0 validation issues.
- Citation truncation: 21/21 baseline -> 1/21 treatment.
- Citation artifacts: baseline had 0 papers with citations/references; treatment had 20 papers with citation output, 1,012 cited works, 1,040 citation relations, and 694 assembled references.
- Metadata venue coverage on these 21: 3/21 -> 21/21.
- Metadata year coverage on these 21: 3/21 -> 21/21.

### Token / Cost Proxy
| Scope | Baseline | Treatment | Change |
|---|---:|---:|---:|
| Citation prompt tokens | 939,152 | 348,010 | -591,142 (-63.0%) |
| Citation completion tokens | 516,096 | 125,082 | -391,014 (-75.8%) |
| Citation eff-cost proxy | 2,925,584 | 671,058 | -2,254,526 (-77.1%) |
| Full-run prompt tokens | 3,165,650 | 2,747,890 | -417,760 (-13.2%) |
| Full-run completion tokens | 715,816 | 422,944 | -292,872 (-40.9%) |
| Full-run eff-cost proxy | 5,383,410 | 2,698,866 | -2,684,544 (-49.9%) |

### Residual
- `NAACL_2025_0224-c8cbba9aead9` still truncates in citation Pass 1 after trimming: raw/body/reference chars = 70,454 / 42,085 / 11,534; body has 76 `et al.` mentions, 64 author-year parentheticals, and 122 year mentions. This is a dense-body citation-output problem, not a post-reference appendix-tail problem.

## Resources
- `/Users/wxy/Downloads/内部评测结果.md`
- `/Users/wxy/projects/knowledge-ontology-ai-focused/section_pipeline.py`
- `/Users/wxy/projects/knowledge-ontology-ai-focused/prompts/section-extraction/`
- `/Users/wxy/projects/knowledge-ontology-ai-focused/schemas/`
- `/Users/wxy/projects/knowledge-ontology-ai-focused/tools/`

## Visual/Browser Findings
- None.
