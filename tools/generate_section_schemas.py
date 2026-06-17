#!/usr/bin/env python3
"""Generate per-section typed-array schemas plus the node-census and relation-pass schemas.

The pipeline is three stages — node census (stage A), relation pass (stage B), and
per-section content fill (stage C); stage descriptions embed the release tag from
``section_pipeline.IR_VERSION``. This script owns exactly five committed schemas,
generated from the controlled vocabularies in ``section_pipeline.py``:
``section-{problem,method,evidence}.schema.json``, ``node-census-output.schema.json``
and ``relation-pass-output.schema.json``. The other structured-output contracts —
``metadata-output.schema.json``, ``citations-output.schema.json`` and
``reference-metadata.schema.json`` — are hand-maintained and NOT generated here. It is authoritative only while kept in sync
with the five owned ``schemas/*.json``: schema changes are sometimes hand-edited into
the committed schemas first (e.g. blob-primary evidence), so port any hand-edit back
here, then VERIFY after running this script that ``git diff schemas/`` shows only the
changes you intended (regeneration clobbers anything not ported).

Each unit carries a primary ``type`` and, on the multi-kind types (Contribution, ExperimentSetup,
Finding), a ``kind`` sub-axis (the discipline-specific differentia). Component, Problem and Measure
are single-level and carry no ``kind``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from section_pipeline import (  # noqa: E402
    COMPARISON_DIRECTIONS,
    CONTRIBUTION_KINDS,
    EXPERIMENT_SETUP_KINDS,
    FINDING_KINDS,
    FINDING_POLARITIES,
    FORMULA_ROLES,
    IR_VERSION,
    MEASURE_OBJECTIVE_CLASSES,
    MEASURE_TABLE_ROLES,
    METHOD_KINDS,
    NODE_TYPES,
    SCORE_VALUE_KINDS,
    SECTION_AUTHORS_RELATIONS,
    STAGE_B_RELATIONS,
    STAGE_C_RELATIONS,
    SUBSTRATE_KINDS,
)

SCHEMAS_DIR = PROJECT_ROOT / "schemas"
ID_PATTERN = r"^[a-z][a-z0-9_]*:[a-z0-9_]+$"

# Typed unit arrays each content section (stage C) returns.
SECTION_TYPED_ARRAYS: dict[str, list[str]] = {
    "problem": ["problems"],
    # A Contribution is materialized by the section that describes it: kind method in the
    # method section, kind dataset/benchmark/finding in the evidence section — so `contributions`
    # appears in both (section-ir-0.17).
    "method": ["contributions", "components"],
    "evidence": ["contributions", "measures", "experiment_setups", "findings"],
}

# Fields that are optional on a unit type (everything else in its property set is required).
# method_kind is an optional finer descriptor (the required differentia on a Contribution is `kind`);
# ExperimentSetup carries an optional description and cite_keys.
# `implementation_notes` is optional (0.10, FG-2): a non-implementation Method — a theorem/lemma/
# bound/definition or a resource/taxonomy deliverable — carries no reproducibility notes, so it is
# not forced to emit the field. Normal algorithmic methods still fill it (method.md asks for it);
# making it schema-optional is additive (every existing 0.9 output already carries it).
OPTIONAL_FIELDS_BY_TYPE: dict[str, set[str]] = {
    # Blob-primary evidence (section-ir-0.12): the table-binding fields
    # (source_table_marker/caption_marker/table_role/headline_result/finding_ids) are all
    # optional — a prose-derived measure carries none of them.
    "Measure": {"comparison_direction", "objective_class",
                "source_table_marker", "caption_marker", "table_role", "headline_result",
                "finding_ids"},
    "Contribution": {"method_kind", "inputs", "outputs", "formulas", "implementation_notes"},
    "Component": {"method_kind", "inputs", "outputs", "formulas", "implementation_notes"},
    "ExperimentSetup": {"description"},
    # FG-11 (section-ir-0.10): optional Finding quantitative payload.
    "Finding": {"polarity", "effect_size", "scope"},
}

ARRAY_TYPE_NAMES: dict[str, str] = {
    "problems": "Problem",
    "contributions": "Contribution",
    "components": "Component",
    "experiment_setups": "ExperimentSetup",
    "measures": "Measure",
    "findings": "Finding",
}

# Census node types and the unit-level kind vocabularies, with explicit ordering for stable
# schemas (section-ir-0.17). Census types are listed in search-cluster order (the_solution,
# evaluation_frame, the_problem). The census is internal-only: prior-art methods are NOT census
# nodes (the citation layer captures them). Findings are not census nodes either — every Finding
# is born during evidence content fill — so Finding is absent from CENSUS_TYPE_ORDER, but
# FINDING_KIND_ORDER still drives the evidence-section Finding `kind` enum.
CENSUS_TYPE_ORDER = ["Contribution", "Component", "ExperimentSetup", "Measure", "Problem"]
CONTRIBUTION_KIND_ORDER = ["method", "dataset", "benchmark", "finding"]
EXPERIMENT_SETUP_KIND_ORDER = [
    "dataset", "benchmark", "task",
    "data_split", "inference_protocol", "training_config", "ensembling", "population",
]
FINDING_KIND_ORDER = [
    "descriptive", "mechanistic", "comparative", "modeling", "ablation_finding", "failure_mode",
    "theorem", "lemma", "bound",
]
# The census `kind` enum = the kinds emittable in the census (Contribution kinds + substrate kinds);
# required on a Contribution/ExperimentSetup node, omitted on Component/Measure/Problem.
CENSUS_KIND_ORDER = ["method", "dataset", "benchmark", "finding", "task"]
STAGE_B_RELATION_ORDER = ["part_of", "builds_on", "uses", "co_contribution",
                          "compares_to", "evaluates"]
# Stage-C edges each content section authors, ordered as they appear in its schema enum.
# problem authors only `motivates` (Problem -> the census Method/ExperimentSetup it justifies);
# evidence authors the Finding-centric `about`/`supports`. The closing `resolves` (Finding ->
# Problem) is synthesized in assembly, not authored by any section, so it appears in no
# stage-C enum. Scoping the enum per section keeps each section's contract tight — it matters
# most for json_object models (DeepSeek), whose only constraint is the in-prompt contract.
STAGE_C_RELATIONS_BY_SECTION: dict[str, list[str]] = {
    "problem": ["motivates"],
    "evidence": ["about", "supports"],
}
# One-line gloss per stage-C relation, joined into the schema field description.
STAGE_C_RELATION_GLOSS: dict[str, str] = {
    "about": "about = a Finding is about a Contribution/Component or ExperimentSetup (never a Measure — mount table↔finding links via the Measure's finding_ids)",
    "supports": "supports = a Finding, or a Contribution (e.g. one stating a proven theorem), supports a Finding (never Measure→Finding)",
    "motivates": "motivates = a Problem motivates the Contribution/Component/ExperimentSetup that addresses it",
}

# The relation order lists above ARE the schema enums, and a new relation cannot be
# auto-placed — stage B's cluster ordering and stage C's per-section routing (plus its
# gloss) are editorial decisions. So refuse to generate, rather than silently emit an
# enum that strict-mode decoding would use to reject a relation the runtime accepts.
if set(STAGE_B_RELATION_ORDER) != STAGE_B_RELATIONS:
    raise ValueError(
        "STAGE_B_RELATION_ORDER is out of sync with section_pipeline.STAGE_B_RELATIONS: "
        f"{sorted(set(STAGE_B_RELATION_ORDER) ^ STAGE_B_RELATIONS)}"
    )
_STAGE_C_UNION = {rel for rels in STAGE_C_RELATIONS_BY_SECTION.values() for rel in rels}
if _STAGE_C_UNION != STAGE_C_RELATIONS:
    raise ValueError(
        "STAGE_C_RELATIONS_BY_SECTION is out of sync with section_pipeline.STAGE_C_RELATIONS: "
        f"{sorted(_STAGE_C_UNION ^ STAGE_C_RELATIONS)}"
    )

ENUM_ORDER: dict[str, list[str]] = {
    "census_type": CENSUS_TYPE_ORDER,
    "census_kind": CENSUS_KIND_ORDER,
    "contribution_kind": CONTRIBUTION_KIND_ORDER,
    "experiment_setup_kind": EXPERIMENT_SETUP_KIND_ORDER,
    "finding_kind": FINDING_KIND_ORDER,
    "method_kind": ["algorithm", "model_architecture", "training_strategy", "objective_function",
                    "resource", "taxonomy", "theorem", "lemma", "bound", "definition"],
    "formula_role": ["objective"],
    "comparison_direction": ["higher_is_better", "lower_is_better", "target", "unspecified"],
    "finding_polarity": ["positive", "negative", "neutral", "mixed"],
    "score_value_kind": ["numeric", "symbolic", "asymptotic", "qualitative", "curve"],
    "measure_objective_class": ["primary_quality", "cost_efficiency", "fairness", "safety", "robustness"],
    "measure_table_role": ["main_result", "ablation"],
}

ENUM_VALUES: dict[str, set[str]] = {
    "census_type": set(NODE_TYPES),
    "census_kind": set(CONTRIBUTION_KINDS) | set(SUBSTRATE_KINDS),
    "contribution_kind": set(CONTRIBUTION_KINDS),
    "experiment_setup_kind": set(EXPERIMENT_SETUP_KINDS),
    "finding_kind": set(FINDING_KINDS),
    "method_kind": METHOD_KINDS,
    "formula_role": FORMULA_ROLES,
    "comparison_direction": COMPARISON_DIRECTIONS,
    "finding_polarity": FINDING_POLARITIES,
    "score_value_kind": SCORE_VALUE_KINDS,
    "measure_objective_class": MEASURE_OBJECTIVE_CLASSES,
    "measure_table_role": MEASURE_TABLE_ROLES,
}


def ordered_enum(name: str) -> list[str]:
    values = ENUM_VALUES[name]
    preferred = [value for value in ENUM_ORDER[name] if value in values]
    return preferred + sorted(values - set(preferred))


def string_schema(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def id_schema(description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "pattern": ID_PATTERN,
        "description": description,
    }


def enum_schema(enum_name: str, description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "enum": ordered_enum(enum_name),
        "description": description,
    }


def string_array_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": description,
    }


def id_array_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string", "pattern": ID_PATTERN},
        "description": description,
    }


def measure_setup_ids_schema() -> dict[str, Any]:
    """`setup_ids` scopes a measure to local ExperimentSetup units in the evidence section.

    Optional in cardinality: a deployable measure may carry scoping setups while an ablation
    measure may carry none, so no min/max bound is imposed. The measure->method (`evaluates`)
    edge is a global relation; the measure->dataset binding is the per-row `setup_id`.
    """
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": "IDs of local ExperimentSetup units scoping this measure; empty when none apply",
    }


def scores_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["variant", "value", "variance", "system_id", "setup_id"],
            "additionalProperties": False,
            "properties": {
                "variant": {"type": "string", "description": "Name of the contribution configuration this score row reports, as the paper labels it (e.g. 'Transformer (big)', 'Ours (ResNet-101)'); on a dataset/benchmark Contribution's rows, the evaluated system's label"},
                "value": {
                    "type": "string",
                    "description": "Reported score encoded as a string, including numeric values",
                },
                "variance": {
                    "type": "string",
                    "description": "Uncertainty (e.g. '± 0.3'); empty string when unreported",
                },
                "system_id": {
                    "type": "string",
                    "description": "ID of the contribution (a Contribution/Component) this row reports (e.g. 'con:transformer'). In prose mode (a paper with no table grids), a transcribed baseline row carries the baseline's id instead; on a dataset/benchmark Contribution's evaluated-system rows, the evaluated system's id. Empty string when no node represents this row's system (e.g. an ensemble-of-baselines the census did not capture).",
                },
                "setup_id": {
                    "type": "string",
                    "description": "ID of the local ExperimentSetup unit this row was measured under — the dataset/split/protocol (e.g. 'exp:wmt14_ende'). This is how the row binds to its data. Empty string when the measure's own setup_ids already scope every row.",
                },
                "value_kind": enum_schema(
                    "score_value_kind",
                    "How to read `value`: numeric (a number, the default — omit the field), symbolic (a closed-form expression like '2/Δ·logT'), asymptotic (a complexity class like 'O(n^6)' or 'PSPACE-complete'), qualitative (a categorical verdict), or curve (a trend). Omit for an ordinary numeric leaderboard score.",
                ),
                "opponent_id": {
                    "type": "string",
                    "description": "Optional (FG-6): for a pairwise/win-rate row (A-vs-B), the id of the Contribution/Component this row's system was compared against — `system_id` is system A, `opponent_id` is system B, `value` is A's win rate vs B. Omit for an ordinary absolute-score row.",
                },
                "judge_id": {
                    "type": "string",
                    "description": "Optional (FG-6): for a judged row (LLM-as-judge or human evaluation), the id of the judge — a Contribution/Component, or an inference_protocol/population ExperimentSetup that was materialized for the evaluator. Omit when the score needs no judge.",
                },
            },
        },
        "description": description,
    }


def formulas_schema(description: str) -> dict[str, Any]:
    # section-ir-0.12 lean formulas: capture the equation itself (name + expression) but NOT a
    # per-symbol glossary. The symbols[] array was ~25% of method output bytes (87% of it the prose
    # descriptions) with no graph consumer — only the HTML renderer ever read it — so it is dropped
    # for cost. Symbol meanings stay recoverable from the expression and the method's description.
    # section-ir-0.14 unified equations: the standalone objective_function field is absorbed here.
    # The training/optimization target is the formulas[] entry tagged role="objective"; the sparse
    # tag keeps multi-objective methods representable and removes the systematic double
    # transcription (the same loss in both fields on 27.6% of OF-bearing methods). `description`
    # (what the objective optimizes) is allowed only on the objective-tagged entry so per-formula
    # prose does not regrow the 0.12 cost win.
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["name", "expression"],
            "additionalProperties": False,
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short label for the equation, e.g. 'Scaled Dot-Product Attention'; empty string when unnamed",
                },
                "expression": {
                    "type": "string",
                    "description": "The equation itself, as LaTeX or plain text, e.g. 'softmax(QK^T/sqrt(d_k))V'",
                },
                "role": enum_schema(
                    "formula_role",
                    "Functional tag: 'objective' marks the loss/optimization target the method "
                    "minimizes/maximizes (at most one entry per distinct objective; a method "
                    "with no stated objective tags nothing). Omit on ordinary defining "
                    "equations.",
                ),
                "description": {
                    "type": "string",
                    "description": "One line on what the objective optimizes; only on a "
                    "role='objective' entry — omit on all other formulas",
                },
            },
        },
        "description": description,
    }


def provenance_schema(noun: str = "unit") -> dict[str, Any]:
    return {
        "type": "array",
        "description": f"Location markers for this {noun}: top-level section anchors such as ['§1', '§2']",
        "items": {"type": "string"},
    }


def base_unit_properties(type_name: str) -> dict[str, Any]:
    return {
        "id": id_schema("Unit identifier in lowercase prefix:descriptor format"),
        "type": {
            "type": "string",
            "enum": [type_name],
            "description": "Unit type discriminator",
        },
        "provenance": provenance_schema(),
    }


def typed_unit_schemas(section_type: str) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {
        "ExperimentSetup": {
            **base_unit_properties("ExperimentSetup"),
            "kind": enum_schema(
                "experiment_setup_kind",
                "Which experimental ingredient this is — a substrate the method is tried on "
                "(dataset/benchmark/task) or a configuration that scopes a measure "
                "(data_split/inference_protocol/training_config/ensembling/population)",
            ),
            "name": string_schema("Name/label of the setup — a dataset name, a split label, a configuration name"),
            "description": string_schema(
                "Optional one-sentence prose describing the setup; empty string when the name suffices"
            ),
        },
        "Problem": {
            **base_unit_properties("Problem"),
            "description": string_schema(
                "The research problem in one or two sentences — the unresolved question or unmet "
                "need the paper addresses, with the necessary background folded into the prose"
            ),
        },
        "Finding": {
            **base_unit_properties("Finding"),
            "kind": enum_schema("finding_kind", "Classification of the finding"),
            "statement": string_schema("The finding as a single declarative sentence"),
            "polarity": enum_schema(
                "finding_polarity",
                "Optional sign of the finding's headline effect from the method/hypothesis's "
                "perspective: positive (confirms/improves), negative (refutes/degrades), neutral "
                "(no significant effect / a null result), mixed (direction depends on conditions); "
                "omit when not applicable",
            ),
            "effect_size": string_schema(
                "Optional magnitude of the effect in the paper's own terms (e.g. '+2.1 BLEU', "
                "'3 orders of magnitude faster', 'r=0.83'); omit when none is stated"
            ),
            "scope": string_schema(
                "Optional conditions/range under which the finding holds (e.g. 'on 11 of 12 "
                "tasks', 'in low-resource regimes'); omit when unrestricted"
            ),
        },
        "Contribution": {
            **base_unit_properties("Contribution"),
            "kind": enum_schema(
                "contribution_kind",
                "What KIND of deliverable this contribution is: method (an algorithm/technique/"
                "architecture/model, or a proven formal result such as a theorem/lemma/bound — tag "
                "those with method_kind), dataset, benchmark, or finding (an empirical/analysis "
                "result — the deliverable of an analysis paper with no novel artifact)",
            ),
            "name": string_schema("Name of the contribution"),
            "method_kind": enum_schema(
                "method_kind",
                "Optional finer structural classification on a kind=method contribution "
                "(algorithm/model_architecture/training_strategy/objective_function for an algorithmic "
                "method; theorem/lemma/bound/definition for a proven formal result; resource/taxonomy "
                "for a non-algorithmic deliverable); omit otherwise",
            ),
            "description": string_schema("Prose description of the contribution; empty string when unknown"),
            "inputs": string_array_schema("Inputs to the method; omit when not stated or the contribution is not an algorithm"),
            "outputs": string_array_schema("Outputs of the method; omit when not stated or the contribution is not an algorithm"),
            "formulas": formulas_schema(
                "Key defining equations, each with a short label; the entry tagged role='objective' "
                "is the optimization objective/loss; omit the field when the contribution states no equations"
            ),
            "implementation_notes": string_schema("Key implementation details; empty string when none are reported"),
        },
        "Component": {
            **base_unit_properties("Component"),
            "name": string_schema("Name of the component (a sub-method/module that is part_of the contribution)"),
            "method_kind": enum_schema(
                "method_kind",
                "Optional finer structural classification of the component "
                "(algorithm/model_architecture/training_strategy/objective_function); omit when unclear",
            ),
            "description": string_schema("Prose description of the component; empty string when unknown"),
            "inputs": string_array_schema("Inputs to the component; omit when the paper does not state them"),
            "outputs": string_array_schema("Outputs of the component; omit when the paper does not state them"),
            "formulas": formulas_schema(
                "Key defining equations of the component, each with a short label; the entry tagged "
                "role='objective' is the optimization objective/loss; omit the field when the component states no equations"
            ),
            "implementation_notes": string_schema("Key implementation details; empty string when none are reported"),
        },
        "Measure": {
            **base_unit_properties("Measure"),
            "name": string_schema("Name of the measure/metric"),
            "unit": string_schema("Non-empty measurement unit such as %, ms, BLEU, F1, perplexity, or unitless"),
            "setup_ids": measure_setup_ids_schema(),
            "comparison_direction": enum_schema("comparison_direction", "Whether higher or lower values are preferred; omit when unspecified"),
            "objective_class": enum_schema("measure_objective_class", "Optional (FG-6): which axis of a multi-objective evaluation this measure sits on — primary_quality (the headline quality metric, the default — omit), cost_efficiency (latency/compute/memory/params), fairness, safety, or robustness. Set it on the non-primary axes of a trade-off so a cost/fairness/safety measure is not read as uniformly positive evidence."),
            "scores": scores_schema("Flat array of reported scores under this measure — one row per system. In blob-primary mode this carries ONLY the contribution method's own rows (table_role main_result), or is empty (table_role ablation); compared-against baselines stay in the source table, not here. Exception — prose mode (the paper has no table grids, so there is no table blob backstop): transcribe ALL reported comparison rows, the contribution's AND every compared-against baseline's. Second exception — a resource root: the headline evaluated-system rows ON the resource are the paper's own result (setup_id = the resource, system_id = the evaluated Method when censused); when rows grade the resource by object/category rather than by system, the headline column's rows (printed row label as variant). Third exception — a censused metric reported only in figures/prose in a paper that HAS tables: transcribe its prose- or caption-stated numbers here with no source_table_marker (never values read off a figure's axes)."),
            # Blob-primary evidence (section-ir-0.12): the measure binds to its source table by
            # marker; code slices the table verbatim so the model never retypes baseline rows.
            "source_table_marker": string_schema(
                "Optional (blob-primary): the [§N] block id of the <table> this measure reads "
                "(e.g. '§53'). Code slices that table verbatim — you never retype it. Omit for "
                "a prose-derived measure."
            ),
            "caption_marker": string_schema(
                "Optional (blob-primary): the [§N] block id of the table's caption (e.g. '§52'). "
                "Code slices the caption verbatim. Omit when there is no caption block."
            ),
            "table_role": enum_schema(
                "measure_table_role",
                "Optional (blob-primary): main_result (a headline comparison — emit the "
                "contribution method's own score rows) or ablation (component/sensitivity study, "
                "or a motivation/diagnostic study whose cells are Δ/gain/correlation quantities "
                "of prior or base models (for a resource root, evaluated-system "
                "rows ON the resource count as contribution rows) — emit no score rows; the "
                "source table carries it). Defaults to main_result.",
            ),
            "headline_result": string_schema(
                "Optional (blob-primary): the contribution method's key one-liner from this "
                "table (e.g. 'Ours reaches 29.1 BLEU on WMT14 EN-DE, +2.1 over the prior best'). "
                "Emit it on every main_result Measure — each table's own key contribution "
                "one-liner; on an ablation Measure only when the contribution's headline number "
                "lives in that table."
            ),
            "finding_ids": id_array_schema(
                "Optional (blob-primary): ids of the Findings this table evidences (mounted "
                "directly, replacing the Finding<->Measure edges). Each must be a Finding born "
                "or materialized (i.e. defined) in this same response."
            ),
        },
    }
    return schemas


def array_schema(array_key: str, unit_schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    type_name = ARRAY_TYPE_NAMES[array_key]
    properties = unit_schemas[type_name]
    optional_fields = OPTIONAL_FIELDS_BY_TYPE.get(type_name, set())
    return {
        "type": "array",
        "description": f"{type_name} units extracted for this section",
        "items": {
            "type": "object",
            "required": [key for key in properties if key not in optional_fields],
            "additionalProperties": False,
            "properties": properties,
        },
    }


def relations_schema(section_type: str) -> dict[str, Any]:
    """The edges a content section authors, scoped to that section's stage-C relations."""
    allowed = STAGE_C_RELATIONS_BY_SECTION[section_type]
    relation_desc = "; ".join(STAGE_C_RELATION_GLOSS[rel] for rel in allowed) + "."
    return {
        "type": "array",
        "description": (
            f"Edges this {section_type} section authors. Lifted into the global "
            "relations[] during assembly. Empty array when none apply."
        ),
        "items": {
            "type": "object",
            "required": ["source_id", "relation", "target_id", "provenance"],
            "additionalProperties": False,
            "properties": {
                "source_id": id_schema("Source unit ID"),
                "relation": {
                    "type": "string",
                    "enum": allowed,
                    "description": relation_desc,
                },
                "target_id": id_schema("Target unit ID"),
                "provenance": provenance_schema(),
            },
        },
    }


