#!/usr/bin/env python3
"""Two-stage section extraction pipeline: section planning -> constrained extraction."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from html.parser import HTMLParser
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = PROJECT_ROOT / "prompts" / "section-extraction"
NODE_CENSUS_PROMPT_PATH = PROMPTS_DIR / "node-census.md"
RELATION_PASS_PROMPT_PATH = PROMPTS_DIR / "relation-pass.md"
SECTION_EXTRACTION_PROMPT_PATH = PROMPTS_DIR / "section-extraction-pass.md"
SECTION_MODULES_DIR = PROMPTS_DIR / "section-modules"
EXAMPLES_DIR = PROMPTS_DIR / "examples"
METADATA_PROMPT_PATH = PROJECT_ROOT / "prompts" / "metadata-extraction.md"
REFERENCES_PROMPT_PATH = PROJECT_ROOT / "prompts" / "references-extraction.md"
SCHEMAS_DIR = PROJECT_ROOT / "schemas"
NODE_CENSUS_SCHEMA_PATH = SCHEMAS_DIR / "node-census-output.schema.json"
RELATION_PASS_SCHEMA_PATH = SCHEMAS_DIR / "relation-pass-output.schema.json"
METADATA_SCHEMA_PATH = SCHEMAS_DIR / "metadata-output.schema.json"
REFERENCES_SCHEMA_PATH = SCHEMAS_DIR / "references-output.schema.json"
SECTION_SCHEMA_FILES: dict[str, str] = {
    "problem": "section-problem.schema.json",
    "method": "section-method.schema.json",
    "evidence": "section-evidence.schema.json",
}

DEFAULT_PARALLEL_MAX_WORKERS = 5
DEFAULT_SECTION_MAX_TOKENS = 131_072
MAX_SECTION_RETRIES = 2
SECTION_MARKER_RE = re.compile(r"(?m)^\[§(\d+)\]\s*")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")
# A provenance marker is a top-level §N (numeric body/block section) or §X (a lettered appendix,
# Roman-numeral section, or short section word — §A, §C, §IV, §supp) — both legitimate, traceable
# paper locations — or a float reference (Table/Figure/Algorithm/Equation/Listing N, plus the
# theorem-environment refs Theorem/Lemma/Corollary/Proposition/Definition that theory papers cite,
# FG-2). A float may carry a panel suffix (Figure 2 (a), Figure 1 (R)). Floats point at a real,
# citeable element of the paper (often the *most* precise source for a Measure's numbers), the
# renderer shows them verbatim, and nothing downstream resolves a marker back to the input — so
# rejecting them only hard-failed otherwise-sound extractions over the model's natural way of
# citing a table or a lemma. Fine-grained section subdivisions (§4.3, §IV-D, §A4.2), block ranges
# (§107-108, §118-§120), spelled appendices (Appendix A.2), and a § glued to a float word (§Table 3
# -> Table 3) are all normalized to a valid form by _normalize_provenance_markers *before* this
# check, so they never reach it. Free prose still fails.
PROVENANCE_SOURCE_RE = re.compile(
    r"^(?:§(?:\d+|[A-Za-z]+)"
    r"|(?:Table|Figure|Fig|Algorithm|Alg|Equation|Eq|Listing"
    r"|Theorem|Lemma|Corollary|Proposition|Definition|Assumption|Claim|Remark|Observation|Proof)"
    r"\.?\s+[A-Za-z0-9][\w.()\-]*(?:\s*\([^)]*\))?)$",
    re.IGNORECASE,
)
# A finer-grained locator that has a real, coarser parent among the input's top-level §N/§X
# anchors: a dotted subsection (§4.3, §C.1, §G.2), an IEEE-style hyphenated subsection (§IV-D,
# §III-F1), or a range of consecutive block markers (§107-108, §118-§120). The input only anchors
# top-level sections/blocks, so all of these collapse to their leading §N / §X parent (group 1).
SUBSECTION_MARKER_RE = re.compile(r"^§(\d+|[A-Z]+)[.\-]")
# A spelled-out appendix reference (Appendix A, Appendix A.2, App. C, App. D.1) maps to the §X
# lettered-appendix anchor; the trailing subsection number is dropped, exactly as for §C.1 -> §C.
APPENDIX_SPELLED_RE = re.compile(r"^App(?:endix)?\.?\s+([A-Za-z])(?![A-Za-z])")
# A lettered appendix with a glued (separatorless) subsection number — §A4.2, §B3, §G2 — collapses
# to its §X parent, exactly as the dotted/hyphenated forms do (the digit starts the subsection).
APPENDIX_NUMBERED_RE = re.compile(r"^§([A-Za-z]+)\d")
# P4 source-of-truth capture: every inline <table> blob is sliced verbatim (deterministically, no
# parser) into extraction_notes.source_tables, a dict keyed by the §N block that contains the table
# (the same `[§N]` marker the evidence pass references) carrying that block's **Table k** caption.
# The model never emits this html — it is the raw grid behind the evidence pass's score rows, kept
# for audit/fallback and as the re-derivation source a future table parser can read instead of
# re-reading the whole paper.
TABLE_BLOCK_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
TABLE_CAPTION_RE = re.compile(r"\*\*\s*Tab(?:le|\.)?[^*\n]*\*\*", re.IGNORECASE)

SECTION_TYPES = {"problem", "method", "evidence"}
SECTION_ORDER = ["problem", "method", "evidence"]
SECTION_ALLOWED_UNIT_TYPES: dict[str, set[str]] = {
    "problem": {"Problem"},
    "method": {"Method"},
    "evidence": {"Measure", "ExperimentSetup", "Finding"},
}
# The unit type that should naturally anchor each section. Used when repairing an
# anchor that names a non-local unit (e.g. an evidence section reaching for the
# root `mth:` method): prefer re-pointing to a local unit of this type before
# falling back to the first local non-Document unit.
SECTION_PREFERRED_ANCHOR_TYPE: dict[str, str] = {
    "problem": "Problem",
    "method": "Method",
    "evidence": "Measure",
}
# Census node types each content section materializes into full units. Method nodes
# become Method units in the method section; Measure and the substrate-role
# ExperimentSetup nodes (dataset/benchmark/task) become units in the evidence section.
# Problem and Finding are not census nodes — they are born during content extraction
# (Problem in the problem section, Finding in evidence). The configuration-role
# ExperimentSetup units (data_split/inference_protocol/...) are likewise born in evidence.
SECTION_MATERIALIZED_NODE_TYPES: dict[str, set[str]] = {
    "problem": set(),
    "method": {"Method"},
    # evidence also materializes the FG-5 `contribution_finding` census root (a Finding): it is
    # the one Finding the census plans, reused by id as the headline finding instead of a freshly
    # born one. All other Findings are still born here.
    "evidence": {"Measure", "ExperimentSetup", "Finding"},
}
# Content sections that author edges in their own `relations[]`: evidence authors the
# claim-centric `about`/`supports`; problem authors `motivates` (Problem -> the census
# Method/ExperimentSetup it justifies). The closing `resolves` (Finding -> Problem) is NOT authored
# by any section — it crosses two parallel sections, so it is synthesized in assembly
# (_assign_resolves). Structural edges are authored earlier by the relation pass. The
# exact relation enum per section lives in the schema generator's STAGE_C_RELATIONS_BY_SECTION.
SECTION_AUTHORS_RELATIONS = {"problem", "evidence"}
TYPED_ARRAY_KEYS: dict[str, str] = {
    "problems": "Problem",
    "methods": "Method",
    "experiment_setups": "ExperimentSetup",
    "measures": "Measure",
    "findings": "Finding",
}
# Census node concepts. The census emits a flat list of referenceable nodes; each
# node_id is reused verbatim as the final unit id once a content section materializes it.
NODE_TYPES = {"Method", "ExperimentSetup", "Measure", "Finding"}
NODE_ID_PREFIX_BY_TYPE: dict[str, str] = {
    "Method": "mth:",
    "ExperimentSetup": "exp:",
    "Measure": "mea:",
    # `fnd:` is a census id prefix only for the FG-5 `contribution_finding` root (the one Finding
    # the census plans); all other Findings are born in the evidence section with `fnd:` ids too,
    # but are not census nodes.
    "Finding": "fnd:",
}
SALIENCE_LEVELS = {"must", "should"}
# Census node role — the single granular tag the census emits per node. It is the
# argumentative function the node plays, grouped into four search clusters by the guiding
# principle "trace the method's life": the_method (mine), prior_art (others'), testbed
# (data), yardsticks (metrics). `type` and the document root are derived from `role` (see
# ROLE_TO_TYPE / normalize_census_nodes), and `role` is carried onto the materialized unit
# as its fine-grained differentia (section-ir-0.9: type = generic scope, role = sub-axis),
# so the model commits to one axis instead of several half-overlapping fields.
NODE_ROLES = {
    "contribution",          # the_method: the paper's single primary method/system (the root)
    "contribution_resource", # the_method: the root when the deliverable is a dataset/benchmark (FG-1)
    "contribution_finding",  # the_method: the root when the deliverable IS a result/finding (an
                             # analysis/mechanistic paper with no novel method or resource; FG-5,
                             # 0.10 Pass 2). Materialized as a Finding (fnd: id) by the evidence
                             # section, which resolves the Problem directly — no hollow "Analysis"
                             # Method is invented as a stand-in root.
    "component",          # the_method: a sub-method/module that is part of the contribution
    "builds_on",          # prior_art: an existing method/model the contribution extends
    "compared_against",   # prior_art: a baseline method the contribution is compared against
    "dataset",            # testbed: data the method is trained or evaluated on
    "benchmark",          # testbed: a standardized dataset+protocol for evaluation
    "task",               # testbed: the problem being solved/evaluated
    "theoretical_setting", # testbed: the regime/assumptions a theorem holds under (FG-2, 0.10)
    "structural_class",    # testbed: the structural family a result ranges over (graph class, etc.)
    "metric",             # yardsticks: a reported performance measure
}
# role -> coarse node type. Total and unambiguous: a node's type is a strict coarsening of
# its role, so the census carries only `role` and the pipeline derives `type` from it.
ROLE_TO_TYPE: dict[str, str] = {
    "contribution": "Method",
    "contribution_resource": "ExperimentSetup",
    "contribution_finding": "Finding",
    "component": "Method",
    "builds_on": "Method",
    "compared_against": "Method",
    "dataset": "ExperimentSetup",
    "benchmark": "ExperimentSetup",
    "task": "ExperimentSetup",
    "theoretical_setting": "ExperimentSetup",
    "structural_class": "ExperimentSetup",
    "metric": "Measure",
}
# role -> search cluster (carried into the registry as context for the relation pass).
ROLE_CLUSTER: dict[str, str] = {
    "contribution": "the_method",
    "contribution_resource": "the_method",
    "contribution_finding": "the_method",
    "component": "the_method",
    "builds_on": "prior_art",
    "compared_against": "prior_art",
    "dataset": "testbed",
    "benchmark": "testbed",
    "task": "testbed",
    "theoretical_setting": "testbed",
    "structural_class": "testbed",
    "metric": "yardsticks",
}
# The single document-level root is the node whose role is `contribution` (a Method) or
# `contribution_resource` (an ExperimentSetup — when the paper's primary deliverable is a dataset/
# benchmark; FG-1, section-ir-0.10). Exactly one root across both roles. An ExperimentSetup root
# hosts its own score rows (it is a valid setup_id target), so a benchmark contribution no longer
# needs a duplicate Method twin to carry its numbers.
CONTRIBUTION_ROLE = "contribution"
# The document-root roles. `contribution` (a Method) and `contribution_resource` (an
# ExperimentSetup deliverable, FG-1) are the artifact roots; `contribution_finding` (a Finding,
# FG-5/0.10 Pass 2) is the root when the paper's deliverable is a *result*, not an artifact — an
# analysis/mechanistic paper. A paper has ≥1 root (usually one; co-equal roots are linked by
# co_contribution, FG-7).
CONTRIBUTION_ROLES = {"contribution", "contribution_resource", "contribution_finding"}
# The census-discovered ExperimentSetup substrate roles. dataset/benchmark/task are the external,
# citeable testbed nodes; contribution_resource (FG-1) is the paper's own benchmark/dataset
# deliverable as the document root (carries no cite_keys). The remaining ExperimentSetup roles
# (data_split/...) are paper-local configuration born during content fill, not emitted by the census.
SUBSTRATE_ROLES = {role for role, type_ in ROLE_TO_TYPE.items() if type_ == "ExperimentSetup"}
UNIT_TYPES = {
    "Document",
    "Problem",
    "Method",
    "ExperimentSetup",
    "Measure",
    "Finding",
}
# Archived/retired type names. The 0.8 set (Entity/Setting/Metric/Claim) was renamed and
# merged in 0.9 (Entity ⊎ Setting → ExperimentSetup, Metric → Measure, Claim → Finding);
# the old names are rejected so a stale prompt or model output fails loudly.
FORBIDDEN_UNIT_TYPES = {
    "RoleBinding",
    "Relation",
    "MethodArtifact",
    "SystemModel",
    "Proposition",
    "Category",
    "Provenance",
    "Entity",
    "Setting",
    "Metric",
    "Claim",
}

# --- Per-type `role` vocabularies (section-ir-0.9) ---------------------------------------
# Every unit carries two classificatory axes: a generic `type` (the scientific-method-anchored
# scope) and a fine-grained `role` (the discipline-specific differentia). The role vocab is
# scoped per type below; Problem and Measure have no sub-axis and carry no `role`. Swapping
# disciplines means swapping these role sets, never the `type` set.

# Document role (was `doc_role`): the kind of document.
DOCUMENT_ROLES = {"research_article", "review", "meta_analysis", "methodology", "benchmark_survey"}

# Method role = the argumentative function the method plays (the census role, lifted onto the
# unit). Derived from ROLE_TO_TYPE so it never drifts from the census vocabulary.
METHOD_ROLES = {role for role, type_ in ROLE_TO_TYPE.items() if type_ == "Method"}

# ExperimentSetup role = the merged Entity-class ⊎ Setting-kind axis (section-ir-0.9). The
# substrate roles (dataset/benchmark/task) are census-discovered, external and citeable; the
# configuration roles are paper-local and born during content fill, materialized only when they
# scope a Measure (reachable via a score row's setup_id). Hardware / global hyperparameters that
# scope no Measure are intentionally NOT captured ("apparatus is not a node").
EXPERIMENT_SETUP_ROLES = SUBSTRATE_ROLES | {
    "data_split",          # the dataset/subset/split a measure was computed on
    "inference_protocol",  # test-time procedure: beam search params, crop/scale, single-view
    "training_config",     # training regime that scopes a measure: optimizer/steps/schedule
    "ensembling",          # multi-model or multi-scale combination presented as a configuration
    "population",          # study population / cohort (e.g. a human-evaluation panel)
}

# Finding role (was `claim_kind`), scoped to AI/ML literature: `causal`/`correlational` never
# fire on this corpus and were dropped; `descriptive` is retained for future-work findings.
# `theorem`/`lemma`/`bound` (0.10, FG-2) carry a *proven* theoretical result as a Finding, so the
# epistemic "proven vs observed" distinction is structural — they were previously coerced into
# `modeling`/`comparative`. (`definition` is not a result, so it is a `method_kind` only, not a
# Finding role.)
FINDING_ROLES = {
    "descriptive",
    "mechanistic",
    "comparative",
    "modeling",
    "ablation_finding",
    "failure_mode",
    "theorem",
    "lemma",
    "bound",
}

# Finding quantitative payload (section-ir-0.10, FG-11). Optional structured fields carried on a
# Finding so its headline effect is queryable instead of buried in prose: `polarity` (the sign of
# the effect, from the perspective of the paper's method/hypothesis — so a null/negative result is
# structurally distinct from a positive one), plus the free-text `effect_size` (magnitude in the
# paper's own terms, e.g. "+2.1 BLEU", "3 orders of magnitude") and `scope` (the conditions/range
# under which it holds, e.g. "on 11 of 12 tasks"). All optional; omitted when the paper is silent.
FINDING_POLARITIES = {"positive", "negative", "neutral", "mixed"}

# `role` vocabulary per unit type (the differentia axis). Types absent here carry no `role`:
# Problem is a single trunk; Measure is uniform.
ROLE_VOCAB_BY_TYPE: dict[str, set[str]] = {
    "Document": DOCUMENT_ROLES,
    "Method": METHOD_ROLES,
    "ExperimentSetup": EXPERIMENT_SETUP_ROLES,
    "Finding": FINDING_ROLES,
}

# Method `method_kind` survives as an OPTIONAL descriptive attribute (the structural kind),
# orthogonal to the argumentative `role`. Scoped to AI/ML: `protocol`/`software_system` never
# fire on this corpus.
# `resource`/`taxonomy` (0.10, FG-1) type a contribution that is a non-algorithmic deliverable
# (a taxonomy, an atlas, a software library) as a Method for want of a dedicated type; method.md
# suppresses the algorithm-form fields (inputs/outputs/formulas/objective_function) for them. A
# dataset/benchmark deliverable is NOT a method_kind — it is an ExperimentSetup via the
# contribution_resource census role, so it hosts score rows natively without a duplicate twin.
# `theorem`/`lemma`/`bound`/`definition` (0.10, FG-2) type a formal statement/construct
# materialized as a Method (a theorem, an established bound, a formal definition the paper
# introduces); like resource/taxonomy these are not algorithms, so method.md suppresses the
# algorithm-form fields for them. The *proven* result then lives as a Finding (role theorem/
# lemma/bound) that the theorem-Method `supports`.
METHOD_KINDS = {"algorithm", "model_architecture", "training_strategy", "objective_function",
                "resource", "taxonomy", "theorem", "lemma", "bound", "definition"}
COMPARISON_DIRECTIONS = {"higher_is_better", "lower_is_better", "target", "unspecified"}
# Optional per-score-row value kind (0.10, FG-2). A score `value` is always a string; `value_kind`
# says how to read it so a symbolic/asymptotic theoretical result (`O(n^6)`, `PSPACE-complete`,
# `2/Δ·logT`) is no longer forced into a numeric pseudo-leaderboard. Omitted ⇒ numeric (the
# empirical-leaderboard default), so this is purely additive for the existing corpus. For a
# symbolic/asymptotic/qualitative row the measure's `comparison_direction` is normally omitted or
# `unspecified` (there is no monotone better/worse), and `variance` is normally "".
SCORE_VALUE_KINDS = {"numeric", "symbolic", "asymptotic", "qualitative", "curve"}
# Optional Measure objective class (0.10, FG-6): which axis of a multi-objective evaluation a
# measure sits on, so a precision/cost/fairness/safety trade-off does not read as uniformly
# positive evidence. Omitted ⇒ the headline quality axis (the leaderboard default), so additive.
MEASURE_OBJECTIVE_CLASSES = {"primary_quality", "cost_efficiency", "fairness", "safety", "robustness"}
# Optional Measure table role (0.12, blob-primary): main_result tables carry the contribution
# method's own score rows (baselines stay in the source-table blob); ablation tables carry no rows
# at all (the blob is the whole story). Omitted ⇒ main_result.
MEASURE_TABLE_ROLES = {"main_result", "ablation"}
# Removed in the AI/ML-scoped type cleanup (each was monotone across the corpus): Measure
# `value_type` (always scalar), Finding `novelty` (always original), `epistemic_status`
# (always conclusion). Finding `polarity` was dropped in 0.9 but is reintroduced in 0.10 as an
# optional FG-11 payload field (FINDING_POLARITIES, above) — off-CV venues report null/negative/
# mixed results the CV corpus did not, so the positive-vs-null distinction is now load-bearing.
# The provenance `source_kind` enum was dropped (2026-05-26): provenance is a flat list of `§N`
# markers. The `measured_on` relation was dropped (section-ir-0.9): metric→dataset is now the
# score row's setup_id → ExperimentSetup.

# Global relation type matrix (section-ir-0.9; +builds_on/uses in 0.10). Endpoints resolve to a
# unit defined anywhere in the extraction; relations are no longer section-local. `measured_on`
# was removed in 0.9 — a Measure binds to its dataset/split via the score row's setup_id →
# ExperimentSetup, not via a global edge. `builds_on`/`uses` (0.10, FG-4) are external-dependency
# edges, distinct from `part_of` (internal composition) and `compares_to` (competition): a
# contribution builds_on the prior art it extends and uses the methods/data it depends on. Before
# 0.10 a builds_on dependency was coerced onto part_of (false containment) or left edgeless.
RELATION_MATRIX: dict[str, tuple[set[str], set[str]]] = {
    "part_of": ({"Method", "ExperimentSetup"}, {"Method", "ExperimentSetup"}),
    "builds_on": ({"Method", "ExperimentSetup"}, {"Method", "ExperimentSetup"}),
    "uses": ({"Method", "ExperimentSetup"}, {"Method", "ExperimentSetup"}),
    "assumes": ({"Method"}, {"ExperimentSetup"}),
    "co_contribution": ({"Method", "ExperimentSetup"}, {"Method", "ExperimentSetup"}),
    "compares_to": ({"Method", "ExperimentSetup", "Measure"}, {"Method", "ExperimentSetup", "Measure"}),
    "evaluates": ({"Measure"}, {"Method"}),
    "about": ({"Finding"}, {"Method", "ExperimentSetup", "Measure"}),
    "supports": ({"Measure", "Finding", "Method"}, {"Finding"}),
    "motivates": ({"Problem"}, {"Method", "ExperimentSetup"}),
    "resolves": ({"Finding"}, {"Problem"}),
}
# Which stage authors each relation. The relation pass (stage B) owns the structural
# node<->node edges over the full node set; content extraction (stage C) owns the
# edges that require units born during content — the Finding-centric `about`/`supports`,
# and `motivates` from a born Problem to the census Method/ExperimentSetup it justifies (the
# Problem-born source plus the globally visible census target are both in hand in the
# problem call, so no forward reference is needed). `resolves` (Finding -> Problem) is the
# closing stroke of the discovery arc; it joins two units born in *different* parallel
# sections, so no section can author it — assembly synthesizes it (_assign_resolves) from
# the contribution-node join, which is globally visible.
# `assumes` (Method -> ExperimentSetup, FG-2) is stage-B: both endpoints are census nodes (a
# theorem-Method and the theoretical_setting/structural_class substrate it holds under), so the
# relation pass binds them with the whole node set in view, no forward reference needed.
# `supports` (FG-2) now also accepts a Method source so a theorem-Method materialized in the
# method section can `supports` the result-Finding born in evidence — the Method endpoint is a
# census node visible to the evidence call, so it stays a stage-C edge.
STAGE_B_RELATIONS = {"part_of", "compares_to", "evaluates", "builds_on", "uses", "assumes",
                     "co_contribution"}
STAGE_C_RELATIONS = {"about", "supports", "motivates"}
SYNTHESIZED_RELATIONS = {"resolves"}
ARGUMENTATIVE_INCOMING = {"supports"}

# FG-12 (section-ir-0.10) + vocab unification: a reference's citation role IS the unit-graph
# edge it implies — the two vocabularies were merged so a role is just an edge-in-waiting, materialized
# by reconcile_reference_units once the cited work links to a node. The reference roles are exactly the
# external-dependency subset of the edge vocabulary plus one context-only sentinel: `builds_on` (the
# contribution's direct predecessor), `uses` (a reused method/data/benchmark building block), and
# `compares_to` (an experimental baseline or a critique — the distinction rides on `stance`) each
# reconcile to the edge of the same name (identity, no translation). `background` (the merged
# background/motivation/future_work/related) is the lone role with NO edge — that absence is how a
# genuinely-run comparison (→ compares_to) is distinguished from a context mention, addressing the
# compared_against overload (FG-4) without inventing a new census role. Backfilled edges are stamped
# `origin="reference"` so downstream can tell a citation-derived edge from a natively-authored one
# (the 3 overlapping edge types are otherwise indistinguishable); natively-authored edges carry no
# `origin`. (Earlier 0.10 used a separate references vocab {extends, uses_component, compares}
# translated via a map; that map collapsed to identity once the names were unified. A finer evolution
# split {improves/replaces/adapts} on an `evolution_kind` attribute was A/B-tested and dropped
# 2026-06-03: the model collapsed all evolution to one bucket, emitting zero finer kinds on 10 papers.)
REFERENCE_EDGE_ROLES: frozenset[str] = frozenset({"builds_on", "uses", "compares_to"})
# The reference-eligible subset of the edge vocabulary. `background` is intentionally absent (no edge).
REFERENCE_EDGE_ORIGIN = "reference"
UNIT_ID_PREFIX_BY_TYPE: dict[str, str] = {
    "Document": "doc:",
    "Problem": "prb:",
    "Finding": "fnd:",
    "Method": "mth:",
    "ExperimentSetup": "exp:",
    "Measure": "mea:",
}
ALLOWED_FIELDS_BY_TYPE: dict[str, set[str]] = {
    "Document": {"id", "type", "doc_id", "title", "role", "thesis", "headline_result", "provenance"},
    "Problem": {"id", "type", "description", "provenance"},
    "Method": {
        "id",
        "type",
        "role",
        "name",
        "method_kind",
        "description",
        "inputs",
        "outputs",
        "formulas",
        "objective_function",
        "implementation_notes",
        "cite_keys",
        "provenance",
    },
    # ExperimentSetup = old Entity ⊎ Setting. `role` is the merged differentia (substrate vs
    # configuration); `name` labels it (a dataset name, a split label); `description` is
    # optional prose. `cite_keys` (the in-text bibliography marker(s)) is copied from the census
    # node onto the unit by _assign_roles_from_census — present only on externally-cited substrate
    # nodes (dataset/benchmark), absent on born configuration roles.
    "ExperimentSetup": {
        "id",
        "type",
        "role",
        "name",
        "description",
        "cite_keys",
        "provenance",
    },
    "Measure": {
        "id",
        "type",
        "name",
        "unit",
        "scores",
        "setup_ids",
        "comparison_direction",
        "objective_class",
        # Blob-primary evidence (section-ir-0.12, all optional): the Measure points at its source
        # table by [§N] marker rather than transcribing every comparison row. `source_table_marker`
        # / `caption_marker` are the [§N] block ids of the <table> and its caption (code slices both
        # verbatim); `table_role` classifies the table; `headline_result` is the contribution's key
        # one-liner (the #2 backstop, kept even for ablations); `finding_ids` mounts the Findings
        # this table evidences (replacing the Finding<->Measure edges).
        "source_table_marker",
        "caption_marker",
        "table_role",
        "headline_result",
        "finding_ids",
        "provenance",
    },
    "Finding": {
        "id",
        "type",
        "role",
        "statement",
        # Optional FG-11 quantitative payload (section-ir-0.10); omitted when unstated.
        "polarity",
        "effect_size",
        "scope",
        "provenance",
    },
}
ALLOWED_SECTION_FIELDS = {"section_type", "anchor_id", "covers_entries", "units"}
# Unit fields that hold a list of unit-id references (rewritten on dedup). In 0.9
# only Measure.setup_ids remains a reference-list field (it points at the section-local
# ExperimentSetup units the measure is scoped by).
REFERENCE_LIST_FIELDS = ("setup_ids",)


def load_prompt(path: Path) -> tuple[str, str]:
    """Load a markdown prompt file and return (system_prompt, user_template)."""
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", text, re.DOTALL)
    if len(blocks) < 2:
        raise ValueError(f"Expected at least 2 fenced code blocks in {path}")
    return blocks[0].strip(), blocks[-1].strip()


def _sanitize_schema_for_gemini(schema: Any) -> Any:
    """Recursively strip Gemini-unsupported JSON Schema features."""
    if isinstance(schema, list):
        return [_sanitize_schema_for_gemini(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        if key == "type" and isinstance(value, list):
            non_null = [t for t in value if t != "null"]
            result[key] = non_null[0] if len(non_null) == 1 else value
        else:
            result[key] = _sanitize_schema_for_gemini(value)
    return result


def _needs_schema_sanitize(model: str) -> bool:
    """Only Gemini models need schema sanitization."""
    return "gemini" in model.lower()


def _is_deepseek_model(model: str) -> bool:
    """Official DeepSeek models (deepseek-chat / deepseek-reasoner / deepseek-v4-pro / ...).

    They are served on api.deepseek.com, which (a) supports only `response_format` `text` and
    `json_object` — never `json_schema` strict decoding — and (b) rejects the OpenAI-proxy
    `prompt_cache_key`/`prompt_cache_retention` kwargs (its context caching is automatic). Both
    facts are keyed off this one check.
    """
    return "deepseek" in model.lower()


def _structured_output_mode(model: str) -> str:
    """How this model accepts a structured-output constraint.

    - ``"json_schema"`` (default): the model constrains decoding to a JSON schema via
      ``response_format`` (the OpenAI-compatible / Gemini proxy). The schema does the enforcing.
    - ``"json_object"`` (DeepSeek): the model only guarantees *some* valid JSON object; the
      schema cannot be sent, so the shape must be spelled out in the prompt instead (see
      ``schema_to_prompt_spec`` / ``_augment_prompt_for_json_object``).
    """
    return "json_object" if _is_deepseek_model(model) else "json_schema"


def _supports_prompt_cache_kwargs(model: str) -> bool:
    """Whether the endpoint accepts the explicit prompt-cache routing kwargs.

    The OpenAI-compatible proxy does; the official DeepSeek API does not (caching is automatic
    and unknown params 400), so they are omitted there.
    """
    return not _is_deepseek_model(model)


def _schema_type_label(schema: Any) -> str:
    """A short, human-readable label for one property's type, surfacing the constraints that
    matter once strict decoding is gone: enum members, id pattern, array item type, nullability.
    """
    if not isinstance(schema, dict):
        return "any"
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        if len(enum) == 1:
            return f'the constant "{enum[0]}"'
        return "one of [" + ", ".join(str(value) for value in enum) + "]"
    typ = schema.get("type")
    if isinstance(typ, list):
        non_null = [t for t in typ if t != "null"]
        label = " or ".join(non_null) if non_null else "value"
        if "null" in typ:
            label += " (nullable — use null when unknown)"
        return label
    if typ == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            item_enum = items.get("enum")
            if isinstance(item_enum, list) and item_enum:
                return "array; each item one of [" + ", ".join(str(v) for v in item_enum) + "]"
            if items.get("type") == "object":
                return "array of objects"
            return f"array of {_schema_type_label(items)}"
        return "array"
    if typ == "object":
        return "object"
    if isinstance(typ, str):
        label = typ
        if schema.get("pattern"):
            label += f' (matching {schema["pattern"]})'
        return label
    return "value"


def _render_schema_object(obj_schema: dict[str, Any], indent: str, lines: list[str]) -> None:
    """Render an object schema's properties as an indented, annotated key list, recursing into
    nested objects and arrays-of-objects."""
    props = obj_schema.get("properties")
    if not isinstance(props, dict):
        return
    required = set(obj_schema.get("required", []) or [])
    for key, prop in props.items():
        if not isinstance(prop, dict):
            continue
        is_required = key in required
        req = "required" if is_required else "optional — omit the key entirely when it does not apply"
        desc = prop.get("description", "")
        suffix = f" — {desc}" if desc else ""
        lines.append(f'{indent}- "{key}" ({_schema_type_label(prop)}, {req}){suffix}')
        if prop.get("type") == "object":
            _render_schema_object(prop, indent + "    ", lines)
        elif prop.get("type") == "array":
            items = prop.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                lines.append(f"{indent}    — each array item is an object with:")
                _render_schema_object(items, indent + "      ", lines)


def schema_to_prompt_spec(schema: dict[str, Any]) -> str:
    """Render a JSON Schema into an in-prompt OUTPUT FORMAT CONTRACT.

    Used for json_object-mode models (DeepSeek) that cannot constrain decoding with the schema:
    the same schema that strict models receive in ``response_format`` is spelled out here so the
    shape, enums, required/optional fields, and id patterns are stated in the prompt. Derived
    straight from the schema, so it never drifts from the runtime contract.
    """
    title = schema.get("title", "")
    description = schema.get("description", "")
    lines: list[str] = [
        "OUTPUT FORMAT CONTRACT",
        "Your response is constrained to a single JSON object by response_format=json_object, but "
        "its exact shape is NOT checked by the decoder — it is enforced only by this contract, so "
        "follow it precisely.",
        "",
    ]
    if title:
        lines.append(f"Target: {title}")
    if description:
        lines.append(description)
    if title or description:
        lines.append("")
    lines.append(
        "Emit a single top-level JSON object with exactly these keys (add no key to any object "
        "beyond those listed here):"
    )
    _render_schema_object(schema, "", lines)
    lines += [
        "",
        "Hard output rules:",
        "- Output ONLY the JSON object — no markdown code fences, no comments, no prose before or after it.",
        "- Include every key marked 'required'. For an 'optional' key, omit the key entirely (do "
        'not emit null or "") when it does not apply, unless its description says otherwise.',
        "- Use only the exact enum values listed; never invent an enum value or an extra key.",
        "- Every id must match the lowercase prefix:descriptor pattern shown.",
    ]
    return "\n".join(lines)


class ValidationError(Exception):
    """Raised when strict pipeline validation finds section-IR issues."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        details = "\n- ".join(issues)
        super().__init__(f"Section-IR validation failed:\n- {details}")


