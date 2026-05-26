#!/usr/bin/env python3
"""Render section-IR extraction into an interactive HTML page.

Supports three input modes:
  1. Single extraction JSON:  python render_extraction.py paper4_extraction.json
  2. With sidecars:           python render_extraction.py paper4_extraction.json --metadata m.json --references r.json
  3. Production output dir:   python render_extraction.py ./output/paper4/
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path
from typing import Any

SECTION_ORDER = ["context", "claim", "method", "evidence"]
SECTION_COLORS = {
    "context": "#6b7280",
    "claim": "#ef4444",
    "method": "#3b82f6",
    "evidence": "#22c55e",
}
SECTION_LABELS = {
    "context": "Context & Background",
    "claim": "Claims & Contributions",
    "method": "Method",
    "evidence": "Evidence (Experiments & Analysis)",
}
TYPE_SHAPES = {
    "Claim": "diamond",
    "Metric": "square",
    "Method": "hexagon",
    "Entity": "dot",
    "Context": "star",
    "Setting": "triangleDown",
    "Document": "database",
}
RESOURCE_ICONS = {
    "code": "&#128187;",
    "paper": "&#128196;",
    "data": "&#128202;",
    "demo": "&#127912;",
    "model": "&#129302;",
}


# --- Data loading ---

def load_pipeline_data(
    path: Path,
    metadata_path: Path | None = None,
    references_path: Path | None = None,
) -> dict[str, Any]:
    """Load extraction + optional metadata/references from various input formats."""
    if path.is_dir():
        return _load_from_directory(path)

    extraction = json.loads(path.read_text(encoding="utf-8"))

    metadata = None
    if metadata_path and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        candidate = path.with_name(path.stem.replace("_extraction", "_metadata") + ".json")
        if candidate.exists():
            metadata = json.loads(candidate.read_text(encoding="utf-8"))

    references = None
    if references_path and references_path.exists():
        references = json.loads(references_path.read_text(encoding="utf-8"))
    else:
        candidate = path.with_name(path.stem.replace("_extraction", "_references") + ".json")
        if candidate.exists():
            references = json.loads(candidate.read_text(encoding="utf-8"))

    return {"extraction": extraction, "metadata": metadata, "references": references}


def _load_from_directory(dir_path: Path) -> dict[str, Any]:
    """Load from a production output directory structure."""
    extraction_path = dir_path / "06_extraction.json"
    if not extraction_path.exists():
        candidates = list(dir_path.glob("*_extraction.json"))
        if candidates:
            extraction_path = candidates[0]
        else:
            raise FileNotFoundError(f"No extraction JSON found in {dir_path}")

    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))

    metadata = None
    meta_path = dir_path / "02_metadata.json"
    if not meta_path.exists():
        candidates = list(dir_path.glob("*_metadata.json"))
        meta_path = candidates[0] if candidates else None
    if meta_path and meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    references = None
    ref_path = dir_path / "03_references.json"
    if not ref_path.exists():
        candidates = list(dir_path.glob("*_references.json"))
        ref_path = candidates[0] if candidates else None
    if ref_path and ref_path.exists():
        references = json.loads(ref_path.read_text(encoding="utf-8"))

    return {"extraction": extraction, "metadata": metadata, "references": references}


# --- Index helpers ---

def build_unit_index(data: dict) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    doc = data.get("document")
    if doc:
        idx[doc["id"]] = doc
    for section in data.get("sections", []):
        anchor = section.get("anchor")
        if anchor:
            idx[anchor["id"]] = anchor
        for u in section.get("units", []):
            idx[u["id"]] = u
    return idx


def build_unit_section_map(data: dict) -> dict[str, str]:
    unit_section: dict[str, str] = {}
    for section in data.get("sections", []):
        st = section.get("section_type", "context")
        anchor_id = section.get("anchor_id")
        if anchor_id:
            unit_section.setdefault(anchor_id, st)
        legacy_anchor = section.get("anchor")
        if legacy_anchor:
            unit_section.setdefault(legacy_anchor.get("id", ""), st)
        for unit in section.get("units", []):
            unit_section.setdefault(unit.get("id", ""), st)
    return unit_section


def collect_all_links(data: dict) -> list[dict]:
    """Return the global relation edge list (section-ir-0.7 top-level `relations`)."""
    relations = data.get("relations", [])
    return [lk for lk in relations if isinstance(lk, dict)]


def build_metric_subjects(data: dict) -> dict[str, list[str]]:
    """Map each Metric id to every Method it evaluates (global `evaluates` relations)."""
    subjects: dict[str, list[str]] = {}
    for lk in data.get("relations", []):
        if isinstance(lk, dict) and lk.get("relation") == "evaluates":
            src, tgt = lk.get("source_id"), lk.get("target_id")
            if isinstance(src, str) and isinstance(tgt, str) and tgt not in subjects.get(src, []):
                subjects.setdefault(src, []).append(tgt)
    return subjects


def build_metric_datasets(data: dict) -> dict[str, list[str]]:
    """Map each Metric id to the dataset/benchmark Entities it was measured on (`measured_on`)."""
    out: dict[str, list[str]] = {}
    for lk in data.get("relations", []):
        if isinstance(lk, dict) and lk.get("relation") == "measured_on":
            src, tgt = lk.get("source_id"), lk.get("target_id")
            if isinstance(src, str) and isinstance(tgt, str) and tgt not in out.get(src, []):
                out.setdefault(src, []).append(tgt)
    return out


# Method-role rank → render order (contribution first, baselines last)
METHOD_ROLE_RANK = {"contribution": 0, "component": 1, "other": 2, "baseline": 3}
METHOD_ROLE_LABELS = {"contribution": "CONTRIBUTION", "component": "COMPONENT", "baseline": "BASELINE"}


def classify_methods(data: dict, unit_index: dict[str, dict]) -> dict[str, str]:
    """Derive each Method's role from the global edges (units no longer carry `role`):
      - contribution: the `part_of` root (a target that is never a source); else the method anchor.
      - component:    a `part_of` source.
      - baseline:     an endpoint of a `compares_to` edge that is not the contribution.
      - other:        a Method with no structural edge (e.g. a standalone optimizer).
    """
    methods = {uid for uid, u in unit_index.items() if u.get("type") == "Method"}
    part_src: set[str] = set()
    part_tgt: set[str] = set()
    compares: set[str] = set()
    for lk in data.get("relations", []):
        rel, s, t = lk.get("relation"), lk.get("source_id"), lk.get("target_id")
        if rel == "part_of":
            part_src.add(s)
            part_tgt.add(t)
        elif rel == "compares_to":
            compares.update((s, t))

    roots = [m for m in methods if m in part_tgt and m not in part_src]
    contribution = roots[0] if roots else None
    if contribution is None:
        for s in data.get("sections", []):
            if s.get("section_type") == "method" and s.get("anchor_id") in methods:
                contribution = s.get("anchor_id")
                break

    roles: dict[str, str] = {}
    for m in methods:
        if m == contribution:
            roles[m] = "contribution"
        elif m in part_src:
            roles[m] = "component"
        elif m in compares:
            roles[m] = "baseline"
        else:
            roles[m] = "other"
    return roles


def _norm(s: str) -> str:
    """Lowercase alphanumeric-only key for fuzzy name matching."""
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def group_sections_by_type(data: dict) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {s: [] for s in SECTION_ORDER}
    for section in data.get("sections", []):
        st = section.get("section_type", "context")
        groups.setdefault(st, []).append(section)
    return groups


# --- Graph builders ---

def build_spine_graph(
    data: dict,
    unit_index: dict[str, dict],
    unit_section: dict[str, str],
    all_links: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Build the overview spine graph — anchor nodes connected by argumentative flow."""
    # Collect anchors grouped by section type (preserving order within same type)
    anchors_by_section: dict[str, list[str]] = {st: [] for st in SECTION_ORDER}
    for section in data.get("sections", []):
        st = section.get("section_type", "context")
        aid = section.get("anchor_id")
        if aid and aid not in anchors_by_section.get(st, []):
            anchors_by_section.setdefault(st, []).append(aid)
        legacy = section.get("anchor")
        if legacy:
            lid = legacy.get("id", "")
            if lid and lid not in anchors_by_section.get(st, []):
                anchors_by_section.setdefault(st, []).append(lid)

    anchor_ids: set[str] = set()
    for ids in anchors_by_section.values():
        anchor_ids.update(ids)

    section_type_order = {st: i for i, st in enumerate(SECTION_ORDER)}

    nodes = []
    for aid in anchor_ids:
        unit = unit_index.get(aid)
        if not unit or unit.get("type") == "Document":
            continue
        st = unit_section.get(aid, "context")
        label = unit.get("name") or unit.get("statement") or unit.get("description") or aid
        if len(label) > 50:
            label = label[:47] + "..."
        nodes.append({
            "id": aid,
            "label": label,
            "color": SECTION_COLORS.get(st, "#999"),
            "shape": TYPE_SHAPES.get(unit.get("type", ""), "dot"),
            "title": f"{unit.get('type', '')} | {SECTION_LABELS.get(st, st)}",
            "level": section_type_order.get(st, 2),
            "size": 22,
        })

    edges = []
    edge_set: set[tuple[str, str]] = set()

    # Structural flow edges: connect last anchor of each section to first anchor of next
    ordered_sections = [st for st in SECTION_ORDER if anchors_by_section.get(st)]
    for i in range(len(ordered_sections) - 1):
        src_section = ordered_sections[i]
        tgt_section = ordered_sections[i + 1]
        src_anchors = anchors_by_section[src_section]
        tgt_anchors = anchors_by_section[tgt_section]
        # Connect all anchors of current section to all anchors of next section
        # (for most papers this is 1-to-1 or 1-to-2)
        for src_id in src_anchors:
            for tgt_id in tgt_anchors:
                if (src_id, tgt_id) not in edge_set:
                    edge_set.add((src_id, tgt_id))
                    edges.append({
                        "from": src_id,
                        "to": tgt_id,
                        "arrows": "to",
                        "dashes": True,
                        "width": 1.5,
                        "color": {"color": "#475569", "opacity": 0.6},
                    })

    # Within same section type: connect anchors if multiple exist
    for st, aids in anchors_by_section.items():
        for i in range(len(aids) - 1):
            if (aids[i], aids[i + 1]) not in edge_set:
                edge_set.add((aids[i], aids[i + 1]))
                edges.append({
                    "from": aids[i],
                    "to": aids[i + 1],
                    "arrows": "to",
                    "color": {"color": SECTION_COLORS.get(st, "#666"), "opacity": 0.7},
                })

    # Explicit links between anchor nodes (override dashed with solid)
    for lk in all_links:
        src, tgt = lk.get("source_id", ""), lk.get("target_id", "")
        if src in anchor_ids and tgt in anchor_ids and (src, tgt) not in edge_set:
            edge_set.add((src, tgt))
            edges.append({
                "from": src,
                "to": tgt,
                "label": lk.get("relation", ""),
                "arrows": "to",
                "color": {"color": "#94a3b8", "opacity": 0.9},
            })

    return nodes, edges


