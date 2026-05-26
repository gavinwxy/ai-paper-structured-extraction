SECTION FOCUS: method

This section captures the technical apparatus the paper introduces or applies: algorithms, model architectures, training strategies, and objectives. The method section justifies the claim by showing how it was realized.

This section **materializes the Method census nodes**: for each `Method` node in `node_registry`, emit a Method unit reusing its `node_id` verbatim as the unit `id`, and fill the rich fields below. You may also add a Method the census missed (fresh `mth:` id). This section authors no relations — composition (`part_of`) and variant contrasts (`compares_to`) between methods are already in the global `relations`, established by the relation pass.

## Units you may define

Only `Method` units (array `methods`). Typical: the primary Method, its major component methods, and every comparison baseline the census listed (`compared_against`). The baseline systems make the unit count higher than the contribution's own parts alone.

### Method
Required fields: `name`, `method_kind`, `description`, `implementation_notes`. Optional fields (include only when the paper supports them; omit otherwise): `inputs`, `outputs`, `formulas`, `objective_function`.
- `method_kind`: one of `algorithm | model_architecture | training_strategy | objective_function`. Use `training_strategy` for a training *process* (schedule, curriculum, optimization procedure); reserve `objective_function` for a method whose own contribution *is* a loss/objective. A method merely *having* a loss does not make it `objective_function` — see the routing rule under `objective_function` below. Use `algorithm` for a procedure, protocol, or software system that is not itself an architecture.
- `name`: match how the paper refers to the method (the exact system or algorithm name).
- `inputs` / `outputs` (optional): what flows into or out of the method, even if stated informally ("takes queries, keys, and values" → `inputs: ["queries", "keys", "values"]`). Omit the field entirely when the paper does not state it — do not invent inputs or outputs.
- `formulas` (optional but high-value): the method's defining equations, each as `{ "name": <short label>, "expression": <LaTeX or plain text>, "symbols": [ { "symbol": <token>, "description": <meaning> } ] }`. **Whenever the paper writes out a displayed/numbered equation that states how the method computes its result — an attention or scoring formula, a layer transform, a recurrence, a residual mapping, a loss term — capture it. Do not leave the field empty when such an equation appears in the text.** Transcribe the expression faithfully and completely, e.g. `Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V`. In `symbols`, define every symbol and variable that appears in the expression — operands, subscripts, and dimensions alike (e.g. `Q` → "query matrix", `d_k` → "dimension of the keys") — using the meaning the paper gives; use an empty array only when the expression introduces no symbols to define. Capture every distinct defining equation, not just one. Skip only incidental algebra or dimension bookkeeping. For a comparison baseline, materialize the Method unit but **omit `formulas` unless the paper actually writes out the baseline's equation** — do not reconstruct it. Omit the field entirely only when the method genuinely states no equation.
- `objective_function` (optional): the loss or optimization objective the method minimizes/maximizes, as `{ "expression": <LaTeX or plain text>, "description": <what it optimizes>, "symbols": [ { "symbol": <token>, "description": <meaning> } ] }`. Use it for the training/optimization target; leave `description` an empty string if only the formula is given, and fill `symbols` for the tokens in `expression` exactly as you would for `formulas` (empty array when it introduces none). Omit the field when the method defines no objective.
  - Routing rule (do not represent one objective three ways): ① a method's loss/optimization target → put it in **that Method's `objective_function` field**; do not spin up a separate unit for it. ② a training *process* (schedule, curriculum, warmup) → a Method with `method_kind: training_strategy`. ③ reserve `method_kind: objective_function` for the rare case where a loss itself is the paper's contribution and stands as its own Method.
- `implementation_notes`: caveats, software choices, or configuration details affecting reproducibility. Boundary conditions and operational constraints go here or in `description`, not as separate units.

## Relations

This section authors no relations and its schema has no `relations` field. Method composition (`child --part_of--> parent`) and variant contrasts (`compares_to`) are established by the relation pass over the full node set, so do not try to express them here — they are already in the global `relations` you were given. There is no `components` field; do not add one.

## Extraction focus

- Materialize every `Method` node from `node_registry`; each becomes one Method unit reusing its `node_id`.
- Named entities (datasets, libraries, models) used as method inputs belong in the `description` field, not as separate Entity units.
- For proofs: use `method_kind: algorithm` with a description naming the proof strategy.

## Anti-patterns

- **Materialize a Method unit for every comparison baseline** the census listed (`compared_against`) — including black-box systems cited only for a score comparison. Keep these **lightweight**: `name`, the best-fit `method_kind`, and a one-line `description` of what the system is (from how the paper describes it); leave `implementation_notes` an empty string and omit `formulas`/`inputs`/`outputs`/`objective_function` unless the paper actually details them. **Never invent technical detail for a baseline.** These units exist so the `compares_to` edges resolve and the baseline's score row in the evidence section has a system to name.
- Give richer fields only to baselines the authors reconstruct, modify, or extend in detail ("we build upon ResNet by…").
- Do not place Metric units here for method performance; metrics belong in the evidence section.
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
        "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
      },
      {
        "id": "mth:attention_mechanism",
        "type": "Method",
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
        "provenance": [{"source_kind": "sentence", "source": ["§5", "§6"]}]
      }
    ]
  }
}

Here `mth:attention_mechanism --part_of--> mth:proposed_model` is **not** emitted in this section; it already lives in the global `relations` from the relation pass.

## Anchor

`anchor_id` must be the primary Method unit — the one corresponding to the main technical contribution (the census `root` method).
