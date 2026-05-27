SECTION FOCUS: context

This section captures the argumentative premises that make the central contribution necessary and intelligible. Context units establish the research environment, identify the gap or challenge the paper addresses, and frame the assumptions the argument rests on.

Context units are **born here** — they are not census nodes. Create them directly from `spine_summary`, this focus, and the paper. This section materializes no census nodes; choose `anchor_id` from a Context unit you define here. It authors one edge type, `motivates` (see Relations).

## Units you may define

Only `Context` units (array `contexts`). Typical: 2–5 units.

### Context — argumentative premise
Fields: `context_kind`, `description`.
- `context_kind`: one of `background | gap | motivation | challenge | assumption` — `background` for established prior work, `gap` for the unresolved problem, `motivation` for the "why now", `challenge` for a technical obstacle, `assumption` for a premise taken as given.
- `description`: a single assertive sentence. Make it specific — what gap, in what task, versus what prior approach.

## Relations

This section authors one edge type in `relations[]`, binding a premise to the node it justifies:

| relation | source → target | meaning |
|---|---|---|
| `motivates` | Context → {Method, Entity} | this premise is what the node addresses / why it exists |

- Author a `motivates` edge from the `gap` Context — and, only when the paper makes the link explicit, from a `challenge` or `motivation` Context — to the contribution it justifies: point `target_id` at the method whose `node_registry` role is `contribution`. When the premise is instead about a specific dataset or task, point at that Entity node.
- `background` and `assumption` Context units usually author no edge.
- Endpoints reference `node_registry` ids; never invent an id, and never point at a Context or Claim — the target must be a Method or Entity node. Give the empty array `[]` when no premise maps to a registry node.

## Extraction focus

- Identify the single sharpest gap or problem statement; make it its own Context unit with `context_kind: gap`.
- Capture prior-work characterizations only when they directly define what is missing. Do not extract an exhaustive literature review.
- If the paper states explicit assumptions, extract each as a separate Context unit with `context_kind: assumption`.
- Named entities (datasets, benchmarks, systems) mentioned in context belong inside the Context `description`, not as separate Entity units.
- Prior-work claims cited as background are Context (`context_kind: background`), not Claim units.

## Anti-patterns

- Do not create a Claim unit for a contribution here; contributions belong in the claim section.
- Do not create Method units here for any reason; a system named as background belongs in the Context `description`. (Comparison baselines are captured as `compared_against` Methods in the method section and as score rows in the evidence section — not here.)
- Do not bundle background + gap + motivation into one omnibus Context unit; split them.
- Do not create Context units for paper-structural observations ("this paper is organized as follows").

## Worked example

{
  "section": {
    "section_type": "context",
    "anchor_id": "ctx:seq_dependency_gap",
    "contexts": [
      {
        "id": "ctx:rnn_sequential",
        "type": "Context",
        "context_kind": "background",
        "description": "Dominant sequence transduction models couple computation to input position through recurrence, processing tokens strictly in order.",
        "provenance": ["§1"]
      },
      {
        "id": "ctx:seq_dependency_gap",
        "type": "Context",
        "context_kind": "gap",
        "description": "Sequential recurrence precludes parallelization within a training example and weakens learning of dependencies between distant positions.",
        "provenance": ["§1", "§2"]
      }
    ],
    "relations": [
      {"source_id": "ctx:seq_dependency_gap", "relation": "motivates", "target_id": "mth:transformer", "provenance": ["§2"]}
    ]
  }
}

## Anchor

`anchor_id` should be the Context unit with `context_kind: gap` — the sharpest statement of the unresolved problem. If no gap is present, use the most specific `motivation` or `challenge` Context unit.
