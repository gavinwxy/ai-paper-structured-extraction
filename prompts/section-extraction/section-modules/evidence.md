SECTION FOCUS: evidence

This section captures the paper's evaluation layer in one pass: both **what was measured** (how the method performs on benchmarks and transfer tests) and **what those measurements mean** (what ablations reveal, what limits the result). The old experiment/analysis split is gone — measurement and interpretation are decided together here, with the whole results table in view, which is exactly the editorial call that the split forced two blind parallel passes to make separately.

This section **materializes** the Metric and Entity census nodes (enriching them with the rich fields below) and **creates** the born Condition and Claim units. The `evaluates` (Metric → Method) and `measured_on` (Metric → dataset Entity) edges are already in the global `relations` from the relation pass — do not restate them. You author only the claim-centric edges (`about`, `supports`).

## Units you may define

- `Metric` (array `metrics`): headline target-method results and diagnostic ablation/sensitivity values. Materialize each Metric census node; you may add one the census missed.
- `Condition` (array `conditions`): evaluation protocol, dataset split, benchmark setup, population, or hyperparameter that scopes a metric. **Born here.**
- `Claim` (array `claims`): interpretive findings — ablation conclusions, sensitivity conclusions, limitations, failure modes. **Born here.**
- `Entity` (array `entities`): the datasets, benchmarks, and tasks the method is evaluated on (`dataset | benchmark | task`). Materialize **every** Entity census node in `node_registry`, including `task` nodes — not only the ones a metric was measured on.

### Metric
Fields: `name`, `unit`, `context_ids`, optional `comparison_direction`, and `scores`.
- `unit`: non-empty measurement unit such as `BLEU`, `%`, `ms`, `F1`, `perplexity`, or `unitless`. Never blank.
- `comparison_direction` (optional): `higher_is_better | lower_is_better | target | unspecified`.
- `context_ids`: IDs of **local** Condition units that scope this metric, defined in this same response. A deployable benchmark metric is normally scoped by at least one Condition; a diagnostic ablation metric may carry none (`[]`). There is no `subject_id` or `evaluated_on` field — the method a metric evaluates and the dataset it ran on are global edges (`evaluates`, `measured_on`), already established.
- `scores`: a flat array of `{variant, value, variance}` — one entry per **system reported under this metric**, covering both the method family's own variants **and every baseline / prior-SOTA system the paper compares against**. `variant` names the system as the paper labels it (`"Transformer (big)"`, `"GNMT"`, `"ConvS2S"`). `value` is always a string ("28.4", "28.4-29.1", or a short categorical string); `variance` is "" when no uncertainty is reported. One entry per system — do not pack multiple scores into one entry. Capturing the baseline rows here is how the quantitative comparison is preserved; the matching baseline systems are `compared_against` Method units and carry `compares_to` edges from the relation pass.

### Condition — operational constraint
Fields: `description`.
- `description`: a single sentence that **names the concrete setup** that scopes a metric — the actual dataset/split, population size, OOD source-vs-target pair, protocol, or hyperparameter, carrying the paper's real names and numbers rather than a paraphrase. Never replace a specific setup with a vague generic restatement (e.g. "evaluated to assess whether the model is more confident") — that loses the recall the Condition exists to carry.
- **Enumerate each distinct evaluation setup as its own Condition.** A separate dataset, a cross-dataset generalization or transfer protocol, a robustness / distribution-shift setup, a user study, and a timing protocol each get their **own** Condition — even when no separate Metric attaches to it. Do not collapse several named setups into one.

### Claim — interpretive finding
Fields: `statement`, `claim_kind`.
Enumerate **every distinct interpretive finding** the evaluation supports — this "what it means" layer is easy to under-capture now that measurement shares the section, so treat completeness here as the job. Each of the following, when the paper states it, is its **own** Claim — do not merge two distinct findings into one, and do not drop a finding because it is secondary. The descriptions below name the *kind* of finding to look for; extract the paper's own finding in its own terms — do not import this wording:
- **ablation / sensitivity conclusions** (`claim_kind: ablation_finding`), including fine-grained sub-findings — a saturation point where adding more of some component or step stops helping, a capacity ceiling, or which of several components contributes most.
- **mechanism / interpretability** findings (`claim_kind: mechanistic`) — *why* the method works, or what a learned representation reveals: the reason behind a result, not merely that the result occurred.
- **comparative analysis** findings (`claim_kind: comparative`) — an analytical "design choice A is more effective than alternative B" conclusion drawn from the results, as distinct from a deployable score row.
- **limitations and failure modes** (`claim_kind: failure_mode`) — an input regime or setting where the method underperforms, or a regime a competing approach fails to handle that this method does.
- **future-work directions** that shape interpretation (`claim_kind: descriptive`).

