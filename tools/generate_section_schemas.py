#!/usr/bin/env python3
"""Generate per-section typed-array schemas."""

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
    CONDITION_KINDS,
    CONTEXT_KINDS,
    ENTITY_CLASSES,
    EPISTEMIC_STATUSES,
    LINK_MATRIX,
    METHOD_KINDS,
    NOVELTIES,
    POLARITIES,
    SOURCE_KINDS,
    VALUE_TYPES,
)

SCHEMAS_DIR = PROJECT_ROOT / "schemas"
ID_PATTERN = r"^[a-z][a-z0-9_]*:[a-z0-9_]+$"

SECTION_TYPED_ARRAYS: dict[str, list[str]] = {
    "context": ["contexts"],
    "claim": ["claims"],
    "method": ["methods"],
    "experiment": ["metrics", "conditions", "entities"],
    "analysis": ["claims", "metrics", "entities"],
}

ENTITY_CLASSES_BY_SECTION: dict[str, list[str]] = {
    "experiment": ["dataset", "benchmark"],
    "analysis": ["dataset", "benchmark", "model", "task", "hardware"],
}

OPTIONAL_FIELDS_BY_TYPE: dict[str, set[str]] = {
    "Claim": {"polarity", "novelty", "epistemic_status"},
    "Metric": {"comparison_direction", "value_type", "evaluated_on"},
    "Method": {"inputs", "outputs", "formulas", "objective_function"},
}

ARRAY_TYPE_NAMES: dict[str, str] = {
    "entities": "Entity",
    "contexts": "Context",
    "conditions": "Condition",
    "claims": "Claim",
    "metrics": "Metric",
    "methods": "Method",
}

ENUM_ORDER: dict[str, list[str]] = {
    "claim_kind": ["descriptive", "mechanistic", "causal", "correlational", "comparative", "modeling", "ablation_finding", "failure_mode"],
    "context_kind": ["background", "gap", "motivation", "challenge", "assumption"],
    "condition_kind": ["experimental", "boundary", "evaluation_setup", "hyperparameter"],
    "entity_class": ["dataset", "benchmark", "model", "task", "hardware"],
    "method_kind": ["algorithm", "model_architecture", "protocol", "software_system", "training_strategy", "objective_function"],
    "source_kind": ["sentence", "table", "figure", "appendix", "caption", "equation", "supplementary_material"],
    "comparison_direction": ["higher_is_better", "lower_is_better", "target", "unspecified"],
    "value_type": ["scalar", "range", "ratio", "categorical"],
    "polarity": ["positive", "negative", "neutral", "mixed"],
    "novelty": ["original", "replication", "citation", "synthesis"],
    "epistemic_status": ["hypothesis", "conclusion", "established_fact"],
}