def build_response_format(schema: dict, name: str = "response", model: str = "") -> dict:
    """Build the ``response_format`` for the model's structured-output mode.

    - json_object models (DeepSeek): ``{"type": "json_object"}`` — the schema is conveyed in the
      prompt instead (``_augment_prompt_for_json_object``), since decoding cannot be schema-bound.
    - json_schema models (default, e.g. the OpenAI-compatible / Gemini proxy): strict
      ``json_schema`` (Gemini's schema is first stripped of unsupported features).
    """
    if _structured_output_mode(model) == "json_object":
        return {"type": "json_object"}
    final = _sanitize_schema_for_gemini(schema) if _needs_schema_sanitize(model) else schema
    return {"type": "json_schema", "json_schema": {"name": name, "schema": final, "strict": True}}


def _augment_prompt_for_json_object(prompt: str, schema: dict[str, Any], model: str) -> str:
    """Append the schema's OUTPUT FORMAT CONTRACT to ``prompt`` for json_object-only models;
    return ``prompt`` unchanged for json_schema models (they get the schema via response_format).
    """
    if _structured_output_mode(model) != "json_object":
        return prompt
    return f"{prompt}\n\n{schema_to_prompt_spec(schema)}"


def load_section_schema(section_type: str) -> dict:
    """Load the per-section schema for structured output."""
    filename = SECTION_SCHEMA_FILES.get(section_type)
    if not filename:
        raise ValueError(f"No schema file registered for section_type: {section_type}")
    path = SCHEMAS_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def load_section_module(section_type: str, blob_primary_evidence: bool = False) -> str:
    """Load the per-section focus module text for prompt injection.

    When ``blob_primary_evidence`` is set, the evidence section uses the blob-primary module
    (``evidence-blob.md``) — the LLM points at result tables by ``[§N]`` marker and transcribes only
    the contribution method's rows, instead of retyping every baseline. All other sections, and the
    flag-off evidence path, use ``{section_type}.md`` unchanged.
    """
    name = section_type
    if blob_primary_evidence and section_type == "evidence":
        name = "evidence-blob"
    path = SECTION_MODULES_DIR / f"{name}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_node_census_schema() -> dict:
    """Load the node-census (stage A) schema for structured output."""
    return json.loads(NODE_CENSUS_SCHEMA_PATH.read_text(encoding="utf-8"))


def load_relation_pass_schema() -> dict:
    """Load the relation-pass (stage B) schema for structured output."""
    return json.loads(RELATION_PASS_SCHEMA_PATH.read_text(encoding="utf-8"))


