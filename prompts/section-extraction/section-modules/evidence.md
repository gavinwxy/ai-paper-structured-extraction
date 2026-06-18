SECTION FOCUS: evidence (blob-primary)

# Goal
You are filling the **evidence** section — capture the paper's **evaluation layer in one pass**.

Extract two layers:
1. **What was measured** — main results, transfer tests, ablations, robustness, costs.
2. **What those measurements mean** — the headline finding, ablation conclusions, limitations, mechanisms, costs, significance, future work.

**CRITICAL-1 — point at tables, do NOT retype them.** For every results table you create a Measure that *points* at the `<table>` block; code splices the verbatim table beside it. You transcribe only the contribution method's own rows, only for a main-result table.

**CRITICAL-2 — the headline finding is born here.** The headline contribution Finding is created in this section as a fresh `fnd:` id and linked with an `about` edge to the root Contribution. There is no separate finding section.

# The Core Rule: Point at Tables, Do Not Retype Them
- For every results table, create a Measure that **points** to the table's `<table>` block using `source_table_marker: "§N"`.
- **Do NOT copy full result tables.** For table-backed main results, transcribe into `scores[]` **only the contribution method's own rows**. Baselines, competitors, prior work, and full ablation grids stay in the pointed-at table blob.
- Use `source_table_marker` **only** from the *Source-table index* (appended at the end of this `section_focus`). Point at the `<table>` block — **never** the caption, prose, figure, or image.
- **Prose mode (whole-paper, no-table):** if the Source-table index contains no real `<table>` grids, omit `source_table_marker` and transcribe **all** explicitly reported comparison rows, **including baselines** (no table blob backs them up). This whole-paper case is the **only** one that admits baseline rows.

# Instructions — Extraction Order (Five Stages, In Order)
1. **Materialize the census.**
   - every `mea:` node → `measures[]`;
   - every substrate `exp:` node of kind `dataset`/`benchmark`/`task` → `experiment_setups[]`;
   - every `con:` node of kind `dataset`/`benchmark`/`finding` → `contributions[]`.
   Method and Component nodes are **referenced by id only**.
2. **Classify every indexed table:**
   - **skip** — configuration, hyperparameters, dataset statistics, notation, or prior-work context with no measured result;
   - **ablation** — component isolation, hyperparameter sweep, sensitivity, diagnostic Δ/gain/correlation table, or any table with no contribution row;
   - **main_result** — headline, leaderboard, transfer, or comparison table with contribution rows.
3. **Materialize censused measures with no table support.**
   - if a table reports the metric (its **own column**), attach the measure to that table;
   - if values appear only in prose/caption, transcribe **only the contribution's own stated** numbers — **no `source_table_marker`, not `main_result`** (a single-metric gap, **not** the whole-paper prose mode above — do **not** bring in baseline rows);
   - **never infer values from figure axes**, and **never point at a figure or a wrong-metric table** to fake a marker;
   - a numeric-free claim becomes a **Finding**, not a score row.
4. **Sweep prose, figures, captions, discussion, and limitations** — emit every interpretive Finding not already covered by a table.
5. **Author only Finding-centric relations**, then run the **Final Completeness Check**.

# Table Roles
**Always set `table_role` when `source_table_marker` is present.**

## `main_result`
Use when the table reports the contribution against alternatives under the paper's main protocol.
- `scores[]` **must be non-empty** — if you cannot fill it, this is **not** a `main_result` (reclassify as prose-mode with **no marker**, `ablation`, or a Finding);
- transcribe **only** contribution rows;
- emit `headline_result`;
- mount the headline Finding via `finding_ids`.

*For dataset/benchmark Contribution roots, the evaluated systems ON that resource count as the contribution's own result rows.*

## `ablation`
Use when the table isolates components, sweeps settings, probes sensitivity, or reports diagnostic quantities.
- `scores: []`;
- point at the table;
- create and mount ablation Finding(s) via `finding_ids`.

