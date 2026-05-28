# section-ir-0.9 — Fields & Schema Reference

This is the **field-level reference** for the active extraction IR (`section-ir-0.9`): every
unit type, its fields, the controlled vocabularies, the relation matrix, and the per-stage
JSON schemas. It documents *what the data looks like*.

For the *why* (the two-level taxonomy rationale, the Entity⊎Setting merge, the `measured_on`
removal) see [`section-ir-0.9-redesign.md`](section-ir-0.9-redesign.md). For the pipeline
narrative see the project `CLAUDE.md`.

**Source of truth:** the constants in `section_pipeline.py` (`UNIT_TYPES`,
`ALLOWED_FIELDS_BY_TYPE`, `ROLE_VOCAB_BY_TYPE`, `RELATION_MATRIX`, …) and the JSON schemas in
`schemas/`, which are generated from those constants by `tools/generate_section_schemas.py`.
This doc is hand-written prose *describing* them; if the two disagree, the code wins.

---

## 1. The extraction envelope

A completed extraction is one JSON object with exactly four top-level keys:

```jsonc
{
  "document":        { … },        // a single Document unit (the paper itself)
  "sections":        [ … ],        // problem / method / evidence, each with units[]
  "relations":       [ … ],        // the single global edge list
  "extraction_notes": { … }        // ir_version, input_mode, coverage, repairs
}
```

- **`document`** — one `Document` unit (see §4.1).
- **`sections`** — three sections in `SECTION_ORDER` = `["problem", "method", "evidence"]`.
  Each section is `{section_type, anchor_id, covers_entries[], units[]}`. `units[]` is the
  flattened unit list (assembly flattens the raw typed arrays into it). `covers_entries[]` is
  the deterministic census-node trace, computed by assembly — the model never echoes it.
- **`relations`** — the *single* global edge list. Sections carry no `links`; every edge
  lives here and may resolve to a unit defined in any section (§5).
- **`extraction_notes`** — `{ir_version: "section-ir-0.9", input_mode: "node_census_pipeline",
  uncovered_items[], uncertain_assignments[], …}`. `ir_version` is validated here, not on the
  Document.

### Identifier convention

Every unit id matches `^[a-z][a-z0-9_]*:[a-z0-9_]+$` — a type prefix, a colon, a slug:

| type | prefix | | type | prefix |
|---|---|---|---|---|
| Document | `doc:` | | ExperimentSetup | `exp:` |
| Problem | `prb:` | | Measure | `mea:` |
| Method | `mth:` | | Finding | `fnd:` |

Each id is **defined exactly once**. A census `node_id` is reused *verbatim* as the unit id
when a section materializes the node (so `node_id == unit_id` and reference links resolve
straight through). Cross-unit references are **edges in `relations[]`**, never unit fields —
the only in-unit references are `Measure.setup_ids[]` and the per-row scalars
`scores[].system_id` / `scores[].setup_id`.

The retired 0.8 prefixes `ent:`/`set:`/`met:`/`clm:`/`ctx:` are canonicalized to their 0.9
forms on ingest and are not emitted.

### Provenance convention

Every unit and every relation carries `provenance: string[]` — a list of top-level section
markers matching `^§(?:\d+|[A-Z]+)$`, i.e. `§4` (numeric body section) or `§C` (lettered
appendix). Fine-grained markers are collapsed to their top-level parent during assembly
(`§4.3 → §4`, `§C.1 → §C`). Table/figure refs (`§Table 3`) are **not** valid provenance.
`Finding` and `Measure` must have **non-empty** provenance.

---

## 2. The two-level taxonomy: `type` + `role`

Every unit carries two classificatory axes:

- **`type`** — a small, discipline-neutral scope, anchored on the anatomy of an empirical
  paper (the scientific method): *Identify a Problem → Design an Experiment → Collect Results
  → Construct a Conclusion*. The 6 types are the same across AI/ML subfields.
- **`role`** — the AI/ML-specific differentia carried *on the unit*. It unifies the old
  scattered `entity_class`/`setting_kind`/`claim_kind`/`doc_role` fields and lifts the census
  argumentative role onto Method. Swapping disciplines means swapping the role vocabularies,
  never the `type` set.

`Problem` and `Measure` carry **no** `role` (Problem is a single trunk; Measure is uniform).

