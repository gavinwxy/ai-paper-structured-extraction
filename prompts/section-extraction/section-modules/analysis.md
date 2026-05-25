SECTION FOCUS: analysis

This section captures the interpretive layer: why the method works, what ablations reveal, what limits the result, and where the paper's own discussion qualifies the central claim.

This section is planless: `section_plan.items` is empty. Extract the analysis role from `spine_summary`, this focus, and the paper. Set `covers_entries: []`, choose `anchor_id` from a unit you define here, and do not invent plan item IDs.

## Units you may define

- `Claim` (array `claims`, primary, 1–4): ablation findings, sensitivity conclusions, limitations, failure modes, or future-work conclusions.
- `Metric` (array `metrics`, supporting, 0–4): ablation/sensitivity values that support a local Claim.
- `Entity` (array `entities`, optional, 0–3): named components or factors being analyzed, only when not already represented by Method IDs in `id_registry`.

### Claim
Fields: `statement`, `claim_kind`, `target_ids`, and optional `polarity`, `novelty`, `epistemic_status`.
- `claim_kind`: one of `descriptive | mechanistic | causal | correlational | comparative | modeling | ablation_finding | failure_mode`. Use `ablation_finding` for ablation conclusions and `failure_mode` for limitations.
- `epistemic_status` (optional): use `conclusion` for ablation/limitation findings — never `established_fact`.
- `novelty` / `polarity` (optional): `original | replication | citation | synthesis` and `positive | negative | neutral | mixed`.
- `target_ids`: reference relevant Method IDs from `id_registry`. Do not invent target IDs; if a specific component is absent, target the nearest broader existing Method ID or leave `target_ids: []`.

### Metric
Fields: `name`, `unit`, `subject_id`, `context_ids`, optional `evaluated_on`, `comparison_direction`, `value_type`, and `scores`.
- `unit`: non-empty measurement unit (`%`, `BLEU`, `F1`, `ms`, `perplexity`, `unitless`). Never blank.
- `subject_id`: the Method the ablation/sensitivity result is about; reference a Method ID from `id_registry`. When the result isolates one specific component (the usual ablation case), set `subject_id` to that **component's** Method ID — the same component its Claim targets — not the overall system/root method. Reserve the root/system method for a genuinely whole-system result. When a Metric supports an ablation Claim, its `subject_id` must name the component that Claim's `target_ids` point to.
- `context_ids`: must be `[]` — this section has no local Conditions.
- `evaluated_on` (optional, rare here): IDs of local dataset/benchmark Entity units the result was measured on. Most analysis metrics omit it; include it only when you define such an Entity locally in this section.
- `scores`: a flat array of `{variant, value, variance}` holding the paper's own ablation/sensitivity variants as peer entries (e.g. `{"variant": "full"}`, `{"variant": "no pos. enc."}`). Never external baselines — express baseline comparisons textually in the Claim `statement`.

### Entity
Fields: `name`, `entity_class` (one of `dataset | benchmark | model | task | hardware`).

## Links

| relation | source | target |
|---|---|---|
| `supports` | Metric, Claim | Claim |
| `compares_to` | Entity, Metric | Entity, Metric |

- Use `Metric --supports--> Claim` when quantitative ablation or sensitivity data supports a local interpretive Claim.
- Use `Claim --supports--> Claim` only when one local analysis conclusion explicitly supports another.
- Use `compares_to` between Metrics only when the analysis explicitly contrasts separate Metric units and the contrast is not already captured in `Metric.scores[]`.

Link counter-example (the easy mistake here):
- ✗ `clm:finding_a --compares_to--> clm:finding_b` — `compares_to` never accepts a Claim on either end. When one finding contrasts with another, state the contrast inside a single Claim `statement`, or connect evidence to a conclusion with `supports`.

## Experiment vs analysis boundary (mirror image of the experiment rule)

The experiment section takes deployable, first-class configurations; this section takes diagnostic results. Each result row lives in exactly one section — never both. A row belongs here when it isolates one component's contribution by removing, replacing, or disabling it ("without attention", "no skip connections", "−BN", "single-head") to argue that the component matters. Capture it as a Claim plus a supporting Metric whose `scores[]` hold the ablation variants.
- Operational test: if a configuration exists only to demonstrate that a part is necessary, it is yours. If the paper presents it as a usable model the reader could deploy, it belongs in experiment — do not restate it here.
- Worked example (the same interleaved table the experiment section sees): "Transformer Base / Big" rows are deployable → experiment. "Base, no pos. enc." and "Base, single-head" rows are ablations → here, as `ablation_finding` Claims with a supporting Metric whose `scores: [{"variant": "full", ...}, {"variant": "no pos. enc.", ...}]`.

## Extraction focus

- Ablation conclusions become Claim + Metric pairs when the paper reports quantitative data.
- Express ablation settings inline in Claim statements; list all variant scores in `scores[]` as peer entries.
- Limitations are Claim units with `claim_kind: failure_mode` and `epistemic_status: conclusion`.
- Future work may be a Claim with `claim_kind: descriptive` when it identifies an unresolved direction that shapes interpretation.
- Capture the "what this means" layer, not a duplicate of primary experiment results.

## Anti-patterns

- Do not restate all experiment-section results here.
- Do not create a Claim for every discussion sentence; extract only claims that change or nuance the argumentative status.
- Do not set `epistemic_status: established_fact` on ablation conclusions; use `conclusion`.
- Do not create Method units for ablation variants; express them inline or reference existing Method IDs.
- Do not give analysis Metrics non-empty `context_ids`.

## Worked example

{
  "section": {
    "section_type": "analysis",
    "anchor_id": "clm:ablation_component_matters",
    "covers_entries": [],
    "claims": [
      {
        "id": "clm:ablation_component_matters",
        "type": "Claim",
        "statement": "Removing the routing component materially reduces accuracy, showing that the component is responsible for most of the gain.",
        "claim_kind": "ablation_finding",
        "target_ids": ["mth:routing_component"],
        "polarity": "positive",
        "novelty": "original",
        "epistemic_status": "conclusion",
        "provenance": [{"source_kind": "sentence", "source": ["§18"]}]
      }
    ],
    "metrics": [
      {
        "id": "met:routing_ablation",
        "type": "Metric",
        "name": "Accuracy under routing ablation",
        "unit": "%",
        "subject_id": "mth:routing_component",
        "context_ids": [],
        "comparison_direction": "higher_is_better",
        "value_type": "scalar",
        "scores": [
          {"variant": "with routing", "value": "85.4", "variance": ""},
          {"variant": "without routing", "value": "81.9", "variance": ""}
        ],
        "provenance": [{"source_kind": "table", "source": ["§18"]}]
      }
    ],
    "entities": [],
    "links": [
      {"source_id": "met:routing_ablation", "relation": "supports", "target_id": "clm:ablation_component_matters"}
    ]
  }
}

## Anchor

`anchor_id` should be the most consequential local Claim — usually the strongest ablation finding or limitation that changes how the reader should understand the central contribution.
