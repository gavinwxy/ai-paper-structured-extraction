# Section-IR Extraction Pipeline

A three-stage LLM pipeline that reads a scientific paper (Markdown) and extracts its
**scientific-discovery throughline** into structured **section-IR** (`section-ir-0.12`):

```
problem → method → evidence
```

- **problem** — the single research problem the paper addresses (one trunk; the old multi-tag
  `context` section collapsed to one).
- **method** — the technical apparatus: the contribution and its components, plus the prior-art
  and baseline methods it builds on or competes with.
- **evidence** — the merged experiment + analysis layer. It carries both *what was measured*
  (`Measure`, `ExperimentSetup`) and *what those measurements mean* (`Finding`), and it hosts the
  **headline contribution finding** — so there is no separate `claim` section.

The discovery arc closes with a synthesized `resolves` edge from the headline finding back to the
problem, and the one-sentence contribution is lifted onto the `Document` as `thesis`.

The output is a single JSON object with four top-level keys — `document`, `sections`, `relations`,
`extraction_notes` — described under [The section-IR data model](#the-section-ir-data-model).

## Pipeline overview

```
                         Paper (Markdown, with [§N] markers)
                                        │
            ┌───────────────────────────┼───────────────────────────┐
            ▼                            ▼                            ▼
   ┌─────────────────┐         ┌──────────────────────┐     ┌──────────────────┐
   │  Metadata       │         │ Stage A: Node Census │     │  References      │
   │  (sidecar)      │         │ (single LLM call)    │     │  (sidecar)       │
   └─────────────────┘         └──────────────────────┘     └──────────────────┘
   title/authors/year/venue   spine_summary + nodes[]       bibliography (cite_keys
                              (roles, salience; NO edges)    later joined to units)
                                        │
                                        ▼
                          ┌──────────────────────────────┐
                          │ Stage B: Relation Pass       │  → global relations[]
                          │ (single LLM call)            │    (structural node↔node edges
                          └──────────────────────────────┘     over the full node set)
                                        │
                                        ▼
                          ┌──────────────────────────────┐
                          │ Stage C: Content Fill        │  → 3 parallel LLM calls
                          │ (parallel, per-section)      │    problem · method · evidence
                          └──────────────────────────────┘    (units + finding-centric edges)
                                        │
                                        ▼
                          ┌──────────────────────────────┐
                          │ Assembly & Validation        │  → final section-IR JSON
                          │ (Python, no LLM)             │    (one global relations[])
                          └──────────────────────────────┘
```

Metadata and references are extracted as independent sidecars, in parallel with the node census.

## Installation

Requires **Python ≥ 3.10**. Dependencies are managed with [uv](https://docs.astral.sh/uv/)
(`uv.lock` is committed); plain `venv` + `pip` works too. There are only two runtime
dependencies: `openai` (the OpenAI-compatible client) and `python-dotenv`.

```bash
uv sync                         # create .venv and install from uv.lock
# or:
python -m venv .venv && .venv/bin/pip install "openai>=2.31.0" "python-dotenv>=1.2.2"
```

Create a `.env` with your API key:

```bash
API_KEY=sk-...                  # API-KEY (with a hyphen) is also accepted
# optional overrides:
# BASE_URL=http://35.220.164.252:3888/v1
# MODEL=deepseek-v4-pro
```

The default endpoint is an OpenAI-compatible proxy (`http://35.220.164.252:3888/v1`); a fallback
proxy lives at `http://34.13.73.248:3888/v1`. You can also point at official DeepSeek
(`https://api.deepseek.com`) with a DeepSeek key — see [Model compatibility](#model-compatibility).

## Quickstart

### Batch extraction (the production path)

Extract every paper in a directory:

```bash
.venv/bin/python -m production <input_dir> <output_dir> --model deepseek-v4-pro
```

`<input_dir>` is a **flat** directory of `*.md` papers (discovery is non-recursive). Each paper
gets its own output subdirectory holding the staged intermediates and the final result:

```
<output_dir>/<paper_id>/
├── 01_census.json                              # stage A
├── 02_metadata.json                            # title/authors/year/venue sidecar
├── 03_references.json                          # bibliography sidecar (+ reconciled provides_unit_ids)
├── 04_relations.json                           # stage B
├── 05_sections/{problem,method,evidence}.json  # stage C (per section)
├── 06_extraction.json                          # ← final assembled section-IR
├── 07_validation.json                          # validation issues ([] = clean)
├── extraction.html                             # rendered view
└── status.json
<output_dir>/run_summary.json                   # batch-level summary
```

Runs are **resumable** — already-completed papers are skipped on re-run; pass `--force` to
reprocess. Common flags:

| Flag | Default | Meaning |
|---|---|---|
| `--limit N` | `0` (all) | process at most N papers |
| `--paper-concurrency N` | `10` | papers in flight at once |
| `--llm-concurrency N` | `30` | concurrent LLM calls |
| `--max-tokens N` | `32768` | output budget for content sections |
| `--planning-max-tokens N` | `24576` | budget for census / relations / metadata / references |
| `--max-retries N` | `3` | retries per LLM call (re-issues on malformed JSON) |
| `--force` | off | ignore resumability, reprocess everything |
| `--no-verify-scores` | on | disable the score-fidelity audit (see below) |
| `--no-warm-content-cache` | on (warming) | disable content-cache warming; run the three content sections fully concurrently instead of warming the shared prefix first (see below) |
| `--no-blob-primary-evidence` | on (blob mode) | disable section-ir-0.12 blob-primary evidence and revert to full transcription: with blob mode on, the evidence pass points at result tables by `[§N]` marker and transcribes only the contribution method's rows; baselines + ablation grids stay in the code-sliced verbatim table blob (see below) |
| `--no-blob-primary-references` | on (blob mode) | disable section-ir-0.12 blob-primary references and revert to full transcription: with blob mode on, the references pass transcribes only graph-linked references; the full bibliography is code-sliced verbatim into `extraction_notes.references_blob` and background refs live there (see below) |

Run `.venv/bin/python -m production --help` for the full set.

**Content-cache warming** (cost lever, **on by default**; disable with `--no-warm-content-cache`).
The three content sections (problem/method/evidence) share a byte-identical paper-inclusive prompt
prefix but would otherwise fire concurrently, so the provider's automatic prefix-cache is cold when
they race and the paper is re-sent uncached up to 3×. Warming runs the cheapest section (`problem`)
to completion first to warm that prefix; the other two then cache it. On a **cold** proxy this
recovers ~25 pts of content-section prompt into cache (≈6% of effective cost / ≈3–4% real $ at the
deepseek-v4-pro rate card), validated 12/12 papers; on an already-warm proxy it is redundant but
harmless (it never worsens cache — only `method`/`evidence` improve). It costs ~one section of serial
latency per paper, so pass `--no-warm-content-cache` for latency-priority runs or when the proxy is
demonstrably warm. Inspect `relations` cached% in the telemetry to tell whether a proxy is warm
(high ⇒ warming redundant); see `tools/token_cost_report.py --cache`.

**Blob-primary evidence** (completion-cost lever, **on by default**; disable with
`--no-blob-primary-evidence`). Result-collection data is the heaviest part of the output (score rows
dominate completion tokens), and most of those rows are *baselines* — competitor numbers the LLM
laboriously (and sometimes lossily) retypes. In blob-primary mode the evidence pass instead **points**
at each result table by its `[§N]` block marker (`source_table_marker`/`caption_marker`); code slices
that table and caption verbatim into `extraction_notes.source_tables`, so the full leaderboard and
every ablation grid are preserved **without** transcription tokens or transcription error. The LLM
transcribes only the **contribution method's own** rows (`table_role: main_result`) or none at all
(`table_role: ablation`), emits a `headline_result` one-liner as a durable text backstop, and mounts
the findings a table evidences via `Measure.finding_ids` (replacing the `Finding`↔`Measure` edges).
The contribution rows stay structured and verifier-checked, so the queryable high-value core is
intact at near-zero cost. Validated in two A/Bs (−12.9% and −11.2% total cost, 20/20 valid, no loss)
before the default flip. With the flag off, the evidence schema is stripped back to the 0.11 shape
at runtime (no blob fields, legacy `scores` wording), so the opt-out arm is a true pre-blob baseline.

**Blob-primary references** (completion-cost lever, **on by default**; disable with
`--no-blob-primary-references`). The references analog of blob-primary evidence: code slices the
full bibliography verbatim into `extraction_notes.references_blob` (header located among broadened
candidates — numbered/bold/bare headers included — and the densest-in-references candidate wins);
the LLM transcribes only the **graph-linked** references (those with a structural role —
`builds_on`/`uses`/`compares_to` — or a provided name, ~40% of refs), and background references
live in the blob. The renderer shows the structured linked entries above the verbatim bibliography.
Validated in a warm A/B (references pass −62%, total −12.2%, 20/20 valid, no link loss). When no
bibliography can be sliced, assembly records an `uncertain_assignments` warning and the renderer
flags the structured list as graph-linked-only.

### End-to-end smoke test (single papers)

```bash
.venv/bin/python tests/test_section_extraction.py --papers 4 5
```

This reads `tests/papers/{id}.md`. That directory **may be empty in a fresh checkout** — populate
it, or drive extraction from `tests/benchmark/` (real papers with `[§N]` markers, addressed by
numeric id) via the batch path above. Add `--allow-validation-issues` to keep going past
validation errors. Useful flags: `--model`, `--base-url`, `--max-tokens` (planning, default 16384),
`--section-max-tokens` (default 32768).

If the primary base URL is unreachable, retry with `--base-url http://34.13.73.248:3888/v1`.

### Unit tests

```bash
.venv/bin/python -m unittest tests.test_section_pipeline
```

### Render an extraction to HTML

```bash
python tools/render_extraction.py <output_dir>/<paper_id>/06_extraction.json
```

The renderer is schema-aware for `anchor_id` sections, colors units by section membership, and
shows reference badges/links.

### Regenerate schemas

```bash
python tools/generate_section_schemas.py
```

Most JSON schemas are generated from constants in `section_pipeline.py`. The exception is the
blob-primary fields in `section-evidence.schema.json`, which are hand-edited into the committed
schema first (the committed `schemas/*.json` are the source of truth). If you change a schema, port
any hand-edit back into the `section_pipeline.py` constants, **then** re-run the generator and verify
`git diff schemas/` shows only the changes you intended — regeneration clobbers anything not ported.
(`metadata-output.schema.json` and `references-output.schema.json` are hand-maintained and are not
produced by the generator.)

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `API_KEY` / `API-KEY` | — | API authentication, loaded from `.env` |
| `BASE_URL` | `http://35.220.164.252:3888/v1` | OpenAI-compatible endpoint |
| `MODEL` | `deepseek-v4-pro` | extraction model |

Token budgets default to **32K** for content sections and **24K** for the single-shot
planning/aux calls (census, relation pass, metadata, references); both are tunable on the CLI.

### Model compatibility

The default model is **`deepseek-v4-pro`**, run with **reasoning/thinking disabled** (faster, and
reasoning gave no quality lift on this corpus). Thinking-off is enforced in the transport, not the
model name: every call injects `extra_body={"thinking": {"type": "disabled"}}` when the model name
matches `deepseek*` (both the sync `_call_llm` in `section_pipeline.py` and the async
`production/llm.py`).

Structured output is **model-adaptive**, detected from the model name (`_structured_output_mode`):

- **json_schema mode** (any non-`deepseek*` model, e.g. the Gemini/OpenAI-compatible proxy) — the
  per-stage JSON schema is sent in `response_format` with `strict: true`, so decoding is
  schema-constrained and the prompts are unchanged.
- **json_object mode** (the default, `deepseek*`) — DeepSeek rejects `response_format: json_schema`,
  so the pipeline sends `{"type": "json_object"}` and renders the *same* schema into the prompt as
  an **OUTPUT FORMAT CONTRACT** (`schema_to_prompt_spec`): keys, required/optional fields, enum
  values, id patterns — the constraints strict decoding used to enforce. The contract is derived
  from the schema, so it never drifts, and the deterministic [assembly repairs](#assembly--validation)
  absorb the benign quirks strict decoding would have rejected. (DeepSeek also rejects the proxy's
  cache-key kwargs, so they are omitted for `deepseek*`.)

To run against official DeepSeek (smaller output ceiling — lower the budgets if a call 400s or
truncates):

```bash
.venv/bin/python -m production <in> <out> \
  --model deepseek-v4-pro --base-url https://api.deepseek.com --max-tokens 8192
```

(`API-KEY` in `.env` must then be your DeepSeek key.)

## How it works

### Stage A — Node Census

**Prompt:** `prompts/section-extraction/node-census.md` · **Schema:**
`schemas/node-census-output.schema.json`

One full-paper call produces:

- `spine_summary` — the central contribution and argument flow (and, optionally,
  `headline_result`, the paper's headline established result).
- `nodes[]` — a flat list of every load-bearing node, each with a single granular **`role`**, a
  **`salience`** (`must`/`should`), and **no relations**. The coarse `type`
  (`Method`/`ExperimentSetup`/`Measure`/`Finding`) and the document root are *derived* from `role`;
  the `role` is then carried onto the materialized unit as its fine-grained differentia. Each
  `node_id` prefix (`mth:`/`exp:`/`mea:`/`fnd:`) follows from the role's type and is reused
  verbatim as the final unit id.

Two scoping rules: a **named model is a Method** (`builds_on`/`compared_against`), never a testbed
node; **apparatus is not a node** (hardware and metric-scoring models are dropped). **Baselines are
captured in full** — every compared-against system is a lightweight `compared_against` Method, and
its number is a row in the relevant `Measure.scores[]`. Prior-art/testbed nodes also carry
`cite_keys` (the in-text bibliography marker), the deterministic join key for reference linking.

### Stage B — Relation Pass

**Prompt:** `prompts/section-extraction/relation-pass.md` · **Schema:**
`schemas/relation-pass-output.schema.json`

One call over the full paper plus the complete flat node list. It establishes the structural
node↔node edges (`part_of`, `builds_on`, `uses`, `assumes`, `co_contribution`, `compares_to`,
`evaluates`) with the whole node set in view — so cross-section composition and measure-subject
binding need no forward references and no reconcile crutches.

### Stage C — Parallel Content Fill

**Prompt:** `prompts/section-extraction/section-extraction-pass.md` (shared core) + per-section
module · **Schema:** `schemas/section-{section}.schema.json`

The shared core carries only the rules common to every section (identifiers, provenance format, the
output envelope, universal hard constraints) and is **byte-identical** across all section calls — so
the paper text stays in the cross-section prompt cache. Each per-section module
(`prompts/section-extraction/section-modules/{problem,method,evidence}.md`; the evidence module is
`evidence-blob.md` by default, or `evidence.md` with `--no-blob-primary-evidence`) is a self-contained
contract: that section's allowed unit types and field contracts, the controlled vocabularies and
relation subset it uses, a worked example, and its section-specific rules.

For each of the three sections:

1. Load the shared system prompt (universal rules only).
2. Inject the self-contained section module as `section_focus`.
3. Build the user prompt with `spine_summary`, `node_registry` (all nodes), the global `relations[]`
   from stage B, `section_focus`, and the paper text.
4. Call the LLM with that section's response format.
5. Get back `section` — the materialized census units it owns plus its born units, and any
   `about`/`supports` (evidence) or `motivates` (problem) edges it authors.

All three sections run in parallel.

### Sidecars — metadata & references

In parallel with the census, two single-shot calls extract `document` metadata (title, authors,
year, venue) and the bibliography. After assembly, `reconcile_reference_units` backfills each
reference's `relation.provides_unit_ids` by matching the reference to a materialized node — first
by `cite_keys` (exact, grounded in the paper's own citation), then by a unique name match — and
(FG-12) backfills contribution→target unit edges from reference roles. Reference roles use the same
vocabulary as the unit-graph edges — a citation role is an edge-in-waiting: `builds_on`/`uses`/
`compares_to` each become the edge of the same name, while `background` is the lone context-only
role with no edge. Each backfilled edge is tagged `origin: "reference"` so a citation-derived edge
can be told apart from a natively-authored one.

### Assembly & Validation

After all sections return, `assemble_extraction` (Python, no LLM):

1. Flattens the typed unit arrays into `section.units[]`, and merges the stage-B edges with each
   section's `relations[]` into a single top-level `relations[]`.
2. Runs deterministic, lossy-but-safe repairs (logged to `extraction_notes.uncertain_assignments`):
   stamp census roles onto materialized units; sanitize control chars; dedup ExperimentSetups and
   duplicate ids; drop empty sections; normalize provenance markers; repair score refs and anchors;
   normalize degenerate optional enums; dedup / drop-dangling / drop-invalid relations against the
   type matrix; **synthesize the `resolves` edge**; derive `Document.role` (FG-3), `thesis`, and
   `headline_result`; recompute `covers_entries`.
3. Runs `validate_section_ir()` — the authoritative runtime contract.
4. Saves the JSON and the rendered HTML.

Assembly also captures every verbatim inline `<table>` blob (with its nearest `[§N]` anchor and
`**Table k**` caption) into `extraction_notes.source_tables` — a lossless, deterministic
source-of-truth for audit/fallback; the model never re-transcribes it.

Using that capture, assembly then runs a **score-fidelity audit** (`extraction_notes.score_fidelity`,
on by default; disable with `--no-verify-scores`): every transcribed score `value` is cross-checked
**by canonical number** against the source-table cells. A value that is in no table while its
Measure's other values are (`flags[].kind = value_not_in_table`, sub-classified by `in_paper`) is a
candidate transcription error; a Measure with no table matches at all is recorded as prose-derived
(`measures_no_table`). It is matched by value, never by cell position, so it cannot be fooled by
rowspan/colspan layout, and it writes only this notes block — never touching units, scores, or
relations.

Coverage is measured against the census `must` nodes; an unmaterialized must-node surfaces in
`extraction_notes.uncovered_items`.

## The section-IR data model

### Unit types & the two-level taxonomy

Every unit carries two classificatory axes: a small, discipline-neutral **`type`** (anchored on the
scientific method — *Identify a Problem → Design an Experiment → Collect Results → Construct a
Conclusion*) and a fine-grained **`role`** (the AI/ML-specific differentia). Swapping disciplines
means swapping the per-type role vocabularies, never the `type` set.

Six allowed unit types:

`Document` · `Problem` · `Method` · `ExperimentSetup` · `Measure` · `Finding`

Per-type `role` vocabulary (`Problem` and `Measure` carry no `role`):

| type | `role` ∈ |
|---|---|
| `Document` | `research_article`, `review`, `meta_analysis`, `methodology`, `benchmark_survey` (derived from the contribution) |
| `Method` | `contribution`, `component`, `builds_on`, `compared_against` |
| `ExperimentSetup` | **substrate** `dataset`, `benchmark`, `task`, `theoretical_setting`, `structural_class` (+ `contribution_resource`, the dataset/benchmark root) · **configuration** `data_split`, `inference_protocol`, `training_config`, `ensembling`, `population` |
| `Finding` | `descriptive`, `mechanistic`, `comparative`, `modeling`, `ablation_finding`, `failure_mode`, `theorem`, `lemma`, `bound` |

`Method`, the substrate `ExperimentSetup` roles, and `Measure` are **census nodes** (role-tagged in
stage A). `Problem`, `Finding`, and the configuration `ExperimentSetup` roles are **born** during
content fill — except the one `contribution_finding` root, which is a census node the evidence
section materializes. `Method` also carries an optional structural `method_kind ∈ {algorithm,
model_architecture, training_strategy, objective_function, resource, taxonomy, theorem, lemma, bound,
definition}`, orthogonal to the argumentative `role`.

### Contribution roots

At least one census node is a **root** — the paper's primary deliverable. There are three shapes:

| census role | unit type | id prefix | shape |
|---|---|---|---|
| `contribution` | `Method` | `mth:` | a proposed method / algorithm / model |
| `contribution_resource` | `ExperimentSetup` | `exp:` | a benchmark / dataset deliverable (FG-1) |
| `contribution_finding` | `Finding` | `fnd:` | a result / finding (an analysis paper with no proposed artifact; FG-5) |

Normally exactly one root; a paper with **co-equal primary contributions** (FG-7) tags each as a
root, and they are linked by `co_contribution`.

### Relations (global)

`relations[]` is a single top-level edge list; every edge resolves to a unit defined anywhere.

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

The matrix lives in `RELATION_MATRIX` in `section_pipeline.py`. `motivates` opens the discovery arc
(Problem → contribution) and `resolves` closes it (headline Finding → Problem); the latter joins two
units born in different parallel sections, so assembly synthesizes it from the contribution-node
join rather than any section authoring it.

## Prompt ↔ schema pairing

Each LLM call has a paired prompt + JSON schema:

| Call | Prompt | Schema |
|------|--------|--------|
| Node census | `node-census.md` | `node-census-output.schema.json` |
| Relation pass | `relation-pass.md` | `relation-pass-output.schema.json` |
| Problem section | `section-extraction-pass.md` + `section-modules/problem.md` | `section-problem.schema.json` |
| Method section | `section-extraction-pass.md` + `section-modules/method.md` | `section-method.schema.json` |
| Evidence section | `section-extraction-pass.md` + `section-modules/evidence-blob.md` (default; `evidence.md` with `--no-blob-primary-evidence`) | `section-evidence.schema.json` |
| Metadata (sidecar) | `metadata-extraction.md` | `metadata-output.schema.json` |
| References (sidecar) | `references-extraction-blob.md` (default; `references-extraction.md` with `--no-blob-primary-references`) | `references-output.schema.json` |

In json_object mode the schema is rendered into the prompt as the OUTPUT FORMAT CONTRACT instead of
sent as `response_format` — see [Model compatibility](#model-compatibility).

## Directory structure

```
.
├── section_pipeline.py                  # Core pipeline + assembly + validation; run_pipeline() is the entrypoint
├── production/                          # Async batch runner (python -m production)
│   ├── cli.py  config.py  runner.py     #   argument parsing, config, batch orchestration
│   ├── worker.py                        #   per-paper pipeline with staged intermediate saves
│   ├── llm.py  outputs.py  progress.py  #   async transport, atomic writes, progress
├── prompts/
│   ├── metadata-extraction.md           # Metadata sidecar prompt
│   ├── references-extraction.md         # References sidecar prompt (--no-blob-primary-references)
│   ├── references-extraction-blob.md    # References sidecar prompt (blob-primary, default)
│   └── section-extraction/
│       ├── node-census.md               # Stage A prompt
│       ├── relation-pass.md             # Stage B prompt
│       ├── section-extraction-pass.md   # Stage C shared core (rules common to all sections)
│       └── section-modules/             # Self-contained per-section contracts (section_focus)
│           ├── problem.md  method.md  evidence.md   # evidence.md = --no-blob-primary-evidence
│           └── evidence-blob.md                     # blob-primary evidence (default)
├── schemas/                             # JSON schemas (generated; evidence schema's blob-primary fields are hand-edited — see "Regenerate schemas")
│   ├── node-census-output.schema.json   relation-pass-output.schema.json
│   ├── section-{problem,method,evidence}.schema.json
│   └── metadata-output.schema.json      references-output.schema.json
├── tools/
│   ├── generate_section_schemas.py      # Regenerate all schemas from section_pipeline.py constants
│   ├── render_extraction.py             # Render extraction JSON → HTML
│   ├── reference_formatter.py           # Render-time rule-based bibliography prettifier (used by render_extraction.py)
│   ├── count_extraction.py              # Node/relation counts
│   ├── relink_references.py             # Replay reference reconcile over an existing batch (in place)
│   ├── ab_reference_roles.py            # A/B-test the references-stage citation-relation vocab
│   └── token_cost_report.py             # Per-stage token/cost report + prompt-cache diagnosis (--cache)
└── tests/                               # Local test harness + corpus (not version-controlled)
    ├── test_section_pipeline.py         #   unit tests
    ├── test_section_extraction.py       #   end-to-end LLM smoke test (reads tests/papers/{id}.md)
    └── benchmark/                       #   real papers (NNN_*.md, with [§N] markers) for the batch path
```

## Validation

`validate_section_ir()` in `section_pipeline.py` is the authoritative runtime contract. It checks:

- Unit type-specific required fields and the per-type `role` vocabulary.
- The global relation matrix (source/target type pairing); endpoints must resolve to a unit defined
  anywhere.
- ID uniqueness and referential integrity.
- Provenance — every `Finding` and `Measure` must have non-empty provenance.
- `Measure` constraints — `name`, `unit`, non-empty `scores`, and a `setup_ids` list (which must be
  present but may be empty — an ablation measure may carry none). Each score row is
  `{variant, value, variance, system_id, setup_id}` plus optional FG-6 `opponent_id`/`judge_id` for
  pairwise/judge rows; a non-empty `system_id` must resolve to a `Method` and a non-empty `setup_id`
  to a section-local `ExperimentSetup`. `setup_ids` entries must point to section-local
  `ExperimentSetup` units.

## Versioning

Current IR version: **`section-ir-0.12`** (`extraction_notes.input_mode = node_census_pipeline`).

0.12 is the **blob-primary** revision, in three parts (the first two **on by default**, with
`--no-blob-primary-evidence` / `--no-blob-primary-references` opting out):

- **Blob-primary evidence**: a results Measure may point at its source `<table>` by `[§N]` marker
  (`source_table_marker`/`caption_marker`) and carry only the contribution method's own score rows
  (`table_role: main_result`) or none at all (`table_role: ablation`), with the compared-against
  baselines and whole ablation grids left in the code-sliced verbatim table blob rather than
  transcribed. A `headline_result` one-liner backstops the contribution number and `finding_ids`
  mounts the Findings a table evidences (replacing the Finding↔Measure edges).
- **Blob-primary references**: the references pass transcribes only graph-linked references; the
  full bibliography is code-sliced verbatim into `extraction_notes.references_blob`
  (`extraction_notes.blob_primary_references` marks the mode) and background refs live there.
- **Lean formulas**: the per-symbol `{symbol, description}` glossary was dropped from Method
  `formulas[]`/`objective_function` (~25% of method output, prose with no graph consumer); the
  equations themselves are kept.

0.12 is additive over 0.11 for every new Measure field (all optional), **except**: the `ir_version`
string, the relaxed rule that a Measure with a `source_table_marker` may carry empty `scores`, and
the lean-formulas drop (a 0.11 `formulas[].symbols` array is no longer in the schema — runtime
validation still tolerates it).

0.11 **unifies** the references-stage citation roles onto the unit-graph edge vocabulary — a
citation role is an edge-in-waiting: `extends`→`builds_on`, `uses_component`→`uses`,
`compares`→`compares_to`, with `background` unchanged as the lone context-only role (no edge). Each
reference-backfilled edge is tagged `origin: "reference"` so it can be told apart from a
natively-authored edge. It is additive over 0.10 except the references `roles` enum values and the
`ir_version` string; re-run the references stage to migrate a 0.10 corpus.

0.10 is an **additive generalization** of 0.9 — 0.9-shaped output stays structurally valid except
the `ir_version` string. It stops the empirical-CV monoculture from coercing other genres (FG-1…
FG-12): a non-Method contribution (`contribution_resource`), a theory home (`method_kind +=
theorem/lemma/bound/definition`, `Finding.role += theorem/lemma/bound`, symbolic score values,
`assumes`), a derived `Document.role`, the `builds_on`/`uses`/`co_contribution` edges, non-leaderboard
evaluation (pairwise/judge score fields, multi-objective measures), a Finding-as-root analysis paper,
an optional Finding quantitative payload, and reference-role edge backfill.

## Design notes & archived material

The data model is specified in [The section-IR data model](#the-section-ir-data-model) above; the
constants in `section_pipeline.py` (`RELATION_MATRIX`, `ROLE_VOCAB_BY_TYPE`, `UNIT_TYPES`, …) are the
authoritative source from which the JSON schemas are generated.

Historical paradigm-based code and legacy utilities are in `archive/`. Do not treat archived
material as active implementation guidance.
