SECTION FOCUS: method

This section captures the technical apparatus the paper introduces or applies: algorithms, model architectures, training strategies, and objectives. The method section justifies the claim by showing how it was realized.

This section **materializes the Method census nodes**: for each `Method` node in `node_registry`, emit a Method unit reusing its `node_id` verbatim as the unit `id` and its `role` verbatim from the registry, and fill the rich fields below. You may also add a Method the census missed (fresh `mth:` id). This section authors no relations — composition (`part_of`) and variant contrasts (`compares_to`) between methods are already in the global `relations`, established by the relation pass.

## Units you may define

Only `Method` units (array `methods`). Typical: the primary Method, its major component methods, and every comparison baseline the census listed (`compared_against`). The baseline systems make the unit count higher than the contribution's own parts alone.

### Method
Required fields: `role`, `name`, `description`. Optional fields (include only when the paper supports them; omit otherwise): `method_kind`, `inputs`, `outputs`, `formulas`, `objective_function`, `implementation_notes`. Fill `implementation_notes` for an algorithmic method (it is the reproducibility nudge — use `""` only when the paper truly states nothing); omit it for a non-implementation `theorem`/`lemma`/`bound`/`definition`/`resource`/`taxonomy` unit rather than inventing detail.
- `role`: the method's argumentative function — one of `contribution | component | builds_on | compared_against`. Copy it verbatim from the node's `role` in `node_registry` (it is authoritative; do not re-decide it). At most one Method here is the `contribution`; a paper whose deliverable is a dataset/benchmark has its root as a `contribution_resource` ExperimentSetup in the evidence section instead, so this section may legitimately have no `contribution` Method.
- `method_kind` (optional): one of `algorithm | model_architecture | training_strategy | objective_function | resource | taxonomy | theorem | lemma | bound | definition`. This is a structural descriptor, orthogonal to `role`; omit it when the kind is unclear rather than guessing. Use `training_strategy` for a training *process* (schedule, curriculum, optimization procedure); reserve `objective_function` for a method whose own contribution *is* a loss/objective. A method merely *having* a loss does not make it `objective_function` — see the routing rule under `objective_function` below. Use `algorithm` for a procedure, protocol, or software system that is not itself an architecture. Use `resource` for a non-algorithmic deliverable that is the contribution but is neither a dataset/benchmark nor an algorithm (a released software library, an atlas, a model collection), and `taxonomy` for a classification scheme / survey taxonomy that is the contribution. Use `theorem` / `lemma` / `bound` for a **formal statement** the paper states and proves (a theorem, a lemma, an established complexity/sample/regret bound) and `definition` for a formal construct it introduces. **When `method_kind` is `resource`, `taxonomy`, `theorem`, `lemma`, `bound`, or `definition` the unit is not an algorithm: omit `inputs`, `outputs`, `formulas`, and `objective_function`** (they describe computation it does not perform — do not fabricate I/O for a static statement) and put the statement and proof strategy in `description`. For these non-implementation kinds `implementation_notes` is optional — omit it rather than inventing reproducibility detail. The **proven result** itself (what the theorem establishes) is a `Finding` with role `theorem`/`lemma`/`bound` in the evidence section; the theorem-Method `supports` that finding.
- `name`: match how the paper refers to the method (the exact system or algorithm name).
- `inputs` / `outputs` (optional): what flows into or out of the method, even if stated informally ("takes queries, keys, and values" → `inputs: ["queries", "keys", "values"]`). Omit the field entirely when the paper does not state it — do not invent inputs or outputs.
- `formulas` (optional but high-value): the method's defining equations, each as `{ "name": <short label>, "expression": <LaTeX or plain text>, "symbols": [ { "symbol": <token>, "description": <meaning> } ] }`. **Whenever the paper writes out a displayed/numbered equation that states how the method computes its result — an attention or scoring formula, a layer transform, a recurrence, a residual mapping, a loss term — capture it. Do not leave the field empty when such an equation appears in the text.** Transcribe the expression faithfully and completely, e.g. `Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V`. In `symbols`, define every symbol and variable that appears in the expression — operands, subscripts, and dimensions alike (e.g. `Q` → "query matrix", `d_k` → "dimension of the keys") — using the meaning the paper gives; use an empty array only when the expression introduces no symbols to define. Capture every distinct defining equation, not just one. Skip only incidental algebra or dimension bookkeeping. For a comparison baseline, materialize the Method unit but **omit `formulas` unless the paper actually writes out the baseline's equation** — do not reconstruct it. Omit the field entirely only when the method genuinely states no equation.
- `objective_function` (optional): the loss or optimization objective the method minimizes/maximizes, as `{ "expression": <LaTeX or plain text>, "description": <what it optimizes>, "symbols": [ { "symbol": <token>, "description": <meaning> } ] }`. Use it for the training/optimization target; leave `description` an empty string if only the formula is given, and fill `symbols` for the tokens in `expression` exactly as you would for `formulas` (empty array when it introduces none). Omit the field when the method defines no objective. **Only emit on `role: contribution` or `role: component`** — and only when the paper explicitly states the optimization target. For `compared_against` baselines, omit entirely; do not reconstruct it from general knowledge of the system.
  - Routing rule (do not represent one objective three ways): ① a method's loss/optimization target → put it in **that Method's `objective_function` field**; do not spin up a separate unit for it. ② a training *process* (schedule, curriculum, warmup) → a Method with `method_kind: training_strategy`. ③ reserve `method_kind: objective_function` for the rare case where a loss itself is the paper's contribution and stands as its own Method.
