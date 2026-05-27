#!/usr/bin/env python3
"""Two-stage section extraction pipeline: section planning -> constrained extraction."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
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
# A provenance marker is a top-level §N (numeric body section) or §X (a lettered appendix,
# e.g. §A, §C). Both are legitimate paper locations; lettered appendices are common and were
# previously rejected. Figure/table refs (`§Table 3`, `§Fig. 2`) still fail — they mix
# lowercase/spaces and match neither alternative.
PROVENANCE_SOURCE_RE = re.compile(r"^§(?:\d+|[A-Z]+)$")
# A finer-grained subsection of a numeric body section (§4.3) or a lettered appendix (§C.1,
# §G.2). The input only anchors top-level sections, so these collapse to their §N / §X parent.
SUBSECTION_MARKER_RE = re.compile(r"^§(\d+|[A-Z]+)(?:\.\d+)+$")

SECTION_TYPES = {"problem", "method", "evidence"}
SECTION_ORDER = ["problem", "method", "evidence"]
SECTION_ALLOWED_UNIT_TYPES: dict[str, set[str]] = {
    "problem": {"Problem"},
    "method": {"Method"},
    "evidence": {"Metric", "Setting", "Claim", "Entity"},
}
# The unit type that should naturally anchor each section. Used when repairing an
# anchor that names a non-local unit (e.g. an evidence section reaching for the
# root `mth:` method): prefer re-pointing to a local unit of this type before
# falling back to the first local non-Document unit.
SECTION_PREFERRED_ANCHOR_TYPE: dict[str, str] = {
    "problem": "Problem",
    "method": "Method",
    "evidence": "Metric",
}
# Census node types each content section materializes into full units. Method
# nodes become Method units in the method section; Metric and Entity nodes become
# units in the evidence section. Problem and Claim are not census nodes — they are
# born during content extraction (Problem in the problem section, Claim in evidence).
SECTION_MATERIALIZED_NODE_TYPES: dict[str, set[str]] = {
    "problem": set(),
    "method": {"Method"},
    "evidence": {"Metric", "Entity"},
}
# Content sections that author edges in their own `relations[]`: evidence authors the
# claim-centric `about`/`supports`; problem authors `motivates` (Problem -> the census
# Method/Entity it justifies). The closing `resolves` (Claim -> Problem) is NOT authored
# by any section — it crosses two parallel sections, so it is synthesized in assembly
# (_assign_resolves). Structural edges are authored earlier by the relation pass. The
# exact relation enum per section lives in the schema generator's STAGE_C_RELATIONS_BY_SECTION.
SECTION_AUTHORS_RELATIONS = {"problem", "evidence"}
TYPED_ARRAY_KEYS: dict[str, str] = {
    "entities": "Entity",
    "problems": "Problem",
    "settings": "Setting",
    "claims": "Claim",
    "metrics": "Metric",
    "methods": "Method",
}
# Census node concepts. The census emits a flat list of referenceable nodes; each
# node_id is reused verbatim as the final unit id once a content section materializes it.
NODE_TYPES = {"Method", "Entity", "Metric"}
NODE_ID_PREFIX_BY_TYPE: dict[str, str] = {
    "Method": "mth:",
    "Entity": "ent:",
    "Metric": "met:",
}
SALIENCE_LEVELS = {"must", "should"}
# Census node role — the single granular tag the census emits per node. It is the
# argumentative function the node plays, grouped into four search clusters by the guiding
# principle "trace the method's life": the_method (mine), prior_art (others'), testbed
# (data), yardsticks (metrics). `type`, the Entity class, and the document root are all
# derived from `role` (see ROLE_TO_TYPE / normalize_census_nodes), so the model commits to
# one axis instead of three half-overlapping fields (the old type/entity_class/is_root).
NODE_ROLES = {
    "contribution",       # the_method: the paper's single primary method/system (the root)
    "component",          # the_method: a sub-method/module that is part of the contribution
    "builds_on",          # prior_art: an existing method/model the contribution extends
    "compared_against",   # prior_art: a baseline method the contribution is compared against
    "dataset",            # testbed: data the method is trained or evaluated on
    "benchmark",          # testbed: a standardized dataset+protocol for evaluation
    "task",               # testbed: the problem being solved/evaluated
    "metric",             # yardsticks: a reported performance measure
}
# role -> coarse node type. Total and unambiguous: a node's type is a strict coarsening of
# its role, so the census carries only `role` and the pipeline derives `type` from it.
ROLE_TO_TYPE: dict[str, str] = {
    "contribution": "Method",
    "component": "Method",
    "builds_on": "Method",
    "compared_against": "Method",
    "dataset": "Entity",
    "benchmark": "Entity",
    "task": "Entity",
    "metric": "Metric",
}
# role -> search cluster (carried into the registry as context for the relation pass).
ROLE_CLUSTER: dict[str, str] = {
    "contribution": "the_method",
    "component": "the_method",
    "builds_on": "prior_art",
    "compared_against": "prior_art",
    "dataset": "testbed",
    "benchmark": "testbed",
    "task": "testbed",
    "metric": "yardsticks",
}
# The single document-level root method is the node whose role is `contribution`.
CONTRIBUTION_ROLE = "contribution"
# Entity roles double as the entity_class on materialized Entity units (identity mapping).
ENTITY_ROLES = {role for role, type_ in ROLE_TO_TYPE.items() if type_ == "Entity"}
UNIT_TYPES = {
    "Document",
    "Entity",
    "Method",
    "Claim",
    "Problem",
    "Setting",
    "Metric",
}
FORBIDDEN_UNIT_TYPES = {
    "RoleBinding",
    "Relation",
    "MethodArtifact",
    "SystemModel",
    "Proposition",
    "Category",
    "Provenance",
}

DOC_ROLES = {"research_article", "review", "meta_analysis", "methodology", "benchmark_survey"}
# Claim kinds, scoped to AI/ML literature: `causal`/`correlational` never fire on this
# corpus and were dropped. `descriptive` is retained for future-work findings.
CLAIM_KINDS = {
    "descriptive",
    "mechanistic",
    "comparative",
    "modeling",
    "ablation_finding",
    "failure_mode",
}
# Setting kinds (reintroduced 2026-05-27). The old `condition_kind` was dropped as monotone
# (always evaluation_setup), but Settings are in fact heterogeneous: a metric is scoped by a
# data split, a test-time inference protocol, a training/compute config, an ensembling regime,
# or a study population — and these are not interchangeable (an ensemble number is not a fair
# peer of a single-model number). `setting_kind` names that axis so consumers can separate
# training/compute setups from evaluation splits without re-parsing the description.
SETTING_KINDS = {
    "data_split",          # the dataset/subset/split the metric was computed on
    "inference_protocol",  # test-time procedure: beam search params, crop/scale, single-view
    "training_config",     # training/compute setup: hardware, steps, fine-tuning regime
    "ensembling",          # multi-model or multi-scale combination presented as a configuration
    "population",          # study population / cohort (e.g. a human-evaluation panel)
}
# Entity = the data/problem substrate. `model` moved to Method (a named model is a Method)
# and `hardware` is apparatus, not a node — both were dropped.
ENTITY_CLASSES = {
    "dataset",
    "benchmark",
    "task",
}
# Method kinds, scoped to AI/ML: `protocol`/`software_system` never fire on this corpus.
METHOD_KINDS = {"algorithm", "model_architecture", "training_strategy", "objective_function"}
COMPARISON_DIRECTIONS = {"higher_is_better", "lower_is_better", "target", "unspecified"}
# Removed in the AI/ML-scoped type cleanup (each was monotone across the corpus): Metric
# `value_type` (always scalar), Claim `novelty` (always original), Claim `epistemic_status`
# (always conclusion), Claim `polarity` (dropped by request). The provenance `source_kind`
# enum was likewise dropped (2026-05-26): provenance is now a flat list of `§N` location
# markers, so SOURCE_KINDS no longer exists. (Setting `condition_kind` was dropped here too
# but returns above as the multi-valued `setting_kind`.)

# Global relation type matrix (section-ir-0.7). Endpoints resolve to a unit defined
# anywhere in the extraction; relations are no longer section-local.
RELATION_MATRIX: dict[str, tuple[set[str], set[str]]] = {
    "part_of": ({"Method", "Entity"}, {"Method", "Entity"}),
    "compares_to": ({"Method", "Entity", "Metric"}, {"Method", "Entity", "Metric"}),
    "evaluates": ({"Metric"}, {"Method"}),
    "measured_on": ({"Metric"}, {"Entity"}),
    "about": ({"Claim"}, {"Method", "Entity", "Metric"}),
    "supports": ({"Metric", "Claim"}, {"Claim"}),
    "motivates": ({"Problem"}, {"Method", "Entity"}),
    "resolves": ({"Claim"}, {"Problem"}),
}
# Which stage authors each relation. The relation pass (stage B) owns the structural
# entity<->entity edges over the full node set; content extraction (stage C) owns the
# edges that require units born during content — the claim-centric `about`/`supports`,
# and `motivates` from a born Problem to the census Method/Entity it justifies (the
# Problem-born source plus the globally visible census target are both in hand in the
# problem call, so no forward reference is needed). `resolves` (Claim -> Problem) is the
# closing stroke of the discovery arc; it joins two units born in *different* parallel
# sections, so no section can author it — assembly synthesizes it (_assign_resolves) from
# the contribution-node join, which is globally visible.
STAGE_B_RELATIONS = {"part_of", "compares_to", "evaluates", "measured_on"}
STAGE_C_RELATIONS = {"about", "supports", "motivates"}
SYNTHESIZED_RELATIONS = {"resolves"}
ARGUMENTATIVE_INCOMING = {"supports"}
UNIT_ID_PREFIX_BY_TYPE: dict[str, str] = {
    "Document": "doc:",
    "Problem": "prb:",
    "Claim": "clm:",
    "Method": "mth:",
    "Entity": "ent:",
    "Setting": "set:",
    "Metric": "met:",
}
ALLOWED_FIELDS_BY_TYPE: dict[str, set[str]] = {
    "Document": {"id", "type", "doc_id", "title", "doc_role", "thesis", "provenance"},
    "Entity": {"id", "type", "name", "entity_class", "provenance"},
    "Method": {
        "id",
        "type",
        "name",
        "method_kind",
        "description",
        "inputs",
        "outputs",
        "formulas",
        "objective_function",
        "implementation_notes",
        "provenance",
    },
    "Claim": {
        "id",
        "type",
        "statement",
        "claim_kind",
        "provenance",
    },
    "Problem": {"id", "type", "description", "provenance"},
    "Setting": {"id", "type", "setting_kind", "description", "provenance"},
    "Metric": {
        "id",
        "type",
        "name",
        "unit",
        "scores",
        "setting_ids",
        "comparison_direction",
        "provenance",
    },
}
ALLOWED_SECTION_FIELDS = {"section_type", "anchor_id", "covers_entries", "units"}
# Unit fields that hold a list of unit-id references (rewritten on dedup). In 0.7
# only Metric.setting_ids remains a reference-list field; subject_id, target_ids,
# components, and evaluated_on were promoted to global relations.
REFERENCE_LIST_FIELDS = ("setting_ids",)


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


def load_section_module(section_type: str) -> str:
    """Load the per-section focus module text for prompt injection."""
    path = SECTION_MODULES_DIR / f"{section_type}.md"
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
    if isinstance(value, str) and value.startswith("setting:"):
        return f"set:{value.split(':', 1)[1]}"
    # Problem ids prefix as prb:; normalize a stray ctx: the model may emit out of habit
    # (Context was the old type name) so its edges/anchors still resolve.
    if isinstance(value, str) and value.startswith("ctx:"):
        return f"prb:{value.split(':', 1)[1]}"
    return value


def _canonicalize_section_id_aliases(sections: list[dict[str, Any]]) -> None:
    """Normalize common LLM ID prefix aliases (e.g. setting: -> set:) before validation."""
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


def _dedup_entities(sections: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[str]:
    """Merge duplicate entities with the same name across sections of the same type."""
    seen: dict[tuple[str, str], str] = {}
    protected_ids = _covered_entry_ids(sections)
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
            if unit.get("type") != "Entity":
                units_to_keep.append(unit)
                continue

            name = unit.get("name", "")
            if not isinstance(name, str) or not name:
                units_to_keep.append(unit)
                continue

            key = (str(section_type), name)
            unit_id = unit.get("id")
            if key in seen and isinstance(unit_id, str):
                if unit_id in protected_ids:
                    units_to_keep.append(unit)
                    continue
                ids_to_replace[unit_id] = seen[key]
                replacements[unit_id] = seen[key]
                warnings.append(
                    f"Merged duplicate Entity {unit_id} into {seen[key]} in {section_type} section"
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


def _normalize_provenance_markers(sections: list[dict[str, Any]]) -> list[str]:
    """Truncate fine-grained subsection markers (e.g. §4.3, §C.1) to their top-level parent.

    Paper input carries only top-level section/appendix markers, so a `§4.3` or `§C.1`
    provenance marker cannot be traced and fails validation. `§4` / `§C` is a real, coarser
    anchor that contains it, so collapse the subnumber rather than discard the marker. This
    covers both numeric body sections (§4.3 -> §4) and lettered appendices (§C.1 -> §C).
    Table/figure references (`§Table 3`) have no clean parent and are left untouched so they
    still surface as genuine provenance violations.
    """
    warnings: list[str] = []
    seen: set[str] = set()
    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            provenance = unit.get("provenance")
            if not isinstance(provenance, list):
                continue
            rewritten: list[Any] = []
            for marker in provenance:
                if isinstance(marker, str):
                    match = SUBSECTION_MARKER_RE.match(marker.strip())
                    if match:
                        new_marker = f"§{match.group(1)}"
                        if marker not in seen:
                            seen.add(marker)
                            warnings.append(f"Normalized provenance marker {marker} to {new_marker}")
                        rewritten.append(new_marker)
                        continue
                rewritten.append(marker)
            unit["provenance"] = rewritten
    return warnings


def _build_unit_type_index(
    sections: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Index unit type (and entity_class for Entities) by unit id across all sections."""
    type_by_id: dict[str, Any] = {}
    entity_class_by_id: dict[str, Any] = {}
    for section in sections:
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                type_by_id[unit["id"]] = unit.get("type")
                if unit.get("type") == "Entity":
                    entity_class_by_id[unit["id"]] = unit.get("entity_class")
    return type_by_id, entity_class_by_id


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
    type_by_id, _ = _build_unit_type_index(sections)
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
    between two Claims, a `measured_on` onto a non-dataset Entity). Such edges are
    unassemblable, so remove them with a warning instead of failing the extraction.
    """
    type_by_id, entity_class_by_id = _build_unit_type_index(sections)
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        rel = relation.get("relation")
        src = relation.get("source_id")
        tgt = relation.get("target_id")
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
        if rel == "measured_on" and entity_class_by_id.get(tgt) not in {"dataset", "benchmark"}:
            warnings.append(
                f"Dropped relation {src} -[measured_on]-> {tgt}: "
                "target must be a dataset/benchmark Entity"
            )
            continue
        kept.append(relation)
    return kept, warnings


def _repair_section_anchors(sections: list[dict[str, Any]]) -> list[str]:
    """Re-point anchors that name a unit not defined in their own section.

    A section may anchor on an external id (e.g. an experiment section anchoring on
    the main `mth:` method, which lives in the method section). The anchor must be a
    local, non-Document unit. Prefer re-pointing to a local unit of the section's
    natural anchor type (experiment -> Metric, analysis -> Claim, ...) so the repaired
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
      emits; type/Entity-class/root are coarsenings of it).
    - Re-prefix a node_id whose prefix disagrees with its derived type (mth:/ent:/met:).
    - Suffix later duplicate node_ids so each is defined exactly once.
    - Ensure exactly one document-level root method (role `contribution`): promote the first
      must-priority method when none is marked, demote extras to `component` when several are.
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
        if not isinstance(node_id, str) or ":" not in node_id or not expected:
            continue
        if not node_id.startswith(expected):
            candidate = f"{expected}{node_id.split(':', 1)[1]}"
            if ID_RE.match(candidate):
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
    if method_nodes:
        roots = [node for node in method_nodes if node.get("role") == CONTRIBUTION_ROLE]
        if not roots:
            chosen = next(
                (node for node in method_nodes if node.get("salience") == "must"),
                method_nodes[0],
            )
            chosen["role"] = CONTRIBUTION_ROLE
        elif len(roots) > 1:
            for extra in roots[1:]:
                extra["role"] = "component"
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

    nodes = census.get("nodes")
    if not isinstance(nodes, list):
        issues.append("Census nodes must be a list")
        return issues

    seen_ids: set[str] = set()
    method_count = 0
    contribution_count = 0
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
        if node_type == "Method":
            method_count += 1
            if role == CONTRIBUTION_ROLE:
                contribution_count += 1

    if method_count and contribution_count != 1:
        issues.append(
            f"Census must mark exactly one contribution method (found {contribution_count})"
        )
    return issues


