# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository implements and documents a **3-section scientific literature extraction pipeline** (section-ir-0.9).

The active system extracts a paper as a **scientific-discovery throughline** into section-IR:

`problem -> method -> evidence`

`problem` is the single research problem the paper addresses (the old multi-tag `context` section, collapsed to one trunk). `method` is the technical apparatus. `evidence` is the merged experiment+analysis section: it carries both what was measured and what those measurements mean — and it now also hosts the **headline contribution finding** (the answer the evidence establishes), so there is no separate `claim` section. The discovery arc closes with a synthesized `resolves` edge from that headline finding back to the problem, and the one-sentence contribution is also lifted onto the Document as `thesis`.

## Active Architecture

The pipeline is **three-stage** (`node census -> relation pass -> content fill`):

1. **Node census (stage A)**: `prompts/section-extraction/node-census.md`
   - One full-paper call producing `spine_summary` and a flat `nodes[]` list of every load-bearing node — with **no relations**.
   - Each node carries a single granular `role` drawn from four search clusters (the guiding principle "trace the method's life"): **the_method** (`contribution`, `component`), **prior_art** (`builds_on`, `compared_against`), **testbed** (`dataset`, `benchmark`, `task`), **yardsticks** (`metric`). The node's coarse `type` (`Method`/`ExperimentSetup`/`Measure`) and document root are **derived from `role`** — the census commits to one axis, and the `role` is then carried onto the materialized unit as its fine-grained differentia (0.9: `type` = generic scope, `role` = sub-axis). The `node_id` prefix (`mth:`/`exp:`/`mea:`) follows from the role's type and is reused verbatim as the final unit id; each node also has a `salience` (`must`/`should`).
   - Two scoping rules: a **named model is a Method** (`builds_on`/`compared_against`), never a testbed node; **apparatus is not a node** (hardware and metric-scoring models like CLIP are dropped — the scoring model lives in the measure's gloss).
   - **Baselines are captured in full** (policy reversed 2026-05-26): every system the paper compares against is a `compared_against` Method node (including black-box, score-only baselines), materialized as a lightweight Method unit in the method section, carrying a `compares_to` edge to the contribution; its number is a row in the relevant Measure's `scores[]` (the `variant` names the system). The comparison is thus captured structurally (edge) and quantitatively (score row). Baselines are never ExperimentSetups.
   - `normalize_census_nodes` derives `type` from `role`, re-prefixes ids, dedups, and ensures **at least one** root (promoting the strongest node when none is tagged); a paper with **co-equal primary deliverables** (a method *and* a benchmark, or two independent algorithms — FG-7) keeps **every `must` root**, demoting only weaker `should` mis-tags, so the relation pass can link them with `co_contribution`. `validate_census` is the stage-A contract (requires ≥1 root, not exactly one).
   - Each prior-art/testbed node also carries `cite_keys` — the in-text bibliography marker(s) it is cited as (`["31"]` for a results-table row "GNMT + RL [31]"; `[]` for the contribution, components, tasks, and measures). This is the deterministic join key for **reference linking**: `reconcile_reference_units` (run after content fill) fills each reference's `relation.provides_unit_ids` by matching the reference `id` to a materialized node's `cite_keys` first (exact, grounded in the paper's own citation, so it survives name mismatches like reference "GNMT" → unit "GNMT + RL"), then falls back to a unique `provides_name`↔unit-name match. Since `node_id == unit_id`, the link resolves straight to the method/evidence unit. The same `cite_keys` list is also stamped onto the materialized Method/ExperimentSetup unit (`_assign_roles_from_census`) so a consumer reading the assembled extraction alone can join a unit to the bibliography — and, across papers, a baseline to the paper that introduced it; it lands only on externally-cited prior-art/testbed units (empty lists are not stamped, so the contribution/components/tasks/measures carry no `cite_keys` field).

2. **Relation pass (stage B)**: `prompts/section-extraction/relation-pass.md`
   - One call receiving the full paper plus the complete flat node list. It establishes the structural node↔node edges (`part_of`, `compares_to`, `evaluates`) with the whole node set in view, so cross-section composition and measure-subject binding need no forward references and no reconcile crutches. (The metric→dataset edge `measured_on` was removed in 0.9 — a Measure binds to its dataset/split via each score row's `setup_id`, not a global edge.)

3. **Content fill (stage C)**: `prompts/section-extraction/section-extraction-pass.md`
   - `section-extraction-pass.md` is a **slim shared core**: only the rules common to every section (identifiers, provenance format, the output envelope, universal hard constraints). It is byte-identical across all section calls, and the paper/spine_summary/node_registry/relations blocks precede `section_focus`, so the paper text stays in the cross-section prompt cache.
   - Three sections run in parallel (`problem`, `method`, `evidence`), each returning `section`. Each materializes the census nodes it owns (reusing `node_id` as the unit id) and creates its born units; `evidence` authors finding-centric edges (`about`, `supports`) and `problem` authors `motivates` (born Problem → the census Method/ExperimentSetup it justifies) in a per-section `relations[]`. The closing `resolves` edge (Finding → Problem) is **not** authored by any section — it joins two units born in different parallel sections, so assembly synthesizes it (`_assign_resolves`) from the contribution-node join.
   - Receives the injected schema constraint, `spine_summary`, `node_registry` (all nodes), the global `relations[]` from stage B, and `section_focus`.
   - Per-section modules (`prompts/section-extraction/section-modules/{problem,method,evidence}.md`) are **self-contained section contracts** injected as `section_focus`: allowed unit types and field contracts, the controlled vocabularies and relation subset used, a worked example, and section-specific rules — none of it duplicated in the shared core.

Assembly and validation run in Python (`section_pipeline.py`). The default entrypoint is `run_pipeline()`.

Structured output is **model-adaptive** (see "Model compatibility" below). For models that support strict JSON-schema decoding (the Gemini/OpenAI-compatible proxy) every stage sends `response_format` with `strict: True`. For json_object-only models (official DeepSeek), `response_format` is `{"type": "json_object"}` and the same schema is rendered into the prompt as an OUTPUT FORMAT CONTRACT instead. Stage schemas: `schemas/node-census-output.schema.json`, `schemas/relation-pass-output.schema.json`, and the per-section `schemas/section-{section}.schema.json`.

Content responses use typed unit arrays instead of a flat `units[]` array: `problems` for problem, `methods` for method, and `measures`/`experiment_setups`/`findings` for evidence. `section_pipeline.py` flattens these typed arrays into `section["units"]` during assembly, and lifts each section's `relations[]` plus the stage-B edges (and the synthesized `resolves` edges) into a single top-level `relations[]`. The Document's `thesis` is filled from the census `spine_summary.central_contribution` during assembly (no extra LLM call).

Implementation entry point: `section_pipeline.py`.

Authoritative validation: Python `validate_section_ir()` in `section_pipeline.py` is the runtime contract.

Default section schemas: `schemas/section-problem.schema.json`, `section-method.schema.json`, `section-evidence.schema.json`.

Regenerate all schemas (per-section + census + relation pass) with `python tools/generate_section_schemas.py`. They are generated from constants in `section_pipeline.py`; never hand-edit the JSON.

Per-section focus modules: `prompts/section-extraction/section-modules/problem.md`, `method.md`, `evidence.md`.

Design reference: `docs/section-ir-0.9-redesign.md` (0.9 two-level type/role taxonomy — current); `docs/section-ir-0.8-redesign.md` (0.8 spine delta); `docs/section-ir-0.7-redesign.md` (0.7 spec); `docs/section-ir-design.md` (legacy 0.6).

## Section-IR Rules

- Units have flat structure — type-specific fields sit directly on the unit, no `payload` wrapper.
- Raw content responses group units into typed arrays: `problems`, `methods`, `measures`, `experiment_setups`, and `findings` as allowed by each section schema.
- Assembled extraction sections include flattened `units[]` for downstream validation and rendering.
- `section_type` exists only on `sections`, never on individual units.
- Section anchors use `anchor_id`, not inline `anchor` objects.
- Top-level keys are `document`, `sections`, `relations`, `extraction_notes`. `relations[]` is the single global edge list; sections no longer carry `links`.
- `covers_entries[]` is the authoritative trace from a section back to the census nodes it materialized. Assembly derives it deterministically (census node_id ∩ section unit ids), so the model does not echo it.
- Each unit ID is defined exactly once. A census `node_id` is reused verbatim as the unit id when a section materializes it. Cross-unit references are edges in the global `relations[]`, not unit fields — the only top-level reference-list unit field is `Measure.setup_ids` (local ExperimentSetup scoping); the only other in-unit references are the per-row scalar `scores[].system_id`/`scores[].setup_id`.
- Every `Finding` and `Measure` must have non-empty provenance.
- Every `Measure` needs `name`, `unit`, non-empty `scores`, and `setup_ids`. `scores[]` holds one row per system **per split** reported under the measure — the method family's own variants **and** every compared-against baseline. Each row is `{variant, value, variance, system_id, setup_id}`: `variant` is the paper's label; `system_id` references the **Method unit** the row reports (the contribution variant or the baseline — `""` only when no node represents it), turning the row into a structured comparison instead of a free-text join; `setup_id` references the **local ExperimentSetup** the row was measured under, used when one measure spans several splits (e.g. EN-DE + EN-FR rows under one BLEU measure) so a dataset/split column is never collapsed to one number per system. A non-empty `system_id` must resolve to a Method (globally); a non-empty `setup_id` must resolve to a section-local ExperimentSetup. `setup_ids` (when non-empty) must point to section-local `ExperimentSetup` units; it may be empty (an ablation measure carries none, a deployable measure is normally scoped by one). The measure→method link is the `evaluates` relation (pointed only at the contribution/component it measures — **never** a `compared_against` baseline), in the global `relations[]` — `Measure` no longer has `subject_id` or `evaluated_on` fields. The measure→dataset link is no longer a global edge (`measured_on` was removed in 0.9): a Measure binds to its dataset/split through each score row's `setup_id` → ExperimentSetup.
- `Finding` has no `target_ids` field; what a finding is about is the `about` relation in `relations[]`.
- The controlled vocabularies are **scoped to AI/ML literature** (the type cleanup pruned what never fired on the corpus). 0.9 unifies the old scattered `entity_class`/`setting_kind`/`claim_kind`/`doc_role` fields into a single per-type `role` axis (see "Two-level taxonomy" below). `Finding` carries only `statement` + `role ∈ {descriptive, mechanistic, comparative, modeling, ablation_finding, failure_mode}` (the old `claim_kind`) — the monotone `polarity`/`novelty`/`epistemic_status` fields were removed, and `causal`/`correlational` dropped. `Method.method_kind ∈ {algorithm, model_architecture, training_strategy, objective_function}` survives as an **optional** structural attribute orthogonal to the argumentative `role` (`protocol`/`software_system` dropped). `Measure` dropped the monotone `value_type` and carries no `role`. `ExperimentSetup.role ∈ {dataset, benchmark, task}` (the substrate; `model` is a Method now; `hardware` is apparatus, not a node) ∪ `{data_split, inference_protocol, training_config, ensembling, population}` (the configuration). `Document.role ∈ {research_article, review, meta_analysis, methodology, benchmark_survey}` (the old `doc_role`).
- `Method` has no `components` field; composition is the `part_of` relation in `relations[]` (established by the relation pass over the full node set, so cross-section composition is captured without reconcile crutches).
- `Method` optional fields (omitted entirely when unsupported, never invented): `inputs[]`, `outputs[]`, `formulas[]` (each `{name, expression, symbols[]}`), and `objective_function` (`{expression, description, symbols[]}`). Each `symbols[]` entry is `{symbol, description}` glossing one token of the equation; the array may be empty when the expression introduces no symbols. Only `name`, `method_kind`, `description`, and `implementation_notes` are required. When present, every `formulas[]` entry and `objective_function` must carry a non-empty `expression`, and each `symbols[]` entry must carry a non-empty `symbol` and `description`.
- At least one census node is a root — `role: contribution` (a Method deliverable) or `contribution_resource` (a dataset/benchmark deliverable). Normally exactly one, but a paper with **co-equal primary contributions** (FG-7) tags each as a root and they are linked by `co_contribution` in stage B. `normalize_census_nodes` promotes the strongest node when none is tagged, and when several are tagged keeps every `must` root (demoting only weaker `should` mis-tags), so a missing contribution no longer hard-fails the census and a genuine co-contribution is no longer flattened to `component`.
- Assembly merges the stage-B relations with each content section's `relations[]` into the global list, then performs lossy-but-safe repairs logged to `extraction_notes.uncertain_assignments`: `_sanitize_unit_text` strips C0 control characters (incl. the NULL bytes some models emit for `·`/`×`) from unit string values; `_assign_roles_from_census` stamps the census-committed `role` onto each materialized Method/ExperimentSetup unit (born units author their own role); `_dedup_experiment_setups` merges same-name ExperimentSetups (rewriting relation endpoints); `_dedup_unit_ids` drops later duplicate definitions; `_drop_empty_sections` removes unit-less sections; `_normalize_provenance_markers` collapses fine-grained subsection markers to their top-level parent — both numeric body sections (`§4.3`→`§4`) and lettered appendices (`§C.1`→`§C`); a bare lettered appendix (`§D`) is itself a valid provenance marker (`PROVENANCE_SOURCE_RE` accepts `§N` or `§X`), so appendix-sourced units no longer fail validation (table/figure refs like `§Table 3` still do); `_repair_section_anchors` re-points non-local anchors; `_repair_score_refs` blanks dangling/wrong-type `scores[].system_id`/`setup_id`; `_dedup_relations`/`_drop_dangling_relations`/`_drop_invalid_relations` clean the global edge list against the relation matrix once the full unit set is known; `_drop_baseline_evaluates` drops `evaluates` edges pointing at a `compared_against` baseline (census-driven, so a measure's primary subject stays recoverable); `_assign_covers_entries` recomputes the census trace. Coverage is measured against census `must` nodes; an unmaterialized must-node surfaces in `extraction_notes.uncovered_items`.
- The headline contribution finding is born in the **evidence** section (there is no `claim` section); it carries an `about` edge to the contribution method. Assembly synthesizes the closing `resolves` edge (that headline Finding → the Problem the contribution motivates) from the contribution-node join — no section authors it. The Document `thesis` is the census `spine_summary.central_contribution`, lifted on at assembly.
- IR version: `section-ir-0.10`. `extraction_notes.input_mode` is `node_census_pipeline`.

### section-ir-0.10 delta (field-design generalization, FG-1…FG-12)

0.10 is an additive generalization of 0.9 that stops the empirical-CV monoculture from coercing other genres. All changes are additive (0.9-shaped output stays structurally valid except the `ir_version` string). Summary of the field changes (each detailed in its section above/below):

- **FG-1 (non-Method contribution):** a benchmark/dataset deliverable is the census role `contribution_resource` (an `exp:` ExperimentSetup that *is* the document root and hosts its own score rows — no duplicate Method twin). `CONTRIBUTION_ROLES = {contribution, contribution_resource}`. Non-data resource/taxonomy deliverables stay a Method with `method_kind ∈ {resource, taxonomy}`.
- **FG-2 (theory home):** `method_kind += {theorem, lemma, bound, definition}` and `Finding.role += {theorem, lemma, bound}` (proven results are epistemically distinct, with no fabricated I/O — method.md suppresses inputs/outputs/formulas/objective_function for these); `scores[].value_kind ∈ {numeric, symbolic, asymptotic, qualitative, curve}` (a `PSPACE-complete`/`O(n^6)`/`2/Δ·logT` value is no longer a fake leaderboard number); census substrate roles `theoretical_setting`/`structural_class` (the regime/structural family a theorem holds under) with the `assumes` edge; `supports` relaxed to accept a Method source.
- **FG-3 (Document genre):** `Document.role` is derived from the materialized contribution by `_derive_document_role` (ExperimentSetup ⇒ `benchmark_survey`, taxonomy Method ⇒ `review`, else `research_article`) — no longer a hardcoded dead axis.
- **FG-4 (dependency edges):** `builds_on`/`uses` global edges (stage B) distinguish external dependency from internal `part_of`.
- **FG-6 (non-leaderboard eval):** optional score-row `opponent_id` (→Method, for pairwise/win-rate) and `judge_id` (→Method/ExperimentSetup, for LLM/human judges); optional Measure `objective_class ∈ {primary_quality, cost_efficiency, fairness, safety, robustness}` for multi-objective trade-offs.
- **FG-7 (co-equal contributions):** `co_contribution` edge (Method/ExperimentSetup ↔ same) replaces fake `part_of`; `_assign_resolves` fans the arc out across it. The **census now tags co-equal roots** (the single-root invariant was relaxed to ≥1; `validate_census`/`normalize_census_nodes`/`node-census.md`/`relation-pass.md` updated), so the edge actually fires on real papers — co-equal methods (013 Method Two/Three, 035 UCB-N/UCB-MaxN) and method+benchmark pairs (074 EMHI+MEPoser) emit `co_contribution`, the false `part_of` containment is gone, and the arc fans across both; single-contribution papers stay single-root (0/6 over-emission on a control batch).
- **FG-9/FG-5 (result-centric, A2 scope):** optional `spine_summary.headline_result` names the paper's headline established result, lifted onto `Document.headline_result`. (Full structural Finding-as-root — eliminating the hollow "Analysis" Method on result-centric papers — needs census Problem/Finding planning, deferred to A1.)
- **FG-10 D1 (silent-loss visibility):** a Measure dropped for empty scores is surfaced in `extraction_notes.uncovered_items` (not only the free-text `uncertain_assignments`).
- **FG-11 (Finding payload):** optional `Finding.polarity ∈ {positive, negative, neutral, mixed}` plus free-text `effect_size`/`scope`.
- **FG-12 (reference-role backfill):** `reconcile_reference_units` backfills contribution→target unit edges from reference roles (extends→`builds_on`, uses_method/uses_data→`uses`, baseline/contrast→`compares_to` with `stance`).

## Two-level taxonomy (type + role)

Every unit carries two classificatory axes (0.9): a generic **`type`** (a small, discipline-neutral scope anchored on the scientific method — *Identify a Problem → Design an Experiment → Collect Results → Construct a Conclusion*) and a fine-grained **`role`** (the AI/ML-specific differentia, unifying the old scattered `entity_class`/`setting_kind`/`claim_kind`/`doc_role` fields and lifting the census argumentative role onto Method). Swapping disciplines means swapping the per-type role vocabularies, never the `type` set. `role` is a first-class unit field; for census-materialized units (Method, substrate ExperimentSetup) assembly stamps it from the census (`_assign_roles_from_census`), born units author their own, and `Problem`/`Measure` carry none. The retired 0.8 names (`Entity`/`Setting`/`Metric`/`Claim`) are in `FORBIDDEN_UNIT_TYPES` so a stale prompt or model output fails loudly.

Allowed unit types (6):

`Document`, `Problem`, `Method`, `ExperimentSetup`, `Measure`, `Finding`

Renames from 0.8: `Metric → Measure` (prefix `met:` → `mea:`), `Claim → Finding` (`clm:` → `fnd:`), and `Entity ⊎ Setting → ExperimentSetup` (a merge of two types into one; `ent:`/`set:` → `exp:`). `Method`, `Problem`, `Document` are unchanged.

`Method`, the substrate `ExperimentSetup` roles (`dataset`/`benchmark`/`task`), and `Measure` are census nodes (role-tagged in stage A, with `type` derived from `role`); `Problem`, `Finding`, and the configuration `ExperimentSetup` roles are born during content fill.

Per-type `role` vocab (`ROLE_VOCAB_BY_TYPE`):

- `Method.role ∈ {contribution, component, builds_on, compared_against}` (the argumentative function; `method_kind` is a separate optional structural attribute).
- `ExperimentSetup.role ∈ {dataset, benchmark, task}` (substrate, census-discovered) ∪ `{data_split, inference_protocol, training_config, ensembling, population}` (configuration, content-born).
- `Finding.role ∈ {descriptive, mechanistic, comparative, modeling, ablation_finding, failure_mode}`.
- `Document.role ∈ {research_article, review, meta_analysis, methodology, benchmark_survey}`.
- `Problem` and `Measure` carry no `role`.

## Problem vs. ExperimentSetup configuration

- `Problem` (the research problem): fields `{description}` — one or two sentences naming the unresolved question or unmet need, with background folded into the prose. **One trunk** per paper; it replaced the old multi-tag `Context` (whose `context_kind ∈ {background, gap, motivation, challenge, assumption}` taxonomy was dropped as over-defined) and carries no `role`. It is born in the `problem` section and authors a `motivates` edge to the contribution.
- `ExperimentSetup` (the merged 0.9 type, old `Entity ⊎ Setting`): fields `{role, name, description}`. The `role` splits the type into two halves of one "Design an Experiment" step — a **substrate** half (`dataset`/`benchmark`/`task`: what you run on, census-discovered, external and citeable, carrying `cite_keys` on the census node) and a **configuration** half (`data_split`/`inference_protocol`/`training_config`/`ensembling`/`population`: under what conditions, paper-local, born during content fill and materialized only when it actually scopes a Measure). The merge collapses the old dataset(Entity)+split(Setting) duplication — a "dataset+split" is naturally one ExperimentSetup unit — and a `data_split` ExperimentSetup per split is what lets a multi-split measure's score rows carry a `setup_id` (so a dataset/split column is never collapsed to one number per system). Configuration that scopes **no** Measure (hardware, global hyperparameters) is still not captured ("apparatus is not a node").

Archived legacy types such as `Relation`, `Category`, `SystemModel`, `MethodArtifact`, `Proposition`, and `RoleBinding` are not valid in active section-IR output.

## Relations (global)

`relations[]` is top-level and global; every edge resolves to a unit defined anywhere. Allowed relations and their type matrix:

| relation | source → target | authored by |
|---|---|---|
| `part_of` | {Method, ExperimentSetup} → {Method, ExperimentSetup} | relation pass (B) |
| `builds_on` | {Method, ExperimentSetup} → same | relation pass (B) |
| `uses` | {Method, ExperimentSetup} → same | relation pass (B) |
| `assumes` | Method → ExperimentSetup | relation pass (B) |
| `co_contribution` | {Method, ExperimentSetup} → same | relation pass (B) |
| `compares_to` | {Method, ExperimentSetup, Measure} → same | relation pass (B) |
| `evaluates` | Measure → Method | relation pass (B) |
| `about` | Finding → {Method, ExperimentSetup, Measure} | content (evidence) |
| `supports` | {Measure, Finding, Method} → Finding | content (evidence) |
| `motivates` | Problem → {Method, ExperimentSetup} | content (problem) |
| `resolves` | Finding → Problem | assembly (synthesized) |

The matrix lives in `RELATION_MATRIX` in `section_pipeline.py` (11 relations in 0.10; stage-B set is `part_of`/`builds_on`/`uses`/`assumes`/`co_contribution`/`compares_to`/`evaluates` in `STAGE_B_RELATIONS`). (`occurs_under` was removed in 0.6; `subject_id`/`target_ids`/`evaluated_on`/`components` were promoted to global edges in 0.7; `measured_on` was removed in 0.9 — the measure→dataset link is now the score row's `setup_id` → ExperimentSetup, not a global edge.) **0.10 additions:** `builds_on` (the contribution extends external prior work — previously coerced onto `part_of`, FG-4) and `uses` (depends on an external method/data as a tool) distinguish external dependency from internal composition; `assumes` (a theorem/result Method holds under a `theoretical_setting`/`structural_class` ExperimentSetup, FG-2); `co_contribution` (two co-equal contributions of one paper — replaces fake `part_of`, FG-7); `supports` now also accepts a **Method** source so a theorem-Method supports its proven-result Finding (FG-2d). A self-loop (`source_id == target_id`) on any relation is dropped in assembly. `motivates` connects the discovery arc's first arrow — the Problem to the contribution it justifies — and survives parallel sectioning because the problem section authors it from a born Problem to a **census** node (visible in every section's `node_registry`), never to another born unit. `resolves` (added in 0.8) is the closing arrow — the headline Finding back to the Problem — but it joins two units born in *different* parallel sections, so no section can author it; assembly's `_assign_resolves` derives it deterministically (`Problem --motivates--> [contribution] <--about-- Finding` ⇒ `Finding --resolves--> Problem`). The stage-C relation enum is scoped per section in the schema generator's `STAGE_C_RELATIONS_BY_SECTION` (problem = `motivates`; evidence = `about`/`supports`); `resolves` appears in no stage-C enum.

## Test Corpus

The benchmark corpus lives in `tests/benchmark/NNN_*.md` (real papers, Markdown with `[§N]` markers) — this is what the `production/` batch path and `tests/deepseek-thinking-off/run_benchmark.py` read by numeric id (`014`, `028`, …).

The `tests/test_section_extraction.py` smoke harness instead reads `tests/papers/{id}.md` (the curated 1–5: "Attention Is All You Need", "Deep Residual Learning", …); that directory may be empty in a fresh checkout, so populate it or drive extraction from `tests/benchmark/` via the batch path.

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
- `MODEL` defaults to `deepseek-v4-pro` (run with reasoning/thinking **disabled** — see Model compatibility)
- `BASE_URL` defaults to `http://35.220.164.252:3888/v1`

If the primary base URL is unreachable, retry the smoke test with:

```bash
.venv/bin/python tests/test_section_extraction.py --papers 4 5 --base-url http://34.13.73.248:3888/v1
```

Outputs are written to `tests/section-extraction-outputs/`.

## Model compatibility (structured output)

**The default extraction model is `deepseek-v4-pro`**, served on the proxy `BASE_URL` and run with **reasoning/thinking disabled** — this is the only model the pipeline is run against. Thinking-off is enforced in the transport, not the model name: both `_call_llm` (sync) and `production/llm.py` (async) inject `extra_body={"thinking": {"type": "disabled"}}` on every call when `_is_deepseek_model(model)` (faster, and reasoning gave no quality lift on this corpus; gated to deepseek so other models are untouched). DeepSeek's output ceiling is smaller than the Gemini proxy's, so the section budget defaults to 32K (`production` `max_tokens`); a higher value 400s on `deepseek-v4-pro`. The single-shot planning/aux calls (census, relation pass, metadata, references) have a separate budget — `planning_max_tokens`, default 24K, tunable via `--planning-max-tokens` — kept below the section budget but above the old 16K so node-dense or reference-heavy papers don't truncate the (required) census and fail the whole paper. In `production/worker.py` every planning call goes through `_call_and_parse`, which re-issues the call (not just re-parses) on a malformed-JSON response, matching the content-section parse-retry so a single bad planning response doesn't sink the paper.

The pipeline detects the model's structured-output capability from the model name (`_structured_output_mode` in `section_pipeline.py`), mirroring the existing Gemini schema-sanitization pattern:

- **json_schema mode** (any model whose name is not `deepseek*`, e.g. the Gemini/OpenAI-compatible proxy): the per-stage JSON schema is sent in `response_format` with `strict: True`, so decoding is schema-constrained. Prompts are unchanged.
- **json_object mode** (**default** — `deepseek*`, i.e. the shipped default `deepseek-v4-pro` on the proxy, with official `deepseek-v4-pro` on `https://api.deepseek.com` as an alternative): DeepSeek does **not** accept `response_format: json_schema` (detection keys off the name, so `deepseek*` is json_object on either endpoint). So the pipeline sends `{"type": "json_object"}` and renders the *same* schema into the prompt as an OUTPUT FORMAT CONTRACT (`schema_to_prompt_spec`), spelling out keys, required/optional fields, enum values, and id patterns — the constraints strict decoding used to enforce. The contract is derived from the schema, so it never drifts. It is appended to the **system prompt** for the four single-shot calls (census, relation pass, metadata, references) and folded into **`<section_focus>`** for content sections, which keeps the cross-section prompt-cache prefix (paper/registry/relations) byte-identical. DeepSeek also rejects the proxy `prompt_cache_key`/`prompt_cache_retention` kwargs (its caching is automatic), so `_call_llm` omits them for `deepseek*`. DeepSeek `json_object` also requires the literal word "json" in the prompt — satisfied by the contract header and the existing "Output a single JSON object" instructions.

To run against official DeepSeek, point the smoke test at it (DeepSeek has a smaller output-token ceiling than the proxy, so lower `--max-tokens`/`--section-max-tokens` if a call 400s or truncates):

```bash
.venv/bin/python tests/test_section_extraction.py --papers 4 5 \
  --model deepseek-v4-pro --base-url https://api.deepseek.com \
  --max-tokens 8192 --section-max-tokens 8192
```

`API-KEY` in `.env` must be the DeepSeek key. The harness prints the detected `Structured output:` mode at startup.

The async batch path (`production/`, run via `python -m production <in> <out> --model deepseek-v4-pro --base-url https://api.deepseek.com --max-tokens 8192`) shares the same detection: `production/worker.py` augments each stage's prompt with the contract in json_object mode and gates the proxy cache key to `None` for `deepseek*` (so the shared `production/llm.py` transport never sends it).

## Rendering

Render an extraction JSON to HTML:

```bash
python tools/render_extraction.py tests/section-extraction-outputs/paper4_extraction.json
```

The renderer is schema-aware for `anchor_id` sections and colors units by section membership.

## Archived Material

Historical code, design discussions, plans, and legacy utilities live in `archive/`. Subdirectories: `legacy-paradigm-ir/`, `docs/`, `discussions/`, `plans/`, `issues/`, `legacy-tests/`, `legacy-prompts/`.

Do not treat archived material as active implementation guidance.
