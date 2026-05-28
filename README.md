# Section-IR Extraction Pipeline

A three-stage scientific literature extraction pipeline that decomposes a paper's scientific-discovery throughline into structured section-IR (`section-ir-0.9`):

```
problem → method → evidence
```

`evidence` is the merged experiment+analysis layer: it carries both what was measured and what those measurements mean, and it hosts the headline contribution finding.

## Pipeline Overview

```
Paper (Markdown)
     │
     ▼
┌─────────────────────────────┐
│  Stage A: Node Census       │  → spine_summary, nodes[] (roles, no relations)
│  (single LLM call)          │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│  Stage B: Relation Pass     │  → global relations[] (structural node↔node edges)
│  (single LLM call)          │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│  Stage C: Content Fill      │  → 3 parallel LLM calls (problem/method/evidence)
│  (parallel, per-section)    │     each returns section units + finding-centric edges
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│  Assembly & Validation      │  → final section-IR JSON (single global relations[])
│  (Python, no LLM)           │
└─────────────────────────────┘
```

Metadata and references are extracted as independent sidecars, in parallel with the node census.

## Directory Structure

```
.
├── section_pipeline.py                  # Main pipeline implementation
├── prompts/section-extraction/
│   ├── node-census.md                   # Stage A prompt (system + user template)
│   ├── relation-pass.md                 # Stage B prompt
│   ├── section-extraction-pass.md       # Stage C shared core (rules common to all sections)
│   ├── section-modules/                 # Self-contained per-section contract injected as section_focus
│   │   ├── problem.md
│   │   ├── method.md
│   │   └── evidence.md
│   └── examples/                        # Section-IR examples
├── schemas/
│   ├── node-census-output.schema.json   # Stage A response_format
│   ├── relation-pass-output.schema.json # Stage B response_format
│   ├── section-problem.schema.json      # Stage C per-section response_format
│   ├── section-method.schema.json
│   └── section-evidence.schema.json
├── tools/
│   ├── generate_section_schemas.py      # Regenerate all schemas from section_pipeline.py constants
│   ├── render_extraction.py             # Render extraction JSON → HTML
│   └── count_extraction.py              # Node/relation counts
├── tests/
│   ├── test_section_pipeline.py         # Unit tests
│   ├── test_section_extraction.py       # LLM smoke test (end-to-end)
│   ├── papers/                          # Test corpus (1-5.md, with §N markers)
│   └── section-extraction-outputs/      # Generated outputs
├── docs/
│   ├── section-ir-0.9-redesign.md       # Active IR design spec (two-level type/role taxonomy)
│   ├── section-ir-0.8-redesign.md       # 0.8 spine delta
│   ├── section-ir-0.7-redesign.md       # 0.7 spec
│   └── section-ir-design.md             # Legacy 0.6 design reference
├── CLAUDE.md                            # Claude Code instructions
└── AGENTS.md                            # Codex / agent instructions (mirrors CLAUDE.md)
```

## How It Works

### Stage A: Node Census

**Prompt:** `prompts/section-extraction/node-census.md`
**Schema:** `schemas/node-census-output.schema.json`

One full-paper call produces:
- `spine_summary` — central contribution + argument flow
- `nodes[]` — a flat list of every load-bearing node, each with a single granular `role` (the coarse `type` Method/ExperimentSetup/Measure and the document root are derived from `role`; the `role` is then carried onto the materialized unit as its fine-grained differentia), a `salience` (`must`/`should`), and **no relations**. Each `node_id` (prefix `mth:`/`exp:`/`mea:`) is reused verbatim as the final unit id.

### Stage B: Relation Pass

**Prompt:** `prompts/section-extraction/relation-pass.md`
**Schema:** `schemas/relation-pass-output.schema.json`