def section_schema(section_type: str, array_keys: list[str]) -> dict[str, Any]:
    unit_schemas = typed_unit_schemas(section_type)
    section_properties: dict[str, Any] = {
        "section_type": {
            "type": "string",
            "enum": [section_type],
        },
        "anchor_id": {
            "type": "string",
            "pattern": ID_PATTERN,
            "description": "ID of the unit that anchors this section; it must be defined in one typed unit array",
        },
    }
    for array_key in array_keys:
        section_properties[array_key] = array_schema(array_key, unit_schemas)

    required = ["section_type", "anchor_id", *array_keys]
    authors_relations = section_type in SECTION_AUTHORS_RELATIONS
    if authors_relations:
        section_properties["relations"] = relations_schema(section_type)
        required.append("relations")

    type_names = [ARRAY_TYPE_NAMES[array_key] for array_key in array_keys]
    return {
        "type": "object",
        "title": f"{section_type.title()} Section Output",
        "description": (
            f"Structured output schema for the {section_type} section content extraction. "
            f"Typed unit arrays: {', '.join(array_keys)}. "
            f"Valid unit types: {', '.join(type_names)}."
            + (" Authors relations." if authors_relations else "")
        ),
        "required": ["section"],
        "additionalProperties": False,
        "properties": {
            "section": {
                "type": "object",
                "required": required,
                "additionalProperties": False,
                "properties": section_properties,
            }
        },
    }


