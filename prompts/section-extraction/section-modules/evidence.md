SECTION FOCUS: evidence (blob-primary)

Capture the paper's evaluation layer in one pass: **what was measured** (results, transfer tests, ablations) and **what those measurements mean** (findings, limits, costs).

The **headline contribution finding** — the one-sentence answer the evidence establishes — is born here with a fresh `fnd:` id and an `about` edge to the root Contribution (see `### Finding`). There is no separate finding section.

## The core rule: point at tables, do not transcribe them

**You never retype a results table.** The paper is segmented into top-level blocks, each tagged `[§N]` at its start; a `<table>` and its caption are **separate adjacent blocks** (caption "**Table 3: …**" = `[§52]`, the `<table>…</table>` after it = `[§53]`). For each results table, create a Measure that **points** at it by `[§N]` marker; code slices that table + caption verbatim beside your Measure. The bulky content — every baseline row, every full ablation grid — stays in the pointed-at table, **not** your output.

For a table-backed measure you transcribe, as structured `scores[]` rows, **only the contribution method's own numbers**, and only for a **main-results** table. Everything else is carried by the verbatim table blob.

**Where to point.** A *Source-table index* at the end lists the EXACT `[§N]` markers of every block holding a `<table>` grid, with each table's caption/columns. Every `source_table_marker` MUST be one of them — match by caption/columns. Point at the `<table>` block, never the prose paragraph that discusses it or a figure/image (`![Table N ...]`) of it. If the index lists no `<table>` grids, omit `source_table_marker` and transcribe ALL reported comparison rows — the contribution method's own rows AND every compared-against baseline row — as `scores[]` rows (prose mode: no table-blob backstop).

## Procedure — five stages, in order

The table loop is **not** the whole job. Run all five, in sequence:

1. **Materialize the census.** Every `mea:` node → `measures[]`; every substrate `exp:` node (`dataset`/`benchmark`/`task`) → `experiment_setups[]`; every `con:` node of kind `dataset`/`benchmark`/`finding` → `contributions[]`. Method/Component nodes are referenced by id only — they live in the method section.
2. **Classify every indexed table** — skip / `ablation` / `main_result` (the per-table procedure just below).
3. **Cover censused measures no table backs.** A censused `mea:` node must still be materialized — attach it to the indexed table that reports ITS OWN metric; if no indexed table reports that metric (its numbers live only in figures or prose), give it no `source_table_marker` and transcribe the contribution's own numbers the paper STATES in prose or a caption as `scores[]` rows — never read values off a figure's axes, and a claim with no stated number becomes a Finding, not a row.
4. **Sweep prose, figures, captions, discussion, and limitations** — sweep the results/discussion/limitations prose and figure captions and emit every interpretive Finding (classes under `### Finding`) that no table evidences — such a Finding appears in no `finding_ids`, which is valid, not an error.
5. **Author only the Finding-centric relations** (`## Relations`), then run the final completeness check.

**Per-table procedure** (Stage 2) — for EACH marker in the *Source-table index*, classify in order:
1. **Skip** — the cells are settings or statistics, not measured results: a configuration/hyperparameter listing (cells are parameter values; no metric column), dataset statistics, notation, or prior-work context evidencing no finding → emit **no** Measure for that table.
2. **`ablation`** — the table's cells are Δ/gain/improvement/correlation quantities of prior or base models reported as motivation or diagnosis (not the headline metric under the paper's own protocol) and no row/column label passes the contribution-row test (see `scores`; for a dataset/benchmark Contribution root, the headline evaluated-system rows ON that resource count as contribution rows) — OR the table isolates a component, sweeps a hyperparameter against a metric, or probes sensitivity → `table_role: "ablation"`, `scores: []`, finding(s) in `finding_ids`.
3. **`main_result`** — otherwise → `table_role: "main_result"`, one Measure per metric the table reports, transcribe the contribution rows and emit `headline_result`.

ALWAYS write `table_role` explicitly whenever `source_table_marker` is set.

