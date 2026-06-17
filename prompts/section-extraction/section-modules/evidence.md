SECTION FOCUS: evidence (blob-primary)

This section captures the paper's evaluation layer in one pass: both **what was measured** (how the method performs on benchmarks and transfer tests) and **what those measurements mean** (what ablations reveal, what limits the result). Measurement and interpretation are decided together here, with the whole results table in view.

This section is also where the paper's discovery arc closes: it states the **headline contribution finding** — the one-sentence answer the evidence establishes — alongside the finer interpretive findings. There is no separate finding section. The headline contribution finding is always born here like every other finding, with a fresh `fnd:` id and an `about` edge to the root Contribution (see "headline contribution finding" below).

## The core rule: point at tables, do not transcribe them

**You never retype a results table.** The paper you are given is segmented into top-level blocks, each tagged `[§N]` at its very start. A `<table>` and its caption are **separate adjacent blocks** — e.g. the caption "**Table 3: …**" is block `[§52]` and the `<table>…</table>` immediately after it is block `[§53]`. For each results table you create a Measure that **points** at the table by its `[§N]` marker; code then slices that table and its caption verbatim and stores them beside your Measure. The bulky content — every baseline row, every full ablation grid — stays in the pointed-at table, **not** in your output.

For a table-backed measure you transcribe, as structured `scores[]` rows, **only the contribution method's own numbers**, and only for a **main-results** table. Everything else is carried by the verbatim table blob.

**Where to point.** A *Source-table index* is given to you at the end of this guidance: it lists the EXACT `[§N]` markers of every block that actually contains a `<table>` grid, with each table's caption/columns. Every `source_table_marker` you emit MUST be one of those markers — match a measure to its table by the caption/columns in the index. The result data lives in the `<table>` block, which is a **separate block** from the paragraph that discusses it and from any figure/image (`![Table N ...]`) of the same table — never point at the prose paragraph or the image; point at the `<table>` block from the index. If the index says the paper has no `<table>` grids, omit `source_table_marker` and transcribe ALL reported comparison rows — the contribution method's own rows AND every compared-against baseline row — as `scores[]` rows (prose mode: there is no table blob backstop).

**Per-table procedure** — for EACH marker in the *Source-table index*, decide in order: (1) the cells are settings or statistics, not measured results — a configuration/hyperparameter listing (cells are parameter values; no metric column), dataset statistics, notation, or prior-work context evidencing no finding → emit NO Measure for that table; (2) the table's cells are Δ/gain/improvement/correlation quantities of prior or base models reported as motivation or diagnosis (not the headline metric under the paper's own protocol) and no row/column label passes the contribution-row test (see `scores`; for a dataset/benchmark Contribution root, the headline evaluated-system rows ON that resource count as contribution rows) — OR the table isolates a component, sweeps a hyperparameter against a metric, or probes sensitivity → `table_role: "ablation"`, `scores: []`, finding(s) in `finding_ids`; (3) otherwise → `table_role: "main_result"`, one Measure per metric the table reports, transcribe the contribution rows and emit `headline_result`. ALWAYS write `table_role` explicitly whenever `source_table_marker` is set. The index loop is not the whole job — two sweeps follow it: (4) a censused `mea:` node must still be materialized — attach it to the indexed table that reports ITS OWN metric; if no indexed table reports that metric (its numbers live only in figures or prose), give it no `source_table_marker` and transcribe the contribution's own numbers the paper STATES in prose or a caption as `scores[]` rows — never read values off a figure's axes, and a claim with no stated number becomes a Finding, not a row; (5) sweep the results/discussion/limitations prose and figure captions and emit every interpretive Finding (classes below) that no table evidences — such a Finding appears in no `finding_ids`, which is valid, not an error.