def _flatten_typed_arrays(section_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge typed unit arrays back into a single units list for IR assembly."""
    units: list[dict[str, Any]] = []
    for array_key, expected_type in TYPED_ARRAY_KEYS.items():
        array_value = section_data.get(array_key, [])
        if not isinstance(array_value, list):
            continue
        for unit in array_value:
            if isinstance(unit, dict):
                unit.setdefault("type", expected_type)
                units.append(unit)
    return units


def _canonicalize_id_alias(value: Any) -> Any:
    # Map retired/stray id prefixes to their section-ir-0.9 form so a model's old-habit id
    # (a renamed 0.8 type, or the pre-0.8 Context) still resolves to the right unit/edge.
    if not isinstance(value, str) or ":" not in value:
        return value
    prefix, rest = value.split(":", 1)
    alias = {
        "setting": "exp", "set": "exp", "ent": "exp",  # Entity ⊎ Setting -> ExperimentSetup
        "met": "mea",                                   # Metric -> Measure
        "clm": "fnd",                                   # Claim -> Finding
        "ctx": "prb",                                   # Context -> Problem (pre-0.8)
    }
    return f"{alias[prefix]}:{rest}" if prefix in alias else value


def _slugify_id_part(value: str) -> str:
    """Coerce the post-colon part of an id into the ID_RE slug charset ``[a-z0-9_]``.

    Models occasionally emit node ids whose slug carries characters outside the charset —
    uppercase (``mea:mIoU``) or punctuation (``mea:delta_1.25``). Lowercase, collapse any run
    of disallowed characters to a single ``_``, and trim leading/trailing ``_``. Returns ""
    when nothing is salvageable (the caller then leaves the id for strict validation to flag).
    """
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def _canonicalize_section_id_aliases(sections: list[dict[str, Any]]) -> None:
    """Normalize common LLM ID prefix aliases (e.g. setting:/set:/ent: -> exp:) before validation."""
    for section in sections:
        section["anchor_id"] = _canonicalize_id_alias(section.get("anchor_id"))
        covers_entries = section.get("covers_entries")
        if isinstance(covers_entries, list):
            section["covers_entries"] = [_canonicalize_id_alias(item) for item in covers_entries]

        units = section.get("units", [])
        if isinstance(units, list):
            for unit in units:
                if not isinstance(unit, dict):
                    continue
                if "id" in unit:
                    unit["id"] = _canonicalize_id_alias(unit["id"])
                for key in REFERENCE_LIST_FIELDS:
                    values = unit.get(key)
                    if isinstance(values, list):
                        unit[key] = [_canonicalize_id_alias(value) for value in values]


def _canonicalize_relation_aliases(relations: list[dict[str, Any]]) -> None:
    """Normalize ID prefix aliases on global relation endpoints."""
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        for key in ("source_id", "target_id"):
            if key in relation:
                relation[key] = _canonicalize_id_alias(relation[key])


def _covered_entry_ids(sections: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for section in sections:
        covers_entries = section.get("covers_entries")
        if isinstance(covers_entries, list):
            covered.update(item for item in covers_entries if isinstance(item, str))
    return covered


def _rewrite_unit_references(sections: list[dict[str, Any]], replacements: dict[str, str]) -> None:
    if not replacements:
        return
    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            for field in REFERENCE_LIST_FIELDS:
                values = unit.get(field)
                if isinstance(values, list):
                    unit[field] = [replacements.get(value, value) for value in values]


def _rewrite_relation_endpoints(relations: list[dict[str, Any]], replacements: dict[str, str]) -> None:
    """Repoint global relation endpoints whose unit ids were merged away during dedup."""
    if not replacements:
        return
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        for key in ("source_id", "target_id"):
            value = relation.get(key)
            if isinstance(value, str) and value in replacements:
                relation[key] = replacements[value]


def _dedup_experiment_setups(
    sections: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    protected_ids: set[str] | None = None,
) -> list[str]:
    """Merge duplicate ExperimentSetup units with the same name across sections of the same type.

    `protected_ids` (the census node ids) are never merged away: a census-materialized
    ExperimentSetup is authoritative and deliberately distinct, so merging it would silently drop
    one node, which then reads as uncovered while a `should` node still passes validation. The
    `_covered_entry_ids` union is empty here (covers_entries is assigned later in assembly), so the
    census ids passed in are the real protection — born configuration setups still dedup normally.
    """
    seen: dict[tuple[str, str], str] = {}
    protected = set(protected_ids or ()) | _covered_entry_ids(sections)
    replacements: dict[str, str] = {}
    warnings: list[str] = []

    for section in sections:
        section_type = section.get("section_type", "")
        units = section.get("units", [])
        if not isinstance(units, list):
            continue

        ids_to_replace: dict[str, str] = {}
        units_to_keep: list[Any] = []
        for unit in units:
            if not isinstance(unit, dict):
                units_to_keep.append(unit)
                continue
            if unit.get("type") != "ExperimentSetup":
                units_to_keep.append(unit)
                continue

            name = unit.get("name", "")
            if not isinstance(name, str) or not name:
                units_to_keep.append(unit)
                continue

            key = (str(section_type), name)
            unit_id = unit.get("id")
            if key in seen and isinstance(unit_id, str):
                if unit_id in protected:
                    units_to_keep.append(unit)
                    continue
                ids_to_replace[unit_id] = seen[key]
                replacements[unit_id] = seen[key]
                warnings.append(
                    f"Merged duplicate ExperimentSetup {unit_id} into {seen[key]} in {section_type} section"
                )
            else:
                if isinstance(unit_id, str):
                    seen[key] = unit_id
                units_to_keep.append(unit)

        if not ids_to_replace:
            continue

        section["units"] = units_to_keep
        if section.get("anchor_id") in ids_to_replace:
            fallback_anchor = next(
                (
                    unit["id"]
                    for unit in section["units"]
                    if isinstance(unit, dict) and isinstance(unit.get("id"), str)
                ),
                None,
            )
            if fallback_anchor is not None:
                section["anchor_id"] = fallback_anchor

    _rewrite_unit_references(sections, replacements)
    _rewrite_relation_endpoints(relations, replacements)
    if replacements:
        for section in sections:
            covers = section.get("covers_entries")
            if isinstance(covers, list):
                section["covers_entries"] = [
                    replacements.get(entry, entry) if isinstance(entry, str) else entry
                    for entry in covers
                ]
    return warnings


def _dedup_unit_ids(sections: list[dict[str, Any]]) -> list[str]:
    """Drop later duplicate unit definitions and keep links section-local."""
    seen_ids: set[str] = set()
    seen_id_section: dict[str, Any] = {}
    warnings: list[str] = []

    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        section_type = section.get("section_type")

        removed_ids: set[str] = set()
        kept_units: list[Any] = []
        for unit in units:
            if not isinstance(unit, dict):
                kept_units.append(unit)
                continue
            unit_id = unit.get("id")
            if not isinstance(unit_id, str):
                kept_units.append(unit)
                continue
            if unit_id in seen_ids:
                removed_ids.add(unit_id)
                first_section = seen_id_section.get(unit_id)
                if first_section and section_type and first_section != section_type:
                    # The same unit landed in two sections — most often the
                    # experiment/analysis double-count that the parallel split invites.
                    warnings.append(
                        f"Dropped duplicate unit id {unit_id} from {section_type} section; "
                        f"kept the definition in {first_section} section"
                    )
                else:
                    warnings.append(f"Dropped duplicate unit id {unit_id}; kept the first definition")
                continue
            seen_ids.add(unit_id)
            seen_id_section[unit_id] = section_type
            kept_units.append(unit)

        if not removed_ids:
            continue

        section["units"] = kept_units
        local_ids = {
            unit["id"]
            for unit in kept_units
            if isinstance(unit, dict) and isinstance(unit.get("id"), str)
        }

        if section.get("anchor_id") in removed_ids:
            fallback_anchor = next(iter(local_ids), None)
            if fallback_anchor is not None:
                section["anchor_id"] = fallback_anchor
    return warnings


def _drop_empty_sections(sections: list[dict[str, Any]]) -> list[str]:
    """Drop sections left with no units, mutating the list in place.

    Over-splitting can leave a section the model never filled (e.g. a second method
    section whose content all landed in the first). An empty section has no unit to
    anchor on, so it can never satisfy the anchor contract and contributes nothing —
    drop it rather than fail the whole extraction.
    """
    warnings: list[str] = []
    kept: list[dict[str, Any]] = []
    for section in sections:
        units = section.get("units")
        has_unit = isinstance(units, list) and any(
            isinstance(unit, dict) and isinstance(unit.get("id"), str) for unit in units
        )
        if has_unit:
            kept.append(section)
        else:
            warnings.append(
                f"Dropped empty {section.get('section_type')} section with no extracted units"
            )
    if len(kept) != len(sections):
        sections[:] = kept
    return warnings


def _normalize_provenance_markers(
    sections: list[dict[str, Any]], relations: list[dict[str, Any]] | None = None
) -> list[str]:
    """Collapse fine-grained / ranged markers to the top-level §N/§X parent that contains them.

    Paper input carries only top-level section/appendix/block markers, so a finer or ranged
    marker cannot be traced and fails validation, even though a real coarser anchor contains it.
    Rather than discard the marker we collapse it to that parent. This covers dotted subsections
    (§4.3 -> §4, §C.1 -> §C), IEEE-style hyphenated subsections (§IV-D -> §IV, §III-F1 -> §III),
    glued appendix subsections (§A4.2 -> §A, §G2 -> §G), block ranges (§107-108 / §118-§120 -> the
    leading block §107 / §118), and spelled-out appendices (Appendix A.2 / App. D.1 -> §A / §D). A
    stray § glued to a float word (§Table 3 -> Table 3, §Figure 2 (a) -> Figure 2 (a)) has the §
    dropped, since § belongs only on a section/appendix marker. Genuine float references (Table 5,
    Figure 8, Algorithm 1, Lemma 2) have no section parent and are left untouched — the validator
    now accepts them directly, since they name a real, citeable element of the paper.

    Applied to both unit provenance and (when given) global relation provenance, so a relation's
    markers are repaired the same way units' are before relation-provenance validation runs.
    """
    warnings: list[str] = []
    seen: set[str] = set()

    def _collapse(provenance: list[Any]) -> list[Any]:
        rewritten: list[Any] = []
        for marker in provenance:
            if isinstance(marker, str):
                stripped = marker.strip()
                new_marker: str | None = None
                appendix = APPENDIX_SPELLED_RE.match(stripped)
                numbered = APPENDIX_NUMBERED_RE.match(stripped)
                subsection = SUBSECTION_MARKER_RE.match(stripped)
                if stripped.startswith("§") and PROVENANCE_SOURCE_RE.match(stripped[1:].strip()):
                    # A stray § glued to a float word (§Table 3, §Figure 2 (a)): drop the § so
                    # the bare float — itself a valid marker — is what remains.
                    new_marker = stripped[1:].strip()
                elif appendix:
                    new_marker = f"§{appendix.group(1).upper()}"
                elif numbered:
                    new_marker = f"§{numbered.group(1)}"
                elif subsection:
                    new_marker = f"§{subsection.group(1)}"
                if new_marker is not None and new_marker != marker:
                    if marker not in seen:
                        seen.add(marker)
                        warnings.append(f"Normalized provenance marker {marker} to {new_marker}")
                    rewritten.append(new_marker)
                    continue
            rewritten.append(marker)
        return rewritten

    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            provenance = unit.get("provenance")
            if isinstance(provenance, list):
                unit["provenance"] = _collapse(provenance)

    for relation in relations or []:
        if not isinstance(relation, dict):
            continue
        provenance = relation.get("provenance")
        if isinstance(provenance, list):
            relation["provenance"] = _collapse(provenance)

    return warnings


def _build_unit_type_index(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Index unit type by unit id across all sections."""
    type_by_id: dict[str, Any] = {}
    for section in sections:
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                type_by_id[unit["id"]] = unit.get("type")
    return type_by_id


def _dedup_relations(relations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop duplicate global relations keyed by (source_id, relation, target_id)."""
    seen: set[tuple[Any, Any, Any]] = set()
    kept: list[dict[str, Any]] = []
    dropped = 0
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        key = (relation.get("source_id"), relation.get("relation"), relation.get("target_id"))
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(relation)
    warnings = [f"Dropped {dropped} duplicate relation(s)"] if dropped else []
    return kept, warnings


def _drop_dangling_relations(
    relations: list[dict[str, Any]], sections: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop global relations whose source or target resolves to no defined unit."""
    type_by_id = _build_unit_type_index(sections)
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        src = relation.get("source_id")
        tgt = relation.get("target_id")
        if src not in type_by_id or tgt not in type_by_id:
            warnings.append(
                f"Dropped dangling relation {src} -[{relation.get('relation')}]-> {tgt}: "
                "endpoint resolves to no unit"
            )
            continue
        kept.append(relation)
    return kept, warnings


def _drop_invalid_relations(
    relations: list[dict[str, Any]], sections: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop global relations that violate the relation type matrix.

    The model sometimes emits relations the IR cannot represent (a `compares_to`
    between two Findings, an `evaluates` onto a non-Method). Such edges are
    unassemblable, so remove them with a warning instead of failing the extraction.
    Self-loops (source_id == target_id) are also dropped: no relation type is
    meaningfully reflexive (a method is not part_of/builds_on/compares_to itself),
    and the relation pass occasionally emits one for the contribution node.
    """
    type_by_id = _build_unit_type_index(sections)
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        rel = relation.get("relation")
        src = relation.get("source_id")
        tgt = relation.get("target_id")
        if src is not None and src == tgt:
            warnings.append(f"Dropped self-loop relation {src} -[{rel}]-> {tgt}")
            continue
        matrix = RELATION_MATRIX.get(rel)
        if matrix is None:
            warnings.append(f"Dropped relation with invalid relation {rel!r}")
            continue
        allowed_sources, allowed_targets = matrix
        src_type = type_by_id.get(src)
        tgt_type = type_by_id.get(tgt)
        if src_type not in allowed_sources or tgt_type not in allowed_targets:
            warnings.append(
                f"Dropped relation {src} -[{rel}]-> {tgt}: invalid type pairing "
                f"({src_type} -> {tgt_type})"
            )
            continue
        kept.append(relation)
    return kept, warnings


def _repair_section_anchors(sections: list[dict[str, Any]]) -> list[str]:
    """Re-point anchors that name a unit not defined in their own section.

    A section may anchor on an external id (e.g. an experiment section anchoring on
    the main `mth:` method, which lives in the method section). The anchor must be a
    local, non-Document unit. Prefer re-pointing to a local unit of the section's
    natural anchor type (evidence -> Measure, ...) so the repaired
    anchor stays semantically meaningful, then fall back to the first local unit.
    """
    warnings: list[str] = []
    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        local_non_doc = [
            unit
            for unit in units
            if isinstance(unit, dict)
            and isinstance(unit.get("id"), str)
            and unit.get("type") != "Document"
        ]
        if not local_non_doc:
            continue
        local_ids = [unit["id"] for unit in local_non_doc]
        anchor_id = section.get("anchor_id")
        if anchor_id in local_ids:
            continue
        preferred_type = SECTION_PREFERRED_ANCHOR_TYPE.get(section.get("section_type"))
        replacement = next(
            (unit["id"] for unit in local_non_doc if unit.get("type") == preferred_type),
            local_ids[0],
        )
        section["anchor_id"] = replacement
        warnings.append(
            f"Reset {section.get('section_type')} section anchor_id from {anchor_id!r} "
            f"to {replacement}: not defined in section"
        )
    return warnings


def _assign_covers_entries(
    sections: list[dict[str, Any]], census_node_ids: set[str]
) -> None:
    """Recompute each section's covers_entries as the census node ids it materialized.

    With section-ir-0.7 a census `node_id` is reused verbatim as the final unit id, so a
    section's coverage is exactly the set of census nodes whose unit it defines. Deriving
    it here (rather than trusting the model to echo the trace) keeps covers_entries always
    consistent and lets census `must` nodes that were never materialized surface honestly
    in extraction_notes.uncovered_items.

    Runs last in assembly, after every step that can remove or merge units.
    """
    for section in sections:
        local_ids = [
            unit["id"]
            for unit in section.get("units", []) or []
            if isinstance(unit, dict) and isinstance(unit.get("id"), str)
        ]
        section["covers_entries"] = sorted(uid for uid in local_ids if uid in census_node_ids)


def _assign_roles_from_census(sections: list[dict[str, Any]], census: dict[str, Any] | None) -> None:
    """Stamp census-committed attributes (role, cite_keys) onto each materialized unit (0.9).

    `role` is a first-class unit field, but for census-materialized units (Method and the
    substrate-role ExperimentSetup nodes) the census already committed the role — so inject it
    here authoritatively rather than trusting the content model to echo it. Born units
    (configuration ExperimentSetup, Finding) author their own role and are left untouched.
    Measure carries no role even though its census node's role is the degenerate "metric".

    `cite_keys` (the in-text bibliography marker(s) the node was cited as) likewise lives only on
    the census node. Copy it onto the materialized Method/ExperimentSetup unit (node_id == unit_id)
    so a downstream consumer reading the assembled extraction alone can join a unit back to the
    bibliography — and across papers, a baseline to the paper that introduced it — without the
    census in hand. Non-empty only for prior-art/testbed nodes (builds_on/compared_against/
    dataset/benchmark); the contribution, components, tasks, and measures carry [], which is left
    off the unit rather than stamped as an empty list.
    """
    if not census:
        return
    node_by_id = {
        node["node_id"]: node
        for node in iter_census_nodes(census)
        if isinstance(node.get("node_id"), str)
    }
    for section in sections:
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict):
                continue
            node = node_by_id.get(unit.get("id"))
            if node is None:
                continue
            unit_type = unit.get("type")
            if unit_type in ROLE_VOCAB_BY_TYPE:
                census_role = node.get("role")
                # Only stamp a census role that is valid for the unit's type. For a census-
                # materialized Method/substrate-ExperimentSetup the census role IS the unit role.
                # But the FG-5 `contribution_finding` root materializes as a Finding, and
                # `contribution_finding` is not a Finding.role — the evidence section authors that
                # finding's content role (mechanistic/comparative/...), so leave it untouched.
                if census_role in ROLE_VOCAB_BY_TYPE[unit_type]:
                    unit["role"] = census_role
            # Only prior-art/testbed nodes legitimately carry cite_keys, and only Method/
            # ExperimentSetup whitelist the field. A Measure census node is spec'd to carry [],
            # but a model sometimes emits a stray marker on a cited metric ("boundary F1 [12]");
            # guarding by unit type keeps that out of the Measure unit (which would fail validation).
            cite_keys = node.get("cite_keys")
            if unit.get("type") in {"Method", "ExperimentSetup"} and isinstance(cite_keys, list) and cite_keys:
                unit["cite_keys"] = list(cite_keys)


def parse_sections(paper_content: str) -> dict[str, str]:
    """Split paper text into a mapping from section marker number to text block."""
    matches = list(SECTION_MARKER_RE.finditer(paper_content))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        section_id = match.group(1)
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(paper_content)
        sections[section_id] = paper_content[start:end].strip()
    return sections


def iter_census_nodes(census: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the census node objects."""
    nodes = census.get("nodes")
    return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []


def all_census_node_ids(census: dict[str, Any]) -> set[str]:
    return {
        node["node_id"]
        for node in iter_census_nodes(census)
        if isinstance(node.get("node_id"), str)
    }


def census_must_node_ids(census: dict[str, Any]) -> set[str]:
    return {
        node["node_id"]
        for node in iter_census_nodes(census)
        if node.get("salience") == "must" and isinstance(node.get("node_id"), str)
    }


def normalize_census_nodes(census: dict[str, Any]) -> dict[str, Any]:
    """Repair section-obvious node-census problems before strict validation.

    - Derive each node's `type` from its `role` (role is the single granular tag the model
      emits; type and document root are coarsenings of it).
    - Rebuild each node_id from its derived-type prefix plus a sanitized slug: fix a prefix that
      disagrees with the type (mth:/exp:/mea:) and coerce the slug into the ID_RE charset, so a
      model id with uppercase or punctuation (mea:mIoU, mea:delta_1.25) is salvaged rather than
      hard-failing the census.
    - Suffix later duplicate node_ids so each is defined exactly once.
    - Ensure exactly one document-level root (role `contribution` for a Method, or
      `contribution_resource` for an ExperimentSetup deliverable; FG-1): promote the strongest
      node when none is marked, demote extras to a non-root role of their type when several are.
    """
    normalized = copy.deepcopy(census)
    nodes = iter_census_nodes(normalized)

    for node in nodes:
        derived = ROLE_TO_TYPE.get(node.get("role"))
        if derived:
            node["type"] = derived

    for node in nodes:
        node_id = node.get("node_id")
        expected = NODE_ID_PREFIX_BY_TYPE.get(node.get("type"))
        if not isinstance(node_id, str) or not expected:
            continue
        raw_slug = node_id.split(":", 1)[1] if ":" in node_id else node_id
        slug = _slugify_id_part(raw_slug)
        if not slug:
            continue
        candidate = f"{expected}{slug}"
        if candidate != node_id and ID_RE.match(candidate):
            node["node_id"] = candidate

    used_ids: set[str] = set()
    for node in nodes:
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or not ID_RE.match(node_id):
            continue
        if node_id not in used_ids:
            used_ids.add(node_id)
            continue
        prefix, slug = node_id.split(":", 1)
        index = 2
        new_id = f"{prefix}:{slug}_{index}"
        while new_id in used_ids:
            index += 1
            new_id = f"{prefix}:{slug}_{index}"
        node["node_id"] = new_id
        used_ids.add(new_id)

    method_nodes = [node for node in nodes if node.get("type") == "Method"]
    roots = [node for node in nodes if node.get("role") in CONTRIBUTION_ROLES]
    if not roots:
        # No root tagged. Promote the strongest node: prefer a must-Method (the empirical-paper
        # common case) as `contribution`, else a must-ExperimentSetup (a benchmark/dataset paper)
        # as `contribution_resource`.
        chosen = next((n for n in method_nodes if n.get("salience") == "must"), None)
        if chosen is None and method_nodes:
            chosen = method_nodes[0]
        if chosen is not None:
            chosen["role"] = CONTRIBUTION_ROLE
        else:
            exp_nodes = [n for n in nodes if n.get("type") == "ExperimentSetup"]
            promote = next((n for n in exp_nodes if n.get("salience") == "must"), None)
            if promote is None and exp_nodes:
                promote = exp_nodes[0]
            if promote is not None:
                promote["role"] = "contribution_resource"
    elif len(roots) > 1:
        # Co-equal primary contributions (FG-7): a paper may deliver two roots that neither
        # contains (a method AND a benchmark, or two independent algorithms presented as joint
        # results). Keep every `must` root as a co-equal contribution — the relation pass links
        # them with `co_contribution` and `_assign_resolves` fans the discovery arc across it.
        # Demote only the weaker `should` "roots": a genuine co-contribution is must-salient, so a
        # should-salient extra root is almost always a mis-tag, and demoting it stops a flood of
        # speculative roots from surviving (when no root is `must`, keep just the first).
        must_roots = [n for n in roots if n.get("salience") == "must"]
        keep_ids = {id(n) for n in (must_roots or roots[:1])}
        for extra in roots:
            if id(extra) not in keep_ids:
                extra["role"] = "component" if extra.get("type") == "Method" else "benchmark"
    return normalized


def validate_census(census: dict[str, Any]) -> list[str]:
    """Validate node-census output before the relation and content stages run."""
    issues: list[str] = []
    if not isinstance(census, dict):
        return ["Census must be a JSON object"]

    spine_summary = census.get("spine_summary")
    if not isinstance(spine_summary, dict):
        issues.append("Census spine_summary must be an object")
    else:
        for key in ("central_contribution", "argument_flow"):
            if not spine_summary.get(key):
                issues.append(f"Census spine_summary missing {key}")
        # headline_result (FG-9, optional): when present it must be a non-empty string. It is a
        # planning-time annotation of the paper's headline result for result-centric papers, not a node.
        headline_result = spine_summary.get("headline_result")
        if headline_result is not None and (
            not isinstance(headline_result, str) or not headline_result.strip()
        ):
            issues.append("Census spine_summary headline_result must be a non-empty string when present")

    nodes = census.get("nodes")
    if not isinstance(nodes, list):
        issues.append("Census nodes must be a list")
        return issues

    seen_ids: set[str] = set()
    method_count = 0
    root_count = 0
    for node in nodes:
        if not isinstance(node, dict):
            issues.append("Census node must be an object")
            continue
        node_id = node.get("node_id")
        role = node.get("role")
        label = node_id if isinstance(node_id, str) else "<missing-id>"
        if not isinstance(node_id, str) or not ID_RE.match(node_id):
            issues.append(f"Census node has invalid node_id: {node_id}")
        elif node_id in seen_ids:
            issues.append(f"Duplicate census node_id: {node_id}")
        else:
            seen_ids.add(node_id)
        node_type = ROLE_TO_TYPE.get(role)
        if node_type is None:
            issues.append(f"Census node {label} has invalid role: {role}")
        elif isinstance(node_id, str):
            expected = NODE_ID_PREFIX_BY_TYPE[node_type]
            if not node_id.startswith(expected):
                issues.append(
                    f"Census node {label} has role {role} (type {node_type}) "
                    f"but id prefix is not {expected!r}"
                )
        if node.get("salience") not in SALIENCE_LEVELS:
            issues.append(f"Census node {label} has invalid salience: {node.get('salience')}")
        cite_keys = node.get("cite_keys")
        if cite_keys is not None and (
            not isinstance(cite_keys, list)
            or any(not isinstance(key, str) for key in cite_keys)
        ):
            issues.append(f"Census node {label} cite_keys must be a list of strings")
        # name/gloss/source_scope are schema-required on every node. Strict decoding enforces them
        # in json_schema mode, but json_object (DeepSeek) mode treats the schema as prompt guidance
        # only, so the stage-A contract must check them here. `name` is the reconcile join key and
        # the materialized unit's name, so an empty one is a hard defect.
        name = node.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append(f"Census node {label} must have a non-empty name")
        gloss = node.get("gloss")
        if not isinstance(gloss, str) or not gloss.strip():
            issues.append(f"Census node {label} must have a non-empty gloss")
        source_scope = node.get("source_scope")
        if not isinstance(source_scope, list) or any(
            not isinstance(marker, str) for marker in source_scope
        ):
            issues.append(f"Census node {label} source_scope must be a list of strings")
        if node_type == "Method":
            method_count += 1
        if role in CONTRIBUTION_ROLES:
            root_count += 1

    # At least one document root: a `contribution` Method or a `contribution_resource`
    # ExperimentSetup (FG-1). Normally exactly one, but a paper with co-equal primary
    # deliverables (a method AND a benchmark, or two independent algorithms) marks each as a
    # root and the relation pass links them with `co_contribution` (FG-7), so root_count > 1 is
    # valid. Only a complete absence of a root (when something is rootable) is a contract defect.
    if (method_count or root_count) and root_count < 1:
        issues.append(
            "Census must mark at least one contribution root (contribution or "
            "contribution_resource); found 0"
        )
    return issues


def build_node_registry(census: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the lightweight all-node registry passed to the relation and content stages.

    Carries what later stages need to reference and route a node: id, type, name, gloss,
    salience, and the granular `role` with its search `cluster`. The role lets the relation
    pass route edges (a `component` is part_of the `contribution`; a `compared_against`
    method is compares_to it) and the content stage find the contribution method. The `role`
    is carried straight onto the materialized unit as its fine-grained differentia.
    """
    registry: list[dict[str, Any]] = []
    for node in iter_census_nodes(census):
        role = node.get("role")
        node_type = ROLE_TO_TYPE.get(role, node.get("type"))
        entry: dict[str, Any] = {
            "node_id": node.get("node_id"),
            "type": node_type,
            "role": role,
            "cluster": ROLE_CLUSTER.get(role, ""),
            "name": node.get("name", ""),
            "gloss": node.get("gloss", ""),
            "salience": node.get("salience", "should"),
        }
        registry.append(entry)
    return registry


def render_content_user_prompt(
    paper_content: str,
    section_type: str,
    section_module: str,
    node_registry: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    spine_summary: dict[str, Any] | None = None,
) -> str:
    """Render the cache-friendly content-extraction user prompt for one section.

    The fixed intro line, the paper, spine_summary, node_registry, and relations blocks are
    byte-identical across all four content sections so the cross-section prompt cache stays
    warm; only `section_focus` and the trailing instruction's section name vary.
    """
    node_registry_json = json.dumps(node_registry, ensure_ascii=False, indent=2)
    relations_json = json.dumps(relations, ensure_ascii=False, indent=2)
    spine_summary_json = (
        json.dumps(spine_summary, ensure_ascii=False, indent=2) if spine_summary else "{}"
    )
    section_guidance = section_module.strip() or "No additional section guidance."

    return f"""Extract the requested section from the paper.

<paper>
{paper_content}
</paper>

<spine_summary>
{spine_summary_json}
</spine_summary>

<node_registry>
{node_registry_json}
</node_registry>

<relations>
{relations_json}
</relations>

<section_focus>
{section_guidance}
</section_focus>

Extract ONLY the {section_type} section, following `section_focus`:
- Materialize the census nodes this section owns into full units, reusing each `node_id` verbatim as the unit `id`, and create the born units this section is responsible for.
- Place each unit in the typed array matching its type, with only the fields its contract names.
- Reference any node in `node_registry` by id; the structural `relations` are already established — do not restate them.
- Emit only the edges your `section_focus` authorizes this section to author (problem: `motivates`; evidence: `about`/`supports`; method: none), in `relations`.
- Use the full paper as source context; extract only this section's role.

Output a single JSON object with key: section.""".strip()


def build_prompt_cache_key(model: str, paper_content: str) -> str:
    """Build a stable OpenAI prompt cache routing key for one paper/model pair."""
    safe_model = re.sub(r"[^A-Za-z0-9_.:-]+", "_", model).strip("_") or "model"
    digest = sha256(paper_content.encode("utf-8")).hexdigest()[:16]
    return f"section-ir:{safe_model}:{digest}"


def _slugify_doc_id(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:30].strip("_") or "paper"


def _derive_document_role(census: dict[str, Any] | None, sections: list[dict[str, Any]]) -> str:
    """Derive the Document genre (FG-3, section-ir-0.10) from the materialized contribution.

    Was a hardcoded literal `research_article` (a dead axis — 763/764 in the 0.9 corpus). The
    reliable signal is what the contribution turned out to be: a dataset/benchmark deliverable
    (a `contribution_resource` materialized as an ExperimentSetup) is a benchmark/dataset paper;
    a `taxonomy` Method is review-like. Everything else stays `research_article`. Genres that need
    true text-level judgement (position/meta_analysis) are not derived here.
    """
    if not isinstance(census, dict):
        return "research_article"
    contribution_ids = {
        node.get("node_id")
        for node in census.get("nodes") or []
        if isinstance(node, dict) and node.get("role") in CONTRIBUTION_ROLES
    }
    contribution_ids.discard(None)
    if not contribution_ids:
        return "research_article"
    for section in sections:
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict) or unit.get("id") not in contribution_ids:
                continue
            if unit.get("type") == "ExperimentSetup":
                return "benchmark_survey"
            if unit.get("type") == "Method" and unit.get("method_kind") == "taxonomy":
                return "review"
            return "research_article"
    return "research_article"


def build_document_unit(
    paper_content: str,
    thesis: str = "",
    document_role: str = "research_article",
    headline_result: str = "",
) -> dict[str, Any]:
    """Build a deterministic Document unit from the paper preamble.

    `thesis` is the one-sentence central contribution; assembly sources it from the census
    `spine_summary.central_contribution` (already extracted and validated non-empty), so no
    extra LLM call is needed. `document_role` is the genre derived by `_derive_document_role`
    (FG-3); it defaults to `research_article` so the builder still works without a census.
    `headline_result` (FG-9, optional) is the census `spine_summary.headline_result` — the paper's
    headline established result for a result-centric paper — lifted on so the finding is first-class
    on the document; omitted entirely when the census did not state one (ordinary artifact paper).
    """
    first_marker = paper_content.find("[§")
    preamble = paper_content[:first_marker] if first_marker >= 0 else paper_content[:500]
    title_match = re.search(r"^#\s+(.+)", preamble, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = next((line.strip() for line in preamble.splitlines() if line.strip()), "Untitled")
    doc_id = _slugify_doc_id(title)
    document: dict[str, Any] = {
        "id": f"doc:{doc_id}",
        "type": "Document",
        "doc_id": doc_id,
        "title": title,
        "role": document_role,
        "thesis": thesis,
        "provenance": [],
    }
    if isinstance(headline_result, str) and headline_result.strip():
        document["headline_result"] = headline_result.strip()
    return document


def build_extraction_notes(
    census: dict[str, Any],
    sections: list[dict[str, Any]],
    sections_included: list[str] | None = None,
    sections_omitted: list[str] | None = None,
    extra_uncovered: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build final extraction notes for assembled content output.

    Coverage is measured against the census `must` nodes: a must-node is covered iff a unit
    reusing its node_id was materialized by some section. node_id == unit_id, so coverage is
    structural and needs no covers_entries echo from the model.

    `extra_uncovered` (FG-10 D1) holds additional `{item_id, reason}` entries for information lost
    during assembly (e.g. a Measure dropped for empty scores) so the canonical `uncovered_items`
    list captures all of it; entries whose item_id is already listed (an uncovered must-node) are
    skipped so a dropped must-Measure is not double-counted.
    """
    sections_used: set[str] = set()
    materialized_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        if isinstance(section.get("section_type"), str):
            sections_used.add(section["section_type"])
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                materialized_ids.add(unit["id"])

    must_nodes = census_must_node_ids(census)
    covered = must_nodes & materialized_ids
    notes: dict[str, Any] = {
        "ir_version": "section-ir-0.12",
        "sections_used": [s for s in SECTION_ORDER if s in sections_used],
        "uncertain_assignments": [],
        "skipped_spans": [],
        "input_mode": "node_census_pipeline",
        "uncovered_items": [
            {"item_id": node_id, "reason": "census must-node not materialized as a unit"}
            for node_id in sorted(must_nodes - covered)
        ],
        "plan_coverage": {
            "must_covered": len(covered),
            "must_total": len(must_nodes),
        },
    }
    if extra_uncovered:
        listed = {item["item_id"] for item in notes["uncovered_items"]}
        for item in extra_uncovered:
            if item.get("item_id") not in listed:
                notes["uncovered_items"].append(item)
                listed.add(item.get("item_id"))
    if sections_included is not None:
        notes["sections_included"] = sections_included
    if sections_omitted is not None:
        notes["sections_omitted"] = sections_omitted
    return notes


# C0 control characters (incl. the NULL bytes some models emit in place of '·'/'×') that have
# no business in extracted text; tab/newline/carriage-return are left alone.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SANITIZE_SKIP_KEYS = {"id", "type"}


def _sanitize_str(value: str) -> str:
    cleaned = _CONTROL_CHAR_RE.sub(" ", value)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned


def _sanitize_unit_text(sections: list[dict[str, Any]]) -> list[str]:
    """Deep-clean control characters out of every unit string value, logging each fix.
    Identifiers (`id`/`type`) are never touched."""
    warnings: list[str] = []

    def clean(obj: Any, owner: str, label: str) -> Any:
        if isinstance(obj, str):
            cleaned = _sanitize_str(obj)
            if cleaned != obj:
                warnings.append(
                    f"Sanitized control characters in {owner} {label}: {obj!r} -> {cleaned!r}"
                )
            return cleaned
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in _SANITIZE_SKIP_KEYS or not isinstance(value, (str, list, dict)):
                    continue
                obj[key] = clean(value, owner, f"{label}.{key}" if label else key)
            return obj
        if isinstance(obj, list):
            for index, item in enumerate(obj):
                if isinstance(item, (str, list, dict)):
                    obj[index] = clean(item, owner, f"{label}[{index}]")
            return obj
        return obj

    for section in sections:
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict):
                clean(unit, unit.get("id", "?"), "")
    return warnings


def _sanitize_unit_ids(
    sections: list[dict[str, Any]], relations: list[dict[str, Any]]
) -> list[str]:
    """Coerce any unit id whose slug carries out-of-charset characters into ID_RE form.

    Census-materialized ids are already valid (normalize_census_nodes), so this only moves
    born-unit ids (Finding/Problem/config ExperimentSetup) a model emitted with uppercase or
    punctuation, e.g. ``fnd:increasing_K_modest`` -> ``fnd:increasing_k_modest``. Every reference
    is rewritten to the new id — relation endpoints, score-row system_id/setup_id,
    Measure.setup_ids, and section anchors — and collisions are suffixed so ids stay unique.
    """
    warnings: list[str] = []

    def sanitized(uid: Any) -> str | None:
        if not isinstance(uid, str) or ":" not in uid:
            return None
        prefix, slug = uid.split(":", 1)
        new_slug = _slugify_id_part(slug)
        return f"{prefix}:{new_slug}" if new_slug else None

    units = [u for s in sections for u in s.get("units", []) or [] if isinstance(u, dict)]
    # Seed the uniqueness set with ids that already survive sanitization unchanged.
    used = {u["id"] for u in units if isinstance(u.get("id"), str) and sanitized(u["id"]) == u["id"]}
    remap: dict[str, str] = {}
    for unit in units:
        uid = unit.get("id")
        candidate = sanitized(uid)
        if candidate is None or candidate == uid:
            continue
        base, index = candidate, 2
        while candidate in used:
            candidate = f"{base}_{index}"
            index += 1
        used.add(candidate)
        remap[uid] = candidate
        unit["id"] = candidate
        warnings.append(f"sanitized unit id {uid!r} -> {candidate!r}")

    if remap:
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            for key in ("source_id", "target_id"):
                if relation.get(key) in remap:
                    relation[key] = remap[relation[key]]
        for section in sections:
            if section.get("anchor_id") in remap:
                section["anchor_id"] = remap[section["anchor_id"]]
            for unit in section.get("units", []) or []:
                if unit.get("type") != "Measure":
                    continue
                setup_ids = unit.get("setup_ids")
                if isinstance(setup_ids, list):
                    unit["setup_ids"] = [remap.get(x, x) for x in setup_ids]
                for row in unit.get("scores", []) or []:
                    if not isinstance(row, dict):
                        continue
                    for key in ("system_id", "setup_id", "opponent_id", "judge_id"):
                        if row.get(key) in remap:
                            row[key] = remap[row[key]]
    return warnings


def _drop_empty_scores_measures(
    sections: list[dict[str, Any]], dropped_out: list[dict[str, str]] | None = None
) -> list[str]:
    """Drop Measure units with an empty/missing ``scores`` list — a measure with no rows carries
    no data and is schema-invalid. Edges that pointed at it are pruned by the later relation
    dangling-check. Lossy-but-safe; logged to uncertain_assignments.

    0.12 (blob-primary) exception: a Measure with empty scores that carries a ``source_table_marker``
    is an **ablation/table-blob** measure — its data is the code-sliced verbatim table, not transcribed
    rows — so it is kept. Only a marker-less empty Measure (a metric the model named but could not
    fill) is dropped.

    FG-10 D1 (section-ir-0.10): each drop is also recorded in ``dropped_out`` (when provided) as a
    structured ``{item_id, reason}`` so assembly can surface it in ``extraction_notes.uncovered_items``
    — the canonical "what was not captured" list — instead of leaving the loss only in the free-text
    ``uncertain_assignments``. This makes a measure the model surfaced but could not fill (a metric
    named with no extractable rows) visible to a downstream consumer scanning a single field."""
    warnings: list[str] = []
    for section in sections:
        units = section.get("units")
        if not isinstance(units, list):
            continue
        kept: list[dict[str, Any]] = []
        for unit in units:
            scores = unit.get("scores")
            has_marker = bool(unit.get("source_table_marker"))
            if unit.get("type") == "Measure" and not (isinstance(scores, list) and scores) and not has_marker:
                warnings.append(f"dropped Measure {unit.get('id')!r} with empty scores")
                if dropped_out is not None and isinstance(unit.get("id"), str):
                    dropped_out.append(
                        {"item_id": unit["id"], "reason": "Measure dropped: empty scores (no extractable rows)"}
                    )
            else:
                kept.append(unit)
        section["units"] = kept
    return warnings


def _clean_method_equations(sections: list[dict[str, Any]]) -> list[str]:
    """Drop empty optional equation fields on Method units: an ``objective_function`` or a
    ``formulas[]`` entry whose ``expression`` is blank (a stub some json_object models emit when
    a paper has no equation). The fields are optional, so dropping them is safe and removes the
    'missing expression' validation failure. Logged to uncertain_assignments."""
    warnings: list[str] = []
    for section in sections:
        for unit in section.get("units", []) or []:
            if unit.get("type") != "Method":
                continue
            objective = unit.get("objective_function")
            if objective is not None and not (
                isinstance(objective, dict) and (objective.get("expression") or "").strip()
            ):
                unit.pop("objective_function", None)
                warnings.append(f"dropped empty objective_function on {unit.get('id')!r}")
            formulas = unit.get("formulas")
            if isinstance(formulas, list):
                kept = [
                    f for f in formulas
                    if isinstance(f, dict) and (f.get("expression") or "").strip()
                ]
                if len(kept) != len(formulas):
                    warnings.append(
                        f"dropped {len(formulas) - len(kept)} empty formula(s) on {unit.get('id')!r}"
                    )
                if kept:
                    unit["formulas"] = kept
                else:
                    unit.pop("formulas", None)
    return warnings


BASELINE_METHOD_BANNED_FIELDS = ("inputs", "outputs", "formulas", "objective_function")


def _strip_baseline_method_fields(
    sections: list[dict[str, Any]], census: dict[str, Any] | None
) -> list[str]:
    """For Method units the census tagged ``compared_against``, drop the heavy optional fields the
    method-section contract bans on baselines: ``objective_function``, ``formulas``, ``inputs``,
    ``outputs``. Baselines exist as structural anchors for ``compares_to`` + score-row ``system_id``;
    reconstructing technical detail invites hallucination (e.g. fabricated objective_functions on
    black-box baselines) and inflates output tokens. Lossy-but-safe; logged."""
    if not census:
        return []
    baseline_ids = {
        node.get("node_id")
        for node in (census.get("nodes") or [])
        if isinstance(node, dict) and node.get("role") == "compared_against"
    }
    baseline_ids.discard(None)
    if not baseline_ids:
        return []
    warnings: list[str] = []
    for section in sections:
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict):
                continue
            if unit.get("type") != "Method" or unit.get("id") not in baseline_ids:
                continue
            for field in BASELINE_METHOD_BANNED_FIELDS:
                if field in unit:
                    if unit[field] not in (None, "", [], {}):
                        warnings.append(
                            f"stripped {field} on baseline Method {unit.get('id')!r} "
                            "(census role=compared_against)"
                        )
                    unit.pop(field, None)
    return warnings


def _repair_score_refs(sections: list[dict[str, Any]]) -> list[str]:
    """Blank dangling or wrong-type per-row score references once the full unit set is known —
    lossy-but-safe, logged to uncertain_assignments. system_id/opponent_id resolve globally to a
    Method; setup_id resolves to a section-local ExperimentSetup; judge_id (FG-6) resolves globally
    to a Method or ExperimentSetup (an LLM/human judge). The Measure-level `setup_ids[]` list is
    pruned the same way (dangling/non-local/wrong-type entries dropped), so one stray setup
    declaration — e.g. a setup the model named in `setup_ids` but never materialized — does not
    hard-fail an otherwise-sound measure; list entries are dropped, not blanked (an empty string
    would re-fail the section-local check)."""
    warnings: list[str] = []
    unit_index = {
        unit["id"]: unit
        for section in sections
        for unit in section.get("units", []) or []
        if isinstance(unit, dict) and unit.get("id")
    }
    for section in sections:
        local_ids = {
            unit.get("id") for unit in section.get("units", []) or [] if isinstance(unit, dict)
        }
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict) or unit.get("type") != "Measure":
                continue
            for index, score in enumerate(unit.get("scores", []) or []):
                if not isinstance(score, dict):
                    continue
                # system_id and opponent_id (FG-6) both resolve globally to a Method.
                for key in ("system_id", "opponent_id"):
                    ref = score.get(key)
                    if ref and (ref not in unit_index or unit_index[ref].get("type") != "Method"):
                        warnings.append(
                            f"Measure {unit.get('id')} scores[{index}] {key} {ref!r} "
                            "did not resolve to a Method; blanked"
                        )
                        score[key] = ""
                setup_id = score.get("setup_id")
                if setup_id and (
                    setup_id not in local_ids
                    or unit_index.get(setup_id, {}).get("type") != "ExperimentSetup"
                ):
                    warnings.append(
                        f"Measure {unit.get('id')} scores[{index}] setup_id {setup_id!r} "
                        "is not a local ExperimentSetup; blanked"
                    )
                    score["setup_id"] = ""
                # judge_id (FG-6) resolves globally to a Method or ExperimentSetup.
                judge_id = score.get("judge_id")
                if judge_id and (
                    judge_id not in unit_index
                    or unit_index[judge_id].get("type") not in {"Method", "ExperimentSetup"}
                ):
                    warnings.append(
                        f"Measure {unit.get('id')} scores[{index}] judge_id {judge_id!r} "
                        "did not resolve to a Method or ExperimentSetup; blanked"
                    )
                    score["judge_id"] = ""
            # The Measure-level setup_ids[] list scopes the measure to local ExperimentSetups.
            # Drop (not blank — an empty string would re-fail the section-local check) any entry
            # that resolves to no unit, is not section-local, or is not an ExperimentSetup.
            setup_ids = unit.get("setup_ids")
            if isinstance(setup_ids, list):
                kept = [
                    s
                    for s in setup_ids
                    if s in local_ids and unit_index.get(s, {}).get("type") == "ExperimentSetup"
                ]
                if len(kept) != len(setup_ids):
                    dropped = [s for s in setup_ids if s not in kept]
                    warnings.append(
                        f"Measure {unit.get('id')} setup_ids dropped "
                        f"{len(dropped)} dangling/non-local entr"
                        f"{'y' if len(dropped) == 1 else 'ies'}: {dropped}"
                    )
                    unit["setup_ids"] = kept
    return warnings


def _repair_unit_enums(sections: list[dict[str, Any]]) -> list[str]:
    """Normalize degenerate / out-of-vocab values on the optional 0.10 enum fields — lossy-but-safe,
    logged to uncertain_assignments.

    These are benign quirks of fields the model fills freely (a blank ``polarity: ""``, a
    ``method_kind`` reaching one step past the controlled set like ``assumption``, a ``Finding.role``
    that holds a *polarity* word like ``mixed`` — confusion induced by FG-11 sitting next to
    ``role``). None carry structural meaning, so rather than hard-fail an otherwise-sound extraction:

    - an OPTIONAL enum whose value is out of vocab is dropped (the field is simply absent when
      unsupported): ``Finding.polarity``, ``Method.method_kind``, ``Measure.objective_class``, and the
      per-score-row ``value_kind``;
    - ``Finding.role`` is REQUIRED (it has a vocab), so it is coerced, never dropped: when the bad
      value is actually a polarity word and the polarity slot is free it is *moved* there and ``role``
      floored to ``descriptive``; otherwise ``role`` is floored to ``descriptive`` outright.
    """
    warnings: list[str] = []

    def _drop_invalid_optional(
        container: dict[str, Any], field: str, vocab: set[str], label: str, uid: str
    ) -> None:
        val = container.get(field)
        if val is not None and val not in vocab:
            del container[field]
            warnings.append(f"{label} {uid} dropped invalid {field}: {val!r}")

    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            utype = unit.get("type")
            uid = unit.get("id")
            if utype == "Finding":
                role = unit.get("role")
                if role is not None and role not in FINDING_ROLES:
                    if role in FINDING_POLARITIES and not unit.get("polarity"):
                        unit["polarity"] = role
                        unit["role"] = "descriptive"
                        warnings.append(
                            f"Finding {uid} role {role!r} moved to polarity; role -> descriptive"
                        )
                    else:
                        unit["role"] = "descriptive"
                        warnings.append(f"Finding {uid} coerced invalid role {role!r} -> descriptive")
                _drop_invalid_optional(unit, "polarity", FINDING_POLARITIES, "Finding", uid)
            elif utype == "Method":
                _drop_invalid_optional(unit, "method_kind", METHOD_KINDS, "Method", uid)
            elif utype == "Measure":
                _drop_invalid_optional(
                    unit, "objective_class", MEASURE_OBJECTIVE_CLASSES, "Measure", uid
                )
                scores = unit.get("scores")
                if isinstance(scores, list):
                    for row in scores:
                        if isinstance(row, dict):
                            _drop_invalid_optional(
                                row, "value_kind", SCORE_VALUE_KINDS, "Measure score", uid
                            )
    return warnings


def _drop_baseline_evaluates(
    relations: list[dict[str, Any]], census: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop `evaluates` edges pointing at a `compared_against` baseline. By policy a Measure
    `evaluates` only the method family it measures (contribution/component); a baseline is linked
    structurally by `compares_to` and quantitatively by a score row (system_id), never evaluated —
    so the measure's primary subject stays recoverable instead of diluted across every system row."""
    if not census:
        return relations, []
    role_by_id = {
        node.get("node_id"): node.get("role")
        for node in (census.get("nodes") or [])
        if isinstance(node, dict)
    }
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    for relation in relations:
        if (
            isinstance(relation, dict)
            and relation.get("relation") == "evaluates"
            and role_by_id.get(relation.get("target_id")) == "compared_against"
        ):
            warnings.append(
                "Dropped evaluates edge to compared_against baseline: "
                f"{relation.get('source_id')} -> {relation.get('target_id')} "
                "(baseline linked via compares_to + score row instead)"
            )
            continue
        kept.append(relation)
    return kept, warnings


def _assign_resolves(
    sections: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    census: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Synthesize the closing `resolves` edges of the discovery arc: Finding -> Problem.

    `resolves` is a born->born edge across two *parallel* content sections (the headline Finding
    in evidence, the Problem in the problem section), so neither section can author it without a
    forward reference into the other's freshly-invented ids. But both ends attach to the same
    globally-visible census `contribution` node — the Problem `motivates` it, the headline Finding
    is `about` it — so assembly derives the edge deterministically once every section is in hand:

        Problem --motivates--> [contribution] <--about-- Finding   =>   Finding --resolves--> Problem

    Returns new relation dicts to append; downstream `_dedup_relations` removes any duplicates.
    """
    if not census:
        return []
    contribution_ids = {
        node.get("node_id")
        for node in (census.get("nodes") or [])
        if isinstance(node, dict) and node.get("role") in CONTRIBUTION_ROLES
    }
    contribution_ids.discard(None)
    if not contribution_ids:
        return []

    # FG-7: a paper with co-equal contributions links them with `co_contribution` (the single
    # census root cannot name both). A finding about *either* co-equal contribution closes the arc,
    # so fan the root set out across co_contribution edges (fixpoint over pairwise links) before
    # deriving resolves — otherwise a correctly-motivated co-contribution would get no `resolves`.
    changed = True
    while changed:
        changed = False
        for rel in relations:
            if not isinstance(rel, dict) or rel.get("relation") != "co_contribution":
                continue
            src, tgt = rel.get("source_id"), rel.get("target_id")
            if src in contribution_ids and tgt not in contribution_ids and tgt is not None:
                contribution_ids.add(tgt)
                changed = True
            if tgt in contribution_ids and src not in contribution_ids and src is not None:
                contribution_ids.add(src)
                changed = True

    unit_type: dict[str, str] = {}
    unit_prov: dict[str, list[str]] = {}
    problem_anchor: str | None = None
    for section in sections:
        if section.get("section_type") == "problem":
            anchor = section.get("anchor_id")
            if isinstance(anchor, str):
                problem_anchor = anchor
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                unit_type[unit["id"]] = unit.get("type")
                if isinstance(unit.get("provenance"), list):
                    unit_prov[unit["id"]] = unit["provenance"]

    # The Problem that motivates the contribution; fall back to the problem section's anchor,
    # then to the sole Problem unit.
    problem_id = next(
        (
            rel.get("source_id")
            for rel in relations
            if isinstance(rel, dict)
            and rel.get("relation") == "motivates"
            and rel.get("target_id") in contribution_ids
            and unit_type.get(rel.get("source_id")) == "Problem"
        ),
        None,
    )
    if problem_id is None and unit_type.get(problem_anchor) == "Problem":
        problem_id = problem_anchor
    if problem_id is None:
        problem_units = [uid for uid, t in unit_type.items() if t == "Problem"]
        problem_id = problem_units[0] if len(problem_units) == 1 else None
    if problem_id is None:
        return []

    new_relations: list[dict[str, Any]] = []
    seen: set[str] = set()

    # FG-5 (Finding-as-root, 0.10 Pass 2): when a contribution is itself a Finding — an analysis/
    # mechanistic paper whose deliverable is the headline result, not a method — it resolves the
    # Problem *directly*. Nothing is `about` it (the about-join below never fires for a Finding
    # root), so emit root-Finding --resolves--> Problem here. This is what closes the arc on the
    # papers that previously rooted on a hollow "Analysis" Method.
    for nid in contribution_ids:
        if unit_type.get(nid) == "Finding" and nid not in seen:
            seen.add(nid)
            prov = unit_prov.get(nid) or unit_prov.get(problem_id) or []
            new_relations.append(
                {
                    "source_id": nid,
                    "relation": "resolves",
                    "target_id": problem_id,
                    "provenance": list(prov),
                }
            )

    for rel in relations:
        if (
            not isinstance(rel, dict)
            or rel.get("relation") != "about"
            or rel.get("target_id") not in contribution_ids
        ):
            continue
        finding_id = rel.get("source_id")
        if unit_type.get(finding_id) != "Finding" or finding_id in seen:
            continue
        seen.add(finding_id)
        prov = rel.get("provenance") or unit_prov.get(problem_id) or unit_prov.get(finding_id) or []
        new_relations.append(
            {
                "source_id": finding_id,
                "relation": "resolves",
                "target_id": problem_id,
                "provenance": list(prov),
            }
        )
    return new_relations


def _slice_source_tables(paper_content: str) -> dict[str, dict[str, str]]:
    """Slice every verbatim inline <table> blob, keyed by the `[§N]` block that contains it.

    Deterministic and lossless (P4): the LLM never emits this html; it is the raw grid behind the
    evidence pass, captured for audit/fallback and as the re-derivation source a future table parser
    can read instead of re-reading the whole paper. The caption is bounded to the region since the
    previous table so a caption-less table can't steal a distant one.

    Returns a dict keyed by the table's `§N` ``marker`` (the same `[§N]` block id the evidence pass
    references via ``source_table_marker``), so a Measure's marker self-checks (it must be a key here)
    and the renderer can resolve the blob by marker. Each entry is ``{marker, caption, html}``. When a
    single `[§N]` block holds more than one ``<table>`` the blobs are concatenated under that one
    marker (lossless for the by-value verifier; flagged elsewhere as an abnormal block).
    """
    if not isinstance(paper_content, str) or "<table" not in paper_content.lower():
        return {}
    anchors = [(m.start(), m.group(1)) for m in SECTION_MARKER_RE.finditer(paper_content)]
    captions = [(m.start(), m.group(0)) for m in TABLE_CAPTION_RE.finditer(paper_content)]
    tables: dict[str, dict[str, str]] = {}
    prev_end = 0
    for m in TABLE_BLOCK_RE.finditer(paper_content):
        pos = m.start()
        anchor = ""
        for astart, anum in anchors:
            if astart >= pos:
                break
            anchor = f"§{anum}"
        caption = ""
        for cstart, ctext in captions:
            if cstart >= pos:
                break
            if cstart >= prev_end:
                caption = ctext.strip("* ").strip()
        html = m.group(0)
        existing = tables.get(anchor)
        if existing is None:
            tables[anchor] = {"marker": anchor, "caption": caption, "html": html}
        else:
            # >1 <table> in one [§N] block: keep both verbatim under the shared marker so the
            # by-value verifier still sees every cell; first non-empty caption wins.
            existing["html"] = existing["html"] + "\n" + html
            if caption and not existing.get("caption"):
                existing["caption"] = caption
        prev_end = m.end()
    return tables


def build_table_index(paper_content: str) -> str:
    """A reference list of the paper's captured ``<table>`` blocks for the blob-primary evidence prompt.

    The slicer knows exactly which ``[§N]`` blocks contain a ``<table>`` grid; handing that list to the
    LLM (each table's caption + a header-row preview) grounds ``source_table_marker`` to a real table
    block instead of letting the model guess a ``§N`` — which it otherwise aims at the prose paragraph
    that *discusses* a table, at an image ``![...]`` figure, or at a bare caption line (the dominant
    failure mode on the first benchmark: 31/142 markers pointed at non-table blocks). Returns a
    no-tables note when the paper has no ``<table>`` grids, so the model transcribes prose numbers
    with no marker instead of inventing one.
    """
    tables = _slice_source_tables(paper_content)
    if not tables:
        return (
            "This paper has NO <table> grids (its results are in prose or figures). Do NOT emit any "
            "source_table_marker; transcribe the contribution's reported numbers directly as scores[] "
            "rows, as for a prose result."
        )
    lines: list[str] = []
    for marker, t in tables.items():
        cap = (t.get("caption") or "").strip().strip("*").strip()
        preview = " | ".join(c for c in _table_cell_texts(t.get("html", ""))[:8] if c)
        label = cap or (f"columns: {preview}" if preview else "(no caption)")
        lines.append(f"- `{marker}` — {label[:180]}")
    header = (
        "Available result tables — these are the ONLY blocks that contain a <table> grid. Set every "
        "`source_table_marker` to one of these EXACT markers; never point at a prose paragraph that "
        "merely discusses a table, at an image/figure `![...]`, or at a bare caption line. Match a "
        "measure to its table by the caption/columns below:"
    )
    return header + "\n" + "\n".join(lines)


def _attach_model_captions(
    sections: list[dict[str, Any]],
    source_tables: dict[str, dict[str, str]],
    paper_content: str,
) -> list[str]:
    """Blob-primary: store each table's model-chosen caption verbatim on its ``source_tables`` entry.

    The model points at the caption block with ``caption_marker`` (e.g. ``§52``) — its authoritative
    location, chosen with the table in view, instead of the slicer's "nearest preceding **Table k**"
    proximity heuristic. Here we slice that block verbatim from the segmented paper and overwrite the
    table entry's ``caption`` (and record ``caption_marker``). Falls back silently to the heuristic
    caption when the marker is missing; warns when it points at a block that does not exist.
    """
    blocks = parse_sections(paper_content)  # {N: block_text}, block_text keeps its leading [§N]
    warnings: list[str] = []
    for section in sections:
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict) or unit.get("type") != "Measure":
                continue
            tmarker = _canon_marker(unit.get("source_table_marker") or "")
            cmarker = _canon_marker(unit.get("caption_marker") or "")
            if not cmarker or tmarker not in source_tables:
                continue
            block_text = blocks.get(cmarker.lstrip("§"))
            if not block_text:
                warnings.append(
                    f"measure {unit.get('id')!r} caption_marker {cmarker} did not resolve to a block"
                )
                continue
            caption = SECTION_MARKER_RE.sub("", block_text, count=1).strip()
            source_tables[tmarker]["caption"] = caption
            source_tables[tmarker]["caption_marker"] = cmarker
    return warnings


def _canon_marker(marker: Any) -> str:
    """Normalize an evidence-pass section marker to canonical ``§N`` form.

    The blob-primary evidence pass is told to write a table/caption marker as ``"§53"``, but a
    json_object model may emit ``"53"`` or ``"[§53]"``. Canonicalizing both the stored marker and any
    lookup key keeps Measure ``source_table_marker``/``caption_marker`` comparable to the
    ``source_tables`` dict keys (which ``_slice_source_tables`` already emits as ``§N``). Returns ""
    for a blank/non-string input.
    """
    if not isinstance(marker, str):
        return ""
    m = marker.strip()
    if m.startswith("[") and m.endswith("]"):
        m = m[1:-1].strip()
    m = m.lstrip("§").strip()
    return f"§{m}" if m else ""


class _TableCellParser(HTMLParser):
    """Collect the text of every <td>/<th> cell in a <table> blob — presence only, no grid topology.

    The fidelity verifier (P2) matches score VALUES against cell TEXT, so a cell's row/column position
    is irrelevant; rowspan/colspan are ignored on purpose. That is exactly why the verifier sidesteps
    the rowspan/colspan addressing errors that make index-based table *binding* unsafe — it never
    addresses a cell, it only asks whether a transcribed number appears somewhere in the table.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self._depth = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("td", "th"):
            if self._depth == 0:
                self._buf = []
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._depth > 0:
            self._depth -= 1
            if self._depth == 0:
                self.cells.append("".join(self._buf).strip())

    def handle_data(self, data: str) -> None:
        if self._depth > 0:
            self._buf.append(data)


def _table_cell_texts(table_html: str) -> list[str]:
    """Every non-empty <td>/<th> cell text in a verbatim table blob (entities unescaped, tags dropped)."""
    parser = _TableCellParser()
    try:
        parser.feed(table_html or "")
    except Exception:
        return []
    return [c for c in parser.cells if c]


_NUM_TOKEN_RE = re.compile(r"[-+]?(?:\d[\d,]*\.?\d*|\.\d+)")


def _canon_num(token: str) -> str | None:
    """Canonical float key for one numeric token: '.323'->'0.323', '28.40'->'28.4', '1,234'->'1234'.

    Returns None when the token is not a parseable number. Canonicalizing through float makes
    leading-zero and trailing-zero formatting differences (the dominant false-positive source for a
    value↔cell match) compare equal, so the verifier doesn't cry wolf over '.5' vs '0.50'.
    """
    t = token.replace(",", "").rstrip(".")
    if t in ("", "-", "+", "."):
        return None
    try:
        return f"{float(t):.10g}"
    except ValueError:
        return None


def _numeric_keys(text: str) -> list[str]:
    """All canonical numeric keys in a string — handles ranges/slashes/± by extracting every token."""
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    keys: list[str] = []
    for m in _NUM_TOKEN_RE.finditer(text):
        key = _canon_num(m.group(0))
        if key is not None:
            keys.append(key)
    return keys


def _verify_score_fidelity(
    sections: list[dict[str, Any]],
    source_tables: dict[str, dict[str, str]],
    paper_content: str = "",
) -> dict[str, Any] | None:
    """Cross-check LLM-transcribed score values against the verbatim source tables (the P2 verifier).

    Forward, presence-based and matched BY VALUE (never by cell position, so it is immune to the
    rowspan/colspan addressing errors that make index-based binding unsafe): every numeric score
    `value` should appear as a cell in some captured <table>. A value absent from every table — while
    OTHER values of the same Measure DO match — is a high-signal candidate transcription error or
    uncaptured-table value, surfaced as a flag. A Measure whose values match NO table at all is
    treated as prose-derived (one low-confidence note, not per-row noise — ~6% of Measures are
    legitimately prose). Reverse coverage (decimal cells never transcribed) is reported only as an
    aggregate hint, because result/config/diagnostic cells are legitimately left untranscribed.

    Pure audit: writes nothing into units/scores/relations, only returns a notes block. Returns None
    when there are no tables (or no numeric cells) to check against.
    """
    if not source_tables:
        return None
    face: set[str] = set()
    cell_decimal_keys: set[str] = set()
    marker_faces: dict[str, set[str]] = {}
    for marker, table in source_tables.items():
        tface: set[str] = set()
        for cell in _table_cell_texts(table.get("html", "")):
            for key in _numeric_keys(cell):
                tface.add(key)
                face.add(key)
                if "." in key:
                    cell_decimal_keys.add(key)
        marker_faces[marker] = tface
    if not face:
        return None
    # Numbers anywhere in the paper text (not just tables) — used to separate a value that is
    # genuinely in the paper but stated in prose/figure (model was right, just not table-grounded —
    # benign) from one absent everywhere (scaling/figure-read/possible transcription error — the
    # higher-priority subset). A hint, not gospel: a bare integer matches loosely.
    paper_keys = set(_numeric_keys(paper_content)) if paper_content else set()

    flags: list[dict[str, Any]] = []
    measures_no_table: list[dict[str, Any]] = []
    transcribed_keys: set[str] = set()
    values_total = 0
    values_located = 0
    flags_absent_from_paper = 0

    for section in sections:
        for unit in section.get("units", []):
            if unit.get("type") != "Measure":
                continue
            rows: list[tuple[str, str, list[str], bool]] = []  # (variant, value, keys, located)
            numeric_count = 0
            located_count = 0
            # 0.12: a Measure that points at its own source table is checked against THAT table's
            # cells only (no cross-table false matches); a marker-less / prose Measure, or one whose
            # marker did not resolve, falls back to the union of all tables.
            marker = _canon_marker(unit.get("source_table_marker") or "")
            local_face = marker_faces.get(marker, face) if marker else face
            for score in unit.get("scores") or []:
                value = str(score.get("value", "")).strip()
                keys = _numeric_keys(value)
                if not keys:
                    continue  # qualitative/symbolic value — out of scope for a numeric cross-check
                numeric_count += 1
                transcribed_keys.update(keys)
                located = any(key in local_face for key in keys)
                if located:
                    located_count += 1
                rows.append((str(score.get("variant", "")), value, keys, located))
            if numeric_count == 0:
                continue
            values_total += numeric_count
            values_located += located_count
            if located_count == 0:
                # Whole Measure unmatched → prose-derived or uncaptured table. One low-confidence note.
                measures_no_table.append(
                    {"measure_id": unit.get("id", ""), "name": unit.get("name", ""),
                     "n_values": numeric_count}
                )
                continue
            # The Measure IS table-derived; an individual miss is now a real anomaly worth flagging.
            for variant, value, keys, located in rows:
                if located:
                    continue
                in_paper = bool(paper_keys) and any(key in paper_keys for key in keys)
                if not in_paper:
                    flags_absent_from_paper += 1
                flags.append({
                    "measure_id": unit.get("id", ""),
                    "measure_name": unit.get("name", ""),
                    "variant": variant,
                    "value": value,
                    "in_paper": in_paper,
                    "kind": "value_not_in_table",
                })

    cells_unmatched = sum(1 for key in cell_decimal_keys if key not in transcribed_keys)
    return {
        "checked": True,
        "values_total": values_total,
        "values_located": values_located,
        "located_pct": round(100.0 * values_located / values_total, 1) if values_total else None,
        "flags": flags,
        "flags_absent_from_paper": flags_absent_from_paper,
        "measures_no_table": measures_no_table,
        "table_cells_unmatched": cells_unmatched,
    }


def _mount_findings_on_measures(
    sections: list[dict[str, Any]], relations: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Blob-primary (0.12): make ``Measure.finding_ids`` the sole table→finding link.

    Three jobs, all on the blob-primary path only (the caller gates on the flag):
    1. Canonicalize each Measure's ``source_table_marker``/``caption_marker`` to ``§N`` form so they
       match the ``source_tables`` dict keys downstream.
    2. Migrate any ``Measure --supports--> Finding`` or ``Finding --about--> Measure`` edge the model
       authored into the target Measure's ``finding_ids`` (so no link is lost if the model used an
       edge instead of the mount), then drop those two edge shapes from ``relations``. Other edges —
       ``Finding --about--> Method/ExperimentSetup``, ``Finding/Method --supports--> Finding`` — are
       untouched.
    3. Drop a ``finding_id`` that does not resolve to a Finding unit (a stale mount — a grounding
       hazard). Each migration/repair is logged to ``uncertain_assignments``.
    """
    warnings: list[str] = []
    finding_unit_ids: set[str] = set()
    measures: dict[str, dict[str, Any]] = {}
    for section in sections:
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict):
                continue
            uid, utype = unit.get("id"), unit.get("type")
            if utype == "Finding" and isinstance(uid, str):
                finding_unit_ids.add(uid)
            elif utype == "Measure" and isinstance(uid, str):
                measures[uid] = unit
                for key in ("source_table_marker", "caption_marker"):
                    if unit.get(key):
                        unit[key] = _canon_marker(unit[key])

    def _mount(measure_id: str, finding_id: str) -> None:
        m = measures.get(measure_id)
        if m is None:
            return
        ids = m.setdefault("finding_ids", [])
        if isinstance(ids, list) and finding_id not in ids:
            ids.append(finding_id)

    kept: list[dict[str, Any]] = []
    for rel in relations:
        if not isinstance(rel, dict):
            kept.append(rel)
            continue
        src, predicate, tgt = rel.get("source_id"), rel.get("relation"), rel.get("target_id")
        if predicate == "supports" and src in measures and tgt in finding_unit_ids:
            _mount(src, tgt)
            warnings.append(f"mounted finding {tgt!r} on measure {src!r} (dropped supports edge)")
            continue
        if predicate == "about" and tgt in measures and src in finding_unit_ids:
            _mount(tgt, src)
            warnings.append(f"mounted finding {src!r} on measure {tgt!r} (dropped about edge)")
            continue
        kept.append(rel)

    for uid, m in measures.items():
        ids = m.get("finding_ids")
        if not isinstance(ids, list):
            continue
        resolved = [fid for fid in ids if fid in finding_unit_ids]
        if len(resolved) != len(ids):
            stale = [fid for fid in ids if fid not in finding_unit_ids]
            warnings.append(f"dropped stale finding_ids {stale!r} from measure {uid!r}")
            m["finding_ids"] = resolved

    return kept, warnings


def assemble_extraction(
    census: dict[str, Any],
    stage_b_relations: list[dict[str, Any]],
    section_results: list[dict[str, Any]],
    paper_content: str,
    sections_included: list[str] | None = None,
    sections_omitted: list[str] | None = None,
    verify_scores: bool = True,
    blob_primary_evidence: bool = False,
) -> dict[str, Any]:
    """Merge content section results + relation-pass edges into final section-IR 0.7 output.

    The single global `relations[]` is the concatenation of the relation pass's structural
    edges and each content section's claim-centric edges, then deduped, dangling-pruned, and
    matrix-checked once the full unit set is known.
    """
    sections: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = [
        relation for relation in (stage_b_relations or []) if isinstance(relation, dict)
    ]

    for result in section_results:
        if not isinstance(result, dict) or not isinstance(result.get("section"), dict):
            raise ValueError(f"Invalid section extraction result: {result}")
        section = result["section"]
        flattened_units = _flatten_typed_arrays(section)
        if any(key in section for key in TYPED_ARRAY_KEYS):
            section["units"] = flattened_units
            for key in TYPED_ARRAY_KEYS:
                section.pop(key, None)
        # Lift each content section's claim-centric edges into the global relation list.
        section_relations = section.pop("relations", None)
        if isinstance(section_relations, list):
            relations.extend(rel for rel in section_relations if isinstance(rel, dict))
        sections.append(section)

    # Order sections along the argumentative spine.
    order_index = {name: i for i, name in enumerate(SECTION_ORDER)}
    sections.sort(key=lambda s: order_index.get(s.get("section_type"), len(SECTION_ORDER)))

    _canonicalize_section_id_aliases(sections)
    _canonicalize_relation_aliases(relations)
    _assign_roles_from_census(sections, census)

    assembly_warnings: list[str] = []
    assembly_warnings.extend(_sanitize_unit_text(sections))
    assembly_warnings.extend(_sanitize_unit_ids(sections, relations))
    assembly_warnings.extend(
        _dedup_experiment_setups(sections, relations, all_census_node_ids(census))
    )
    assembly_warnings.extend(_dedup_unit_ids(sections))
    # Drop dataless Measures before section/anchor repair: a section emptied by the drop is then
    # caught by _drop_empty_sections, and a section that anchored on the dropped measure is
    # re-pointed by _repair_section_anchors instead of being left with a dangling anchor_id.
    dropped_measures: list[dict[str, str]] = []
    assembly_warnings.extend(_drop_empty_scores_measures(sections, dropped_measures))
    assembly_warnings.extend(_drop_empty_sections(sections))
    assembly_warnings.extend(_normalize_provenance_markers(sections, relations))
    assembly_warnings.extend(_repair_section_anchors(sections))
    assembly_warnings.extend(_repair_score_refs(sections))
    assembly_warnings.extend(_repair_unit_enums(sections))
    assembly_warnings.extend(_clean_method_equations(sections))
    assembly_warnings.extend(_strip_baseline_method_fields(sections, census))

    relations, warns = _dedup_relations(relations)
    assembly_warnings.extend(warns)
    relations, warns = _drop_dangling_relations(relations, sections)
    assembly_warnings.extend(warns)
    relations, warns = _drop_invalid_relations(relations, sections)
    assembly_warnings.extend(warns)
    relations, warns = _drop_baseline_evaluates(relations, census)
    assembly_warnings.extend(warns)

    # Blob-primary (0.12): the table↔finding link is the Measure's `finding_ids`, not an edge —
    # migrate any Measure↔Finding edge the model authored into the mount and drop those edge shapes
    # (and canonicalize the table markers). Runs on the contribution-node-join edges that survive the
    # cleanup above, and before _assign_resolves (which uses Finding→contribution `about`, untouched).
    if blob_primary_evidence:
        relations, warns = _mount_findings_on_measures(sections, relations)
        assembly_warnings.extend(warns)

    # Synthesize the closing `resolves` edge(s) from the surviving contribution-node join,
    # then dedup so a re-run can't double it. These are valid by construction (Finding->Problem).
    synthesized = _assign_resolves(sections, relations, census)
    if synthesized:
        relations.extend(synthesized)
        relations, warns = _dedup_relations(relations)
        assembly_warnings.extend(warns)

    _assign_covers_entries(sections, all_census_node_ids(census))

    # Build notes from the final, repaired sections so coverage reflects assembly mutations.
    extraction_notes = build_extraction_notes(
        census,
        sections,
        sections_included=sections_included,
        sections_omitted=sections_omitted,
        extra_uncovered=dropped_measures,
    )
    if assembly_warnings:
        uncertain = extraction_notes.setdefault("uncertain_assignments", [])
        if isinstance(uncertain, list):
            uncertain.extend(assembly_warnings)

    spine_summary = census.get("spine_summary") if isinstance(census, dict) else None
    thesis = spine_summary.get("central_contribution") or "" if isinstance(spine_summary, dict) else ""
    headline_result = spine_summary.get("headline_result") or "" if isinstance(spine_summary, dict) else ""
    document_role = _derive_document_role(census, sections)
    source_tables = _slice_source_tables(paper_content)
    if source_tables:
        # Blob-primary: override each table's heuristic caption with the model-chosen caption block
        # (the model's caption_marker is the authoritative location; code slices it verbatim), so the
        # caption stored beside the table is the one the model pointed at, not a proximity guess.
        if blob_primary_evidence:
            cap_warns = _attach_model_captions(sections, source_tables, paper_content)
            if cap_warns:
                uncertain = extraction_notes.setdefault("uncertain_assignments", [])
                if isinstance(uncertain, list):
                    uncertain.extend(cap_warns)
        extraction_notes["source_tables"] = source_tables
        # Audit-only (P2 verifier): cross-check transcribed score values against the verbatim tables.
        # Writes nothing into units/scores/relations — only a notes block — so it cannot affect render
        # or validation. Matched by value, so it is immune to table-grid addressing errors.
        if verify_scores:
            fidelity = _verify_score_fidelity(sections, source_tables, paper_content)
            if fidelity is not None:
                extraction_notes["score_fidelity"] = fidelity
    return {
        "document": build_document_unit(
            paper_content, thesis=thesis, document_role=document_role, headline_result=headline_result
        ),
        "sections": sections,
        "relations": relations,
        "extraction_notes": extraction_notes,
    }


def _extract_balanced_json(raw: str) -> str:
    start = raw.find("{")
    if start < 0:
        raise ValueError("No JSON object found in LLM response")

    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(raw)):
        ch = raw[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : pos + 1]
    raise ValueError("Could not find a balanced JSON object in LLM response")


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse JSON from a possibly fenced or reasoning-heavy LLM response."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("{"):
        cleaned = _extract_balanced_json(cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Escape stray backslashes that commonly appear in model output.
        repaired = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", cleaned)
        parsed = json.loads(repaired)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed


def _call_llm(
    client: Any,
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.0,
    max_tokens: int = 16_384,
    response_format: dict | None = None,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
) -> str:
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format is not None:
        kwargs["response_format"] = response_format
    # DeepSeek reasons by default; the extraction pipeline runs it with thinking DISABLED
    # (faster, and reasoning gave no quality lift on this corpus). The proxy accepts the
    # toggle via extra_body; gated to deepseek so other models are untouched.
    if _is_deepseek_model(model):
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    # The explicit prompt-cache routing kwargs are OpenAI-proxy features; the official DeepSeek
    # API rejects unknown params (its caching is automatic), so only send them where supported.
    if _supports_prompt_cache_kwargs(model):
        if prompt_cache_key:
            kwargs["prompt_cache_key"] = prompt_cache_key
        if prompt_cache_retention:
            kwargs["prompt_cache_retention"] = prompt_cache_retention
    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    if choice.finish_reason == "length":
        content = choice.message.content or ""
        raise ValueError(
            f"LLM response truncated (finish_reason=length, got {len(content)} chars). "
            f"Increase max_tokens or reduce prompt size."
        )
    return choice.message.content or ""


def run_node_census(
    client: Any,
    model: str,
    paper_content: str,
    temperature: float = 0.0,
    max_tokens: int = 16_384,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
) -> dict[str, Any]:
    """Run stage A: the node census over the full paper. Returns {spine_summary, nodes}."""
    system_prompt, user_template = load_prompt(NODE_CENSUS_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = load_node_census_schema()
    resp_fmt = build_response_format(schema, name="node_census_output", model=model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, model)
    raw = _call_llm(
        client, model, system_prompt, user_prompt,
        temperature=temperature, max_tokens=max_tokens, response_format=resp_fmt,
        prompt_cache_key=prompt_cache_key, prompt_cache_retention=prompt_cache_retention,
    )
    return _parse_llm_json(raw)


def run_relation_pass(
    client: Any,
    model: str,
    paper_content: str,
    node_registry: list[dict[str, Any]],
    temperature: float = 0.0,
    max_tokens: int = 16_384,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
) -> dict[str, Any]:
    """Run stage B: the relation pass over the full node set. Returns {relations}."""
    system_prompt, user_template = load_prompt(RELATION_PASS_PROMPT_PATH)
    nodes_json = json.dumps(node_registry, ensure_ascii=False, indent=2)
    user_prompt = (
        user_template
        .replace("{{paper_content}}", paper_content)
        .replace("{{nodes_json}}", nodes_json)
    )
    schema = load_relation_pass_schema()
    resp_fmt = build_response_format(schema, name="relation_pass_output", model=model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, model)
    raw = _call_llm(
        client, model, system_prompt, user_prompt,
        temperature=temperature, max_tokens=max_tokens, response_format=resp_fmt,
        prompt_cache_key=prompt_cache_key, prompt_cache_retention=prompt_cache_retention,
    )
    return _parse_llm_json(raw)


def run_metadata_extraction(
    client: Any,
    model: str,
    paper_content: str,
    temperature: float = 0.0,
    max_tokens: int = 16_384,
) -> dict[str, Any]:
    """Extract paper metadata (title, authors, resources)."""
    system_prompt, user_template = load_prompt(METADATA_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = json.loads(METADATA_SCHEMA_PATH.read_text(encoding="utf-8"))
    resp_fmt = build_response_format(schema, name="metadata_output", model=model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, model)
    raw = _call_llm(client, model, system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens, response_format=resp_fmt)
    return _parse_llm_json(raw)


def run_references_extraction(
    client: Any,
    model: str,
    paper_content: str,
    temperature: float = 0.0,
    max_tokens: int = 16_384,
) -> dict[str, Any]:
    """Extract paper reference list into structured entries."""
    system_prompt, user_template = load_prompt(REFERENCES_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    schema = json.loads(REFERENCES_SCHEMA_PATH.read_text(encoding="utf-8"))
    resp_fmt = build_response_format(schema, name="references_output", model=model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, model)
    raw = _call_llm(client, model, system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens, response_format=resp_fmt)
    return _parse_llm_json(raw)


def _normalize_name(text: Any) -> str:
    """Lowercase a name to space-joined alphanumeric tokens for tolerant matching."""
    if not isinstance(text, str):
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# An author-year citation marker names the same reference two ways across stages: the census
# tends to echo the in-text marker verbatim ("Warburg et al., 2021", "Qin et al., 2022a") while
# the references pass compacts it ("Warburg2021", "Qin2022a"). A strip-brackets/lowercase compare
# misses that pair (the "et al.", commas, and secondary authors survive on one side only), so on
# the ros_ai 8-venue corpus the cite-key join held at 98% on numbered papers but fell to 45% on
# author-year papers. Reducing any year-bearing marker to <first-author><year><disambig-letter>
# on BOTH sides converges them; bare numeric markers and year-less keys keep the old behavior.
_CITE_YEAR_RE = re.compile(r"(1[89]\d\d|20\d\d)([a-z])?")
_CITE_AUTHOR_STOPWORDS = frozenset({"et", "al", "and", "the"})


def _normalize_cite_key(value: Any) -> str:
    """Normalize a citation marker to a comparable key so census `cite_keys` and reference `id`s
    join on the paper's own citation rather than a fuzzy name match.

    Numbered markers collapse to their digits ('[31]' -> '31'). Author-year markers collapse to
    '<first-author-lastname><year><letter>' regardless of surface form ('Warburg et al., 2021' ->
    'warburg2021', 'Qin et al., 2022a' -> 'qin2022a', already-compact 'Vaswani2017' -> 'vaswani2017'),
    so the census's verbatim in-text form and the references pass's compacted form land on the same
    key. A year-less, non-numeric key falls back to strip-brackets/whitespace + lowercase
    ('[AlexNet]' -> 'alexnet').
    """
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    # Numbered marker (optionally bracketed): digits only, never author-year-parsed.
    if re.fullmatch(r"\[?\s*\d+\s*\]?", stripped):
        return re.sub(r"[\[\]\s]+", "", stripped).lower()
    match = _CITE_YEAR_RE.search(stripped)
    if not match:
        return re.sub(r"[\[\]\s]+", "", stripped).lower()
    year, letter = match.group(1), (match.group(2) or "")
    authors = [
        tok
        for tok in re.findall(r"[A-Za-z][A-Za-z\-]*", stripped[: match.start()])
        if tok.lower() not in _CITE_AUTHOR_STOPWORDS
    ]
    if not authors:
        return re.sub(r"[\[\]\s]+", "", stripped).lower()
    first = re.sub(r"[^a-z0-9]", "", authors[0].lower())
    return f"{first}{year}{letter}" if first else re.sub(r"[\[\]\s]+", "", stripped).lower()


def reconcile_reference_units(
    references: dict[str, Any] | None,
    extraction: dict[str, Any],
    census: dict[str, Any] | None = None,
) -> list[str]:
    """Link each reference to the spine Method/ExperimentSetup unit(s) it contributes.

    The references pass runs before section extraction, so it never knows the final unit IDs
    and always emits `provides_unit_ids: []`. Once the spine exists, fill it with a two-tier
    join, strongest signal first:

    1. **Citation key** (primary, exact): a census node carries the in-text bibliography
       marker(s) it was cited as (`cite_keys`); since `node_id == unit_id`, a reference whose
       `id` matches a materialized node's cite_key links straight to that unit. Grounded in the
       paper's own citation, so it catches names the spine spells differently (reference "GNMT"
       -> unit "GNMT + RL" cited as [31]).
    2. **Name** (fallback, fuzzy): when no citation key matches, fall back to a unique
       normalized match of `provides_name` against Method/ExperimentSetup unit names (the original
       behavior). Conservative: an ambiguous (multi-unit) or unmatched name stays `[]`.

    Mutates `references` in place and returns warnings for the audit trail.
    """
    warnings: list[str] = []
    if not isinstance(references, dict):
        return warnings
    ref_list = references.get("references")
    if not isinstance(ref_list, list):
        return warnings

    # Index materialized Method/ExperimentSetup units by id and by normalized name.
    type_by_id: dict[str, Any] = {}
    name_to_ids: dict[str, list[str]] = {}
    for section in extraction.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict) or unit.get("type") not in {"Method", "ExperimentSetup"}:
                continue
            uid = unit.get("id")
            if not isinstance(uid, str):
                continue
            type_by_id[uid] = unit.get("type")
            name_key = _normalize_name(unit.get("name"))
            if name_key and uid not in name_to_ids.setdefault(name_key, []):
                name_to_ids[name_key].append(uid)

    # Index materialized nodes' citation keys -> unit ids (node_id == unit_id).
    citekey_to_ids: dict[str, list[str]] = {}
    if isinstance(census, dict):
        for node in census.get("nodes", []) or []:
            if not isinstance(node, dict):
                continue
            nid = node.get("node_id")
            if not isinstance(nid, str) or nid not in type_by_id:
                continue
            for raw_key in node.get("cite_keys", []) or []:
                cite_key = _normalize_cite_key(raw_key)
                if cite_key and nid not in citekey_to_ids.setdefault(cite_key, []):
                    citekey_to_ids[cite_key].append(nid)

    # FG-12 (section-ir-0.10) + vocab unification: also backfill unit-graph edges from each
    # reference's citation roles — a role uses the same vocabulary as the edges, so it is materialized
    # as the edge of the same name. Each edge is sourced at the contribution (the paper's own work
    # relates to the cited prior work); the reference's linked unit is the target, and the edge is
    # stamped origin="reference". An edge already present (e.g. a natively-authored stage-B
    # compares_to) is not duplicated and stays native (no origin); a non-neutral stance is merged onto
    # it instead. Source attribution to the contribution is a deterministic default — an internal
    # component's own builds_on/uses to an uncited dependency is not covered.
    relations = extraction.get("relations")
    if not isinstance(relations, list):
        relations = None
    contribution_id: str | None = None
    if isinstance(census, dict):
        for node in census.get("nodes", []) or []:
            if isinstance(node, dict) and node.get("role") in CONTRIBUTION_ROLES:
                cid = node.get("node_id")
                if isinstance(cid, str) and cid in type_by_id:
                    contribution_id = cid
                break
    existing_edges: set[tuple] = set()
    if relations is not None:
        for existing in relations:
            if isinstance(existing, dict):
                existing_edges.add(
                    (existing.get("source_id"), existing.get("relation"), existing.get("target_id"))
                )

    for ref in ref_list:
        if not isinstance(ref, dict):
            continue
        relation = ref.get("relation")
        if not isinstance(relation, dict):
            continue
        # Python owns this field; the model always emits []. Recompute from scratch.
        relation["provides_unit_ids"] = []

        linked = citekey_to_ids.get(_normalize_cite_key(ref.get("id")), [])
        via = "cite_key"
        if not linked:
            name_key = _normalize_name(relation.get("provides_name"))
            matches = name_to_ids.get(name_key, []) if name_key else []
            if len(matches) == 1:
                linked = matches
                via = "name"
        if linked:
            relation["provides_unit_ids"] = list(linked)
            detail = (
                f"cite_key {ref.get('id')!r}"
                if via == "cite_key"
                else f"provides_name {relation.get('provides_name')!r}"
            )
            warnings.append(
                f"Linked reference {ref.get('id')!r} to unit(s) {list(linked)} via {detail}"
            )
            # Backfill dependency/comparison edges from this reference's citation roles.
            if relations is not None and contribution_id:
                stance = relation.get("stance")
                for role_name in relation.get("roles") or []:
                    # A reference role IS the edge it implies (identity); `background` and any other
                    # non-edge role carry no unit-graph edge.
                    if role_name not in REFERENCE_EDGE_ROLES:
                        continue
                    edge_rel = role_name
                    for target_id in linked:
                        if target_id == contribution_id:
                            continue
                        key = (contribution_id, edge_rel, target_id)
                        if key in existing_edges:
                            # Edge already present (e.g. a natively-authored stage-B edge); enrich a
                            # stance-less compares_to with stance, but leave it native (no origin).
                            if edge_rel == "compares_to" and stance in {"supportive", "critical"}:
                                for existing in relations:
                                    if (
                                        existing.get("source_id"),
                                        existing.get("relation"),
                                        existing.get("target_id"),
                                    ) == key and not existing.get("stance"):
                                        existing["stance"] = stance
                            continue
                        edge: dict[str, Any] = {
                            "source_id": contribution_id,
                            "relation": edge_rel,
                            "target_id": target_id,
                            "provenance": [],
                            "origin": REFERENCE_EDGE_ORIGIN,
                        }
                        if edge_rel == "compares_to" and stance in {"supportive", "critical"}:
                            edge["stance"] = stance
                        relations.append(edge)
                        existing_edges.add(key)
                        warnings.append(
                            f"Backfilled {contribution_id} -[{edge_rel}]-> {target_id} "
                            f"from reference {ref.get('id')!r} role {role_name!r}"
                        )
    return warnings


def _validate_section_result_shape(result: dict[str, Any], section_type: str) -> None:
    if not isinstance(result.get("section"), dict):
        raise ValueError("Section extraction result missing section object")
    section = result["section"]
    if section.get("section_type") != section_type:
        raise ValueError(
            "Section extraction result section_type mismatch: "
            f"{section.get('section_type')} != {section_type}"
        )
    typed_array_keys = [key for key in TYPED_ARRAY_KEYS if key in section]
    if not typed_array_keys:
        raise ValueError("Section extraction result missing typed unit arrays")
    for key in typed_array_keys:
        if not isinstance(section.get(key), list):
            raise ValueError(f"Section extraction result {key} must be a list")


def extract_single_content_section_sync(
    client: Any,
    model: str,
    section_type: str,
    paper_content: str,
    node_registry: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    spine_summary: dict[str, Any] | None = None,
    temperature: float = 0.0,
    max_tokens: int = DEFAULT_SECTION_MAX_TOKENS,
    max_retries: int = MAX_SECTION_RETRIES,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
    blob_primary_evidence: bool = False,
) -> dict[str, Any]:
    """Extract one content section (stage C) using the synchronous LLM client."""
    system_prompt, _ = load_prompt(SECTION_EXTRACTION_PROMPT_PATH)
    section_module = load_section_module(section_type, blob_primary_evidence)
    if blob_primary_evidence and section_type == "evidence":
        section_module = f"{section_module}\n\n## Source-table index\n{build_table_index(paper_content)}"
    section_schema = load_section_schema(section_type)
    resp_fmt = build_response_format(section_schema, name=f"{section_type}_section", model=model)

    # For json_object models (DeepSeek), the schema cannot constrain decoding, so fold its
    # contract into section_focus. Placing it inside <section_focus> — which already varies per
    # section — keeps the shared user-prompt prefix (paper, spine_summary, node_registry,
    # relations) byte-identical across the four sections, so the cross-section cache stays warm.
    if _structured_output_mode(model) == "json_object":
        section_module = f"{section_module}\n\n{schema_to_prompt_spec(section_schema)}"

    user_prompt = render_content_user_prompt(
        paper_content,
        section_type=section_type,
        section_module=section_module,
        node_registry=node_registry,
        relations=relations,
        spine_summary=spine_summary,
    )

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            raw = _call_llm(
                client,
                model,
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=resp_fmt,
                prompt_cache_key=prompt_cache_key,
                prompt_cache_retention=prompt_cache_retention,
            )
            result = _parse_llm_json(raw)
            _validate_section_result_shape(result, section_type)
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= max_retries:
                break
    raise RuntimeError(
        f"Content extraction failed after retries for {section_type} section"
    ) from last_error


def _sort_section_refs(refs: set[str]) -> list[str]:
    def sort_key(ref: str) -> tuple[int, str]:
        match = re.search(r"\d+", ref)
        return (int(match.group(0)) if match else 10**9, ref)

    return sorted(refs, key=sort_key)


def run_content_extraction_sync(
    client: Any,
    model: str,
    paper_content: str,
    census: dict[str, Any],
    relations: list[dict[str, Any]],
    max_workers: int = DEFAULT_PARALLEL_MAX_WORKERS,
    temperature: float = 0.0,
    max_tokens: int = DEFAULT_SECTION_MAX_TOKENS,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
    blob_primary_evidence: bool = False,
) -> dict[str, Any]:
    """Run the four content sections (stage C) over a shared prefix, then assemble 0.7 output."""
    parsed_sections = parse_sections(paper_content)
    sections_included = _sort_section_refs({f"§{section_id}" for section_id in parsed_sections})
    sections_omitted: list[str] = []
    node_registry = build_node_registry(census)
    spine_summary = census.get("spine_summary") if isinstance(census.get("spine_summary"), dict) else None
    cache_key = prompt_cache_key if prompt_cache_key is not None else build_prompt_cache_key(model, paper_content)

    section_types = list(SECTION_ORDER)
    ordered_results: list[dict[str, Any] | None] = [None] * len(section_types)

    def run_one(section_type: str) -> dict[str, Any]:
        return extract_single_content_section_sync(
            client,
            model,
            section_type,
            paper_content,
            node_registry,
            relations,
            spine_summary=spine_summary,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=MAX_SECTION_RETRIES,
            prompt_cache_key=cache_key,
            prompt_cache_retention=prompt_cache_retention,
            blob_primary_evidence=blob_primary_evidence,
        )

    # Seed the shared paper prefix into the cache with the first call, then fan out.
    try:
        ordered_results[0] = run_one(section_types[0])
    except Exception as exc:
        raise RuntimeError(f"Content extraction failed for section {section_types[0]}") from exc

    remaining = list(enumerate(section_types[1:], start=1))
    if remaining:
        worker_count = max(1, min(max_workers, len(remaining)))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {
                pool.submit(run_one, section_type): (index, section_type)
                for index, section_type in remaining
            }
            for future in as_completed(futures):
                index, section_type = futures[future]
                try:
                    ordered_results[index] = future.result()
                except Exception as exc:
                    raise RuntimeError(f"Content extraction failed for section {section_type}") from exc

    section_results = [result for result in ordered_results if result is not None]
    return assemble_extraction(
        census,
        relations,
        section_results,
        paper_content,
        sections_included=sections_included,
        sections_omitted=sections_omitted,
        blob_primary_evidence=blob_primary_evidence,
    )


def run_pipeline(
    client: Any,
    model: str,
    paper_content: str,
    output_dir: Path | str | None = None,
    paper_id: str = "paper",
    temperature: float = 0.0,
    max_tokens: int = 16_384,
    max_workers: int = DEFAULT_PARALLEL_MAX_WORKERS,
    section_max_tokens: int = DEFAULT_SECTION_MAX_TOKENS,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
    strict: bool = True,
    blob_primary_evidence: bool = False,
) -> dict[str, Any]:
    """Run census + metadata + references in parallel, then the relation pass, content fill, and validation."""
    pipeline_warnings: list[str] = []
    cache_key = prompt_cache_key if prompt_cache_key is not None else build_prompt_cache_key(model, paper_content)
    with ThreadPoolExecutor(max_workers=3) as executor:
        census_future = executor.submit(
            run_node_census, client, model, paper_content,
            temperature=temperature, max_tokens=max_tokens,
            prompt_cache_key=cache_key, prompt_cache_retention=prompt_cache_retention,
        )
        metadata_future = executor.submit(
            run_metadata_extraction, client, model, paper_content, temperature=temperature, max_tokens=max_tokens
        )
        references_future = executor.submit(
            run_references_extraction, client, model, paper_content, temperature=temperature, max_tokens=max_tokens
        )
        raw_census = census_future.result()
        try:
            metadata = metadata_future.result()
        except Exception as exc:
            metadata = None
            pipeline_warnings.append(f"metadata extraction failed: {exc}")
        try:
            references = references_future.result()
        except Exception as exc:
            references = None
            pipeline_warnings.append(f"references extraction failed: {exc}")

    census = normalize_census_nodes(raw_census)
    census_issues = validate_census(census)
    if census_issues:
        details = "\n- ".join(census_issues)
        raise ValueError(f"Node census validation failed:\n- {details}")

    node_registry = build_node_registry(census)
    relation_output = run_relation_pass(
        client, model, paper_content, node_registry,
        temperature=temperature, max_tokens=max_tokens,
        prompt_cache_key=cache_key, prompt_cache_retention=prompt_cache_retention,
    )
    relations = relation_output.get("relations") if isinstance(relation_output, dict) else None
    if not isinstance(relations, list):
        relations = []

    extraction = run_content_extraction_sync(
        client,
        model,
        paper_content,
        census,
        relations,
        max_workers=max_workers,
        temperature=temperature,
        max_tokens=section_max_tokens,
        prompt_cache_key=cache_key,
        prompt_cache_retention=prompt_cache_retention,
        blob_primary_evidence=blob_primary_evidence,
    )
    if references is not None:
        pipeline_warnings.extend(reconcile_reference_units(references, extraction, census))
    validation_issues = validate_section_ir(extraction, census=census)
    result = {
        "census": census,
        "relations": relations,
        "extraction": extraction,
        "metadata": metadata,
        "references": references,
        "validation_issues": validation_issues,
        "pipeline_warnings": pipeline_warnings,
    }

    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / f"{paper_id}_census.json").write_text(
            json.dumps(census, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_path / f"{paper_id}_extraction.json").write_text(
            json.dumps(extraction, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_path / f"{paper_id}_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_path / f"{paper_id}_references.json").write_text(
            json.dumps(references, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_path / f"{paper_id}_pipeline.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if strict and validation_issues:
        raise ValidationError(validation_issues)
    return result


def _contains_legacy_marker(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key == "paradigm_tags" or _contains_legacy_marker(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_legacy_marker(item) for item in value)
    return value in FORBIDDEN_UNIT_TYPES


def _validate_provenance(unit: dict[str, Any], issues: list[str]) -> None:
    uid = unit.get("id", "<missing-id>")
    provenance = unit.get("provenance")
    if not isinstance(provenance, list):
        issues.append(f"Unit {uid} provenance must be a list")
        return

    if unit.get("type") in {"Finding", "Measure"} and not provenance:
        issues.append(f"{unit.get('type')} {uid} must have non-empty provenance")

    for index, marker in enumerate(provenance):
        if not isinstance(marker, str) or not PROVENANCE_SOURCE_RE.match(marker):
            issues.append(f"Unit {uid} provenance[{index}] '{marker}' must be a §N location marker")


def _validate_formula_symbols(
    uid: str,
    where: str,
    symbols: Any,
    issues: list[str],
) -> None:
    """Validate the optional symbol gloss on a formula or objective_function.

    Each entry maps one symbol/variable from the expression to its meaning; both
    fields must be non-empty when an entry is present. The array may be empty when
    the expression introduces no symbols to define.
    """
    if symbols is None:
        return
    if not isinstance(symbols, list):
        issues.append(f"Method {uid} {where} symbols must be a list")
        return
    for index, entry in enumerate(symbols):
        if not isinstance(entry, dict):
            issues.append(f"Method {uid} {where} symbols[{index}] must be an object")
            continue
        if not entry.get("symbol"):
            issues.append(f"Method {uid} {where} symbols[{index}] missing symbol")
        if not entry.get("description"):
            issues.append(f"Method {uid} {where} symbols[{index}] missing description")


def _validate_unit_fields(
    unit: dict[str, Any],
    unit_index: dict[str, dict[str, Any]],
    unit_sections: dict[str, str],
    local_ids: set[str],
    issues: list[str],
) -> None:
    uid = unit.get("id", "<missing-id>")
    utype = unit.get("type")

    # `role` is the fine-grained differentia carried on every unit type that has one
    # (Document/Method/ExperimentSetup/Finding). Problem and Measure carry no role.
    role = unit.get("role")
    role_vocab = ROLE_VOCAB_BY_TYPE.get(utype)
    if role_vocab is not None:
        if not role:
            issues.append(f"{utype} {uid} missing role")
        elif role not in role_vocab:
            issues.append(f"{utype} {uid} has invalid role: {role}")

    if utype == "Document":
        for key in ("doc_id", "title"):
            if not unit.get(key):
                issues.append(f"Document {uid} missing {key}")
    elif utype == "ExperimentSetup":
        if not unit.get("name"):
            issues.append(f"ExperimentSetup {uid} missing name")
    elif utype == "Method":
        if not unit.get("name"):
            issues.append(f"Method {uid} missing name")
        # method_kind is an OPTIONAL descriptive attribute (orthogonal to role); validate when present.
        method_kind = unit.get("method_kind")
        if method_kind is not None and method_kind not in METHOD_KINDS:
            issues.append(f"Method {uid} has invalid method_kind: {method_kind}")
        # inputs/outputs/formulas/objective_function are optional; validate shape only when present.
        formulas = unit.get("formulas")
        if formulas is not None:
            if not isinstance(formulas, list):
                issues.append(f"Method {uid} formulas must be a list")
            else:
                for index, formula in enumerate(formulas):
                    if not isinstance(formula, dict):
                        issues.append(f"Method {uid} formulas[{index}] must be an object")
                        continue
                    if not formula.get("expression"):
                        issues.append(f"Method {uid} formulas[{index}] missing expression")
                    _validate_formula_symbols(
                        uid, f"formulas[{index}]", formula.get("symbols"), issues
                    )
        objective = unit.get("objective_function")
        if objective is not None:
            if not isinstance(objective, dict):
                issues.append(f"Method {uid} objective_function must be an object")
            else:
                if not objective.get("expression"):
                    issues.append(f"Method {uid} objective_function missing expression")
                _validate_formula_symbols(
                    uid, "objective_function", objective.get("symbols"), issues
                )
    elif utype == "Finding":
        if not unit.get("statement"):
            issues.append(f"Finding {uid} missing statement")
        # Optional FG-11 payload: `polarity` is an enum when present; effect_size/scope are free text.
        polarity = unit.get("polarity")
        if polarity is not None and polarity not in FINDING_POLARITIES:
            issues.append(f"Finding {uid} has invalid polarity: {polarity}")
    elif utype == "Problem":
        if not unit.get("description"):
            issues.append(f"Problem {uid} missing description")
    elif utype == "Measure":
        for key in ("name", "unit"):
            if not unit.get(key):
                issues.append(f"Measure {uid} missing {key}")
        scores = unit.get("scores")
        has_marker = bool(unit.get("source_table_marker"))
        if not isinstance(scores, list):
            issues.append(f"Measure {uid} scores must be a non-empty list")
        elif not scores and not has_marker:
            # 0.12 (blob-primary): an ablation/table-blob Measure may carry empty scores, but only
            # when it points at its source table by marker (the blob carries the data). A marker-less
            # empty Measure is dataless and is dropped in assembly.
            issues.append(f"Measure {uid} scores must be a non-empty list")
        else:
            for index, score in enumerate(scores):
                if not isinstance(score, dict):
                    issues.append(f"Measure {uid} scores[{index}] must be an object")
                    continue
                if not score.get("variant"):
                    issues.append(f"Measure {uid} scores[{index}] missing variant")
                if score.get("value") is None:
                    issues.append(f"Measure {uid} scores[{index}] missing value")
                elif not isinstance(score.get("value"), str):
                    issues.append(f"Measure {uid} scores[{index}] value must be a string")
                if not isinstance(score.get("variance"), str):
                    issues.append(f"Measure {uid} scores[{index}] variance must be a string")
                # Optional FG-2 value kind: how to read the (string) value. Omitted ⇒ numeric.
                value_kind = score.get("value_kind")
                if value_kind is not None and value_kind not in SCORE_VALUE_KINDS:
                    issues.append(
                        f"Measure {uid} scores[{index}] has invalid value_kind: {value_kind}"
                    )
                # Per-row references: a row may name the Method it reports (system_id, global)
                # and the local ExperimentSetup it was measured under (setup_id). In 0.9 the
                # setup_id also carries the dataset/split — it is how a Measure binds to its
                # data, replacing the removed `measured_on` edge. Both are optional ("" means
                # "not pinned") but when non-empty must resolve.
                system_id = score.get("system_id")
                if system_id:
                    system_unit = unit_index.get(system_id)
                    if system_unit is None:
                        issues.append(f"Measure {uid} scores[{index}] has unknown system_id: {system_id}")
                    elif system_unit.get("type") != "Method":
                        issues.append(f"Measure {uid} scores[{index}] system_id {system_id} must point to a Method")
                row_setup_id = score.get("setup_id")
                if row_setup_id:
                    row_setup_unit = unit_index.get(row_setup_id)
                    if row_setup_unit is None:
                        issues.append(f"Measure {uid} scores[{index}] has unknown setup_id: {row_setup_id}")
                    elif row_setup_id not in local_ids:
                        issues.append(f"Measure {uid} scores[{index}] setup_id must be section-local: {row_setup_id}")
                    elif row_setup_unit.get("type") != "ExperimentSetup":
                        issues.append(f"Measure {uid} scores[{index}] setup_id {row_setup_id} must point to a local ExperimentSetup")
                # FG-6 (optional): a pairwise/win-rate row names its opponent (the other system in
                # an A-vs-B comparison → a Method), and a judged row names its judge (an LLM/human
                # evaluator → a Method or an inference_protocol ExperimentSetup). Both optional;
                # when non-empty must resolve to a unit of the right type.
                opponent_id = score.get("opponent_id")
                if opponent_id:
                    opponent_unit = unit_index.get(opponent_id)
                    if opponent_unit is None:
                        issues.append(f"Measure {uid} scores[{index}] has unknown opponent_id: {opponent_id}")
                    elif opponent_unit.get("type") != "Method":
                        issues.append(f"Measure {uid} scores[{index}] opponent_id {opponent_id} must point to a Method")
                judge_id = score.get("judge_id")
                if judge_id:
                    judge_unit = unit_index.get(judge_id)
                    if judge_unit is None:
                        issues.append(f"Measure {uid} scores[{index}] has unknown judge_id: {judge_id}")
                    elif judge_unit.get("type") not in {"Method", "ExperimentSetup"}:
                        issues.append(f"Measure {uid} scores[{index}] judge_id {judge_id} must point to a Method or ExperimentSetup")
        # setup_ids scope a measure to local ExperimentSetup units. It is optional: a deployable
        # measure is normally scoped by one setup, an ablation measure may carry none.
        setup_ids = unit.get("setup_ids")
        if setup_ids is None:
            issues.append(f"Measure {uid} missing setup_ids")
        elif not isinstance(setup_ids, list):
            issues.append(f"Measure {uid} setup_ids must be a list")
        else:
            for setup_id in setup_ids:
                setup_unit = unit_index.get(setup_id)
                if setup_unit is None:
                    issues.append(f"Measure {uid} has unknown setup_id: {setup_id}")
                elif setup_id not in local_ids:
                    issues.append(f"Measure {uid} setup_id must be section-local: {setup_id}")
                elif setup_unit.get("type") != "ExperimentSetup":
                    issues.append(
                        f"Measure {uid} setup_id {setup_id} must point to a local ExperimentSetup"
                    )
        comparison_direction = unit.get("comparison_direction")
        if "comparison_direction" in unit and comparison_direction not in COMPARISON_DIRECTIONS:
            issues.append(f"Measure {uid} has invalid comparison_direction: {comparison_direction}")
        objective_class = unit.get("objective_class")
        if objective_class is not None and objective_class not in MEASURE_OBJECTIVE_CLASSES:
            issues.append(f"Measure {uid} has invalid objective_class: {objective_class}")
        # 0.12 blob-primary fields (all optional). Structure/enum/referential checks here; marker
        # resolution against extraction_notes.source_tables is enforced loudly in assembly
        # (_validate_finding_mounts), which is where source_tables is in hand.
        table_role = unit.get("table_role")
        if table_role is not None and table_role not in MEASURE_TABLE_ROLES:
            issues.append(f"Measure {uid} has invalid table_role: {table_role}")
        for marker_key in ("source_table_marker", "caption_marker"):
            marker = unit.get(marker_key)
            if marker is not None and not isinstance(marker, str):
                issues.append(f"Measure {uid} {marker_key} must be a string")
        headline = unit.get("headline_result")
        if headline is not None and not isinstance(headline, str):
            issues.append(f"Measure {uid} headline_result must be a string")
        finding_ids = unit.get("finding_ids")
        if finding_ids is not None:
            if not isinstance(finding_ids, list):
                issues.append(f"Measure {uid} finding_ids must be a list")
            else:
                for fid in finding_ids:
                    target = unit_index.get(fid) if isinstance(fid, str) else None
                    if target is None:
                        issues.append(f"Measure {uid} finding_ids has unknown id: {fid}")
                    elif target.get("type") != "Finding":
                        issues.append(f"Measure {uid} finding_ids {fid} must point to a Finding")


def _validate_relation(
    relation: dict[str, Any],
    unit_index: dict[str, dict[str, Any]],
    issues: list[str],
) -> None:
    if not isinstance(relation, dict):
        issues.append("relation must be an object")
        return

    source_id = relation.get("source_id")
    target_id = relation.get("target_id")
    rel = relation.get("relation")
    source_unit = unit_index.get(source_id)
    target_unit = unit_index.get(target_id)

    if source_unit is None:
        issues.append(f"relation has unknown source_id: {source_id}")
    if target_unit is None:
        issues.append(f"relation has unknown target_id: {target_id}")

    # provenance is schema-required on every relation (an array of §N markers). Strict decoding
    # enforces it in json_schema mode, but json_object (DeepSeek) mode treats the schema as prompt
    # guidance only, so the runtime contract must check it here. An empty list is allowed (matching
    # the schema, which sets no minItems, and the synthesized `resolves` edge's provenance fallback).
    provenance = relation.get("provenance")
    if not isinstance(provenance, list):
        issues.append(f"relation {source_id} -[{rel}]-> {target_id} provenance must be a list")
    else:
        for index, marker in enumerate(provenance):
            if not isinstance(marker, str) or not PROVENANCE_SOURCE_RE.match(marker):
                issues.append(
                    f"relation {source_id} -[{rel}]-> {target_id} provenance[{index}] "
                    f"'{marker}' must be a §N location marker"
                )

    matrix = RELATION_MATRIX.get(rel)
    if matrix is None:
        issues.append(f"relation has invalid relation: {rel}")
        return

    allowed_sources, allowed_targets = matrix
    if source_unit is not None and source_unit.get("type") not in allowed_sources:
        issues.append(
            f"relation {source_id} -[{rel}]-> {target_id} has invalid source type: "
            f"{source_unit.get('type')}"
        )
    if target_unit is not None and target_unit.get("type") not in allowed_targets:
        issues.append(
            f"relation {source_id} -[{rel}]-> {target_id} has invalid target type: "
            f"{target_unit.get('type')}"
        )


def validate_section_ir(extraction: dict[str, Any], census: dict[str, Any] | None = None) -> list[str]:
    """Validate section-IR 0.7 output: typed units, global relations, and census coverage."""
    issues: list[str] = []
    if not isinstance(extraction, dict):
        return ["Extraction must be a JSON object"]

    required_top = {"document", "sections", "relations", "extraction_notes"}
    for key in sorted(required_top - set(extraction)):
        issues.append(f"Missing top-level key: {key}")
    allowed_top = required_top
    for key in sorted(set(extraction) - allowed_top):
        issues.append(f"Unexpected top-level key: {key}")

    if _contains_legacy_marker(extraction):
        issues.append("Legacy paradigm fields or forbidden unit types are present")

    unit_index: dict[str, dict[str, Any]] = {}
    unit_locations: dict[str, str] = {}
    unit_sections: dict[str, str] = {}
    unit_local_ids: dict[str, set[str]] = {}
    section_unit_ids: list[set[str]] = []

    def register_unit(unit: Any, location: str) -> None:
        if not isinstance(unit, dict):
            issues.append(f"{location} unit must be an object")
            return
        uid = unit.get("id")
        utype = unit.get("type")
        if "section_type" in unit:
            issues.append(f"Unit {uid or '<missing-id>'} must not contain section_type")
        if not isinstance(uid, str) or not ID_RE.match(uid):
            issues.append(f"{location} unit has invalid id: {uid}")
        if utype not in UNIT_TYPES:
            issues.append(f"Unit {uid or '<missing-id>'} has invalid type: {utype}")
        if isinstance(uid, str) and isinstance(utype, str) and utype in UNIT_ID_PREFIX_BY_TYPE:
            expected_prefix = UNIT_ID_PREFIX_BY_TYPE[utype]
            if not uid.startswith(expected_prefix):
                issues.append(
                    f"unit '{uid}' has type {utype} but ID prefix does not match expected '{expected_prefix}'"
                )
        if isinstance(utype, str) and utype in ALLOWED_FIELDS_BY_TYPE:
            extra_fields = sorted(set(unit) - ALLOWED_FIELDS_BY_TYPE[utype])
            if extra_fields:
                field_label = "field" if len(extra_fields) == 1 else "fields"
                issues.append(
                    f"Unit {uid or '<missing-id>'} has unexpected {field_label}: "
                    f"{', '.join(extra_fields)}"
                )
        if utype in FORBIDDEN_UNIT_TYPES:
            issues.append(f"Unit {uid or '<missing-id>'} uses forbidden legacy type: {utype}")
        if isinstance(uid, str):
            if uid in unit_index:
                issues.append(f"Duplicate unit id: {uid} in {location}; first seen in {unit_locations[uid]}")
            else:
                unit_index[uid] = unit
                unit_locations[uid] = location

    document = extraction.get("document")
    if isinstance(document, dict):
        register_unit(document, "document")
        if document.get("type") != "Document":
            issues.append(f"document must be a Document unit, got {document.get('type')}")
    elif "document" in extraction:
        issues.append("document must be an object")

    sections_list = extraction.get("sections", [])
    if not isinstance(sections_list, list):
        issues.append("sections must be a list")
        sections_list = []
    for s_index, section in enumerate(sections_list):
        local_ids: set[str] = set()
        if not isinstance(section, dict):
            issues.append(f"Section {s_index} must be an object")
            section_unit_ids.append(local_ids)
            continue
        extra_section_fields = sorted(set(section) - ALLOWED_SECTION_FIELDS)
        if extra_section_fields:
            field_label = "field" if len(extra_section_fields) == 1 else "fields"
            issues.append(
                f"Section {s_index} has unexpected {field_label}: "
                f"{', '.join(extra_section_fields)}"
            )
        if "anchor" in section:
            issues.append(f"Section {s_index} uses legacy inline anchor; use anchor_id")
        units = section.get("units", [])
        if not isinstance(units, list):
            issues.append(f"Section {s_index} units must be a list")
            units = []
        for unit in units:
            register_unit(unit, f"sections[{s_index}].units")
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                local_ids.add(unit["id"])
                if isinstance(section.get("section_type"), str):
                    unit_sections.setdefault(unit["id"], section["section_type"])
                unit_local_ids.setdefault(unit["id"], local_ids)
        section_unit_ids.append(local_ids)

    for unit in list(unit_index.values()):
        _validate_provenance(unit, issues)
    for unit in list(unit_index.values()):
        _validate_unit_fields(unit, unit_index, unit_sections, unit_local_ids.get(unit.get("id"), set()), issues)

    covered_entries: set[str] = set()
    for s_index, section in enumerate(sections_list):
        if not isinstance(section, dict):
            continue
        units = section.get("units", [])
        if not isinstance(units, list):
            units = []
        section_type = section.get("section_type")
        if section_type not in SECTION_TYPES:
            issues.append(f"Section {s_index} has invalid section_type: {section_type}")
        else:
            allowed_unit_types = SECTION_ALLOWED_UNIT_TYPES.get(section_type, set())
            for unit in units:
                if not isinstance(unit, dict):
                    continue
                if unit.get("type") not in allowed_unit_types:
                    issues.append(
                        f"Section {s_index} ({section_type}) contains unit {unit.get('id', '<missing-id>')} "
                        f"with invalid type for section: {unit.get('type')}"
                    )

        anchor_id = section.get("anchor_id")
        if not isinstance(anchor_id, str):
            issues.append(f"Section {s_index} missing anchor_id")
        elif anchor_id not in unit_index:
            issues.append(f"Section {s_index} anchor_id is undefined: {anchor_id}")
        elif anchor_id not in section_unit_ids[s_index]:
            issues.append(f"Section {s_index} anchor_id must refer to a unit defined in that section: {anchor_id}")
        elif unit_index[anchor_id].get("type") == "Document":
            issues.append(f"Section {s_index} anchor_id cannot point to Document: {anchor_id}")

        covers_entries = section.get("covers_entries")
        if not isinstance(covers_entries, list):
            issues.append(f"Section {s_index} covers_entries must be a list")
        else:
            for entry_id in covers_entries:
                if isinstance(entry_id, str):
                    covered_entries.add(entry_id)
                else:
                    issues.append(f"Section {s_index} covers_entries contains non-string value: {entry_id}")

    # Global relations (section-ir-0.7): a single top-level edge list, validated against
    # the relation type matrix with endpoints resolving to any defined unit.
    relations_list = extraction.get("relations", [])
    if not isinstance(relations_list, list):
        issues.append("relations must be a list")
        relations_list = []
    for relation in relations_list:
        _validate_relation(relation, unit_index, issues)

    incoming_argumentative = {
        relation.get("target_id")
        for relation in relations_list
        if isinstance(relation, dict) and relation.get("relation") in ARGUMENTATIVE_INCOMING
    }
    for uid, unit in unit_index.items():
        if unit.get("type") == "Finding":
            if (
                unit_sections.get(uid) != "evidence"
                and uid not in incoming_argumentative
            ):
                issues.append(f"Finding {uid} lacks an incoming argumentative (supports) relation")

    notes = extraction.get("extraction_notes")
    if not isinstance(notes, dict):
        issues.append("extraction_notes must be an object")
        notes = {}
    else:
        for key in (
            "ir_version",
            "sections_used",
            "uncertain_assignments",
            "skipped_spans",
            "input_mode",
            "uncovered_items",
            "plan_coverage",
        ):
            if key not in notes:
                issues.append(f"extraction_notes missing {key}")
        if notes.get("input_mode") != "node_census_pipeline":
            issues.append(f"extraction_notes has invalid input_mode: {notes.get('input_mode')}")
        if notes.get("ir_version") != "section-ir-0.12":
            issues.append(f"extraction_notes has invalid ir_version: {notes.get('ir_version')}")
        sections_used = notes.get("sections_used", [])
        if isinstance(sections_used, list):
            invalid_sections = [st for st in sections_used if st not in SECTION_TYPES]
            if invalid_sections:
                issues.append(f"extraction_notes.sections_used has invalid values: {invalid_sections}")

    # 0.12 blob-primary: a Measure's source_table_marker must resolve to a captured [§N] table block
    # (extraction_notes.source_tables is a dict keyed by §N). An unresolved marker means the verbatim
    # table cannot be attached — a grounding hazard — so it is a hard issue. (caption_marker points at
    # a separate caption block resolved against the paper text in assembly, not here.)
    source_tables = notes.get("source_tables") if isinstance(notes, dict) else None
    table_markers = set(source_tables) if isinstance(source_tables, dict) else set()
    for uid, unit in unit_index.items():
        if unit.get("type") != "Measure":
            continue
        raw_marker = unit.get("source_table_marker")
        if raw_marker and _canon_marker(raw_marker) not in table_markers:
            issues.append(
                f"Measure {uid} source_table_marker {raw_marker!r} does not resolve to a captured source table"
            )

    if census is not None:
        _validate_census_trace(census, covered_entries, unit_index, notes, issues)

    return issues


def _validate_census_trace(
    census: dict[str, Any],
    covered_entries: set[str],
    unit_index: dict[str, dict[str, Any]],
    notes: dict[str, Any],
    issues: list[str],
) -> None:
    """Trace assembled units back to the node census: every must-node must be materialized."""
    nodes = census.get("nodes")
    if not isinstance(nodes, list):
        issues.append("census.nodes must be a list")
        return

    node_ids = all_census_node_ids(census)
    must_node_ids = census_must_node_ids(census)

    uncovered_items_raw = notes.get("uncovered_items", [])
    uncovered_items: set[str] = set()
    if not isinstance(uncovered_items_raw, list):
        issues.append("extraction_notes.uncovered_items must be a list")
    else:
        for item in uncovered_items_raw:
            if not isinstance(item, dict) or not isinstance(item.get("item_id"), str) or not item.get("reason"):
                issues.append(f"Invalid uncovered_items item: {item}")
                continue
            uncovered_items.add(item["item_id"])

    unknown_covered = sorted(covered_entries - node_ids)
    if unknown_covered:
        issues.append(f"covers_entries references unknown census nodes: {unknown_covered}")
    # uncovered_items is assembly-built (never model-written): it lists uncovered census must-nodes
    # AND, since 0.10 (FG-10 D1), assembly-dropped non-census units (e.g. a born/should Measure
    # dropped for empty scores). Only the census-node entries are constrained — the must-node
    # accounting below ensures every must-node is materialized or declared uncovered; the dropped-
    # unit entries are an informational superset, so they are not required to be census nodes.

    for entry_id in sorted(covered_entries):
        if entry_id not in unit_index:
            issues.append(f"covers_entries claims '{entry_id}' but no unit with this ID exists")

    missing_must = sorted(must_node_ids - covered_entries - uncovered_items)
    if missing_must:
        issues.append(f"must census nodes neither materialized nor declared uncovered: {missing_must}")

    coverage = notes.get("plan_coverage", {})
    if isinstance(coverage, dict):
        expected_covered = len(must_node_ids & covered_entries)
        expected_total = len(must_node_ids)
        if coverage.get("must_covered") != expected_covered:
            issues.append(
                "plan_coverage.must_covered does not match materialized census nodes: "
                f"{coverage.get('must_covered')} != {expected_covered}"
            )
        if coverage.get("must_total") != expected_total:
            issues.append(
                "plan_coverage.must_total does not match census: "
                f"{coverage.get('must_total')} != {expected_total}"
            )
    else:
        issues.append("extraction_notes.plan_coverage must be an object")
