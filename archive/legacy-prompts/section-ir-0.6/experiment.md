SECTION FOCUS: experiment

This section captures the factual evaluation layer: how the paper's target method performs on primary benchmarks or transfer/generalization tests. It stays compact and target-method centered.

## Units you may define

- `Metric` (array `metrics`, primary, 2–4 per segment): headline target-method results.
- `Condition` (array `conditions`, required, 1–4): evaluation protocol, dataset split, benchmark setup, population, or hardware/config that scopes a metric.
- `Entity` (array `entities`, supporting, 0–4): datasets and benchmarks only.

### Metric
Fields: `name`, `unit`, `subject_id`, `context_ids`, optional `evaluated_on`, `comparison_direction`, `value_type`, and `scores`.
- `unit`: non-empty measurement unit such as `BLEU`, `%`, `ms`, `F1`, `perplexity`, or `unitless`. Never blank.
- `comparison_direction` (optional): `higher_is_better | lower_is_better | target | unspecified`.
- `value_type` (optional): `scalar | range | ratio | categorical`.
- `subject_id`: the Method this metric measures; reference the relevant Method ID from `id_registry`. Plan relation `evaluates` means exactly this — when the `section_plan` declares an `evaluates` target for this metric, set `subject_id` to that method's `id_registry` ID. Fall back to the entry whose role is `root` only when no `evaluates` relation applies; do not default to `root` when a specific `evaluates` target is given.
- `context_ids`: a non-empty array of **local** Condition IDs defined in this same response. If the metric needs setup context planned elsewhere, restate it as a local Condition with a segment-specific `cnd:` ID.
- `evaluated_on` (optional): IDs of the **local** dataset/benchmark Entity units this metric was measured on (e.g. `["ent:imagenet"]`). This is the structured dataset link: define the dataset as a local Entity and reference its ID here, rather than only naming it inside a Condition `description`. Omit the field entirely when no local dataset/benchmark Entity applies — never invent one.
- `scores`: a flat array of `{variant, value, variance}`, one entry per deployable variant of the method family (e.g. ResNet-50/101/152, ViT-S/B/L). `value` is always a string ("28.4", "28.4-29.1", or a short categorical string); `variance` is "" when the paper reports no uncertainty. One entry per variant — do not pack multiple scores into one entry, and do not include external baselines or prior SOTA.

### Condition — operational constraint
Fields: `condition_kind`, `description`.
- `condition_kind`: `evaluation_setup` for benchmark splits; `experimental` for lab/trial populations; `boundary` for applicability limits; `hyperparameter` for a setup parameter that scopes a reported metric.
- `description`: a single sentence stating the constraint.

### Entity
Fields: `name`, `entity_class`. In this section `entity_class` must be `dataset` or `benchmark`. Define here the datasets/benchmarks a metric is measured on, and connect them with the metric's `evaluated_on` so the Entity is not left orphaned.

## Links

| relation | source | target |
|---|---|---|
| `compares_to` | Entity, Metric | Entity, Metric |

- `compares_to` is the only link relation available in this section; usually no local links are needed at all, since measurement is carried by Metric fields rather than links.
- Use `compares_to` only for explicit comparisons between local dataset/benchmark Entities or between local Metrics.
- Do not emit `supports` in experiment; interpretation belongs in analysis.

Never invent a link to express measurement scope — there is no relation for "this metric ran under this setup / on this dataset". Encode those on the Metric instead:
- ✗ A link from a Metric to its Condition — put the Condition ID in the Metric's `context_ids`.
- ✗ A link from a Metric (or a Condition) to a dataset Entity — put the Entity ID in the Metric's `evaluated_on`, or name the dataset in the Condition `description`.
- ✗ A link between a Condition and an Entity — state "this setup uses this dataset" inside the Condition `description`.

## Extraction focus

- Every Metric must measure the target method or a transfer/generalization result of the target method, with exactly one `subject_id`, non-empty `context_ids`, and provenance.
- List all deployable variant scores in `scores[]` with one `{variant, value, variance}` entry per variant. When the paper reports uncertainty, put the point estimate in `value` and the uncertainty in `variance`.
- Create separate Metrics when the target method is evaluated under meaningfully different contexts.
- If the `section_plan` contains only `cnd:` and/or `ent:` items and no `met:` items, extract only Conditions and/or Entities; do not invent Metrics.
- For tables, extract only the argumentatively salient target-method rows/columns. Use `source_kind: table`.

## Experiment vs analysis boundary (decide per table row)

