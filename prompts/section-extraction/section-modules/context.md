SECTION FOCUS: context

This section captures the argumentative premises that make the central contribution necessary and intelligible. Context units establish the research environment, identify the gap or challenge the paper addresses, and frame the assumptions the argument rests on.

This section is planless: `section_plan.items` is empty. Extract the context role directly from `spine_summary`, this focus, and the paper. Set `covers_entries: []`, choose `anchor_id` from a Context unit you define here, and do not invent plan item IDs.

## Units you may define

Only `Context` units (array `contexts`). Typical: 2–5 units.

### Context — argumentative premise
Fields: `context_kind`, `description`.
- `context_kind`: one of `background | gap | motivation | challenge | assumption` — `background` for established prior work, `gap` for the unresolved problem, `motivation` for the "why now", `challenge` for a technical obstacle, `assumption` for a premise taken as given.
- `description`: a single assertive sentence. Make it specific — what gap, in what task, versus what prior approach.

## Links

This section emits no links — each Context unit stands as an independent premise. Return `links: []`.

## Extraction focus

- Identify the single sharpest gap or problem statement; make it its own Context unit with `context_kind: gap`.
- Capture prior-work characterizations only when they directly define what is missing. Do not extract an exhaustive literature review.
- If the paper states explicit assumptions, extract each as a separate Context unit with `context_kind: assumption`.
- Named entities (datasets, benchmarks, systems) mentioned in context belong inside the Context `description`, not as separate Entity units.
- Prior-work claims cited as background are Context (`context_kind: background`), not Claim units.

## Anti-patterns

- Do not create a Claim unit for a contribution here; contributions belong in the claim section.
- Do not create Method units for methods cited only as score baselines; baseline scores are not captured in the IR.
- Do not bundle background + gap + motivation into one omnibus Context unit; split them.
- Do not create Context units for paper-structural observations ("this paper is organized as follows").

## Worked example

{
  "section": {
    "section_type": "context",
    "anchor_id": "ctx:seq_dependency_gap",
    "covers_entries": [],
    "contexts": [
      {
        "id": "ctx:rnn_sequential",
        "type": "Context",
        "context_kind": "background",
        "description": "Dominant sequence transduction models couple computation to input position through recurrence, processing tokens strictly in order.",
        "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
      },
      {
        "id": "ctx:seq_dependency_gap",
        "type": "Context",
        "context_kind": "gap",
        "description": "Sequential recurrence precludes parallelization within a training example and weakens learning of dependencies between distant positions.",
        "provenance": [{"source_kind": "sentence", "source": ["§1", "§2"]}]
      }
    ],
    "links": []
  }
}

## Anchor

`anchor_id` should be the Context unit with `context_kind: gap` — the sharpest statement of the unresolved problem. If no gap is present, use the most specific `motivation` or `challenge` Context unit.
