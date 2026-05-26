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
PLANNING_PROMPT_PATH = PROMPTS_DIR / "planning-pass.md"
SECTION_EXTRACTION_PROMPT_PATH = PROMPTS_DIR / "section-extraction-pass.md"
SECTION_MODULES_DIR = PROMPTS_DIR / "section-modules"
EXAMPLES_DIR = PROMPTS_DIR / "examples"
METADATA_PROMPT_PATH = PROJECT_ROOT / "prompts" / "metadata-extraction.md"
REFERENCES_PROMPT_PATH = PROJECT_ROOT / "prompts" / "references-extraction.md"
SCHEMAS_DIR = PROJECT_ROOT / "schemas"
PLANNING_SCHEMA_PATH = SCHEMAS_DIR / "planning-output.schema.json"
METADATA_SCHEMA_PATH = SCHEMAS_DIR / "metadata-output.schema.json"
REFERENCES_SCHEMA_PATH = SCHEMAS_DIR / "references-output.schema.json"
SECTION_SCHEMA_FILES: dict[str, str] = {
    "context": "section-context.schema.json",
    "claim": "section-claim.schema.json",
    "method": "section-method.schema.json",
    "experiment": "section-experiment.schema.json",
    "analysis": "section-analysis.schema.json",
}

DEFAULT_PARALLEL_MAX_WORKERS = 5
DEFAULT_SECTION_MAX_TOKENS = 131_072
MAX_SECTION_RETRIES = 2
SECTION_MARKER_RE = re.compile(r"(?m)^\[§(\d+)\]\s*")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")
PROVENANCE_SOURCE_RE = re.compile(r"^§\d+$")
SUBSECTION_MARKER_RE = re.compile(r"^§(\d+)(?:\.\d+)+$")

