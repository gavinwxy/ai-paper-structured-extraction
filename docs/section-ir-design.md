# 5-Section IR Design

> **Superseded (legacy 0.6).** The active design is section-ir-0.7 (`context → claim → method → evidence`,
> three-stage `node census → relation pass → content fill`, global top-level `relations[]`). See
> `docs/section-ir-0.7-redesign.md` and `CLAUDE.md`. This file is retained for the 0.6 history below.

This was the active design for the scientific literature extraction pipeline.
It replaced the archived 8-paradigm IR as the main implementation path.

## Scope

5-section IR is a focused extraction mode for research papers whose argument can be reconstructed as:

`context and gap -> claim -> method -> experiment -> analysis`

It is optimized for experimental, computational, methodological, benchmark, and applied scientific papers. It is not yet the right primary representation for taxonomy-heavy descriptive papers, pure axiomatic-deductive work, or papers whose value is mostly a catalog rather than an argument spine.

## Pipeline

The active pipeline has two LLM stages:

1. `planning` pass: read the paper and produce a section-first extraction plan.
2. `parallel section extraction` pass: extract each planned section and assemble section-IR JSON.

The implementation entry point is `section_pipeline.py`.

The runtime does not branch on paper length. Every paper follows the same planning -> parallel section extraction -> assembly flow. Each planned section receives the full paper text. The `source_scope` field in plan items serves as salience guidance for the model, not as a physical text slice.

## Planning Output

The planning pass emits:

- `spine_summary`: the central contribution and the high-level argument flow.
- `section_plans`: extraction targets organized by `section_type`, with optional multi-segment expansion.

Each plan item has:

```json
{
  "item_id": "clm:main_claim",
  "priority": "must",
  "source_scope": ["§12"],
  "description": "The headline contribution claim."
}
```

`item_id` is the trace key. Extraction sections record covered plan items in `covers_entries[]`.

## Top-Level Output

Every extraction returns exactly these keys:

- `document`: the single `Document` unit.
- `sections`: section-oriented bundles with `section_type`, `anchor_id`, `covers_entries`, local `units`, and `links`.
- `extraction_notes`: audit metadata, including plan coverage.

There is no top-level `shared_units` array and no top-level `cross_section_links` array. Every non-document unit is defined exactly once in its home section. Metrics may refer to externally defined units by ID through `subject_id`; Claims may refer to external units through `target_ids`.

`section_type` belongs only on sections. Units must not contain `section_type`.

## Unit Types

Allowed unit types are:

- `Document`
- `Entity`
- `Method`
- `Claim`
- `Context` — argumentative premise (background, gap, motivation, challenge, assumption)
- `Condition` — operational constraint (experimental setup, boundary, evaluation protocol, hyperparameter)
- `Metric`

The archived legacy types `Relation`, `Category`, `SystemModel`, `MethodArtifact`, `Proposition`, `RoleBinding`, and standalone `Provenance` are not valid in section-IR raw output.

## Unit Structure (Flat)

Units have a flat structure — type-specific fields sit directly on the unit object with no `payload` wrapper:

```json
{
  "id": "clm:main_claim",
  "type": "Claim",
  "statement": "...",
  "claim_kind": "comparative",
  "target_ids": ["mth:attention"],
  "polarity": "positive",
  "epistemic_status": "conclusion",
  "provenance": [{"source_kind": "sentence", "source": ["§3"]}]
}
```

Each unit always has `id`, `type`, and `provenance[]`. Other fields depend on the unit type. In structured output schemas, inapplicable string fields use `""` and inapplicable arrays use `[]`.

## Context vs. Condition

`Context` carries argumentative weight — it motivates, qualifies, or challenges the claim by virtue of section membership and its description. It uses `context_kind ∈ {background, gap, motivation, challenge, assumption}` and a `description` field.

`Condition` carries operational weight — it bounds the experimental setup or constrains how a metric should be interpreted. It uses `condition_kind ∈ {experimental, boundary, evaluation_setup, hyperparameter}` and a `description` field.

Decision rule: if removing the unit would make the argument incomprehensible, it is `Context`; if it would merely make an experiment underdescribed, it is `Condition`.

## Unit Home Sections

Each unit is defined in the section where it plays its core role:

| unit role | home section |
|---|---|
| research background, gap, problem, scope, assumptions | context |
| central contribution, thesis, headline finding | claim |
| algorithm, architecture, protocol, workflow, detailed baselines | method |
| dataset, benchmark, evaluation setup, target-method result metric | experiment |
| interpretation, ablation conclusion, ablation metric, limitation, sensitivity, future work | analysis |

## Section Contract

Each section has:

```json
{
  "section_type": "context | claim | method | experiment | analysis",
  "anchor_id": "unit:id",
  "covers_entries": ["plan:item_id"],
  "units": [],
  "links": []
}
```

`anchor_id` must reference a unit defined in that section's local `units`.

`covers_entries` is the authoritative trace from extraction output back to the planning pass. Validator coverage is computed from this field, not from self-reported notes.