| scientific-method phase | `type` | `role` vocab |
|---|---|---|
| Identify a Problem | **Problem** | — |
| Design an Experiment (apparatus) | **Method** | `contribution` · `component` · `builds_on` · `compared_against` |
| Design an Experiment (materials + conditions) | **ExperimentSetup** | substrate: `dataset` · `benchmark` · `task` — config: `data_split` · `inference_protocol` · `training_config` · `ensembling` · `population` |
| Collect Results | **Measure** | — |
| Construct a Conclusion | **Finding** | `descriptive` · `mechanistic` · `comparative` · `modeling` · `ablation_finding` · `failure_mode` |
| the paper | **Document** | `research_article` · `review` · `meta_analysis` · `methodology` · `benchmark_survey` |

`FORBIDDEN_UNIT_TYPES` rejects the retired names `Entity`, `Setting`, `Metric`, `Claim`
(plus older `RoleBinding`/`Relation`/`MethodArtifact`/`SystemModel`/`Proposition`/`Category`/
`Provenance`) so a stale prompt or model output fails loudly.

---

## 3. Where each unit comes from (census vs born)

| `type` (+role) | discovered by | materialized in |
|---|---|---|
| Method (all roles) | node census (A) | method section (C) |
| ExperimentSetup — substrate (`dataset`/`benchmark`/`task`) | node census (A) | evidence section (C) |
| ExperimentSetup — config (`data_split`/…) | — (born) | evidence section (C) |
| Measure | node census (A) | evidence section (C) |
| Problem | — (born) | problem section (C) |
| Finding | — (born) | evidence section (C) |
| Document | metadata + census | assembly |

For census-materialized units (Method, substrate ExperimentSetup) the census already committed
the `role`, so assembly's `_assign_roles_from_census` stamps it authoritatively rather than
trusting the content model to echo it. Born units (config ExperimentSetup, Finding) author
their own `role`.

---

## 4. Unit type reference

Field tables below mark **R** = required, **O** = optional (omitted entirely when unsupported —
never invented). The authoritative per-type field allow-list is `ALLOWED_FIELDS_BY_TYPE`;
required/optional split is `OPTIONAL_FIELDS_BY_TYPE` in the schema generator.

### 4.1 Document

The paper itself. One per extraction.

| field | R/O | notes |
|---|---|---|
| `id` | R | `doc:…` |
| `type` | R | `"Document"` |
| `doc_id` | R | stable document identifier |
| `title` | R | paper title |
| `role` | R | `DOCUMENT_ROLES` (default `research_article`) |
| `thesis` | R | the one-sentence contribution, lifted from census `spine_summary.central_contribution` at assembly |
| `provenance` | O | |

### 4.2 Problem

The single research problem the paper addresses — **one trunk** (replaced the old multi-tag
`Context`). Born in the problem section; authors a `motivates` edge to the contribution.

| field | R/O | notes |
|---|---|---|
| `id` | R | `prb:…` |
| `type` | R | `"Problem"` |
| `description` | R | one–two sentences naming the unresolved question / unmet need; background folded into the prose |
| `provenance` | R | |

Carries **no** `role`.

### 4.3 Method

The technical apparatus — the contribution, its components, the prior art it builds on, and
every baseline it is compared against.

| field | R/O | notes |
|---|---|---|
| `id` | R | `mth:…` |
| `type` | R | `"Method"` |
| `role` | R | `METHOD_ROLES` — the argumentative function (`contribution`/`component`/`builds_on`/`compared_against`) |
| `name` | R | |
| `description` | R | |
| `implementation_notes` | R | |
| `method_kind` | O | structural attribute, orthogonal to `role`: `algorithm` · `model_architecture` · `training_strategy` · `objective_function` |
| `inputs` | O | `string[]` |
| `outputs` | O | `string[]` |
| `formulas` | O | `[{name, expression, symbols[]}]` |
| `objective_function` | O | `{expression, description, symbols[]}` |
| `provenance` | R | |

Exactly **one** Method has `role: contribution` (the document root); `normalize_census_nodes`
promotes the first must-method if none is tagged and demotes extras to `component`.
Composition is the `part_of` relation, not a `components` field.

