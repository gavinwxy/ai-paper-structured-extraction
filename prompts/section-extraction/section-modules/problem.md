SECTION FOCUS: problem

This section opens the paper's discovery arc: it states the **research problem** — the unresolved question or unmet need the work addresses. It is the premise that makes the contribution necessary and intelligible, and the thing the evidence will ultimately resolve.

Problem units are **born here** — they are not census nodes. Create the problem directly from `spine_summary`, this focus, and the paper. This section materializes no census nodes; choose `anchor_id` from the Problem you define here. It authors one edge type, `motivates` (see Relations).

## Units you may define

Only `Problem` units (array `problems`). **Typically exactly one** — the single research problem. Define a second only when the paper genuinely pursues two independent problems; never split one problem into background/gap/motivation fragments.

### Problem — the research problem
Fields: `description`.
- `description`: one or two assertive sentences naming the problem. Be specific — *what* is unsolved, in *what* task or setting, and *why* existing approaches fall short. Fold the necessary background straight into this prose; do not spin background, motivation, or assumptions out into separate units. Carry the paper's real task names and the concrete limitation, not a vague restatement.

## Relations

This section authors one edge type in `relations[]`, binding the problem to the contribution that addresses it:

| relation | source → target | meaning |
|---|---|---|
| `motivates` | Problem → {Method, ExperimentSetup} | this problem is what the node addresses / why it exists |

- Author one `motivates` edge from the Problem; pick `target_id` by the root's `role` in `node_registry`: (1) `contribution` or `contribution_resource` → that node. (2) `contribution_finding` (`motivates` cannot target a Finding) → the Method or ExperimentSetup the paper investigates: a `builds_on`/`compared_against`/`component` Method, or the `task`/`benchmark` it probes. (3) If the problem is specifically about one dataset/task, target that `exp:` node instead.
- `source_id` is the Problem unit you define in this section. `target_id` must be an existing `node_registry` id of type Method or ExperimentSetup — never a Problem or Finding, never invented. Emit `[]` only when no registry node maps.
- You do **not** author the closing `resolves` edge (the finding that answers this problem). That edge is added automatically downstream, from the contribution the problem motivates and the finding that is about it.

## Extraction focus

- Identify the single sharpest problem statement and make it the Problem `description`.
- Pull in prior-work characterizations only as the part of the description that defines what is missing. Do not write a literature review.
- Named entities (datasets, benchmarks, systems) mentioned belong inside the `description`, not as separate units.

## Anti-patterns

- Do not emit several Problem units for one problem (no background/gap/motivation split) — that is the old over-tagged shape; collapse it into one focused statement.
- Do not create a Finding unit for the contribution here; the contribution finding belongs in the evidence section.
- Do not create Method units here; a system named as background belongs in the `description`. (Comparison baselines are `compared_against` Methods in the method section — not here; the baseline's number is preserved by the evidence stage, in the verbatim source table or as a score row.)
- Do not create a Problem for paper-structural remarks ("this paper is organized as follows").

## Worked example

{
  "section": {
    "section_type": "problem",
    "anchor_id": "prb:seq_dependency",
    "problems": [
      {
        "id": "prb:seq_dependency",
        "type": "Problem",
        "description": "Dominant sequence transduction models couple computation to input position through recurrence, which precludes parallelization within a training example and weakens the learning of dependencies between distant positions — limiting both training speed and quality on long sequences.",
        "provenance": ["§1", "§2"]
      }
    ],
    "relations": [
      {"source_id": "prb:seq_dependency", "relation": "motivates", "target_id": "mth:transformer", "provenance": ["§2"]}
    ]
  }
}

## Anchor

`anchor_id` must be the Problem unit — the statement of the unresolved problem. With a single Problem this is unambiguous; with two, anchor on the primary one.