SECTION_TYPES = {"context", "claim", "method", "experiment", "analysis"}
PLANNED_SECTION_TYPES = {"method", "experiment"}
PLANLESS_SECTION_TYPES = {"context", "claim", "analysis"}
SECTION_ORDER = ["context", "claim", "method", "experiment", "analysis"]
SECTION_ALLOWED_UNIT_TYPES: dict[str, set[str]] = {
    "context": {"Context"},
    "claim": {"Claim"},
    "method": {"Method"},
    "experiment": {"Metric", "Condition", "Entity"},
    "analysis": {"Claim", "Metric", "Entity"},
}
# The unit type that should naturally anchor each section. Used when repairing an
# anchor that names a non-local unit (e.g. an experiment section reaching for the
# root `mth:` method): prefer re-pointing to a local unit of this type before
# falling back to the first local non-Document unit.
SECTION_PREFERRED_ANCHOR_TYPE: dict[str, str] = {
    "context": "Context",
    "claim": "Claim",
    "method": "Method",
    "experiment": "Metric",
    "analysis": "Claim",
}
PLAN_RELATIONS_BY_SECTION: dict[str, set[str]] = {
    "method": {"part_of", "feeds", "alternative_to"},
    "experiment": {"evaluates"},
}
PLAN_ITEM_PREFIXES_BY_SECTION: dict[str, tuple[str, ...]] = {
    "method": ("mth:",),
    "experiment": ("met:", "cnd:", "ent:"),
}
TYPED_ARRAY_KEYS: dict[str, str] = {
    "entities": "Entity",
    "contexts": "Context",
    "conditions": "Condition",
    "claims": "Claim",
    "metrics": "Metric",
    "methods": "Method",
}
UNIT_TYPES = {
    "Document",
    "Entity",
    "Method",
    "Claim",
    "Context",
    "Condition",
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
CLAIM_KINDS = {
    "descriptive",
    "mechanistic",
    "causal",
    "correlational",
    "comparative",
    "modeling",
    "ablation_finding",
    "failure_mode",
}
CONTEXT_KINDS = {
    "background",
    "gap",
    "motivation",
    "challenge",
    "assumption",
}
CONDITION_KINDS = {
    "experimental",
    "boundary",
    "evaluation_setup",
    "hyperparameter",
}
ENTITY_CLASSES = {
    "dataset",
    "benchmark",
    "model",
    "task",
    "hardware",
}
METHOD_KINDS = {"algorithm", "model_architecture", "protocol", "software_system", "training_strategy", "objective_function"}
SOURCE_KINDS = {
    "sentence",
    "table",
    "figure",
    "appendix",
    "caption",
    "equation",
    "supplementary_material",
}
COMPARISON_DIRECTIONS = {"higher_is_better", "lower_is_better", "target", "unspecified"}
VALUE_TYPES = {"scalar", "range", "ratio", "categorical"}
POLARITIES = {"positive", "negative", "neutral", "mixed"}
NOVELTIES = {"original", "replication", "citation", "synthesis"}
EPISTEMIC_STATUSES = {"hypothesis", "conclusion", "established_fact"}

LINK_MATRIX: dict[str, tuple[set[str], set[str]]] = {
    "supports": ({"Metric", "Claim"}, {"Claim"}),
    "part_of": ({"Method", "Entity"}, {"Method", "Entity"}),
    "compares_to": ({"Method", "Entity", "Metric"}, {"Method", "Entity", "Metric"}),
}
ARGUMENTATIVE_INCOMING = {"supports"}
UNIT_ID_PREFIX_BY_TYPE: dict[str, str] = {
    "Document": "doc:",
    "Context": "ctx:",
    "Claim": "clm:",
    "Method": "mth:",
    "Entity": "ent:",
    "Condition": "cnd:",
    "Metric": "met:",
}
ALLOWED_FIELDS_BY_TYPE: dict[str, set[str]] = {
    "Document": {"id", "type", "doc_id", "title", "doc_role", "provenance"},
    "Entity": {"id", "type", "name", "entity_class", "provenance"},
    "Method": {
        "id",
        "type",
        "name",
        "method_kind",
        "description",
        "components",
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
        "polarity",
        "novelty",
        "epistemic_status",
        "target_ids",
        "provenance",
    },
    "Context": {"id", "type", "context_kind", "description", "provenance"},
    "Condition": {"id", "type", "condition_kind", "description", "provenance"},
    "Metric": {
        "id",
        "type",
        "name",
        "unit",
        "scores",
        "subject_id",
        "context_ids",
        "evaluated_on",
        "comparison_direction",
        "value_type",
        "provenance",
    },
}
ALLOWED_SECTION_FIELDS = {"section_type", "anchor_id", "covers_entries", "units", "links"}
REFERENCE_LIST_FIELDS = ("target_ids", "context_ids", "components", "evaluated_on")


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


class ValidationError(Exception):
    """Raised when strict pipeline validation finds section-IR issues."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        details = "\n- ".join(issues)
        super().__init__(f"Section-IR validation failed:\n- {details}")


def build_response_format(schema: dict, name: str = "response", model: str = "") -> dict:
    """Build the response_format dict for structured output with JSON schema."""
    final = _sanitize_schema_for_gemini(schema) if _needs_schema_sanitize(model) else schema
    return {"type": "json_schema", "json_schema": {"name": name, "schema": final, "strict": True}}


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


def load_planning_schema() -> dict:
    """Load the planning pass schema for structured output."""
    return json.loads(PLANNING_SCHEMA_PATH.read_text(encoding="utf-8"))


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
    if isinstance(value, str) and value.startswith("cond:"):
        return f"cnd:{value.split(':', 1)[1]}"
    return value


def _canonicalize_section_id_aliases(sections: list[dict[str, Any]]) -> None:
    """Normalize common LLM ID prefix aliases before validation."""
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
                for key in ("id", "subject_id"):
                    if key in unit:
                        unit[key] = _canonicalize_id_alias(unit[key])
                for key in REFERENCE_LIST_FIELDS:
                    values = unit.get(key)
                    if isinstance(values, list):
                        unit[key] = [_canonicalize_id_alias(value) for value in values]

        links = section.get("links", [])
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                for key in ("source_id", "target_id"):
                    if key in link:
                        link[key] = _canonicalize_id_alias(link[key])


def _covered_entry_ids(sections: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for section in sections:
        covers_entries = section.get("covers_entries")
        if isinstance(covers_entries, list):
            covered.update(item for item in covers_entries if isinstance(item, str))
    return covered


def _section_local_ids(section: dict[str, Any]) -> set[str]:
    units = section.get("units", [])
    if not isinstance(units, list):
        return set()
    return {
        unit["id"]
        for unit in units
        if isinstance(unit, dict) and isinstance(unit.get("id"), str)
    }


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
            subject_id = unit.get("subject_id")
            if isinstance(subject_id, str) and subject_id in replacements:
                unit["subject_id"] = replacements[subject_id]
            for field in REFERENCE_LIST_FIELDS:
                values = unit.get(field)
                if isinstance(values, list):
                    unit[field] = [replacements.get(value, value) for value in values]


def _rewrite_section_links(section: dict[str, Any], replacements: dict[str, str]) -> None:
    links = section.get("links", [])
    if not isinstance(links, list):
        return
    local_ids = _section_local_ids(section)
    rewritten_links = []
    for link in links:
        if not isinstance(link, dict):
            rewritten_links.append(link)
            continue
        source_id = replacements.get(link.get("source_id"), link.get("source_id"))
        target_id = replacements.get(link.get("target_id"), link.get("target_id"))
        if source_id not in local_ids or target_id not in local_ids:
            continue
        link["source_id"] = source_id
        link["target_id"] = target_id
        rewritten_links.append(link)
    section["links"] = rewritten_links


def _dedup_entities(sections: list[dict[str, Any]]) -> list[str]:
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
    for section in sections:
        _rewrite_section_links(section, replacements)
        if replacements:
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

        links = section.get("links", [])
        if isinstance(links, list):
            section["links"] = [
                link
                for link in links
                if isinstance(link, dict)
                and link.get("source_id") in local_ids
                and link.get("target_id") in local_ids
            ]
    return warnings


def _reconcile_method_components(sections: list[dict[str, Any]]) -> None:
    """Make `part_of` links the source of truth for Method composition.

    Method decomposition can be stated two ways: a child ``--part_of-->`` parent link
    and the parent's ``components[]`` list. The link is authoritative. This folds any
    model-emitted component that names a section-local Method into the link set (adding
    the missing link), then rebuilds every Method's ``components[]`` as a deterministic
    projection of those links, so the two representations always agree. Components that
    do not resolve to a section-local Method are dropped.

    Runs after `_dedup_unit_ids`, when unit IDs are final and links are section-local.
    """
    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        method_units = [
            unit
            for unit in units
            if isinstance(unit, dict)
            and unit.get("type") == "Method"
            and isinstance(unit.get("id"), str)
        ]
        if not method_units:
            continue
        method_ids = {unit["id"] for unit in method_units}

        links = section.get("links")
        if not isinstance(links, list):
            links = []

        # Collect authoritative child -> parent edges in first-seen order.
        edges: list[tuple[str, str]] = []
        seen_edges: set[tuple[str, str]] = set()

        def add_edge(child: Any, parent: Any) -> None:
            if (
                isinstance(child, str)
                and isinstance(parent, str)
                and child != parent
                and child in method_ids
                and parent in method_ids
            ):
                edge = (child, parent)
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    edges.append(edge)

        # Existing part_of links come first so link order drives component order.
        for link in links:
            if isinstance(link, dict) and link.get("relation") == "part_of":
                add_edge(link.get("source_id"), link.get("target_id"))

        # Fold model-emitted components so their intent survives the projection.
        for unit in method_units:
            components = unit.get("components")
            if isinstance(components, list):
                for child in components:
                    add_edge(child, unit["id"])

        # Promote any folded component into the authoritative link set.
        existing_part_of = {
            (link.get("source_id"), link.get("target_id"))
            for link in links
            if isinstance(link, dict) and link.get("relation") == "part_of"
        }
        for child, parent in edges:
            if (child, parent) not in existing_part_of:
                links.append({"source_id": child, "relation": "part_of", "target_id": parent})
                existing_part_of.add((child, parent))
        section["links"] = links

        # Rebuild components[] as a pure projection of the authoritative edges.
        children_by_parent: dict[str, list[str]] = {}
        for child, parent in edges:
            children_by_parent.setdefault(parent, []).append(child)
        for unit in method_units:
            unit["components"] = children_by_parent.get(unit["id"], [])


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
    """Truncate fine-grained subsection markers (e.g. §4.3) to their top-level §N.

    Paper input carries only top-level `[§N]` markers, so a `§4.3` provenance source
    cannot be traced and fails validation. `§4` is a real, coarser anchor that does
    contain `§4.3`, so collapse the subnumber rather than discard the provenance.
    Appendix (`§G.2`) and table/figure references have no `§N` to collapse to and are
    left untouched so they still surface as genuine provenance violations.
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
            for marker in provenance:
                if not isinstance(marker, dict):
                    continue
                source = marker.get("source")
                if not isinstance(source, list):
                    continue
                rewritten: list[Any] = []
                for item in source:
                    if isinstance(item, str):
                        match = SUBSECTION_MARKER_RE.match(item.strip())
                        if match:
                            new_item = f"§{match.group(1)}"
                            if item not in seen:
                                seen.add(item)
                                warnings.append(f"Normalized provenance marker {item} to {new_item}")
                            rewritten.append(new_item)
                            continue
                    rewritten.append(item)
                marker["source"] = rewritten
    return warnings


def _drop_invalid_links(sections: list[dict[str, Any]]) -> list[str]:
    """Drop section-local links that violate the link type matrix.

    The model sometimes emits relations the IR cannot represent (e.g. an
    `occurs_under` from a Condition, or a `compares_to` between two Claims). Such
    links are unassemblable, so remove them with a warning instead of letting them
    fail the whole extraction.
    """
    warnings: list[str] = []
    for section in sections:
        units = section.get("units", [])
        if not isinstance(units, list):
            continue
        type_by_id = {
            unit["id"]: unit.get("type")
            for unit in units
            if isinstance(unit, dict) and isinstance(unit.get("id"), str)
        }
        links = section.get("links")
        if not isinstance(links, list):
            continue
        kept: list[Any] = []
        section_type = section.get("section_type")
        for link in links:
            if not isinstance(link, dict):
                continue
            relation = link.get("relation")
            source_id = link.get("source_id")
            target_id = link.get("target_id")
            matrix = LINK_MATRIX.get(relation)
            if matrix is None:
                warnings.append(
                    f"Dropped link with invalid relation {relation!r} in {section_type} section"
                )
                continue
            allowed_sources, allowed_targets = matrix
            source_type = type_by_id.get(source_id)
            target_type = type_by_id.get(target_id)
            if source_type not in allowed_sources or target_type not in allowed_targets:
                warnings.append(
                    f"Dropped link {source_id} -[{relation}]-> {target_id}: invalid type pairing "
                    f"({source_type} -> {target_type}) in {section_type} section"
                )
                continue
            kept.append(link)
        if len(kept) != len(links):
            section["links"] = kept
    return warnings


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


def _reconcile_covers_entries(sections: list[dict[str, Any]]) -> list[str]:
    """Drop covers_entries that no longer resolve to a defined unit.

    Validation requires every covers_entries value to name a real unit. A section can
    end up claiming a plan item whose unit was never materialized — a phantom `_2`
    plan item from duplicate-id normalization, or a unit merged away during dedup that
    left no replacement. Prune the unresolved entries here; any must-item that loses
    its only cover resurfaces honestly in extraction_notes.uncovered_items.

    Runs last in assembly, after every step that can remove or merge units.
    """
    warnings: list[str] = []
    unit_ids: set[str] = set()
    for section in sections:
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                unit_ids.add(unit["id"])
    for section in sections:
        covers = section.get("covers_entries")
        if not isinstance(covers, list):
            continue
        kept = [entry for entry in covers if isinstance(entry, str) and entry in unit_ids]
        if len(kept) != len(covers):
            dropped = [entry for entry in covers if not (isinstance(entry, str) and entry in unit_ids)]
            warnings.append(
                f"Dropped unresolved covers_entries in {section.get('section_type')} section: {dropped}"
            )
            section["covers_entries"] = kept
    return warnings


def _reconcile_metric_subjects(sections: list[dict[str, Any]], plan: dict[str, Any]) -> list[str]:
    """Align experiment Metric.subject_id with the plan, falling back to the root method.

    The method->experiment seam is a single edge: an experiment Metric measures a method
    via `subject_id`, which the planner declares with an `evaluates` relation. Two failures
    show up once parallel sections are merged:

    - B: the extractor blindly defaults `subject_id` to the root method even though the plan
      names a specific `evaluates` target. When the covered plan item carries an `evaluates`
      relation that resolves to a real Method unit, re-point `subject_id` to it.
    - E: the extractor emits a `subject_id` that resolves to no unit (a dangling cross-section
      reference). Fall back to the document-level root method so the seam stays connected.

    Both repairs are logged to uncertain_assignments. Mapping is best-effort: a Metric is keyed
    by its own id first (the planner's `item_id` is reused as the unit id) then by the section's
    covered plan items; when nothing resolves we leave the value for E or validation to handle.
    """
    warnings: list[str] = []

    evaluates_target: dict[str, str] = {}
    root_method_id: str | None = None
    for section_plan in expand_section_plans(plan):
        is_method_section = section_plan.get("section_type") == "method"
        for item in section_plan.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id")
            if is_method_section and item.get("is_root") is True and isinstance(item_id, str):
                root_method_id = item_id
            for relation in item.get("relations", []) or []:
                if not isinstance(relation, dict) or relation.get("type") != "evaluates":
                    continue
                target = relation.get("target_id")
                if isinstance(item_id, str) and isinstance(target, str):
                    evaluates_target[item_id] = target

    type_by_id: dict[str, str | None] = {}
    for section in sections:
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                type_by_id[unit["id"]] = unit.get("type")

    def is_method(uid: Any) -> bool:
        return isinstance(uid, str) and type_by_id.get(uid) == "Method"

    for section in sections:
        if section.get("section_type") != "experiment":
            continue
        covers = [c for c in (section.get("covers_entries") or []) if isinstance(c, str)]
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict) or unit.get("type") != "Metric":
                continue
            uid = unit.get("id")
            current = unit.get("subject_id")
            # B: prefer the evaluates target declared for this metric's plan item.
            desired = next(
                (
                    evaluates_target[key]
                    for key in [uid, *covers]
                    if key in evaluates_target and is_method(evaluates_target[key])
                ),
                None,
            )
            if desired is not None:
                if desired != current:
                    unit["subject_id"] = desired
                    warnings.append(
                        f"Set experiment Metric {uid} subject_id to evaluates target {desired} "
                        f"(was {current!r})"
                    )
                continue
            # E: fall back to root only when subject_id resolves to no unit at all (a
            # dangling cross-section reference). A reference that resolves to a real but
            # wrong-typed unit is left for validation to report, not silently rewritten.
            resolves = isinstance(current, str) and current in type_by_id
            if not resolves and is_method(root_method_id):
                unit["subject_id"] = root_method_id
                warnings.append(
                    f"Reset experiment Metric {uid} subject_id from {current!r} to root method "
                    f"{root_method_id}: original did not resolve to any unit"
                )
    return warnings