ENUM_VALUES: dict[str, set[str]] = {
    "claim_kind": CLAIM_KINDS,
    "context_kind": CONTEXT_KINDS,
    "condition_kind": CONDITION_KINDS,
    "entity_class": ENTITY_CLASSES,
    "method_kind": METHOD_KINDS,
    "source_kind": SOURCE_KINDS,
    "comparison_direction": COMPARISON_DIRECTIONS,
    "value_type": VALUE_TYPES,
    "polarity": POLARITIES,
    "novelty": NOVELTIES,
    "epistemic_status": EPISTEMIC_STATUSES,
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


def metric_context_ids_schema(section_type: str) -> dict[str, Any]:
    """Section-aware `context_ids` constraint for Metric.

    The same field flips polarity by section: experiment metrics must be scoped
    by at least one local Condition, while analysis metrics have no local
    Conditions and must leave it empty. Encoding these bounds in the schema lets
    the structured-output backend enforce the rule directly instead of relying on
    the model to remember a per-section reversal (see issues P0-3).
    """
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if section_type == "experiment":
        schema["minItems"] = 1
        schema["description"] = (
            "IDs of local Condition units scoping this metric; "
            "experiment metrics require at least one local Condition."
        )
    elif section_type == "analysis":
        schema["maxItems"] = 0
        schema["description"] = (
            "Must be an empty array: analysis sections have no local Conditions, "
            "so analysis metrics carry no context_ids."
        )
    else:
        schema["description"] = "IDs of local Condition units scoping this metric"
    return schema


def scores_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["variant", "value", "variance"],
            "additionalProperties": False,
            "properties": {
                "variant": {"type": "string", "description": "Method variant or configuration name"},
                "value": {
                    "type": "string",
                    "description": "Reported score encoded as a string, including numeric values",
                },
                "variance": {
                    "type": "string",
                    "description": "Uncertainty (e.g. '± 0.3'); empty string when unreported",
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
        "description": "Source references for this unit",
        "items": {
            "type": "object",
            "required": ["source_kind", "source"],
            "additionalProperties": False,
            "properties": {
                "source_kind": enum_schema("source_kind", "Source marker kind"),
                "source": string_array_schema("Section markers such as ['\\u00a71', '\\u00a72']"),
            },
        },
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
        "Condition": {
            **base_unit_properties("Condition"),
            "condition_kind": enum_schema("condition_kind", "Operational role of the constraint"),
            "description": string_schema("Single-sentence prose statement of the constraint"),
        },
        "Claim": {
            **base_unit_properties("Claim"),
            "statement": string_schema("The claim as a single declarative sentence"),
            "claim_kind": enum_schema("claim_kind", "Classification of the claim"),
            "target_ids": string_array_schema("IDs of entities or methods the claim is about"),
            "polarity": enum_schema("polarity", "Directional assertion of the claim; omit when unspecified"),
            "novelty": enum_schema("novelty", "Whether the claim is original to this paper; omit when unspecified"),
            "epistemic_status": enum_schema("epistemic_status", "Confidence level of the claim; omit when unspecified"),
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
            "subject_id": string_schema("ID of the unit being measured"),
            "context_ids": metric_context_ids_schema(section_type),
            "evaluated_on": string_array_schema(
                "IDs of local dataset/benchmark Entity units this metric was measured on; "
                "omit entirely when no such local Entity exists"
            ),
            "comparison_direction": enum_schema("comparison_direction", "Whether higher or lower values are preferred; omit when unspecified"),
            "value_type": enum_schema("value_type", "Shape of the metric value; omit when unspecified"),
            "scores": scores_schema("Flat array of reported scores for method-family variants under this metric"),
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


LINK_RELATION_HINTS: dict[str, str] = {
    "context": "supports",
    "claim": "supports",
    "method": "part_of, compares_to",
    "experiment": "compares_to",
    "analysis": "supports, compares_to",
}


def links_schema(section_type: str) -> dict[str, Any]:
    return {
        "type": "array",
        "description": "Section-local links between units",
        "items": {
            "type": "object",
            "required": ["source_id", "relation", "target_id"],
            "additionalProperties": False,
            "properties": {
                "source_id": id_schema("Source unit ID"),
                "relation": {
                    "type": "string",
                    "enum": list(LINK_MATRIX),
                    "description": f"Section-local relation. Recommended for {section_type}: {LINK_RELATION_HINTS[section_type]}.",
                },
                "target_id": id_schema("Target unit ID"),
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
        "covers_entries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Plan item IDs covered by this section",
        },
    }
    for array_key in array_keys:
        section_properties[array_key] = array_schema(array_key, unit_schemas)
    section_properties["links"] = links_schema(section_type)

    type_names = [ARRAY_TYPE_NAMES[array_key] for array_key in array_keys]
    return {
        "type": "object",
        "title": f"{section_type.title()} Section Output",
        "description": (
            f"Structured output schema for the {section_type} section section extraction. "
            f"Typed unit arrays: {', '.join(array_keys)}. "
            f"Valid unit types: {', '.join(type_names)}."
        ),
        "required": ["section"],
        "additionalProperties": False,
        "properties": {
            "section": {
                "type": "object",
                "required": ["section_type", "anchor_id", "covers_entries", *array_keys, "links"],
                "additionalProperties": False,
                "properties": section_properties,
            }
        },
    }


def main() -> None:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for section_type, array_keys in SECTION_TYPED_ARRAYS.items():
        path = SCHEMAS_DIR / f"section-{section_type}.schema.json"
        payload = section_schema(section_type, array_keys)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(path.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