**Metric-identity rule** — a `scores[]` value must be a value OF that Measure's own metric, as the table's header/caption labels it. Two mechanical checks: (a) **composite cells** — when one cell packs several metrics (header like `ACC(↑)MD(↓)`, caption like 'each entry is "accuracy | maximum discrepancy"', cell like `49.03[8.23]`), the table reports SEVERAL metrics: emit one Measure per packed metric sharing the same `source_table_marker`, and copy into each Measure only its own component, matched by position to the header/caption order (first component → first-named metric; bracketed component → bracket-named metric). Never copy the whole cell or the other metric's component. (b) **relative values** — a value labeled Δ / gain / improvement / reduction (%) is a relative-improvement quantity, NOT the absolute metric it derives from: never transcribe it into an absolute-metric Measure (a ΔMSE(%) value is never an MSE row).

## Units you may define

- `Measure` (array `measures`): one per results table per metric. Materialize each census Measure; you may add one the census missed. Several tables, one census metric: REUSE the census `node_id` for the measure whose table carries the headline result; if unclear, the FIRST `main_result` table in the index that reports it. Other tables get fresh `mea:` ids — never abandon a census `mea:` id, and never assign one census id to two measures. One table, several metrics → several Measures **sharing one `source_table_marker`**.
- `ExperimentSetup` (array `experiment_setups`): what it ran on / under what configuration. Substrate kinds materialized from census; configuration kinds born here (fresh `exp:` id). Rules in `### ExperimentSetup`.
- `Contribution` (array `contributions`): **only** `dataset`/`benchmark`/`finding`-kind Contributions here (method Contributions live in the method section). Materialize each such `con:` census node (reuse `node_id` + `kind`); you may add one the census missed. It hosts its own score rows — a Measure's `setup_id`/per-row `setup_id` may point at this `con:` id.
- `Finding` (array `findings`): the **headline contribution finding** plus interpretive findings (ablation, sensitivity, limitations, failure modes). Rules in `### Finding`.

### Measure
Fields: `name`, `unit`, `setup_ids`, optional `comparison_direction`, optional `objective_class`, and the blob-primary fields `source_table_marker`, `caption_marker`, `table_role`, `headline_result`, `finding_ids`, plus `scores`.

- `unit`: measurement unit (`BLEU`, `%`, `ms`, `F1`, `unitless`). Never blank.
- `comparison_direction` (opt): `higher_is_better | lower_is_better | target`. Omit if the paper states none — never `unspecified`/`""`. Per-measure (BLEU ≠ latency from the same table).
- `source_table_marker`: the `[§N]` id of the `<table>` this measure reads, as `"§N"` (e.g. `"§53"`) — MUST be a marker from the *Source-table index* below. **Set it on every table-derived measure**; omit only when transcribing directly because the index lists no tables (prose/figure paper), or because no indexed table CONTAINS this measure's values. When a table holds the numbers but its caption doesn't name the metric, that table IS its table — point at it. Never point a Measure at a table of a different metric, or a configuration table, just to give a census node a marker.
- `caption_marker`: the `[§N]` id of the table's caption block (e.g. `"§52"`), as `"§N"` — almost always the block **immediately before** the `<table>`. Omit when there's no caption block.
- `table_role`: `main_result` or `ablation` (defaults to `main_result` if omitted).
  - `main_result` — a headline / leaderboard / transfer table showing the contribution vs alternatives. **MUST** emit `scores[]` rows for the **contribution** (variants × splits) **plus** a `headline_result`; empty `scores[]` is an error — transcribe the contribution's row(s), baselines stay in the blob. No contribution row (pure prior-work context)? Not a `main_result` — reclassify or drop. (Dataset/benchmark root: the headline evaluated-system rows ON that resource count as contribution rows — see `scores`.)
  - `ablation` — isolates a component, sweeps a hyperparameter, or probes sensitivity ("without attention", "−BN", "K = 2,4,8,16") — or a motivation/diagnostic study whose cells are Δ/gain/correlation quantities of prior or base models (dataset/benchmark root: evaluated-system rows ON that resource count as contribution rows). Leaves `scores[]` empty (`[]`); mount the ablation Finding(s) via `finding_ids`.