def node_census_schema() -> dict[str, Any]:
    """Stage A schema: spine_summary + a flat list of referenceable nodes."""
    return {
        "type": "object",
        "title": "Node Census Output",
        "description": (
            f"Stage A of {IR_VERSION}: a flat census of every argumentatively load-bearing "
            "node, each tagged with its type (plus a kind on Contribution/ExperimentSetup), with "
            "no relations. The census emits Contribution nodes (the root deliverable(s)), Component "
            "nodes (sub-modules), the substrate ExperimentSetup nodes (dataset/benchmark/task), "
            "Measure nodes, and the single research-problem Problem node (RF-08). Findings are born "
            "during content fill; configuration ExperimentSetup units (splits/protocols) too."
        ),
        "required": ["spine_summary", "nodes"],
        "additionalProperties": False,
        "properties": {
            "spine_summary": {
                "type": "object",
                "required": ["central_contribution", "argument_flow"],
                "additionalProperties": False,
                "description": "Summary of the paper's contribution and argument structure",
                "properties": {
                    "research_problem": string_schema(
                        "Optional orientation annotation (RF-08): one sentence stating the central "
                        "unmet need or unresolved question the paper addresses. A summary annotation, "
                        "NOT a node — the single research-problem Problem node remains the structured "
                        "graph unit; do NOT drop that node because this field is filled."
                    ),
                    "central_contribution": string_schema("One sentence naming the main contribution."),
                    "argument_flow": string_schema(
                        "One sentence describing how problem, method, and evidence fit together."
                    ),
                    "headline_result": string_schema(
                        "Optional (FG-9): one sentence stating the paper's headline established RESULT — the "
                        "answer the evidence demonstrates — as distinct from central_contribution (which names "
                        "the artifact/contribution). State the finding itself: 'value learning is not the main "
                        "bottleneck in offline RL', 'the model matches SOTA with 10x fewer parameters'. Fill it "
                        "whenever the paper establishes a clear headline result (for an analysis/'is X the "
                        "bottleneck?' paper this IS the payload); omit when the paper states no clear headline "
                        "result (typically only a pure resource/tool release). This stays a summary annotation — "
                        "do NOT add a Finding node for it."
                    ),
                    "topics": string_array_schema(
                        "Optional (RF-07): 3-6 lowercase free-keyword topic tags for corpus routing "
                        "(e.g. 'semantic segmentation', 'weak supervision', 'vision transformers'). "
                        "Specific enough to differentiate papers within one field; not section names."
                    ),
                    "tasks": string_array_schema(
                        "Optional (RF-07): the concrete task(s) the paper addresses or evaluates on, "
                        "as the community names them (e.g. 'semantic segmentation', 'machine "
                        "translation', 'offline reinforcement learning')."
                    ),
                    "domain": string_schema(
                        "Optional (RF-07): ONE coarse research domain, lowercase (e.g. 'computer "
                        "vision', 'natural language processing', 'reinforcement learning', 'machine "
                        "learning theory')."
                    ),
                },
            },
            "nodes": {
                "type": "array",
                "description": "Flat list of referenceable nodes; node_id is reused verbatim as the final unit id.",
                "items": {
                    "type": "object",
                    "required": ["node_id", "type", "name", "gloss", "source_scope", "cite_keys"],
                    "additionalProperties": False,
                    "properties": {
                        "node_id": id_schema(
                            "Node id; the prefix follows from the type — con: for Contribution, "
                            "cmp: for Component, exp: for ExperimentSetup, mea: for Measure, "
                            "prb: for Problem. Lowercase ASCII/digits/underscores, with acronyms "
                            "lowercased (map, not mAP); reused verbatim as the final unit id, so "
                            "choose it once and never reuse it."
                        ),
                        "type": enum_schema(
                            "census_type",
                            "Node type, in search-cluster order. the_solution: Contribution (the "
                            "paper's root deliverable) or Component (a sub-module that is part_of the "
                            "contribution). evaluation_frame: ExperimentSetup (a dataset/benchmark/"
                            "task the work runs on) or Measure (a metric). the_problem: Problem (the "
                            "single research problem). Prior-art methods the paper builds on or "
                            "compares against are NOT census nodes — the citation layer captures "
                            "them; Findings are born during content fill.",
                        ),
                        "kind": enum_schema(
                            "census_kind",
                            "REQUIRED on a Contribution (method/dataset/benchmark/finding — "
                            "what the deliverable IS) and on an ExperimentSetup (dataset/benchmark/"
                            "task). OMIT on Component, Measure, and Problem (they are single-level).",
                        ),
                        "name": string_schema("Short name of the node as the paper refers to it"),
                        "gloss": string_schema("One short phrase stating what the node intrinsically IS — not how it relates to any other node (no 'used by', 'part of', 'improves', 'evaluated on'); relations are the next pass's job."),
                        "source_scope": string_array_schema("Section markers — the paper's own printed heading number(s) where the node is introduced or defined, e.g. ['§3']; echo them from the text, never fabricate a number the paper does not print."),
                        "cite_keys": string_array_schema(
                            "In-text bibliography citation marker(s) attached to this node, as "
                            "bare keys matching the reference list ('8', not '[8]'; 'vaswani2017' "
                            "for author-year). Fill for cited evaluation-frame nodes (dataset/benchmark) "
                            "drawn from cited data, e.g. 'evaluated on ImageNet [8]' -> ['8']. "
                            "Empty [] for any Contribution/Component (your own work), for "
                            "task/metric/problem nodes, and when no citation is attached."
                        ),
                    },
                },
            },
        },
    }


