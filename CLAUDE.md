# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository implements and documents a **3-section scientific literature extraction pipeline** (section-ir-0.8).

The active system extracts a paper as a **scientific-discovery throughline** into section-IR:

`problem -> method -> evidence`

`problem` is the single research problem the paper addresses (the old multi-tag `context` section, collapsed to one trunk). `method` is the technical apparatus. `evidence` is the merged experiment+analysis section: it carries both what was measured and what those measurements mean — and it now also hosts the **headline contribution claim** (the answer the evidence establishes), so there is no separate `claim` section. The discovery arc closes with a synthesized `resolves` edge from that headline claim back to the problem, and the one-sentence contribution is also lifted onto the Document as `thesis`.

## Active Architecture

The pipeline is **three-stage** (`node census -> relation pass -> content fill`):

1. **Node census (stage A)**: `prompts/section-extraction/node-census.md`
   - One full-paper call producing `spine_summary` and a flat `nodes[]` list of every load-bearing node — with **no relations**.
   - Each node carries a single granular `role` drawn from four search clusters (the guiding principle "trace the method's life"): **the_method** (`contribution`, `component`), **prior_art** (`builds_on`, `compared_against`), **testbed** (`dataset`, `benchmark`, `task`), **yardsticks** (`metric`). The node's coarse `type` (`Method`/`Entity`/`Metric`), Entity class, and document root are all **derived from `role`** — the census commits to one axis, not three. The `node_id` prefix (`mth:`/`ent:`/`met:`) follows from the role's type and is reused verbatim as the final unit id; each node also has a `salience` (`must`/`should`).
   - Two scoping rules: a **named model is a Method** (`builds_on`/`compared_against`), never a testbed node; **apparatus is not a node** (hardware and metric-scoring models like CLIP are dropped — the scoring model lives in the metric's gloss).
   - **Baselines are captured in full** (policy reversed 2026-05-26): every system the paper compares against is a `compared_against` Method node (including black-box, score-only baselines), materialized as a lightweight Method unit in the method section, carrying a `compares_to` edge to the contribution; its number is a row in the relevant Metric's `scores[]` (the `variant` names the system). The comparison is thus captured structurally (edge) and quantitatively (score row). Baselines are never Entities.
   - `normalize_census_nodes` derives `type` from `role`, re-prefixes ids, dedups, and ensures exactly one `contribution` (promoting the first must-method when none, demoting extras to `component`); `validate_census` is the stage-A contract.
   - Each prior-art/testbed node also carries `cite_keys` — the in-text bibliography marker(s) it is cited as (`["31"]` for a results-table row "GNMT + RL [31]"; `[]` for the contribution, components, tasks, and metrics). This is the deterministic join key for **reference linking**: `reconcile_reference_units` (run after content fill) fills each reference's `relation.provides_unit_ids` by matching the reference `id` to a materialized node's `cite_keys` first (exact, grounded in the paper's own citation, so it survives name mismatches like reference "GNMT" → unit "GNMT + RL"), then falls back to a unique `provides_name`↔unit-name match. Since `node_id == unit_id`, the link resolves straight to the method/evidence unit.

2. **Relation pass (stage B)**: `prompts/section-extraction/relation-pass.md`
   - One call receiving the full paper plus the complete flat node list. It establishes the structural entity↔entity edges (`part_of`, `compares_to`, `evaluates`, `measured_on`) with the whole node set in view, so cross-section composition and metric-subject binding need no forward references and no reconcile crutches.

3. **Content fill (stage C)**: `prompts/section-extraction/section-extraction-pass.md`
   - `section-extraction-pass.md` is a **slim shared core**: only the rules common to every section (identifiers, provenance format, the output envelope, universal hard constraints). It is byte-identical across all section calls, and the paper/spine_summary/node_registry/relations blocks precede `section_focus`, so the paper text stays in the cross-section prompt cache.
   - Three sections run in parallel (`problem`, `method`, `evidence`), each returning `section`. Each materializes the census nodes it owns (reusing `node_id` as the unit id) and creates its born units; `evidence` authors claim-centric edges (`about`, `supports`) and `problem` authors `motivates` (born Problem → the census Method/Entity it justifies) in a per-section `relations[]`. The closing `resolves` edge (Claim → Problem) is **not** authored by any section — it joins two units born in different parallel sections, so assembly synthesizes it (`_assign_resolves`) from the contribution-node join.
   - Receives the injected schema constraint, `spine_summary`, `node_registry` (all nodes), the global `relations[]` from stage B, and `section_focus`.
   - Per-section modules (`prompts/section-extraction/section-modules/{problem,method,evidence}.md`) are **self-contained section contracts** injected as `section_focus`: allowed unit types and field contracts, the controlled vocabularies and relation subset used, a worked example, and section-specific rules — none of it duplicated in the shared core.

Assembly and validation run in Python (`section_pipeline.py`). The default entrypoint is `run_pipeline()`.

Structured output is **model-adaptive** (see "Model compatibility" below). For models that support strict JSON-schema decoding (the Gemini/OpenAI-compatible proxy) every stage sends `response_format` with `strict: True`. For json_object-only models (official DeepSeek), `response_format` is `{"type": "json_object"}` and the same schema is rendered into the prompt as an OUTPUT FORMAT CONTRACT instead. Stage schemas: `schemas/node-census-output.schema.json`, `schemas/relation-pass-output.schema.json`, and the per-section `schemas/section-{section}.schema.json`.

Content responses use typed unit arrays instead of a flat `units[]` array: `problems` for problem, `methods` for method, and `metrics`/`settings`/`claims`/`entities` for evidence. `section_pipeline.py` flattens these typed arrays into `section["units"]` during assembly, and lifts each section's `relations[]` plus the stage-B edges (and the synthesized `resolves` edges) into a single top-level `relations[]`. The Document's `thesis` is filled from the census `spine_summary.central_contribution` during assembly (no extra LLM call).

Implementation entry point: `section_pipeline.py`.

Authoritative validation: Python `validate_section_ir()` in `section_pipeline.py` is the runtime contract.

Default section schemas: `schemas/section-problem.schema.json`, `section-method.schema.json`, `section-evidence.schema.json`.

Regenerate all schemas (per-section + census + relation pass) with `python tools/generate_section_schemas.py`. They are generated from constants in `section_pipeline.py`; never hand-edit the JSON.

Per-section focus modules: `prompts/section-extraction/section-modules/problem.md`, `method.md`, `evidence.md`.

Design reference: `docs/section-ir-0.7-redesign.md` (0.7 spec); `docs/section-ir-0.8-redesign.md` (0.8 spine delta); `docs/section-ir-design.md` (legacy 0.6).

## Section-IR Rules

- Units have flat structure — type-specific fields sit directly on the unit, no `payload` wrapper.
- Raw content responses group units into typed arrays: `problems`, `methods`, `metrics`, `settings`, `claims`, and `entities` as allowed by each section schema.
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
- Assembly merges the stage-B relations with each content section's `relations[]` into the global list, then performs lossy-but-safe repairs logged to `extraction_notes.uncertain_assignments`: `_sanitize_unit_text` strips C0 control characters (incl. the NULL bytes some models emit for `·`/`×`) from unit string values; `_dedup_entities` merges same-name Entities (rewriting relation endpoints); `_dedup_unit_ids` drops later duplicate definitions; `_drop_empty_sections` removes unit-less sections; `_normalize_provenance_markers` collapses fine-grained subsection markers to their top-level parent — both numeric body sections (`§4.3`→`§4`) and lettered appendices (`§C.1`→`§C`); a bare lettered appendix (`§D`) is itself a valid provenance marker (`PROVENANCE_SOURCE_RE` accepts `§N` or `§X`), so appendix-sourced units no longer fail validation (table/figure refs like `§Table 3` still do); `_repair_section_anchors` re-points non-local anchors; `_repair_score_refs` blanks dangling/wrong-type `scores[].system_id`/`setting_id`; `_dedup_relations`/`_drop_dangling_relations`/`_drop_invalid_relations` clean the global edge list against the relation matrix once the full unit set is known; `_drop_baseline_evaluates` drops `evaluates` edges pointing at a `compared_against` baseline (census-driven, so a metric's primary subject stays recoverable); `_assign_covers_entries` recomputes the census trace. Coverage is measured against census `must` nodes; an unmaterialized must-node surfaces in `extraction_notes.uncovered_items`.
- The headline contribution claim is born in the **evidence** section (there is no `claim` section); it carries an `about` edge to the contribution method. Assembly synthesizes the closing `resolves` edge (that headline Claim → the Problem the contribution motivates) from the contribution-node join — no section authors it. The Document `thesis` is the census `spine_summary.central_contribution`, lifted on at assembly.
- IR version: `section-ir-0.8`. `extraction_notes.input_mode` is `node_census_pipeline`.

Allowed unit types:

`Document`, `Entity`, `Method`, `Claim`, `Problem`, `Setting`, `Metric`

`Method`, `Entity`, and `Metric` are census nodes (role-tagged in stage A, with `type` derived from `role`); `Problem`, `Setting`, and `Claim` are born during content fill.

## Problem vs. Setting

- `Problem` (the research problem): fields `{description}` — one or two sentences naming the unresolved question or unmet need, with background folded into the prose. **One trunk** per paper; it replaced the old multi-tag `Context` (whose `context_kind ∈ {background, gap, motivation, challenge, assumption}` taxonomy was dropped as over-defined). It is born in the `problem` section and authors a `motivates` edge to the contribution.
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
| `about` | Claim → {Method, Entity, Metric} | content (evidence) |
| `supports` | {Metric, Claim} → Claim | content (evidence) |
| `motivates` | Problem → {Method, Entity} | content (problem) |
| `resolves` | Claim → Problem | assembly (synthesized) |

The matrix lives in `RELATION_MATRIX` in `section_pipeline.py`. (`occurs_under` was removed in 0.6; `subject_id`/`target_ids`/`evaluated_on`/`components` were promoted to global edges in 0.7.) `motivates` connects the discovery arc's first arrow — the Problem to the contribution it justifies — and survives parallel sectioning because the problem section authors it from a born Problem to a **census** node (visible in every section's `node_registry`), never to another born unit. `resolves` (added in 0.8) is the closing arrow — the headline Claim back to the Problem — but it joins two units born in *different* parallel sections, so no section can author it; assembly's `_assign_resolves` derives it deterministically (`Problem --motivates--> [contribution] <--about-- Claim` ⇒ `Claim --resolves--> Problem`). The stage-C relation enum is scoped per section in the schema generator's `STAGE_C_RELATIONS_BY_SECTION` (problem = `motivates`; evidence = `about`/`supports`); `resolves` appears in no stage-C enum.

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
