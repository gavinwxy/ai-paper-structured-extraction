SECTION FOCUS: evidence (blob-primary)

This section captures the paper's evaluation layer in one pass: both **what was measured** (how the method performs on benchmarks and transfer tests) and **what those measurements mean** (what ablations reveal, what limits the result). The old experiment/analysis split is gone — measurement and interpretation are decided together here, with the whole results table in view.

This section is also where the paper's discovery arc closes: it states the **headline contribution finding** — the one-sentence answer the evidence establishes — alongside the finer interpretive findings. There is no separate finding section. The contribution finding is normally born here like every other finding — **except** when the census planned the paper's deliverable as a `contribution_finding` root (an analysis/mechanistic paper whose *result* is the contribution, with no proposed artifact): then you **materialize** that finding by reusing its `node_id`, instead of borning a fresh one.

## The core rule: point at tables, do not transcribe them

**You never retype a results table.** The paper you are given is segmented into top-level blocks, each tagged `[§N]` at its very start. A `<table>` and its caption are **separate adjacent blocks** — e.g. the caption "**Table 3: …**" is block `[§52]` and the `<table>…</table>` immediately after it is block `[§53]`. For each results table you create a Measure that **points** at the table by its `[§N]` marker; code then slices that table and its caption verbatim and stores them beside your Measure. The bulky content — every baseline row, every full ablation grid — stays in the pointed-at table, **not** in your output.

You transcribe, as structured `scores[]` rows, **only the contribution method's own numbers**, and only for a **main-results** table. Everything else is carried by the verbatim table blob.

**Where to point.** A *Source-table index* is given to you at the end of this guidance: it lists the EXACT `[§N]` markers of every block that actually contains a `<table>` grid, with each table's caption/columns. Every `source_table_marker` you emit MUST be one of those markers — match a measure to its table by the caption/columns in the index. The result data lives in the `<table>` block, which is a **separate block** from the paragraph that discusses it and from any figure/image (`![Table N ...]`) of the same table — never point at the prose paragraph or the image; point at the `<table>` block from the index. If the index says the paper has no `<table>` grids, omit `source_table_marker` and transcribe the contribution's numbers as `scores[]` rows (prose mode).

This is the whole point of the merged section: one editorial call per table (main-result vs ablation), made with the full table visible, instead of two blind passes double-extracting or dropping rows — and the leaderboard of competitors is preserved verbatim instead of being laboriously (and lossily) retyped.

## Units you may define

- `Measure` (array `measures`): one per results table per metric — the addressable node that points at a source table and (for a main result) carries the contribution method's own score rows. Materialize each Measure census node; you may add one the census missed. A table reporting several metrics (BLEU **and** latency) becomes several Measures **sharing the same `source_table_marker`**.
- `ExperimentSetup` (array `experiment_setups`): the merged "what it ran on / under what configuration" type. Two flavours, told apart by `role`:
  - **substrate** (`role: dataset | benchmark | task | theoretical_setting | structural_class | contribution_resource`) — the datasets, benchmarks, and tasks the method is evaluated on, the formal regime/structural family a **theoretical** result holds under (`theoretical_setting`/`structural_class`), plus (`contribution_resource`) a dataset/benchmark that is itself the paper's primary deliverable. Materialize **every** substrate census node in `node_registry`, including `task`, any theoretical setting, and any `contribution_resource` node, reusing each `node_id` and its `role`. A `contribution_resource` is the document root: the contribution's scores reported on it are `scores[]` rows on Measures whose `setup_ids`/per-row `setup_id` point at this very ExperimentSetup, and the headline contribution finding points `about` it.
  - **configuration** (`role: data_split | inference_protocol | training_config | ensembling | population`) — a setup that scopes a contribution score row. **Born here**, with a fresh `exp:` id. You only need configurations that scope a **contribution** row you actually emit — do not born a split just to bind a baseline row you are no longer transcribing.
