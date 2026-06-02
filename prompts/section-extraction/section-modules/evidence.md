SECTION FOCUS: evidence

This section captures the paper's evaluation layer in one pass: both **what was measured** (how the method performs on benchmarks and transfer tests) and **what those measurements mean** (what ablations reveal, what limits the result). The old experiment/analysis split is gone — measurement and interpretation are decided together here, with the whole results table in view, which is exactly the editorial call that the split forced two blind parallel passes to make separately.

This section is also where the paper's discovery arc closes: it states the **headline contribution finding** — the one-sentence answer the evidence establishes — alongside the finer interpretive findings. There is no separate finding section; the contribution finding is born here, like every other finding.

This section **materializes** the Measure census nodes and the substrate ExperimentSetup census nodes (dataset/benchmark/task — enriching them with the fields below) and **creates** the born configuration ExperimentSetup units and Finding units. The `evaluates` (Measure → Method) edges are already in the global `relations` from the relation pass — do not restate them. There is no `measured_on` edge: a measure binds to the dataset/split it ran on through each score row's `setup_id`. You author only the Finding-centric edges (`about`, `supports`).

## Units you may define

- `Measure` (array `measures`): headline target-method results and diagnostic ablation/sensitivity values. Materialize each Measure census node; you may add one the census missed.
- `ExperimentSetup` (array `experiment_setups`): the merged "what it ran on / under what configuration" type. Two flavours, told apart by `role`:
  - **substrate** (`role: dataset | benchmark | task | theoretical_setting | structural_class | contribution_resource`) — the datasets, benchmarks, and tasks the method is evaluated on, the formal regime/structural family a **theoretical** result holds under (`theoretical_setting`/`structural_class`), plus (`contribution_resource`) a dataset/benchmark that is itself the paper's primary deliverable. Materialize **every** substrate census node in `node_registry`, including `task`, any theoretical setting, and any `contribution_resource` node, reusing each `node_id` and its `role`. A `contribution_resource` is the document root: the baseline scores reported on it are `scores[]` rows on Measures whose `setup_ids`/per-row `setup_id` point at this very ExperimentSetup, and the headline contribution finding points `about` it — so a benchmark contribution carries its numbers directly, with no duplicate Method twin.
  - **configuration** (`role: data_split | inference_protocol | training_config | ensembling | population`) — a setup that scopes a reported number. **Born here**, with a fresh `exp:` id.
