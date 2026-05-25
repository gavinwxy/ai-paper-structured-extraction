# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository now implements and documents a **5-section scientific literature extraction pipeline**.

The active system extracts a paper's argumentative spine into section-IR:

`context and gap -> claim -> method -> experiment -> analysis`

## Active Architecture

The pipeline is two-stage:

1. **Planning pass**: `prompts/section-extraction/planning-pass.md`
   - Produces `spine_summary` and `section_plans[]` only for `method` and `experiment`.
   - Method and experiment plan items may include structural `relations` hints: `part_of`, `feeds`, `alternative_to`, and `evaluates`.
   - `section_pipeline.py` injects empty planless stubs for `context`, `claim`, and `analysis` before extraction.

2. **Parallel section extraction**: `prompts/section-extraction/section-extraction-pass.md`
   - `section-extraction-pass.md` is a **slim shared core**: only the rules common to every section (identifiers, provenance format, the output envelope, universal hard constraints). It is byte-identical across all section calls, so the paper text stays in the cross-section prompt cache.
   - Each expanded section extracts independently and returns `section`.
   - Receives injected schema constraint, spine_summary, id_registry, section_plan, section_focus, and paper text.
   - Planless sections receive `items: []`, extract directly from `section_focus` and `spine_summary`, and return `covers_entries: []`.
   - Per-section modules (`prompts/section-extraction/section-modules/{context,claim,method,experiment,analysis}.md`) are **self-contained section contracts** injected into the user prompt as `section_focus`. Each module declares its section's allowed unit types and field contracts, the controlled vocabularies and link-matrix subset it uses, plan-relation handling (method/experiment), a worked example, and section-specific rules — none of it duplicated in the shared core.

Assembly and validation run in Python (`section_pipeline.py`). The default entrypoint is `run_pipeline()`.

Both stages always use API-level structured output (`response_format` with `strict: True`). Planning schema is `schemas/planning-output.schema.json` and constrains LLM planning output to method/experiment plans. Section extraction uses the active per-section schemas under `schemas/section-{section}.schema.json`; each expanded section receives the schema for its own `section_type`.

Section extraction responses use typed unit arrays instead of a flat `units[]` array. Each schema exposes only the arrays allowed for that section, such as `contexts`, `entities`, and `claims` for context sections, `metrics`, `conditions`, and `entities` for experiment sections, and `claims`, `metrics`, and `entities` for analysis sections. `section_pipeline.py` flattens these typed arrays back into `section["units"]` during assembly so validation and rendering continue to consume the stable section-IR shape.

Implementation entry point: `section_pipeline.py`.

Authoritative validation: Python `validate_section_ir()` in `section_pipeline.py` is the runtime contract.

Default section schemas: `schemas/section-context.schema.json`, `section-claim.schema.json`, `section-method.schema.json`, `section-experiment.schema.json`, `section-analysis.schema.json`.

Regenerate per-section schemas with `python tools/generate_section_schemas.py`.

Per-section schemas are generated from `tools/generate_section_schemas.py`.

Per-section focus modules: `prompts/section-extraction/section-modules/context.md`, `claim.md`, `method.md`, `experiment.md`, `analysis.md`.

Design reference: `docs/section-ir-design.md`.

## Section-IR Rules