**`formulas[]` entry** — `{name (R), expression (R, non-empty), symbols[] (R)}`.
**`objective_function`** — `{expression (R, non-empty), description (R), symbols[] (R)}`.
**`symbols[]` entry** — `{symbol (R, non-empty), description (R, non-empty)}` glossing one
token of the equation; the array may be empty when the expression introduces no symbols.

**Baselines** (policy: captured in full): every compared-against system is a `compared_against`
Method unit (including black-box / score-only baselines), carrying a `compares_to` edge to the
contribution and appearing as a row in the relevant Measure's `scores[]`. Baselines are never
ExperimentSetups.

### 4.4 ExperimentSetup

The merged 0.9 type (old `Entity ⊎ Setting`). One type, two halves split by `role`: a
**substrate** half (what you run on — census-discovered, external, citeable) and a
**configuration** half (under what conditions — paper-local, born, materialized only when it
actually scopes a Measure).

| field | R/O | notes |
|---|---|---|
| `id` | R | `exp:…` |
| `type` | R | `"ExperimentSetup"` |
| `role` | R | `EXPERIMENT_SETUP_ROLES` (substrate ∪ config — see below) |
| `name` | R | a dataset name, a split label |
| `description` | O | prose |
| `provenance` | R | |

`role` ∈ substrate `{dataset, benchmark, task}` ∪ config `{data_split, inference_protocol,
training_config, ensembling, population}`.

Bibliography markers (`cite_keys`) live on the **census node**, not on the unit — reference
reconcile joins via `node_id`, so the unit stays clean. Configuration that scopes **no**
Measure (hardware, global hyperparameters) is intentionally not captured.

### 4.5 Measure

A reported performance measure. Census node; materialized in evidence.

| field | R/O | notes |
|---|---|---|
| `id` | R | `mea:…` |
| `type` | R | `"Measure"` |
| `name` | R | |
| `unit` | R | e.g. `"BLEU"`, `"F1"`, `"%"` |
| `scores` | R | non-empty; one row per system **per split** (§4.5.1) |
| `setup_ids` | R | scoping ExperimentSetups (may be `[]` — e.g. an ablation measure) |
| `comparison_direction` | O | `higher_is_better` · `lower_is_better` · `target` · `unspecified` |
| `provenance` | R | |

Carries **no** `role`. The measure→method link is the `evaluates` edge (pointed only at the
contribution/component it measures, **never** at a baseline). The measure→dataset link is
**not** a global edge (`measured_on` was removed in 0.9) — it is each score row's `setup_id`.
`setup_ids[]` (when non-empty) must point to section-local ExperimentSetup units.

#### 4.5.1 `scores[]` row

Each row is `{variant, value, variance, system_id, setup_id}` (all five required; `system_id`
and `setup_id` may be the empty string when no unit represents them):

| field | notes |
|---|---|
| `variant` | the paper's label for the system on this row |
| `value` | the reported number (as a string) |
| `variance` | error / std-dev / CI, or `""` |
| `system_id` | the **Method** unit this row reports (a contribution variant *or* a baseline). Non-empty must resolve to a Method globally. Turns the row into a structured comparison. |
| `setup_id` | the **local ExperimentSetup** this row was measured under. Non-empty must resolve to a section-local ExperimentSetup. Lets one measure span several splits (EN-DE + EN-FR rows under one BLEU measure) without collapsing a split column to one number. |

### 4.6 Finding

A conclusion drawn from the evidence. Born in the evidence section. The **headline
contribution finding** lives here too (there is no separate `claim` section): it carries an
`about` edge to the contribution method, and assembly synthesizes the closing `resolves` edge
from it back to the Problem.

| field | R/O | notes |
|---|---|---|
| `id` | R | `fnd:…` |
| `type` | R | `"Finding"` |
| `role` | R | `FINDING_ROLES` — `descriptive` · `mechanistic` · `comparative` · `modeling` · `ablation_finding` · `failure_mode` |
| `statement` | R | |
| `provenance` | R | |

Has no `target_ids` field — what a finding is about is the `about` edge. The monotone
`polarity`/`novelty`/`epistemic_status` fields and `causal`/`correlational` roles were dropped
in the AI/ML-scoped cleanup.

---

## 5. Relations (global)

`relations[]` is a single top-level list; every edge is `{source_id, relation, target_id,
provenance[]}` and resolves to a unit defined anywhere. The type matrix is `RELATION_MATRIX`
(7 relations):