- `Finding` (array `findings`): the **headline contribution finding** (the paper's central established answer) plus the interpretive findings — ablation conclusions, sensitivity conclusions, limitations, failure modes. **All born here.**

### Measure
Fields: `name`, `unit`, `setup_ids`, optional `comparison_direction`, optional `objective_class`, and `scores`.
- `unit`: non-empty measurement unit such as `BLEU`, `%`, `ms`, `F1`, `perplexity`, or `unitless`. Never blank.
- `comparison_direction` (optional): `higher_is_better | lower_is_better | target | unspecified`.
- `objective_class` (optional): which axis of a **multi-objective** evaluation this measure sits on — `primary_quality` (the headline quality metric, the default — omit it), `cost_efficiency` (latency/compute/memory/params), `fairness`, `safety`, `robustness`. Set it on the *non-primary* axes of a trade-off (the accuracy-vs-cost, accuracy-vs-fairness tension) so a cost/fairness/safety measure is not read as one more uniformly-positive quality number. Omit for an ordinary headline-quality measure.
- `setup_ids`: IDs of **local** ExperimentSetup units that scope this measure (the datasets/splits/protocols it was computed under), defined or materialized in this same response. A deployable benchmark measure is normally scoped by at least one setup; a diagnostic ablation measure may carry none (`[]`). There is no `subject_id` or `evaluated_on` field — the method a measure evaluates is the global `evaluates` edge, already established.
- `scores`: a flat array of `{variant, value, variance, system_id, setup_id}`, with an optional `value_kind` — one entry per **system reported under this measure**, covering both the method family's own variants **and every baseline / prior-SOTA system the paper compares against**. One entry per system per split — do not pack multiple numbers into one entry.
  - `variant`: names the system as the paper labels it (`"Transformer (big)"`, `"GNMT"`, `"ConvS2S"`).
  - `value`: always a string ("28.4", "28.4-29.1", or a short categorical string); `variance` is "" when no uncertainty is reported.
  - `value_kind` (optional): how to read `value`. Omit it (⇒ numeric) for an ordinary leaderboard number. Set it for a **theoretical** result so a formal value is not forced into a fake leaderboard: `symbolic` for a closed-form expression (`"2/Δ·logT"`), `asymptotic` for a complexity/rate class (`"O(n^6)"`, `"PSPACE-complete"`), `qualitative` for a categorical verdict, `curve` for a trend. For a symbolic/asymptotic measure there is usually no monotone better/worse, so omit `comparison_direction` or set it `unspecified`, and `variance` is normally `""`.
  - `opponent_id` (optional): for a **pairwise / win-rate** row (A-vs-B preference), the Method id of the system this row was compared against — `system_id` is system A, `opponent_id` is system B, and `value` is A's win rate vs B. This rescues the opponent from being buried in the `variant` string. Omit for an ordinary absolute-score row.
  - `judge_id` (optional): for a **judged** row (LLM-as-judge or human evaluation), the id of the judge — a Method, or the `inference_protocol`/`population` ExperimentSetup materialized for the evaluator. Omit when the score needs no judge.
  - `system_id`: the id of the **Method unit this row reports** — the contribution variant (`mth:transformer`) or the compared-against baseline (`mth:gnmt`). This is what turns the row into a structured comparison instead of a free-text label, so **set it whenever a Method node for the system exists in `node_registry`**. Use `""` only when no node represents the row (e.g. an ensemble-of-baselines the census did not capture). Two variant rows of the same family (base/big) share one `system_id`.
  - `setup_id`: the id of the **local ExperimentSetup** this row was measured on — the dataset/split for the row. **This is how the row binds to its data** (the old `measured_on` edge is gone). Point it at the substrate ExperimentSetup for the row's dataset/split; leave `""` only when the measure's `setup_ids` already scope every row uniformly (a single-split measure).
- **Never collapse a dataset/split column.** When the same measure is reported across several datasets, splits, or language pairs (a BLEU table with EN-DE *and* EN-FR columns, an mAP table across COCO/VOC), keep **one row per (system × split)** and pin each row's `setup_id` to its split's ExperimentSetup — do not keep one number per system, which silently drops the other column's values and mixes incomparable scores under one measure. When the census already gave you a substrate node per split (one per language pair), point at those; when a single dataset has finer splits the census did not break out (dev/test), born a `data_split` ExperimentSetup per split so each row has a `setup_id` to point at.

### ExperimentSetup — substrate and configuration
Fields: `role`, `name`, optional `description`.
- `role`: which experimental ingredient this is.
  - substrate — `dataset` (data trained/evaluated on), `benchmark` (a standardized dataset+protocol), `task` (the problem solved/evaluated), `theoretical_setting` (the regime/assumptions a theoretical result holds under — e.g. "convex Lipschitz losses", "a PDDL planning domain"), `structural_class` (the structural family a result ranges over — e.g. "bounded-degree graphs", "two-player zero-sum games"). **Materialized** from census; reuse the node's `role`.
  - configuration — `data_split` (the dataset/subset/split/language pair a measure was computed on, finer than a census substrate node), `inference_protocol` (a test-time procedure: beam search beam=4/α=0.6, 10-crop single-scale, single-view), `training_config` (a training/compute setup that scopes a reported number: fine-tuning regime, training steps), `ensembling` (a multi-model or multi-scale combination presented as a configuration — kept distinct because an ensemble number is not a fair peer of a single-model one), `population` (a study population / cohort, e.g. a human-evaluation panel).
- `name`: the setup's name/label — a dataset name (`WMT 2014 English-German`), a split label (`newstest2014`), or a configuration name (`beam search, beam=4`).
- `description` (optional): one sentence naming the concrete setup with the paper's real names and numbers when the name alone is not enough; empty string otherwise. Never replace a specific setup with a vague generic restatement — that loses the recall the unit exists to carry.
- **Enumerate each distinct configuration as its own ExperimentSetup.** A cross-dataset generalization or transfer protocol, a robustness / distribution-shift setup, a user study, and a timing protocol each get their **own** configuration unit — even when no separate Measure attaches to it. Do not collapse several named setups into one. Do **not** capture hardware (GPU model/count) or a global hyperparameter that scopes no measure — those carry no edge and are out of scope.

### Finding — contribution finding and interpretive findings
Fields: `role`, `statement`; optional payload `polarity`, `effect_size`, `scope`.
- `polarity` (optional): the sign of the finding's headline effect, from the method/hypothesis's perspective — `positive` (confirms/improves), `negative` (refutes/degrades), `neutral` (no significant effect, or an explicit null result), `mixed` (direction depends on conditions). Set it whenever the finding has a clear direction — this is what lets a positive result be told apart from a null or negative one. Omit when not applicable.
- `effect_size` (optional): the magnitude of the effect in the paper's own terms (`"+2.1 BLEU"`, `"3 orders of magnitude faster"`, `"r=0.83"`). Lift the number out of the prose instead of leaving it buried in `statement`. Omit when none is stated.
- `scope` (optional): the conditions or range under which the finding holds (`"on 11 of 12 tasks"`, `"in low-resource regimes"`, `"for sequences > 512 tokens"`). Omit when unrestricted.

First, capture the **headline contribution finding**: the single sentence that states what the paper establishes — the answer to the research problem. Author an `about` edge from it to the **root contribution** (the `node_registry` node with role `contribution`, or the `contribution_resource` ExperimentSetup when the deliverable is a dataset/benchmark); this is what lets the paper's problem→answer throughline be drawn. Its `role` is usually `comparative` ("A outperforms B") or `modeling` (a formal/architectural claim) — or `theorem`/`bound` when the headline result is a **proven** statement rather than a measured one. Do not restate it as several units; one headline finding, the way the abstract states it.

Then enumerate **every distinct interpretive finding** the evaluation supports — this "what it means" layer is easy to under-capture now that measurement shares the section, so treat completeness here as the job. Each of the following, when the paper states it, is its **own** Finding — do not merge two distinct findings into one, and do not drop a finding because it is secondary. The descriptions below name the *kind* of finding to look for; extract the paper's own finding in its own terms — do not import this wording:
- **ablation / sensitivity conclusions** (`role: ablation_finding`), including fine-grained sub-findings — a saturation point where adding more of some component or step stops helping, a capacity ceiling, or which of several components contributes most.
- **mechanism / interpretability** findings (`role: mechanistic`) — *why* the method works, or what a learned representation reveals: the reason behind a result, not merely that the result occurred.
- **comparative analysis** findings (`role: comparative`) — an analytical "design choice A is more effective than alternative B" conclusion drawn from the results, as distinct from a deployable score row.
- **limitations and failure modes** (`role: failure_mode`) — an input regime or setting where the method underperforms, or a regime a competing approach fails to handle that this method does.
- **proven theoretical results** (`role: theorem | lemma | bound`) — a result the paper **establishes by proof**, not by measurement: a theorem ("Algorithm X converges to the global optimum"), a lemma, or an established bound (a regret/sample-complexity/approximation/hardness bound). Use these roles (not `comparative`/`modeling`) so a proven result is epistemically distinct from an observed one. The formal statement is materialized as a Method (`method_kind: theorem`/`lemma`/`bound`) in the method section; this Finding carries what it establishes, and the theorem-Method `supports` it (see Relations). A symbolic/asymptotic value (a rate, a complexity class) goes in a Measure score row with the matching `value_kind`, not in the finding text.
- **future-work directions** that shape interpretation (`role: descriptive`).

## The one editorial call: deployable vs diagnostic

Each result row lives in exactly one place — never both. Decide, once, what the row's purpose is:

- It reports how a **deployable, first-class configuration** performs — a model the authors present as shippable (ResNet-50/101/152, Transformer Base/Big, ViT-S/B/L) → it is a `scores[]` entry on a **Measure** (measurement).
- It reports an **external comparison system / baseline** (GNMT, ConvS2S, a prior SOTA row) → it is also a `scores[]` entry on the same **Measure**, with `variant` naming the external system. The measure still `evaluates` the contribution; the baseline rows record what it was compared against.
- It **isolates one component's contribution** by removing, replacing, or disabling it ("without attention", "no skip connections", "−BN", "single-head") to argue that the component matters → it is a **diagnostic ablation**: a `Finding` (`role: ablation_finding`) plus a supporting **Measure** whose `scores[]` hold the ablation variants. Connect them with `supports` (Measure → Finding) and point the finding `about` the component method.

Operational test: would the paper offer this configuration as a usable model? If yes, it is a deployable variant (a Measure score). If it exists only to show a part is necessary, it is a diagnostic ablation (a Finding + supporting Measure).

Worked boundary example — a table that interleaves both:

| Configuration        | BLEU | becomes |
|----------------------|------|---------|
| GNMT (baseline)      | 24.6 | a `scores` entry on the BLEU Measure (`variant: "GNMT"`, `system_id: "mth:gnmt"`); GNMT is a `compared_against` Method unit |
| Transformer Base     | 27.3 | a `scores` entry on the BLEU Measure (`system_id: "mth:transformer"`) |
| Transformer Big      | 28.4 | a `scores` entry on the BLEU Measure (`system_id: "mth:transformer"`) |
| Base, no pos. enc.   | 25.1 | an ablation Finding + supporting ablation Measure (the ablated row's `system_id` is `""`) |
| Base, single-head    | 26.0 | an ablation Finding + supporting ablation Measure |

Making this call once, with the full table visible, is the whole point of the merged section: a deployable row and a diagnostic row from the same table no longer get double-extracted or dropped by two passes that cannot see each other.

## Relations

This section authors the Finding-centric edges in `relations[]`:

| relation | source → target | meaning |
|---|---|---|
| `supports` | Measure → Finding | quantitative ablation/sensitivity data supports an interpretive Finding |
| `supports` | Finding → Finding | one local finding supports another |
| `supports` | Method → Finding | a theorem/proof Method establishes a proven-result Finding (the formal analogue of measurement) |
| `about` | Finding → {Method, ExperimentSetup, Measure} | the finding is about that node (for an ablation, the **component** it isolates) |

- For the headline contribution finding: emit `Finding --about--> <root>`, pointing at the `node_registry` node whose role is `contribution` (an `mth:` id) or `contribution_resource` (an `exp:` id, for a dataset/benchmark deliverable). (Downstream this is joined with the problem the contribution motivates to draw the closing problem→answer edge — you do not author that edge.)
- For each ablation finding: emit `Measure --supports--> Finding` and `Finding --about--> mth:<component>`, pointing at the specific component node from `node_registry` (not the whole-system root) when the ablation isolates one part.
- For a proven theoretical result: emit `Method --supports--> Finding` from the theorem-Method (the `node_registry` node materialized with `method_kind: theorem`/`lemma`/`bound`) to the proven-result Finding — the formal analogue of `Measure --supports--> Finding`. The theorem-Method binds to the regime it holds under via the `assumes` edge, which the relation pass already established — do not author `assumes` here.
- Do not author `evaluates`, `part_of`, or `compares_to` — those are global structural edges already established by the relation pass. There is no `measured_on` edge to author.
- `compares_to` and other structural edges are never authored here; never put a Finding on either end of a structural edge.

### Findings about data and metrics, and multi-step chains

The `about` and `supports` endpoints above are deliberately broad — use them. A finding is **not always about the method**:

- **about a dataset / benchmark** — a conclusion about the *data itself* (a label bias, a distribution property, a benchmark that has saturated): `Finding --about--> exp:<dataset>`. Example: "ImageNet-V2 shows a 5-point accuracy drop attributable to a harder label distribution" → a `Finding` (`role: descriptive` or `mechanistic`, `polarity: negative`) pointing `about` the `exp:imagenet_v2` benchmark, not about any method.
- **about a metric** — a conclusion about a *measure's behavior* (it saturates, is gameable, disagrees with human judgment): `Finding --about--> mea:<metric>`. Example: "BLEU saturates above 40 and stops tracking adequacy" → a `Finding` pointing `about` the `mea:bleu` measure.
- **multi-step chain** — when one observation licenses a conclusion, connect them with `supports`: `Finding(observation) --supports--> Finding(conclusion)`. Example: "attention weights concentrate on head words" `supports` "the model has learned a syntactic dependency". Do not flatten a derivation ("we observe A, therefore B") into two unconnected sibling findings.

Point each finding `about` the node it is genuinely about; never reroute a data/metric finding onto the contribution method just because Method→ is the common case.

## Salience filter

- Extract best/final target-method results on primary benchmarks, and transfer/generalization results that demonstrate the main finding beyond the primary benchmark.
- Extract scale/capacity variants only when presented as first-class configurations, not as ablation controls.
- Capture the **full** "what this means" layer as Findings — every distinct ablation, mechanism, comparative, limitation, and future-work finding listed above — not a duplicate of the primary result rows. Secondary findings (interpretability remarks, edge-case behaviors, fine-grained ablation sub-results) are in scope; only skip a sentence that adds no argumentative nuance.
- Keep baseline comparison rows; skip only intermediate variants, repeated nearly identical measures, and supplementary rows that do not qualify the main finding.

## Baseline handling

- **Capture every baseline the paper compares against.** Its score is a `scores[]` row on the relevant Measure (`variant` = the system's name, `system_id` = the baseline's Method node id), and the system itself is a `compared_against` **Method** unit (materialized in the method section) that carries a `compares_to` edge from the relation pass. The comparison is captured both quantitatively (the row, joined to the system by `system_id`) and structurally (the edge).
- Do **not** model a baseline/comparison system as an **ExperimentSetup** unit — a baseline is a Method, never a dataset/benchmark/task. ExperimentSetups are testbeds and configurations only.
- The Measure still `evaluates` the contribution (its primary subject); the baseline rows in its `scores[]` record what the contribution was measured against, they do not change the measure's subject.
- If the paper's own method modifies a named base model, that base model is a Method (it should be a census node), not an evidence ExperimentSetup.

## Anti-patterns

- Do not create a `subject_id` or `evaluated_on` field on a Measure — they no longer exist; use the global `evaluates` edge (already present), the local `setup_ids`, and per-row `setup_id`.
- Do not author a `measured_on` edge — it was removed; bind a measure to its data via the score row's `setup_id`.
- Do not create Method units here; reference method nodes by id in `about` edges.
- Do not duplicate a deployable row as both a `scores` entry and an ablation Finding.
- Do not collapse a multi-dataset/multi-split column into one number per system; keep a row per (system × split) with each row's `setup_id`.
- Do not leave `system_id` blank when a Method node for the row's system exists in `node_registry` — the blank is reserved for systems the census did not capture.

## Worked example

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
        "scores": [
          {"variant": "GNMT", "value": "24.6", "variance": "", "system_id": "mth:gnmt", "setup_id": "exp:wmt2014_en_de"},
          {"variant": "GNMT", "value": "39.92", "variance": "", "system_id": "mth:gnmt", "setup_id": "exp:wmt2014_en_fr"},
          {"variant": "Transformer (big)", "value": "28.4", "variance": "", "system_id": "mth:transformer", "setup_id": "exp:wmt2014_en_de"},
          {"variant": "Transformer (big)", "value": "41.0", "variance": "", "system_id": "mth:transformer", "setup_id": "exp:wmt2014_en_fr"}
        ],
        "provenance": ["§6"]
      },
      {
        "id": "mea:pos_enc_ablation",
        "type": "Measure",
        "name": "BLEU under positional-encoding ablation",
        "unit": "BLEU",
        "setup_ids": [],
        "comparison_direction": "higher_is_better",
        "scores": [
          {"variant": "full (base)", "value": "25.8", "variance": "", "system_id": "mth:transformer", "setup_id": ""},
          {"variant": "no pos. enc.", "value": "23.6", "variance": "", "system_id": "", "setup_id": ""}
        ],
        "provenance": ["§6"]
      }
    ],
    "experiment_setups": [
      {"id": "exp:wmt2014_en_de", "type": "ExperimentSetup", "role": "benchmark", "name": "WMT 2014 English-German", "provenance": ["§6"]},
      {"id": "exp:wmt2014_en_fr", "type": "ExperimentSetup", "role": "benchmark", "name": "WMT 2014 English-French", "provenance": ["§6"]},
      {"id": "exp:beam_search", "type": "ExperimentSetup", "role": "inference_protocol", "name": "Beam search (beam=4, α=0.6)", "description": "Beam search with beam size 4 and length penalty alpha=0.6, shared across both language pairs.", "provenance": ["§6"]}
    ],
    "findings": [
      {
        "id": "fnd:pos_enc_matters",
        "type": "Finding",
        "role": "ablation_finding",
        "statement": "Removing positional encodings lowers BLEU by 2.2, showing they are necessary for the attention-only model.",
        "provenance": ["§6"]
      }
    ],
    "relations": [
      {"source_id": "mea:pos_enc_ablation", "relation": "supports", "target_id": "fnd:pos_enc_matters", "provenance": ["§6"]},
      {"source_id": "fnd:pos_enc_matters", "relation": "about", "target_id": "mth:positional_encoding", "provenance": ["§6"]}
    ]
  }
}

The single `mea:bleu` measure holds both language-pair columns: each row carries its own `setup_id` pointing at the benchmark substrate node it ran on, so the EN-FR headline `41.0` is preserved instead of being dropped when the column collapses — and that `setup_id` is what now binds the measure to its data, replacing the old `measured_on` edge. The shared decoding protocol is a born `inference_protocol` ExperimentSetup in `setup_ids`. Baseline rows (`GNMT`) and contribution rows (`Transformer (big)`) are distinguished by `system_id`, not by parsing the `variant` string; the ablated `"no pos. enc."` row has `system_id: ""` because no Method node represents that disabled configuration. The edges `mea:bleu --evaluates--> mth:transformer` and `mth:transformer --compares_to--> mth:gnmt` are **not** emitted here — they already live in the global `relations` from the relation pass (and `evaluates` points only at the contribution, never at `mth:gnmt`).

## Anchor

`anchor_id` should be the primary headline Measure (`mea:`) — the result that most directly validates the main finding. Do not anchor on an ExperimentSetup or Finding.
