SECTION FOCUS: method

This section captures the technical apparatus the paper introduces or applies: algorithms, model architectures, training strategies, and objectives. The method section justifies the claim by showing how it was realized.

This section **materializes the method-section census nodes**: for each `Contribution` node (kind `method`/`theory`) in `node_registry`, emit a Contribution unit reusing its `node_id` verbatim as the unit `id` and its `kind` verbatim from the registry; for each `Component` node, emit a Component unit reusing its `node_id` verbatim. Fill the rich fields below. You may also add a unit the census missed (fresh `con:` id for a contribution, `cmp:` id for a component).

## Units you may define

`Contribution` units (array `contributions`) and `Component` units (array `components`). Typical: the primary Contribution and its major Components. (The census is internal-only — it lists no external baselines, so there are none to materialize here; the paper's comparisons to prior art live in the citation layer.)

A `Contribution` is the root deliverable the paper introduces; a `Component` is a sub-module that is `part_of` a Contribution (single-level — a Component never decomposes into further Components here). A dataset/benchmark deliverable is a `Contribution` (kind `dataset`/`benchmark`) materialized in the evidence section, not here; a `finding`-kind Contribution (an analysis paper's result) is likewise born in the evidence section. So this section materializes the `method`/`theory`-kind Contributions and the Components.

### Contribution
Fill `implementation_notes` for an algorithmic contribution (it is the reproducibility nudge — use `""` only when the paper truly states nothing); omit it for a non-implementation `theorem`/`lemma`/`bound`/`definition`/`resource`/`taxonomy` unit rather than inventing detail.
- `kind` (required): the contribution's category — for a method-section unit one of `method | theory`. Copy it verbatim from the node's `kind` in `node_registry` (it is authoritative; do not re-decide it). Use `theory` when the deliverable is a proven formal result (a theorem, lemma, or bound the paper itself proves); use `method` otherwise (an algorithm, architecture, training strategy, released artifact, or taxonomy). Usually exactly one Contribution is the root; when the census tagged co-equal roots (linked by `co_contribution`), materialize each — never demote one. A unit you add fresh is a Component, never a Contribution.
- `method_kind` (optional): a finer structural sub-tag — one of `algorithm | model_architecture | training_strategy | objective_function | resource | taxonomy | theorem | lemma | bound | definition`. It refines `kind`; omit it when the sub-kind is unclear rather than guessing. Use `training_strategy` for a training *process* (schedule, curriculum, optimization procedure); reserve `objective_function` for a contribution whose own deliverable *is* a loss/objective. A method merely *having* a loss does not make it `objective_function` — see the routing rule under `formulas` below. Use `algorithm` for a procedure or protocol the paper describes executing (steps, pseudo-code, a pipeline, complexity analysis); use `resource` only when the deliverable is presented as a released artifact (a software library, an atlas, a model collection) and the paper describes what it contains or provides rather than a procedure of its own. Use `taxonomy` for a classification scheme / survey taxonomy that is the contribution. A `theorem`/`lemma`/`bound`/`definition` sub-tag belongs on a `kind: theory` Contribution — a **formal statement** the paper states and proves (a theorem, a lemma, a complexity/sample/regret bound the paper itself proves), or a formal construct it introduces (`definition`). **When `method_kind` is `resource`, `taxonomy`, `theorem`, `lemma`, `bound`, or `definition` the unit is not an algorithm: omit `inputs`, `outputs`, and `formulas`** (they describe computation it does not perform — do not fabricate I/O for a static statement) and put the statement and proof strategy in `description`. For these non-implementation sub-kinds `implementation_notes` is optional — omit it rather than inventing reproducibility detail. The **proven result** itself (what the theorem establishes) is a `Finding` with kind `theorem`/`lemma`/`bound` in the evidence section; the theory Contribution `supports` that finding.
- `name`: match how the paper refers to the contribution (the exact system or algorithm name).
- `inputs` / `outputs` (optional): what flows into or out of the contribution, even if stated informally ("takes queries, keys, and values" → `inputs: ["queries", "keys", "values"]`). Do not invent inputs or outputs.
- `formulas` (optional but high-value): the contribution's defining equations, each as `{ "name": <short label>, "expression": <LaTeX or plain text> }`. **Whenever the paper writes out a displayed/numbered equation that states how the method computes its result — an attention or scoring formula, a layer transform, a recurrence, a residual mapping, a loss term — capture it. Do not leave the field empty when such an equation appears in the text.** Transcribe the expression faithfully and completely, e.g. `Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V`. Capture every distinct defining equation, not just one. **Do not transcribe a symbol-by-symbol glossary** — the expression and the unit's `description` carry the meaning; just give the equation and a short `name`. Skip only incidental algebra or dimension bookkeeping.
  - **Objective tag — actively hunt for the training objective.** For every Contribution and Component, check whether the paper states the loss or optimization objective it minimizes/maximizes — it is often stated briefly, in a training-details paragraph rather than the core exposition, and is often a standard loss (cross-entropy, `L1 + λ·L_SSIM`, MSE). **When stated, transcribe it — even a one-line standard loss — as a formulas entry tagged `"role": "objective"`** with a one-line `description` of what it optimizes: `{ "name": ..., "expression": ..., "role": "objective", "description": <what it optimizes> }`. A missing objective must mean the paper states none, not that it was overlooked. The converse also holds: transcribe only what the paper states — never reconstruct an objective from general knowledge of a system, and never tag a forward/inference/rendering equation as the objective just so the unit has one. `role` and `description` appear **only** on objective entries — every other formula carries just `name` + `expression`. A unit optimizing several stated objectives may tag each. (This `role` is the per-formula objective marker — it is the only `role` in this section; the unit itself has no `role` field.)
  - **Each equation appears once per unit, on the unit whose computation it defines.** The objective is a tagged entry in `formulas`, not a second copy of one. When a composite Contribution's objective combines component losses (`L = L^A + αL^R`), the parent carries only the combined objective; each component loss is the objective of its own Component unit — do not re-transcribe component losses in the parent's `formulas`. This parent↔component rule is the only cross-unit ban: **sibling systems or variants that each train with the same stated objective each carry it** — do not drop a stated training loss merely because another unit also states it.
  - Routing rule (do not represent one objective three ways): ① a unit's loss/optimization target → a `role: "objective"` entry in **that unit's `formulas`**; do not spin up a separate unit for it. ② a training *process* (schedule, curriculum, warmup) → a unit with `method_kind: training_strategy`. ③ reserve `method_kind: objective_function` for the rare case where a loss itself is the paper's contribution and stands as its own Contribution.
- `implementation_notes`: caveats, software choices, or configuration details affecting reproducibility. Boundary conditions and operational constraints go here or in `description`, not as separate units.

### Component
A sub-module that is `part_of` a Contribution. Same rich fields as a Contribution (`name`, `description`, optional `inputs`/`outputs`/`formulas`/`implementation_notes`, optional `method_kind`) **except it has no `kind`** — a Component is single-level and carries no required differentia. Its `method_kind` (optional) draws from the same vocabulary and follows the same field-suppression rule (a `theorem`/`lemma`/`bound`/`definition`/`resource`/`taxonomy` Component omits `inputs`/`outputs`/`formulas`). The objective-tag guidance above applies to Components too.

## Relations

This section authors no relations and its schema has no `relations` field. Method composition (`child --part_of--> parent`, i.e. a Component into its Contribution) and variant contrasts (`compares_to`) are established by the relation pass over the full node set, so do not try to express them here — they are already in the global `relations` you were given.

## Extraction focus

- A dataset/benchmark that is the paper's **own deliverable** is a `Contribution` (kind `dataset`/`benchmark`) materialized in the evidence section, not a method-section unit. Do not re-materialize it here.
- Named entities (datasets, libraries, models) used as method inputs belong in the `description` field, not as separate ExperimentSetup units.
- For a theorem/lemma/bound the paper states and proves, materialize it as a Contribution with `kind: theory` and `method_kind: theorem` (or `lemma`/`bound`), `description` giving the statement and proof strategy, and no fabricated `inputs`/`outputs`/`formulas`. The proven result is a `Finding` (kind `theorem`/`lemma`/`bound`) in evidence; the theory Contribution `supports` it. A formal definition the paper introduces is `method_kind: definition`.

## Anti-patterns

- Do not place Measure units here for method performance; measures belong in the evidence section.

## Worked example

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

Here `cmp:attention_mechanism --part_of--> con:proposed_model` is **not** emitted in this section; it already lives in the global `relations` from the relation pass.

## Anchor

`anchor_id` must be the primary Contribution unit — the one corresponding to the main technical contribution (the census `root`). When the census tagged co-equal roots, anchor on the one the paper's title/abstract centers on.