def _reconcile_analysis_metric_subjects(sections: list[dict[str, Any]]) -> list[str]:
    """Point an analysis Metric.subject_id at the component its supported Claim is about.

    Ablation findings live in analysis as a Claim plus a supporting Metric. The Claim's
    `target_ids` bind to the specific ablated component fairly reliably, but the supporting
    Metric's `subject_id` often stays on the whole-system/root method: `_reconcile_metric_subjects`
    only fixes *experiment* Metrics, so analysis subjects are unguided. When an analysis Metric
    supports — via a `Metric --supports--> Claim` link — claims that point to exactly one
    component, re-point its `subject_id` to that component so the quantitative ablation value is
    attributed to the part it measures rather than the whole system.

    Conservative by design:
    - only fires when the supported claims collapse to a single component (ambiguous,
      system-level, or unlinked metrics are left untouched);
    - never downgrades a `subject_id` that already names a component.

    A "component" is any Method id that appears as a child in some Method's `components[]`, so
    this must run after `_reconcile_method_components` (which populates that projection) and
    before link validation strips anything.
    """
    warnings: list[str] = []

    child_ids: set[str] = set()
    for section in sections:
        for unit in section.get("units", []) or []:
            if isinstance(unit, dict) and unit.get("type") == "Method":
                for child in unit.get("components", []) or []:
                    if isinstance(child, str):
                        child_ids.add(child)
    if not child_ids:
        return warnings

    for section in sections:
        if section.get("section_type") != "analysis":
            continue
        units = section.get("units", []) or []

        unit_types: dict[str, str | None] = {}
        claim_components: dict[str, list[str]] = {}
        for unit in units:
            if not isinstance(unit, dict) or not isinstance(unit.get("id"), str):
                continue
            unit_types[unit["id"]] = unit.get("type")
            if unit.get("type") == "Claim":
                claim_components[unit["id"]] = [
                    t for t in (unit.get("target_ids") or []) if isinstance(t, str) and t in child_ids
                ]

        # metric id -> claim ids it supports (only Metric --supports--> Claim counts)
        metric_supports: dict[str, set[str]] = {}
        for link in section.get("links", []) or []:
            if not isinstance(link, dict) or link.get("relation") != "supports":
                continue
            src, tgt = link.get("source_id"), link.get("target_id")
            if unit_types.get(src) == "Metric" and unit_types.get(tgt) == "Claim":
                metric_supports.setdefault(src, set()).add(tgt)

        for unit in units:
            if not isinstance(unit, dict) or unit.get("type") != "Metric":
                continue
            uid = unit.get("id")
            current = unit.get("subject_id")
            if isinstance(current, str) and current in child_ids:
                continue  # already a component — never downgrade
            candidates: list[str] = []
            for claim_id in metric_supports.get(uid, set()):
                for comp in claim_components.get(claim_id, []):
                    if comp not in candidates:
                        candidates.append(comp)
            if len(candidates) != 1:
                continue  # ambiguous, system-level, or unlinked — leave as-is
            desired = candidates[0]
            if desired != current:
                unit["subject_id"] = desired
                warnings.append(
                    f"Set analysis Metric {uid} subject_id to component {desired} "
                    f"(was {current!r}; aligned to its supported ablation Claim)"
                )
    return warnings


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