def build_section_graph(
    section_type: str,
    sections: list[dict],
    unit_index: dict[str, dict],
    all_links: list[dict],
) -> tuple[list[dict], list[dict]] | None:
    """Build a local graph for a section group. Returns None if too trivial.

    Edges are the global relations whose endpoints both fall inside this section group.
    """
    local_ids: set[str] = set()

    for section in sections:
        aid = section.get("anchor_id")
        if aid:
            local_ids.add(aid)
        for u in section.get("units", []):
            local_ids.add(u.get("id", ""))

    links = [
        lk
        for lk in all_links
        if lk.get("source_id") in local_ids and lk.get("target_id") in local_ids
    ]

    if len(local_ids) < 3 or len(links) < 1:
        return None

    color = SECTION_COLORS.get(section_type, "#999")
    nodes = []
    for uid in local_ids:
        unit = unit_index.get(uid)
        if not unit:
            continue
        utype = unit.get("type", "")
        label = unit.get("name") or unit.get("statement") or unit.get("description") or uid
        if len(label) > 35:
            label = label[:32] + "..."
        is_anchor = any(s.get("anchor_id") == uid for s in sections)
        nodes.append({
            "id": uid,
            "label": label,
            "color": color if not is_anchor else "#f59e0b",
            "shape": TYPE_SHAPES.get(utype, "dot"),
            "title": f"{utype}: {uid}",
            "size": 18 if is_anchor else 14,
            "borderWidth": 2 if is_anchor else 1,
        })

    edges = []
    for lk in links:
        src, tgt = lk.get("source_id", ""), lk.get("target_id", "")
        if src in local_ids and tgt in local_ids:
            edges.append({
                "from": src,
                "to": tgt,
                "label": lk.get("relation", ""),
                "arrows": "to",
                "color": {"color": "#64748b", "opacity": 0.8},
            })

    return nodes, edges