# Metric Identity
A `scores[]` value must belong to the **Measure's own metric**.
- **Composite cell** — if one cell contains multiple metrics, create **one Measure per metric sharing the same table marker**, and copy **only that metric's component**.
- **Relative value** — if a value is labeled Δ, gain, improvement, or reduction, treat it as a **relative-improvement** metric, **not** the underlying absolute metric.
- **Wrong-table guard** — a `source_table_marker` must point at a table that **contains this metric's own column**. **NEVER** point a Measure at a table of a *different* metric, a configuration table, or a **figure**, just to give a census node a marker. A metric reported **only in a figure or in prose** (no table column of its own) carries **no `source_table_marker`** and is **not** `main_result` — transcribe **the contribution's own stated** numbers (no marker, not `main_result`), or emit it as a **Finding**. An **empty `main_result` is never correct**: if you cannot fill `scores[]`, the measure is prose-mode (no marker), `ablation`, or a Finding — never `main_result` with a fabricated marker.

# Important Definitions — Units You May Define

## Measure
Fields: `name`, `unit`, `setup_ids`, optional `comparison_direction`, optional `objective_class`, plus `source_table_marker`, `caption_marker`, `table_role`, `headline_result`, `finding_ids`, `scores`.
- `unit` is **required and never blank**.
- `comparison_direction` ∈ `higher_is_better | lower_is_better | target`; **omit if unstated**.
- `source_table_marker` is **required for table-derived measures**, and set **only** when that table contains this metric's **own column**; a figure-only or prose-only metric carries **no marker** and is **not** `main_result` (see *Metric Identity → Wrong-table guard*).
- `caption_marker` points at the caption block when available.
- **Reuse a census `mea:` id** for the headline table carrying that metric; other tables for the same metric get **fresh** `mea:` ids.
- One table with multiple metrics → **multiple Measures sharing one `source_table_marker`**.

