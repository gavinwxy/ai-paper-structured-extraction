SECTION FOCUS: method

# Goal
You are filling the **method** section — the technical apparatus the paper introduces or applies: algorithms, model architectures, training strategies, objectives, formal statements, and major components. This section **explains how the paper's claim is realized**.

**CRITICAL-1 — materialize the census; add only Components.** Reuse every census `node_id` **verbatim**. For each `Contribution` node (`kind: method`) emit a Contribution unit (copy its `kind` verbatim too); for each `Component` node emit a Component unit. You may add a fresh `cmp:` Component **only** when the method section clearly contains a named, method-defining part the census missed. **NEVER add a fresh Contribution here** — a missing root is a census-repair issue, not a method-fill one.

**CRITICAL-2 — formulas are the priority field, and an objective lives only in `formulas`.** Capture **every** displayed/stated defining equation and **every** stated loss/objective. **When one unit defines several equations, capture them all — never stop at the first.** An objective is a tagged entry in its unit's `formulas` — never a separate unit, and never represented two ways (see *Routing*).

# The Core Rule: Materialize Method Census Nodes
From `node_registry`:
1. every `Contribution` node with `kind: method` → one Contribution unit (`id` = its `node_id` **verbatim**; `kind` copied **verbatim**);
2. every `Component` node → one Component unit (`id` = its `node_id` **verbatim**);
3. add a fresh `cmp:` Component **only** for a clearly named, method-defining part the census missed.