- `headline_result`: the contribution's key one-liner from this table, in the paper's own numbers (e.g. `"Transformer (big) reaches 28.4 BLEU on WMT14 EN-DE and 41.0 on EN-FR, +2.0 BLEU over the prior best"`). **Emit on every `main_result` Measure; on an `ablation` Measure only when the contribution's headline number lives there.** Put the delta over baselines **here, in words** ("+2.0 BLEU over GNMT"), not as a structured field.
- `finding_ids`: ids of the Findings this table evidences, defined in this same response (e.g. `["fnd:headline", "fnd:pos_enc_matters"]`). The **canonical table→finding link** — do not author `Measure --supports--> Finding` or `Finding --about--> Measure` edges. Flexible: a finding id may appear on several measures, a measure may mount several findings (main-result → headline finding; ablation → its ablation finding(s)).
- `setup_ids`: **local** ExperimentSetup ids scoping this measure (the datasets/splits/protocols the **contribution rows** ran under), defined in this same response. A benchmark measure normally has ≥1 setup; an empty-`scores[]` `ablation` may carry none (`[]`). No `subject_id`/`evaluated_on` field — the evaluated method is the global `evaluates` edge.
- `scores`: a flat array of `{variant, value, variance, system_id, setup_id}`, with optional `value_kind`/`opponent_id`/`judge_id`. For a `main_result` table, **the contribution's own rows** — its variants (base/big, ResNet-50/101/152) across the datasets/splits evaluated — and **non-empty**. **Do not transcribe baselines or prior-SOTA rows** — they stay in the verbatim table blob. Row test (priority order): a label naming the contribution, "Ours", or a contribution component/variant anywhere is a CONTRIBUTION row even with a backbone citation ("Faster R-CNN [32] + Ours"); the citation-marker = baseline test applies only to labels that do **not** name the contribution. **Exception — dataset/benchmark Contribution root:** the evaluation ON that resource IS the paper's own result — transcribe the headline evaluated-system rows (`setup_id` = the resource Contribution, `system_id` = the evaluated Contribution/Component when censused), the systems the paper headlines, not every minor variant; when the table grades the resource by object/category rather than by system, transcribe the headline column's rows with the printed row label as `variant`; tables of those systems on OTHER datasets are context (co-equal roots: the contribution's own rows take priority — apply this carve-out only to tables with no contribution row). For a prose/figure number with no table, transcribe it as a row here and omit `source_table_marker`.
  - `variant`: the contribution configuration as the paper labels it (`"Transformer (big)"`, `"Ours (ResNet-101)"`), INCLUDING every distinguishing label — backbone, base model, scale, iteration, per-class/per-scene column (`"CLUSTSEG (Swin-B)"`, `"ReST-MCTS* (Mistral-7B, iter 2)"`). Compose the label only from strings the table prints (row label + column header); never invent a name the table does not print. No two rows of one Measure share the same (`variant`, `setup_id`); if two would, add the missing label to `variant`, never drop the row.
  - `value`: always a string (`"28.4"`, `"28.4-29.1"`, or a short categorical string); `variance` is `""` when no uncertainty is reported.
  - `system_id`: the `con:`/`cmp:` id of the **contribution this row reports** (`con:transformer`). Set it whenever that node exists in `node_registry`; `""` only when no node represents the row. Same-family variants (base/big) share one `system_id`.
  - `setup_id`: the **local ExperimentSetup** this row was measured on — the row's dataset/split, matching its OWN table/protocol. If the row's protocol/split/task differs from every defined setup (single-scale vs multi-scale, a segmentation vs detection test set), born the matching configuration ExperimentSetup — never reuse the nearest same-dataset setup for a different protocol. Leave `""` only when `setup_ids` already scope every row uniformly.
- **Never collapse a dataset/split column of the contribution.** Across several datasets/splits/language pairs, keep **one contribution row per (variant × split)** and pin each `setup_id` — one number per variant silently drops the other column's values.

### ExperimentSetup — substrate and configuration
Fields: `kind`, `name`, optional `description`.
- `kind`: which experimental ingredient this is.
  - substrate — `dataset`, `benchmark` (dataset+protocol), `task`. Materialize **every** substrate census node (including `task`), reusing each `node_id` + `kind`. No `resource` kind: a dataset/benchmark that is the paper's *own deliverable* is a `Contribution`, not an ExperimentSetup.
  - configuration — `data_split`, `inference_protocol` (beam=4/α=0.6, 10-crop), `training_config`, `ensembling`, `population`. Born only when it scopes a row you emit — contribution rows only for table-backed measures (not a baseline row that stays in the blob); in prose mode, the splits any transcribed row needs.
