SECTION FOCUS: claim

This section captures the paper's central thesis and its direct logical corollaries. It is the argumentative hub: every other section either supports, operationalizes, qualifies, or evaluates claims defined here.

This section is planless: `section_plan.items` is empty. Extract the claim role from `spine_summary`, this focus, and the paper. Set `covers_entries: []`, choose `anchor_id` from a Claim you define here, and do not invent plan item IDs.

## Units you may define

Only `Claim` units (array `claims`). Typical: 1–3 units — the main contribution claim plus at most two direct corollaries.

### Claim
Fields: `statement`, `claim_kind`, `target_ids`, and optional `polarity`, `novelty`, `epistemic_status`.
- `claim_kind`: one of `descriptive | mechanistic | causal | correlational | comparative | modeling | ablation_finding | failure_mode`. Be precise: `comparative` for "A outperforms B", `causal` for "X causes Y", `descriptive` for "X is characterized by Y", `mechanistic` for "X works because Y".
- `epistemic_status` (optional): `conclusion` for claims presented as demonstrated, `hypothesis` for conjectural claims, `established_fact` only for universally accepted prior knowledge.
- `novelty` (optional): `original` for new contributions, `citation` for prior-work claims, `replication` for reproduced results, `synthesis` for combined findings.
- `polarity` (optional): `positive | negative | neutral | mixed`.
- `target_ids`: reference Method IDs from `id_registry` (the method section) when the claim is about a specific method. Use only IDs defined here or in `id_registry`; never invent one. If the exact method is absent, use the nearest broader Method ID, else `[]`. For the paper-level contribution claim, include the method entry whose `id_registry` role is `root`.

## Links

Within the section only: `supports` from a corollary Claim to the primary Claim, when the paper states a direct logical dependency.

| relation | source | target |
|---|---|---|
| `supports` | Claim | Claim |

This section emits no cross-section links; its hub role is implicit in the five-section structure.

## Extraction focus

- Keep the section tight: 1–3 precisely scoped claims. Sub-findings belong in experiment or analysis.
- Named entities (datasets, models) mentioned in claims belong in the `statement` text, not as separate Entity units.
- Every Claim must point via `provenance` to the sentence stating the contribution.

## Anti-patterns

- Do not extract every sentence that sounds like a finding as a separate Claim. Sub-findings belong in experiment or analysis sections.
- Do not create support-only units here; support is represented by experiment Metrics and analysis Claim/Metric pairs.
- Do not create Method units for the contribution system; reference their IDs via `target_ids`.
- Do not omit provenance.

## Worked example

{
  "section": {
    "section_type": "claim",
    "anchor_id": "clm:attention_only",
    "covers_entries": [],
    "claims": [
      {
        "id": "clm:attention_only",
        "type": "Claim",
        "statement": "A sequence transduction architecture based solely on attention, dispensing with recurrence and convolutions, reaches state-of-the-art translation quality while training markedly faster.",
        "claim_kind": "comparative",
        "target_ids": ["mth:transformer"],
        "polarity": "positive",
        "novelty": "original",
        "epistemic_status": "conclusion",
        "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
      }
    ],
    "links": []
  }
}

## Anchor

`anchor_id` must be the primary contribution Claim — the one sentence that, if removed, would make the paper's contribution invisible.