# --- HTML renderers ---

def render_provenance(prov_list: list) -> str:
    if not prov_list:
        return ""
    parts = [
        f'<span class="prov-badge">{escape(marker)}</span>'
        for marker in prov_list
        if isinstance(marker, str)
    ]
    return " ".join(parts)


def render_payload_table(payload: dict) -> str:
    """Fallback for unrecognized leftover fields (keeps the renderer forward-compatible)."""
    rows = ""
    for k, v in payload.items():
        if isinstance(v, (dict, list)):
            val_html = f"<pre>{escape(json.dumps(v, ensure_ascii=False, indent=1))}</pre>"
        else:
            val_html = escape(str(v))
        rows += f"<tr><td class='payload-key'>{escape(k)}</td><td>{val_html}</td></tr>"
    return f"<table class='payload-table'>{rows}</table>" if rows else ""


def render_symbols(symbols: list | None) -> str:
    rows = "".join(
        f"<tr><td class='sym'>{escape(str(s.get('symbol', '')))}</td>"
        f"<td>{escape(str(s.get('description', '')))}</td></tr>"
        for s in (symbols or [])
        if isinstance(s, dict) and s.get("symbol")
    )
    return f"<table class='symbol-table'>{rows}</table>" if rows else ""


def render_formula_block(name: str, expr: str, desc: str, symbols: list | None) -> str:
    name_html = f"<div class='formula-name'>{escape(name)}</div>" if name else ""
    desc_html = f"<div class='formula-desc'>{escape(desc)}</div>" if desc else ""
    return (
        f"<div class='formula-block'>{name_html}"
        f"<div class='formula-expr'>{escape(expr)}</div>{desc_html}"
        f"{render_symbols(symbols)}</div>"
    )


def render_formulas(formulas: list | None) -> str:
    blocks = "".join(
        render_formula_block(f.get("name", ""), f.get("expression", ""), "", f.get("symbols", []))
        for f in (formulas or [])
        if isinstance(f, dict) and f.get("expression")
    )
    return f"<div class='field-group'><div class='field-label'>Formulas</div>{blocks}</div>" if blocks else ""


def render_objective(obj: dict | None) -> str:
    if not isinstance(obj, dict) or not obj.get("expression"):
        return ""
    block = render_formula_block("", obj["expression"], obj.get("description", ""), obj.get("symbols", []))
    return f"<div class='field-group'><div class='field-label'>Objective</div>{block}</div>"


def render_chips(label: str, items: list | None) -> str:
    chips = "".join(f"<span class='chip'>{escape(str(i))}</span>" for i in (items or []))
    return (
        f"<div class='field-group'><div class='field-label'>{escape(label)}</div>"
        f"<div class='chips'>{chips}</div></div>"
        if chips else ""
    )