## scores
`scores[]` is a flat array of `{variant, value, variance, system_id, setup_id}`; optional `value_kind`, `opponent_id`, `judge_id`.
- **main_result** tables: include **contribution rows only**.
- **ablation** tables: leave **empty**.
- **prose mode** (whole-paper, no `<table>` grids indexed): include **all** explicitly reported comparison rows, including baselines. *(A single metric whose numbers live only in prose/caption is **not** this case — transcribe the contribution's own rows only.)*
- **Never collapse** dataset, split, language-pair, or protocol columns — **one row per (`variant` × `setup`)**.
- `variant` is built **only from printed labels**: row label plus relevant column/header labels.
- `value` is always a **string**; `variance` is `""` if not reported.
- Set `system_id` when the row's Contribution or Component node exists.
- Set `setup_id` to the exact dataset/split/protocol for that row; **create a configuration ExperimentSetup when needed**.

**Contribution-row test:**
- labels naming the contribution, "Ours", or a contribution component/variant **are** contribution rows;
- a citation marker implies baseline **only when the label does not name the contribution**;
- for dataset/benchmark roots, transcribe the **headline evaluated-system rows** on that resource.

## ExperimentSetup
Materialize **every substrate census node**: `dataset`, `benchmark`, `task`.
Create **configuration** setups **only when they scope emitted contribution rows**: `data_split`, `inference_protocol`, `training_config`, `ensembling`, `population`.
- Do **NOT** create a parallel Contribution for a standard evaluation dataset.
- A dataset/benchmark **released by the paper** is a **Contribution**, not an ExperimentSetup.
- Use **precise names**, not vague descriptions. Add a `description` **only** for a setup the paper itself constructs (own dataset, prompt suite, user study, custom protocol): one sentence of composition/coverage in the paper's **real names/numbers**. For a standard external benchmark, leave it an empty string unless a non-obvious subset or protocol is used. **Never** replace a specific setup with a vague restatement.

## Contribution
Materialize **only** Contribution nodes of kind `dataset`, `benchmark`, or `finding`.
Do **NOT** create method or component Contributions here — reference existing method/component ids only.

## Finding
Create **one headline Finding** plus **all interpretive Findings**.
Required: `kind`, `statement`. Optional: `polarity`, `effect_size`, `scope`.
Allowed `kind`: `descriptive | mechanistic | comparative | modeling | ablation_finding | failure_mode | theorem | lemma | bound`.

**Headline Finding — create exactly one:**
- fresh `fnd:` id;
- states the main answer established by the evidence;
- includes paper-stated headline numbers when available;
- has an `about` edge to the **root Contribution**;
- is mounted on the main-result Measure via `finding_ids`;
- do **NOT** copy `spine_summary.headline_result` verbatim.

**Interpretive Findings — completeness is the job (this layer is the most under-captured). ALWAYS emit, when stated, a separate Finding for every distinct author-stated:**
- **headline empirical/analysis claim** — a prevalence rate, a phenomenon's frequency, a diagnostic or characterization conclusion; for an analysis/empirical paper this is the **marquee result**, easy to miss because it is not a leaderboard row;
- ablation or sensitivity conclusion;
- mechanism or interpretability claim;
- comparative design conclusion;
- limitation or failure mode;
- method cost: dollars, tokens, GPU-hours, latency, memory;
- statistical-significance claim;
- theorem, lemma, or bound proved by the paper;
- future-work direction that affects interpretation;
- figure-only conclusion.

*A figure-only finding is still a Finding even if no table supports it. A limitation requires a stated inability, dependency, or non-extension — a mere extension proposal is **future work**, not a `failure_mode`.*

# Output Detail Level (Tiered Strategy)
- **`scores[]`: faithful & contribution-only.** Transcribe the contribution's rows exactly as printed, every (variant × split); baselines stay in the blob.
- **`findings[]`: completeness is the job.** A separate Finding for each distinct conclusion above — this "what it means" layer is easy to under-capture.
- **`headline_result` / `statement`: the paper's own numbers.** Never invent a number; never read one off a figure's axes.

# Relations
Author **only** these relations in `relations[]`:

| relation | source → target |
|---|---|
| `about` | `Finding` → {`Contribution`, `Component`, `ExperimentSetup`} |
| `supports` | `Finding` → `Finding` |
| `supports` | `Contribution` → `Finding` |

- headline Finding: `Finding --about--> root Contribution`;
- ablation Finding: `Finding --about--> isolated Component` when one exists;
- theorem/proof Contribution: `Contribution --supports--> proven-result Finding`;
- table↔Finding links are stored **only** in `Measure.finding_ids`;
- do **NOT** create `Finding --about--> Measure`;
- do **NOT** create `Measure --supports--> Finding`;
- do **NOT** author `evaluates`, `part_of`, `compares_to`, `measured_on`, or any other structural edge.

## Findings about data and metrics, and multi-step chains
A Finding is **not always about the method**:
- **about a dataset / benchmark** — a conclusion about the *data itself* (a label bias, a saturated benchmark) → `Finding --about--> exp:<dataset>`. Example: "ImageNet-V2 shows a 5-point drop from a harder label distribution" → a `Finding` (`polarity: negative`) `about` `exp:imagenet_v2`.
- **about a metric** — a conclusion about a *measure's behavior* (it saturates, is gameable) → **mount the Finding on that Measure via its `finding_ids`** (not an edge).
- **multi-step chain** — when one observation licenses a conclusion, connect them: `Finding(observation) --supports--> Finding(conclusion)`. Do **NOT** flatten a derivation into two unconnected siblings.

# Mental Sandbox / Worked Example
Assume the blocks include caption "**Table 4: BLEU on WMT14**" = `[§52]`, the leaderboard `<table>` = `[§53]`, and a positional-encoding ablation `<table>` = `[§55]`.

{
  "section": {
    "section_type": "evidence",
    "anchor_id": "mea:bleu",
    "measures": [
      {
        "id": "mea:bleu", "type": "Measure", "name": "BLEU", "unit": "BLEU",
        "setup_ids": ["exp:wmt2014_en_de", "exp:wmt2014_en_fr"],
        "comparison_direction": "higher_is_better",
        "source_table_marker": "§53", "caption_marker": "§52", "table_role": "main_result",
        "headline_result": "Transformer (big) reaches 28.4 BLEU on WMT14 EN-DE and 41.0 on EN-FR, +2.0 BLEU over the prior best.",
        "finding_ids": ["fnd:headline"],
        "scores": [
          {"variant": "Transformer (big)", "value": "28.4", "variance": "", "system_id": "con:transformer", "setup_id": "exp:wmt2014_en_de"},
          {"variant": "Transformer (big)", "value": "41.0", "variance": "", "system_id": "con:transformer", "setup_id": "exp:wmt2014_en_fr"}
        ],
        "provenance": ["§53"]
      },
      {
        "id": "mea:pos_enc_ablation", "type": "Measure", "name": "BLEU under positional-encoding ablation", "unit": "BLEU",
        "setup_ids": [], "comparison_direction": "higher_is_better",
        "source_table_marker": "§55", "table_role": "ablation",
        "finding_ids": ["fnd:pos_enc_matters"], "scores": [], "provenance": ["§55"]
      }
    ],
    "experiment_setups": [
      {"id": "exp:wmt2014_en_de", "type": "ExperimentSetup", "kind": "benchmark", "name": "WMT 2014 English-German", "provenance": ["§53"]},
      {"id": "exp:wmt2014_en_fr", "type": "ExperimentSetup", "kind": "benchmark", "name": "WMT 2014 English-French", "provenance": ["§53"]}
    ],
    "findings": [
      {"id": "fnd:headline", "type": "Finding", "kind": "comparative", "statement": "An attention-only model outperforms the best prior recurrent and convolutional systems on WMT14 translation.", "polarity": "positive", "effect_size": "+2.0 BLEU", "provenance": ["§53"]},
      {"id": "fnd:pos_enc_matters", "type": "Finding", "kind": "ablation_finding", "statement": "Removing positional encodings lowers BLEU by 2.2, showing they are necessary.", "polarity": "negative", "effect_size": "-2.2 BLEU", "provenance": ["§55"]}
    ],
    "relations": [
      {"source_id": "fnd:headline", "relation": "about", "target_id": "con:transformer", "provenance": ["§53"]},
      {"source_id": "fnd:pos_enc_matters", "relation": "about", "target_id": "cmp:positional_encoding", "provenance": ["§55"]}
    ]
  }
}

**Key lesson:** `mea:bleu` *points* at `[§53]` and transcribes **only** the contribution's two rows (one per split); baselines stay in the blob. The ablation Measure points at `[§55]` with **empty** `scores[]` and mounts its finding via `finding_ids`. Table↔Finding links live in `finding_ids` — the only authored edges are the two `Finding --about-->` edges; `evaluates`/`compares_to` already live in the global `relations`.

# Anchor
`anchor_id` must be the **primary headline `mea:` id**. Do NOT anchor on an ExperimentSetup or Finding.

# Anti-Patterns
Do **NOT**:
- retype baseline, competitor, or prior-SOTA rows for table-backed measures;
- transcribe full ablation grids;
- omit `source_table_marker` for table-derived measures;
- create `subject_id`, `evaluated_on`, or `measured_on`;
- create method or component units here;
- leave `system_id` blank when the row's node exists;
- assign one census `mea:` id to multiple Measures;
- read numeric values from figure axes;
- collapse split, dataset, language-pair, or protocol columns.

# Final Completeness Check
Before closing the JSON, verify:
1. every `mea:` registry id appears in `measures[]`;
2. every substrate `exp:` registry id appears in `experiment_setups[]`;
3. every `con:` registry id of kind `dataset`/`benchmark`/`finding` appears in `contributions[]`;
4. every id in `finding_ids`, `setup_ids`, and row-level `setup_id` is defined locally — except row `setup_id: ""` when unambiguous;
5. table-backed `main_result` Measures have **non-empty** `scores[]`;
6. table-backed `ablation` Measures have **empty** `scores[]`;
7. every stated limitation, cost, significance claim, figure-only result, and future-work interpretation has a Finding;
8. the headline Finding has an `about` edge to the root Contribution.
