# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository implements and documents a **4-section scientific literature extraction pipeline** (section-ir-0.7).

The active system extracts a paper's argumentative spine into section-IR:

`context and gap -> claim -> method -> evidence`

`evidence` is the merged experiment+analysis section: it carries both what was measured and what those measurements mean.

## Active Architecture

The pipeline is **three-stage** (`node census -> relation pass -> content fill`):

1. **Node census (stage A)**: `prompts/section-extraction/node-census.md`
   - One full-paper call producing `spine_summary` and a flat `nodes[]` list of every load-bearing node — with **no relations**.
   - Each node carries a single granular `role` drawn from four search clusters (the guiding principle "trace the method's life"): **the_method** (`contribution`, `component`), **prior_art** (`builds_on`, `compared_against`), **testbed** (`dataset`, `benchmark`, `task`), **yardsticks** (`metric`). The node's coarse `type` (`Method`/`Entity`/`Metric`), Entity class, and document root are all **derived from `role`** — the census commits to one axis, not three. The `node_id` prefix (`mth:`/`ent:`/`met:`) follows from the role's type and is reused verbatim as the final unit id; each node also has a `salience` (`must`/`should`).
   - Two scoping rules: a **named model is a Method** (`builds_on`/`compared_against`), never a testbed node; **apparatus is not a node** (hardware and metric-scoring models like CLIP are dropped — the scoring model lives in the metric's gloss).
   - **Baselines are captured in full** (policy reversed 2026-05-26): every system the paper compares against is a `compared_against` Method node (including black-box, score-only baselines), materialized as a lightweight Method unit in the method section, carrying a `compares_to` edge to the contribution; its number is a row in the relevant Metric's `scores[]` (the `variant` names the system). The comparison is thus captured structurally (edge) and quantitatively (score row). Baselines are never Entities.
   - `normalize_census_nodes` derives `type` from `role`, re-prefixes ids, dedups, and ensures exactly one `contribution` (promoting the first must-method when none, demoting extras to `component`); `validate_census` is the stage-A contract.

2. **Relation pass (stage B)**: `prompts/section-extraction/relation-pass.md`
   - One call receiving the full paper plus the complete flat node list. It establishes the structural entity↔entity edges (`part_of`, `compares_to`, `evaluates`, `measured_on`) with the whole node set in view, so cross-section composition and metric-subject binding need no forward references and no reconcile crutches.

3. **Content fill (stage C)**: `prompts/section-extraction/section-extraction-pass.md`
   - `section-extraction-pass.md` is a **slim shared core**: only the rules common to every section (identifiers, provenance format, the output envelope, universal hard constraints). It is byte-identical across all section calls, and the paper/spine_summary/node_registry/relations blocks precede `section_focus`, so the paper text stays in the cross-section prompt cache.
   - Four sections run in parallel (`context`, `claim`, `method`, `evidence`), each returning `section`. Each materializes the census nodes it owns (reusing `node_id` as the unit id) and creates its born units; `claim` and `evidence` also author claim-centric edges (`about`, `supports`) in a per-section `relations[]`.
   - Receives the injected schema constraint, `spine_summary`, `node_registry` (all nodes), the global `relations[]` from stage B, and `section_focus`.
   - Per-section modules (`prompts/section-extraction/section-modules/{context,claim,method,evidence}.md`) are **self-contained section contracts** injected as `section_focus`: allowed unit types and field contracts, the controlled vocabularies and relation subset used, a worked example, and section-specific rules — none of it duplicated in the shared core.

Assembly and validation run in Python (`section_pipeline.py`). The default entrypoint is `run_pipeline()`.

Every stage uses API-level structured output (`response_format` with `strict: True`). Stage schemas: `schemas/node-census-output.schema.json`, `schemas/relation-pass-output.schema.json`, and the per-section `schemas/section-{section}.schema.json`.

Content responses use typed unit arrays instead of a flat `units[]` array: `contexts` for context, `claims` for claim, `methods` for method, and `metrics`/`conditions`/`claims`/`entities` for evidence. `section_pipeline.py` flattens these typed arrays into `section["units"]` during assembly, and lifts each section's `relations[]` plus the stage-B edges into a single top-level `relations[]`.

Implementation entry point: `section_pipeline.py`.

Authoritative validation: Python `validate_section_ir()` in `section_pipeline.py` is the runtime contract.

Default section schemas: `schemas/section-context.schema.json`, `section-claim.schema.json`, `section-method.schema.json`, `section-evidence.schema.json`.

Regenerate all schemas (per-section + census + relation pass) with `python tools/generate_section_schemas.py`. They are generated from constants in `section_pipeline.py`; never hand-edit the JSON.

Per-section focus modules: `prompts/section-extraction/section-modules/context.md`, `claim.md`, `method.md`, `evidence.md`.

Design reference: `docs/section-ir-0.7-redesign.md` (full spec); `docs/section-ir-design.md` (legacy 0.6).

## Section-IR Rules

- Units have flat structure — type-specific fields sit directly on the unit, no `payload` wrapper.
- Raw content responses group units into typed arrays: `contexts`, `claims`, `methods`, `metrics`, `conditions`, and `entities` as allowed by each section schema.
- Assembled extraction sections include flattened `units[]` for downstream validation and rendering.
- `section_type` exists only on `sections`, never on individual units.
- Section anchors use `anchor_id`, not inline `anchor` objects.
- Top-level keys are `document`, `sections`, `relations`, `extraction_notes`. `relations[]` is the single global edge list; sections no longer carry `links`.
- `covers_entries[]` is the authoritative trace from a section back to the census nodes it materialized. Assembly derives it deterministically (census node_id ∩ section unit ids), so the model does not echo it.
- Each unit ID is defined exactly once. A census `node_id` is reused verbatim as the unit id when a section materializes it. Cross-unit references are edges in the global `relations[]`, not unit fields — the only top-level reference-list unit field is `Metric.setting_ids` (local Setting scoping); the only other in-unit references are the per-row scalar `scores[].system_id`/`scores[].setting_id`.
- Every `Claim` and `Metric` must have non-empty provenance.
- Every `Metric` needs `name`, `unit`, non-empty `scores`, and `setting_ids`. `scores[]` holds one row per system **per split** reported under the metric — the method family's own variants **and** every compared-against baseline. Each row is `{variant, value, variance, system_id, setting_id}`: `variant` is the paper's label; `system_id` references the **Method unit** the row reports (the contribution variant or the baseline — `""` only when no node represents it), turning the row into a structured comparison instead of a free-text join; `setting_id` references the **local Setting** the row was measured under, used when one metric spans several splits (e.g. EN-DE + EN-FR rows under one BLEU metric) so a dataset/split column is never collapsed to one number per system. A non-empty `system_id` must resolve to a Method (globally); a non-empty `setting_id` must resolve to a section-local Setting. `setting_ids` (when non-empty) must point to section-local `Setting` units; it may be empty (an ablation metric carries none, a deployable metric is normally scoped by one). The metric→method link is the `evaluates` relation (pointed only at the contribution/component it measures — **never** a `compared_against` baseline) and the metric→dataset link is the `measured_on` relation, both in the global `relations[]` — `Metric` no longer has `subject_id` or `evaluated_on` fields.
- `Claim` has no `target_ids` field; what a claim is about is the `about` relation in `relations[]`.
- The controlled vocabularies are **scoped to AI/ML literature** (the type cleanup pruned what never fired on the corpus). `Claim` carries only `statement` + `claim_kind ∈ {descriptive, mechanistic, comparative, modeling, ablation_finding, failure_mode}` — the monotone `polarity`/`novelty`/`epistemic_status` fields were removed, and `causal`/`correlational` dropped. `method_kind ∈ {algorithm, model_architecture, training_strategy, objective_function}` (`protocol`/`software_system` dropped). `Metric` dropped the monotone `value_type`. `Entity.entity_class ∈ {dataset, benchmark, task}` (`model` is a Method now; `hardware` is apparatus, not a node).
- `Method` has no `components` field; composition is the `part_of` relation in `relations[]` (established by the relation pass over the full node set, so cross-section composition is captured without reconcile crutches).
- `Method` optional fields (omitted entirely when unsupported, never invented): `inputs[]`, `outputs[]`, `formulas[]` (each `{name, expression, symbols[]}`), and `objective_function` (`{expression, description, symbols[]}`). Each `symbols[]` entry is `{symbol, description}` glossing one token of the equation; the array may be empty when the expression introduces no symbols. Only `name`, `method_kind`, `description`, and `implementation_notes` are required. When present, every `formulas[]` entry and `objective_function` must carry a non-empty `expression`, and each `symbols[]` entry must carry a non-empty `symbol` and `description`.
- Exactly one census node has `role: contribution` (the document-level root method). `normalize_census_nodes` promotes the first must-method when none is tagged and demotes extras to `component`, so a missing contribution no longer hard-fails the census.
- Assembly merges the stage-B relations with each content section's `relations[]` into the global list, then performs lossy-but-safe repairs logged to `extraction_notes.uncertain_assignments`: `_sanitize_unit_text` strips C0 control characters (incl. the NULL bytes some models emit for `·`/`×`) from unit string values; `_dedup_entities` merges same-name Entities (rewriting relation endpoints); `_dedup_unit_ids` drops later duplicate definitions; `_drop_empty_sections` removes unit-less sections; `_normalize_provenance_markers` collapses `§N.M` to top-level `§N`; `_repair_section_anchors` re-points non-local anchors; `_repair_score_refs` blanks dangling/wrong-type `scores[].system_id`/`setting_id`; `_dedup_relations`/`_drop_dangling_relations`/`_drop_invalid_relations` clean the global edge list against the relation matrix once the full unit set is known; `_drop_baseline_evaluates` drops `evaluates` edges pointing at a `compared_against` baseline (census-driven, so a metric's primary subject stays recoverable); `_assign_covers_entries` recomputes the census trace. Coverage is measured against census `must` nodes; an unmaterialized must-node surfaces in `extraction_notes.uncovered_items`.
- IR version: `section-ir-0.7`. `extraction_notes.input_mode` is `node_census_pipeline`.

