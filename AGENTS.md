# AGENTS.md

This file provides guidance to coding agents (e.g. Codex) when working with code in this repository. It mirrors `CLAUDE.md` — keep the two in sync.

## Project Overview

This repository implements and documents a **3-section scientific literature extraction pipeline** (section-ir-0.9).

The active system extracts a paper as a **scientific-discovery throughline** into section-IR:

`problem -> method -> evidence`

`evidence` is the merged experiment+analysis section: it carries both what was measured and what those measurements mean, and it hosts the headline contribution finding.

## Active Architecture

The pipeline is **three-stage** (`node census -> relation pass -> content fill`):

1. **Node census (stage A)**: `prompts/section-extraction/node-census.md`
   - One full-paper call producing `spine_summary` and a flat `nodes[]` list of every load-bearing node — with **no relations**.
   - Each node carries a single granular `role` drawn from four search clusters (the guiding principle "trace the method's life"): **the_method** (`contribution`, `component`), **prior_art** (`builds_on`, `compared_against`), **testbed** (`dataset`, `benchmark`, `task`), **yardsticks** (`metric`). The node's coarse `type` (`Method`/`ExperimentSetup`/`Measure`) and document root are **derived from `role`** — the census commits to one axis, and the `role` is carried onto the materialized unit as its fine-grained differentia (0.9: `type` = generic scope, `role` = sub-axis). The `node_id` prefix (`mth:`/`exp:`/`mea:`) follows from the role's type and is reused verbatim as the final unit id; each node also has a `salience` (`must`/`should`).
   - Two scoping rules: a **named model is a Method** (`builds_on`/`compared_against`), never a testbed node; **apparatus is not a node** (hardware and metric-scoring models like CLIP are dropped — the scoring model lives in the measure's gloss).
   - **Baselines are captured in full** (policy reversed 2026-05-26): every system the paper compares against is a `compared_against` Method node (including black-box, score-only baselines), materialized as a lightweight Method unit in the method section, carrying a `compares_to` edge to the contribution; its number is a row in the relevant Measure's `scores[]` (the `variant` names the system). The comparison is thus captured structurally (edge) and quantitatively (score row). Baselines are never ExperimentSetups.
   - `normalize_census_nodes` derives `type` from `role`, re-prefixes ids, dedups, and ensures exactly one `contribution` (promoting the first must-method when none, demoting extras to `component`); `validate_census` is the stage-A contract.

2. **Relation pass (stage B)**: `prompts/section-extraction/relation-pass.md`
   - One call receiving the full paper plus the complete flat node list. It establishes the structural node↔node edges (`part_of`, `compares_to`, `evaluates`) with the whole node set in view, so cross-section composition and measure-subject binding need no forward references and no reconcile crutches. (The metric→dataset edge `measured_on` was removed in 0.9 — a Measure binds to its dataset/split via each score row's `setup_id`, not a global edge.)

3. **Content fill (stage C)**: `prompts/section-extraction/section-extraction-pass.md`
   - `section-extraction-pass.md` is a **slim shared core**: only the rules common to every section (identifiers, provenance format, the output envelope, universal hard constraints). It is byte-identical across all section calls, and the paper/spine_summary/node_registry/relations blocks precede `section_focus`, so the paper text stays in the cross-section prompt cache.
   - Three sections run in parallel (`problem`, `method`, `evidence`), each returning `section`. Each materializes the census nodes it owns (reusing `node_id` as the unit id) and creates its born units; `evidence` authors finding-centric edges (`about`, `supports`) and `problem` authors `motivates` (born Problem → the census Method/ExperimentSetup it justifies) in a per-section `relations[]`. The closing `resolves` edge (Finding → Problem) joins two units born in different parallel sections, so assembly synthesizes it (`_assign_resolves`).
   - Receives the injected schema constraint, `spine_summary`, `node_registry` (all nodes), the global `relations[]` from stage B, and `section_focus`.
   - Per-section modules (`prompts/section-extraction/section-modules/{problem,method,evidence}.md`) are **self-contained section contracts** injected as `section_focus`: allowed unit types and field contracts, the controlled vocabularies and relation subset used, a worked example, and section-specific rules — none of it duplicated in the shared core.

Assembly and validation run in Python (`section_pipeline.py`). The default entrypoint is `run_pipeline()`.

Every stage uses API-level structured output (`response_format` with `strict: True`). Stage schemas: `schemas/node-census-output.schema.json`, `schemas/relation-pass-output.schema.json`, and the per-section `schemas/section-{section}.schema.json`.

Content responses use typed unit arrays instead of a flat `units[]` array: `problems` for problem, `methods` for method, and `measures`/`experiment_setups`/`findings` for evidence. `section_pipeline.py` flattens these typed arrays into `section["units"]` during assembly, and lifts each section's `relations[]` plus the stage-B edges (and the synthesized `resolves` edges) into a single top-level `relations[]`.

Implementation entry point: `section_pipeline.py`.

Authoritative validation: Python `validate_section_ir()` in `section_pipeline.py` is the runtime contract.

Default section schemas: `schemas/section-problem.schema.json`, `section-method.schema.json`, `section-evidence.schema.json`.

Regenerate all schemas (per-section + census + relation pass) with `python tools/generate_section_schemas.py`. They are generated from constants in `section_pipeline.py`; never hand-edit the JSON.

Per-section focus modules: `prompts/section-extraction/section-modules/context.md`, `claim.md`, `method.md`, `evidence.md`.

Design reference: `docs/section-ir-0.9-redesign.md` (0.9 two-level type/role taxonomy — current); `docs/section-ir-0.8-redesign.md` (0.8 spine delta); `docs/section-ir-0.7-redesign.md` (0.7 spec); `docs/section-ir-design.md` (legacy 0.6).

## Section-IR Rules

- Units have flat structure — type-specific fields sit directly on the unit, no `payload` wrapper.
- Raw content responses group units into typed arrays: `problems`, `methods`, `measures`, `experiment_setups`, and `findings` as allowed by each section schema.
- Assembled extraction sections include flattened `units[]` for downstream validation and rendering.
- `section_type` exists only on `sections`, never on individual units.
- Section anchors use `anchor_id`, not inline `anchor` objects.
- Top-level keys are `document`, `sections`, `relations`, `extraction_notes`. `relations[]` is the single global edge list; sections no longer carry `links`.
- `covers_entries[]` is the authoritative trace from a section back to the census nodes it materialized. Assembly derives it deterministically (census node_id ∩ section unit ids), so the model does not echo it.
- Each unit ID is defined exactly once. A census `node_id` is reused verbatim as the unit id when a section materializes it. Cross-unit references are edges in the global `relations[]`, not unit fields — the only remaining reference-list unit field is `Measure.setup_ids` (local ExperimentSetup scoping).
- Every `Finding` and `Measure` must have non-empty provenance.
- Every `Measure` needs `name`, `unit`, non-empty `scores`, and `setup_ids`. `scores[]` holds one row per system **per split** reported under the measure — the method family's own variants **and** every compared-against baseline. Each row is `{variant, value, variance, system_id, setup_id}`: `system_id` references the **Method unit** the row reports (the contribution variant or a baseline; `""` when no node represents it), and `setup_id` references the **local ExperimentSetup** the row was measured on (the dataset/split) — this is how a Measure binds to its data. `setup_ids` (when non-empty) must point to section-local `ExperimentSetup` units; it may be empty (an ablation measure carries none, a deployable measure is normally scoped by one). The measure→method link is the `evaluates` relation in the global `relations[]` (never pointed at a baseline) — `Measure` has no `subject_id`/`evaluated_on` fields. The measure→dataset link is **not** a global edge: `measured_on` was removed in 0.9, replaced by the per-row `setup_id` → ExperimentSetup.
- `Finding` has no `target_ids` field; what a finding is about is the `about` relation in `relations[]`.
- The controlled vocabularies are **scoped to AI/ML literature**. 0.9 unifies the old scattered `entity_class`/`setting_kind`/`claim_kind`/`doc_role` fields into a single per-type `role` axis. `Finding` carries `statement` + `role ∈ {descriptive, mechanistic, comparative, modeling, ablation_finding, failure_mode}` — the monotone `polarity`/`novelty`/`epistemic_status` were removed, `causal`/`correlational` dropped. `Method.method_kind ∈ {algorithm, model_architecture, training_strategy, objective_function}` survives as an **optional** structural attribute orthogonal to the argumentative `role` (`protocol`/`software_system` dropped). `Measure` dropped the monotone `value_type` and carries no `role`. `ExperimentSetup.role ∈ {dataset, benchmark, task}` (substrate) ∪ `{data_split, inference_protocol, training_config, ensembling, population}` (configuration). `Document.role ∈ {research_article, review, meta_analysis, methodology, benchmark_survey}`.
- `Method` has no `components` field; composition is the `part_of` relation in `relations[]` (established by the relation pass over the full node set, so cross-section composition is captured without reconcile crutches).
- `Method` optional fields (omitted entirely when unsupported, never invented): `inputs[]`, `outputs[]`, `formulas[]` (each `{name, expression, symbols[]}`), and `objective_function` (`{expression, description, symbols[]}`). Each `symbols[]` entry is `{symbol, description}` glossing one token of the equation; the array may be empty when the expression introduces no symbols. Only `name`, `method_kind`, `description`, and `implementation_notes` are required. When present, every `formulas[]` entry and `objective_function` must carry a non-empty `expression`, and each `symbols[]` entry must carry a non-empty `symbol` and `description`. Only `role`, `name`, `description`, and `implementation_notes` are required on a Method; `method_kind` is optional.
- Exactly one census node has `role: contribution` (the document-level root method). `normalize_census_nodes` promotes the first must-method when none is tagged and demotes extras to `component`, so a missing contribution no longer hard-fails the census.
- Assembly merges the stage-B relations with each content section's `relations[]` into the global list, then performs lossy-but-safe repairs logged to `extraction_notes.uncertain_assignments`: `_assign_roles_from_census` stamps the census role onto materialized Method/ExperimentSetup units; `_dedup_experiment_setups` merges same-name ExperimentSetups (rewriting relation endpoints); `_dedup_unit_ids` drops later duplicate definitions; `_drop_empty_sections` removes unit-less sections; `_normalize_provenance_markers` collapses `§N.M` to top-level `§N`; `_repair_section_anchors` re-points non-local anchors; `_repair_score_refs` blanks dangling per-row `system_id`/`setup_id`; `_dedup_relations`/`_drop_dangling_relations`/`_drop_invalid_relations`/`_drop_baseline_evaluates` clean the global edge list against the relation matrix once the full unit set is known; `_assign_covers_entries` recomputes the census trace. Coverage is measured against census `must` nodes; an unmaterialized must-node surfaces in `extraction_notes.uncovered_items`.
- IR version: `section-ir-0.9`. `extraction_notes.input_mode` is `node_census_pipeline`.

Allowed unit types:

`Document`, `Problem`, `Method`, `ExperimentSetup`, `Measure`, `Finding`

`Method`, the substrate `ExperimentSetup` roles (`dataset`/`benchmark`/`task`), and `Measure` are census nodes (role-tagged in stage A, with `type` derived from `role`); `Problem`, `Finding`, and the configuration `ExperimentSetup` roles are born during content fill.

## Problem vs. ExperimentSetup

- `Problem` (the research problem): fields `{description}` — one or two sentences naming the unresolved question. **One trunk** per paper; born in the problem section and authoring a `motivates` edge to the contribution.
- `ExperimentSetup` (old `Entity ⊎ Setting`, merged in 0.9): fields `{role, name, description}`. Its `role` splits one "Design an Experiment" step into a **substrate** half (`dataset`/`benchmark`/`task`: census-discovered, external and citeable) and a **configuration** half (`data_split`/`inference_protocol`/`training_config`/`ensembling`/`population`: paper-local, born during content fill, materialized only when it scopes a Measure). Hardware/global hyperparameters that scope no Measure are not captured.

Archived/retired types — `Relation`, `Category`, `SystemModel`, `MethodArtifact`, `Proposition`, `RoleBinding`, and the renamed 0.8 names `Entity`/`Setting`/`Metric`/`Claim` — are not valid in active section-IR output (the 0.8 names are in `FORBIDDEN_UNIT_TYPES`).

## Relations (global)

`relations[]` is top-level and global; every edge resolves to a unit defined anywhere. Allowed relations and their type matrix:

| relation | source → target | authored by |
|---|---|---|
| `part_of` | {Method, ExperimentSetup} → {Method, ExperimentSetup} | relation pass (B) |
| `compares_to` | {Method, ExperimentSetup, Measure} → same | relation pass (B) |
| `evaluates` | Measure → Method | relation pass (B) |
| `about` | Finding → {Method, ExperimentSetup, Measure} | content (evidence) |
| `supports` | {Measure, Finding} → Finding | content (evidence) |
| `motivates` | Problem → {Method, ExperimentSetup} | content (problem) |
| `resolves` | Finding → Problem | assembly (synthesized) |

The matrix lives in `RELATION_MATRIX` in `section_pipeline.py` (stage-B set is `part_of`/`compares_to`/`evaluates`). (`occurs_under` was removed in 0.6; `subject_id`/`target_ids`/`evaluated_on`/`components` were promoted to global edges in 0.7; `measured_on` was removed in 0.9 — the measure→dataset link is now the score row's `setup_id` → ExperimentSetup.)

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