One call over the full paper plus the complete flat node list. It establishes the structural node↔node edges (`part_of`, `compares_to`, `evaluates`) with the whole node set in view — so cross-section composition and measure-subject binding need no forward references and no reconcile crutches. (The metric→dataset edge `measured_on` was removed in 0.9; a Measure binds to its dataset/split via the score row's `setup_id`.)

### Stage C: Parallel Content Fill

**Prompt:** `prompts/section-extraction/section-extraction-pass.md` (shared core) + per-section module
**Schema:** `schemas/section-{section}.schema.json`

The shared core carries only the rules common to every section (identifiers, provenance,
the output envelope, universal hard constraints) and is byte-identical across all section
calls — so the paper text stays in the cross-section prompt cache. Each section module is
self-contained: it declares that section's allowed unit types and their field contracts,
the controlled vocabularies it uses, the relation subset it may author, a worked example, and
its section-specific rules.

For each of the three sections (`problem`, `method`, `evidence`):
1. Load the shared system prompt (universal rules only)
2. Inject the self-contained section module as `section_focus`
3. Build the user prompt with: `spine_summary`, `node_registry` (all nodes), the global `relations[]` from stage B, `section_focus`, and paper text
4. Call LLM with that section's JSON schema as `response_format` (strict: true)
5. Returns `section` (materialized + born units, plus any `about`/`supports`/`motivates` edges it authors)

All three sections extract in parallel (ThreadPoolExecutor, max 5 workers).

### Assembly & Validation

After all sections return:
1. Flatten typed unit arrays into `section.units[]`; merge the stage-B edges with each section's `relations[]` into a single top-level `relations[]`
2. Deterministic repairs (stamp census roles onto materialized units, dedup ExperimentSetups/IDs, drop empty sections, normalize provenance markers, dedup/drop-dangling/drop-invalid relations against the type matrix, synthesize `resolves`, recompute `covers_entries`)
3. Run `validate_section_ir()` — the authoritative runtime contract
4. Save JSON + rendered HTML

## Prompt ↔ Schema Pairing

Each LLM call has a paired prompt + JSON schema enforced via `response_format`:

| Call | Prompt | Schema |
|------|--------|--------|
| Node census | `node-census.md` | `node-census-output.schema.json` |
| Relation pass | `relation-pass.md` | `relation-pass-output.schema.json` |
| Problem section | `section-extraction-pass.md` + `section-modules/problem.md` | `section-problem.schema.json` |
| Method section | `section-extraction-pass.md` + `section-modules/method.md` | `section-method.schema.json` |
| Evidence section | `section-extraction-pass.md` + `section-modules/evidence.md` | `section-evidence.schema.json` |

## Section Modules

Each module is a self-contained contract for its section — allowed unit types and fields,
the vocabularies and relations it uses, a worked example, and its own rules — injected
into the shared core as `section_focus`:

- **problem** — born Problem unit (the single research-problem trunk); authors the `motivates` edge to the contribution.
- **method** — materializes Method nodes (description, optional method_kind, formulas, objective_function, inputs/outputs, implementation_notes).
- **evidence** — merged experiment+analysis: materializes Measure and substrate ExperimentSetup nodes (scores, unit, comparison_direction), creates born configuration ExperimentSetup and Finding units (including the headline contribution finding), sets `Measure.setup_ids`, and authors `about` / `supports` edges. The deployable-vs-diagnostic call is made once, with the whole results table in view.

## Running

### Unit tests

```bash
.venv/bin/python -m unittest tests.test_section_pipeline
```

### LLM smoke test

```bash
.venv/bin/python tests/test_section_extraction.py --papers 4 5
```

Default LLM smoke-test settings:
- Python: use the project-local `.venv/bin/python`.
- API key: loaded from `.env` as `API_KEY` or `API-KEY`.
- Model: `gemini-3-flash-preview` unless `MODEL` is set.
- Primary base URL: `http://35.220.164.252:3888/v1`.
- Fallback base URL: if the primary endpoint is unreachable, retry with `--base-url http://34.13.73.248:3888/v1`.

Options:
- `--model MODEL` — LLM model name
- `--base-url URL` — API endpoint
- `--allow-validation-issues` — don't fail on validation errors

### Render output

```bash
python tools/render_extraction.py tests/section-extraction-outputs/paper4_extraction.json
```

### Regenerate schemas

```bash
python tools/generate_section_schemas.py
```

Schemas are generated from constants in `section_pipeline.py` — never hand-edit the JSON.

### Environment variables

- `BASE_URL` — API endpoint override; default is `http://35.220.164.252:3888/v1`
- `API_KEY` or `API-KEY` — API authentication, usually loaded from `.env`
- `MODEL` — model name override; default is `gemini-3-flash-preview`

## IR Version

Current: `section-ir-0.9` (`extraction_notes.input_mode` is `node_census_pipeline`)

### Allowed Unit Types

`Document`, `Problem`, `Method`, `ExperimentSetup`, `Measure`, `Finding`

Every unit carries a generic `type` (above) plus a fine-grained `role` (the AI/ML differentia; `Problem` and `Measure` carry none). `Method`, the substrate `ExperimentSetup` roles (`dataset`/`benchmark`/`task`), and `Measure` are census nodes; `Problem`, `Finding`, and the configuration `ExperimentSetup` roles (`data_split`/`inference_protocol`/`training_config`/`ensembling`/`population`) are born during content fill. 0.9 renamed `Metric → Measure`, `Claim → Finding`, and merged `Entity ⊎ Setting → ExperimentSetup`.

### Allowed Relations (global)

`relations[]` is a single top-level edge list; every edge resolves to a unit defined anywhere.

| relation | source → target | authored by |
|---|---|---|
| `part_of` | {Method, ExperimentSetup} → {Method, ExperimentSetup} | relation pass |
| `compares_to` | {Method, ExperimentSetup, Measure} → same | relation pass |
| `evaluates` | Measure → Method | relation pass |
| `about` | Finding → {Method, ExperimentSetup, Measure} | content (evidence) |
| `supports` | {Measure, Finding} → Finding | content (evidence) |
| `motivates` | Problem → {Method, ExperimentSetup} | content (problem) |
| `resolves` | Finding → Problem | assembly (synthesized) |

(`measured_on` was removed in 0.9 — a Measure binds to its dataset/split via each score row's `setup_id` → ExperimentSetup, not a global edge.)

## Validation

The Python `validate_section_ir()` function in `section_pipeline.py` is the authoritative runtime contract. It checks:
- Unit type-specific required fields and per-type `role` vocabulary
- The global relation matrix (source/target type pairing); endpoints must resolve to a unit defined anywhere
- ID uniqueness and referential integrity
- Provenance requirements (Finding and Measure must have non-empty provenance)
- Measure constraints (`name`, `unit`, non-empty `scores`; `setup_ids` must point to section-local `ExperimentSetup` units; per-row `scores[].system_id` resolves to a Method and `scores[].setup_id` to a section-local ExperimentSetup; no `subject_id` / `evaluated_on` fields)

## Archived Material

Historical paradigm-based code, design discussions, and legacy utilities are in `archive/`.