### Entity
Fields: `name`, `entity_class` (`dataset | benchmark | task`). **Materialize every Entity census node from `node_registry`**, reusing each `node_id`. A `dataset`/`benchmark` anchors the global `measured_on` edges; a `task` anchors `about` edges and frames what was evaluated — materialize it too, even though no `measured_on` points at a task. Leaving any Entity census node unmaterialized strands its edges and leaves a `must` node uncovered.

## The one editorial call: deployable vs diagnostic

Each result row lives in exactly one place — never both. Decide, once, what the row's purpose is:

- It reports how a **deployable, first-class configuration** performs — a model the authors present as shippable (ResNet-50/101/152, Transformer Base/Big, ViT-S/B/L) → it is a `scores[]` entry on a **Metric** (measurement).
- It reports an **external comparison system / baseline** (GNMT, ConvS2S, a prior SOTA row) → it is also a `scores[]` entry on the same **Metric**, with `variant` naming the external system. The metric still `evaluates` the contribution; the baseline rows record what it was compared against.
- It **isolates one component's contribution** by removing, replacing, or disabling it ("without attention", "no skip connections", "−BN", "single-head") to argue that the component matters → it is a **diagnostic ablation**: a `Claim` (`claim_kind: ablation_finding`) plus a supporting **Metric** whose `scores[]` hold the ablation variants. Connect them with `supports` (Metric → Claim) and point the claim `about` the component method.

Operational test: would the paper offer this configuration as a usable model? If yes, it is a deployable variant (a Metric score). If it exists only to show a part is necessary, it is a diagnostic ablation (a Claim + supporting Metric).

Worked boundary example — a table that interleaves both:

| Configuration        | BLEU | becomes |
|----------------------|------|---------|
| GNMT (baseline)      | 24.6 | a `scores` entry on the BLEU Metric (`variant: "GNMT"`); GNMT is a `compared_against` Method unit |
| Transformer Base     | 27.3 | a `scores` entry on the BLEU Metric |
| Transformer Big      | 28.4 | a `scores` entry on the BLEU Metric |
| Base, no pos. enc.   | 25.1 | an ablation Claim + supporting ablation Metric |
| Base, single-head    | 26.0 | an ablation Claim + supporting ablation Metric |

Making this call once, with the full table visible, is the whole point of the merged section: a deployable row and a diagnostic row from the same table no longer get double-extracted or dropped by two passes that cannot see each other.

## Relations

This section authors the claim-centric edges in `relations[]`:

| relation | source → target | meaning |
|---|---|---|
| `supports` | Metric → Claim | quantitative ablation/sensitivity data supports an interpretive Claim |
| `supports` | Claim → Claim | one local finding supports another |
| `about` | Claim → {Method, Entity, Metric} | the finding is about that node (for an ablation, the **component** it isolates) |

- For each ablation finding: emit `Metric --supports--> Claim` and `Claim --about--> mth:<component>`, pointing at the specific component node from `node_registry` (not the whole-system root) when the ablation isolates one part.
- Do not author `evaluates`, `measured_on`, `part_of`, or `compares_to` — those are global structural edges already established by the relation pass.
- `compares_to` and other structural edges are never authored here; never put a Claim on either end of a structural edge.

## Salience filter

- Extract best/final target-method results on primary benchmarks, and transfer/generalization results that demonstrate the main claim beyond the primary benchmark.
- Extract scale/capacity variants only when presented as first-class configurations, not as ablation controls.
- Capture the **full** "what this means" layer as Claims — every distinct ablation, mechanism, comparative, limitation, and future-work finding listed above — not a duplicate of the primary result rows. Secondary findings (interpretability remarks, edge-case behaviors, fine-grained ablation sub-results) are in scope; only skip a sentence that adds no argumentative nuance.
- Keep baseline comparison rows; skip only intermediate variants, repeated nearly identical metrics, and supplementary rows that do not qualify the main claim.