- `implementation_notes`: caveats, software choices, or configuration details affecting reproducibility. Boundary conditions and operational constraints go here or in `description`, not as separate units.

## Relations

This section authors no relations and its schema has no `relations` field. Method composition (`child --part_of--> parent`) and variant contrasts (`compares_to`) are established by the relation pass over the full node set, so do not try to express them here — they are already in the global `relations` you were given. There is no `components` field; do not add one.

## Extraction focus

- Materialize every `Method` node from `node_registry`; each becomes one Method unit reusing its `node_id`.
- A dataset/benchmark that is the paper's **own deliverable** is not a Method — it is a `contribution_resource` ExperimentSetup materialized in the evidence section. Do not re-materialize it here.
- Named entities (datasets, libraries, models) used as method inputs belong in the `description` field, not as separate ExperimentSetup units.
- For a theorem/lemma/bound the paper states and proves, materialize it as a Method with `method_kind: theorem` (or `lemma`/`bound`), `description` giving the statement and proof strategy, and no fabricated `inputs`/`outputs`/`formulas`. The proven result is a `Finding` (role `theorem`/`lemma`/`bound`) in evidence; the theorem-Method `supports` it. A formal definition the paper introduces is `method_kind: definition`.

## Anti-patterns

- **Materialize a Method unit for every comparison baseline** the census listed (`compared_against`) — including black-box systems cited only for a score comparison. For a baseline, emit **only** these fields: `role`, `name`, optionally `method_kind`, a one-line `description` of what the system is (from how the paper describes it), and `implementation_notes: ""`. **Do not emit** `inputs`, `outputs`, `formulas`, or `objective_function` — even if the paper writes them out, that detail belongs to the baseline's own paper, not here. The baseline unit is a structural anchor for the `compares_to` edge and the score-row `system_id`; its number is the only quantitative information that matters, and it lives in `scores[]`.
- Do not place Measure units here for method performance; measures belong in the evidence section.
- Do not add a `components` field or any `part_of`/`compares_to` edge — structural edges are global and already established.

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
        "objective_function": {
          "expression": "L = -sum_t log P(y_t | y_<t, x)",
          "description": "Token-level cross-entropy with label smoothing over the target sequence.",
          "symbols": [
            {"symbol": "L", "description": "training loss to minimize"},
            {"symbol": "y_t", "description": "target token at position t"},
            {"symbol": "y_<t", "description": "target tokens preceding position t"},
            {"symbol": "x", "description": "source input sequence"}
          ]
        },
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
            "expression": "Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V",
            "symbols": [
              {"symbol": "Q", "description": "query matrix"},
              {"symbol": "K", "description": "key matrix"},
              {"symbol": "V", "description": "value matrix"},
              {"symbol": "d_k", "description": "dimension of the keys, used to scale the dot products"}
            ]
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

`anchor_id` must be the primary Method unit — the one corresponding to the main technical contribution (the census `root` method).