This section may define **only** `contributions[]` and `components[]`, and authors **no `relations` field**. Dataset, benchmark, and `finding` Contributions are materialized in the **evidence** section, not here; **Measure** and **ExperimentSetup** units never belong here. *(The census is internal-only — it lists no external baselines, so there are none to materialize here; the paper's comparisons to prior art live in the citation layer.)*

# Important Definitions — Units You May Define

## Contribution
The **root method deliverable** the paper introduces. Fields: `name`, `kind`, optional `method_kind`, optional `inputs` / `outputs` / `formulas`, `implementation_notes`.
- **`kind` (required)** — copy it **verbatim** from the node's `kind` in `node_registry` (authoritative; do NOT re-decide). In this section it is **always `method`** (a dataset/benchmark/finding Contribution is born in the evidence section). A proven formal result (theorem, lemma, bound) or a formal construct (definition) is **still `kind: method`** — its formal nature rides on `method_kind` below, **never** on a `theory` kind (there is no such kind).
- **Materialize every `method`-kind Contribution, including co-equal roots** (the census links them via `co_contribution`). **Do NOT demote a co-equal root into a Component**, and **do NOT create a new Contribution** — any fresh unit you add is a Component.
- **`name`** — match how the paper refers to the contribution (the exact system or algorithm name).

## `method_kind` (optional refinement — use only when clear)
One of: `algorithm | model_architecture | training_strategy | objective_function | resource | taxonomy | theorem | lemma | bound | definition | assumption`. It refines `kind`; **omit it when the sub-kind is unclear** rather than guessing.
- **`algorithm`** — an executable procedure, pipeline, protocol, pseudo-code, or complexity-described method.
- **`model_architecture`** — a model structure or network design.
- **`training_strategy`** — a training *process*: schedule, curriculum, warmup, or optimization procedure.
- **`objective_function`** — **reserve** for a contribution whose own deliverable *is* a loss/objective. A method merely *having* a loss is **not** `objective_function` (see *Routing*).
- **`resource`** — a released artifact (software library, atlas, model collection) where the paper describes what it *contains/provides* rather than a procedure of its own.
- **`taxonomy`** — a classification scheme or survey taxonomy that *is* the contribution.
- **`theorem` / `lemma` / `bound`** — a **formal statement the paper proves** (including a complexity/sample/regret bound it proves itself).
- **`definition`** — a formal construct the paper introduces.
- **`assumption`** — a **named premise** the formal results explicitly invoke (e.g. "Low-rank Tasks", "bounded rewards"); tag the named, separately-stated premise the theorems rest on, **not** every passing caveat.

## Component
A **single-level sub-module** of a Contribution. **Same rich fields as a Contribution** (`name`, `description`, optional `inputs` / `outputs` / `formulas` / `implementation_notes`, optional `method_kind`) **except it has no `kind`**. A Component is **not** decomposed into further sub-components here. A named theorem **premise / condition / assumption** may be a Component with `method_kind: assumption`. **Any fresh unit you add is a Component, never a Contribution.**

## Field Suppression for Static / Formal Units
When `method_kind` is **`resource`, `taxonomy`, `theorem`, `lemma`, `bound`, `definition`, or `assumption`**, the unit performs **no computation** — **omit `inputs`, `outputs`, and `formulas`** (do NOT fabricate I/O or equations for a static statement). Put the statement, contents, scope, or proof strategy in **`description`**. For these units **omit `implementation_notes`** unless the paper gives concrete implementation or release details.

# Inputs & Outputs
Use `inputs` / `outputs` **only** when the paper states or clearly describes what flows into or out of the unit — e.g. `inputs: ["queries", "keys", "values"]`, `outputs: ["context vectors"]`. **Do NOT invent** I/O from general knowledge. Named datasets, libraries, models, and resources *used by* the method belong in **`description`**, **not** as `ExperimentSetup` units.

# `formulas` — Defining Equations (optional, but high-value)
Capture **every** displayed or clearly stated equation that defines how the unit works — attention/scoring formulas, layer transforms, recurrences, residual mappings, losses, optimization objectives, regularizers. **Do NOT** leave the field empty when such an equation appears in the text. Transcribe expressions **faithfully and completely** (e.g. `Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V`), and capture **every distinct** defining equation — **even when a single unit defines many** (a multi-stage method, a layered architecture): transcribe them all, do **not** stop at the first or summarize the rest in prose. **Do NOT** transcribe incidental algebra, dimensional bookkeeping, or a symbol-by-symbol glossary — the expression and the unit's `description` carry the meaning.

Each entry takes **exactly one of two shapes**:
- **defining equation** — `{ "name": <short label>, "expression": <LaTeX or plain text> }`
- **objective** — `{ "name": ..., "expression": ..., "role": "objective", "description": <what it optimizes> }`

`role` takes **only** the value `"objective"`; `role` and `description` appear on **objective entries only** — an ordinary defining equation carries just `name` + `expression`.

## Objective Hunt — actively check for a stated loss/objective
For **every** Contribution and Component, check whether the paper states the loss or optimization objective it minimizes/maximizes — it is often stated briefly, in a training-details paragraph rather than the core exposition, and is often a standard loss (cross-entropy, `L1 + λ·L_SSIM`, MSE). **When stated, transcribe it — even a one-line standard loss — as an objective entry.** A *missing* objective must mean the paper states none, not that it was overlooked. Conversely, transcribe **only what the paper states** — **never** reconstruct an unstated objective from general knowledge of a system, and **never** tag a forward/inference/rendering equation as the objective just so the unit has one. A unit optimizing several stated objectives may tag each.

## Routing — do not represent one objective three ways
① a unit's loss/optimization target → a `role: "objective"` entry in **that unit's `formulas`** (NOT a separate unit); ② a training *process* (schedule, curriculum, warmup) → a unit with `method_kind: training_strategy`; ③ a contributed loss that **itself** is the paper's deliverable → `method_kind: objective_function`.

## Formula Placement — each equation appears once, on the unit it defines
The parent Contribution carries **only its own combined objective** (`L = L^A + αL^R`); each component loss is the objective of **its own Component** — do NOT re-transcribe component losses in the parent's `formulas`. This parent↔component ban is the **only** cross-unit one: **sibling systems or variants that each state the same objective each carry it** — do NOT drop a stated training loss merely because a sibling also states it.

**This rule scopes LOSSES only — it never thins a unit's *defining* equations.** A computation-heavy unit (a multi-stage root, a layered architecture) carries **all of its own** defining equations, however many. Moving an equation onto the component that computes it is **relocation, not deletion** — every distinct equation the paper writes out must survive on exactly one unit. **Never** reduce a computation-heavy unit to just its objective when the paper states the equations it computes.

# Descriptions & Implementation Notes
- **`description`** — state what the unit does. For a **formal** unit, include the formal statement, its scope, and (when given) the proof strategy. Do NOT invent causal rationale the paper does not state.
- **`implementation_notes`** — for an **algorithmic / implemented** unit, give reproducibility-relevant detail (software, configuration, caveats, boundary conditions, operational constraints); use `""` only when the paper states nothing. For **static / formal** units, omit unless real implementation or release detail is provided.

# Formal Results
A **theorem, lemma, bound, definition, or assumption** introduced by the paper is a `method`-kind unit: a formal **root** is a `Contribution` with `kind: method` whose formal type rides on `method_kind`; a premise/condition may be a `Component` with `method_kind: assumption`. Do NOT fabricate `inputs` / `outputs` / `formulas`. The **proven result itself** becomes a `Finding` (kind `theorem` / `lemma` / `bound`) in the **evidence** section, and the `Contribution --supports--> Finding` edge is authored **there, not here**.

# Output Detail Level (Tiered Strategy)
- **`formulas`: high-value, faithful, complete.** Transcribe every defining equation and every stated objective verbatim — the section's priority field. Never summarize an equation in prose instead of giving it.
- **`description`: factual & complete.** What the unit does, and for a theorem/lemma its proof strategy. No invented rationale.
- **`implementation_notes`: reproducibility-focused.** Concrete config/software choices; `""` when the paper states none.

# Relations
This section authors **no relations** and its schema has **no `relations` field**. Do NOT emit `relations`, `part_of`, `compares_to`, `supports`, or `evaluates` here — method composition (`child --part_of--> parent`, a Component into its Contribution) and variant contrasts (`compares_to`) are established by the global **relation pass** over the full node set and are already in the `relations` you were given.

# Mental Sandbox / Worked Example

{
  "section": {
    "section_type": "method",
    "anchor_id": "con:proposed_model",
    "contributions": [
      {
        "id": "con:proposed_model",
        "type": "Contribution",
        "kind": "method",
        "name": "ProposedNet",
        "method_kind": "model_architecture",
        "description": "An encoder-decoder architecture using stacked self-attention layers with residual connections.",
        "inputs": ["token embeddings", "positional encodings"],
        "outputs": ["output probability distribution"],
        "formulas": [
          {
            "name": "Training Objective",
            "expression": "L = -sum_t log P(y_t | y_<t, x)",
            "role": "objective",
            "description": "Token-level cross-entropy with label smoothing over the target sequence."
          }
        ],
        "implementation_notes": "Trained with label smoothing (ε=0.1) using 8 GPUs.",
        "provenance": ["§5"]
      }
    ],
    "components": [
      {
        "id": "cmp:attention_mechanism",
        "type": "Component",
        "name": "Multi-Head Attention",
        "method_kind": "algorithm",
        "description": "Projects queries, keys, and values into h subspaces, applies scaled dot-product attention in parallel, and concatenates results.",
        "inputs": ["queries", "keys", "values"],
        "outputs": ["context vectors"],
        "formulas": [
          {
            "name": "Scaled Dot-Product Attention",
            "expression": "Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V"
          }
        ],
        "implementation_notes": "",
        "provenance": ["§5", "§6"]
      }
    ]
  }
}

**Key lesson:** the parent carries the **objective** (cross-entropy) as a tagged `formulas` entry; the Component carries its own **defining equation** (scaled dot-product attention) with no `role`. And `cmp:attention_mechanism --part_of--> con:proposed_model` is **NOT** emitted here — it already lives in the global `relations` from the relation pass.

# Anchor
`anchor_id` must be the **primary method Contribution** id — the census `root`. When the census tagged co-equal roots, anchor on the one the paper's **title/abstract** centers on.

# Anti-Patterns
Do **NOT**:
- add a fresh Contribution (any newly introduced unit is a `cmp:` Component);
- materialize dataset, benchmark, or `finding` Contributions here;
- create `Measure` or `ExperimentSetup` units, or represent method inputs as ExperimentSetups;
- invent `inputs` / `outputs` / `formulas`, or fabricate `implementation_notes`;
- duplicate a component's objective in the parent (the parent carries only the combined objective);
- use `kind: theory`, or a unit-level `role` field;
- emit method `relations`.

# Final Completeness Check
Before closing the JSON, verify:
1. every `Contribution` registry node with `kind: method` appears in `contributions[]`;
2. every `Component` registry node appears in `components[]`;
3. no fresh Contribution was created;
4. any fresh unit is a `cmp:` Component;
5. no dataset, benchmark, finding, Measure, or ExperimentSetup unit appears here;
6. no `relations` field exists;
7. every stated defining equation is captured once, on the correct unit;
8. every stated loss/objective is captured as a `role: "objective"` formula;
9. static / formal units omit fabricated `inputs` / `outputs` / `formulas`;
10. `anchor_id` points to the primary method Contribution.
