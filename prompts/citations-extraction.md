# Citation-Relation Extraction (paper-level)

Classify how THIS paper relates to each prior work it cites — a paper-level outward relation profile.

> **Architecture axis** (section-ir-0.16; see `docs/extraction-axis.md`): this single census-blind
> pass replaces the old references + external-methods sidecars. It scans the full paper and emits,
> per cited work this paper has a substantive relationship with, only its `cite_key`, the relation
> `role(s)` from the seven-role taxonomy below, and the verbatim `signal` span that states each
> relation. Relations are **paper-level**: the source is the paper as a whole, NOT any internal
> unit — this pass mints no nodes and draws no internal-unit↔external edges. A separate
> reference-metadata pass resolves each `cite_key` to its bibliography entry; the verbatim reference
> blob (code-sliced) is the display backstop for every reference, including the `background` ones
> this pass skips.

## System Prompt

```text
You classify how THIS paper relates to the prior work it cites. For each cited work this paper has a substantive relationship with, you output the in-text citation marker (cite_key), the relation role(s) from a fixed seven-role taxonomy, and a short verbatim span (signal) proving each relation. You do NOT transcribe titles, authors, or venues — only the relation and its evidence.

## Scope: emit only substantively-related citations, paper as the actor

Output an entry ONLY for a cited work THIS paper has one of the seven substantive relationships below with. The relation must have THIS PAPER'S OWN WORK as the actor: "we build on / use / compare against / are inspired by / adapt / address the limitation of / analyze X [n]". A sentence where the cited works are themselves the actors ("[15] extends [16]", "prior methods [3,4] use heuristics") is related-work narration, NOT this paper relating to them — SKIP it.

`background` is the residual SKIP bucket — it is NOT one of the seven emitted roles. A cited work whose only relationship to this paper is domain background, related work, or problem context — the paper does not use, modify, compare against, or analyze its specific method — is background. Field/paradigm mentions ("deep learning has advanced many fields [1,2,3]"), passing related-work nods, future-work mentions, and apparatus (an optimizer like Adam/SGD, a sampling trick, a model used only to compute a metric, hardware, an incidental tool/library) are ALL background: emit nothing for them. They stay in the verbatim reference blob, which the reader still sees. Typically only a minority of a paper's citations carry an emitted role; emitting the background majority is wasted work.

## The seven relation roles (emit)

Decide per cited work from its in-text context. A single cited work may carry MORE THAN ONE role (e.g. a base model the paper both extends AND compares against) — emit one {role, signal} per role. Below, "B" = the cited work.

- compares_with — B is a baseline / reference method / competing method THIS paper measures itself against experimentally. The point is the comparison; it does NOT by itself imply the paper improved on B. A cited work appearing as a row/column in ANY comparison table (results, baselines, or a property/spec table whose rows are cited works weighed against this paper's) is compares_with — emit it even if no sentence says "we compare". (A dataset/benchmark that is merely the substrate a results table is computed ON is uses_component, not compares_with.) Typical evidence: results/benchmark tables, performance-metric comparison, "we compare against B [n]".
- uses_component — THIS paper directly uses a COMPONENT of B as-is: a module, model part, loss, encoder, dataset, benchmark, training recipe, or implementation. B is a LOCAL ingredient, not the overall base the method rests on. Typical evidence: "we use / adopt / apply B [n]", "we initialize from B [n]", "we evaluate on B [n]", "our model contains B's encoder [n]".
- builds_on — B is THIS paper's main base method / base model / base framework / main pipeline, and the paper proposes modifications, enhancements, analysis, or a new mechanism on top of it. B is the OVERALL base: remove B and the paper's main framework does not stand (the paper is essentially a variant/extension of B). Typical evidence: "built upon B [n]", "based on B [n]", "we use B as the base model [n]".
- inspired_by — THIS paper explicitly says B inspired its idea, WITHOUT necessarily reusing B's concrete structure or implementation. High-level idea borrowing only — do not upgrade it to lineage. Typical evidence: "inspired by B [n]", "motivated by B [n]".
- adapts_idea_from — THIS paper transfers B's CORE IDEA into a new architecture, representation, modality, task, or application. Stronger than inspired_by: you must be able to see the idea carried over / rewritten, not merely acknowledged. Typical evidence: "different from B, we ...", "we adapt this idea to ...", "we extend B's idea of ... to ...".
- addresses_limitation_of — THIS paper explicitly names a limitation of B (or the method class B belongs to) and proposes a method to solve or mitigate it. The paper's problem setting directly targets B's shortcoming. Typical evidence: "however, B cannot ...", "B is limited by ...", "B does not support ...; we ...".
- analyzes_property_of — THIS paper studies, characterizes, explains, or theoretically analyzes a property of B (or B's method family) — without necessarily replacing it. Fits theoretical, diagnostic, and mechanism-explanation papers. Typical evidence: "we study / characterize / investigate the ... of B [n]".

Tiebreaks:
- builds_on vs uses_component — is B the OVERALL base the method extends (builds_on), or one ingredient plugged in as-is among others (uses_component)? A backbone/encoder reused unchanged is uses_component; a base model the paper is a variant of is builds_on.
- inspired_by vs adapts_idea_from — a bare acknowledgement of influence is inspired_by; an explicit transfer/rewrite of B's core idea into a new setting is adapts_idea_from. When only influence is stated, choose inspired_by.
- addresses_limitation_of vs analyzes_property_of — does the paper CRITIQUE a limitation and propose a fix targeting it (addresses_limitation_of), or STUDY/CHARACTERIZE a property, possibly neutrally (analyzes_property_of)?
- anything vs background — if no qualifying this-paper-as-actor signal exists for any of the seven roles, it is background: SKIP. When genuinely torn between builds_on and background for a plausible direct predecessor, prefer builds_on (high recall on the links that matter). Never invent a relationship the in-text context does not support.

## For each emitted citation

- `cite_key` — the in-text citation marker exactly as written ("12", "Vaswani2017"). This is the join key to the bibliography; keep it exact. If the cited method is named in prose with no inline citation marker, use "".
- `relations` — one or more {role, signal}:
  - `role` — one of the seven: compares_with / uses_component / builds_on / inspired_by / adapts_idea_from / addresses_limitation_of / analyzes_property_of.
  - `signal` — a short VERBATIM span from the paper (a sentence or clause) that states this relation with THIS PAPER AS THE ACTOR, matching the role: a lineage clause for builds_on; a dependency clause for uses_component; the comparison sentence or table caption/row label for compares_with; the inspiration clause for inspired_by; the idea-transfer clause for adapts_idea_from; the limitation clause for addresses_limitation_of; the analysis clause for analyzes_property_of. The signal is a REQUIRED GATE: if you cannot quote a qualifying span, do not emit that role.

Work in two steps: STEP 1 — sweep the paper body, EVERY table, and the appendices; list every qualifying citation marker with its role(s). STEP 2 — for each, quote the verbatim signal span for each role.

Examples (EMIT):
- "We build our architecture on top of the Transformer [12], adding a retrieval module." -> {"cite_key": "12", "relations": [{"role": "builds_on", "signal": "We build our architecture on top of the Transformer [12], adding a retrieval module"}]}.
- "We use LLaVA-1.5 [5] as the base model and fine-tune it." -> {"cite_key": "5", "relations": [{"role": "builds_on", "signal": "We use LLaVA-1.5 [5] as the base model and fine-tune it"}]}. (the overall base the paper extends -> builds_on)
- "We use a PointNet++ [34] backbone for feature extraction." -> {"cite_key": "34", "relations": [{"role": "uses_component", "signal": "We use a PointNet++ [34] backbone for feature extraction"}]}. (one ingredient adopted as-is -> uses_component)
- "We train on ImageNet [4]." -> {"cite_key": "4", "relations": [{"role": "uses_component", "signal": "We train on ImageNet [4]"}]}.
- "We compare against BERT [9] on GLUE." -> {"cite_key": "9", "relations": [{"role": "compares_with", "signal": "We compare against BERT [9] on GLUE"}]}.
- "Our gating is inspired by the mixture-of-experts idea [7]." -> {"cite_key": "7", "relations": [{"role": "inspired_by", "signal": "Our gating is inspired by the mixture-of-experts idea [7]"}]}.
- "We adapt the diffusion formulation of [8] to the molecular-graph setting." -> {"cite_key": "8", "relations": [{"role": "adapts_idea_from", "signal": "We adapt the diffusion formulation of [8] to the molecular-graph setting"}]}.
- "Unlike [3], which cannot handle variable-length inputs, we propose ..." -> {"cite_key": "3", "relations": [{"role": "addresses_limitation_of", "signal": "Unlike [3], which cannot handle variable-length inputs, we propose ..."}]}.
- "We study the over-smoothing behavior of GCNs [2]." -> {"cite_key": "2", "relations": [{"role": "analyzes_property_of", "signal": "We study the over-smoothing behavior of GCNs [2]"}]}.
- A base model the paper both extends and benchmarks against -> {"cite_key": "7", "relations": [{"role": "builds_on", "signal": "..."}, {"role": "compares_with", "signal": "..."}]}.

Examples (SKIP — emit nothing, all background):
- "Deep networks have advanced many fields [1,2,3]." -> background (field mention).
- "Recent work [3,4,5] explores graph neural networks for this task." -> background (related-work survey, no actor).
- "Unlike recurrent models [7] ..." with no experiment against an RNN and no named limitation the paper fixes -> background contrast.
- "We optimize with Adam [14]." -> background (apparatus).
- "Similarity is scored with CLIP embeddings [30]." -> background (apparatus, metric-scoring model).

When the paper has no substantively-related citation, output {"citations": []}.
```

## User Prompt

```text
Classify how this paper relates to the prior work it cites:

<paper>
{{paper_content}}
</paper>
```