## Link Matrix

All links are section-local.

| relation | source types | target types |
|---|---|---|
| `supports` | Metric, Claim | Claim |
| `part_of` | Method, Entity | Method, Entity |
| `compares_to` | Method, Entity, Metric | Method, Entity, Metric |

Measurement is represented on `Metric` fields (`subject_id`, `context_ids`, `evaluated_on`, and `scores[]`) rather than with a `measured_by` link. `subject_id` names the measured Method, `context_ids` the local Conditions that scope it, and the optional `evaluated_on` the local dataset/benchmark Entities it was measured on — the structured "method × dataset × metric" triple. `scores[]` is a flat array of method-family variant results; external baselines are not captured.

Method-to-method dataflow is descriptive only: it lives in `Method.inputs`/`outputs` strings, never as a link. The method section emits only `part_of` (composition) and `compares_to` (alternatives); there is no `feeds`/dataflow relation. (`occurs_under` was removed in `section-ir-0.6`: under the 5-section partition no section could co-locate a valid source and target for it, so it only induced invalid output.)

`Method.components[]` is a denormalized projection of section-local `Method --part_of--> Method` links, present only in the assembled output. The per-section extraction schema does not expose a component field, so extractors express composition solely through `part_of` links (`child --part_of--> parent`). Assembly (`_reconcile_method_components` in `section_pipeline.py`) rebuilds `components[]` from those links — defensively folding any stray model-emitted component into the link set first — so the two representations never disagree.

## Plan Traceability

The extraction pass must:

- Cover every `priority: "must"` plan item through `covers_entries`, or explain it in `extraction_notes.uncovered_items`.
- Prefer reusing an item's `item_id` as the final unit ID when the item naturally maps to one unit.
- Report `extraction_notes.plan_coverage.must_covered` and `must_total`; the validator recomputes these from `covers_entries`.

## Parallel Extraction

The default runtime path is:

`run_planning() -> run_parallel_extraction_sync() -> assemble_extraction() -> validate_section_ir()`

`expand_section_plans()` turns each top-level or nested segment plan into an independent extraction task. Each task receives:

- the current section plan
- the complete ID registry from `build_id_registry()`
- the full paper text, with shared prompt prefixing for cache reuse

Each section extractor returns one `section`. Assembly generates the `document`, preserves section order from the plan, and builds `extraction_notes`.

Exactly one method plan item is marked `is_root: true`, evaluated document-level across all method section plans rather than per section. `is_root` is consumed only as a soft default downstream (preferred Claim `target_ids` and Experiment Metric `subject_id`), so `normalize_planning_item_ids` backfills it — choosing the first must-priority method item, else the first method item — when the planner omits it, and demotes extras to keep exactly one.

## Assembly Repairs

Assembly is lossy-but-safe: it repairs recoverable model mistakes instead of failing the whole extraction, recording each repair in `extraction_notes.uncertain_assignments`. After flattening typed arrays it runs, in order:

- `_dedup_entities` / `_dedup_unit_ids`: merge same-name entities and drop duplicate unit IDs.
- `_reconcile_method_components`: make `part_of` links authoritative for `Method.components[]`.
- `_reconcile_metric_subjects`: align each experiment `Metric.subject_id` with the plan's `evaluates` target, falling back to the document-level root method when the model's reference is missing or dangles.
- `_reconcile_analysis_metric_subjects`: re-point an analysis `Metric.subject_id` at the component its supported ablation Claim targets, when the metric's `Metric --supports--> Claim` links collapse to exactly one component. Conservative: never downgrades a subject that already names a component, and leaves ambiguous/system-level/unlinked metrics untouched.
- `_drop_empty_sections`: remove a section the model left with no units (a common over-split artifact); an empty section can never satisfy the anchor contract.
- `_normalize_provenance_markers`: collapse a fine-grained `§N.M` source to its real top-level `§N`. Appendix (`§G.2`) and table/figure markers have no `§N` to collapse to and are left to fail as genuine provenance violations.
- `_drop_invalid_links`: remove section-local links whose source/target types violate the link matrix.
- `_repair_section_anchors`: re-point an `anchor_id` that names a non-local unit to the section's first local non-Document unit.
- `_reconcile_covers_entries`: drop `covers_entries` that no longer resolve to a defined unit; uncovered must-items then resurface in `extraction_notes.uncovered_items`.

`extraction_notes` is computed from the repaired sections, so plan coverage reflects these mutations.

## Active Files

- Section prompt: `prompts/section-extraction/section-extraction-pass.md`
- Planning prompt: `prompts/section-extraction/planning-pass.md`
- Planning schema: `schemas/planning-output.schema.json`
- Section schemas: `schemas/section-{context,claim,method,experiment,analysis}.schema.json`
- Pipeline and validator: `section_pipeline.py`
- HTML renderer: `tools/render_extraction.py`
- Unit tests: `tests/test_section_pipeline.py`
- LLM smoke script: `tests/test_section_extraction.py`
