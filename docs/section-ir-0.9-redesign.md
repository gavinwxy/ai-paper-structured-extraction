# section-ir-0.9 — two-level type/role taxonomy

0.9 keeps the three-stage pipeline and the `problem → method → evidence` spine of 0.8 unchanged. It rewrites the **unit type taxonomy** into two explicit levels and, as a consequence, removes one relation and merges two types. Net effect is **reductive**: 7 types → 6, one relation dropped, zero new roles or relations.

## The principle: `type` = generic scope, `role` = fine-grained differentia

Every unit carries two classificatory axes:

- **`type`** — a small, discipline-neutral scope, anchored on the canonical anatomy of an empirical paper (the scientific method): *Identify a Problem → Design an Experiment → Collect Results → Construct a Conclusion*. The type set looks the same whether the paper is from NLP, vision, or another field.
- **`role`** — the AI/ML-specific differentia carried *on the unit*, unifying the old scattered `entity_class` / `setting_kind` / `claim_kind` / `doc_role` fields, and lifting the census argumentative role onto the Method unit. Swapping disciplines means swapping the per-type role vocabularies, never the `type` set.

This regularizes a pattern 0.8 already had unevenly (Document had `doc_role`, census nodes had `role`, others had `*_kind`): now every type that has a sub-axis names it `role`.

## Types (6) and their `role` vocab

| scientific-method phase | type | role vocab |
|---|---|---|
| Identify a Problem | **Problem** | — (single trunk, no role) |
| Design an Experiment — apparatus | **Method** | `contribution` · `component` · `builds_on` · `compared_against` (argumentative function; `method_kind` survives as an **optional** structural attribute) |
| Design an Experiment — materials + conditions | **ExperimentSetup** | substrate: `dataset` · `benchmark` · `task` (census-discovered) · configuration: `data_split` · `inference_protocol` · `training_config` · `ensembling` · `population` (content-born) |
| Collect Results | **Measure** | — (uniform; keeps `comparison_direction`) |
| Construct a Conclusion | **Finding** | `descriptive` · `mechanistic` · `comparative` · `modeling` · `ablation_finding` · `failure_mode` |
| the paper | **Document** | `research_article` · `review` · `meta_analysis` · `methodology` · `benchmark_survey` |

Renames from 0.8: `Metric → Measure`, `Claim → Finding`, and `Entity ⊎ Setting → ExperimentSetup` (a true merge). ID prefixes follow: `mea:`, `fnd:`, `exp:` (the old `met:`/`clm:`/`ent:`/`set:` are retired). The old type names are added to `FORBIDDEN_UNIT_TYPES` so a stale prompt or model output fails loudly.

## Why Entity ⊎ Setting → ExperimentSetup

`Entity` was the genus name (everything in a graph is an "entity") stolen by a species, and it was defined by exclusion — a grab-bag of "testbed things that aren't methods or metrics". "Design an Experiment" is **one** scientific-method step that bundles both *what you run on* (dataset/benchmark/task) and *under what configuration* (split/protocol/training/ensembling/population), so folding them into one type with a `role` differentia is a **positive, named** concept rather than a residual one. The merge also collapses the long-standing dataset(Entity)+split(Setting) duplication: a "dataset+split" is naturally one ExperimentSetup unit.

The census/born distinction survives *within* the type by role: the substrate roles are emitted by the node census (stage A) and carry the bibliography `cite_keys` on the census node (used by reference reconcile via `node_id`); the configuration roles are born during content fill (stage C), materialized only when they actually scope a Measure.

## Relations: `measured_on` removed (8 → 7)

`measured_on` (Metric → dataset Entity) is gone. A Measure now binds to the dataset/split it ran on through each **score row's `setup_id` → ExperimentSetup** (the unit-level scalar reference, renamed from `setting_id`; the list field `setting_ids → setup_ids`). The metric→dataset link is therefore a scalar reference, not a global edge. This is the one precision trade the merge accepts: "a measure's data must be a dataset/benchmark, not a hardware config" drops from a *type*-level guarantee to a *role*-level one, enforced by validation/prompt rather than by the relation matrix.

Surviving relation matrix:

| relation | source → target | authored by |
|---|---|---|
| `part_of` | {Method, ExperimentSetup} → same | relation pass (B) |
| `compares_to` | {Method, ExperimentSetup, Measure} → same | relation pass (B) |
| `evaluates` | Measure → Method | relation pass (B) |
| `about` | Finding → {Method, ExperimentSetup, Measure} | content (evidence) |
| `supports` | {Measure, Finding} → Finding | content (evidence) |
| `motivates` | Problem → {Method, ExperimentSetup} | content (problem) |
| `resolves` | Finding → Problem | assembly (synthesized) |

## Out of scope by decision

Hardware (GPU model/count) and global hyperparameters that scope **no** Measure are **not** captured — there is no `hardware` role and no `configured_by` relation. Only configuration that actually scopes a Measure (reachable via `setup_id`) is materialized. This keeps the 0.8 "apparatus is not a node" discipline.

## Role injection

`role` is a first-class unit field, but for census-materialized units (Method, substrate ExperimentSetup) the census already committed the role, so assembly (`_assign_roles_from_census`) stamps it authoritatively rather than trusting the content model to echo it. Born units (configuration ExperimentSetup, Finding) author their own role. Problem and Measure carry no role.
