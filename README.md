# Section-IR Extraction Pipeline

A two-stage scientific literature extraction pipeline that decomposes a paper's argumentative spine into structured section-IR:

```
context and gap → claim → method → experiment → analysis
```

## Pipeline Overview

```
Paper (Markdown)
     │
     ▼
┌─────────────────────────────┐
│  Stage 1: Planning Pass     │  → spine_summary, section_plans[]
│  (single LLM call)          │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│  Stage 2: Section Extraction│  → 5 parallel LLM calls (one per section)
│  (parallel, per-section)    │     each returns section
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│  Assembly & Validation      │  → final section-IR JSON
│  (Python, no LLM)           │
└─────────────────────────────┘
```

## Directory Structure

```
.
├── section_pipeline.py                  # Main pipeline implementation
├── prompts/section-extraction/
│   ├── planning-pass.md                 # Stage 1 prompt (system + user template)
│   ├── section-extraction-pass.md       # Stage 2 shared core (rules common to all sections)
│   ├── section-modules/                 # Self-contained per-section contract injected as section_focus
│   │   ├── context.md
│   │   ├── claim.md
│   │   ├── method.md
│   │   ├── experiment.md
│   │   └── analysis.md
│   └── examples/                        # Section-IR examples
├── schemas/
│   ├── planning-output.schema.json      # Stage 1 response_format
│   ├── section-context.schema.json      # Stage 2 per-section response_format
│   ├── section-claim.schema.json
│   ├── section-method.schema.json
│   ├── section-experiment.schema.json
│   └── section-analysis.schema.json
├── tools/
│   └── render_extraction.py             # Render extraction JSON → HTML
├── tests/
│   ├── test_section_pipeline.py         # Unit tests
│   ├── test_section_extraction.py       # LLM smoke test (end-to-end)
│   ├── papers/                          # Test corpus (1-5.md, with §N markers)
│   └── section-extraction-outputs/      # Generated outputs
├── docs/
│   └── section-ir-design.md             # IR design reference
├── CLAUDE.md                            # Claude Code instructions
└── AGENTS.md                            # Codex instructions
```

## How It Works

### Stage 1: Planning Pass

**Prompt:** `prompts/section-extraction/planning-pass.md`
**Schema:** `schemas/planning-output.schema.json`

Takes the full paper and produces:
- `spine_summary` — one-sentence contribution + argument flow
- `section_plans[]` — per-section extraction targets with item IDs, priorities, source scopes

### Stage 2: Parallel Section Extraction

**Prompt:** `prompts/section-extraction/section-extraction-pass.md` (shared core) + per-section module
**Schema:** `schemas/section-{section}.schema.json`

The shared core carries only the rules common to every section (identifiers, provenance,
the output envelope, universal hard constraints) and is byte-identical across all section
calls — so the paper text stays in the cross-section prompt cache. Each section module is
self-contained: it declares that section's allowed unit types and their field contracts,
the controlled vocabularies it uses, the link relations it may emit, a worked example, and
its section-specific rules.

For each planned section (typically 5, one per section):
1. Load the shared system prompt (universal rules only)
2. Inject the self-contained section module via `{{section_guidance}}` as `section_focus`
3. Build the user prompt with: `id_registry`, `section_plan`, `section_focus`, and paper text
4. Call LLM with that section's JSON schema as `response_format` (strict: true)
5. Returns `section` (units + local links)

All 5 sections extract in parallel (ThreadPoolExecutor, max 5 workers).

### Assembly & Validation

After all sections return:
1. Assemble into final section-IR structure (document, sections, extraction_notes)
2. Run `validate_section_ir()` — the authoritative runtime contract
3. Save JSON + rendered HTML

## Prompt ↔ Schema Pairing

Each LLM call has a paired prompt + JSON schema enforced via `response_format`:

| Call | Prompt | Schema |
|------|--------|--------|
| Planning | `planning-pass.md` | `planning-output.schema.json` |
| Context section | `section-extraction-pass.md` + `section-modules/context.md` | `section-context.schema.json` |
| Claim section | `section-extraction-pass.md` + `section-modules/claim.md` | `section-claim.schema.json` |
| Method section | `section-extraction-pass.md` + `section-modules/method.md` | `section-method.schema.json` |
| Experiment section | `section-extraction-pass.md` + `section-modules/experiment.md` | `section-experiment.schema.json` |
| Analysis section | `section-extraction-pass.md` + `section-modules/analysis.md` | `section-analysis.schema.json` |

## Section Modules

Each module is a self-contained contract for its section — allowed unit types and fields,
the vocabularies and link relations it uses, a worked example, and its own rules — injected
into the shared core as `section_focus`:

- **context** — Extracts: Context (gap/background/motivation).
- **claim** — Extracts: Claim (1-3 tight contributions).
- **method** — Extracts: Method.
- **experiment** — Extracts: target-method Metric, Condition, Entity (datasets/benchmarks only).
- **analysis** — Extracts: Claim + Metric pairs for ablations/limits, plus optional Entity.

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

Fallback example:

```bash
.venv/bin/python tests/test_section_extraction.py --papers 4 5 --base-url http://34.13.73.248:3888/v1
```

### Environment variables

- `BASE_URL` — API endpoint override; default is `http://35.220.164.252:3888/v1`
- `API_KEY` or `API-KEY` — API authentication, usually loaded from `.env`
- `MODEL` — model name override; default is `gemini-3-flash-preview`

## IR Version

Current: `section-ir-0.6`

### Allowed Unit Types

`Document`, `Entity`, `Method`, `Claim`, `Context`, `Condition`, `Metric`

### Allowed Link Relations

`supports`, `part_of`, `compares_to`

## Validation

The Python `validate_section_ir()` function in `section_pipeline.py` is the authoritative runtime contract. It checks:
- Unit type-specific required fields
- Link direction constraints (source/target type matrix)
- ID uniqueness and referential integrity
- Provenance requirements (Claim and Metric must have non-empty provenance)
- Metric constraints (subject_id, context_ids pointing to Context/Condition when present; experiment Metrics require non-empty context_ids; optional evaluated_on must reference section-local dataset/benchmark Entities)
- Section-local link endpoints

## Archived Material

Historical paradigm-based code, design discussions, and legacy utilities are in `archive/`.