- Units have flat structure — type-specific fields sit directly on the unit, no `payload` wrapper.
- Raw section responses group units into typed arrays: `contexts`, `claims`, `methods`, `metrics`, `conditions`, and `entities` as allowed by each section schema.
- Assembled extraction sections include flattened `units[]` for downstream validation and rendering.
- `section_type` exists only on `sections`, never on individual units.
- Section anchors use `anchor_id`, not inline `anchor` objects.
- `covers_entries[]` is the authoritative trace from sections back to plan items.
- Each unit ID must be defined exactly once in its home section. Metrics may reference external unit IDs through `subject_id`; Claims may reference external unit IDs through `target_ids`.
- Every `Claim` and `Metric` must have non-empty provenance.
- Every `Metric` needs `subject_id`, `context_ids`, and provenance; experiment metrics require non-empty `context_ids`; analysis metrics require empty `context_ids`. `Metric.evaluated_on` is an optional list of section-local `dataset`/`benchmark` Entity IDs the metric was measured on (the structured dataset link); omit it when no such local Entity exists.
- Extraction output has no top-level `cross_section_links`; all explicit links are section-local.
- `Method.components[]` is a denormalized projection of section-local `Method --part_of--> Method` links, present only in assembled output. The extraction schema no longer exposes a component field; extractors express composition solely with `part_of` links and assembly (`_reconcile_method_components`) rebuilds `components[]` from them.
- `Method` optional fields (omitted entirely when unsupported, never invented): `inputs[]`, `outputs[]`, `formulas[]` (each `{name, expression}`), and `objective_function` (`{expression, description}`). Only `name`, `method_kind`, `description`, and `implementation_notes` are required. When present, every `formulas[]` entry and `objective_function` must carry a non-empty `expression`.
- Exactly one method plan item is `is_root: true`, document-level (across all method section plans, not per section). `normalize_planning_item_ids` backfills it when the planner omits it and demotes extras, so a missing root no longer hard-fails planning.
- Assembly performs lossy-but-safe repairs and logs each to `extraction_notes.uncertain_assignments`: `_reconcile_metric_subjects` aligns each experiment `Metric.subject_id` with the plan's `evaluates` target (falling back to the root method when missing or dangling); `_drop_empty_sections` removes unit-less (often over-split) sections; `_normalize_provenance_markers` collapses `§N.M` sources to their real top-level `§N` (appendix/table markers are left to fail); `_drop_invalid_links` removes link-matrix violations; `_repair_section_anchors` re-points non-local anchors; `_reconcile_covers_entries` prunes `covers_entries` that no longer resolve to a unit (uncovered must-items then resurface in `extraction_notes.uncovered_items`).
- IR version: `section-ir-0.6`.

Allowed unit types:

`Document`, `Entity`, `Method`, `Claim`, `Context`, `Condition`, `Metric`

## Context vs. Condition

- `Context` (argumentative premise): `context_kind ∈ {background, gap, motivation, challenge, assumption}`, fields `{context_kind, description}`.
- `Condition` (operational constraint): `condition_kind ∈ {experimental, boundary, evaluation_setup, hyperparameter}`, fields `{condition_kind, description}`.

Archived legacy types such as `Relation`, `Category`, `SystemModel`, `MethodArtifact`, `Proposition`, and `RoleBinding` are not valid in active section-IR output.

## Link Relations

Allowed link relations:

`supports`, `part_of`, `compares_to`

Follow the type matrix in `docs/section-ir-design.md` and `prompts/section-extraction/section-extraction-pass.md`. (`occurs_under` was removed in `section-ir-0.6`; the 5-section partition leaves no section able to co-locate a valid source and target for it.)

## Test Corpus

`tests/papers/1-5.md` contain real papers formatted in Markdown with `[§N]` section markers.

Current smoke-test defaults:

- Paper 4: "Attention Is All You Need"
- Paper 5: "Deep Residual Learning"

## Test Harness

Unit tests:

```bash
.venv/bin/python -m unittest tests.test_section_pipeline
```

LLM smoke test:

```bash
.venv/bin/python tests/test_section_extraction.py --papers 4 5
```

Environment variables:

- `API_KEY` or `API-KEY` is loaded from `.env`
- `MODEL` defaults to `gemini-3-flash-preview`
- `BASE_URL` defaults to `http://35.220.164.252:3888/v1`

If the primary base URL is unreachable, retry the smoke test with:

```bash
.venv/bin/python tests/test_section_extraction.py --papers 4 5 --base-url http://34.13.73.248:3888/v1
```

Outputs are written to `tests/section-extraction-outputs/`.

## Rendering

Render an extraction JSON to HTML:

```bash
python tools/render_extraction.py tests/section-extraction-outputs/paper4_extraction.json
```

The renderer is schema-aware for `anchor_id` sections and colors units by section membership.

## Archived Material

Historical code, design discussions, plans, and legacy utilities live in `archive/`. Subdirectories: `legacy-paradigm-ir/`, `docs/`, `discussions/`, `plans/`, `issues/`, `legacy-tests/`, `legacy-prompts/`.

Do not treat archived material as active implementation guidance.
