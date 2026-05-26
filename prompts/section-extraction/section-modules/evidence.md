SECTION FOCUS: evidence

This section captures the paper's evaluation layer in one pass: both **what was measured** (how the method performs on benchmarks and transfer tests) and **what those measurements mean** (what ablations reveal, what limits the result). The old experiment/analysis split is gone — measurement and interpretation are decided together here, with the whole results table in view, which is exactly the editorial call that the split forced two blind parallel passes to make separately.

This section **materializes** the Metric and Entity census nodes (enriching them with the rich fields below) and **creates** the born Condition and Claim units. The `evaluates` (Metric → Method) and `measured_on` (Metric → dataset Entity) edges are already in the global `relations` from the relation pass — do not restate them. You author only the claim-centric edges (`about`, `supports`).

## Units you may define

- `Metric` (array `metrics`): headline target-method results and diagnostic ablation/sensitivity values. Materialize each Metric census node; you may add one the census missed.
- `Condition` (array `conditions`): evaluation protocol, dataset split, benchmark setup, population, or hyperparameter that scopes a metric. **Born here.**
- `Claim` (array `claims`): interpretive findings — ablation conclusions, sensitivity conclusions, limitations, failure modes. **Born here.**
- `Entity` (array `entities`): datasets, benchmarks, and other named factors (`dataset | benchmark | model | task | hardware`). Materialize Entity census nodes used in evaluation.

### Metric
Fields: `name`, `unit`, `context_ids`, optional `comparison_direction`, `value_type`, and `scores`.
- `unit`: non-empty measurement unit such as `BLEU`, `%`, `ms`, `F1`, `perplexity`, or `unitless`. Never blank.
- `comparison_direction` (optional): `higher_is_better | lower_is_better | target | unspecified`.
- `value_type` (optional): `scalar | range | ratio | categorical`.
- `context_ids`: IDs of **local** Condition units that scope this metric, defined in this same response. A deployable benchmark metric is normally scoped by at least one Condition; a diagnostic ablation metric may carry none (`[]`). There is no `subject_id` or `evaluated_on` field — the method a metric evaluates and the dataset it ran on are global edges (`evaluates`, `measured_on`), already established.
- `scores`: a flat array of `{variant, value, variance}`, one entry per variant of the method family under this metric. `value` is always a string ("28.4", "28.4-29.1", or a short categorical string); `variance` is "" when no uncertainty is reported. One entry per variant — do not pack multiple scores into one entry, and do not include external baselines or prior SOTA.

### Condition — operational constraint
Fields: `condition_kind`, `description`.
- `condition_kind`: `evaluation_setup` for benchmark splits; `experimental` for lab/trial populations; `boundary` for applicability limits; `hyperparameter` for a setup parameter that scopes a reported metric.
- `description`: a single sentence that **names the concrete setup** — the actual dataset/split, population size, OOD pair, or protocol ("OOD detection using TCGA-PRAD prostate images against CAMELYON16", "user study with 35 participants and 700 responses", "total inference time measured including landmark detection and warping"). Never replace a specific setup with a vague generic restatement such as "evaluated to assess whether the model is more confident" — that loses the recall the Condition exists to carry.
- **Enumerate each distinct evaluation setup as its own Condition.** A separate dataset, a cross-dataset generalization or transfer protocol, a robustness / distribution-shift setup, a user study, and a timing protocol each get their **own** Condition — even when no separate Metric attaches to it. Do not collapse several named setups into one.

### Claim — interpretive finding
Fields: `statement`, `claim_kind`, optional `polarity`, `novelty`, `epistemic_status`.
Enumerate **every distinct interpretive finding** the evaluation supports — this "what it means" layer is easy to under-capture now that measurement shares the section, so treat completeness here as the job. Each of the following, when the paper states it, is its **own** Claim — do not merge two distinct findings into one, and do not drop a finding because it is secondary:
- **ablation / sensitivity conclusions** (`claim_kind: ablation_finding`), including fine-grained sub-findings — a saturation point ("gains stop after 3 iterations"), a capacity ceiling ("more than two blocks no longer helps"), or which of several components contributes most.
- **mechanism / interpretability** findings (`claim_kind: mechanistic`) — why the method works, or what a learned representation reveals ("the inverted attention yields interpretable variate correlations").
- **comparative analysis** findings (`claim_kind: comparative`) — an analytical "A is more effective than B" conclusion drawn from the results, as opposed to a deployable score row.
- **limitations and failure modes** (`claim_kind: failure_mode`) — including a specific competitor-failure or edge-case observation ("the baseline detector fails when aspect ratios vary").
- **future-work directions** that shape interpretation (`claim_kind: descriptive`).
- `epistemic_status` (optional): use `conclusion` for ablation/limitation findings — never `established_fact`.

### Entity
Fields: `name`, `entity_class` (`dataset | benchmark | model | task | hardware`). Materialize the dataset/benchmark Entity nodes the metrics were measured on so the global `measured_on` edges resolve.

## The one editorial call: deployable vs diagnostic

Each result row lives in exactly one place — never both. Decide, once, what the row's purpose is:

- It reports how a **deployable, first-class configuration** performs — a model the authors present as shippable (ResNet-50/101/152, Transformer Base/Big, ViT-S/B/L) → it is a `scores[]` entry on a **Metric** (measurement).
- It **isolates one component's contribution** by removing, replacing, or disabling it ("without attention", "no skip connections", "−BN", "single-head") to argue that the component matters → it is a **diagnostic ablation**: a `Claim` (`claim_kind: ablation_finding`) plus a supporting **Metric** whose `scores[]` hold the ablation variants. Connect them with `supports` (Metric → Claim) and point the claim `about` the component method.

Operational test: would the paper offer this configuration as a usable model? If yes, it is a deployable variant (a Metric score). If it exists only to show a part is necessary, it is a diagnostic ablation (a Claim + supporting Metric).

Worked boundary example — a table that interleaves both:

| Configuration        | BLEU | becomes |
|----------------------|------|---------|
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
- Skip baseline-only scores, intermediate variants, repeated nearly identical metrics, and supplementary rows that do not qualify the main claim.

## Baseline handling

- Do not model baseline/comparison systems as Entity units, and do not create baseline Metrics or put baseline scores in `scores[]`. Baselines may be mentioned textually in a Claim `statement` when they matter to the interpretation.
- If the paper's own method modifies a named base model, that base model is a Method (it should be a census node), not an evidence Entity.

## Anti-patterns

- Do not create a `subject_id` or `evaluated_on` field on a Metric — they no longer exist; use the global `evaluates`/`measured_on` edges (already present) and local `context_ids`.
- Do not create Method units here; reference method nodes by id in `about` edges.
- Do not set `epistemic_status: established_fact` on ablation conclusions; use `conclusion`.
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
        "value_type": "scalar",
        "scores": [
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
        "value_type": "scalar",
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
        "condition_kind": "evaluation_setup",
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
        "polarity": "positive",
        "novelty": "original",
        "epistemic_status": "conclusion",
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

Here `met:bleu_en_de --evaluates--> mth:transformer` and `met:bleu_en_de --measured_on--> ent:wmt2014_en_de` are **not** emitted in this section; they already live in the global `relations` from the relation pass.

## Anchor

`anchor_id` should be the primary headline Metric (`met:`) — the result that most directly validates the main claim. Do not anchor on a Condition, Entity, or Claim.
