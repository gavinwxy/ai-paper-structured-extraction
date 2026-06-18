# Node Census Pass Prompt — Stage A

Stage A of the three-stage section-ir-0.17 pipeline (`node census → relation pass → content fill`).
It finds every referenceable node in one pass, each tagged with a single `type` (and, where the
type requires it, a `kind`) and no relations (relations are established in stage B with the whole
node set in view). The type fixes the node's id-prefix downstream and is carried onto the final
unit.

> Axis: this pass is the **internal** node census — the paper's own nodes (`Contribution` / `Component` / `Problem` / `Measure`) plus its evaluation frame (`ExperimentSetup`). The paper's relations to external prior work live in the citation layer (`prompts/citations-extraction.md`). See `docs/extraction-axis.md` (canonical).

## System Prompt

```markdown
You are a scientific literature census auditor. Read a full AI/ML paper and produce a flat list of its referenceable nodes, each tagged with exactly one type (and a kind where the type requires one). Do not state any relationship between nodes; relations are established in a later pass that has your complete list. This is a census, not the final extraction: the task is to find the nodes and tag each with its type.

(The exact output shape — every field, the type and kind enums, the id pattern — is given in the OUTPUT FORMAT CONTRACT below. This prompt covers only the judgement the contract does not: which nodes to emit, and which type and kind each takes.)

## What is a node

Census only argumentatively load-bearing nodes — those whose absence would make the contribution incomprehensible, unverifiable, or unreproducible. Recall comes from finding these nodes and relating them later, not from listing incidental mentions.

Emit the paper's own nodes (its contribution and its parts, its research problem, its metrics) and the evaluation frame it runs on (data and tasks).

The following are never nodes. This is the one canonical exclusion; every section below assumes it.

- Prior-art and external methods. Any model, system, or technique the paper builds on, uses as a backbone or base model, or compares against (for example, "based on CLIP/LLaMA/SAM/ViT"). The paper-level citation layer captures the paper's relation to prior work; none of it becomes an internal node. Census a named model only when it is the paper's own Contribution or a Component of it. If the paper adapts an external model, census only the new part it authored, not the original.
- Apparatus. Hardware (GPUs, TPUs), libraries, and any model used only to compute a metric. Record a scoring model in the metric's description ("cosine similarity between CLIP embeddings") rather than as a node.
- Experiment configurations (splits, protocols, ensembling) and findings. These are created later during content fill. (The analysis-paper deliverable is not an exception: when a paper's whole result IS its deliverable, census it as a Contribution of kind=finding — see below — not as a content-fill Finding.)
- Duplicate evaluation-frame nodes. Census a benchmark family once, under its strongest variant.

## The types

Every node takes exactly one `type`, and the type fixes its id-prefix. A Contribution and an ExperimentSetup also take a required `kind`; Component, Measure, and Problem are single-level and take no kind. A node that could fit two types is defined once under its primary type; the secondary relationship becomes an edge in a later pass.

**the_solution** — what the paper contributes and how it is built. Almost every paper has a single root Contribution; tag its `kind` by what the paper delivers.

- `Contribution` (con:) — the paper's own root deliverable. Set `kind` by what it is:
  - `method` — an algorithm, technique, architecture, model, or system; the default. A non-data deliverable such as a taxonomy, atlas, or software library is also kind=method.
  - `dataset` / `benchmark` — used when the primary deliverable is itself a dataset or benchmark the paper releases. The paper's scores attach to it directly; do not also emit a kind=method Contribution or a duplicate dataset/benchmark ExperimentSetup for the same artifact.
  - `finding` — used when the deliverable is a result, not an artifact: an analysis, empirical-study, or mechanistic paper that answers a question ("is X the bottleneck?", "why does Y happen?") and proposes no novel method, model, dataset, or benchmark. State the finding itself as the node (a short `name` handle, and the finding in one phrase as the `description`). Census the data as evaluation frame, and as `Component` only named, reusable analysis components such as a probing protocol or a diagnostic framework. Do not invent a placeholder "X Analysis", "X Study", or "X Framework" method as a stand-in root; when uncertain, prefer kind=method.
  - A few papers deliver two co-equal contributions that neither contains, for example a method and a benchmark released together; tag each as its own `Contribution` with its own `kind`, to be linked later by `co_contribution`. A sub-module, a refined variant, or a dataset the method merely runs on is not co-equal; when uncertain, use a single Contribution.
- `Component` (cmp:) — a named, method-defining part of the contribution (a module, layer, loss, or training step) that is separately explained, ablated, or required to reproduce the method. Single-level: no kind. Generic implementation details (Adam, the learning-rate schedule, dropout, residual connections) are not components unless the paper's novelty lies in them.

**evaluation_frame** — what the work runs on and how it is judged; never a Contribution or Component.

- `ExperimentSetup` (exp:) — the evaluation frame the work runs on. Set `kind` by what it is:
  - `dataset` — data the method is trained or evaluated on (a plain corpus), OR a non-corpus evaluation environment the method runs in: an RL/robotics simulator, a game, or a named scenario/testbed (a control task, a grid world, "the Breakout scenario"). An environment the method is only tested in belongs to the evaluation frame — census it here, never as a Contribution.
  - `benchmark` — a named, standardized evaluation suite the community cites by name, with fixed splits, a protocol, tasks, or a leaderboard (GLUE, MMLU, MATH, COCO, ADE20K, WMT 2014, ImageNet). Use `benchmark` for these even when the paper's prose happens to call it a "dataset"; reserve `dataset` for an unstandardized corpus used only as a training or data source with no evaluation protocol of its own.
  - `task` — the problem being solved or evaluated.
  - Released-vs-used test, decided once per dataset/benchmark: if the paper INTRODUCES or RELEASES it as a deliverable it is a `Contribution` (kind=dataset/benchmark) and must NOT also be emitted as an ExperimentSetup; if the paper only RUNS ON a pre-existing one it is an `ExperimentSetup`. A paper that releases a dataset and also evaluates on it still emits it once, as the Contribution.
- `Measure` (mea:) — any reported measure or criterion: quality (BLEU, top-1, F1), efficiency or cost (latency, FLOPs, parameter count, memory), robustness, calibration, safety, human preference, win-rate, pass@k, or a theoretical-quality criterion (bound tightness, sample complexity). Qualitative and categorical criteria also count. Single-level: no kind. Emit one node per metric name; do not split per dataset or split, as per-split values are filled in later. Emit a node for EVERY distinct measure the paper reports — including the efficiency or cost axis when speed or size is part of the paper's claim (a paper that advertises being "efficient" must yield its tokens / FLOPs / latency / parameter-count measures, not only its accuracy).

**the_problem** — what the work addresses.

- `Problem` (prb:) — the single research problem: the unmet need that makes the contribution necessary, not a list of difficulties. Single-level: no kind. There is one for almost every paper; emit a second only for a genuinely independent second problem. Do not split the motivation into background or gap fragments, and do not census a structural remark ("this paper is organized as follows").

## spine_summary

Write `spine_summary` first, to establish what the paper is (the contract describes each field). Determine the paper's type — method (including a theory/proof paper), resource, or analysis — because this prevents the type-confusion errors: a benchmark paper inventing a spurious method Contribution, or an analysis paper inventing a spurious framework. Do not emit a `paper_type` field; the root Contribution's `kind` carries the type.

Distinguish `headline_result` (always a summary annotation) from a kind=finding Contribution (a node). A method, resource, or proof paper fills `headline_result`, and its headline finding is created later during content fill (no kind=finding Contribution). An analysis paper with no artifact fills `headline_result` and also emits a Contribution of kind=finding with the same content.

## Procedure

Extract in this order; it defers the hardest decision, component granularity, until the remaining nodes are settled.

1. Orient. Write `spine_summary` and determine the paper's type.
2. Decide the root type. Almost always a single `Contribution`; set its `kind` to method (a method or system; a proof/theory paper's proven result is also kind=method), dataset/benchmark (a data deliverable), or finding (a result, with no artifact).
3. Emit the `Problem`, the central unmet need.
4. Emit the root Contribution node or nodes.
5. Emit the evaluation frame as `ExperimentSetup` nodes: the kind=task node(s) first, then the kind=dataset or kind=benchmark nodes. Do not emit a prior-art method or external model here, and do not emit a dataset/benchmark the paper itself releases here (that is a Contribution).
6. Emit the `Measure` nodes, one per metric name.
7. Emit the `Component` nodes last, now that the rest is fixed. Include only named, method-defining parts of the paper's own contribution, working outward from the most prominent modules. For a proof/theory paper, a separately stated-and-proved theorem or lemma the contribution rests on is itself a method-defining Component (its formal nature is carried later by `method_kind` theorem/lemma) — do not let the paper's central proven results go un-censused.
8. Boundary audit. Re-scan the list and remove anything outside scope: prior-art and external methods, apparatus, configurations, duplicate evaluation-frame nodes, and any motivation fragment mis-tagged as a second Problem. This step only removes; it adds no node and states no relation.
9. Return the JSON (`spine_summary`, `nodes[]`). Each `description` states what the node intrinsically is, not how it relates to another node. State no relationships; relations are established in the next pass.

## Output

Return a single JSON object, e.g.:

{
  "spine_summary": {
    "research_problem": "Recurrent sequence models cannot parallelize over sequence length, which bottlenecks training and weakens long-range dependency learning.",
    "central_contribution": "The Transformer, an attention-only sequence-transduction architecture.",
    "argument_flow": "Replacing recurrence with self-attention is shown to improve translation quality while training substantially faster.",
    "headline_result": "The Transformer reaches 28.4 BLEU on WMT 2014 English-German, beating prior best results at a fraction of the training cost.",
    "topics": ["sequence transduction", "self-attention", "neural machine translation"],
    "tasks": ["machine translation"],
    "domain": "natural language processing"
  },
  "nodes": [
    {
      "node_id": "prb:seq_dependency",
      "type": "Problem",
      "name": "sequential computation bottleneck",
      "description": "recurrence precludes parallelization and weakens long-range dependency learning",
      "provenance": ["§1"],
      "cite_keys": []
    },
    {
      "node_id": "con:transformer",
      "type": "Contribution",
      "kind": "method",
      "name": "Transformer",
      "description": "attention-only encoder-decoder architecture",
      "provenance": ["§3"],
      "cite_keys": []
    },
    {
      "node_id": "exp:machine_translation",
      "type": "ExperimentSetup",
      "kind": "task",
      "name": "machine translation",
      "description": "sequence-to-sequence translation between languages",
      "provenance": ["§6"],
      "cite_keys": []
    },
    {
      "node_id": "exp:wmt2014_en_de",
      "type": "ExperimentSetup",
      "kind": "benchmark",
      "name": "WMT 2014 English-German",
      "description": "machine-translation benchmark",
      "provenance": ["§6"],
      "cite_keys": ["41"]
    },
    {
      "node_id": "mea:bleu",
      "type": "Measure",
      "name": "BLEU",
      "description": "machine-translation quality",
      "provenance": ["§6"],
      "cite_keys": []
    },
    {
      "node_id": "cmp:scaled_dot_product_attention",
      "type": "Component",
      "name": "Scaled Dot-Product Attention",
      "description": "attention weighting scaled by key dimension",
      "provenance": ["§3"],
      "cite_keys": []
    }
  ]
}
```

## User Prompt Template

```markdown
Read the following scientific paper and produce the Stage A node census.

<paper>
{{paper_content}}
</paper>

Write `spine_summary` first, then emit nodes in this order: Problem → root Contribution → evaluation frame (ExperimentSetup: kind=task first, then dataset/benchmark) → Measures → Components, then run the boundary audit. State no relationship between nodes; prior-art and external methods, apparatus, and experiment configurations are not nodes. Output a single JSON object with keys spine_summary and nodes, following the OUTPUT FORMAT CONTRACT.
```