This is the single most important editorial call here, and the analysis section is judged against the mirror-image rule. Each result row lives in exactly one section — never both. Ask what the row's purpose is:
- It reports how a deployable, first-class configuration performs — a model the authors present as shippable (ResNet-50/101/152, Transformer Base/Big, ViT-S/B/L) → experiment, as a `scores[]` entry on a Metric.
- It isolates one component's contribution by removing, replacing, or disabling it ("without attention", "no skip connections", "−BN", "single-head") to argue that component matters → analysis, as a Claim + supporting Metric. It is not a `scores[]` entry here.

Operational test for a `scores[]` variant: would the paper offer this configuration as a usable model? If yes, it is a deployable variant (experiment). If it exists only to show a part is necessary, it is a diagnostic ablation (analysis).

Worked boundary example — a table that interleaves both:

| Configuration        | BLEU | goes to    |
|----------------------|------|------------|
| Transformer Base     | 27.3 | experiment (scores entry) |
| Transformer Big      | 28.4 | experiment (scores entry) |
| Base, no pos. enc.   | 25.1 | analysis (ablation Claim + Metric) |
| Base, single-head    | 26.0 | analysis (ablation Claim + Metric) |

Here the experiment Metric carries `scores: [{"variant": "Transformer Base", "value": "27.3"}, {"variant": "Transformer Big", "value": "28.4"}]`; the two ablation rows are left for analysis. Do not also emit the ablation rows here.

## Salience filter

- Extract best/final target-method results on primary benchmarks.
- Extract transfer/generalization results that demonstrate the main claim beyond the primary benchmark.
- Extract scale/capacity variant results only when the paper presents them as first-class configurations, not as ablation controls.
- Skip baseline-only scores, intermediate variants, repeated nearly identical metrics, and supplementary rows that do not qualify the main claim.

## Baseline handling

- Do not model baseline or comparison systems as Entity units, and do not create baseline Metrics.
- Do not put baseline scores in `scores[]`; baseline scores are not extracted anywhere in the IR.
- Baselines may be mentioned textually in analysis Claim statements when they matter to the paper's interpretation.
- If the paper's own method modifies a named base model, that base model belongs in the method section as a Method unit, not as an experiment Entity.
- In multi-segment experiments, avoid redefining common datasets with the same generic ID across segments. If a dataset is only needed to scope a metric, mention it in the Condition description; if a local Entity is necessary, make the ID segment-specific.

## Anti-patterns

- Do not create Entity units for models, tasks, hardware, or baseline systems.
- Do not model baselines anywhere.
- Do not create a Metric without `context_ids`; validation rejects experiment Metrics with empty context.
- Do not move ablation, sensitivity, robustness, or failure-mode interpretation into experiment. Those belong in analysis as Claim + Metric pairs.

## Worked example

{
  "section": {
    "section_type": "experiment",
    "anchor_id": "met:imagenet_top1",
    "covers_entries": ["met:imagenet_top1", "cnd:imagenet_eval"],
    "entities": [
      {
        "id": "ent:imagenet",
        "type": "Entity",
        "name": "ImageNet-1K",
        "entity_class": "dataset",
        "provenance": [{"source_kind": "sentence", "source": ["§12"]}]
      }
    ],
    "conditions": [
      {
        "id": "cnd:imagenet_eval",
        "type": "Condition",
        "condition_kind": "evaluation_setup",
        "description": "Evaluated on the ImageNet validation split with the paper's standard test-time protocol.",
        "provenance": [{"source_kind": "sentence", "source": ["§12"]}]
      }
    ],
    "metrics": [
      {
        "id": "met:imagenet_top1",
        "type": "Metric",
        "name": "Top-1 Accuracy",
        "unit": "%",
        "subject_id": "mth:proposed_model",
        "context_ids": ["cnd:imagenet_eval"],
        "evaluated_on": ["ent:imagenet"],
        "comparison_direction": "higher_is_better",
        "value_type": "scalar",
        "scores": [
          {"variant": "ViT-Large", "value": "85.4", "variance": "± 0.2"},
          {"variant": "ViT-Base", "value": "83.3", "variance": ""}
        ],
        "provenance": [{"source_kind": "table", "source": ["§14"]}]
      }
    ],
    "links": []
  }
}

## Anchor

`anchor_id` should be the primary headline Metric (`met:`), the result that most directly validates the main claim. Do not anchor on a Condition or Entity.
- ✗ Do not anchor on the root/target method (`mth:...`), even though it is the gravity center of the whole extraction. Methods are not defined in the experiment section, so an `mth:` id is never section-local here and will fail the anchor contract. The method belongs in each Metric's `subject_id`; the anchor must be a local headline `met:`.
