#!/usr/bin/env python3
"""Generate per-section typed-array schemas plus the node-census and relation-pass schemas.

section-ir-0.9: the pipeline is three stages — node census (stage A), relation pass
(stage B), and per-section content fill (stage C). This script is the single source for
every structured-output schema, generated from the controlled vocabularies in
``section_pipeline.py`` so the schemas never drift from the runtime contract.

Each unit carries two classificatory axes: a generic ``type`` (the scientific-method-anchored
scope) and a fine-grained ``role`` (the discipline-specific differentia). Problem and Measure
have no sub-axis and carry no ``role``.
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
    EXPERIMENT_SETUP_ROLES,
    FINDING_POLARITIES,
    FINDING_ROLES,
    MEASURE_OBJECTIVE_CLASSES,
    METHOD_KINDS,
    METHOD_ROLES,
    NODE_ROLES,
    SCORE_VALUE_KINDS,
    SECTION_AUTHORS_RELATIONS,
)

SCHEMAS_DIR = PROJECT_ROOT / "schemas"
ID_PATTERN = r"^[a-z][a-z0-9_]*:[a-z0-9_]+$"

# Typed unit arrays each content section (stage C) returns.
SECTION_TYPED_ARRAYS: dict[str, list[str]] = {
    "problem": ["problems"],
    "method": ["methods"],
    "evidence": ["measures", "experiment_setups", "findings"],
}

# Fields that are optional on a unit type (everything else in its property set is required).
# method_kind is now an optional descriptive attribute (the role is the required differentia);
# ExperimentSetup carries an optional description and cite_keys.
# `implementation_notes` is optional (0.10, FG-2): a non-implementation Method — a theorem/lemma/
# bound/definition or a resource/taxonomy deliverable — carries no reproducibility notes, so it is
# not forced to emit the field. Normal algorithmic methods still fill it (method.md asks for it);
# making it schema-optional is additive (every existing 0.9 output already carries it).
OPTIONAL_FIELDS_BY_TYPE: dict[str, set[str]] = {
    "Measure": {"comparison_direction", "objective_class"},
    "Method": {"method_kind", "inputs", "outputs", "formulas", "objective_function",
               "implementation_notes"},
    "ExperimentSetup": {"description"},
    # FG-11 (section-ir-0.10): optional Finding quantitative payload.
    "Finding": {"polarity", "effect_size", "scope"},
}

ARRAY_TYPE_NAMES: dict[str, str] = {
    "problems": "Problem",
    "methods": "Method",
    "experiment_setups": "ExperimentSetup",
    "measures": "Measure",
    "findings": "Finding",
}

# Census node roles and the unit-level role vocabularies, with explicit ordering for stable
# schemas. Census roles are listed in search-cluster order (the_method, prior_art, testbed,
# yardsticks). The substrate roles (dataset/benchmark/task) are the only ExperimentSetup roles
# the census emits; the configuration roles are born during content fill.
NODE_ROLE_ORDER = [
    "contribution", "contribution_resource", "component",
    "builds_on", "compared_against",
    "dataset", "benchmark", "task", "theoretical_setting", "structural_class",
    "metric",
]
METHOD_ROLE_ORDER = ["contribution", "component", "builds_on", "compared_against"]
EXPERIMENT_SETUP_ROLE_ORDER = [
    "dataset", "benchmark", "task", "theoretical_setting", "structural_class",
    "contribution_resource",
    "data_split", "inference_protocol", "training_config", "ensembling", "population",
]
FINDING_ROLE_ORDER = [
    "descriptive", "mechanistic", "comparative", "modeling", "ablation_finding", "failure_mode",
    "theorem", "lemma", "bound",
]
SALIENCE_ORDER = ["must", "should"]
STAGE_B_RELATION_ORDER = ["part_of", "builds_on", "uses", "assumes", "co_contribution",
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
    "about": "about = a Finding is about a Method/ExperimentSetup/Measure",
    "supports": "supports = a Measure, Finding, or Method (a theorem/proof) supports a Finding",
    "motivates": "motivates = a Problem motivates the Method/ExperimentSetup that addresses it",
}

ENUM_ORDER: dict[str, list[str]] = {
    "node_role": NODE_ROLE_ORDER,
    "method_role": METHOD_ROLE_ORDER,
    "experiment_setup_role": EXPERIMENT_SETUP_ROLE_ORDER,
    "finding_role": FINDING_ROLE_ORDER,
    "method_kind": ["algorithm", "model_architecture", "training_strategy", "objective_function",
                    "resource", "taxonomy", "theorem", "lemma", "bound", "definition"],
    "comparison_direction": ["higher_is_better", "lower_is_better", "target", "unspecified"],
    "finding_polarity": ["positive", "negative", "neutral", "mixed"],
    "score_value_kind": ["numeric", "symbolic", "asymptotic", "qualitative", "curve"],
    "measure_objective_class": ["primary_quality", "cost_efficiency", "fairness", "safety", "robustness"],
}

ENUM_VALUES: dict[str, set[str]] = {
    "node_role": NODE_ROLES,
    "method_role": METHOD_ROLES,
    "experiment_setup_role": EXPERIMENT_SETUP_ROLES,
    "finding_role": FINDING_ROLES,
    "method_kind": METHOD_KINDS,
    "comparison_direction": COMPARISON_DIRECTIONS,
    "finding_polarity": FINDING_POLARITIES,
    "score_value_kind": SCORE_VALUE_KINDS,
    "measure_objective_class": MEASURE_OBJECTIVE_CLASSES,
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


def inline_enum_schema(values: list[str], description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "enum": values,
        "description": description,
    }


def string_array_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string"},
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
                "variant": {"type": "string", "description": "System name for this score row as the paper labels it — a method-family variant/configuration or a compared-against baseline (e.g. 'Transformer (big)', 'GNMT')"},
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
                    "description": "ID of the Method unit this row reports — the contribution variant or the compared-against baseline (e.g. 'mth:transformer', 'mth:gnmt'). Empty string when no node represents this row's system (e.g. an ensemble-of-baselines the census did not capture).",
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
                    "description": "Optional (FG-6): for a pairwise/win-rate row (A-vs-B), the id of the Method this row's system was compared against — `system_id` is system A, `opponent_id` is system B, `value` is A's win rate vs B. Omit for an ordinary absolute-score row.",
                },
                "judge_id": {
                    "type": "string",
                    "description": "Optional (FG-6): for a judged row (LLM-as-judge or human evaluation), the id of the judge — a Method, or an inference_protocol/population ExperimentSetup that was materialized for the evaluator. Omit when the score needs no judge.",
                },
            },
        },
        "description": description,
    }


def symbols_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "description": (
            "Definitions of the symbols and variables appearing in the expression; "
            "empty array when the expression introduces none"
        ),
        "items": {
            "type": "object",
            "required": ["symbol", "description"],
            "additionalProperties": False,
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "A symbol or variable from the expression, e.g. 'Q', 'd_k', 'W^O'",
                },
                "description": {
                    "type": "string",
                    "description": "What the symbol denotes, e.g. 'query matrix', 'dimension of the keys'",
                },
            },
        },
    }


def formulas_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["name", "expression", "symbols"],
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
                "symbols": symbols_schema(),
            },
        },
        "description": description,
    }


def objective_function_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["expression", "description", "symbols"],
        "additionalProperties": False,
        "properties": {
            "expression": {
                "type": "string",
                "description": "The objective or loss as LaTeX or plain text, e.g. 'L = -sum log P(y|x)'",
            },
            "description": {
                "type": "string",
                "description": "What the objective optimizes; empty string when only the formula is reported",
            },
            "symbols": symbols_schema(),
        },
        "description": description,
    }


def provenance_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "description": "Location markers for this unit: top-level section anchors such as ['\\u00a71', '\\u00a72']",
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
            "role": enum_schema(
                "experiment_setup_role",
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
            "role": enum_schema("finding_role", "Classification of the finding"),
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
        "Method": {
            **base_unit_properties("Method"),
            "role": enum_schema(
                "method_role",
                "Argumentative role: contribution (the single primary method/system), component "
                "(a sub-method that is part_of the contribution), builds_on (prior work extended), "
                "or compared_against (a baseline)",
            ),
            "name": string_schema("Name of the method"),
            "method_kind": enum_schema(
                "method_kind",
                "Optional structural classification of the method; omit when unclear",
            ),
            "description": string_schema("Prose description of the method; empty string when unknown"),
            "inputs": string_array_schema("Inputs to the method; omit when the paper does not state them"),
            "outputs": string_array_schema("Outputs of the method; omit when the paper does not state them"),
            "formulas": formulas_schema(
                "Key defining equations of the method, each with a short label; omit when the method states none"
            ),
            "objective_function": objective_function_schema(
                "The optimization objective or loss the method minimizes/maximizes; omit when the method defines none"
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
            "scores": scores_schema("Flat array of reported scores under this measure — one row per system, covering the method family's own variants and every compared-against baseline"),
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
            "Stage A of section-ir-0.9: a flat census of every argumentatively load-bearing "
            "node, each tagged with one granular role (its type is derived from the role), with "
            "no relations. The census emits Method nodes, the substrate ExperimentSetup nodes "
            "(dataset/benchmark/task), and Measure nodes. Problem and Finding are not nodes, and "
            "configuration ExperimentSetup units (splits/protocols) are born during content fill."
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
                        "bottleneck?' paper this IS the payload); omit only for a pure resource/tool release with "
                        "no empirical result. This stays a summary annotation — do NOT add a Finding node for it."
                    ),
                },
            },
            "nodes": {
                "type": "array",
                "description": "Flat list of referenceable nodes; node_id is reused verbatim as the final unit id.",
                "items": {
                    "type": "object",
                    "required": ["node_id", "role", "name", "gloss", "source_scope", "cite_keys", "salience"],
                    "additionalProperties": False,
                    "properties": {
                        "node_id": id_schema(
                            "Node id; the prefix follows from the role's type — mth: for "
                            "contribution/component/builds_on/compared_against, exp: for "
                            "dataset/benchmark/task, mea: for metric"
                        ),
                        "role": enum_schema(
                            "node_role",
                            "Argumentative role, in search-cluster order. the_method: "
                            "contribution (the single primary method) and component. prior_art: "
                            "builds_on and compared_against. testbed: dataset, benchmark, task. "
                            "yardsticks: metric.",
                        ),
                        "name": string_schema("Short name of the node as the paper refers to it"),
                        "gloss": string_schema("One short phrase describing the node"),
                        "source_scope": string_array_schema("Section markers where the node appears, e.g. ['§3']"),
                        "cite_keys": string_array_schema(
                            "In-text bibliography citation marker(s) attached to this node, as "
                            "bare keys matching the reference list ('8', not '[8]'; 'vaswani2017' "
                            "for author-year). Fill for builds_on/compared_against/dataset/benchmark "
                            "nodes (drawn from cited prior work or data), e.g. 'we compare against "
                            "ConvS2S [8]' -> ['8']. Empty [] for the contribution and its components "
                            "(your own work), for task/metric nodes, and when no citation is attached."
                        ),
                        "salience": inline_enum_schema(
                            SALIENCE_ORDER,
                            "must = load-bearing for the contribution; should = adds nuance",
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
            "Stage B of section-ir-0.9: structural edges over the full node set. Sees every "
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
                                "part_of = internal composition between Methods/ExperimentSetups; "
                                "builds_on = the contribution extends external prior work it derives from; "
                                "uses = the contribution depends on an external method/dataset as a tool; "
                                "assumes = a theorem/result Method holds under a theoretical_setting/structural_class ExperimentSetup; "
                                "co_contribution = two co-equal contributions of one paper (emit once, not fake part_of); "
                                "compares_to = contrasted peers; "
                                "evaluates = a Measure measures a Method."
                            ),
                        },
                        "target_id": id_schema("Target node id"),
                        "provenance": provenance_schema(),
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
