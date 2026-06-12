SECTION FOCUS: method

This section captures the technical apparatus the paper introduces or applies: algorithms, model architectures, training strategies, and objectives. The method section justifies the claim by showing how it was realized.

This section **materializes the Method census nodes**: for each `Method` node in `node_registry`, emit a Method unit reusing its `node_id` verbatim as the unit `id` and its `role` verbatim from the registry, and fill the rich fields below. You may also add a Method the census missed (fresh `mth:` id).

## Units you may define

Only `Method` units (array `methods`). Typical: the primary Method, its major component methods, and every comparison baseline the census listed (`compared_against`).

### Method
Fill `implementation_notes` for an algorithmic method (it is the reproducibility nudge — use `""` only when the paper truly states nothing); omit it for a non-implementation `theorem`/`lemma`/`bound`/`definition`/`resource`/`taxonomy` unit rather than inventing detail.
- `role`: the method's argumentative function — one of `contribution | component | builds_on | compared_against`. Copy it verbatim from the node's `role` in `node_registry` (it is authoritative; do not re-decide it). Usually exactly one Method is the `contribution`; when the census tagged co-equal `contribution` roots (linked by `co_contribution`), copy each role verbatim — never demote one. A Method you add fresh is never the `contribution`. A paper whose deliverable is a dataset/benchmark has its root as a `contribution_resource` ExperimentSetup in the evidence section instead, so this section may legitimately have no `contribution` Method.
- `method_kind` (optional): one of `algorithm | model_architecture | training_strategy | objective_function | resource | taxonomy | theorem | lemma | bound | definition`. This is a structural descriptor, orthogonal to `role`; omit it when the kind is unclear rather than guessing. Use `training_strategy` for a training *process* (schedule, curriculum, optimization procedure); reserve `objective_function` for a method whose own contribution *is* a loss/objective. A method merely *having* a loss does not make it `objective_function` — see the routing rule under `formulas` below. Use `algorithm` for a procedure or protocol the paper describes executing (steps, pseudo-code, a pipeline, complexity analysis); use `resource` only when the deliverable that is the contribution is presented as a released artifact (a software library, an atlas, a model collection) and the paper describes what it contains or provides rather than a procedure of its own. Use `taxonomy` for a classification scheme / survey taxonomy that is the contribution. Use `theorem` / `lemma` / `bound` for a **formal statement** the paper states and proves (a theorem, a lemma, a complexity/sample/regret bound the paper itself proves) and `definition` for a formal construct it introduces. **When `method_kind` is `resource`, `taxonomy`, `theorem`, `lemma`, `bound`, or `definition` the unit is not an algorithm: omit `inputs`, `outputs`, and `formulas`** (they describe computation it does not perform — do not fabricate I/O for a static statement) and put the statement and proof strategy in `description`. For these non-implementation kinds `implementation_notes` is optional — omit it rather than inventing reproducibility detail. The **proven result** itself (what the theorem establishes) is a `Finding` with role `theorem`/`lemma`/`bound` in the evidence section; the theorem-Method `supports` that finding.
- `name`: match how the paper refers to the method (the exact system or algorithm name).
- `inputs` / `outputs` (optional): what flows into or out of the method, even if stated informally ("takes queries, keys, and values" → `inputs: ["queries", "keys", "values"]`). Do not invent inputs or outputs.
- `formulas` (optional but high-value): the method's defining equations, each as `{ "name": <short label>, "expression": <LaTeX or plain text> }`. **Whenever the paper writes out a displayed/numbered equation that states how the method computes its result — an attention or scoring formula, a layer transform, a recurrence, a residual mapping, a loss term — capture it. Do not leave the field empty when such an equation appears in the text.** Transcribe the expression faithfully and completely, e.g. `Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V`. Capture every distinct defining equation, not just one. **Do not transcribe a symbol-by-symbol glossary** — the expression and the method's `description` carry the meaning; just give the equation and a short `name`. Skip only incidental algebra or dimension bookkeeping. For a `compared_against` baseline, omit `formulas` entirely.
  - **Objective tag — actively hunt for the training objective.** For every `contribution`/`component` method, check whether the paper states the loss or optimization objective it minimizes/maximizes — it is often stated briefly, in a training-details paragraph rather than the core exposition, and is often a standard loss (cross-entropy, `L1 + λ·L_SSIM`, MSE). **When stated, transcribe it — even a one-line standard loss — as a formulas entry tagged `"role": "objective"`** with a one-line `description` of what it optimizes: `{ "name": ..., "expression": ..., "role": "objective", "description": <what it optimizes> }`. A missing objective must mean the paper states none, not that it was overlooked. The converse also holds: transcribe only what the paper states — never reconstruct an objective from general knowledge of a system, and never tag a forward/inference/rendering equation as the objective just so the method has one. `role` and `description` appear **only** on objective entries — every other formula carries just `name` + `expression`. A method optimizing several stated objectives may tag each. Only a `role: contribution` or `role: component` Method may carry an objective-tagged formula (a `builds_on` method's stated equations stay untagged).
  - **Each equation appears once per unit, on the unit whose computation it defines.** The objective is a tagged entry in `formulas`, not a second copy of one. When a composite method's objective combines component losses (`L = L^A + αL^R`), the parent carries only the combined objective; each component loss is the objective of its own component Method unit — do not re-transcribe component losses in the parent's `formulas`. This parent↔component rule is the only cross-unit ban: **sibling systems or variants that each train with the same stated objective each carry it** — do not drop a stated training loss merely because another unit also states it.
  - Routing rule (do not represent one objective three ways): ① a method's loss/optimization target → a `role: "objective"` entry in **that Method's `formulas`**; do not spin up a separate unit for it. ② a training *process* (schedule, curriculum, warmup) → a Method with `method_kind: training_strategy`. ③ reserve `method_kind: objective_function` for the rare case where a loss itself is the paper's contribution and stands as its own Method.
- `implementation_notes`: caveats, software choices, or configuration details affecting reproducibility. Boundary conditions and operational constraints go here or in `description`, not as separate units.

## Relations

This section authors no relations and its schema has no `relations` field. Method composition (`child --part_of--> parent`) and variant contrasts (`compares_to`) are established by the relation pass over the full node set, so do not try to express them here — they are already in the global `relations` you were given. There is no `components` field; do not add one.

## Extraction focus

- A dataset/benchmark that is the paper's **own deliverable** is not a Method — it is a `contribution_resource` ExperimentSetup materialized in the evidence section. Do not re-materialize it here.
- Named entities (datasets, libraries, models) used as method inputs belong in the `description` field, not as separate ExperimentSetup units.
- For a theorem/lemma/bound the paper states and proves, materialize it as a Method with `method_kind: theorem` (or `lemma`/`bound`), `description` giving the statement and proof strategy, and no fabricated `inputs`/`outputs`/`formulas`. The proven result is a `Finding` (role `theorem`/`lemma`/`bound`) in evidence; the theorem-Method `supports` it. A formal definition the paper introduces is `method_kind: definition`.

## Baselines (`compared_against`)

**Materialize a Method unit for every comparison baseline** the census listed (`compared_against`) — including black-box systems cited only for a score comparison. For a baseline, emit **only** these fields: `role`, `name`, optionally `method_kind`, a one-line `description` of what the system is (from how the paper describes it), and `implementation_notes: ""`. **Do not emit** `inputs`, `outputs`, or `formulas` — even if the paper writes them out, that detail belongs to the baseline's own paper, not here. The baseline unit is a structural anchor for the `compares_to` edge and the score-row `system_id`; its number is the only quantitative information that matters, and it is preserved by the evidence stage (in the verbatim source table, or as a score row).

## Anti-patterns

- Do not place Measure units here for method performance; measures belong in the evidence section.

## Worked example

{
  "section": {
    "section_type": "method",
    "anchor_id": "mth:proposed_model",
    "methods": [
      {
        "id": "mth:proposed_model",
        "type": "Method",
        "role": "contribution",
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
      },
      {
        "id": "mth:attention_mechanism",
        "type": "Method",
        "role": "component",
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

Here `mth:attention_mechanism --part_of--> mth:proposed_model` is **not** emitted in this section; it already lives in the global `relations` from the relation pass.

## Anchor

`anchor_id` must be the primary Method unit — the one corresponding to the main technical contribution (the census `root` method). When the census tagged co-equal `contribution` roots, anchor on the one the paper's title/abstract centers on.
