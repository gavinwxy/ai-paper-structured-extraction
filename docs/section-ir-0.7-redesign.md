# section-ir-0.7 redesign: nodes → edges → content

Status: **design spec** for the `planning-stage-redesign` branch. This supersedes the
two-stage (planning + parallel section extraction) pipeline of `section-ir-0.6`
described in `section-ir-design.md`. Once shipped, fold the durable parts back into
`section-ir-design.md` and retire this file.

## Motivation

Three independent pain points in 0.6 share one root cause — **commitment under
incomplete visibility**:

1. The planner enumerates items and declares their `relations` inline, forward-referencing
   targets it has not enumerated yet.
2. Every link is **section-local**; the validator hard-fails any cross-section link
   (`section_pipeline.py` ~L2498). Two known failures fall out of this:
   - method-section segmentation severs cross-segment `part_of` (the root method loses
     components);
   - an ablation Metric's subject is scattered from the component it measures, needing the
     `_reconcile_metric_subjects` / `_reconcile_analysis_metric_subjects` crutches.
3. The experiment/analysis boundary is adjudicated **per table row** by two blind parallel
   calls over the same results table (mirror-image rules duplicated in `experiment.md` /
   `analysis.md`), inviting double-extraction and gaps.

0.7 attacks the root cause directly: **find all entities first (no relating), relate them
once with the whole node set in view, then fill content.** Headline metric for the change
is raw recall — **node count and relation count** — held on a fixed model, with validity and
fragmentation guards so we can tell real recall from inflation.

Baseline (on-disk, gemini-3-flash-nothinking, 50-paper NeurIPS batch, measured with
`tools/count_extraction.py`): **23.8 nodes/paper, 19.3 relations/paper**. A prior un-tracked
"decoupled" run scored *lower* (21.9 / 17.6), so decoupling is not an automatic win —
execution decides. `Metric.evaluated_on` is **0 across every batch** (a dead edge today).
Relations are field-dominated (target_ids 337, subject_id 184, context_ids 141) vs sparse
explicit links (~5/paper).

## Final IR shape (0.7)

Top-level keys: `document`, `sections`, `relations`, `extraction_notes`.

- **`sections[]`** keep organizing/rendering the argumentative spine, now four:
  `context → claim → method → evidence` (experiment+analysis merged into `evidence`).
  Each section: `{section_type, anchor_id, covers_entries, units[]}`. **No per-section
  `links` anymore.**
- **`relations[]`** is new and **top-level / global**. It is the single authoritative edge
  list. Every cross-unit argumentative or structural edge lives here; unit fields hold only
  intrinsic properties and local scoping.

```json
{
  "document": { "...": "..." },
  "sections": [
    {"section_type": "context",  "anchor_id": "ctx:...", "covers_entries": [], "units": []},
    {"section_type": "claim",    "anchor_id": "clm:...", "covers_entries": [], "units": []},
    {"section_type": "method",   "anchor_id": "mth:...", "covers_entries": [], "units": []},
    {"section_type": "evidence", "anchor_id": "met:...", "covers_entries": [], "units": []}
  ],
  "relations": [
    {"source_id": "met:bleu", "relation": "evaluates",   "target_id": "mth:transformer",
     "provenance": ["§6"]},
    {"source_id": "mth:attn", "relation": "part_of",     "target_id": "mth:transformer", "provenance": []},
    {"source_id": "met:bleu", "relation": "measured_on", "target_id": "ent:wmt14",       "provenance": []},
    {"source_id": "clm:abl",  "relation": "about",       "target_id": "mth:attn",        "provenance": []},
    {"source_id": "met:abl",  "relation": "supports",    "target_id": "clm:abl",         "provenance": []}
  ],
  "extraction_notes": { "ir_version": "section-ir-0.7", "...": "..." }
}
```

### What moved from fields to edges

The 0.6 field-encoded edges that dominated the relation count become first-class entries in
`relations[]`:

| 0.6 representation | 0.7 relation | type rule |
|---|---|---|
| `Metric.subject_id` | `evaluates` | Metric → Method |
| `Metric.evaluated_on[]` (dead) | `measured_on` | Metric → Entity (dataset/benchmark) |
| `Claim.target_ids[]` | `about` | Claim → {Method, Entity, Metric} |
| section-local `part_of` link + `Method.components[]` | `part_of` | {Method,Entity} → {Method,Entity} |
| section-local `compares_to` link | `compares_to` | {Method,Entity,Metric} ↔ {Method,Entity,Metric} |
| section-local `supports` link | `supports` | {Metric,Claim} → Claim |

Stays a **unit field** (local scoping, not a global argument edge): `Metric.setting_ids[]`
→ the section-local Settings that scope the metric (evidence section only).

Dropped entirely: `Metric.subject_id`, `Metric.evaluated_on`, `Claim.target_ids`,
`Method.components` (no convenience projections; consumers read `relations[]`).

### Relation type matrix (global, authoritative)