Allowed unit types:

`Document`, `Entity`, `Method`, `Claim`, `Context`, `Setting`, `Metric`

`Method`, `Entity`, and `Metric` are census nodes (role-tagged in stage A, with `type` derived from `role`); `Context`, `Setting`, and `Claim` are born during content fill.

## Context vs. Setting

- `Context` (argumentative premise): `context_kind ∈ {background, gap, motivation, challenge, assumption}`, fields `{context_kind, description}`.
- `Setting` (operational constraint): fields `{setting_kind, description}` — a single sentence naming the concrete setup that scopes a metric. `setting_kind ∈ {data_split, inference_protocol, training_config, ensembling, population}` names which axis it constrains (reintroduced 2026-05-27: the old monotone `condition_kind` was always `evaluation_setup`, but Settings are genuinely heterogeneous — a `training_config`/`ensembling` setup is not interchangeable with a `data_split`, and an ensemble number is not a fair peer of a single-model one). A `data_split` Setting per split is also what lets a multi-split metric's score rows carry a `setting_id`.

Archived legacy types such as `Relation`, `Category`, `SystemModel`, `MethodArtifact`, `Proposition`, and `RoleBinding` are not valid in active section-IR output.

## Relations (global)

`relations[]` is top-level and global; every edge resolves to a unit defined anywhere. Allowed relations and their type matrix:

| relation | source → target | authored by |
|---|---|---|
| `part_of` | {Method, Entity} → {Method, Entity} | relation pass (B) |
| `compares_to` | {Method, Entity, Metric} → same | relation pass (B) |
| `evaluates` | Metric → Method | relation pass (B) |
| `measured_on` | Metric → Entity (dataset/benchmark) | relation pass (B) |
| `about` | Claim → {Method, Entity, Metric} | content (claim/evidence) |
| `supports` | {Metric, Claim} → Claim | content (claim/evidence) |

The matrix lives in `RELATION_MATRIX` in `section_pipeline.py`. (`occurs_under` was removed in 0.6; `subject_id`/`target_ids`/`evaluated_on`/`components` were promoted to global edges in 0.7.)

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
