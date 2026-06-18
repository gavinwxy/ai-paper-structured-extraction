SECTION FOCUS: problem

# Goal
You are filling the **problem** section — the opening of the paper's discovery arc. It states the **research problem**: the unresolved question or unmet need the work addresses. This is the premise that makes the contribution necessary and intelligible, and the thing the evidence will ultimately resolve.

**CRITICAL — materialize the planned `prb:` node.** The census plans the research problem as a `prb:` node (type `Problem`) in `node_registry`; this section **materializes** it — write the Problem unit with **that exact `prb:` id** (its census `name`/`description` are only the handle; you author the full `description` here, from the paper). If the registry carries **no** `Problem` node (the census missed it), create the Problem yourself with a fresh `prb:` id — *the problem must exist either way.* Choose `anchor_id` from the Problem unit. This section authors **one** edge type, `motivates`.

# Units You May Define
**Only `Problem` units** (array `problems`). **Typically exactly one** — the single research problem, under the census `prb:` id when the registry has one. Define a second **only** when the paper genuinely pursues two *independent* problems (the census may have tagged both); **never split one problem into background/gap/motivation fragments**. A `Problem` is single-level and carries no `kind`.

## Problem — the research problem
Fields: `description`.
- `description`: **be specific** — *what* is unsolved, in *what* task or setting, and *why* existing approaches fall short. **Fold the necessary background straight into this prose**; do NOT spin background, motivation, or assumptions out into separate units. Carry the paper's **real task names** and the **concrete limitation**, not a vague restatement.

# Output Detail Level (Tiered Strategy)
- `description`: **Sharp & self-contained.** One focused statement that names the real task/setting and the concrete gap. Detailed enough to stand alone, but **not** a literature review — fold only the background that *defines what is missing*.

# Relations
This section authors **one** edge type in `relations[]`, binding the problem to the contribution that addresses it:

| relation | source → target | meaning |
|---|---|---|
| `motivates` | `Problem` → {`Contribution`, `Component`, `ExperimentSetup`} | this problem is what the node addresses / why it exists |

- Author **one** `motivates` edge **per Problem**, from that Problem to the node it best matches — normally the **root Contribution** (a `con:` node — it always exists, whatever the paper's kind: a method, dataset/benchmark, or finding deliverable is all a `Contribution` now). With two independent Problems, **each** gets its own `motivates` edge to its own best-matching target. When the census tagged co-equal Contributions, target the **primary** one (the deliverable the title/abstract centers on). A `Component` (`cmp:`) or `ExperimentSetup` (`exp:`) is an acceptable target **only when needed** — e.g. the problem is specifically about one dataset/task, in which case target that `exp:` node instead.
- `source_id` is the Problem unit you define in this section. `target_id` must be an **existing** `node_registry` id of type Contribution, Component, or ExperimentSetup — **never a Problem or Finding, never invented**. Emit `[]` only when no registry node maps.
- You do **NOT** author the closing `resolves` edge (the finding that answers this problem). That edge is added automatically downstream, from the Contribution the problem motivates and the finding that is about it.

# Instructions (Extraction Focus)
1. **Find the single sharpest problem statement** and make it the Problem `description`.
2. **Pull in prior-work characterizations only as the part of the description that defines what is missing.** Do NOT write a literature review.
3. **Keep named entities inside the prose.** Datasets, benchmarks, and systems mentioned belong *inside* the `description`, not as separate units.

# Anti-Patterns
- Do **NOT** emit several Problem units for one problem (no background/gap/motivation split) — that is the old over-tagged shape; collapse it into one focused statement.
- Do **NOT** create a Finding unit for the contribution here; the contribution finding belongs in the evidence section.
- Do **NOT** create Contribution or Component units here. A system named as background belongs in the `description`. *(The paper's own contribution and its sub-modules are materialized in the method/evidence sections; external baselines it merely compares against are not units at all — the paper's relation to them is captured paper-level by the citation layer, and their numbers are preserved verbatim by the evidence stage.)*
- Do **NOT** create a Problem for paper-structural remarks ("this paper is organized as follows").

# Mental Sandbox / Worked Example

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
      {"source_id": "prb:seq_dependency", "relation": "motivates", "target_id": "con:transformer", "provenance": ["§2"]}
    ]
  }
}

**Key lesson:** one focused Problem, materialized under the census `prb:` id, with background folded *into* the description and a single `motivates` edge to the root Contribution — no background/gap fragments, no Finding, no Contribution units.

# Anchor
`anchor_id` must be the **Problem unit** — the statement of the unresolved problem. With a single Problem this is unambiguous; with two, anchor on the **primary** one.