| relation | source types | target types | produced by |
|---|---|---|---|
| `part_of` | Method, Entity | Method, Entity | stage B |
| `compares_to` | Method, Entity, Metric | Method, Entity, Metric | stage B |
| `evaluates` | Metric | Method | stage B |
| `measured_on` | Metric | Entity (dataset/benchmark) | stage B |
| `about` | Claim | Method, Entity, Metric | stage C (claim/evidence) |
| `supports` | Metric, Claim | Claim | stage C (evidence/claim) |

Endpoints must resolve to a unit defined **anywhere** (global), not section-local.

## Pipeline (three LLM stages + deterministic assembly)

`run_pipeline`:
1. In parallel: `run_node_census` (stage A, replaces planning) + `run_metadata_extraction` +
   `run_references_extraction` (independent sidecars).
2. `run_relation_pass` (stage B) — depends on census output.
3. `run_content_extraction` (stage C) — depends on A+B; per-section parallel, shared prompt
   prefix + paper text for cache reuse (same cache discipline as 0.6).
4. `reconcile_reference_units` → `assemble_extraction` → `validate_section_ir`.

### Stage A — node census (`run_node_census`)

One call, full paper. Output (`schemas/node-census-output.schema.json`):

```json
{
  "spine_summary": {"central_contribution": "...", "argument_flow": "..."},
  "nodes": [
    {"node_id": "mth:transformer", "role": "contribution", "name": "Transformer",
     "gloss": "encoder-decoder attention architecture",
     "source_scope": ["§3"], "salience": "must"}
  ]
}
```

> **Type-system cleanup (post-ship).** The census node carries a single granular `role`, not a
> `type`/`entity_class`/`is_root` triple. The eight roles group into four search clusters by the
> guiding principle "trace the method's life": **the_method** (`contribution`, `component`),
> **prior_art** (`builds_on`, `compared_against`), **testbed** (`dataset`, `benchmark`, `task`),
> **yardsticks** (`metric`). `type` and the Entity class are derived from `role` (total mapping
> in `ROLE_TO_TYPE`), so the model commits to one axis instead of three half-overlapping fields.

- `role` is the one tag the census emits; `type ∈ {Method, Entity, Metric}` is derived from it.
  Context, Setting, Claim are **not** nodes; they are born in content (stage C).
- `node_id` prefix follows from the role's type (`mth:` / `ent:` / `met:`); reused verbatim as
  the final unit id. A **named model is a Method** (role `builds_on`/`compared_against`), and
  **apparatus** (hardware, metric-scoring models) is not a node at all.
- **Baseline capture (policy reversed 2026-05-26).** 0.6 dropped score-only comparison baselines.
  0.7 captures them in full: every compared-against system is a `compared_against` Method node
  (even black-box ones), materialized lightweight in the method section, carrying a `compares_to`
  edge from stage B; its number is a `scores[]` row on the relevant Metric (`variant` = system
  name). This is prompt-only — `scores[].variant` was already a free string. The smoke test on
  paper 4 surfaced the prior self-inconsistency: the census emitted the baseline nodes but the
  method module refused to materialize them, so the `compares_to` edges always dangled and dropped.
- `salience ∈ {must, should}` — **keep the 0.6 salience discipline**: only argumentatively
  load-bearing nodes. Count rises from "relate-what-you-found" + the merge, not from flooding.
- Exactly one node has `role: contribution` (document-level); promoted/demoted deterministically
  in `normalize_census_nodes`.