**Metric-identity rule** — a `scores[]` value must be a value OF that Measure's own metric, as the table's header/caption labels it. Two mechanical checks: (a) **composite cells** — when one cell packs several metrics (header like `ACC(↑)MD(↓)`, caption like 'each entry is "accuracy | maximum discrepancy"', cell like `49.03[8.23]`), the table reports SEVERAL metrics: emit one Measure per packed metric sharing the same `source_table_marker`, and copy into each Measure only its own component, matched by position to the header/caption order (first component → first-named metric; bracketed component → bracket-named metric). Never copy the whole cell or the other metric's component. (b) **relative values** — a value labeled Δ / gain / improvement / reduction (%) is a relative-improvement quantity, NOT the absolute metric it derives from: never transcribe it into an absolute-metric Measure (a ΔMSE(%) value is never an MSE row).

## Units you may define

- `Measure` (array `measures`): one per results table per metric — the addressable node that points at a source table and (for a main result) carries the contribution method's own score rows. Materialize each Measure census node; you may add one the census missed. When several tables report the same census metric, REUSE the census `node_id` for the measure whose table carries the headline result for that metric; if unclear, the FIRST `main_result` table in the index that reports it. Give the other tables' measures fresh `mea:` ids — never abandon a census `mea:` id (check (1) below would fail), and never assign one census id to two measures. A table reporting several metrics (BLEU **and** latency) becomes several Measures **sharing the same `source_table_marker`**.
- `ExperimentSetup` (array `experiment_setups`): the merged "what it ran on / under what configuration" type — substrate kinds are materialized from census, configuration kinds are born here with a fresh `exp:` id. The kind split and rules are in "### ExperimentSetup" below.
- `Contribution` (array `contributions`): **only** a dataset/benchmark or `finding`-kind Contribution is born/materialized here (the method/theory Contributions live in the method section). A dataset/benchmark deliverable is a `Contribution` with `kind` `dataset`/`benchmark`; an analysis paper's deliverable is a `Contribution` with `kind` `finding`. Materialize each such `con:` census node reusing its `node_id` and `kind`; you may add one the census missed (fresh `con:` id). It hosts its own score rows — a Measure's `setup_id`/per-row `setup_id` may point at this `con:` id.
- `Finding` (array `findings`): the **headline contribution finding** (the paper's central established answer) plus the interpretive findings — ablation conclusions, sensitivity conclusions, limitations, failure modes. The headline finding is born here with a fresh `fnd:` id and an `about` edge to the root Contribution, exactly like every other paper (see "headline contribution finding" below).

### Measure
Fields: `name`, `unit`, `setup_ids`, optional `comparison_direction`, optional `objective_class`, and the blob-primary fields `source_table_marker`, `caption_marker`, `table_role`, `headline_result`, `finding_ids`, plus `scores`.

- `unit`: non-empty measurement unit such as `BLEU`, `%`, `ms`, `F1`, `perplexity`, or `unitless`. Never blank.
- `comparison_direction` (optional): `higher_is_better | lower_is_better | target`. When the paper gives no direction, omit the field entirely — do not emit `unspecified` or `""`. Keep it per-measure — a BLEU measure and a latency measure from the same table have **different** directions.
- `source_table_marker`: the `[§N]` block id of the `<table>` this measure reads, written as `"§N"` (e.g. `"§53"`) — and it MUST be one of the markers in the *Source-table index* below (those are the only blocks that hold a `<table>` grid). **Set it on every table-derived measure**; omit it only when you are transcribing numbers directly because the index lists no tables (prose/figure-only paper) — or because no indexed table CONTAINS this measure's values (its numbers live only in figures or prose). When a table holds the measure's numbers but its caption does not name the metric, that table IS its table — point at it. Never point a Measure at a table of a different metric, or at a configuration table, just to give a census node a marker.
- `caption_marker`: the `[§N]` block id of the table's caption block (e.g. `"§52"`), written as `"§N"`. The caption is almost always the block **immediately before** the `<table>` block ("**Table k: …**"). Code slices it verbatim — you only point. Omit when the table has no caption block.
- `table_role`: `main_result` or `ablation` (defaults to `main_result` if omitted).
  - `main_result` — a headline comparison / leaderboard / transfer table whose purpose is to show how the contribution performs against alternatives. You **MUST** emit `scores[]` rows for the **contribution** (its variants × splits — see below) **plus** a `headline_result`. A `main_result` Measure with **empty** `scores[]` is an error: the contribution's own number is in the `<table>` you pointed at, so transcribe its row(s) — the baselines (only) stay in the blob. If the table truly has no contribution row (a pure prior-work comparison that is context, not your result), it is not a `main_result` — reclassify or drop it. (For a dataset/benchmark Contribution root, the headline evaluated-system rows ON that resource count as contribution rows — see `scores` below.)
  - `ablation` — a study that isolates a component, sweeps a hyperparameter, or probes sensitivity ("without attention", "−BN", "K = 2,4,8,16") — or a motivation/diagnostic study whose cells are Δ/gain/correlation quantities of prior or base models (for a dataset/benchmark Contribution root, evaluated-system rows ON that resource count as contribution rows). This role leaves `scores[]` empty (`[]`) — the verbatim table carries the whole grid. Mount the ablation Finding(s) via `finding_ids`.
- `headline_result`: the contribution's key one-liner drawn from this table, in the paper's own numbers (e.g. `"Transformer (big) reaches 28.4 BLEU on WMT14 EN-DE and 41.0 on EN-FR, +2.0 BLEU over the prior best"`). **Emit it on every `main_result` Measure — each table's own key contribution one-liner; on an `ablation` Measure only when the contribution's headline number lives in that table.** This is the durable text backstop for the contribution's result, independent of the structured rows. Put the improvement / delta over baselines **here, in words** ("+2.0 BLEU over GNMT") rather than as a structured field.
- `finding_ids`: ids of the Findings this table evidences, born or materialized (i.e. defined) in this same response (e.g. `["fnd:headline", "fnd:pos_enc_matters"]`). This is the **canonical table→finding link** — it replaces the old `Measure --supports--> Finding` and `Finding --about--> Measure` edges (do not author those). The mapping is flexible: a finding id may appear on several measures, and a measure may mount several findings. A main-result measure normally mounts the headline finding; an ablation measure mounts its ablation finding(s).
- `setup_ids`: IDs of **local** ExperimentSetup units that scope this measure (the datasets/splits/protocols the **contribution rows** were computed under), defined or materialized in this same response. A deployable benchmark measure is normally scoped by at least one setup; an `ablation` measure with empty `scores[]` may carry none (`[]`). There is no `subject_id` or `evaluated_on` field — the method a measure evaluates is the global `evaluates` edge, already established.
- `scores`: a flat array of `{variant, value, variance, system_id, setup_id}`, with optional `value_kind`/`opponent_id`/`judge_id`. For a `main_result` table this carries **the contribution's own rows** — its variants (base/big, ResNet-50/101/152) across the datasets/splits it was evaluated on — and it must be **non-empty** (the contribution's headline number(s) belong here as structured rows; this is the queryable core). **Do not transcribe baselines or prior-SOTA rows** — they remain in the verbatim table blob, retrievable by `source_table_marker`. Row test, in priority order: if the label names the contribution, "Ours", or a contribution component/variant anywhere in the label, it is a CONTRIBUTION row even if it also carries a citation marker for a backbone ("Faster R-CNN [32] + Ours"); the citation-marker test (a bracketed citation marks a baseline row) applies only to labels that do not name the contribution. **Exception — dataset/benchmark Contribution root:** the evaluation ON that resource IS the paper's own result — transcribe the headline evaluated-system rows (`setup_id` = the resource Contribution, `system_id` = the evaluated Contribution/Component when censused), the systems the paper headlines, not every minor variant; when the table grades the resource itself by object/category rather than by system (per-object success, per-class agreement), transcribe the headline column's rows with the printed row label as `variant`; tables of those systems on OTHER datasets are context (co-equal roots: the contribution's own rows take priority — apply this carve-out only to tables with no contribution row). For a prose/figure number with no table, transcribe it as a row here and omit `source_table_marker`.
  - `variant`: names the contribution configuration as the paper labels it (`"Transformer (big)"`, `"Ours (ResNet-101)"`) — or the paper's name for the configuration, for a prose row — INCLUDING every label the table uses to tell the contribution's rows/columns apart: backbone, base model, scale, iteration, per-class/per-scene column (`"CLUSTSEG (Swin-B)"`, `"ReST-MCTS* (Mistral-7B, iter 2)"`). Compose the label only from strings the table prints (row label + column header); never invent a name the table does not print. Check: no two rows of one Measure may share the same (`variant`, `setup_id`) pair; if two would, the distinguishing label is missing — add it to `variant`, never drop the row.
  - `value`: always a string (`"28.4"`, `"28.4-29.1"`, or a short categorical string); `variance` is `""` when no uncertainty is reported.
  - `system_id`: the id of the **contribution this row reports** — a `con:` or `cmp:` id (`con:transformer`). Set it whenever a Contribution or Component node for the contribution variant exists in `node_registry`. Use `""` only when no node represents the row. Two variant rows of the same family (base/big) share one `system_id`.
  - `setup_id`: the id of the **local ExperimentSetup** this contribution row was measured on — the dataset/split for the row. **This is how the row binds to its data.** Point it at the setup matching the row's OWN table/protocol: if the row's table reports a different protocol, split, or task than every defined setup (single-scale vs multi-scale, a segmentation test set vs the detection one), born the matching configuration ExperimentSetup and point at it — never reuse the nearest same-dataset setup for a different protocol. Leave `""` only when the measure's `setup_ids` already scope every row uniformly (a single-split measure).
- **Never collapse a dataset/split column of the contribution.** When the contribution is reported across several datasets/splits/language pairs, keep **one contribution row per (variant × split)** and pin each row's `setup_id` — do not keep one number per variant, which silently drops the other column's contribution values. (You no longer keep baseline rows, so this rule now applies only to the contribution's own numbers.)

### ExperimentSetup — substrate and configuration
Fields: `kind`, `name`, optional `description`.
- `kind`: which experimental ingredient this is.
  - substrate — `dataset` (data trained/evaluated on), `benchmark` (a standardized dataset+protocol), `task` (the problem solved/evaluated). Materialize **every** substrate census node in `node_registry`, including `task`, reusing each `node_id` and its `kind`. (There is no `resource` substrate kind: a dataset/benchmark that is the paper's *own deliverable* is a `Contribution` with `kind` `dataset`/`benchmark`, materialized in `contributions`, not an ExperimentSetup.)
  - configuration — `data_split`, `inference_protocol` (beam search beam=4/α=0.6, 10-crop), `training_config`, `ensembling`, `population`. Born here, but only when it scopes a row you actually emit — for table-backed measures that means contribution rows only (do not born a split just to bind a baseline row that stays in the blob); in prose mode, born the splits any transcribed row needs.
- A dataset/benchmark **Contribution** is the document root: the scores the paper reports on it are `scores[]` rows on Measures whose `setup_ids`/per-row `setup_id` point at that very `con:` Contribution, and the headline contribution finding points `about` it. For such a root, the evaluation ON that resource IS the paper's own result: transcribe the headline evaluated-system rows (`setup_id` = the resource Contribution, `system_id` = the evaluated Contribution/Component when censused) — the systems the paper headlines, not every minor variant; when the rows grade the resource by object/category rather than by system, transcribe the headline column's rows with the printed row label as `variant`; tables of those systems on OTHER datasets are context. When the census tagged co-equal roots (another contribution linked to the dataset/benchmark Contribution by `co_contribution`), the normal contribution-row rule takes priority: transcribe that contribution's own rows, and apply this carve-out only to tables where no contribution row exists.
- `name`: the setup's name/label — a dataset name (`WMT 2014 English-German`), a split label (`newstest2014`), a configuration name (`beam search, beam=4`).
- `description` (optional): for a setup the paper itself constructs (its own dataset, prompt suite, user study, custom protocol), one sentence stating composition and coverage in the paper's real names/numbers; for a standard external benchmark, empty string unless a non-obvious subset or protocol is used. Never replace a specific setup with a vague generic restatement.
- **Enumerate each distinct configuration as its own ExperimentSetup** when it scopes a contribution result — a cross-dataset transfer protocol, a robustness / distribution-shift setup, a user study, a timing protocol. Do **not** capture hardware or a global hyperparameter that scopes no contribution measure.

### Finding — contribution finding and interpretive findings
Fields: `kind`, `statement`; optional payload `polarity`, `effect_size`, `scope`.
- `kind` (required): the finding's category — one of `descriptive | mechanistic | comparative | modeling | ablation_finding | failure_mode | theorem | lemma | bound`.
- `polarity` (optional): set it whenever the finding has a clear direction.

First, capture the **headline contribution finding**: the single sentence that states what the paper establishes — the answer to the research problem. Its `kind` is usually `comparative` ("A outperforms B") or `modeling` (a formal/architectural claim) — or `theorem`/`bound` when the headline is a **proven** statement. One headline finding — state it grounded in the main-result evidence, with the paper's headline numbers WHEN IT STATES ANY (set `effect_size`); do NOT copy `spine_summary.headline_result` byte-for-byte (the Document already carries that sentence). It attaches the same way for every paper: born the finding with a fresh `fnd:` id and author an `about` edge to the **root Contribution** (the `node_registry` node of type `Contribution` — a `con:` id; for co-equal roots, the primary one). This holds whatever the contribution's kind — a method, a dataset/benchmark deliverable, or an analysis paper whose deliverable is a `kind: finding` Contribution. This draws the problem→answer throughline; assembly then draws the closing `resolves` edge from that Contribution to the Problem. Mount this finding on the main-result Measure via that Measure's `finding_ids`.

Then enumerate **every distinct interpretive finding** the evaluation supports — this "what it means" layer is easy to under-capture, so treat completeness here as the job. Each of the following, when the paper states it, is its **own** Finding — extract the paper's own finding in its own terms:
- **ablation / sensitivity conclusions** (`kind: ablation_finding`), including fine-grained sub-findings — a saturation point, a capacity ceiling, which component contributes most. Mount each on the ablation Measure (the one pointing at the ablation table) via `finding_ids`.
- **mechanism / interpretability** findings (`kind: mechanistic`) — *why* the method works.
- **comparative analysis** findings (`kind: comparative`) — an analytical "design choice A beats B" conclusion, distinct from a deployable score row.
- **limitations and failure modes** (`kind: failure_mode`) — ALWAYS one Finding per author-stated limitation, wherever it appears (a Limitations/Discussion/Conclusion/appendix sentence: "could not deal with X", "relies on Y", "does not extend to Z"), even when no table or number backs it. A hedged extension proposal ("can be extended to", "we leave to future work") is a future-work Finding (`kind: descriptive`), not `failure_mode` — `failure_mode` requires a stated inability or dependency ("could not", "relies on", "does not extend").
- **cost-of-method** (`kind: descriptive`) — the paper's stated cost of running the method (dollars, tokens, GPU-hours, latency) and its acceptability verdict; put the numbers in `effect_size`. ALWAYS emit when stated.
- **statistical-significance defense** (`kind: comparative`, or `ablation_finding` inside an ablation) — a t-test / p-value / confidence statement defending a main comparison ("significant at the 1% level"). ALWAYS emit when stated.
- **proven theoretical results** (`kind: theorem | lemma | bound`) — a result established **by proof**, not measurement. The formal statement is a Contribution (`kind: theory`, `method_kind: theorem`/`lemma`/`bound`) in the method section; this Finding carries what it establishes, and the theory Contribution `supports` it (see Relations). A symbolic/asymptotic value goes in a score row with the matching `value_kind`.
- **future-work directions** that shape interpretation (`kind: descriptive`).

A finding whose evidence is a **figure**, not a table (a speed/memory curve, a robustness or sensitivity sweep, a named subsection's claim about a plot) is emitted exactly like a table finding — absence from the *Source-table index* never drops it.

## Relations

This section authors only these Finding-centric edges in `relations[]`:

| relation | source → target | meaning |
|---|---|---|
| `about` | Finding → {Contribution, Component, ExperimentSetup} | the finding is about that node (for an ablation, the **component** it isolates; for a data/benchmark conclusion, the `exp:` substrate) |
| `supports` | Finding → Finding | one local finding supports another (a derivation: observation → conclusion) |
| `supports` | Contribution → Finding | a theory Contribution (a theorem/proof) establishes a proven-result Finding (the formal analogue of measurement) |

- For the headline contribution finding: emit `Finding --about--> <root>`, pointing at the `node_registry` node of type `Contribution` (a `con:` id), whatever its kind — method, dataset/benchmark, theory, or finding. For co-equal roots, point at the primary one.
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

- Extract best/final contribution results on primary benchmarks, and transfer/generalization results that demonstrate the main finding — as contribution `scores[]` rows pointing at their tables.
- Extract contribution scale/capacity variants when presented as first-class configurations.
- Capture the **full** "what this means" layer as Findings — every distinct ablation, mechanism, comparative, limitation, and future-work finding — and mount each on the table that evidences it.
- For table-backed measures you do not transcribe baseline rows; they are preserved verbatim in the pointed-at table blob. Skip a table only when it is pure context (dataset statistics, notation) that evidences no contribution result and no finding — do not create an empty Measure for it.

## Anti-patterns

- Do not retype baseline / prior-SOTA / competitor rows into `scores[]` for a table-backed measure. They stay in the source table; you point at it with `source_table_marker`. Two exceptions: the headline evaluated-system rows ON a dataset/benchmark Contribution root (they ARE the paper's own result), and prose mode (no tables — transcribe every reported comparison row).
- Do not transcribe a full ablation grid into `scores[]`. An `ablation` measure has empty `scores[]` and points at its table.
- Do not omit `source_table_marker` on a table-derived measure — without it the verbatim table cannot be attached and the measure becomes dataless.
- Do not create a `subject_id`, `evaluated_on`, or `measured_on` — they do not exist; use the global `evaluates` edge, `setup_ids`, and per-row `setup_id`.
- Do not create method/theory Contribution or Component units here; reference those nodes by id in `about` edges (they are materialized in the method section). A dataset/benchmark or `finding`-kind Contribution, however, IS materialized here.
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

The `mea:bleu` measure points at the leaderboard table (`source_table_marker: "§53"`, caption `"§52"`) and transcribes **only** the contribution's two rows (EN-DE and EN-FR), each pinned to its benchmark via `setup_id`; GNMT and every other baseline stay in the verbatim `[§53]` table, not retyped. `headline_result` carries the contribution number and the +2.0 delta in words. The ablation measure `mea:pos_enc_ablation` points at `[§55]` with **empty** `scores[]` — the full ablation grid is the blob — and mounts its finding via `finding_ids`. The table↔finding links are the `finding_ids` arrays; there are **no** `Measure --supports--> Finding` or `Finding --about--> Measure` edges. The only edges authored are the two `Finding --about--> Contribution`/`Component` edges. The structural edges (`mea:bleu --evaluates--> con:transformer`, `con:transformer --compares_to--> <baseline>`) already live in the global `relations`.

## Anchor

`anchor_id` should be the primary headline Measure (`mea:`) — the result that most directly validates the main finding. Do not anchor on an ExperimentSetup or Finding.

Final completeness check — before closing the JSON, verify: (1) every `mea:` id in `node_registry` appears in `measures[]`; (2) every `exp:` registry node with a substrate kind appears in `experiment_setups[]`, and every `con:` registry node of kind `dataset`/`benchmark`/`finding` appears in `contributions[]`; (3) every id in `finding_ids`/`setup_ids`/`setup_id` is defined in this response (per-row `setup_id` `""` is allowed where no configuration applies); (4) for a table-backed measure (`source_table_marker` set), `scores[]` is non-empty exactly when its `table_role` is `main_result`; (5) every author-stated limitation, cost analysis, statistical-significance statement, and figure-only main result has a Finding in `findings[]` — including Findings no `finding_ids` mounts.