def iter_plan_items(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all item objects from top-level and nested section plan segments."""
    items: list[dict[str, Any]] = []
    section_plans = plan.get("section_plans", [])
    if not isinstance(section_plans, list):
        return items

    for section_plan in section_plans:
        if not isinstance(section_plan, dict):
            continue
        for item in section_plan.get("items", []) or []:
            if isinstance(item, dict):
                items.append(item)
        for segment_plan in section_plan.get("segments", []) or []:
            if not isinstance(segment_plan, dict):
                continue
            for item in segment_plan.get("items", []) or []:
                if isinstance(item, dict):
                    items.append(item)
    return items


def _iter_plan_items_with_section(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return all plan items with their owning planned section type."""
    items: list[tuple[str, dict[str, Any]]] = []
    section_plans = plan.get("section_plans", [])
    if not isinstance(section_plans, list):
        return items

    for section_plan in section_plans:
        if not isinstance(section_plan, dict):
            continue
        section_type = section_plan.get("section_type")
        if not isinstance(section_type, str):
            continue
        for item in section_plan.get("items", []) or []:
            if isinstance(item, dict):
                items.append((section_type, item))
        for segment_plan in section_plan.get("segments", []) or []:
            if not isinstance(segment_plan, dict):
                continue
            for item in segment_plan.get("items", []) or []:
                if isinstance(item, dict):
                    items.append((section_type, item))
    return items


def validate_plan(plan: dict[str, Any]) -> list[str]:
    """Validate planning-pass output before planless stubs are injected."""
    issues: list[str] = []
    if not isinstance(plan, dict):
        return ["Plan must be a JSON object"]

    items_with_section = _iter_plan_items_with_section(plan)
    item_ids = [
        item.get("item_id")
        for _, item in items_with_section
        if isinstance(item.get("item_id"), str)
    ]
    counts = Counter(item_ids)
    duplicate_item_ids = sorted(item_id for item_id, count in counts.items() if count > 1)
    if duplicate_item_ids:
        issues.append(f"Duplicate plan item_id values: {duplicate_item_ids}")

    # Root is a document-level signal: exactly one method item across the whole
    # plan is the paper's primary method. Checking per method section_plan made
    # over-split plans (several method sections) fail once per section, so collect
    # all method items together instead.
    method_items = [item for section_type, item in items_with_section if section_type == "method"]
    if method_items:
        root_items = [item for item in method_items if item.get("is_root") is True]
        if not root_items:
            issues.append("method plan has no root item (is_root: true)")
        elif len(root_items) > 1:
            issues.append("method plan has multiple root items (is_root: true)")

    item_sections = {
        item_id: section_type
        for section_type, item in items_with_section
        if isinstance((item_id := item.get("item_id")), str)
    }
    known_item_ids = set(item_sections)

    for section_type, item in items_with_section:
        item_id = item.get("item_id")
        label = item_id if isinstance(item_id, str) else "<missing-id>"
        if not isinstance(item_id, str) or not ID_RE.match(item_id):
            issues.append(f"Plan item has invalid item_id: {item_id}")
        else:
            allowed_prefixes = PLAN_ITEM_PREFIXES_BY_SECTION.get(section_type)
            if allowed_prefixes and not item_id.startswith(allowed_prefixes):
                issues.append(
                    f"Plan item {item_id} has invalid prefix for {section_type}: "
                    f"expected one of {list(allowed_prefixes)}"
                )

        if "is_root" in item and not isinstance(item.get("is_root"), bool):
            issues.append(f"Plan item {label} is_root must be a boolean when present")
        if section_type != "method" and item.get("is_root") is True:
            issues.append(f"Plan item {label} is_root is only valid for method items")

        relations = item.get("relations")
        if not isinstance(relations, list):
            issues.append(f"Plan item {label} relations must be a list")
            continue

        allowed_relations = PLAN_RELATIONS_BY_SECTION.get(section_type)
        for relation in relations:
            if not isinstance(relation, dict):
                issues.append(f"Plan item {label} relation must be an object")
                continue
            relation_type = relation.get("type")
            target_id = relation.get("target_id")
            if allowed_relations is not None and relation_type not in allowed_relations:
                issues.append(
                    f"Plan item {label} relation {relation_type} is invalid for {section_type}"
                )
            if not isinstance(target_id, str) or target_id not in known_item_ids:
                issues.append(f"Plan item {label} relation target_id is unknown: {target_id}")
                continue
            if relation_type == "evaluates":
                target_section = item_sections.get(target_id)
                if target_section != "method" or not target_id.startswith("mth:"):
                    issues.append(
                        f"Plan item {label} evaluates target must be a method item: {target_id}"
                    )

    return issues


def _collapse_exact_duplicate_plan_items(plan: dict[str, Any]) -> None:
    """Drop verbatim-duplicate plan items in place, merging their relation hints.

    A planner sometimes emits the same item twice (identical item_id, description,
    priority, and source_scope). Suffixing the second to `_2` would manufacture a
    phantom must-item the extractor cannot satisfy with a distinct unit, which then
    surfaces as a spurious uncovered item and breaks the covers_entries trace. Such
    an exact repeat is unambiguously a slip, so keep the first and drop the rest.
    Same-id items whose content differs are left for the `_2` pass, since they may
    be genuinely distinct targets that merely collided on an id.
    """
    seen: dict[str, dict[str, Any]] = {}

    def signature(item: dict[str, Any]) -> tuple[Any, ...]:
        scope = item.get("source_scope")
        scope_key = tuple(scope) if isinstance(scope, list) else scope
        return (item.get("description"), item.get("priority"), scope_key)

    def dedup_items(items: list[Any]) -> list[Any]:
        kept: list[Any] = []
        for item in items:
            item_id = item.get("item_id") if isinstance(item, dict) else None
            if not isinstance(item_id, str):
                kept.append(item)
                continue
            prior = seen.get(item_id)
            if prior is not None and signature(prior) == signature(item):
                prior_relations = prior.setdefault("relations", [])
                if isinstance(prior_relations, list):
                    for relation in item.get("relations", []) or []:
                        if relation not in prior_relations:
                            prior_relations.append(relation)
                continue
            seen.setdefault(item_id, item)
            kept.append(item)
        return kept

    for section_plan in plan.get("section_plans", []) or []:
        if not isinstance(section_plan, dict):
            continue
        if isinstance(section_plan.get("items"), list):
            section_plan["items"] = dedup_items(section_plan["items"])
        for segment in section_plan.get("segments", []) or []:
            if isinstance(segment, dict) and isinstance(segment.get("items"), list):
                segment["items"] = dedup_items(segment["items"])


def normalize_planning_item_ids(plan: dict[str, Any]) -> dict[str, Any]:
    """Repair section-obvious plan ID problems before strict validation."""
    normalized = copy.deepcopy(plan)
    renames: dict[str, str] = {}

    for section_type, item in _iter_plan_items_with_section(normalized):
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or ":" not in item_id:
            continue
        allowed_prefixes = PLAN_ITEM_PREFIXES_BY_SECTION.get(section_type)
        if not allowed_prefixes or item_id.startswith(allowed_prefixes):
            continue

        _, slug = item_id.split(":", 1)
        if section_type == "method":
            new_id = f"mth:{slug}"
        else:
            continue

        if ID_RE.match(new_id):
            item["item_id"] = new_id
            renames[item_id] = new_id

    for _, item in _iter_plan_items_with_section(normalized):
        relations = item.get("relations")
        if not isinstance(relations, list):
            continue
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            target_id = relation.get("target_id")
            if isinstance(target_id, str) and target_id in renames:
                relation["target_id"] = renames[target_id]

    # Collapse verbatim repeats before suffixing, so only genuinely distinct same-id
    # items become `_2` and accidental duplicates never reach covers_entries.
    _collapse_exact_duplicate_plan_items(normalized)

    used_ids: set[str] = set()
    for _, item in _iter_plan_items_with_section(normalized):
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not ID_RE.match(item_id):
            continue
        if item_id not in used_ids:
            used_ids.add(item_id)
            continue

        prefix, slug = item_id.split(":", 1)
        index = 2
        new_id = f"{prefix}:{slug}_{index}"
        while new_id in used_ids:
            index += 1
            new_id = f"{prefix}:{slug}_{index}"
        item["item_id"] = new_id
        used_ids.add(new_id)

    item_sections = {
        item_id: section_type
        for section_type, item in _iter_plan_items_with_section(normalized)
        if isinstance((item_id := item.get("item_id")), str)
    }
    known_item_ids = set(item_sections)

    for section_type, item in _iter_plan_items_with_section(normalized):
        relations = item.get("relations")
        if not isinstance(relations, list):
            continue
        allowed_relations = PLAN_RELATIONS_BY_SECTION.get(section_type)
        kept_relations: list[Any] = []
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            relation_type = relation.get("type")
            target_id = relation.get("target_id")
            if allowed_relations is not None and relation_type not in allowed_relations:
                continue
            if not isinstance(target_id, str) or target_id not in known_item_ids:
                continue
            if relation_type == "evaluates":
                target_section = item_sections.get(target_id)
                if target_section != "method" or not target_id.startswith("mth:"):
                    continue
            kept_relations.append(relation)
        item["relations"] = kept_relations

    # Backfill a single document-level root method. `is_root` is consumed only as a
    # soft default downstream, yet its absence is a hard planning failure, so repair
    # it here: pick the first must-priority method item (else the first method item)
    # when none is marked, and demote extras when several are.
    method_items = [
        item for section_type, item in _iter_plan_items_with_section(normalized)
        if section_type == "method"
    ]
    if method_items:
        roots = [item for item in method_items if item.get("is_root") is True]
        if not roots:
            chosen = next(
                (item for item in method_items if item.get("priority") == "must"),
                method_items[0],
            )
            chosen["is_root"] = True
        elif len(roots) > 1:
            for extra in roots[1:]:
                extra["is_root"] = False

    return normalized


def build_planless_stubs(plan: dict[str, Any]) -> dict[str, Any]:
    """Inject empty extraction plans for sections that do not need item-level planning."""
    normalized = copy.deepcopy(plan)
    section_plans = normalized.get("section_plans")
    if not isinstance(section_plans, list):
        section_plans = []

    active_plans = [
        section_plan
        for section_plan in section_plans
        if isinstance(section_plan, dict) and section_plan.get("section_type") in PLANNED_SECTION_TYPES
    ]
    active_by_type = {
        section_type: [
            section_plan
            for section_plan in active_plans
            if section_plan.get("section_type") == section_type
        ]
        for section_type in PLANNED_SECTION_TYPES
    }

    def stub(section_type: str) -> dict[str, Any]:
        return {
            "section_type": section_type,
            "segment_count": 1,
            "anchor_hint": f"Planless {section_type} extraction",
            "items": [],
            "segments": [],
        }

    ordered_plans: list[dict[str, Any]] = []
    for section_type in SECTION_ORDER:
        if section_type in PLANLESS_SECTION_TYPES:
            ordered_plans.append(stub(section_type))
        else:
            ordered_plans.extend(active_by_type.get(section_type, []))
    normalized["section_plans"] = ordered_plans
    return normalized


def expand_section_plans(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand section_plans into one dict per planned extraction section."""
    expanded: list[dict[str, Any]] = []
    section_plans = plan.get("section_plans", [])
    if not isinstance(section_plans, list):
        return expanded

    for section_index, section_plan in enumerate(section_plans):
        if not isinstance(section_plan, dict):
            continue
        section_type = section_plan.get("section_type")
        segment_count = section_plan.get("segment_count", 1)
        segments = section_plan.get("segments")
        if isinstance(segments, list) and segments:
            for segment_index, segment_plan in enumerate(segments):
                if not isinstance(segment_plan, dict):
                    continue
                expanded.append(
                    {
                        "section_type": section_type,
                        "segment_count": 1,
                        "segment_label": segment_plan.get("segment_label")
                        or f"{section_type}_{segment_index}",
                        "anchor_hint": segment_plan.get("anchor_hint", ""),
                        "items": segment_plan.get("items", []) or [],
                        "source_section_index": section_index,
                        "source_segment_index": segment_index,
                    }
                )
        elif segment_count:
            expanded.append(
                {
                    "section_type": section_type,
                    "segment_count": 1,
                    "anchor_hint": section_plan.get("anchor_hint", ""),
                    "items": section_plan.get("items", []) or [],
                    "source_section_index": section_index,
                    "source_segment_index": 0,
                }
            )
    return expanded


def build_id_registry(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a flat registry of planned item IDs for permitted cross-section references."""
    registry: list[dict[str, Any]] = []
    for section_plan in expand_section_plans(plan):
        section_type = section_plan.get("section_type")
        if section_type in PLANLESS_SECTION_TYPES:
            continue
        segment_label = section_plan.get("segment_label")
        for item in section_plan.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            entry: dict[str, Any] = {
                "item_id": item.get("item_id"),
                "section": section_type,
                "description": item.get("description", ""),
            }
            if segment_label:
                entry["segment_label"] = segment_label
            relations = item.get("relations")
            if relations:
                entry["relations"] = relations
            if item.get("is_root") is True:
                entry["role"] = "root"
            registry.append(entry)
    return registry


def _requested_section_numbers(items: list[dict[str, Any]]) -> set[int]:
    requested: set[int] = set()
    for item in items:
        for raw_ref in item.get("source_scope", []) or []:
            for match in re.finditer(r"§\s*(\d+)|\[(?:§)?(\d+)\]", str(raw_ref)):
                requested.add(int(match.group(1) or match.group(2)))
            if not re.search(r"§|\[", str(raw_ref)):
                for match in re.finditer(r"\b(\d+)\b", str(raw_ref)):
                    requested.add(int(match.group(1)))
    return requested


def _build_excerpt_from_items(
    paper_content: str,
    items: list[dict[str, Any]],
    context_window: int = 1,
) -> tuple[str, list[str], list[str]]:
    sections = parse_sections(paper_content)
    if not sections:
        return paper_content, [], []

    requested = _requested_section_numbers(items)
    if not requested:
        return paper_content, sorted(sections, key=lambda x: int(x)), []

    available = {int(key) for key in sections}
    expanded: set[int] = set()
    for section_num in requested:
        for offset in range(-context_window, context_window + 1):
            candidate = section_num + offset
            if candidate in available:
                expanded.add(candidate)

    included_nums = sorted(expanded)
    omitted_nums = sorted(requested - available)

    preamble = paper_content[: min((m.start() for m in SECTION_MARKER_RE.finditer(paper_content)), default=0)].strip()
    parts = [preamble] if preamble else []
    parts.extend(sections[str(num)] for num in included_nums)
    return "\n\n".join(parts), [f"§{num}" for num in included_nums], [f"§{num}" for num in omitted_nums]


def build_section_excerpt(
    paper_content: str,
    section_plan: dict[str, Any],
    context_window: int = 1,
) -> tuple[str, list[str], list[str]]:
    """Build an excerpt for one expanded section plan."""
    items = [item for item in section_plan.get("items", []) or [] if isinstance(item, dict)]
    return _build_excerpt_from_items(paper_content, items, context_window=context_window)


def render_section_user_prompt(
    paper_content: str,
    id_registry: list[dict[str, Any]],
    section_plan: dict[str, Any],
    section_module: str,
    spine_summary: dict[str, Any] | None = None,
) -> str:
    """Render the cache-friendly section extraction user prompt."""
    id_registry_json = json.dumps(id_registry, ensure_ascii=False, indent=2)
    section_plan_json = json.dumps(section_plan, ensure_ascii=False, indent=2)
    spine_summary_json = json.dumps(spine_summary, ensure_ascii=False, indent=2) if spine_summary else None
    section_guidance = section_module.strip() or "No additional section guidance."
    spine_summary_block = (
        f"\n\n<spine_summary>\n{spine_summary_json}\n</spine_summary>"
        if spine_summary_json
        else ""
    )

    return f"""Extract the following section from the paper.

<paper>
{paper_content}
</paper>
{spine_summary_block}

<id_registry>
{id_registry_json}
</id_registry>

<section_focus>
{section_guidance}
</section_focus>

<section_plan>
{section_plan_json}
</section_plan>

Extract units and links for ONLY the planned section above.
- Place only the fields defined by your section schema in each unit.
- Place each unit in the array matching its type.
- Define units that belong to this section.
- In `links`, use only unit IDs defined in this section.
- Use `id_registry` only when a Metric needs an external `subject_id` or a Claim needs external `target_ids`.
- When `id_registry` contains a method entry with `"role": "root"`, prefer it for paper-level Claim `target_ids` and as the default Experiment Metric `subject_id`.
- For non-empty plans, use the full paper only as source context and do not extract units outside the current `section_plan`.
- For empty planless sections, extract the current section role freely using `section_focus` and `spine_summary`.

Output a single JSON object with key: section.""".strip()


def build_prompt_cache_key(model: str, paper_content: str) -> str:
    """Build a stable OpenAI prompt cache routing key for one paper/model pair."""
    safe_model = re.sub(r"[^A-Za-z0-9_.:-]+", "_", model).strip("_") or "model"
    digest = sha256(paper_content.encode("utf-8")).hexdigest()[:16]
    return f"section-ir:{safe_model}:{digest}"


def _slugify_doc_id(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:30].strip("_") or "paper"


def build_document_unit(plan: dict[str, Any], paper_content: str) -> dict[str, Any]:
    """Build a deterministic Document unit from the paper preamble."""
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
        "provenance": [],
    }


def build_extraction_notes(
    plan: dict[str, Any],
    section_results: list[dict[str, Any]],
    sections_included: list[str] | None = None,
    sections_omitted: list[str] | None = None,
) -> dict[str, Any]:
    """Build final extraction notes for assembled parallel output."""
    all_covered: set[str] = set()
    sections_used: set[str] = set()
    for result in section_results:
        section = result.get("section", {}) if isinstance(result, dict) else {}
        if not isinstance(section, dict):
            continue
        if isinstance(section.get("section_type"), str):
            sections_used.add(section["section_type"])
        for entry_id in section.get("covers_entries", []) or []:
            if isinstance(entry_id, str):
                all_covered.add(entry_id)

    items = iter_plan_items(plan)
    must_items = {
        item.get("item_id")
        for item in items
        if item.get("priority") == "must" and isinstance(item.get("item_id"), str)
    }
    notes: dict[str, Any] = {
        "ir_version": "section-ir-0.6",
        "sections_used": [section for section in ["context", "claim", "method", "experiment", "analysis"] if section in sections_used],
        "uncertain_assignments": [],
        "skipped_spans": [],
        "input_mode": "parallel_section_extraction",
        "uncovered_items": [
            {"item_id": item_id, "reason": "not covered by any section"}
            for item_id in sorted(must_items - all_covered)
        ],
        "plan_coverage": {
            "must_covered": len(must_items & all_covered),
            "must_total": len(must_items),
        },
    }
    if sections_included is not None:
        notes["sections_included"] = sections_included
    if sections_omitted is not None:
        notes["sections_omitted"] = sections_omitted
    return notes


def assemble_extraction(
    plan: dict[str, Any],
    section_results: list[dict[str, Any]],
    paper_content: str,
    sections_included: list[str] | None = None,
    sections_omitted: list[str] | None = None,
) -> dict[str, Any]:
    """Merge section extraction results into final section-IR output."""
    sections: list[dict[str, Any]] = []
    for result in section_results:
        if not isinstance(result, dict) or not isinstance(result.get("section"), dict):
            raise ValueError(f"Invalid section extraction result: {result}")
        section = result["section"]
        flattened_units = _flatten_typed_arrays(section)
        if any(key in section for key in TYPED_ARRAY_KEYS):
            section["units"] = flattened_units
            for key in TYPED_ARRAY_KEYS:
                section.pop(key, None)
        sections.append(section)

    _canonicalize_section_id_aliases(sections)
    assembly_warnings = []
    assembly_warnings.extend(_dedup_entities(sections))
    assembly_warnings.extend(_dedup_unit_ids(sections))
    _reconcile_method_components(sections)
    assembly_warnings.extend(_reconcile_metric_subjects(sections, plan))
    assembly_warnings.extend(_reconcile_analysis_metric_subjects(sections))
    assembly_warnings.extend(_drop_empty_sections(sections))
    assembly_warnings.extend(_normalize_provenance_markers(sections))
    assembly_warnings.extend(_drop_invalid_links(sections))
    assembly_warnings.extend(_repair_section_anchors(sections))
    assembly_warnings.extend(_reconcile_covers_entries(sections))

    # Build notes from the final, repaired sections so coverage reflects assembly
    # mutations (dropped sections, pruned covers_entries) rather than raw model output.
    extraction_notes = build_extraction_notes(
        plan,
        [{"section": section} for section in sections],
        sections_included=sections_included,
        sections_omitted=sections_omitted,
    )
    if assembly_warnings:
        uncertain = extraction_notes.setdefault("uncertain_assignments", [])
        if isinstance(uncertain, list):
            uncertain.extend(assembly_warnings)

    return {
        "document": build_document_unit(plan, paper_content),
        "sections": sections,
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


def run_planning(
    client: Any,
    model: str,
    paper_content: str,
    temperature: float = 0.0,
    max_tokens: int = 16_384,
) -> dict[str, Any]:
    """Run phase 1 section planning and return parsed JSON."""
    system_prompt, user_template = load_prompt(PLANNING_PROMPT_PATH)
    user_prompt = user_template.replace("{{paper_content}}", paper_content)
    planning_schema = load_planning_schema()
    resp_fmt = build_response_format(planning_schema, name="planning_output", model=model)
    raw = _call_llm(client, model, system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens, response_format=resp_fmt)
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
    raw = _call_llm(client, model, system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens, response_format=resp_fmt)
    return _parse_llm_json(raw)


def _normalize_name(text: Any) -> str:
    """Lowercase a name to space-joined alphanumeric tokens for tolerant matching."""
    if not isinstance(text, str):
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def reconcile_reference_units(
    references: dict[str, Any] | None,
    extraction: dict[str, Any],
) -> list[str]:
    """Link each reference's `provides_name` to a spine Method/Entity unit by name.

    The references pass runs before section extraction, so it never knows the final
    unit IDs and always emits `provides_unit_ids: []`. Once the spine exists, match
    each reference's `provides_name` against Method/Entity unit names to materialize
    the bibliography->spine "uses" edge. Conservative by design: links only on a
    unique normalized-name match; an ambiguous (multi-unit) or unmatched name stays
    `[]`. Mutates `references` in place and returns warnings for the audit trail.
    """
    warnings: list[str] = []
    if not isinstance(references, dict):
        return warnings
    ref_list = references.get("references")
    if not isinstance(ref_list, list):
        return warnings

    name_to_ids: dict[str, list[str]] = {}
    for section in extraction.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict) or unit.get("type") not in {"Method", "Entity"}:
                continue
            key = _normalize_name(unit.get("name"))
            uid = unit.get("id")
            if key and isinstance(uid, str) and uid not in name_to_ids.setdefault(key, []):
                name_to_ids[key].append(uid)

    for ref in ref_list:
        if not isinstance(ref, dict):
            continue
        relation = ref.get("relation")
        if not isinstance(relation, dict):
            continue
        relation["provides_unit_ids"] = []  # model cannot know unit IDs; Python owns this field
        key = _normalize_name(relation.get("provides_name"))
        if not key:
            continue
        matches = name_to_ids.get(key, [])
        if len(matches) == 1:
            relation["provides_unit_ids"] = list(matches)
            warnings.append(
                f"Linked reference {ref.get('id')!r} provides_name "
                f"{relation.get('provides_name')!r} to unit {matches[0]}"
            )
    return warnings


def _validate_section_result_shape(result: dict[str, Any], section_plan: dict[str, Any]) -> None:
    if not isinstance(result.get("section"), dict):
        raise ValueError("Section extraction result missing section object")
    section = result["section"]
    if section.get("section_type") != section_plan.get("section_type"):
        raise ValueError(
            "Section extraction result section_type mismatch: "
            f"{section.get('section_type')} != {section_plan.get('section_type')}"
        )
    typed_array_keys = [key for key in TYPED_ARRAY_KEYS if key in section]
    if not typed_array_keys:
        raise ValueError("Section extraction result missing typed unit arrays")
    for key in typed_array_keys:
        if not isinstance(section.get(key), list):
            raise ValueError(f"Section extraction result {key} must be a list")


def extract_single_section_sync(
    client: Any,
    model: str,
    plan: dict[str, Any],
    section_plan: dict[str, Any],
    paper_content: str,
    id_registry: list[dict[str, Any]] | None = None,
    temperature: float = 0.0,
    max_tokens: int = DEFAULT_SECTION_MAX_TOKENS,
    max_retries: int = MAX_SECTION_RETRIES,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
) -> dict[str, Any]:
    """Extract one planned section using the synchronous LLM client."""
    system_prompt, _ = load_prompt(SECTION_EXTRACTION_PROMPT_PATH)
    section_type = section_plan.get("section_type", "")

    section_module = load_section_module(section_type)
    if id_registry is None:
        id_registry = build_id_registry(plan)
    user_prompt = render_section_user_prompt(
        paper_content,
        id_registry=id_registry,
        section_plan=section_plan,
        section_module=section_module,
        spine_summary=plan.get("spine_summary") if isinstance(plan.get("spine_summary"), dict) else None,
    )

    section_schema = load_section_schema(section_type)
    resp_fmt = build_response_format(section_schema, name=f"{section_type}_section", model=model)

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
            _validate_section_result_shape(result, section_plan)
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= max_retries:
                break
    raise RuntimeError(
        "Section extraction failed after retries for "
        f"{section_plan.get('section_type')}:{section_plan.get('segment_label', section_plan.get('anchor_hint', 'unknown'))}"
    ) from last_error


def _sort_section_refs(refs: set[str]) -> list[str]:
    def sort_key(ref: str) -> tuple[int, str]:
        match = re.search(r"\d+", ref)
        return (int(match.group(0)) if match else 10**9, ref)

    return sorted(refs, key=sort_key)


def run_parallel_extraction_sync(
    client: Any,
    model: str,
    paper_content: str,
    plan: dict[str, Any],
    max_workers: int = DEFAULT_PARALLEL_MAX_WORKERS,
    temperature: float = 0.0,
    max_tokens: int = DEFAULT_SECTION_MAX_TOKENS,
    context_window: int = 1,
    prompt_cache_key: str | None = None,
    prompt_cache_retention: str | None = None,
) -> dict[str, Any]:
    """Run per-section extraction calls with a shared prompt prefix and assemble final output."""
    section_plans = expand_section_plans(plan)
    if not section_plans:
        raise ValueError("Plan contains no sections to extract")

    _ = context_window  # Retained for API compatibility; full-paper section prompts do not slice excerpts.
    parsed_sections = parse_sections(paper_content)
    sections_included = _sort_section_refs({f"§{section_id}" for section_id in parsed_sections})
    sections_omitted: list[str] = []
    id_registry = build_id_registry(plan)
    cache_key = prompt_cache_key if prompt_cache_key is not None else build_prompt_cache_key(model, paper_content)

    ordered_results: list[dict[str, Any] | None] = [None] * len(section_plans)
    try:
        ordered_results[0] = extract_single_section_sync(
            client,
            model,
            plan,
            section_plans[0],
            paper_content,
            id_registry=id_registry,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=MAX_SECTION_RETRIES,
            prompt_cache_key=cache_key,
            prompt_cache_retention=prompt_cache_retention,
        )
    except Exception as exc:
        label = section_plans[0].get("segment_label") or section_plans[0].get("anchor_hint") or 0
        raise RuntimeError(f"Parallel extraction failed for section {label}") from exc

    remaining = list(enumerate(section_plans[1:], start=1))
    if remaining:
        worker_count = max(1, min(max_workers, len(remaining)))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {
                pool.submit(
                    extract_single_section_sync,
                    client,
                    model,
                    plan,
                    section_plan,
                    paper_content,
                    id_registry=id_registry,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=MAX_SECTION_RETRIES,
                    prompt_cache_key=cache_key,
                    prompt_cache_retention=prompt_cache_retention,
                ): (index, section_plan)
                for index, section_plan in remaining
            }
            for future in as_completed(futures):
                index, section_plan = futures[future]
                try:
                    ordered_results[index] = future.result()
                except Exception as exc:
                    label = section_plan.get("segment_label") or section_plan.get("anchor_hint") or index
                    raise RuntimeError(f"Parallel extraction failed for section {label}") from exc

    section_results = [result for result in ordered_results if result is not None]
    return assemble_extraction(
        plan,
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
    """Run planning + metadata + references in parallel, then section extraction, then validation."""
    pipeline_warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        planning_future = executor.submit(
            run_planning, client, model, paper_content, temperature=temperature, max_tokens=max_tokens
        )
        metadata_future = executor.submit(
            run_metadata_extraction, client, model, paper_content, temperature=temperature, max_tokens=max_tokens
        )
        references_future = executor.submit(
            run_references_extraction, client, model, paper_content, temperature=temperature, max_tokens=max_tokens
        )
        raw_plan = planning_future.result()
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

    normalized_plan = normalize_planning_item_ids(raw_plan)
    plan_issues = validate_plan(normalized_plan)
    if plan_issues:
        details = "\n- ".join(plan_issues)
        raise ValueError(f"Planning validation failed:\n- {details}")
    plan = build_planless_stubs(normalized_plan)
    extraction = run_parallel_extraction_sync(
        client,
        model,
        paper_content,
        plan,
        max_workers=max_workers,
        temperature=temperature,
        max_tokens=section_max_tokens,
        prompt_cache_key=prompt_cache_key,
        prompt_cache_retention=prompt_cache_retention,
    )
    if references is not None:
        pipeline_warnings.extend(reconcile_reference_units(references, extraction))
    validation_issues = validate_section_ir(extraction, plan=plan)
    result = {
        "plan": plan,
        "extraction": extraction,
        "metadata": metadata,
        "references": references,
        "validation_issues": validation_issues,
        "pipeline_warnings": pipeline_warnings,
    }

    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / f"{paper_id}_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
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
        if not isinstance(marker, dict):
            issues.append(f"Unit {uid} provenance[{index}] must be an object")
            continue
        source_kind = marker.get("source_kind")
        if source_kind not in SOURCE_KINDS:
            issues.append(f"Unit {uid} provenance[{index}] has invalid source_kind: {source_kind}")
        source = marker.get("source")
        if not isinstance(source, list) or not source:
            issues.append(f"Unit {uid} provenance[{index}] source must be a non-empty list")
        else:
            for item in source:
                if not isinstance(item, str) or not PROVENANCE_SOURCE_RE.match(item):
                    issues.append(f"provenance source '{item}' does not match §N format")


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
        polarity = unit.get("polarity")
        if "polarity" in unit and polarity not in POLARITIES:
            issues.append(f"Claim {uid} has invalid polarity: {polarity}")
        novelty = unit.get("novelty")
        if "novelty" in unit and novelty not in NOVELTIES:
            issues.append(f"Claim {uid} has invalid novelty: {novelty}")
        epistemic_status = unit.get("epistemic_status")
        if "epistemic_status" in unit and epistemic_status not in EPISTEMIC_STATUSES:
            issues.append(f"Claim {uid} has invalid epistemic_status: {epistemic_status}")
        target_ids = unit.get("target_ids")
        if target_ids is not None:
            if not isinstance(target_ids, list):
                issues.append(f"Claim {uid} target_ids must be a list")
            else:
                for target_id in target_ids:
                    target_unit = unit_index.get(target_id)
                    if target_unit is None:
                        issues.append(f"Claim {uid} has unknown target_id: {target_id}")
                    elif target_unit.get("type") not in {"Method", "Entity"}:
                        issues.append(
                            f"Claim {uid} target_id {target_id} points to {target_unit.get('type')}"
                        )
    elif utype == "Context":
        for key in ("context_kind", "description"):
            if not unit.get(key):
                issues.append(f"Context {uid} missing {key}")
        if unit.get("context_kind") not in CONTEXT_KINDS:
            issues.append(f"Context {uid} has invalid context_kind: {unit.get('context_kind')}")
    elif utype == "Condition":
        for key in ("condition_kind", "description"):
            if not unit.get(key):
                issues.append(f"Condition {uid} missing {key}")
        if unit.get("condition_kind") not in CONDITION_KINDS:
            issues.append(f"Condition {uid} has invalid condition_kind: {unit.get('condition_kind')}")
    elif utype == "Metric":
        for key in ("name", "unit", "subject_id"):
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
        if unit.get("context_ids") is None:
            issues.append(f"Metric {uid} missing context_ids")
        subject_id = unit.get("subject_id")
        if subject_id and subject_id not in unit_index:
            issues.append(f"Metric {uid} has unknown subject_id: {subject_id}")
        elif subject_id and unit_index[subject_id].get("type") != "Method":
            issues.append(f"Metric {uid} subject_id {subject_id} points to {unit_index[subject_id].get('type')}")
        context_ids = unit.get("context_ids")
        if not isinstance(context_ids, list):
            issues.append(f"Metric {uid} context_ids must be a list")
        else:
            section_type = unit_sections.get(uid)
            if section_type == "experiment":
                if not context_ids:
                    issues.append(f"Experiment Metric {uid} must have non-empty context_ids")
                for context_id in context_ids:
                    context_unit = unit_index.get(context_id)
                    if context_unit is None:
                        issues.append(f"Metric {uid} has unknown context_id: {context_id}")
                    elif context_id not in local_ids:
                        issues.append(
                            f"Experiment Metric {uid} context_id must be section-local: {context_id}"
                        )
                    elif context_unit.get("type") != "Condition":
                        issues.append(
                            f"Experiment Metric {uid} context_id {context_id} must point to a local Condition"
                        )
            elif section_type == "analysis":
                if context_ids != []:
                    issues.append(f"Analysis Metric {uid} must have empty context_ids")
            else:
                for context_id in context_ids:
                    context_unit = unit_index.get(context_id)
                    if context_unit is None:
                        issues.append(f"Metric {uid} has unknown context_id: {context_id}")
                    elif context_unit.get("type") not in ("Context", "Condition"):
                        issues.append(f"Metric {uid} context_id {context_id} points to {context_unit.get('type')}")
        evaluated_on = unit.get("evaluated_on")
        if evaluated_on is not None:
            if not isinstance(evaluated_on, list):
                issues.append(f"Metric {uid} evaluated_on must be a list")
            else:
                for entity_id in evaluated_on:
                    entity_unit = unit_index.get(entity_id)
                    if entity_unit is None:
                        issues.append(f"Metric {uid} has unknown evaluated_on id: {entity_id}")
                    elif entity_id not in local_ids:
                        issues.append(f"Metric {uid} evaluated_on id must be section-local: {entity_id}")
                    elif entity_unit.get("type") != "Entity":
                        issues.append(
                            f"Metric {uid} evaluated_on id {entity_id} must point to a local Entity"
                        )
                    elif entity_unit.get("entity_class") not in {"dataset", "benchmark"}:
                        issues.append(
                            f"Metric {uid} evaluated_on id {entity_id} must be a dataset or benchmark Entity"
                        )
        comparison_direction = unit.get("comparison_direction")
        if "comparison_direction" in unit and comparison_direction not in COMPARISON_DIRECTIONS:
            issues.append(f"Metric {uid} has invalid comparison_direction: {comparison_direction}")
        value_type = unit.get("value_type")
        if "value_type" in unit and value_type not in VALUE_TYPES:
            issues.append(f"Metric {uid} has invalid value_type: {value_type}")


def _validate_link(
    link: dict[str, Any],
    unit_index: dict[str, dict[str, Any]],
    issues: list[str],
) -> None:
    if not isinstance(link, dict):
        issues.append("link must be an object")
        return

    source_id = link.get("source_id")
    target_id = link.get("target_id")
    relation = link.get("relation")
    source_unit = unit_index.get(source_id)
    target_unit = unit_index.get(target_id)

    if source_unit is None:
        issues.append(f"link has unknown source_id: {source_id}")
    if target_unit is None:
        issues.append(f"link has unknown target_id: {target_id}")

    matrix = LINK_MATRIX.get(relation)
    if matrix is None:
        issues.append(f"link has invalid relation: {relation}")
        return

    allowed_sources, allowed_targets = matrix
    if source_unit is not None and source_unit.get("type") not in allowed_sources:
        issues.append(
            f"link {source_id} -[{relation}]-> {target_id} has invalid source type: "
            f"{source_unit.get('type')}"
        )
    if target_unit is not None and target_unit.get("type") not in allowed_targets:
        issues.append(
            f"link {source_id} -[{relation}]-> {target_id} has invalid target type: "
            f"{target_unit.get('type')}"
        )


def validate_section_ir(extraction: dict[str, Any], plan: dict[str, Any] | None = None) -> list[str]:
    """Validate section-IR output against the section-plan contract."""
    issues: list[str] = []
    if not isinstance(extraction, dict):
        return ["Extraction must be a JSON object"]

    required_top = {"document", "sections", "extraction_notes"}
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

    all_links: list[dict[str, Any]] = []
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
                if (
                    section_type == "experiment"
                    and unit.get("type") == "Entity"
                    and unit.get("entity_class") not in {"dataset", "benchmark"}
                ):
                    issues.append(
                        f"Experiment Entity {unit.get('id', '<missing-id>')} has invalid entity_class "
                        f"for experiment section: {unit.get('entity_class')}"
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

        links = section.get("links", [])
        if not isinstance(links, list):
            issues.append(f"Section {s_index} links must be a list")
            continue
        for link in links:
            _validate_link(link, unit_index, issues)
            if isinstance(link, dict):
                source_id = link.get("source_id")
                target_id = link.get("target_id")
                if source_id not in section_unit_ids[s_index] or target_id not in section_unit_ids[s_index]:
                    issues.append(
                        f"Section {s_index} link must be section-local: "
                        f"{source_id} -[{link.get('relation')}]-> {target_id}"
                    )
                all_links.append(link)

    incoming_argumentative = {
        link.get("target_id")
        for link in all_links
        if isinstance(link, dict) and link.get("relation") in ARGUMENTATIVE_INCOMING
    }
    for uid, unit in unit_index.items():
        if unit.get("type") == "Claim":
            status = unit.get("epistemic_status")
            if (
                status != "established_fact"
                and unit_sections.get(uid) not in {"claim", "analysis"}
                and uid not in incoming_argumentative
            ):
                issues.append(f"Claim {uid} lacks an incoming argumentative link")

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
        if notes.get("input_mode") not in {
            "full_paper",
            "parallel_section_extraction",
        }:
            issues.append(f"extraction_notes has invalid input_mode: {notes.get('input_mode')}")
        sections_used = notes.get("sections_used", [])
        if isinstance(sections_used, list):
            invalid_sections = [st for st in sections_used if st not in SECTION_TYPES]
            if invalid_sections:
                issues.append(f"extraction_notes.sections_used has invalid values: {invalid_sections}")

    if plan is not None:
        _validate_plan_trace(plan, covered_entries, unit_index, notes, issues)

    return issues


def _validate_plan_trace(
    plan: dict[str, Any],
    covered_entries: set[str],
    unit_index: dict[str, dict[str, Any]],
    notes: dict[str, Any],
    issues: list[str],
) -> None:
    section_plans = plan.get("section_plans", [])
    if not isinstance(section_plans, list):
        issues.append("plan.section_plans must be a list")
        return

    items = iter_plan_items(plan)
    item_ids_list = [item.get("item_id") for item in items if isinstance(item.get("item_id"), str)]
    item_ids = set(item_ids_list)
    duplicate_item_ids = sorted({item_id for item_id in item_ids_list if item_ids_list.count(item_id) > 1})
    if duplicate_item_ids:
        issues.append(f"Duplicate plan item_id values: {duplicate_item_ids}")
    for item in items:
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not ID_RE.match(item_id):
            issues.append(f"Plan item has invalid item_id: {item_id}")
        if item.get("priority") not in {"must", "should"}:
            issues.append(f"Plan item {item_id or '<missing-id>'} has invalid priority: {item.get('priority')}")
        source_scope = item.get("source_scope")
        if not isinstance(source_scope, list) or not source_scope:
            issues.append(f"Plan item {item_id or '<missing-id>'} must have non-empty source_scope")

    must_item_ids = {
        item.get("item_id")
        for item in items
        if item.get("priority") == "must" and isinstance(item.get("item_id"), str)
    }

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

    unknown_covered = sorted(covered_entries - item_ids)
    if unknown_covered:
        issues.append(f"covers_entries references unknown plan items: {unknown_covered}")
    unknown_uncovered = sorted(uncovered_items - item_ids)
    if unknown_uncovered:
        issues.append(f"uncovered_items references unknown plan items: {unknown_uncovered}")

    for entry_id in sorted(covered_entries):
        if entry_id not in unit_index and entry_id not in uncovered_items:
            issues.append(f"covers_entries claims '{entry_id}' but no unit with this ID exists")

    missing_must = sorted(must_item_ids - covered_entries - uncovered_items)
    if missing_must:
        issues.append(f"must plan items neither covered nor declared uncovered: {missing_must}")

    coverage = notes.get("plan_coverage", {})
    if isinstance(coverage, dict):
        expected_covered = len(must_item_ids & covered_entries)
        expected_total = len(must_item_ids)
        if coverage.get("must_covered") != expected_covered:
            issues.append(
                "plan_coverage.must_covered does not match covers_entries: "
                f"{coverage.get('must_covered')} != {expected_covered}"
            )
        if coverage.get("must_total") != expected_total:
            issues.append(
                "plan_coverage.must_total does not match plan: "
                f"{coverage.get('must_total')} != {expected_total}"
            )
    else:
        issues.append("extraction_notes.plan_coverage must be an object")