- A dataset/benchmark **Contribution** is the document root, not an ExperimentSetup: the scores the paper reports on it are `scores[]` rows on Measures whose `setup_ids`/per-row `setup_id` point at that very `con:` Contribution, and the headline contribution finding points `about` it. *How* to transcribe those rows — the headline evaluated-system rows, the grade-by-object/category case, and the co-equal-root priority — is the dataset/benchmark-root rule under `### Measure` → `scores`; it is **not** restated here.
- `name`: the setup's name/label — a dataset name (`WMT 2014 English-German`), a split label (`newstest2014`), a configuration name (`beam search, beam=4`).
- `description` (optional): for a setup the paper itself constructs (own dataset, prompt suite, user study, custom protocol), one sentence of composition/coverage in the paper's real names/numbers; for a standard external benchmark, empty string unless a non-obvious subset or protocol is used. Never replace a specific setup with a vague restatement.
- **Enumerate each distinct configuration as its own ExperimentSetup** when it scopes a contribution result (cross-dataset transfer, robustness / distribution-shift, user study, timing protocol). Do **not** capture hardware or a global hyperparameter that scopes no contribution measure.

### Finding — contribution finding and interpretive findings
Fields: `kind`, `statement`; optional payload `polarity`, `effect_size`, `scope`.
- `kind` (required): the finding's category — one of `descriptive | mechanistic | comparative | modeling | ablation_finding | failure_mode | theorem | lemma | bound`.
- `polarity` (optional): set it whenever the finding has a clear direction.

First, the **headline contribution finding**: the single sentence stating what the paper establishes — the answer to the research problem. `kind` is usually `comparative` ("A outperforms B") or `modeling` (a formal/architectural claim) — or `theorem`/`bound` when the headline is **proven**. One headline finding, grounded in the main-result evidence, with the paper's headline numbers WHEN IT STATES ANY (set `effect_size`); do NOT copy `spine_summary.headline_result` byte-for-byte. Born it with a fresh `fnd:` id and an `about` edge to the **root Contribution** (the `node_registry` node of type `Contribution` — a `con:` id; for co-equal roots, the primary one), whatever its kind (method, dataset/benchmark, or `kind: finding`). Mount it on the main-result Measure via `finding_ids`.

Then **every distinct interpretive finding** the evaluation supports — this "what it means" layer is easy to under-capture, so treat completeness as the job. Each below, when the paper states it, is its **own** Finding:
- **ablation / sensitivity conclusions** (`kind: ablation_finding`), including fine-grained sub-findings (a saturation point, a capacity ceiling, which component contributes most). Mount each on the ablation Measure via `finding_ids`.
- **mechanism / interpretability** findings (`kind: mechanistic`) — *why* the method works.
- **comparative analysis** findings (`kind: comparative`) — an analytical "design choice A beats B" conclusion, distinct from a deployable score row.
- **limitations and failure modes** (`kind: failure_mode`) — ALWAYS one Finding per author-stated limitation, wherever it appears ("could not deal with X", "relies on Y", "does not extend to Z"), even with no table or number. A hedged extension proposal ("can be extended to", "we leave to future work") is a future-work Finding (`kind: descriptive`), not `failure_mode` — `failure_mode` requires a stated inability or dependency ("could not", "relies on", "does not extend").
- **cost-of-method** (`kind: descriptive`) — the paper's stated cost of running the method (dollars, tokens, GPU-hours, latency) and its acceptability verdict; numbers in `effect_size`. ALWAYS emit when stated.
- **statistical-significance defense** (`kind: comparative`, or `ablation_finding` inside an ablation) — a t-test / p-value / confidence statement defending a main comparison ("significant at the 1% level"). ALWAYS emit when stated.
- **proven theoretical results** (`kind: theorem | lemma | bound`) — established **by proof**, not measurement. The formal statement is a Contribution (`kind: method`, `method_kind: theorem`/`lemma`/`bound`) in the method section; this Finding carries what it establishes, and the Contribution `supports` it. A symbolic/asymptotic value goes in a score row with the matching `value_kind`.
- **future-work directions** that shape interpretation (`kind: descriptive`).

