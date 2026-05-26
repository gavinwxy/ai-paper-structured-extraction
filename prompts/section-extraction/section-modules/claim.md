SECTION FOCUS: claim

This section captures the paper's central thesis and its direct logical corollaries. It is the argumentative hub: every other section either supports, operationalizes, qualifies, or evaluates claims defined here.

Claim units are **born here** — they are not census nodes. Create them from `spine_summary`, this focus, and the paper. This section materializes no census nodes; it authors the claim-centric edges that connect its claims to the nodes they are about. Choose `anchor_id` from a Claim you define here.

## Units you may define

Only `Claim` units (array `claims`). Typical: 1–3 units — the main contribution claim plus at most two direct corollaries.

### Claim
Fields: `statement`, `claim_kind`.
- `claim_kind`: one of `descriptive | mechanistic | comparative | modeling | ablation_finding | failure_mode`. Be precise: `comparative` for "A outperforms B", `descriptive` for "X is characterized by Y", `mechanistic` for "X works because Y", `modeling` for a formal or architectural claim.
- A Claim carries no `target_ids` field. What the claim is about is expressed as an `about` relation (see Relations).

## Relations

This section authors claim-centric edges in `relations[]`:

| relation | source → target | meaning |
|---|---|---|
| `about` | Claim → {Method, Entity, Metric} | the claim is about that node |
| `supports` | Claim → Claim | a corollary claim supports the primary claim |

- Use `about` to bind each claim to the node(s) it is about, referencing `node_registry` ids. For the paper-level contribution claim, point `about` at the method whose `node_registry` role is `contribution`. If the exact node is absent, point at the nearest broader node, else author no `about` edge.
- Use `supports` only when the paper states a direct logical dependency from a corollary claim to the primary claim.
- Endpoints reference nodes/units by id; never invent an id. Every claim needs `provenance`.

## Extraction focus

- Keep the section tight: 1–3 precisely scoped claims. Sub-findings belong in the evidence section.
- Named entities (datasets, models) mentioned in claims belong in the `statement` text, not as separate units.
- Every Claim must point via `provenance` to the sentence stating the contribution.

## Anti-patterns

- Do not extract every sentence that sounds like a finding as a separate Claim. Sub-findings and ablation conclusions belong in the evidence section.
- Do not create Method units for the contribution system; reference their node ids via `about`.
- Do not omit provenance.

## Worked example

{
  "section": {
    "section_type": "claim",
    "anchor_id": "clm:attention_only",
    "claims": [
      {
        "id": "clm:attention_only",
        "type": "Claim",
        "statement": "A sequence transduction architecture based solely on attention, dispensing with recurrence and convolutions, reaches state-of-the-art translation quality while training markedly faster.",
        "claim_kind": "comparative",
        "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
      }
    ],
    "relations": [
      {"source_id": "clm:attention_only", "relation": "about", "target_id": "mth:transformer", "provenance": [{"source_kind": "sentence", "source": ["§1"]}]}
    ]
  }
}

## Anchor

`anchor_id` must be the primary contribution Claim — the one sentence that, if removed, would make the paper's contribution invisible.
