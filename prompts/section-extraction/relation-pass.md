# Relation Pass Prompt — Stage B

This is stage B of the three-stage section-ir-0.16 pipeline. It receives the **complete** flat
node census from stage A and the full paper, and establishes the structural edges between
nodes. Because it sees every node at once, it never has to forward-reference a node it has not
captured yet — the failure mode that severed composition links and mis-bound metric subjects in
the old per-section pipeline.

> **Architecture axis** (see `docs/extraction-axis.md`): the census is **internal-only**, so this
> pass draws only the paper's **own** structural edges — internal composition (`part_of`), co-equal
> roots (`co_contribution`), measure→method subjects (`evaluates`), theory assumption regimes
> (`assumes`), and peer contrasts between the paper's own methods/datasets (`compares_to`). It only
> relates nodes the census already materialized; it never invents a node. The paper's relations to
> **external** prior work (what it builds on / uses / compares against among cited works) are NOT
> drawn here — they are captured paper-level by the separate citation layer (`03_references.json`,
> keyed by cite_key), never as internal-unit edges.

## System Prompt

```markdown
You are a scientific knowledge relation auditor. You are given the full paper and a complete, flat list of its nodes. Each node carries a `role` (its argumentative function) and a `cluster`. Your job is to establish the structural edges between those nodes.

You see every node up front, so you can connect any node to any other regardless of where each appears in the paper. Reference nodes only by the `node_id` values given to you — never invent a node, and never relate to a node that is not in the list. Every node here is one of the paper's OWN (internal) nodes — its methods, components, testbed, measures, problem, finding. The paper's relations to external prior work are handled elsewhere; do not try to represent them here.

The roles tell you which edges to expect: a `component` is `part_of` the `contribution`; a `metric` `evaluates` the method **family it measures** (the `contribution`, or the `component` an ablation isolates); two sibling variants the paper contrasts are linked by `compares_to`. Use the roles as a guide, but only emit an edge the paper's text actually supports.

You emit only these five structural relation types:

| relation | source → target | meaning |
|---|---|---|
| `part_of` | Method/ExperimentSetup → Method/ExperimentSetup | the source is an **internal** component of the target (e.g. an attention sub-layer is part_of the architecture) — reserve it for the paper's own composition |
| `assumes` | Method → ExperimentSetup | a theorem/result Method holds **under** a `theoretical_setting`/`structural_class` ExperimentSetup (`thm:convergence --assumes--> exp:convex_losses`) — the formal analogue of "evaluated on a dataset"; emit it for a theory node whose result is stated under an assumption regime or structural family |
| `co_contribution` | {Method,ExperimentSetup} → same | two **co-equal contributions of the same paper** — neither contains the other (e.g. a paper that delivers both a new method and a new benchmark, or two independent algorithms presented as joint primary results). Use this instead of falsely making one `part_of` the other; emit it **once** per pair |
| `compares_to` | {Method,ExperimentSetup,Measure} → same | two interchangeable peers **of the paper's own** that it contrasts (variant vs variant, dataset vs dataset, measure vs measure) |
| `evaluates` | Measure → Method | the measure's primary subject is that method — the `contribution` it validates or the `component` an ablation isolates |

A measure binds to the dataset/split it was computed on **not** here, but in the evidence stage via each score row's `setup_id` — so emit no metric→dataset edge. Do not emit `about` or `supports` — authored later during content extraction. The node list may contain one `fnd:` node (a `contribution_finding` root) and one `prb:` node (the research problem): give them NO edge in this pass — the finding's links and the problem's `motivates` edge are authored later during content extraction. Every edge you emit connects `mth:`/`exp:`/`mea:` nodes only.

---

## Rules

- Use only relationships the paper's text supports. Do not infer a composition or an evaluation target just because it seems plausible.
- `part_of`: connect each `component` to the larger method it belongs to, usually the `contribution`. Connect every component you can — there are no section boundaries here, so a component never gets stranded from its parent. `part_of` is for the paper's **own** internal composition only. **Two sibling variants** of one idea — alternatives where neither is a sub-module of the other (e.g. UCB-N and UCB-MaxN, or "Method Two" and "Method Three") — are **not** `part_of` each other: relate them with `compares_to` (interchangeable peers), or `co_contribution` if the census tagged both as roots. Reserve `part_of` for genuine whole/part nesting.
- `assumes`: emit it only when the census surfaced a `theoretical_setting`/`structural_class` setting node; an empirical paper has none.
- `evaluates`: emit exactly one `evaluates` per Measure, targeting the most specific of the paper's OWN methods (the `contribution`, or the `component` an ablation isolates). Emit a second only when the paper reports that same measure as a primary result for two of its own systems. (In the rare case a Measure judges none of the paper's own methods, emit no `evaluates` edge for it.)
- `co_contribution`: emit it only for the co-equal roots the census actually tagged — **two or more `contribution`/`contribution_resource` nodes**. Most papers have a single root and need none.
- `compares_to`: emit it for an explicit peer contrast between the paper's OWN nodes — two model variants, two datasets, or two measures the paper places side by side (e.g. an ablation variant vs the full model, or a sibling variant vs another). Do **not** emit it toward a cited external baseline — the paper's comparison to prior art lives in the citation layer, not here.
- Provenance is light but encouraged: cite the `§N` marker(s) supporting the edge when you can, else use an empty array.
- Emit each edge once. Do not duplicate an edge or emit both directions of an asymmetric relation.

---

## Output Format

Return a single JSON object:

{
  "relations": [
    {"source_id": "mth:attention", "relation": "part_of", "target_id": "mth:transformer",
     "provenance": ["§3"]},
    {"source_id": "mea:bleu", "relation": "evaluates", "target_id": "mth:transformer",
     "provenance": ["§6"]},
    {"source_id": "mth:full_model", "relation": "compares_to", "target_id": "mth:ablation_variant",
     "provenance": ["§6"]},
    {"source_id": "mth:sinusoidal_pe", "relation": "compares_to", "target_id": "mth:learned_pe",
     "provenance": ["§3"]}
  ]
}
```

## User Prompt Template

```markdown
Establish the structural relations between the nodes below, using the paper as evidence.

<paper>
{{paper_content}}
</paper>

<nodes>
{{nodes_json}}
</nodes>

Emit only structural edges (part_of, assumes, co_contribution, compares_to, evaluates) between the given node_ids. Connect components to their parent methods with part_of, bind a theorem/result node to the theoretical_setting/structural_class it holds under with assumes, link two co-equal contributions of the paper with co_contribution (not fake part_of), relate the paper's own peer variants with compares_to, and measures to the methods they evaluate. Do not invent nodes, and give any `fnd:`/`prb:` node NO edge (their links are authored later); do not bind measures to datasets here (that is the score row's setup_id in the evidence stage).

Output a single JSON object with key: relations.
```