A finding whose evidence is a **figure**, not a table (a speed/memory curve, a robustness or sensitivity sweep, a named subsection's claim about a plot) is emitted exactly like a table finding — absence from the *Source-table index* never drops it.

## Relations

This section authors only these Finding-centric edges in `relations[]`:

| relation | source → target | meaning |
|---|---|---|
| `about` | Finding → {Contribution, Component, ExperimentSetup} | the finding is about that node (for an ablation, the **component** it isolates; for a data/benchmark conclusion, the `exp:` substrate) |
| `supports` | Finding → Finding | one local finding supports another (a derivation: observation → conclusion) |
| `supports` | Contribution → Finding | a theory Contribution (a theorem/proof) establishes a proven-result Finding (the formal analogue of measurement) |

- For the headline contribution finding: emit `Finding --about--> <root>`, pointing at the `node_registry` node of type `Contribution` (a `con:` id), whatever its kind — method, dataset/benchmark, or finding. For co-equal roots, point at the primary one.
- For each ablation finding: emit `Finding --about--> cmp:<component>`, pointing at the specific Component node from `node_registry` (not the whole-system root) when the ablation isolates one part. The link **to the data** is the `finding_ids` mount on the ablation Measure.
- For a proven theoretical result: emit `Contribution --supports--> Finding` from the theory Contribution to the proven-result Finding.
- **Do not author `Finding --about--> Measure` or `Measure --supports--> Finding`** — the table↔finding link is now the Measure's `finding_ids`, not an edge.
- Do not author `evaluates`, `part_of`, `compares_to`, or `measured_on` — those are global structural edges already established by the relation pass (or removed). Never put a Finding or Measure on either end of a structural edge.

### Findings about data and metrics, and multi-step chains

A finding is **not always about the method**:
- **about a dataset / benchmark** — a conclusion about the *data itself* (a label bias, a saturated benchmark): `Finding --about--> exp:<dataset>`. Example: "ImageNet-V2 shows a 5-point drop from a harder label distribution" → a `Finding` (`polarity: negative`) `about` `exp:imagenet_v2`.
- **about a metric** — a conclusion about a *measure's behavior* (it saturates, is gameable): **mount the finding on that Measure via its `finding_ids`**.
- **multi-step chain** — when one observation licenses a conclusion, connect them with `supports`: `Finding(observation) --supports--> Finding(conclusion)`. Do not flatten a derivation into two unconnected siblings.

## What to extract

- **Results:** best/final contribution results on primary benchmarks + transfer/generalization results that demonstrate the main finding, as `scores[]` rows on their tables; include scale/capacity variants presented as first-class configurations.
- **Findings:** capture the **full** "what this means" layer — every distinct ablation, mechanism, comparative, limitation, cost, and future-work finding (completeness here is the job).

## Anti-patterns

- Do not retype baseline / prior-SOTA / competitor rows into `scores[]` for a table-backed measure — they stay in the source table (you point with `source_table_marker`). Exceptions: the headline evaluated-system rows ON a dataset/benchmark Contribution root, and prose mode (no tables — transcribe every reported comparison row).
- Do not transcribe a full ablation grid — an `ablation` measure has empty `scores[]` and points at its table.
- Do not omit `source_table_marker` on a table-derived measure — without it the verbatim table can't attach.
- Do not create a `subject_id`, `evaluated_on`, or `measured_on` — they do not exist; use the global `evaluates` edge, `setup_ids`, and per-row `setup_id`.
- Do not create method Contribution or Component units here (reference those nodes by id in `about` edges); a dataset/benchmark or `finding`-kind Contribution IS materialized here.
- Do not leave a contribution row's `system_id` blank when its Contribution/Component node exists in `node_registry`.

## Worked example

Assume the paper's blocks include the caption "**Table 4: BLEU on WMT14**" as `[§52]`, the leaderboard `<table>` as `[§53]`, and a positional-encoding ablation `<table>` as `[§55]`.

{
  "section": {
    "section_type": "evidence",
    "anchor_id": "mea:bleu",
    "measures": [
      {
        "id": "mea:bleu",
        "type": "Measure",
        "name": "BLEU",
        "unit": "BLEU",
        "setup_ids": ["exp:wmt2014_en_de", "exp:wmt2014_en_fr", "exp:beam_search"],
        "comparison_direction": "higher_is_better",
        "source_table_marker": "§53",
        "caption_marker": "§52",
        "table_role": "main_result",
        "headline_result": "Transformer (big) reaches 28.4 BLEU on WMT14 EN-DE and 41.0 on EN-FR, +2.0 BLEU over the prior best (GNMT) while training far less.",
        "finding_ids": ["fnd:headline"],
        "scores": [
          {"variant": "Transformer (big)", "value": "28.4", "variance": "", "system_id": "con:transformer", "setup_id": "exp:wmt2014_en_de"},
          {"variant": "Transformer (big)", "value": "41.0", "variance": "", "system_id": "con:transformer", "setup_id": "exp:wmt2014_en_fr"}
        ],
        "provenance": ["§53"]
      },
      {
        "id": "mea:pos_enc_ablation",
        "type": "Measure",
        "name": "BLEU under positional-encoding ablation",
        "unit": "BLEU",
        "setup_ids": [],
        "comparison_direction": "higher_is_better",
        "source_table_marker": "§55",
        "table_role": "ablation",
        "finding_ids": ["fnd:pos_enc_matters"],
        "scores": [],
        "provenance": ["§55"]
      }
    ],
    "experiment_setups": [
      {"id": "exp:wmt2014_en_de", "type": "ExperimentSetup", "kind": "benchmark", "name": "WMT 2014 English-German", "provenance": ["§53"]},
      {"id": "exp:wmt2014_en_fr", "type": "ExperimentSetup", "kind": "benchmark", "name": "WMT 2014 English-French", "provenance": ["§53"]},
      {"id": "exp:beam_search", "type": "ExperimentSetup", "kind": "inference_protocol", "name": "Beam search (beam=4, α=0.6)", "description": "Beam search with beam size 4 and length penalty alpha=0.6.", "provenance": ["§53"]}
    ],
    "findings": [
      {"id": "fnd:headline", "type": "Finding", "kind": "comparative", "statement": "An attention-only model outperforms the best prior recurrent and convolutional systems on WMT14 translation.", "polarity": "positive", "effect_size": "+2.0 BLEU", "provenance": ["§53"]},
      {"id": "fnd:pos_enc_matters", "type": "Finding", "kind": "ablation_finding", "statement": "Removing positional encodings lowers BLEU by 2.2, showing they are necessary for the attention-only model.", "polarity": "negative", "effect_size": "-2.2 BLEU", "provenance": ["§55"]}
    ],
    "relations": [
      {"source_id": "fnd:headline", "relation": "about", "target_id": "con:transformer", "provenance": ["§53"]},
      {"source_id": "fnd:pos_enc_matters", "relation": "about", "target_id": "cmp:positional_encoding", "provenance": ["§55"]}
    ]
  }
}

`mea:bleu` points at the leaderboard (`§53`/caption `§52`) and transcribes **only** the contribution's two rows (EN-DE, EN-FR), each pinned via `setup_id`; baselines stay in the verbatim `[§53]` table. The `ablation` measure points at `[§55]` with **empty** `scores[]` and mounts its finding via `finding_ids`. Table↔finding links are the `finding_ids` arrays — no `Measure --supports--> Finding` / `Finding --about--> Measure` edges; the only authored edges are the two `Finding --about-->` edges. Structural edges (`evaluates`, `compares_to`) already live in the global `relations`.

## Anchor

`anchor_id` should be the primary headline Measure (`mea:`) — the result that most directly validates the main finding. Do not anchor on an ExperimentSetup or Finding.

Final completeness check — before closing the JSON, verify: (1) every `mea:` id in `node_registry` appears in `measures[]`; (2) every `exp:` registry node with a substrate kind appears in `experiment_setups[]`, and every `con:` registry node of kind `dataset`/`benchmark`/`finding` appears in `contributions[]`; (3) every id in `finding_ids`/`setup_ids`/`setup_id` is defined in this response (per-row `setup_id` `""` is allowed where no configuration applies); (4) for a table-backed measure (`source_table_marker` set), `scores[]` is non-empty exactly when its `table_role` is `main_result`; (5) every author-stated limitation, cost analysis, statistical-significance statement, and figure-only main result has a Finding in `findings[]` — including Findings no `finding_ids` mounts.