| relation | source → target | authored by |
|---|---|---|
| `part_of` | {Method, ExperimentSetup} → {Method, ExperimentSetup} | relation pass (B) |
| `compares_to` | {Method, ExperimentSetup, Measure} → same | relation pass (B) |
| `evaluates` | Measure → Method | relation pass (B) |
| `about` | Finding → {Method, ExperimentSetup, Measure} | content — evidence (C) |
| `supports` | {Measure, Finding} → Finding | content — evidence (C) |
| `motivates` | Problem → {Method, ExperimentSetup} | content — problem (C) |
| `resolves` | Finding → Problem | assembly (synthesized) |

- **Stage B** (`STAGE_B_RELATIONS`) owns the structural node↔node edges over the full node
  set: `part_of`, `compares_to`, `evaluates`.
- **Stage C** sections author edges needing born units: evidence → `about`/`supports`,
  problem → `motivates` (born Problem → a *census* node visible in every section's registry,
  so no forward reference is needed).
- **`resolves`** (`SYNTHESIZED_RELATIONS`) is the closing arc stroke; it joins two units born
  in *different* parallel sections, so no section can author it. Assembly's `_assign_resolves`
  derives it deterministically from the contribution-node join: `Problem --motivates-->
  [contribution] <--about-- Finding` ⇒ `Finding --resolves--> Problem`.

The discovery arc closes: `Problem --motivates--> Method(contribution) … Finding --about-->
Method(contribution)`, and `Finding --resolves--> Problem`. The contribution's headline
sentence is also lifted onto `Document.thesis`.

---

## 6. Per-stage schemas

The pipeline is three LLM stages plus deterministic assembly. Each stage has its own schema
in `schemas/`, generated from the `section_pipeline.py` constants by
`tools/generate_section_schemas.py` (never hand-edit the JSON; regenerate with
`python tools/generate_section_schemas.py`).

### 6.1 Stage A — node census (`schemas/node-census-output.schema.json`)

One full-paper call producing the spine summary and a flat node list with **no relations**:

```jsonc
{
  "spine_summary": {
    "central_contribution": "string",   // → lifted onto Document.thesis
    "argument_flow":        "string"
  },
  "nodes": [
    {
      "node_id":      "mth:… | exp:… | mea:…",   // reused verbatim as the unit id
      "role":         "contribution | component | builds_on | compared_against | dataset | benchmark | task | metric",
      "name":         "string",
      "gloss":        "string",
      "source_scope": ["§N", …],
      "cite_keys":    ["31", …],   // in-text bib markers; [] for contribution/components/tasks/measures
      "salience":     "must | should"
    }
  ]
}
```

The node's coarse `type` and the `node_id` prefix are **derived from `role`** (`ROLE_TO_TYPE`):
the four Method roles → `mth:`, the three substrate roles → `exp:`, `metric` → `mea:`. The
census commits to the single `role` axis; `normalize_census_nodes` derives `type`, re-prefixes
ids, dedups, and ensures exactly one `contribution`. `cite_keys` is the deterministic join key
for reference linking (`reconcile_reference_units`).

### 6.2 Stage B — relation pass (`schemas/relation-pass-output.schema.json`)

One call receiving the full paper plus the complete flat node list; emits only the structural
edges:

```jsonc
{
  "relations": [
    { "source_id": "…", "relation": "part_of | compares_to | evaluates",
      "target_id": "…", "provenance": ["§N", …] }
  ]
}
```

### 6.3 Stage C — content fill (`schemas/section-{problem,method,evidence}.schema.json`)

Three sections run in parallel. Each returns `{ "section": { … } }`. Raw responses group units
into **typed arrays** (assembly flattens them into `section.units[]`):

| section | typed arrays | authors `relations[]` (enum) |
|---|---|---|
| `problem` | `problems[]` | `motivates` |
| `method` | `methods[]` | — (none) |
| `evidence` | `measures[]`, `experiment_setups[]`, `findings[]` | `about`, `supports` |

Each section object is `{section_type, anchor_id, <typed arrays>, relations[]?}`. `resolves`
appears in **no** stage-C enum (it is synthesized). `covers_entries[]` is **not** in the
schema — assembly derives it.

