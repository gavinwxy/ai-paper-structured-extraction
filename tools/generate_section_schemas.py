#!/usr/bin/env python3
"""Generate per-section typed-array schemas plus the node-census and relation-pass schemas.

section-ir-0.7: the pipeline is three stages — node census (stage A), relation pass
(stage B), and per-section content fill (stage C). This script is the single source for
every structured-output schema, generated from the controlled vocabularies in
``section_pipeline.py`` so the schemas never drift from the runtime contract.
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
    CLAIM_KINDS,
    COMPARISON_DIRECTIONS,
    CONTEXT_KINDS,
    ENTITY_CLASSES,
    METHOD_KINDS,
    NODE_ROLES,
    SECTION_AUTHORS_RELATIONS,
    SETTING_KINDS,
)

SCHEMAS_DIR = PROJECT_ROOT / "schemas"
ID_PATTERN = r"^[a-z][a-z0-9_]*:[a-z0-9_]+$"

# Typed unit arrays each content section (stage C) returns.
SECTION_TYPED_ARRAYS: dict[str, list[str]] = {
    "context": ["contexts"],
    "claim": ["claims"],
    "method": ["methods"],
    "evidence": ["metrics", "settings", "claims", "entities"],
}

# Entity classes allowed per section. Evidence may carry any class an entity node can take.
ENTITY_CLASSES_BY_SECTION: dict[str, list[str]] = {
    "evidence": ["dataset", "benchmark", "task"],
}

OPTIONAL_FIELDS_BY_TYPE: dict[str, set[str]] = {
    "Metric": {"comparison_direction"},
    "Method": {"inputs", "outputs", "formulas", "objective_function"},
}

ARRAY_TYPE_NAMES: dict[str, str] = {
    "entities": "Entity",
    "contexts": "Context",
    "settings": "Setting",
    "claims": "Claim",
    "metrics": "Metric",
    "methods": "Method",
}

# Census node roles and the relation vocabularies, with explicit ordering for stable schemas.
# Roles are listed in search-cluster order (the_method, prior_art, testbed, yardsticks).
ROLE_ORDER = [
    "contribution", "component",
    "builds_on", "compared_against",
    "dataset", "benchmark", "task",
    "metric",
]
SALIENCE_ORDER = ["must", "should"]
STAGE_B_RELATION_ORDER = ["part_of", "compares_to", "evaluates", "measured_on"]
# Stage-C edges each content section authors, ordered as they appear in its schema enum.
# context authors only `motivates` (Context -> the census Method/Entity it justifies);
# claim/evidence author the claim-centric `about`/`supports`. Scoping the enum per section
# keeps each section's contract tight — it matters most for json_object models (DeepSeek),
# whose only constraint is the in-prompt contract, not strict decoding.
STAGE_C_RELATIONS_BY_SECTION: dict[str, list[str]] = {
    "context": ["motivates"],
    "claim": ["about", "supports"],
    "evidence": ["about", "supports"],
}
# One-line gloss per stage-C relation, joined into the schema field description.
STAGE_C_RELATION_GLOSS: dict[str, str] = {
    "about": "about = a Claim is about a Method/Entity/Metric",
    "supports": "supports = a Metric or Claim supports a Claim",
    "motivates": "motivates = a Context premise motivates the Method/Entity it justifies",
}

ENUM_ORDER: dict[str, list[str]] = {
    "role": ROLE_ORDER,
    "claim_kind": ["descriptive", "mechanistic", "comparative", "modeling", "ablation_finding", "failure_mode"],
    "context_kind": ["background", "gap", "motivation", "challenge", "assumption"],
    "entity_class": ["dataset", "benchmark", "task"],
    "method_kind": ["algorithm", "model_architecture", "training_strategy", "objective_function"],
    "comparison_direction": ["higher_is_better", "lower_is_better", "target", "unspecified"],
    "setting_kind": ["data_split", "inference_protocol", "training_config", "ensembling", "population"],
}

ENUM_VALUES: dict[str, set[str]] = {
    "role": NODE_ROLES,
    "claim_kind": CLAIM_KINDS,
    "context_kind": CONTEXT_KINDS,
    "entity_class": ENTITY_CLASSES,
    "method_kind": METHOD_KINDS,
    "comparison_direction": COMPARISON_DIRECTIONS,
    "setting_kind": SETTING_KINDS,
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


def metric_setting_ids_schema() -> dict[str, Any]:
    """`setting_ids` scopes a metric to local Setting units in the evidence section.

    In 0.7 this is optional in cardinality: a deployable metric may carry scoping
    Settings while an ablation metric may carry none, so no min/max bound is imposed.
    The metric->method (`evaluates`) and metric->dataset (`measured_on`) edges that used
    to live on the Metric are global relations now.
    """
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": "IDs of local Setting units scoping this metric; empty when none apply",
    }


def scores_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["variant", "value", "variance", "system_id", "setting_id"],
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
                "setting_id": {
                    "type": "string",
                    "description": "ID of the local Setting unit this row was measured under (the dataset split / language pair / protocol), when one Metric spans several. Empty string when the metric's own setting_ids already scope every row.",
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
    entity_classes = ENTITY_CLASSES_BY_SECTION.get(section_type, ordered_enum("entity_class"))
    schemas: dict[str, dict[str, Any]] = {
        "Entity": {
            **base_unit_properties("Entity"),
            "name": string_schema("Name of the entity"),
            "entity_class": inline_enum_schema(entity_classes, "Classification of the entity"),
        },
        "Context": {
            **base_unit_properties("Context"),
            "context_kind": enum_schema("context_kind", "Argumentative role of the context premise"),
            "description": string_schema("Single-sentence prose statement of the premise"),
        },
        "Setting": {
            **base_unit_properties("Setting"),
            "setting_kind": enum_schema(
                "setting_kind",
                "Which axis of the evaluation this setup constrains: data_split, "
                "inference_protocol, training_config, ensembling, or population",
            ),
            "description": string_schema(
                "Single-sentence prose statement of the operational constraint that scopes a "
                "metric — the concrete dataset split, protocol, population, or hyperparameter"
            ),
        },
        "Claim": {
            **base_unit_properties("Claim"),
            "statement": string_schema("The claim as a single declarative sentence"),
            "claim_kind": enum_schema("claim_kind", "Classification of the claim"),
        },
        "Method": {
            **base_unit_properties("Method"),
            "name": string_schema("Name of the method"),
            "method_kind": enum_schema("method_kind", "Classification of the method"),
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
        "Metric": {
            **base_unit_properties("Metric"),
            "name": string_schema("Name of the metric"),
            "unit": string_schema("Non-empty measurement unit such as %, ms, BLEU, F1, perplexity, or unitless"),
            "setting_ids": metric_setting_ids_schema(),
            "comparison_direction": enum_schema("comparison_direction", "Whether higher or lower values are preferred; omit when unspecified"),
            "scores": scores_schema("Flat array of reported scores under this metric — one row per system, covering the method family's own variants and every compared-against baseline"),
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
            "Stage A of section-ir-0.7: a flat census of every argumentatively load-bearing "
            "node, each tagged with one granular role (its type and Entity class are derived "
            "from the role), with no relations. Context, Setting, and Claim are not nodes; "
            "they are born during content extraction."
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
                        "One sentence describing how context, claim, method, and evidence fit together."
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
                            "contribution/component/builds_on/compared_against, ent: for "
                            "dataset/benchmark/task, met: for metric"
                        ),
                        "role": enum_schema(
                            "role",
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
    """Stage B schema: structural entity<->entity edges over the full node set."""
    return {
        "type": "object",
        "title": "Relation Pass Output",
        "description": (
            "Stage B of section-ir-0.7: structural edges over the full node set. Sees every "
            "node, so cross-section composition and metric-subject binding are captured here "
            "with no forward references."
        ),
        "required": ["relations"],
        "additionalProperties": False,
        "properties": {
            "relations": {
                "type": "array",
                "description": "Structural entity<->entity edges between census nodes.",
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
                                "part_of = composition between Methods/Entities; "
                                "compares_to = contrasted peers; "
                                "evaluates = Metric measures a Method; "
                                "measured_on = Metric measured on a dataset/benchmark Entity."
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