def render_scores(scores: list | None, baseline_keys: set[str]) -> str:
    """Render a Metric's scores[] as a comparison table, tagging baseline rows."""
    rows = ""
    for s in (scores or []):
        if not isinstance(s, dict):
            continue
        variant = str(s.get("variant", ""))
        nv = _norm(variant)
        is_base = bool(nv) and any(nv in b or b in nv for b in baseline_keys)
        tag = " <span class='base-tag'>baseline</span>" if is_base else ""
        var = str(s.get("variance", "") or "")
        rows += (
            f"<tr class='score-row{' baseline-row' if is_base else ''}'>"
            f"<td>{escape(variant)}{tag}</td>"
            f"<td class='score-val'>{escape(str(s.get('value', '')))}</td>"
            f"<td class='score-var'>{escape(var) if var else '&mdash;'}</td></tr>"
        )
    if not rows:
        return ""
    return (
        "<table class='score-table'><thead><tr><th>System</th><th>Value</th><th>&plusmn;</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


META_FIELDS = {"id", "type", "provenance"}
TAG_FIELDS = ("method_kind", "entity_class", "claim_kind", "context_kind", "comparison_direction", "unit")
PROSE_FIELDS = ("description", "implementation_notes")
# Fields rendered by dedicated logic (or consumed as the card label); never echoed as leftover.
RICH_FIELDS = {"formulas", "objective_function", "inputs", "outputs", "scores", "setting_ids", "statement", "name"}


def render_unit_card(
    unit: dict,
    unit_index: dict,
    *,
    is_anchor: bool = False,
    section_type: str = "context",
    method_roles: dict[str, str] | None = None,
    baseline_keys: set[str] | None = None,
) -> str:
    method_roles = method_roles or {}
    baseline_keys = baseline_keys or set()
    uid = unit.get("id", "?")
    utype = unit.get("type", "?")
    color = SECTION_COLORS.get(section_type, "#999")
    prov_html = render_provenance(unit.get("provenance", []))
    anchor_cls = " anchor-unit" if is_anchor else ""

    # Label: prefer statement, then name; description is the label only when neither exists.
    label, label_field = "", ""
    for cand in ("statement", "name", "description"):
        if unit.get(cand):
            label, label_field = unit[cand], cand
            break
    if not label:
        label = unit.get("summary") or ""
    used_label_fields = {label_field} if label_field else set()
    disp_label = label[:160] + "..." if isinstance(label, str) and len(label) > 160 else label

    role = method_roles.get(uid) if utype == "Method" else None
    role_badge = (
        f"<span class='role-badge role-{role}'>{METHOD_ROLE_LABELS[role]}</span>"
        if role in METHOD_ROLE_LABELS else ""
    )

    tag_html = "".join(f"<span class='tag'>{escape(str(unit[f]))}</span>" for f in TAG_FIELDS if unit.get(f))
    tags_html = f"<div class='tags'>{tag_html}</div>" if tag_html else ""

    # Expandable detail: prose, then type-specific rich blocks, then any leftover fields.
    prose = ""
    for f in PROSE_FIELDS:
        if unit.get(f) and f not in used_label_fields:
            prose += (
                f"<div class='field-group'><div class='field-label'>{escape(f.replace('_', ' '))}</div>"
                f"<div class='field-prose'>{escape(str(unit[f]))}</div></div>"
            )

    rich = ""
    if utype == "Method":
        rich += render_chips("Inputs", unit.get("inputs"))
        rich += render_chips("Outputs", unit.get("outputs"))
        rich += render_formulas(unit.get("formulas"))
        rich += render_objective(unit.get("objective_function"))
    elif utype == "Metric":
        scores_html = render_scores(unit.get("scores"), baseline_keys)
        if scores_html:
            rich += f"<div class='field-group'><div class='field-label'>Scores</div>{scores_html}</div>"
        if unit.get("setting_ids"):
            setting_names = [
                (unit_index.get(s, {}).get("description") or unit_index.get(s, {}).get("name") or s)
                for s in unit["setting_ids"]
            ]
            rich += render_chips("Settings", setting_names)

    handled = META_FIELDS | RICH_FIELDS | set(TAG_FIELDS) | set(PROSE_FIELDS) | used_label_fields
    leftover = {k: v for k, v in unit.items() if k not in handled and v not in (None, "", [], {})}
    leftover_html = render_payload_table(leftover)

    detail_html = prose + rich + leftover_html

    return f"""
    <div class="unit-card{anchor_cls}" data-unit-id="{escape(uid)}">
      <div class="unit-header" onclick="this.parentElement.classList.toggle('expanded')">
        <span class="unit-type-badge" style="background:{color}">{escape(utype)}</span>
        {role_badge}
        <span class="unit-id">{escape(uid)}</span>
        {'<span class="anchor-badge">ANCHOR</span>' if is_anchor else ''}
        <span class="unit-chevron">&#9654;</span>
      </div>
      <div class="unit-label">{escape(disp_label)}</div>
      {tags_html}
      <div class="unit-prov">{prov_html}</div>
      <div class="unit-detail">{detail_html}</div>
    </div>"""


def render_metric_table(
    sections: list[dict],
    unit_index: dict,
    subject_by_metric: dict[str, list[str]],
    dataset_by_metric: dict[str, list[str]],
    method_roles: dict[str, str],
    baseline_keys: set[str],
) -> str:
    """Render each Metric as a block: name + unit/direction + evaluated method + dataset, then a
    full scores comparison table (baseline rows tagged)."""
    metrics: list[dict] = []
    seen: set[str] = set()
    for section in sections:
        for u in section.get("units", []):
            if u.get("type") == "Metric" and u.get("id") not in seen:
                seen.add(u.get("id"))
                metrics.append(u)
    if not metrics:
        return ""

    def name_of(uid: str) -> str:
        u = unit_index.get(uid, {})
        return u.get("name") or u.get("statement") or uid

    blocks = ""
    for m in metrics:
        mid = m.get("id", "")
        subj_ids = subject_by_metric.get(mid, [])
        head = next(
            (s for s in subj_ids if method_roles.get(s) == "contribution"),
            subj_ids[0] if subj_ids else "",
        )
        ds_names = [name_of(d) for d in dataset_by_metric.get(mid, [])]
        direction = m.get("comparison_direction", "")
        dir_icon = {"higher_is_better": "&#9650;", "lower_is_better": "&#9660;"}.get(direction, "")
        scores_html = render_scores(m.get("scores"), baseline_keys)

        meta_bits = ""
        if head:
            meta_bits += f"<span class='metric-meta'>evaluates <b>{escape(str(name_of(head)))}</b></span>"
        if ds_names:
            meta_bits += f"<span class='metric-meta'>on {escape(', '.join(str(d) for d in ds_names))}</span>"

        blocks += f"""
        <div class="metric-block">
          <div class="metric-block-head">
            <span class="metric-name">{escape(m.get('name', ''))}</span>
            <span class="metric-unit">{escape(str(m.get('unit', '')))} {dir_icon}</span>
            {meta_bits}
          </div>
          {scores_html}
        </div>"""

    return f'<div class="metrics-wrap">{blocks}</div>'


def render_metadata_panel(metadata: dict | None, doc: dict) -> str:
    title = ""
    authors_html = ""
    resources_html = ""

    if metadata:
        title = metadata.get("title", "") or doc.get("title", "Untitled")
        authors = metadata.get("authors", [])
        if authors:
            author_parts = []
            for a in authors:
                name = a.get("name", "")
                affils = a.get("affiliations", [])
                if affils:
                    author_parts.append(f"{escape(name)} <span class='affil'>({escape(', '.join(affils))})</span>")
                else:
                    author_parts.append(escape(name))
            authors_html = f'<div class="authors">{" &middot; ".join(author_parts)}</div>'

        resources = metadata.get("resources", [])
        if resources:
            res_parts = []
            for r in resources:
                rtype = r.get("type", "paper")
                url = r.get("url", "")
                icon = RESOURCE_ICONS.get(rtype, "&#128279;")
                if url:
                    res_parts.append(f'<a href="{escape(url)}" class="resource-link" target="_blank">{icon} {escape(rtype)}</a>')
            if res_parts:
                resources_html = f'<div class="resources">{" ".join(res_parts)}</div>'
    else:
        title = doc.get("title", "Untitled")

    return f"""
    <div class="paper-header">
      <h1>{escape(title)}</h1>
      {authors_html}
      {resources_html}
    </div>"""


def render_references_panel(references: dict | None) -> str:
    if not references:
        return ""
    refs = references.get("references", [])
    if not refs:
        return ""

    rows = ""
    for r in refs:
        rid = r.get("id", "")
        authors = r.get("authors", [])
        if len(authors) > 3:
            author_str = f"{authors[0]} et al."
        elif authors:
            author_str = ", ".join(authors)
        else:
            author_str = ""
        title = r.get("title", "")
        venue = r.get("venue", "")
        year = r.get("year", "")
        year_str = f", {year}" if year else ""
        venue_str = f" &mdash; {escape(venue)}{escape(str(year_str))}" if venue else ""

        rows += f'<div class="ref-entry"><span class="ref-id">[{escape(str(rid))}]</span> {escape(author_str)} <span class="ref-title">&ldquo;{escape(title)}&rdquo;</span>{venue_str}</div>\n'

    return f"""
    <div class="references-section">
      <div class="section-header" onclick="this.parentElement.classList.toggle('collapsed')">
        <span class="section-title">References ({len(refs)})</span>
        <span class="section-chevron">&#9660;</span>
      </div>
      <div class="section-body">
        {rows}
      </div>
    </div>"""


def render_section_card(
    section_type: str,
    sections: list[dict],
    unit_index: dict,
    unit_section: dict[str, str],
    graph_id: str,
    all_links: list[dict],
    subject_by_metric: dict[str, list[str]],
    dataset_by_metric: dict[str, list[str]],
    method_roles: dict[str, str],
    baseline_keys: set[str],
) -> str:
    color = SECTION_COLORS[section_type]
    label = SECTION_LABELS[section_type]

    # Gather units once, de-duplicated, tracking which are section anchors.
    seen_ids: set[str] = set()
    items: list[tuple[dict, bool]] = []
    for section in sections:
        anchor_id = section.get("anchor_id")
        anchor = unit_index.get(anchor_id) if anchor_id else section.get("anchor")
        if anchor and anchor.get("id") not in seen_ids:
            seen_ids.add(anchor.get("id"))
            items.append((anchor, True))
        for u in section.get("units", []):
            if u.get("id") in seen_ids:
                continue
            seen_ids.add(u.get("id"))
            items.append((u, False))

    count = len(items)

    # In evidence, Metrics are shown as comparison blocks rather than cards.
    card_items = [(u, a) for (u, a) in items if not (section_type == "evidence" and u.get("type") == "Metric")]

    # In method, order contribution -> components -> other -> baselines.
    if section_type == "method":
        card_items.sort(key=lambda ia: METHOD_ROLE_RANK.get(method_roles.get(ia[0].get("id"), "other"), 2))

    units_html = "".join(
        render_unit_card(
            u, unit_index, is_anchor=a, section_type=section_type,
            method_roles=method_roles, baseline_keys=baseline_keys,
        )
        for (u, a) in card_items
    )

    metric_html = (
        render_metric_table(sections, unit_index, subject_by_metric, dataset_by_metric, method_roles, baseline_keys)
        if section_type == "evidence" else ""
    )

    graph_data = build_section_graph(section_type, sections, unit_index, all_links)
    has_graph = graph_data is not None

    if has_graph:
        content_html = f"""
        <div class="section-content-grid">
          <div class="section-units">
            {metric_html}
            {units_html}
          </div>
          <div class="section-graph-panel">
            <div class="section-graph" id="{graph_id}"></div>
          </div>
        </div>"""
    else:
        content_html = f"""
        <div class="section-units-full">
          {metric_html}
          {units_html}
        </div>"""

    return f"""
    <div class="section-card" id="section-{section_type}">
      <div class="section-header" onclick="this.parentElement.classList.toggle('collapsed')" style="border-left: 4px solid {color}">
        <span class="section-color-dot" style="background:{color}"></span>
        <span class="section-title">{escape(label)}</span>
        <span class="section-count">{count} units in {len(sections)} section(s)</span>
        <span class="section-chevron">&#9660;</span>
      </div>
      <div class="section-body">
        {content_html}
      </div>
    </div>"""


# --- Main render ---

def render_html(pipeline_data: dict[str, Any]) -> str:
    data = pipeline_data["extraction"]
    metadata = pipeline_data.get("metadata")
    references = pipeline_data.get("references")

    unit_index = build_unit_index(data)
    unit_section = build_unit_section_map(data)
    all_links = collect_all_links(data)
    subject_by_metric = build_metric_subjects(data)
    dataset_by_metric = build_metric_datasets(data)
    method_roles = classify_methods(data, unit_index)
    baseline_keys = {
        _norm(unit_index.get(uid, {}).get("name", ""))
        for uid, role in method_roles.items() if role == "baseline"
    }
    baseline_keys.discard("")
    grouped = group_sections_by_type(data)

    doc = data.get("document", {})
    notes = data.get("extraction_notes", {})
    ir_version = notes.get("ir_version", "")

    # Stats
    total_units = sum(1 for uid, u in unit_index.items() if u.get("type") != "Document")
    total_sections = len(data.get("sections", []))
    total_links = len(all_links)
    plan_coverage = notes.get("plan_coverage", {})
    cov_value = f"{plan_coverage.get('must_covered', 0)}/{plan_coverage.get('must_total', 0)}" if isinstance(plan_coverage, dict) else "n/a"

    sections_used = notes.get("sections_used") or [s.get("section_type") for s in data.get("sections", [])]
    coverage_dots = ""
    for st in SECTION_ORDER:
        active = st in sections_used
        c = SECTION_COLORS[st]
        opacity = "1" if active else "0.2"
        coverage_dots += f'<span class="cov-dot" style="background:{c}; opacity:{opacity}" title="{st}"></span>'

    # Metadata panel
    header_html = render_metadata_panel(metadata, doc)

    # Spine graph
    spine_nodes, spine_edges = build_spine_graph(data, unit_index, unit_section, all_links)

    # Section cards with per-section graphs
    section_cards = ""
    section_graphs_js = ""
    for st in SECTION_ORDER:
        sections_for_type = grouped.get(st, [])
        graph_id = f"graph-{st}"
        if sections_for_type:
            section_cards += render_section_card(
                st, sections_for_type, unit_index, unit_section, graph_id, all_links,
                subject_by_metric, dataset_by_metric, method_roles, baseline_keys,
            )
            graph_data = build_section_graph(st, sections_for_type, unit_index, all_links)
            if graph_data:
                sg_nodes, sg_edges = graph_data
                section_graphs_js += f"""
                initSectionGraph('{graph_id}', {json.dumps(sg_nodes, ensure_ascii=False)}, {json.dumps(sg_edges, ensure_ascii=False)});
                """
        else:
            color = SECTION_COLORS[st]
            label = SECTION_LABELS[st]
            section_cards += f"""
            <div class="section-card empty-section" id="section-{st}">
              <div class="section-header" style="border-left: 4px solid {color}; opacity: 0.4">
                <span class="section-color-dot" style="background:{color}"></span>
                <span class="section-title">{escape(label)}</span>
                <span class="section-count">No data</span>
              </div>
            </div>"""

    # References panel
    references_html = render_references_panel(references)

    # Notes
    notes_html = ""
    for ua in notes.get("uncertain_assignments", []):
        notes_html += f"<li class='note-item'>{escape(str(ua))}</li>"
    for item in notes.get("uncovered_items", []):
        notes_html += f"<li class='note-item'>uncovered {escape(item.get('item_id', ''))}: {escape(item.get('reason', ''))}</li>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(doc.get('title', 'Extraction'))} — Section-IR View</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}

/* Header */
.paper-header {{ margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #1e293b; }}
.paper-header h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 8px; color: #f8fafc; }}
.authors {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 6px; line-height: 1.8; }}
.affil {{ font-size: 0.75rem; color: #64748b; }}
.resources {{ display: flex; gap: 10px; margin-top: 8px; flex-wrap: wrap; }}
.resource-link {{ font-size: 0.8rem; color: #3b82f6; text-decoration: none; padding: 3px 10px; background: #1e293b; border-radius: 4px; border: 1px solid #334155; }}
.resource-link:hover {{ background: #334155; }}

/* Stats */
.stats {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
.stat {{ background: #1e293b; border-radius: 8px; padding: 10px 14px; min-width: 100px; }}
.stat-value {{ font-size: 1.15rem; font-weight: 700; color: #f1f5f9; }}
.stat-label {{ font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
.coverage {{ display: flex; gap: 5px; align-items: center; margin-top: 4px; }}
.cov-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
.meta-tag {{ font-size: 0.75rem; color: #64748b; margin-top: 6px; }}

/* Spine graph */
.spine-section {{ background: #1e293b; border-radius: 8px; margin-bottom: 24px; overflow: hidden; }}
.spine-section h2 {{ padding: 12px 18px; font-size: 0.9rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #334155; }}
#spine-graph {{ width: 100%; height: 260px; }}
.spine-legend {{ display: flex; gap: 14px; padding: 8px 18px; flex-wrap: wrap; border-top: 1px solid #334155; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 0.72rem; color: #94a3b8; }}
.legend-dot {{ width: 9px; height: 9px; border-radius: 50%; }}

/* Section cards */
.section-card {{ background: #1e293b; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }}
.section-header {{ padding: 12px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; user-select: none; }}
.section-header:hover {{ background: #283548; }}
.section-color-dot {{ width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }}
.section-title {{ font-weight: 600; font-size: 0.95rem; flex: 1; }}
.section-count {{ font-size: 0.72rem; color: #94a3b8; }}
.section-chevron {{ font-size: 0.7rem; color: #64748b; transition: transform 0.2s; }}
.section-card.collapsed .section-body {{ display: none; }}
.section-card.collapsed .section-chevron {{ transform: rotate(-90deg); }}
.section-body {{ padding: 0 16px 16px; }}

/* Section grid layout */
.section-content-grid {{ display: grid; grid-template-columns: 1fr 320px; gap: 16px; }}
@media (max-width: 900px) {{ .section-content-grid {{ grid-template-columns: 1fr; }} }}
.section-units, .section-units-full {{ }}
.section-graph-panel {{ position: sticky; top: 16px; align-self: start; }}
.section-graph {{ width: 100%; height: 280px; background: #0f172a; border-radius: 6px; border: 1px solid #334155; }}

/* Unit cards */
.unit-card {{ background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; margin-top: 8px; transition: border-color 0.15s; }}
.unit-card:hover {{ border-color: #64748b; }}
.unit-card.anchor-unit {{ border-left: 3px solid #f59e0b; }}
.unit-card.highlighted {{ border-color: #f59e0b; box-shadow: 0 0 12px rgba(245,158,11,0.25); }}
.unit-header {{ display: flex; align-items: center; gap: 7px; cursor: pointer; user-select: none; }}
.unit-type-badge {{ font-size: 0.6rem; padding: 2px 5px; border-radius: 3px; color: #fff; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }}
.unit-id {{ font-size: 0.72rem; color: #64748b; font-family: monospace; }}
.anchor-badge {{ font-size: 0.58rem; background: #f59e0b; color: #000; padding: 1px 5px; border-radius: 3px; font-weight: 700; }}
.unit-chevron {{ margin-left: auto; font-size: 0.6rem; color: #475569; transition: transform 0.15s; }}
.unit-card.expanded .unit-chevron {{ transform: rotate(90deg); }}
.unit-label {{ font-size: 0.85rem; margin-top: 5px; color: #cbd5e1; }}
.unit-prov {{ margin-top: 4px; }}
.prov-badge {{ font-size: 0.62rem; background: #334155; color: #94a3b8; padding: 1px 5px; border-radius: 3px; margin-right: 3px; }}
.unit-detail {{ display: none; margin-top: 8px; }}
.unit-card.expanded .unit-detail {{ display: block; }}
.payload-table {{ width: 100%; font-size: 0.78rem; border-collapse: collapse; }}
.payload-table td {{ padding: 3px 7px; border-bottom: 1px solid #1e293b; vertical-align: top; }}
.payload-key {{ color: #94a3b8; white-space: nowrap; font-family: monospace; width: 110px; }}
.payload-table pre {{ margin: 0; font-size: 0.72rem; white-space: pre-wrap; color: #cbd5e1; }}

/* Metric blocks */
.metrics-wrap {{ margin: 8px 0 4px; display: flex; flex-direction: column; gap: 10px; }}
.metric-block {{ background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; }}
.metric-block-head {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }}
.metric-name {{ font-weight: 600; font-size: 0.9rem; color: #f1f5f9; }}
.metric-unit {{ font-size: 0.72rem; color: #22c55e; font-weight: 700; font-variant-numeric: tabular-nums; }}
.metric-meta {{ font-size: 0.72rem; color: #94a3b8; }}
.metric-meta b {{ color: #cbd5e1; font-weight: 600; }}

/* Score / comparison tables */
.score-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-top: 4px; }}
.score-table th {{ text-align: left; padding: 4px 8px; border-bottom: 1px solid #334155; color: #64748b; font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.04em; }}
.score-table td {{ padding: 4px 8px; border-bottom: 1px solid #1e293b; }}
.score-val {{ font-weight: 700; color: #22c55e; font-variant-numeric: tabular-nums; }}
.score-var {{ color: #64748b; font-variant-numeric: tabular-nums; }}
.score-row.baseline-row td {{ color: #94a3b8; }}
.score-row.baseline-row .score-val {{ color: #64748b; font-weight: 600; }}
.base-tag {{ font-size: 0.56rem; background: #334155; color: #94a3b8; padding: 1px 5px; border-radius: 3px; vertical-align: middle; text-transform: uppercase; letter-spacing: 0.04em; }}

/* Field groups (formulas, chips, prose) */
.field-group {{ margin-top: 8px; }}
.field-label {{ font-size: 0.62rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }}
.field-prose {{ font-size: 0.8rem; color: #cbd5e1; }}
.chips {{ display: flex; gap: 5px; flex-wrap: wrap; }}
.chip {{ font-size: 0.72rem; background: #1e293b; color: #cbd5e1; border: 1px solid #334155; padding: 2px 8px; border-radius: 10px; }}

/* Formula blocks */
.formula-block {{ background: #0b1220; border: 1px solid #334155; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }}
.formula-name {{ font-size: 0.68rem; color: #94a3b8; margin-bottom: 4px; }}
.formula-expr {{ font-family: 'SF Mono', 'Fira Code', Consolas, monospace; font-size: 0.82rem; color: #e2e8f0; white-space: pre-wrap; word-break: break-word; }}
.formula-desc {{ font-size: 0.74rem; color: #94a3b8; margin-top: 4px; }}
.symbol-table {{ margin-top: 6px; border-collapse: collapse; font-size: 0.74rem; }}
.symbol-table td {{ padding: 2px 8px 2px 0; vertical-align: top; color: #cbd5e1; }}
.symbol-table .sym {{ font-family: 'SF Mono', Consolas, monospace; color: #93c5fd; white-space: nowrap; }}

/* Tags & role badges */
.tags {{ display: flex; gap: 5px; flex-wrap: wrap; margin-top: 5px; }}
.tag {{ font-size: 0.62rem; background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 1px 7px; border-radius: 3px; }}
.role-badge {{ font-size: 0.56rem; font-weight: 700; padding: 1px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.04em; }}
.role-contribution {{ background: #f59e0b; color: #000; }}
.role-component {{ background: #1d4ed8; color: #dbeafe; }}
.role-baseline {{ background: #334155; color: #94a3b8; }}

/* References */
.references-section {{ background: #1e293b; border-radius: 8px; margin-top: 20px; overflow: hidden; }}
.references-section .section-header {{ padding: 12px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; user-select: none; }}
.references-section .section-header:hover {{ background: #283548; }}
.references-section.collapsed .section-body {{ display: none; }}
.references-section.collapsed .section-chevron {{ transform: rotate(-90deg); }}
.references-section .section-body {{ padding: 8px 16px 16px; max-height: 400px; overflow-y: auto; }}
.ref-entry {{ font-size: 0.78rem; color: #94a3b8; padding: 4px 0; border-bottom: 1px solid #0f172a; }}
.ref-id {{ color: #64748b; font-family: monospace; font-size: 0.7rem; margin-right: 6px; }}
.ref-title {{ color: #cbd5e1; }}

/* Notes */
.notes-section {{ margin-top: 20px; background: #1e293b; border-radius: 8px; padding: 14px 16px; }}
.notes-section h2 {{ font-size: 0.85rem; margin-bottom: 8px; color: #94a3b8; }}
.notes-section li {{ font-size: 0.78rem; color: #64748b; margin-bottom: 3px; padding-left: 6px; list-style: none; }}
.note-item::before {{ content: "\\2022  "; color: #475569; }}
</style>
</head>
<body>
<div class="container">
  {header_html}

  <div class="stats">
    <div class="stat"><div class="stat-value">{total_sections}</div><div class="stat-label">Sections</div></div>
    <div class="stat"><div class="stat-value">{total_units}</div><div class="stat-label">Units</div></div>
    <div class="stat"><div class="stat-value">{total_links}</div><div class="stat-label">Relations</div></div>
    <div class="stat"><div class="stat-value">{escape(cov_value)}</div><div class="stat-label">Must Coverage</div></div>
    <div class="stat">
      <div class="coverage">{coverage_dots}</div>
      <div class="stat-label">Section Coverage</div>
    </div>
  </div>
  <div class="meta-tag">{escape(ir_version)}</div>

  <div class="spine-section">
    <h2>Argumentative Spine</h2>
    <div id="spine-graph"></div>
    <div class="spine-legend">
      {''.join(f'<span class="legend-item"><span class="legend-dot" style="background:{c}"></span>{SECTION_LABELS[s]}</span>' for s, c in SECTION_COLORS.items())}
    </div>
  </div>

  {section_cards}

  {references_html}

  {'<div class="notes-section"><h2>Extraction Notes</h2><ul>' + notes_html + '</ul></div>' if notes_html else ''}
</div>

<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<script>
// Spine graph
const spineNodes = {json.dumps(spine_nodes, ensure_ascii=False)};
const spineEdges = {json.dumps(spine_edges, ensure_ascii=False)};

const spineContainer = document.getElementById('spine-graph');
if (spineContainer && spineNodes.length > 0) {{
  const spineData = {{
    nodes: new vis.DataSet(spineNodes),
    edges: new vis.DataSet(spineEdges)
  }};
  const spineOptions = {{
    layout: {{
      hierarchical: {{
        direction: 'LR',
        sortMethod: 'directed',
        levelSeparation: 200,
        nodeSpacing: 80,
      }}
    }},
    physics: false,
    nodes: {{
      font: {{ color: '#cbd5e1', size: 12, face: '-apple-system, sans-serif', multi: true }},
      borderWidth: 1,
      borderWidthSelected: 2,
    }},
    edges: {{
      font: {{ color: '#64748b', size: 9, strokeWidth: 0, face: '-apple-system, sans-serif' }},
      width: 1.5,
      smooth: {{ type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.4 }}
    }},
    interaction: {{ hover: true, zoomView: true, dragView: true }}
  }};
  const spineNetwork = new vis.Network(spineContainer, spineData, spineOptions);
  spineNetwork.on('click', function(params) {{
    if (params.nodes.length > 0) {{
      const el = document.querySelector(`[data-unit-id="${{params.nodes[0]}}"]`);
      if (el) {{
        el.classList.add('highlighted', 'expanded');
        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        setTimeout(() => el.classList.remove('highlighted'), 3000);
      }}
    }}
  }});
}}

// Section graphs
function initSectionGraph(containerId, nodes, edges) {{
  const container = document.getElementById(containerId);
  if (!container || nodes.length === 0) return;
  const data = {{
    nodes: new vis.DataSet(nodes),
    edges: new vis.DataSet(edges)
  }};
  const options = {{
    physics: {{
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {{ gravitationalConstant: -30, centralGravity: 0.01, springLength: 100, springConstant: 0.03, damping: 0.5 }},
      stabilization: {{ iterations: 150 }}
    }},
    nodes: {{
      font: {{ color: '#cbd5e1', size: 10, face: '-apple-system, sans-serif' }},
      borderWidth: 1,
    }},
    edges: {{
      font: {{ color: '#64748b', size: 8, strokeWidth: 0 }},
      width: 1,
      smooth: {{ type: 'cubicBezier', roundness: 0.3 }}
    }},
    interaction: {{ hover: true, zoomView: true, dragView: true }}
  }};
  const network = new vis.Network(container, data, options);
  network.on('click', function(params) {{
    document.querySelectorAll('.unit-card.highlighted').forEach(el => el.classList.remove('highlighted'));
    if (params.nodes.length > 0) {{
      const el = document.querySelector(`[data-unit-id="${{params.nodes[0]}}"]`);
      if (el) {{
        el.classList.add('highlighted', 'expanded');
        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        setTimeout(() => el.classList.remove('highlighted'), 3000);
      }}
    }}
  }});
}}

{section_graphs_js}

// Collapse references by default
document.querySelectorAll('.references-section').forEach(el => el.classList.add('collapsed'));
</script>
</body>
</html>"""


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Render section-IR extraction to interactive HTML",
    )
    parser.add_argument("input", type=Path, help="Extraction JSON file or production output directory")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path (default: auto)")
    parser.add_argument("--metadata", type=Path, default=None, help="Metadata JSON sidecar")
    parser.add_argument("--references", type=Path, default=None, help="References JSON sidecar")
    args = parser.parse_args()

    pipeline_data = load_pipeline_data(args.input, args.metadata, args.references)

    if args.output:
        output_path = args.output
    elif args.input.is_dir():
        output_path = args.input / "extraction.html"
    else:
        output_path = args.input.with_suffix(".html")

    html = render_html(pipeline_data)
    output_path.write_text(html, encoding="utf-8")
    print(f"Rendered: {output_path} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