def build_node_registry(census: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the lightweight all-node registry passed to the relation and content stages.

    Carries what later stages need to reference and route a node: id, type, name, gloss,
    salience, and the granular `role` with its search `cluster`. The role lets the relation
    pass route edges (a `component` is part_of the `contribution`; a `compared_against`
    method is compares_to it) and the content stage find the contribution method. For an
    Entity, `role` doubles as the entity_class (dataset/benchmark/task).
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
        if node_type == "Entity" and role in ENTITY_ROLES:
            entry["entity_class"] = role
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
- Emit only the claim-centric edges (`about`, `supports`) your section authors, in `relations`.
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


def build_document_unit(paper_content: str, thesis: str = "") -> dict[str, Any]:
    """Build a deterministic Document unit from the paper preamble.

    `thesis` is the one-sentence central contribution; assembly sources it from the census
    `spine_summary.central_contribution` (already extracted and validated non-empty), so no
    extra LLM call is needed. It is optional so the builder still works without a census.
    """
    first_marker = paper_content.find("[§")
    preamble = paper_content[:first_marker] if first_marker >= 0 else paper_content[:500]
    title_match = re.search(r"^#\s+(.+)", preamble, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = next((line.strip() for line in preamble.splitlines() if line.strip()), "Untitled")
    doc_id = _slugify_doc_id(title)
    return {
        "id": f"doc:{doc_id}",
        "type": "Document",
        "doc_id": doc_id,
        "title": title,
        "doc_role": "research_article",
        "thesis": thesis,
        "provenance": [],
    }


def build_extraction_notes(
    census: dict[str, Any],
    sections: list[dict[str, Any]],
    sections_included: list[str] | None = None,
    sections_omitted: list[str] | None = None,
) -> dict[str, Any]:
    """Build final extraction notes for assembled content output.

    Coverage is measured against the census `must` nodes: a must-node is covered iff a unit
    reusing its node_id was materialized by some section. node_id == unit_id, so coverage is
    structural and needs no covers_entries echo from the model.
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
        "ir_version": "section-ir-0.8",
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


def _repair_score_refs(sections: list[dict[str, Any]]) -> list[str]:
    """Blank dangling or wrong-type per-row score references (system_id/setting_id) once the
    full unit set is known — lossy-but-safe, logged to uncertain_assignments. system_id resolves
    globally (Methods live in the method section); setting_id resolves to a section-local Setting."""
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
            if not isinstance(unit, dict) or unit.get("type") != "Metric":
                continue
            for index, score in enumerate(unit.get("scores", []) or []):
                if not isinstance(score, dict):
                    continue
                system_id = score.get("system_id")
                if system_id and (
                    system_id not in unit_index or unit_index[system_id].get("type") != "Method"
                ):
                    warnings.append(
                        f"Metric {unit.get('id')} scores[{index}] system_id {system_id!r} "
                        "did not resolve to a Method; blanked"
                    )
                    score["system_id"] = ""
                setting_id = score.get("setting_id")
                if setting_id and (
                    setting_id not in local_ids
                    or unit_index.get(setting_id, {}).get("type") != "Setting"
                ):
                    warnings.append(
                        f"Metric {unit.get('id')} scores[{index}] setting_id {setting_id!r} "
                        "is not a local Setting; blanked"
                    )
                    score["setting_id"] = ""
    return warnings


def _drop_baseline_evaluates(
    relations: list[dict[str, Any]], census: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop `evaluates` edges pointing at a `compared_against` baseline. By policy a Metric
    `evaluates` only the method family it measures (contribution/component); a baseline is linked
    structurally by `compares_to` and quantitatively by a score row (system_id), never evaluated —
    so the metric's primary subject stays recoverable instead of diluted across every system row."""
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
    """Synthesize the closing `resolves` edges of the discovery arc: Claim -> Problem.

    `resolves` is a born->born edge across two *parallel* content sections (the headline Claim
    in evidence, the Problem in the problem section), so neither section can author it without a
    forward reference into the other's freshly-invented ids. But both ends attach to the same
    globally-visible census `contribution` node — the Problem `motivates` it, the headline Claim
    is `about` it — so assembly derives the edge deterministically once every section is in hand:

        Problem --motivates--> [contribution] <--about-- Claim   =>   Claim --resolves--> Problem

    Returns new relation dicts to append; downstream `_dedup_relations` removes any duplicates.
    """
    if not census:
        return []
    contribution_ids = {
        node.get("node_id")
        for node in (census.get("nodes") or [])
        if isinstance(node, dict) and node.get("role") == CONTRIBUTION_ROLE
    }
    contribution_ids.discard(None)
    if not contribution_ids:
        return []

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
    for rel in relations:
        if (
            not isinstance(rel, dict)
            or rel.get("relation") != "about"
            or rel.get("target_id") not in contribution_ids
        ):
            continue
        claim_id = rel.get("source_id")
        if unit_type.get(claim_id) != "Claim" or claim_id in seen:
            continue
        seen.add(claim_id)
        prov = rel.get("provenance") or unit_prov.get(problem_id) or unit_prov.get(claim_id) or []
        new_relations.append(
            {
                "source_id": claim_id,
                "relation": "resolves",
                "target_id": problem_id,
                "provenance": list(prov),
            }
        )
    return new_relations


def assemble_extraction(
    census: dict[str, Any],
    stage_b_relations: list[dict[str, Any]],
    section_results: list[dict[str, Any]],
    paper_content: str,
    sections_included: list[str] | None = None,
    sections_omitted: list[str] | None = None,
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

    assembly_warnings: list[str] = []
    assembly_warnings.extend(_sanitize_unit_text(sections))
    assembly_warnings.extend(_dedup_entities(sections, relations))
    assembly_warnings.extend(_dedup_unit_ids(sections))
    assembly_warnings.extend(_drop_empty_sections(sections))
    assembly_warnings.extend(_normalize_provenance_markers(sections))
    assembly_warnings.extend(_repair_section_anchors(sections))
    assembly_warnings.extend(_repair_score_refs(sections))

    relations, warns = _dedup_relations(relations)
    assembly_warnings.extend(warns)
    relations, warns = _drop_dangling_relations(relations, sections)
    assembly_warnings.extend(warns)
    relations, warns = _drop_invalid_relations(relations, sections)
    assembly_warnings.extend(warns)
    relations, warns = _drop_baseline_evaluates(relations, census)
    assembly_warnings.extend(warns)

    # Synthesize the closing `resolves` edge(s) from the surviving contribution-node join,
    # then dedup so a re-run can't double it. These are valid by construction (Claim->Problem).
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
    )
    if assembly_warnings:
        uncertain = extraction_notes.setdefault("uncertain_assignments", [])
        if isinstance(uncertain, list):
            uncertain.extend(assembly_warnings)

    spine_summary = census.get("spine_summary") if isinstance(census, dict) else None
    thesis = spine_summary.get("central_contribution") or "" if isinstance(spine_summary, dict) else ""
    return {
        "document": build_document_unit(paper_content, thesis=thesis),
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


def _normalize_cite_key(value: Any) -> str:
    """Normalize a citation marker to a comparable key: strip brackets/whitespace, lowercase.

    A reference's `id` and a census node's `cite_keys` both name the same in-text marker but
    may differ cosmetically ('[31]' vs '31'); normalizing both lets the bibliography join the
    spine on the paper's own citation rather than on a fuzzy name match.
    """
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\[\]\s]+", "", value).lower()


def reconcile_reference_units(
    references: dict[str, Any] | None,
    extraction: dict[str, Any],
    census: dict[str, Any] | None = None,
) -> list[str]:
    """Link each reference to the spine Method/Entity unit(s) it contributes.

    The references pass runs before section extraction, so it never knows the final unit IDs
    and always emits `provides_unit_ids: []`. Once the spine exists, fill it with a two-tier
    join, strongest signal first:

    1. **Citation key** (primary, exact): a census node carries the in-text bibliography
       marker(s) it was cited as (`cite_keys`); since `node_id == unit_id`, a reference whose
       `id` matches a materialized node's cite_key links straight to that unit. Grounded in the
       paper's own citation, so it catches names the spine spells differently (reference "GNMT"
       -> unit "GNMT + RL" cited as [31]).
    2. **Name** (fallback, fuzzy): when no citation key matches, fall back to a unique
       normalized match of `provides_name` against Method/Entity unit names (the original
       behavior). Conservative: an ambiguous (multi-unit) or unmatched name stays `[]`.

    Mutates `references` in place and returns warnings for the audit trail.
    """
    warnings: list[str] = []
    if not isinstance(references, dict):
        return warnings
    ref_list = references.get("references")
    if not isinstance(ref_list, list):
        return warnings

    # Index materialized Method/Entity units by id and by normalized name.
    type_by_id: dict[str, Any] = {}
    name_to_ids: dict[str, list[str]] = {}
    for section in extraction.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict) or unit.get("type") not in {"Method", "Entity"}:
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
) -> dict[str, Any]:
    """Extract one content section (stage C) using the synchronous LLM client."""
    system_prompt, _ = load_prompt(SECTION_EXTRACTION_PROMPT_PATH)
    section_module = load_section_module(section_type)
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

    if unit.get("type") in {"Claim", "Metric"} and not provenance:
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

    if utype == "Document":
        for key in ("doc_id", "title", "doc_role"):
            if not unit.get(key):
                issues.append(f"Document {uid} missing {key}")
        if unit.get("doc_role") not in DOC_ROLES:
            issues.append(f"Document {uid} has invalid doc_role: {unit.get('doc_role')}")
    elif utype == "Entity":
        for key in ("name", "entity_class"):
            if not unit.get(key):
                issues.append(f"Entity {uid} missing {key}")
        if unit.get("entity_class") not in ENTITY_CLASSES:
            issues.append(f"Entity {uid} has invalid entity_class: {unit.get('entity_class')}")
    elif utype == "Method":
        for key in ("name", "method_kind"):
            if not unit.get(key):
                issues.append(f"Method {uid} missing {key}")
        if unit.get("method_kind") not in METHOD_KINDS:
            issues.append(f"Method {uid} has invalid method_kind: {unit.get('method_kind')}")
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
    elif utype == "Claim":
        for key in ("statement", "claim_kind"):
            if not unit.get(key):
                issues.append(f"Claim {uid} missing {key}")
        if unit.get("claim_kind") not in CLAIM_KINDS:
            issues.append(f"Claim {uid} has invalid claim_kind: {unit.get('claim_kind')}")
    elif utype == "Problem":
        if not unit.get("description"):
            issues.append(f"Problem {uid} missing description")
    elif utype == "Setting":
        if not unit.get("description"):
            issues.append(f"Setting {uid} missing description")
        if not unit.get("setting_kind"):
            issues.append(f"Setting {uid} missing setting_kind")
        elif unit.get("setting_kind") not in SETTING_KINDS:
            issues.append(f"Setting {uid} has invalid setting_kind: {unit.get('setting_kind')}")
    elif utype == "Metric":
        for key in ("name", "unit"):
            if not unit.get(key):
                issues.append(f"Metric {uid} missing {key}")
        scores = unit.get("scores")
        if not isinstance(scores, list) or not scores:
            issues.append(f"Metric {uid} scores must be a non-empty list")
        else:
            for index, score in enumerate(scores):
                if not isinstance(score, dict):
                    issues.append(f"Metric {uid} scores[{index}] must be an object")
                    continue
                if not score.get("variant"):
                    issues.append(f"Metric {uid} scores[{index}] missing variant")
                if score.get("value") is None:
                    issues.append(f"Metric {uid} scores[{index}] missing value")
                elif not isinstance(score.get("value"), str):
                    issues.append(f"Metric {uid} scores[{index}] value must be a string")
                if not isinstance(score.get("variance"), str):
                    issues.append(f"Metric {uid} scores[{index}] variance must be a string")
                # Per-row references (0.7, 2026-05-27): a row may name the Method it reports
                # (system_id, global) and the local Setting it was measured under (setting_id).
                # Both are optional — "" means "not pinned" — but when non-empty they must resolve.
                system_id = score.get("system_id")
                if system_id:
                    system_unit = unit_index.get(system_id)
                    if system_unit is None:
                        issues.append(f"Metric {uid} scores[{index}] has unknown system_id: {system_id}")
                    elif system_unit.get("type") != "Method":
                        issues.append(f"Metric {uid} scores[{index}] system_id {system_id} must point to a Method")
                row_setting_id = score.get("setting_id")
                if row_setting_id:
                    row_setting_unit = unit_index.get(row_setting_id)
                    if row_setting_unit is None:
                        issues.append(f"Metric {uid} scores[{index}] has unknown setting_id: {row_setting_id}")
                    elif row_setting_id not in local_ids:
                        issues.append(f"Metric {uid} scores[{index}] setting_id must be section-local: {row_setting_id}")
                    elif row_setting_unit.get("type") != "Setting":
                        issues.append(f"Metric {uid} scores[{index}] setting_id {row_setting_id} must point to a local Setting")
        # setting_ids scope a metric to local Settings. In 0.7 it is optional: a
        # deployable metric may carry scoping Settings, an ablation metric may carry
        # none. The metric->method and metric->dataset edges are global relations now.
        setting_ids = unit.get("setting_ids")
        if setting_ids is None:
            issues.append(f"Metric {uid} missing setting_ids")
        elif not isinstance(setting_ids, list):
            issues.append(f"Metric {uid} setting_ids must be a list")
        else:
            for setting_id in setting_ids:
                setting_unit = unit_index.get(setting_id)
                if setting_unit is None:
                    issues.append(f"Metric {uid} has unknown setting_id: {setting_id}")
                elif setting_id not in local_ids:
                    issues.append(f"Metric {uid} setting_id must be section-local: {setting_id}")
                elif setting_unit.get("type") != "Setting":
                    issues.append(
                        f"Metric {uid} setting_id {setting_id} must point to a local Setting"
                    )
        comparison_direction = unit.get("comparison_direction")
        if "comparison_direction" in unit and comparison_direction not in COMPARISON_DIRECTIONS:
            issues.append(f"Metric {uid} has invalid comparison_direction: {comparison_direction}")


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
    if (
        rel == "measured_on"
        and target_unit is not None
        and target_unit.get("entity_class") not in {"dataset", "benchmark"}
    ):
        issues.append(
            f"relation {source_id} -[measured_on]-> {target_id} target must be a "
            "dataset/benchmark Entity"
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
        if unit.get("type") == "Claim":
            if (
                unit_sections.get(uid) != "evidence"
                and uid not in incoming_argumentative
            ):
                issues.append(f"Claim {uid} lacks an incoming argumentative (supports) relation")

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
        if notes.get("ir_version") != "section-ir-0.8":
            issues.append(f"extraction_notes has invalid ir_version: {notes.get('ir_version')}")
        sections_used = notes.get("sections_used", [])
        if isinstance(sections_used, list):
            invalid_sections = [st for st in sections_used if st not in SECTION_TYPES]
            if invalid_sections:
                issues.append(f"extraction_notes.sections_used has invalid values: {invalid_sections}")

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
    unknown_uncovered = sorted(uncovered_items - node_ids)
    if unknown_uncovered:
        issues.append(f"uncovered_items references unknown census nodes: {unknown_uncovered}")

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
