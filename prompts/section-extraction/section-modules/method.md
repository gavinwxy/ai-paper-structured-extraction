SECTION FOCUS: method

This section captures the technical apparatus the paper introduces or applies: algorithms, model architectures, protocols, and software systems. The method section justifies the claim by showing how it was realized.

## Units you may define

Only `Method` units (array `methods`). Typical: 1–5 units — one primary Method for the main contribution system plus sub-methods for major components.

### Method
Required fields: `name`, `method_kind`, `description`, `implementation_notes`. Optional fields (include only when the paper supports them; omit otherwise): `inputs`, `outputs`, `formulas`, `objective_function`.
- `method_kind`: one of `algorithm | model_architecture | protocol | software_system | training_strategy | objective_function`. Use `training_strategy` for a training *process* (schedule, curriculum, optimization procedure); reserve `objective_function` for a method whose own contribution *is* a loss/objective. A method merely *having* a loss does not make it `objective_function` — see the routing rule under `objective_function` below.
- `name`: match how the paper refers to its main contribution (the exact system or algorithm name).
- `inputs` / `outputs` (optional): what flows into or out of the method, even if stated informally ("takes queries, keys, and values" → `inputs: ["queries", "keys", "values"]`). Omit the field entirely when the paper does not state it — do not invent inputs or outputs.
- `formulas` (optional but high-value): the method's defining equations, each as `{ "name": <short label>, "expression": <LaTeX or plain text>, "symbols": [ { "symbol": <token>, "description": <meaning> } ] }`. **Whenever the paper writes out a displayed/numbered equation that states how the method computes its result — an attention or scoring formula, a layer transform, a recurrence, a residual mapping, a loss term — capture it. Do not leave the field empty when such an equation appears in the text.** Transcribe the expression faithfully and completely, e.g. `Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V`. In `symbols`, define every symbol and variable that appears in the expression — operands, subscripts, and dimensions alike (e.g. `Q` → "query matrix", `d_k` → "dimension of the keys") — using the meaning the paper gives; use an empty array only when the expression introduces no symbols to define. Capture every distinct defining equation, not just one. Skip only incidental algebra, dimension bookkeeping, or equations that belong to a baseline you are not extracting. Omit the field entirely only when the method genuinely states no equation.
- `objective_function` (optional): the loss or optimization objective the method minimizes/maximizes, as `{ "expression": <LaTeX or plain text>, "description": <what it optimizes>, "symbols": [ { "symbol": <token>, "description": <meaning> } ] }`. Use it for the training/optimization target; leave `description` an empty string if only the formula is given, and fill `symbols` for the tokens in `expression` exactly as you would for `formulas` (empty array when it introduces none). Omit the field when the method defines no objective.
  - Routing rule (do not represent one objective three ways): ① a method's loss/optimization target → put it in **that Method's `objective_function` field**; do not spin up a separate unit for it. ② a training *process* (schedule, curriculum, warmup) → a Method with `method_kind: training_strategy`. ③ reserve `method_kind: objective_function` for the rare case where a loss itself is the paper's contribution and stands as its own Method.
- `implementation_notes`: caveats, software choices, or configuration details affecting reproducibility. Boundary conditions and operational constraints go here or in `description`, not as separate units.
- Express decomposition with a `part_of` link from each sub-method to the primary Method (`child --part_of--> parent`). This link is authoritative; assembly derives the component list from it. There is no component field to fill on the Method.

## Links

| relation | source | target | meaning |
|---|---|---|---|
| `part_of` | Method | Method | a child component belongs to a larger method |
| `compares_to` | Method | Method | two interchangeable method variants are contrasted |

Both ends of every link must be Methods defined in this section. This section emits no cross-section links; its relationship to the contribution claim is implicit in the section structure.

## Using plan relations

Plan item `relations` are hints, not mandates. Use them only when the paper text supports the relationship.

| plan relation | example | encode as |
|---|---|---|
| `part_of` | `mth:attention part_of mth:encoder_layer` | local link `mth:attention --part_of--> mth:encoder_layer` |
| `feeds` (used inside) | a sub-routine called within the main loop | local link `child --part_of--> parent` |
| `feeds` (separate stage) | `mth:encoder feeds mth:decoder` | name the encoder output in the decoder's `inputs`; no link |
| `alternative_to` | `mth:sinusoidal_pe alternative_to mth:learned_pe` | local link `mth:sinusoidal_pe --compares_to--> mth:learned_pe` |

The only judgment call is `feeds`: does A run *inside* B (→ `part_of` link) or *before* B as its own stage (→ B's `inputs`)? When unsure, prefer `inputs` and no link. If a relation points to a plan item outside this section, do not create a section-local link to it.

Dataflow between methods is **descriptive only** — it lives in the `inputs`/`outputs` strings, never as a reconstructable link. This section has exactly two structured link relations: `part_of` (composition) and `compares_to` (alternatives). There is no dataflow/`feeds` link; do not attempt to encode "A feeds B" as a link.

## Extraction focus

- Named entities (datasets, libraries, models) used as method inputs belong in the `description` field, not as separate Entity units.
- For proofs: use `method_kind: algorithm` with a description naming the proof strategy.

## Anti-patterns

- Do not create Method units for black-box comparison baselines cited only for score comparison. Baseline scores are not captured in the IR.
- Do create Method units for baselines the authors reconstruct, modify, or extend in detail ("we build upon ResNet by…").
- Do not create support-only units for why the method works; interpretation belongs in analysis.
- Do not place Metric units here for method performance; metrics belong in experiment.

## Worked example

{
  "section": {
    "section_type": "method",
    "anchor_id": "mth:proposed_model",
    "covers_entries": ["mth:proposed_model", "mth:attention_mechanism"],
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
          },
          {
            "name": "Multi-Head Attention",
            "expression": "MultiHead(Q,K,V)=Concat(head_1..head_h)W^O",
            "symbols": [
              {"symbol": "head_i", "description": "output of the i-th attention head"},
              {"symbol": "h", "description": "number of parallel attention heads"},
              {"symbol": "W^O", "description": "output projection matrix"}
            ]
          }
        ],
        "implementation_notes": "",
        "provenance": [{"source_kind": "sentence", "source": ["§5", "§6"]}]
      }
    ],
    "links": [
      {"source_id": "mth:attention_mechanism", "relation": "part_of", "target_id": "mth:proposed_model"}
    ]
  }
}

## Anchor

`anchor_id` must be the primary Method unit — the one corresponding to the main technical contribution.