def relation_pass_schema() -> dict[str, Any]:
    """Stage B schema: structural node<->node edges over the full node set."""
    return {
        "type": "object",
        "title": "Relation Pass Output",
        "description": (
            f"Stage B of {IR_VERSION}: structural edges over the full node set. Sees every "
            "node, so cross-section composition and measure-subject binding are captured here "
            "with no forward references."
        ),
        "required": ["relations"],
        "additionalProperties": False,
        "properties": {
            "relations": {
                "type": "array",
                "description": "Structural node<->node edges between census nodes.",
                "items": {
                    "type": "object",
                    "required": ["source_id", "relation", "target_id", "provenance"],
                    "additionalProperties": False,
                    "properties": {
                        "source_id": id_schema("Source node id"),
                        "relation": {
                            "type": "string",
                            "enum": STAGE_B_RELATION_ORDER,
                            "description": (
                                "One of the six structural relation types — semantics and "
                                "direction rules are defined in the system prompt."
                            ),
                        },
                        "target_id": id_schema("Target node id"),
                        "provenance": provenance_schema("edge"),
                    },
                },
            },
        },
    }


def main() -> None:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for section_type, array_keys in SECTION_TYPED_ARRAYS.items():
        path = SCHEMAS_DIR / f"section-{section_type}.schema.json"
        payload = section_schema(section_type, array_keys)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(path.relative_to(PROJECT_ROOT))

    for filename, builder in (
        ("node-census-output.schema.json", node_census_schema),
        ("relation-pass-output.schema.json", relation_pass_schema),
    ):
        path = SCHEMAS_DIR / filename
        path.write_text(json.dumps(builder(), indent=2) + "\n", encoding="utf-8")
        print(path.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
