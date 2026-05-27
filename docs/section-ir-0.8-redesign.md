# section-ir-0.8: the discovery-throughline spine

0.8 is a spine reshaping on top of 0.7 (see `section-ir-0.7-redesign.md` for the
nodes→edges→content architecture, which is unchanged). The three-stage pipeline (node
census → relation pass → content fill) and every census/relation mechanism carry over
verbatim. What changes is the **content-section spine** and two small additions.

## Motivation

0.7 organized content by *unit type* — a `context` section, a `claim` section, a `method`
section, an `evidence` section — which read as an information-completeness dump rather than a
scientific discovery with a traceable line. Two parts were weak:

- **`context`** over-defined a five-value `context_kind` taxonomy (background / gap / motivation
  / challenge / assumption). In practice the load-bearing thing is just **the research
  problem**; the taxonomy was completeness noise.
- **`claim`** was a thin section — one or two sentences restating the contribution — already
  subsumed by `evidence`, which produces Claim items of its own.

0.8 reframes the output as a discovery arc: **`problem → method → evidence`**, where the
contribution is not a standstill box at the front but the *answer the evidence establishes* at
the climax.

## Changes from 0.7

| 0.7 | 0.8 |
|---|---|
| 4 content sections: `context`, `claim`, `method`, `evidence` | 3: `problem`, `method`, `evidence` |
| `Context` unit, `context_kind ∈ {background,gap,motivation,challenge,assumption}` | `Problem` unit, single `description` field (taxonomy dropped); one trunk per paper |
| headline contribution claim lives in its own `claim` section | born in `evidence` (the section that also holds the findings) |
| — | Document gains a `thesis` string |
| — | new relation `resolves` (Claim → Problem), synthesized in assembly |
| `motivates`: Context → {Method, Entity} | `motivates`: Problem → {Method, Entity} |
| IR `section-ir-0.7` | IR `section-ir-0.8` |

`method` and `evidence`'s field contracts are otherwise unchanged.

## The throughline, as edges

```
Problem ──motivates──▶ [contribution](census node) ◀──about── Claim(headline)
   ▲                                                              │
   └──────────────── resolves (synthesized) ─────────────────────┘
```

- `motivates` (problem section authors it): the Problem → the census `contribution` it justifies.
- `about` (evidence section authors it): the headline Claim → the same census `contribution`.
- `resolves` (**no section authors it**): the closing arrow, Claim → Problem.

## Why `resolves` is synthesized, not authored

The four content sections run as **parallel** LLM calls; only census nodes (in
`node_registry`) are visible across them. A `Claim --resolves--> Problem` edge joins the
headline Claim (born in `evidence`) to the Problem (born in `problem`) — two units invented in
*different* parallel calls, neither aware of the other's ids. Authoring it in either section
would require a forward reference into a sibling's fresh output, the same failure mode that
retired `occurs_under`.

But both ends attach to the same globally-visible census `contribution` node. So assembly
derives the edge once every section is in hand (`_assign_resolves` in `section_pipeline.py`):

```
contribution C = the census node with role == "contribution"
Problem P      = the Problem unit with a motivates edge to C
                 (fallback: the problem section anchor, else the sole Problem)
for each Claim K with an about edge to C:
    emit  K --resolves--> P
```

It is deduped by the existing `_dedup_relations` and validated like any edge
(`RELATION_MATRIX["resolves"] = ({Claim}, {Problem})`), but it is **not** in
`STAGE_C_RELATIONS` / any section's stage-C enum.

## `thesis` for free

The census `spine_summary.central_contribution` is already a validated, non-empty one-sentence
contribution. Assembly lifts it straight onto `document.thesis` — no new LLM call, no metadata
prompt change.

## Files touched

- `section_pipeline.py`: section/unit/relation constants; `Problem` validation; the Claim
  membership check (`evidence` only); `_assign_resolves`; `build_document_unit(thesis=…)`;
  `assemble_extraction` wiring; `ctx:`→`prb:` id alias; IR version.
- `tools/generate_section_schemas.py`: `SECTION_TYPED_ARRAYS`, `STAGE_C_RELATIONS_BY_SECTION`,
  `ARRAY_TYPE_NAMES`, the `Problem` unit schema (dropped `context_kind`), gloss/description text.
- Prompts: `section-modules/problem.md` (new, replaces `context.md`); `claim.md` deleted;
  `evidence.md` (hosts the headline claim); `section-extraction-pass.md`; `node-census.md`.
- `tools/render_extraction.py`: section labels/colors/shapes, `Problem`, the `thesis` header,
  dropped `context_kind` tag.
- Schemas: `section-problem.schema.json` (regenerated); `section-context`/`section-claim` removed.
- Tests: `tests/test_section_pipeline.py` (fixtures + assertions; new `resolves`/`thesis` checks).