The shared user-prompt prefix (paper / `spine_summary` / `node_registry` / stage-B
`relations`) precedes the per-section `section_focus`, so the paper text stays in the
cross-section prompt cache. The per-section focus module
(`prompts/section-extraction/section-modules/{problem,method,evidence}.md`) is a self-contained
section contract injected as `section_focus`.

---

## 7. Schema generation & model compatibility

Schemas are generated from constants — `python tools/generate_section_schemas.py` regenerates
all five (per-section + census + relation pass). Structured-output enforcement is
**model-adaptive** (`_structured_output_mode` keys off the model name):

- **`json_schema` mode** (non-DeepSeek, e.g. the Gemini/OpenAI-compatible proxy): the schema
  is sent in `response_format` with `strict: True`; prompts are unchanged.
- **`json_object` mode** (**default** — `deepseek*`): `response_format` is
  `{"type": "json_object"}`, and the *same* schema is rendered into the prompt as an OUTPUT
  FORMAT CONTRACT via `schema_to_prompt_spec` (keys, required/optional, enums, id patterns).
  The contract is derived from the schema, so it never drifts. It is appended to the system
  prompt for the four single-shot calls and folded into `section_focus` for content sections
  (keeping the cross-section cache prefix byte-identical).

The default model is **`deepseek-v4-pro`**, run with reasoning/thinking disabled (injected in
the transport via `extra_body={"thinking": {"type": "disabled"}}`, gated to `deepseek*`).

---

## 8. Validation contract (summary)

`validate_section_ir()` in `section_pipeline.py` is the runtime contract. Beyond the schema
shape it enforces:

- top-level keys are exactly `document`/`sections`/`relations`/`extraction_notes`;
  `extraction_notes.ir_version == "section-ir-0.9"`, `input_mode == "node_census_pipeline"`.
- every unit `type` ∈ `UNIT_TYPES`; none in `FORBIDDEN_UNIT_TYPES`; fields ⊆
  `ALLOWED_FIELDS_BY_TYPE[type]`; `role` (where the type has one) ∈ `ROLE_VOCAB_BY_TYPE[type]`.
- each unit id matches `ID_RE` and is defined exactly once.
- `Finding` and `Measure` provenance non-empty; every provenance marker matches
  `PROVENANCE_SOURCE_RE`.
- every relation `relation` is in `RELATION_MATRIX`, with endpoints of the allowed types,
  resolving to defined units.
- `Measure.scores` non-empty; non-empty `scores[].system_id` resolves to a Method; non-empty
  `scores[].setup_id` resolves to a section-local ExperimentSetup; `setup_ids` (when non-empty)
  point to section-local ExperimentSetups.

Assembly performs lossy-but-safe repairs first, logged to
`extraction_notes.uncertain_assignments` (control-char stripping, role stamping, ExperimentSetup
dedup, id dedup, empty-section drop, provenance-marker normalization, anchor repair, dangling
score-ref blanking, relation-list cleanup, baseline-`evaluates` drop, `covers_entries`
recompute). Coverage is measured against census `must` nodes; an unmaterialized must-node
surfaces in `extraction_notes.uncovered_items`.

---

## Appendix — quick reference

**Unit types (6):** `Document`, `Problem`, `Method`, `ExperimentSetup`, `Measure`, `Finding`.

**Id prefixes:** `doc:` `prb:` `mth:` `exp:` `mea:` `fnd:`.

**Role vocabs:**
- Document — `research_article` `review` `meta_analysis` `methodology` `benchmark_survey`
- Method — `contribution` `component` `builds_on` `compared_against`
- ExperimentSetup — `dataset` `benchmark` `task` `data_split` `inference_protocol` `training_config` `ensembling` `population`
- Finding — `descriptive` `mechanistic` `comparative` `modeling` `ablation_finding` `failure_mode`
- Problem, Measure — *(none)*

**Other enums:** `method_kind` (optional) — `algorithm` `model_architecture` `training_strategy`
`objective_function`; `comparison_direction` — `higher_is_better` `lower_is_better` `target`
`unspecified`; `salience` (census) — `must` `should`.

**Relations (7):** `part_of` `compares_to` `evaluates` `about` `supports` `motivates`
`resolves`. Stage B: `part_of`/`compares_to`/`evaluates`. Stage C: `about`/`supports`
(evidence), `motivates` (problem). Synthesized: `resolves`.