- `spine_summary` is carried into content (replaces the 0.6 planner's summary).
- This is the **"node count"** numerator.
- **Vocabulary scoping (AI/ML).** Fields that were monotone across the corpus are gone: Metric
  `value_type`, Claim `novelty`/`epistemic_status`/`polarity`, Setting `condition_kind`.
  Enum values that never fired were dropped: `claim_kind` loses `causal`/`correlational`,
  `method_kind` loses `protocol`/`software_system`, `entity_class` loses `model`/`hardware`.

### Stage B — relation pass (`run_relation_pass`)

One call. Input: full paper + the flat `nodes[]` (id, type, name, gloss). Output
(`schemas/relation-pass-output.schema.json`):

```json
{"relations": [{"source_id": "met:bleu", "relation": "evaluates", "target_id": "mth:transformer",
                "provenance": ["§6"]}]}
```

- Emits only the **entity↔entity** edges: `part_of`, `compares_to`, `evaluates`, `measured_on`.
- Sees every node ⇒ no forward references; cross-section composition (the severed-`part_of`
  pain) and ablation-subject binding (the `subject_id` pain) are solved structurally — both
  0.6 reconcile crutches are deleted.
- Provenance is light but encouraged for traceability.
- This is the bulk of the **"relation count"** numerator.

### Stage C — content extraction (`run_content_extraction`)

Per-section parallel calls over `context | claim | method | evidence`, each receiving the full
paper (cached), the relevant node subset, the global `relations[]`, `spine_summary`, and its
section focus module. Output per call: `{section_type, anchor_id, covers_entries, <typed unit
arrays>, relations[]}` where `relations[]` carries the **claim-centric** edges this section
authors (`about`, `supports`).

- **context**: born `Context` units (background/gap/motivation/challenge/assumption).
- **claim**: born `Claim` units (headline); their `about`/`supports` edges → `relations[]`.
- **method**: enrich each Method node with `description`, `method_kind`, `formulas`,
  `objective_function`, `inputs`, `outputs`, `implementation_notes`.
- **evidence** (merged experiment+analysis): enrich each Metric node with `scores`, `unit`,
  `comparison_direction`, `value_type`; create local `Setting` units and set
  `Metric.setting_ids`; author interpretive `Claim` units (`ablation_finding`, `failure_mode`)
  with `about`/`supports` edges. The deployable-vs-diagnostic call is now made **once, with the
  whole table in view** — encoded as Metric (measurement) vs Claim+supports (interpretation),
  not as a section boundary. Segment `evidence` by experimental purpose (primary / ablation /
  transfer) so each segment is self-contained.
- **Node augmentation (recall default):** a content call MAY introduce a node the census missed
  (fresh id, correct prefix) and SHOULD emit its obvious edges; assembly keeps it (lifts recall).

## Assembly (`assemble_extraction`, 0.7)

1. Flatten each content section's typed arrays → `section.units[]`; collect into `sections[]`
   in spine order (`context, claim, method, evidence`).
2. `relations = stageB.relations + Σ section.relations`.
3. `_dedup_entities`, `_dedup_unit_ids` (keep).
4. `_dedup_relations` by `(source_id, relation, target_id)` (new).
5. `_drop_dangling_relations`: drop edges whose endpoint resolves to no unit; log to
   `uncertain_assignments` (new; replaces section-local link pruning).
6. `_drop_invalid_relations`: enforce the global type matrix (was `_drop_invalid_links`).
7. `_normalize_provenance_markers` (keep). `_repair_section_anchors` (keep — anchors stay
   section-local). `_reconcile_covers_entries` (keep — traces to census `must` nodes).
8. **Deleted:** `_reconcile_method_components`, `_reconcile_metric_subjects`,
   `_reconcile_analysis_metric_subjects` (their jobs are now done up-front by stage B with full
   visibility).

## Validator (`validate_section_ir`, 0.7)

- Top-level allowed keys: `document, sections, relations, extraction_notes`.
- `SECTION_TYPES = {context, claim, method, evidence}`;
  `evidence` allowed unit types = `{Metric, Setting, Claim, Entity}`.
- Validate `relations[]` globally: relation in matrix, endpoints resolve to a defined unit
  (any section), type pairing legal. Drop the section-local hard-fail.
- Metric: require `name`, `unit`, non-empty `scores`; `setting_ids` (if present) must be
  section-local Settings. No `subject_id`/`evaluated_on` fields. Soft check
  (`uncertain_assignments`, not fail): a result Metric with no `evaluates` edge.
- Claim: a Claim outside `{claim, evidence}` needs an incoming `supports` (the `established_fact`
  exemption is gone with `epistemic_status`).
- `extraction_notes.ir_version == "section-ir-0.7"`; `input_mode == "node_census_pipeline"`.

## Files to change

- `section_pipeline.py`: constants (`RELATION_MATRIX`, `SECTION_TYPES`, section→unit-types,
  prefixes), stages A/B/C, assembly, validator.
- `tools/generate_section_schemas.py`: `SECTION_TYPED_ARRAYS = {context:[contexts],
  claim:[claims], method:[methods], evidence:[metrics, conditions, claims, entities]}`; drop
  experiment/analysis; emit node-census + relation-pass schemas; Metric loses
  `subject_id`/`evaluated_on`; content section schemas gain `relations[]`, lose `links`.
- `prompts/section-extraction/`: new `node-census.md`, `relation-pass.md`; section modules
  `context.md`, `claim.md`, `method.md`, new `evidence.md` (absorbs experiment+analysis);
  archive `experiment.md`/`analysis.md`; update shared core `section-extraction-pass.md`.
- `tests/test_section_pipeline.py`, `tests/test_section_extraction.py`,
  `tools/render_extraction.py` (global relations + evidence section).

## Measurement plan

- Headline: node count + relation count per paper (`tools/count_extraction.py`, extended for
  top-level `relations[]`), before vs after on the **same** model (gemini-3-flash-nothinking)
  and the same 50-paper batch — model is a confound (deepseek ≈ +42% nodes / +76% relations).
- Guards: validity pass rate; a fragmentation/dedup proxy (e.g. duplicate-name merge rate,
  method over-split rate) so a count gain from over-splitting is visible, not mistaken for recall.
- Target: relation count up materially (the merge + edges-as-first-class + `measured_on` revival),
  node count up modestly, validity ≥ 0.6 baseline, fragmentation not worse.