- `Finding` (array `findings`): the **headline contribution finding** (the paper's central established answer) plus the interpretive findings — ablation conclusions, sensitivity conclusions, limitations, failure modes. Born here — **except** a `contribution_finding` census root, which is materialized by reusing its `node_id` (see "headline contribution finding" below).

### Measure
Fields: `name`, `unit`, `setup_ids`, optional `comparison_direction`, optional `objective_class`, and the blob-primary fields `source_table_marker`, `caption_marker`, `table_role`, `headline_result`, `finding_ids`, plus `scores`.

- `unit`: non-empty measurement unit such as `BLEU`, `%`, `ms`, `F1`, `perplexity`, or `unitless`. Never blank.
- `comparison_direction` (optional): `higher_is_better | lower_is_better | target | unspecified`. Keep it per-measure — a BLEU measure and a latency measure from the same table have **different** directions.
- `objective_class` (optional): which axis of a **multi-objective** evaluation this measure sits on — `primary_quality` (the headline quality metric, the default — omit it), `cost_efficiency` (latency/compute/memory/params), `fairness`, `safety`, `robustness`. Set it on the *non-primary* axes of a trade-off so a cost/fairness/safety measure is not read as one more uniformly-positive quality number. Omit for an ordinary headline-quality measure.
- `source_table_marker`: the `[§N]` block id of the `<table>` this measure reads, written as `"§N"` (e.g. `"§53"`) — and it MUST be one of the markers in the *Source-table index* below (those are the only blocks that hold a `<table>` grid). **Set it on every table-derived measure**; omit it only when the index lists no tables (prose/figure-only paper) and you are transcribing numbers directly.
- `caption_marker`: the `[§N]` block id of the table's caption block (e.g. `"§52"`), written as `"§N"`. The caption is almost always the block **immediately before** the `<table>` block ("**Table k: …**"). Code slices it verbatim — you only point. Omit when the table has no caption block.
- `table_role`: `main_result` or `ablation` (defaults to `main_result` if omitted).
  - `main_result` — a headline comparison / leaderboard / transfer table whose purpose is to show how the contribution performs against alternatives. You **MUST** emit `scores[]` rows for the **contribution method** (its variants × splits — see below) **plus** a `headline_result`. A `main_result` Measure with **empty** `scores[]` is an error: the contribution's own number is in the `<table>` you pointed at, so transcribe its row(s) — the baselines (only) stay in the blob. If the table truly has no contribution row (a pure prior-work comparison that is context, not your result), it is not a `main_result` — reclassify or drop it.
  - `ablation` — a study that isolates a component, sweeps a hyperparameter, or probes sensitivity ("without attention", "−BN", "K = 2,4,8,16"). This is the **only** role that may leave `scores[]` empty (`[]`) — the verbatim table carries the whole grid. Mount the ablation Finding(s) via `finding_ids`.
- `headline_result`: the contribution's key one-liner drawn from this table, in the paper's own numbers (e.g. `"Transformer (big) reaches 28.4 BLEU on WMT14 EN-DE and 41.0 on EN-FR, +2.0 BLEU over the prior best"`). **Emit it whenever the contribution's headline number is in this table — for either `table_role`.** This is the durable text backstop for the contribution's result, independent of the structured rows. Put the improvement / delta over baselines **here, in words** ("+2.0 BLEU over GNMT") rather than as a structured field.
- `finding_ids`: ids of the Findings this table evidences, born in this same response (e.g. `["fnd:headline", "fnd:pos_enc_matters"]`). This is the **canonical table→finding link** — it replaces the old `Measure --supports--> Finding` and `Finding --about--> Measure` edges (do not author those). The mapping is flexible: a finding id may appear on several measures, and a measure may mount several findings. A main-result measure normally mounts the headline finding; an ablation measure mounts its ablation finding(s).
- `setup_ids`: IDs of **local** ExperimentSetup units that scope this measure (the datasets/splits/protocols the **contribution rows** were computed under), defined or materialized in this same response. A deployable benchmark measure is normally scoped by at least one setup; an `ablation` measure with empty `scores[]` may carry none (`[]`). There is no `subject_id` or `evaluated_on` field — the method a measure evaluates is the global `evaluates` edge, already established.
- `scores`: a flat array of `{variant, value, variance, system_id, setup_id}`, with optional `value_kind`/`opponent_id`/`judge_id`. For a `main_result` table this carries **the contribution method's own rows** — its variants (base/big, ResNet-50/101/152) across the datasets/splits it was evaluated on — and it must be **non-empty** (the contribution's headline number(s) belong here as structured rows; this is the queryable core). **Do not transcribe baselines or prior-SOTA rows** — they remain in the verbatim table blob, retrievable by `source_table_marker`. Leave `scores[]` empty **only** for an `ablation` table. For a prose/figure number with no table, transcribe it as a row here and omit `source_table_marker`.
  - `variant`: names the contribution configuration as the paper labels it (`"Transformer (big)"`, `"Ours (ResNet-101)"`).
  - `value`: always a string (`"28.4"`, `"28.4-29.1"`, or a short categorical string); `variance` is `""` when no uncertainty is reported.
  - `value_kind` (optional): how to read `value`. Omit (⇒ numeric) for an ordinary leaderboard number. Set it for a **theoretical** result: `symbolic` (a closed form like `"2/Δ·logT"`), `asymptotic` (a complexity/rate class like `"O(n^6)"`), `qualitative`, or `curve`.
  - `opponent_id` (optional): for a **pairwise / win-rate** contribution row, the Method id of the system this row was compared against (`system_id` = system A, `opponent_id` = system B, `value` = A's win rate vs B). Omit for an ordinary absolute-score row.
  - `judge_id` (optional): for a **judged** row, the id of the judge — a Method, or the `inference_protocol`/`population` ExperimentSetup materialized for the evaluator. Omit when the score needs no judge.
  - `system_id`: the id of the **contribution Method this row reports** (`mth:transformer`). Set it whenever a Method node for the contribution variant exists in `node_registry`. Use `""` only when no node represents the row. Two variant rows of the same family (base/big) share one `system_id`.
  - `setup_id`: the id of the **local ExperimentSetup** this contribution row was measured on — the dataset/split for the row. **This is how the row binds to its data.** Point it at the substrate ExperimentSetup for the row's dataset/split; leave `""` only when the measure's `setup_ids` already scope every row uniformly (a single-split measure).
- **Never collapse a dataset/split column of the contribution.** When the contribution is reported across several datasets/splits/language pairs, keep **one contribution row per (variant × split)** and pin each row's `setup_id` — do not keep one number per variant, which silently drops the other column's contribution values. (You no longer keep baseline rows, so this rule now applies only to the contribution's own numbers.)

### ExperimentSetup — substrate and configuration
Fields: `role`, `name`, optional `description`.
- `role`: which experimental ingredient this is.
  - substrate — `dataset` (data trained/evaluated on), `benchmark` (a standardized dataset+protocol), `task` (the problem solved/evaluated), `theoretical_setting` (the regime/assumptions a theoretical result holds under), `structural_class` (the structural family a result ranges over). **Materialized** from census; reuse the node's `role`.
  - configuration — `data_split`, `inference_protocol` (beam search beam=4/α=0.6, 10-crop), `training_config`, `ensembling`, `population`. Born here, but only when it scopes a contribution row you emit.
- `name`: the setup's name/label — a dataset name (`WMT 2014 English-German`), a split label (`newstest2014`), a configuration name (`beam search, beam=4`).
- `description` (optional): one sentence with the paper's real names/numbers when the name alone is not enough; empty string otherwise. Never replace a specific setup with a vague generic restatement.
- **Enumerate each distinct configuration as its own ExperimentSetup** when it scopes a contribution result — a cross-dataset transfer protocol, a robustness / distribution-shift setup, a user study, a timing protocol. Do **not** capture hardware or a global hyperparameter that scopes no contribution measure.

### Finding — contribution finding and interpretive findings
Fields: `role`, `statement`; optional payload `polarity`, `effect_size`, `scope`.
- `polarity` (optional): the sign of the finding's headline effect — `positive`, `negative`, `neutral`, `mixed`. Set it whenever the finding has a clear direction. Omit when not applicable.
- `effect_size` (optional): the magnitude in the paper's own terms (`"+2.1 BLEU"`, `"3 orders of magnitude faster"`, `"r=0.83"`). Omit when none is stated.
- `scope` (optional): the conditions under which the finding holds (`"on 11 of 12 tasks"`, `"in low-resource regimes"`). Omit when unrestricted.

First, capture the **headline contribution finding**: the single sentence that states what the paper establishes — the answer to the research problem. Its `role` is usually `comparative` ("A outperforms B") or `modeling` (a formal/architectural claim) — or `theorem`/`bound` when the headline is a **proven** statement. One headline finding, the way the abstract states it. How it attaches has two cases:
- **Usual (a method/resource paper).** Born the finding with a fresh `fnd:` id and author an `about` edge to the **root contribution** (the `node_registry` node with role `contribution`, or the `contribution_resource` ExperimentSetup for a dataset/benchmark deliverable). This draws the problem→answer throughline. Mount this finding on the main-result Measure via that Measure's `finding_ids`.
- **An analysis paper with a `contribution_finding` root.** When `node_registry` contains a node with role `contribution_finding` (a `fnd:` id — the paper's deliverable *is* a result), that node **is** the headline finding: **materialize** it by reusing its exact `node_id`, give it a content `role` and `statement`, and author **no** `about` edge for it. Assembly draws the closing `resolves` edge from it to the Problem.

Then enumerate **every distinct interpretive finding** the evaluation supports — this "what it means" layer is easy to under-capture, so treat completeness here as the job. Each of the following, when the paper states it, is its **own** Finding — extract the paper's own finding in its own terms:
- **ablation / sensitivity conclusions** (`role: ablation_finding`), including fine-grained sub-findings — a saturation point, a capacity ceiling, which component contributes most. Mount each on the ablation Measure (the one pointing at the ablation table) via `finding_ids`.
- **mechanism / interpretability** findings (`role: mechanistic`) — *why* the method works.
- **comparative analysis** findings (`role: comparative`) — an analytical "design choice A beats B" conclusion, distinct from a deployable score row.
- **limitations and failure modes** (`role: failure_mode`).
- **proven theoretical results** (`role: theorem | lemma | bound`) — a result established **by proof**, not measurement. The formal statement is a Method (`method_kind: theorem`/`lemma`/`bound`) in the method section; this Finding carries what it establishes, and the theorem-Method `supports` it (see Relations). A symbolic/asymptotic value goes in a score row with the matching `value_kind`.
- **future-work directions** that shape interpretation (`role: descriptive`).

## Relations

This section authors only these Finding-centric edges in `relations[]`:

| relation | source → target | meaning |
|---|---|---|
| `about` | Finding → {Method, ExperimentSetup} | the finding is about that node (for an ablation, the **component** it isolates; for a data/benchmark conclusion, the `exp:` substrate) |
| `supports` | Finding → Finding | one local finding supports another (a derivation: observation → conclusion) |
| `supports` | Method → Finding | a theorem/proof Method establishes a proven-result Finding (the formal analogue of measurement) |

- For the headline contribution finding: emit `Finding --about--> <root>`, pointing at the `node_registry` node whose role is `contribution` (an `mth:` id) or `contribution_resource` (an `exp:` id). **Exception:** if the root is a `contribution_finding` node, emit **no** `about` edge for it.
- For each ablation finding: emit `Finding --about--> mth:<component>`, pointing at the specific component node from `node_registry` (not the whole-system root) when the ablation isolates one part. The link **to the data** is the `finding_ids` mount on the ablation Measure — **do not** author a `Measure --supports--> Finding` edge.
- For a proven theoretical result: emit `Method --supports--> Finding` from the theorem-Method to the proven-result Finding. The theorem-Method binds to its regime via `assumes`, already established by the relation pass — do not author `assumes` here.
- **Do not author `Finding --about--> Measure` or `Measure --supports--> Finding`** — the table↔finding link is now the Measure's `finding_ids`, not an edge.
- Do not author `evaluates`, `part_of`, `compares_to`, or `measured_on` — those are global structural edges already established by the relation pass (or removed). Never put a Finding or Measure on either end of a structural edge.

### Findings about data and metrics, and multi-step chains

A finding is **not always about the method**:
- **about a dataset / benchmark** — a conclusion about the *data itself* (a label bias, a saturated benchmark): `Finding --about--> exp:<dataset>`. Example: "ImageNet-V2 shows a 5-point drop from a harder label distribution" → a `Finding` (`polarity: negative`) `about` `exp:imagenet_v2`.
- **about a metric** — a conclusion about a *measure's behavior* (it saturates, is gameable): there is no `about`→Measure edge; **mount the finding on that Measure via its `finding_ids`** instead.
- **multi-step chain** — when one observation licenses a conclusion, connect them with `supports`: `Finding(observation) --supports--> Finding(conclusion)`. Do not flatten a derivation into two unconnected siblings.

## Salience filter

- Extract best/final contribution results on primary benchmarks, and transfer/generalization results that demonstrate the main finding — as contribution `scores[]` rows pointing at their tables.
- Extract contribution scale/capacity variants when presented as first-class configurations.
- Capture the **full** "what this means" layer as Findings — every distinct ablation, mechanism, comparative, limitation, and future-work finding — and mount each on the table that evidences it.
- You no longer transcribe baseline rows at all; they are preserved verbatim in the pointed-at table blob. Skip a table only when it is pure context (dataset statistics, notation) that evidences no contribution result and no finding — do not create an empty Measure for it.

## Anti-patterns

- Do not retype baseline / prior-SOTA / competitor rows into `scores[]`. They stay in the source table; you point at it with `source_table_marker`.
- Do not transcribe a full ablation grid into `scores[]`. An `ablation` measure has empty `scores[]` and points at its table.
- Do not emit a `main_result` measure with empty `scores[]`. The contribution's own row(s) are in the `<table>` you point at — transcribe them; only the baselines stay in the blob. Empty `scores[]` is for `ablation` only.
- Do not omit `source_table_marker` on a table-derived measure — without it the verbatim table cannot be attached and the measure becomes dataless.
- Do not author `Finding --about--> Measure` or `Measure --supports--> Finding` — use the Measure's `finding_ids`.
- Do not create a `subject_id`, `evaluated_on`, or `measured_on` — they do not exist; use the global `evaluates` edge, `setup_ids`, and per-row `setup_id`.
- Do not create Method units here; reference method nodes by id in `about` edges.
- Do not leave a contribution row's `system_id` blank when its Method node exists in `node_registry`.

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
          {"variant": "Transformer (big)", "value": "28.4", "variance": "", "system_id": "mth:transformer", "setup_id": "exp:wmt2014_en_de"},
          {"variant": "Transformer (big)", "value": "41.0", "variance": "", "system_id": "mth:transformer", "setup_id": "exp:wmt2014_en_fr"}
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
      {"id": "exp:wmt2014_en_de", "type": "ExperimentSetup", "role": "benchmark", "name": "WMT 2014 English-German", "provenance": ["§53"]},
      {"id": "exp:wmt2014_en_fr", "type": "ExperimentSetup", "role": "benchmark", "name": "WMT 2014 English-French", "provenance": ["§53"]},
      {"id": "exp:beam_search", "type": "ExperimentSetup", "role": "inference_protocol", "name": "Beam search (beam=4, α=0.6)", "description": "Beam search with beam size 4 and length penalty alpha=0.6.", "provenance": ["§53"]}
    ],
    "findings": [
      {"id": "fnd:headline", "type": "Finding", "role": "comparative", "statement": "An attention-only model outperforms the best prior recurrent and convolutional systems on WMT14 translation.", "polarity": "positive", "effect_size": "+2.0 BLEU", "provenance": ["§53"]},
      {"id": "fnd:pos_enc_matters", "type": "Finding", "role": "ablation_finding", "statement": "Removing positional encodings lowers BLEU by 2.2, showing they are necessary for the attention-only model.", "polarity": "negative", "effect_size": "-2.2 BLEU", "provenance": ["§55"]}
    ],
    "relations": [
      {"source_id": "fnd:headline", "relation": "about", "target_id": "mth:transformer", "provenance": ["§53"]},
      {"source_id": "fnd:pos_enc_matters", "relation": "about", "target_id": "mth:positional_encoding", "provenance": ["§55"]}
    ]
  }
}

The `mea:bleu` measure points at the leaderboard table (`source_table_marker: "§53"`, caption `"§52"`) and transcribes **only** the contribution's two rows (EN-DE and EN-FR), each pinned to its benchmark via `setup_id`; GNMT and every other baseline stay in the verbatim `[§53]` table, not retyped. `headline_result` carries the contribution number and the +2.0 delta in words. The ablation measure `mea:pos_enc_ablation` points at `[§55]` with **empty** `scores[]` — the full ablation grid is the blob — and mounts its finding via `finding_ids`. The table↔finding links are the `finding_ids` arrays; there are **no** `Measure --supports--> Finding` or `Finding --about--> Measure` edges. The only edges authored are the two `Finding --about--> Method` edges. The structural edges (`mea:bleu --evaluates--> mth:transformer`, `mth:transformer --compares_to--> mth:gnmt`) already live in the global `relations`.

## Anchor

`anchor_id` should be the primary headline Measure (`mea:`) — the result that most directly validates the main finding. Do not anchor on an ExperimentSetup or Finding.
