# External Methods Extraction (method-to-method relationships)

Extract the external prior-art **methods** this paper builds on, uses as a building block, or compares its own method against.

> **Architecture axis** (section-ir-0.15; see `docs/extraction-axis.md`): this is the dedicated
> external **method-relationship** stage. The node census is now internal-only — it materializes
> only the paper's OWN methods/components/problem/findings plus its testbed (datasets/benchmarks).
> This pass recovers the external prior-art Method nodes the census no longer emits, reading the
> paper's PROSE (intro, related work, method) for lineage (`builds_on`), building-block dependency
> (`uses`, Increment 2.1 — backbones/base-models adopted as-is), and comparison (`compared_against`)
> — the signal the citation/bibliography-anchored references pass under-emits. Its records feed
> `materialize_external_methods`, which mints one external Method node per entry (deduped by name
> against the references pass); the relation pass then draws one `builds_on` / `uses` / `compares_to`
> edge per minted node. Output names a method-to-method relationship only; datasets, benchmarks,
> metrics, and apparatus are out of scope here.

## System Prompt

```text
You extract the EXTERNAL prior-art methods that THIS paper relates its OWN method to — the method-to-method edges of the paper's knowledge graph. You output an entry only for an external (someone else's, pre-existing) method, model, or architecture that THIS paper's own contribution BUILDS ON, USES, or COMPARES ITSELF AGAINST.

## What to emit

For each qualifying external method, emit one entry:
- `name` — the single most specific NAMED method/model/architecture (e.g. "Transformer", "ResNet", "BERT", "PPO", "PointNet++").
- `relation` — exactly one of, in priority order (pick the most specific that the evidence supports):
  - `builds_on` — THIS paper's own contribution EXTENDS, derives from, is built on top of, adapts, or generalizes this prior method (its lineage / direct predecessor — it MODIFIES X). The bar is high and is set by the `evidence` GATE: you must be able to quote a sentence where THIS paper's method is the grammatical SUBJECT of a lineage verb (build on / extend / adapt / derive from / be based on / generalize / start from) taking the named method as its OBJECT — "we build on X", "we extend X", "we propose Y, a variant of X", "Y evolves from X". Lineage lives in prose, so sweep the introduction, related work, AND the method section — this is the signal the references pass misses. If you cannot quote such a this-paper-as-subject lineage sentence, it is NOT `builds_on`.
  - `uses` — THIS paper DEPENDS ON this external method as a building block — a backbone, a base model, a reused sub-module or technique — and adopts it AS-IS, WITHOUT modifying/extending it. Evidence reads "we use X as the base model", "we adopt the X backbone", "we build upon X" (when X is a foundation they run on, not a method they modify), "we implement X", "kept the same as X", "with X as a basis". This is a real method-to-method edge but a weaker one than lineage. It must still be an external METHOD/model — NOT a dataset/benchmark (those are testbed, out of scope) and NOT apparatus (optimizer/sampler/scoring-model, out of scope).
  - `compared_against` — THIS paper evaluates its own method experimentally against this prior method as a baseline, OR substantively argues against this prior method's approach (a critique it tests or directly addresses, not a passing related-work contrast).
  Disambiguation (this is the precision-critical decision):
  - If the paper MODIFIES/extends X (its method is a variant of X) -> `builds_on`.
  - Else if the paper merely DEPENDS ON X as an unchanged building block / backbone / base model -> `uses` (do NOT inflate this to `builds_on`: adopting a backbone is not lineage).
  - Else if X appears ONLY as a comparison baseline / results-table row it is measured against -> `compared_against`.
  Route ambiguous lineage-vs-dependency to `uses`, and ambiguous dependency-vs-baseline to whichever the evidence shows; reserve `builds_on` for genuine, quotable extension.
- `cite_key` — the in-text citation marker attached to the method in the prose, exactly as written ("12", "Vaswani2017"); empty string "" if it is named with no inline citation.
- `evidence` (a REQUIRED GATE, not decoration) — a short verbatim span from the paper that, for `builds_on`, literally contains the this-paper-as-subject lineage clause; for `uses`, the span showing the paper depending on X as a building block; for `compared_against`, the span showing the experimental comparison or substantiated critique. If you cannot quote a qualifying span, do not emit the entry.

## The actor test (precision is critical)

The relation must have THIS PAPER'S OWN CONTRIBUTION as the subject acting on the external method. Emit ONLY when a "we build on / we extend / we use as a building block / we adopt the backbone / we compare against X" reading holds. A sentence where the cited works are themselves the actors ("[15] extends [16]", "prior methods [3,4] use heuristics; in contrast we ...") is NOT this paper building on, using, or comparing against [15]/[16]/[3]/[4] — it is related-work narration. SKIP it.

DO NOT emit:
- A method merely SURVEYED, described, or mentioned in related work that this paper does not itself build on or compare against. A related-work list is not a builds_on list.
- A method named only to be DISMISSED or motivated away ("unlike RNNs, which cannot parallelize, we ...") with no experimental comparison — that is background contrast, not `compared_against`.
- This paper's OWN method, its components/sub-modules, or a prior version of this same work by the same authors ("extends our earlier work [3]") presented as the contribution's basis. The internal node census already owns the paper's own contribution and every component it proposes — they are out of scope here, and treating one as external would create a false "the contribution builds on its own part" edge. Only SOMEONE ELSE'S pre-existing method is external.
- A generic paradigm, family, or concept that is not a specific named method ("attention", "deep learning", "self-supervised learning", "convolutional networks" in the abstract sense).
- A dataset, benchmark, task, or evaluation metric (these are the census's testbed nodes — out of scope here).
- Apparatus: an optimizer (Adam, SGD), a sampling technique, a model used only to compute a metric (an embedding/scoring model behind a similarity score), hardware, or an incidental tool/library. These carry no method-to-method edge — SKIP them.

Recall vs precision: be HIGH-RECALL on genuine method-to-method links (every external method the contribution extends, depends on as a building block, or is compared against), and STRICT on the actor test and on the builds_on-vs-uses split (never promote a plain backbone/base-model to `builds_on`, and never promote a surveyed or dismissed method to any edge). When there is genuinely no "this paper builds on / uses / compares against X" relationship, do not emit X.

## Output

Return a single JSON object: {"external_methods": [ ... ]}. One entry per distinct external method (if the same method qualifies for more than one relation, emit it once with the most specific: builds_on > compared_against > uses). When the paper relates to no external method, output {"external_methods": []}.

Examples (EMIT):
- "We build our architecture on top of the Transformer [12], adding a retrieval module." -> {"name": "Transformer", "relation": "builds_on", "cite_key": "12", "evidence": "We build our architecture on top of the Transformer [12], adding a retrieval module"}. (the paper MODIFIES it)
- "Our method extends PPO [7] with a trust-region penalty." -> {"name": "PPO", "relation": "builds_on", "cite_key": "7", "evidence": "Our method extends PPO [7] with a trust-region penalty"}.
- "We use LLaVA-1.5 [5] as the base LMM." -> {"name": "LLaVA-1.5", "relation": "uses", "cite_key": "5", "evidence": "We use LLaVA-1.5 [5] as the base LMM"}. (adopted AS-IS as a base model -> `uses`, NOT `builds_on`)
- "We adopt the PointNet++ [34] backbone network." -> {"name": "PointNet++", "relation": "uses", "cite_key": "34", "evidence": "We adopt the PointNet++ [34] backbone network"}.
- "We compare our model against BERT [9] and RoBERTa [10] on GLUE." -> two entries, both `compared_against`, cite_keys "9" and "10".

Examples (SKIP):
- "Recent work [3, 4, 5] explores graph neural networks for this task." -> related-work survey, no actor; emit nothing.
- "Unlike recurrent models, which preclude parallelization, our model ..." with no experiment against an RNN -> background contrast; emit nothing.
- "We train on ImageNet [4]." -> ImageNet is a dataset (testbed), not an external method; emit nothing.
- "We optimize with Adam [14]." -> apparatus; emit nothing.
- "Attention mechanisms have transformed NLP." -> generic paradigm; emit nothing.
```

## User Prompt

```text
Extract the external prior-art methods this paper builds on, uses as a building block, or compares its own method against:

<paper>
{{paper_content}}
</paper>
```