## Baseline handling

- **Capture every baseline the paper compares against.** Its score is a `scores[]` row on the relevant Metric (`variant` = the system's name), and the system itself is a `compared_against` **Method** unit (materialized in the method section) that carries a `compares_to` edge from the relation pass. The comparison is captured both quantitatively (the row) and structurally (the edge).
- Do **not** model a baseline/comparison system as an **Entity** unit — a baseline is a Method, never a dataset/benchmark/task. Entities are testbeds only.
- The Metric still `evaluates` the contribution (its primary subject); the baseline rows in its `scores[]` record what the contribution was measured against, they do not change the metric's subject.
- If the paper's own method modifies a named base model, that base model is a Method (it should be a census node), not an evidence Entity.

## Anti-patterns

- Do not create a `subject_id` or `evaluated_on` field on a Metric — they no longer exist; use the global `evaluates`/`measured_on` edges (already present) and local `context_ids`.
- Do not create Method units here; reference method nodes by id in `about` edges.
- Do not duplicate a deployable row as both a `scores` entry and an ablation Claim.

## Worked example

{
  "section": {
    "section_type": "evidence",
    "anchor_id": "met:bleu_en_de",
    "metrics": [
      {
        "id": "met:bleu_en_de",
        "type": "Metric",
        "name": "BLEU (EN-DE)",
        "unit": "BLEU",
        "context_ids": ["cnd:wmt_newstest2014"],
        "comparison_direction": "higher_is_better",
        "scores": [
          {"variant": "GNMT", "value": "24.6", "variance": ""},
          {"variant": "ConvS2S", "value": "25.16", "variance": ""},
          {"variant": "Transformer Base", "value": "27.3", "variance": ""},
          {"variant": "Transformer Big", "value": "28.4", "variance": ""}
        ],
        "provenance": [{"source_kind": "table", "source": ["§6"]}]
      },
      {
        "id": "met:pos_enc_ablation",
        "type": "Metric",
        "name": "BLEU under positional-encoding ablation",
        "unit": "BLEU",
        "context_ids": [],
        "comparison_direction": "higher_is_better",
        "scores": [
          {"variant": "full", "value": "27.3", "variance": ""},
          {"variant": "no pos. enc.", "value": "25.1", "variance": ""}
        ],
        "provenance": [{"source_kind": "table", "source": ["§6"]}]
      }
    ],
    "conditions": [
      {
        "id": "cnd:wmt_newstest2014",
        "type": "Condition",
        "description": "Evaluated on the WMT 2014 English-German newstest2014 test set with beam search.",
        "provenance": [{"source_kind": "sentence", "source": ["§6"]}]
      }
    ],
    "claims": [
      {
        "id": "clm:pos_enc_matters",
        "type": "Claim",
        "statement": "Removing positional encodings lowers BLEU by 2.2, showing they are necessary for the attention-only model.",
        "claim_kind": "ablation_finding",
        "provenance": [{"source_kind": "table", "source": ["§6"]}]
      }
    ],
    "entities": [
      {
        "id": "ent:wmt2014_en_de",
        "type": "Entity",
        "name": "WMT 2014 English-German",
        "entity_class": "benchmark",
        "provenance": [{"source_kind": "sentence", "source": ["§6"]}]
      }
    ],
    "relations": [
      {"source_id": "met:pos_enc_ablation", "relation": "supports", "target_id": "clm:pos_enc_matters", "provenance": [{"source_kind": "table", "source": ["§6"]}]},
      {"source_id": "clm:pos_enc_matters", "relation": "about", "target_id": "mth:positional_encoding", "provenance": [{"source_kind": "sentence", "source": ["§6"]}]}
    ]
  }
}

Here `met:bleu_en_de --evaluates--> mth:transformer` and `met:bleu_en_de --measured_on--> ent:wmt2014_en_de` are **not** emitted in this section; they already live in the global `relations` from the relation pass. The `GNMT` and `ConvS2S` score rows name `compared_against` Method units defined in the method section; their `mth:transformer --compares_to--> mth:gnmt` edges likewise come from the relation pass, not from here.

## Anchor

`anchor_id` should be the primary headline Metric (`met:`) — the result that most directly validates the main claim. Do not anchor on a Condition, Entity, or Claim.
