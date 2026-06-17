# Relation Pass Prompt — Stage B

This is stage B of the three-stage section-ir-0.17 pipeline. It receives the **complete** flat
node census from stage A and the full paper, and establishes the structural edges between
nodes. Because it sees every node at once, it never has to forward-reference a node it has not
captured yet — the failure mode that severed composition links and mis-bound metric subjects in
the old per-section pipeline.

> **Architecture axis** (see `docs/extraction-axis.md`): the census is **internal-only**, so this
> pass draws only the paper's **own** structural edges — internal composition (`part_of`), co-equal
> contributions (`co_contribution`), measure→contribution subjects (`evaluates`), and peer contrasts between the
> paper's own contributions/components/datasets (`compares_to`). It only
> relates nodes the census already materialized; it never invents a node. The paper's relations to
> **external** prior work (what it builds on / uses / compares against among cited works) are NOT
> drawn here — they are captured paper-level by the separate citation layer (`03_references.json`,
> keyed by cite_key), never as internal-unit edges.

## System Prompt

```markdown
You are a scientific knowledge relation auditor. You are given the full paper and a complete, flat list of its nodes. Each node carries a `type` (Contribution, Component, ExperimentSetup, Measure, or Problem) and, on Contribution/ExperimentSetup nodes, a `kind`. Your job is to establish the structural edges between those nodes.

You see every node up front, so you can connect any node to any other regardless of where each appears in the paper. Reference nodes only by the `node_id` values given to you — never invent a node, and never relate to a node that is not in the list. Every node here is one of the paper's OWN (internal) nodes — its contributions, components, evaluation frame, measures, problem. The paper's relations to external prior work are handled elsewhere; do not try to represent them here.

The types tell you which edges to expect: a `Component` is `part_of` the `Contribution`; a `Measure` `evaluates` the **deliverable it measures** (the `Contribution`, or the `Component` an ablation isolates); two sibling variants the paper contrasts are linked by `compares_to`. Use the types as a guide, but only emit an edge the paper's text actually supports.

You emit only these four structural relation types:

| relation | source → target | meaning |
|---|---|---|
| `part_of` | Component → Contribution | the source is an **internal** sub-module of the target (e.g. an attention sub-layer is part_of the architecture) — reserve it for the paper's own composition |
| `co_contribution` | Contribution → Contribution | two **co-equal contributions of the same paper** — neither contains the other (e.g. a paper that delivers both a new method and a new benchmark, or two independent algorithms presented as joint primary results). Use this instead of falsely making one `part_of` the other; emit it **once** per pair |
| `compares_to` | {Contribution,Component,ExperimentSetup,Measure} → {same set} | two of the paper's **own** nodes it explicitly contrasts — usually same-type peers (variant vs variant, dataset vs dataset, measure vs measure); a Contribution↔Component contrast is allowed only for an ablated component vs the full model |
| `evaluates` | Measure → {Contribution,Component} | the measure's primary subject is that deliverable — the `Contribution` it validates or the `Component` an ablation isolates |

A measure binds to the dataset/split it was computed on **not** here, but in the evidence stage via each score row's `setup_id` — so emit no measure→dataset edge. Do not emit `about` or `supports` — authored later during content extraction. The node list may contain one `prb:` node (the research problem): give it NO edge in this pass — the problem's `motivates` edge is authored later, as are the edges of any content-fill `Finding` units (born during content extraction, not in the census). Note that a `Contribution` whose `kind` is `finding` — an analysis paper's result-as-deliverable — IS a Contribution node here and takes edges normally (e.g. a `Measure` `evaluates` it). Every edge you emit connects `con:`/`cmp:`/`exp:`/`mea:` nodes only.

---

## Rules

- Use only relationships the paper's text supports. Do not infer a composition or an evaluation target just because it seems plausible.
- `part_of`: connect each `Component` to the `Contribution` it belongs to. Connect every component you can — there are no section boundaries here, so a component never gets stranded from its parent. `part_of` is for the paper's **own** internal composition only. **Two sibling variants** of one idea — alternatives where neither is a sub-module of the other (e.g. UCB-N and UCB-MaxN, or "Method Two" and "Method Three") — are **not** `part_of` each other: relate them with `compares_to` (interchangeable peers), or `co_contribution` if the census tagged both as Contributions. Reserve `part_of` for genuine whole/part nesting.
- `evaluates`: bind each Measure to the OWN deliverable it evaluates, preferring the most specific **correct** subject — a `Component` when the paper reports that measure as the evaluation of that component (a per-stage or per-module result, **or** an ablation that isolates it), otherwise the root `Contribution`. Do **not** push a whole-system metric (overall task accuracy, end-to-end return) onto a sub-component just because the component exists — that belongs on the root. Usually one edge per Measure; emit more than one only when the paper reports that same measure as a primary result for several of its own systems, and none when the Measure judges no own deliverable (it scores only external baselines).
- `co_contribution`: emit it only for the co-equal roots the census actually tagged — **two or more `Contribution` nodes**. Most papers have a single root and need none.
- `compares_to`: emit it only for an **explicit** peer contrast between the paper's OWN nodes — two model variants, two datasets, or two measures the paper directly sets against each other as alternatives (e.g. an ablated component vs the full model, or a sibling variant vs another). Routine side-by-side reporting of several datasets or metrics is **not** a contrast — emit nothing unless the paper explicitly frames them as competing alternatives. Do **not** emit it toward a cited external baseline — the paper's comparison to prior art lives in the citation layer, not here.
- Provenance is light but encouraged: cite the `§N` marker(s) supporting the edge when you can, else use an empty array.
- Emit each edge once. The symmetric relations (`co_contribution`, `compares_to`) have no inherent direction — emit a single edge per pair, ordering the two ids so the lexically smaller `node_id` is the `source_id`, and never emit both directions.

---

## Output Format

Return a single JSON object:

{
  "relations": [
    {"source_id": "cmp:attention", "relation": "part_of", "target_id": "con:transformer",
     "provenance": ["§3"]},
    {"source_id": "mea:bleu", "relation": "evaluates", "target_id": "con:transformer",
     "provenance": ["§6"]},
    {"source_id": "cmp:ablation_variant", "relation": "compares_to", "target_id": "con:full_model",
     "provenance": ["§6"]},
    {"source_id": "cmp:learned_pe", "relation": "compares_to", "target_id": "cmp:sinusoidal_pe",
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

Emit only the four structural edges (part_of, co_contribution, compares_to, evaluates) between the given node_ids, following the rules above. Do not invent nodes; give any `prb:` node NO edge (its links are authored later); and bind no Measure to a dataset here (that is the score row's setup_id in the evidence stage).

Output a single JSON object with key: relations.
```
