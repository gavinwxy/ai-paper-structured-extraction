#!/usr/bin/env python3
"""Render a section-IR (0.9) extraction into a single self-contained HTML page.

The page is organised around the scientific-discovery throughline the IR encodes:

    problem  --motivates-->  method (contribution)  <--about--  finding  --resolves-->  problem

Layout (no external dependencies, no CDN):
  * a sticky section nav,
  * a compact **discovery-arc** strip tracing problem -> contribution -> headline
    finding -> resolves (built from the real `motivates` / `about` / `resolves` edges),
  * the three sections (problem / method / evidence), each unit rendered as a card
    that shows **its own relations inline** as clickable pills (part_of, evaluates,
    compares_with, about, supports, motivates, resolves), and
  * a references appendix.

Interactivity (vanilla JS, embedded):
  * click any node (or relation pill / arc chip) to highlight every unit it links to,
  * collapsible sections, expandable unit detail, Esc to clear the highlight.

Input modes:
  1. Single extraction JSON:  python render_extraction.py 06_extraction.json
  2. With sidecars:           python render_extraction.py x_extraction.json --metadata m.json --references r.json
  3. Production output dir:    python render_extraction.py ./output/paper4/
"""

from __future__ import annotations

import argparse
import json
import re
import webbrowser
from collections import defaultdict
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

try:  # works both as a package import (tools.render_extraction) and as a script (cwd=tools/)
    from tools.reference_formatter import format_references_blob
except ImportError:
    from reference_formatter import format_references_blob

SECTION_ORDER = ["problem", "method", "evidence"]
SECTION_COLORS = {
    "problem": "#f59e0b",
    "method": "#3b82f6",
    "evidence": "#22c55e",
}
SECTION_LABELS = {
    "problem": "Problem",
    "method": "Method",
    "evidence": "Evidence",
}
SECTION_SUBTITLES = {
    "problem": "the research question",
    "method": "the technical apparatus",
    "evidence": "what was measured & what it means",
}
# Per-type badge colours (orthogonal to the section accent).
TYPE_COLORS = {
    "Problem": "#f59e0b",
    "Method": "#3b82f6",
    "ExperimentSetup": "#a855f7",
    "Measure": "#14b8a6",
    "Finding": "#22c55e",
    "Document": "#64748b",
}
RESOURCE_ICONS = {
    "code": "&#128187;",
    "paper": "&#128196;",
    "data": "&#128202;",
    "demo": "&#127912;",
    "model": "&#129302;",
}

# Human phrasing for each relation, from the source's view (out) and the target's view (in).
REL_OUT = {
    "part_of": "part of",
    "builds_on": "builds on",
    "uses": "uses",
    "assumes": "assumes",
    "co_contribution": "co-contribution with",
    "compares_to": "compared with",
    "evaluates": "evaluates",
    "about": "about",
    "supports": "supports",
    "motivates": "motivates",
    "resolves": "resolves",
}
REL_IN = {
    "part_of": "includes",
    "builds_on": "extended by",
    "uses": "used by",
    "assumes": "assumed by",
    "co_contribution": "co-contribution with",
    "compares_to": "compared with",
    "evaluates": "evaluated by",
    "about": "discussed by",
    "supports": "supported by",
    "motivates": "motivated by",
    "resolves": "resolved by",
}
# Accent colour per relation family (structural / dependency / evaluative / evidential / arc).
REL_COLOR = {
    "part_of": "#64748b",
    "co_contribution": "#64748b",
    "builds_on": "#3b82f6",
    "uses": "#3b82f6",
    "assumes": "#3b82f6",
    "compares_to": "#64748b",
    "evaluates": "#14b8a6",
    "about": "#22c55e",
    "supports": "#22c55e",
    "motivates": "#f59e0b",
    "resolves": "#f59e0b",
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
        candidates = list(dir_path.glob("*_extraction.json")) + list(dir_path.glob("*extraction*.json"))
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
    """id -> unit for every section unit. The Document is deliberately excluded: it is
    not rendered as a card, so any edge that touches it stays non-clickable (a dangling
    pill) instead of becoming a link that scrolls to nothing."""
    idx: dict[str, dict] = {}
    for section in data.get("sections") or []:
        for u in section.get("units") or []:
            if isinstance(u, dict) and u.get("id"):
                idx[u["id"]] = u
    return idx


def build_unit_section_map(data: dict) -> dict[str, str]:
    """id -> section_type, used to colour cross-section relation pills."""
    unit_section: dict[str, str] = {}
    for section in data.get("sections") or []:
        st = section.get("section_type", "problem")
        for unit in section.get("units") or []:
            if isinstance(unit, dict) and unit.get("id"):
                unit_section.setdefault(unit["id"], st)
    return unit_section


def build_edge_index(data: dict, unit_index: dict) -> tuple[dict, dict, dict]:
    """Build adjacency from the global `relations[]`:
      out_edges[id] = [(relation, target_id), ...]   (this unit is the source)
      in_edges[id]  = [(relation, source_id), ...]   (this unit is the target)
      neighbors[id] = set of connected ids that actually exist as units (for highlight)
    """
    out_edges: dict[str, list] = defaultdict(list)
    in_edges: dict[str, list] = defaultdict(list)
    neighbors: dict[str, set] = defaultdict(set)
    seen: set[tuple] = set()
    for e in data.get("relations") or []:
        if not isinstance(e, dict):
            continue
        rel = e.get("relation")
        s, t = e.get("source_id"), e.get("target_id")
        if not rel or not isinstance(s, str) or not isinstance(t, str):
            continue
        key = (rel, s, t)
        if key in seen:
            continue
        seen.add(key)
        out_edges[s].append((rel, t))
        in_edges[t].append((rel, s))
        if t in unit_index:
            neighbors[s].add(t)
        if s in unit_index:
            neighbors[t].add(s)
    return out_edges, in_edges, neighbors


def collect_all_links(data: dict) -> list[dict]:
    return [lk for lk in data.get("relations") or [] if isinstance(lk, dict)]


def build_metric_subjects(data: dict) -> dict[str, list[str]]:
    """Measure id -> every Method it `evaluates`."""
    subjects: dict[str, list[str]] = {}
    for lk in data.get("relations") or []:
        if isinstance(lk, dict) and lk.get("relation") == "evaluates":
            src, tgt = lk.get("source_id"), lk.get("target_id")
            if isinstance(src, str) and isinstance(tgt, str) and tgt not in subjects.get(src, []):
                subjects.setdefault(src, []).append(tgt)
    return subjects


def build_metric_datasets(data: dict, unit_index: dict[str, dict]) -> dict[str, list[str]]:
    """Measure id -> ExperimentSetup units it ran on (via score-row `setup_id` / `setup_ids`)."""
    out: dict[str, list[str]] = {}
    for section in data.get("sections") or []:
        for u in section.get("units") or []:
            if not isinstance(u, dict) or u.get("type") != "Measure":
                continue
            mid = u.get("id", "")
            if not mid:
                continue
            setup_ids: list[str] = []
            for s in u.get("scores", []) or []:
                if isinstance(s, dict) and isinstance(s.get("setup_id"), str) and s["setup_id"]:
                    setup_ids.append(s["setup_id"])
            for sid in u.get("setup_ids", []) or []:
                if isinstance(sid, str) and sid:
                    setup_ids.append(sid)
            for sid in setup_ids:
                if sid in unit_index and sid not in out.get(mid, []):
                    out.setdefault(mid, []).append(sid)
    return out


# Method-role render order (contribution first, baselines last). Accepts both the 0.9
# unit role names and the legacy edge-derived names.
METHOD_ROLE_RANK = {
    "contribution": 0, "component": 1, "builds_on": 2, "other": 2,
    "compared_against": 3, "baseline": 3,
}


def classify_methods(data: dict, unit_index: dict[str, dict]) -> dict[str, str]:
    """Best-effort Method role: prefer the unit's own 0.9 `role`, else derive from edges
    (contribution = part_of root; component = part_of source; baseline = compares_to endpoint)."""
    methods = {uid for uid, u in unit_index.items() if u.get("type") == "Method"}
    part_src: set[str] = set()
    part_tgt: set[str] = set()
    compares: set[str] = set()
    for lk in data.get("relations") or []:
        if not isinstance(lk, dict):
            continue
        rel, s, t = lk.get("relation"), lk.get("source_id"), lk.get("target_id")
        if rel == "part_of":
            part_src.add(s)
            part_tgt.add(t)
        elif rel == "compares_to":
            compares.update((s, t))

    roles: dict[str, str] = {}
    derived_contribution = None
    roots = [m for m in methods if m in part_tgt and m not in part_src]
    if roots:
        derived_contribution = roots[0]

    for m in methods:
        own = (unit_index.get(m) or {}).get("role")
        if own:
            roles[m] = own
        elif m == derived_contribution:
            roles[m] = "contribution"
        elif m in part_src:
            roles[m] = "component"
        elif m in compares:
            roles[m] = "compared_against"
        else:
            roles[m] = "other"
    # Guarantee a single contribution for arc/ordering even if none was tagged.
    if methods and not any(r == "contribution" for r in roles.values()):
        roles[derived_contribution or next(iter(methods))] = "contribution"
    return roles


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _unit_label(unit: dict | None, limit: int = 70) -> str:
    """Concise human label for a unit: name > statement > description > id."""
    if not unit:
        return ""
    s = unit.get("name") or unit.get("statement") or unit.get("description") or unit.get("id") or ""
    s = str(s).strip()
    return (s[: limit - 1] + "…") if len(s) > limit else s


def group_sections_by_type(data: dict) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {s: [] for s in SECTION_ORDER}
    for section in data.get("sections") or []:
        st = section.get("section_type", "problem")
        groups.setdefault(st, []).append(section)
    return groups


# --- Small renderers (provenance, formulas, scores, chips) ---

def render_provenance(prov_list: list) -> str:
    parts = [
        f'<span class="prov">{escape(m)}</span>'
        for m in (prov_list or []) if isinstance(m, str) and m
    ]
    return " ".join(parts)


def render_payload_table(payload: dict) -> str:
    rows = ""
    for k, v in payload.items():
        if isinstance(v, (dict, list)):
            val_html = f"<pre>{escape(json.dumps(v, ensure_ascii=False, indent=1))}</pre>"
        else:
            val_html = escape(str(v))
        rows += f"<tr><td class='pk'>{escape(k)}</td><td>{val_html}</td></tr>"
    return f"<table class='payload'>{rows}</table>" if rows else ""


def render_symbols(symbols: list | None) -> str:
    rows = "".join(
        f"<tr><td class='sym'>{escape(str(s.get('symbol', '')))}</td>"
        f"<td>{escape(str(s.get('description', '')))}</td></tr>"
        for s in (symbols or [])
        if isinstance(s, dict) and s.get("symbol")
    )
    return f"<table class='symbols'>{rows}</table>" if rows else ""


def render_formula_block(name: str, expr: str, desc: str, symbols: list | None) -> str:
    name_html = f"<div class='f-name'>{escape(name)}</div>" if name else ""
    desc_html = f"<div class='f-desc'>{escape(desc)}</div>" if desc else ""
    return (
        f"<div class='formula'>{name_html}"
        f"<div class='f-expr'>{escape(expr)}</div>{desc_html}"
        f"{render_symbols(symbols)}</div>"
    )


def render_formulas(formulas: list | None) -> str:
    # 0.14: the objective lives in formulas[] as the role='objective' entry (with its one-line
    # description); split it out into the Objective group the old standalone field used to fill.
    entries = [f for f in (formulas or []) if isinstance(f, dict) and f.get("expression")]
    objective_blocks = "".join(
        render_formula_block(f.get("name", ""), f["expression"], f.get("description", ""), f.get("symbols", []))
        for f in entries
        if f.get("role") == "objective"
    )
    plain_blocks = "".join(
        render_formula_block(f.get("name", ""), f["expression"], "", f.get("symbols", []))
        for f in entries
        if f.get("role") != "objective"
    )
    html = ""
    if plain_blocks:
        html += f"<div class='fg'><div class='fl'>Formulas</div>{plain_blocks}</div>"
    if objective_blocks:
        html += f"<div class='fg'><div class='fl'>Objective</div>{objective_blocks}</div>"
    return html


def render_objective(obj: dict | None) -> str:
    # Legacy standalone objective_function (pre-0.14 corpora rendered without retrofit).
    if not isinstance(obj, dict) or not obj.get("expression"):
        return ""
    block = render_formula_block("", obj["expression"], obj.get("description", ""), obj.get("symbols", []))
    return f"<div class='fg'><div class='fl'>Objective</div>{block}</div>"


def render_chips(label: str, items: list | None) -> str:
    chips = "".join(f"<span class='chip'>{escape(str(i))}</span>" for i in (items or []) if str(i).strip())
    return f"<div class='fg'><div class='fl'>{escape(label)}</div><div class='chips'>{chips}</div></div>" if chips else ""


def render_scores(
    scores: list | None,
    baseline_keys: set[str],
    *,
    unit_index: dict | None = None,
    baseline_ids: set[str] | None = None,
) -> str:
    """Render a Measure's scores[] as a comparison table. A row's system is tagged as a
    baseline from its `system_id` (robust) or a fuzzy variant-name match; a per-row
    `setup_id` becomes its own column when any row carries one."""
    unit_index = unit_index or {}
    baseline_ids = baseline_ids or set()
    show_setup = any(isinstance(s, dict) and s.get("setup_id") for s in (scores or []))
    rows = ""
    for s in (scores or []):
        if not isinstance(s, dict):
            continue
        variant = str(s.get("variant", ""))
        sys_id = str(s.get("system_id", "") or "")
        if sys_id:
            is_base = sys_id in baseline_ids
        else:
            nv = _norm(variant)
            is_base = bool(nv) and any(nv in b or b in nv for b in baseline_keys)
        tag = " <span class='basetag'>baseline</span>" if is_base else ""
        sys_html = (
            f" <a class='score-sys' data-peer='{escape(sys_id)}'>{escape(sys_id)}</a>"
            if sys_id and sys_id in unit_index else
            (f" <span class='score-sys'>{escape(sys_id)}</span>" if sys_id else "")
        )
        var = str(s.get("variance", "") or "")
        setup_cell = ""
        if show_setup:
            setup_id = str(s.get("setup_id", "") or "")
            setup_label = ""
            if setup_id:
                su = unit_index.get(setup_id, {})
                setup_label = su.get("description") or su.get("name") or setup_id
                setup_label = setup_label[:40] + ("…" if len(setup_label) > 40 else "")
            setup_cell = f"<td class='score-set'>{escape(setup_label) if setup_label else '&mdash;'}</td>"
        rows += (
            f"<tr class='score-row{' baseline-row' if is_base else ''}'>"
            f"<td>{escape(variant)}{tag}{sys_html}</td>"
            f"<td class='score-val'>{escape(str(s.get('value', '')))}</td>"
            f"<td class='score-var'>{escape(var) if var else '&mdash;'}</td>"
            f"{setup_cell}</tr>"
        )
    if not rows:
        return ""
    set_head = "<th>Setup</th>" if show_setup else ""
    return (
        "<table class='scores'><thead><tr><th>System</th><th>Value</th><th>&plusmn;</th>"
        f"{set_head}</tr></thead><tbody>{rows}</tbody></table>"
    )


# --- Relation pills (the contextual "logic flow" on every card) ---

def _rel_pill(rel: str, peer_id: str, direction: str, unit_index: dict, unit_section: dict) -> str:
    peer = unit_index.get(peer_id)
    name = _unit_label(peer, 46) or peer_id
    verb = (REL_OUT if direction == "out" else REL_IN).get(rel, rel)
    arrow = "&rarr;" if direction == "out" else "&larr;"
    color = REL_COLOR.get(rel, "#64748b")
    sec = unit_section.get(peer_id, "")
    inner = (
        f"<span class='rel-arrow'>{arrow}</span>"
        f"<span class='rel-verb'>{escape(verb)}</span> "
        f"<span class='rel-peer'>{escape(name)}</span>"
    )
    if peer is not None:
        return (
            f"<a class='rel sec-{sec}' style='border-left-color:{color}' "
            f"data-peer='{escape(peer_id)}'>{inner}</a>"
        )
    return f"<span class='rel rel-dangling' style='border-left-color:{color}'>{inner}</span>"


# Order edges by argumentative priority so the flow reads top-down on each card.
_REL_PRIORITY = {
    "motivates": 0, "part_of": 1, "compares_to": 2, "evaluates": 3,
    "about": 4, "supports": 5, "resolves": 6,
}


def render_unit_relations(uid: str, out_edges: dict, in_edges: dict, unit_index: dict, unit_section: dict) -> str:
    edges = [("out", rel, t) for (rel, t) in out_edges.get(uid, [])]
    edges += [("in", rel, s) for (rel, s) in in_edges.get(uid, [])]
    if not edges:
        return ""
    edges.sort(key=lambda e: _REL_PRIORITY.get(e[1], 9))
    pills = "".join(_rel_pill(rel, peer, d, unit_index, unit_section) for (d, rel, peer) in edges)
    return f"<div class='rels'>{pills}</div>"


# --- Unit cards ---

# `source_table_marker`/`caption_marker`/`table_role` are the 0.12 blob-addressing metadata —
# consumed by the evidence-section metric blocks, suppressed (never dumped raw) on plain cards.
META_FIELDS = {"id", "type", "provenance", "role", "source_table_marker", "caption_marker", "table_role"}
# Scalar fields shown as pills. Includes the 0.10 optional payloads: Measure `objective_class`
# (FG-6) and the Finding quantitative payload `polarity`/`effect_size`/`scope` (FG-11), each shown
# only when populated.
TAG_FIELDS = ("method_kind", "comparison_direction", "objective_class", "unit",
              "polarity", "effect_size", "scope")
PROSE_FIELDS = ("description", "implementation_notes")
RICH_FIELDS = {"formulas", "objective_function", "inputs", "outputs", "scores", "setup_ids", "statement", "name",
               "headline_result", "finding_ids"}


def _role_badge(unit: dict, roles_final: dict) -> str:
    uid, utype = unit.get("id", ""), unit.get("type", "")
    role = unit.get("role") or (roles_final.get(uid) if utype == "Method" else None)
    if not role or role == "other":
        return ""
    cls = f"role role-{escape(str(role))}"
    star = "&#9733; " if role == "contribution" else ""
    return f"<span class='{cls}'>{star}{escape(str(role).replace('_', ' '))}</span>"


def render_unit_card(
    unit: dict,
    unit_index: dict,
    *,
    section_type: str,
    out_edges: dict,
    in_edges: dict,
    neighbors: dict,
    unit_section: dict,
    roles_final: dict,
    baseline_keys: set[str],
    baseline_ids: set[str],
    cite_by_unit: dict,
) -> str:
    uid = unit.get("id", "?")
    utype = unit.get("type", "?")
    tcolor = TYPE_COLORS.get(utype, "#64748b")
    prov_html = render_provenance(unit.get("provenance", []))

    label, label_field = "", ""
    for cand in ("statement", "name", "description"):
        if unit.get(cand):
            label, label_field = unit[cand], cand
            break
    used_label_fields = {label_field} if label_field else set()
    disp_label = label[:200] + "…" if isinstance(label, str) and len(label) > 200 else label

    role_badge = _role_badge(unit, roles_final)
    tag_html = "".join(f"<span class='tag'>{escape(str(unit[f]))}</span>" for f in TAG_FIELDS if unit.get(f))
    tags_html = f"<div class='tags'>{tag_html}</div>" if tag_html else ""

    cite_ids = cite_by_unit.get(uid, [])
    cite_html = ""
    if cite_ids:
        chips = "".join(
            f"<a class='cite-badge' title='Cited as reference {escape(str(r))}'>[{escape(str(r))}]</a>"
            for r in cite_ids
        )
        cite_html = f"<span class='cite-badges'>{chips}</span>"

    # Detail (collapsed): prose, type-specific rich blocks, then leftover fields.
    prose = ""
    for f in PROSE_FIELDS:
        if unit.get(f) and f not in used_label_fields:
            prose += (
                f"<div class='fg'><div class='fl'>{escape(f.replace('_', ' '))}</div>"
                f"<div class='prose'>{escape(str(unit[f]))}</div></div>"
            )
    rich = ""
    if utype == "Method":
        rich += render_chips("Inputs", unit.get("inputs"))
        rich += render_chips("Outputs", unit.get("outputs"))
        rich += render_formulas(unit.get("formulas"))
        rich += render_objective(unit.get("objective_function"))
    elif utype == "Measure":
        # 0.12 fields on a Measure that landed outside the evidence section (where
        # render_metric_block would own them): same pill/chip treatment, never a raw dump.
        if unit.get("headline_result"):
            rich += f"<div class='m-headline'>{escape(str(unit['headline_result']))}</div>"
        scores_html = render_scores(unit.get("scores"), baseline_keys, unit_index=unit_index, baseline_ids=baseline_ids)
        if scores_html:
            rich += f"<div class='fg'><div class='fl'>Scores</div>{scores_html}</div>"
        if unit.get("setup_ids"):
            names = [(unit_index.get(s, {}).get("description") or unit_index.get(s, {}).get("name") or s)
                     for s in unit["setup_ids"]]
            rich += render_chips("Setups", names)
        if unit.get("finding_ids"):
            names = [(unit_index.get(f, {}).get("statement") or unit_index.get(f, {}).get("name") or f)
                     for f in unit["finding_ids"]]
            rich += render_chips("Findings", names)

    handled = META_FIELDS | RICH_FIELDS | set(TAG_FIELDS) | set(PROSE_FIELDS) | used_label_fields
    leftover = {k: v for k, v in unit.items() if k not in handled and v not in (None, "", [], {})}
    detail_html = prose + rich + render_payload_table(leftover)
    detail = f"<div class='u-detail'>{detail_html}</div>" if detail_html.strip() else ""

    rels_html = render_unit_relations(uid, out_edges, in_edges, unit_index, unit_section)
    data_rel = " ".join(sorted(neighbors.get(uid, set())))
    chevron = "<span class='u-chevron'>&#9656;</span>" if detail else ""

    return f"""
    <div class="unit" id="u-{escape(uid)}" data-uid="{escape(uid)}" data-rel="{escape(data_rel)}">
      <div class="u-head">
        <span class="u-badge" style="background:{tcolor}">{escape(utype)}</span>
        {role_badge}
        <span class="u-id">{escape(uid)}</span>
        {cite_html}
        {chevron}
      </div>
      <div class="u-label">{escape(disp_label)}</div>
      {tags_html}
      {f'<div class="u-prov">{prov_html}</div>' if prov_html else ''}
      {rels_html}
      {detail}
    </div>"""


# Void elements may legally appear unclosed inside a table blob (the HTML5 void list).
_BLOB_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
# Blobs are sliced verbatim from untrusted OCR'd paper content, so the audit is an ALLOW-list:
# table structure + inline formatting only. Any other tag (script, meta, base, link, img, a,
# form, svg, ...) fails — nothing in a blob may navigate, fetch, or execute on open.
_BLOB_ALLOWED_TAGS = {
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col",
    "b", "i", "em", "strong", "u", "s", "small", "sub", "sup", "br", "hr", "span", "p", "div",
}
# Attributes that can navigate or fetch. No allowed tag needs a URI attribute, so the NAME is
# rejected outright — immune to scheme obfuscation a value check would have to chase. `style` is
# included because CSS url()/image-set() fetch on render without any scheme prefix.
_BLOB_REJECT_ATTRS = {
    "href", "src", "srcset", "action", "formaction", "xlink:href", "background",
    "data", "ping", "poster", "cite", "usemap", "style",
}
# A raw `<` a browser would tokenise as markup (tag / end tag / comment / decl / PI).
_BLOB_MARKUP_RE = re.compile(r"<[a-zA-Z/!?]")


class _TableBlobAuditor(HTMLParser):
    """Structural audit for a verbatim source-table blob: every opened tag must be closed (void
    elements exempt), only allow-listed table/inline-formatting tags with no navigating/fetching/
    executable attributes (``on*`` handlers, URI attributes, inline ``style``), and no stray
    ``<`` the browser would tokenise as markup — an unclosed ``<div>`` or half-emitted tag in an
    OCR-mangled table would otherwise swallow the rest of the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.ok = True

    def _check_tag(self, tag: str, attrs: list) -> None:
        if tag not in _BLOB_ALLOWED_TAGS:
            self.ok = False
            return
        for name, _value in attrs:
            name = str(name or "").lower()
            if name.startswith("on") or name in _BLOB_REJECT_ATTRS:
                self.ok = False
                return

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self._check_tag(tag, attrs)
        if tag not in _BLOB_VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self._check_tag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOB_VOID_TAGS:
            return  # browsers ignore a stray </br> & co
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.ok = False  # close without a matching open, or misnested

    def handle_data(self, data: str) -> None:
        if _BLOB_MARKUP_RE.search(data):
            self.ok = False  # raw `<` the parser did not consume as a complete construct


def _table_blob_is_safe(blob: str) -> bool:
    """True when the blob is balanced, non-executable table markup safe to insert verbatim."""
    # An unterminated comment swallows everything after it — check explicitly.
    i = 0
    while (start := blob.find("<!--", i)) != -1:
        end = blob.find("-->", start + 4)
        if end == -1:
            return False
        i = end + 3
    auditor = _TableBlobAuditor()
    try:
        auditor.feed(blob)
        auditor.close()
    except Exception:
        return False
    return auditor.ok and not auditor.stack


def render_table_prettify(html: str, caption: str = "", marker: str = "") -> str:
    """Render a verbatim source ``<table>`` blob inside a namespaced ``kb-measure-table`` wrapper.

    The wrapper scopes all styling via descendant selectors (``.kb-measure-table table`` …) so the
    paper's own table classes cannot collide with the viewer's. The table HTML is the paper's own
    markup, inserted as-is once it passes a structural audit (balanced allow-listed tags, nothing
    that navigates/fetches/executes); a mangled or unsafe blob would swallow the rest of the page
    or phone home on open, so it falls back to an escaped ``<pre>`` instead — never worse than raw. The caption (the model-chosen block, sliced verbatim in
    assembly) is shown as a label with its surrounding ``**`` markdown stripped.
    """
    if not html:
        return ""
    cap = (caption or "").strip().strip("*").strip()
    cap_html = f"<div class='kb-mt-cap'>{escape(cap)}</div>" if cap else ""
    src_html = f"<span class='kb-mt-src'>source {escape(marker)}</span>" if marker else ""
    body = html if _table_blob_is_safe(html) else f"<pre class='kb-mt-raw'>{escape(html)}</pre>"
    return f"<div class='kb-measure-table'>{cap_html}<div class='kb-mt-wrap'>{body}</div>{src_html}</div>"


def render_metric_block(
    m: dict,
    unit_index: dict,
    subject_by_metric: dict,
    dataset_by_metric: dict,
    roles_final: dict,
    baseline_keys: set[str],
    baseline_ids: set[str],
    out_edges: dict,
    in_edges: dict,
    neighbors: dict,
    unit_section: dict,
    source_tables: dict | None = None,
    rendered_markers: set[str] | None = None,
) -> str:
    """A Measure rendered as a comparison block — itself an addressable, focusable node.

    Blob-primary (0.12): a Measure may carry a ``headline_result`` one-liner (rendered as a pill), a
    ``source_table_marker`` that resolves to a verbatim source-table blob (rendered once per distinct
    marker — a shared multi-metric table is drawn under its first Measure, later ones link up to it),
    and ``finding_ids`` mounting the Findings it evidences (rendered as links). Marker-less Measures
    (flag-off / prose / older outputs) render exactly as before via ``render_scores``.
    """
    source_tables = source_tables or {}
    mid = m.get("id", "")
    subj_ids = subject_by_metric.get(mid, [])
    head = next((s for s in subj_ids if roles_final.get(s) == "contribution"), subj_ids[0] if subj_ids else "")
    ds_ids = dataset_by_metric.get(mid, [])

    def name_of(uid: str) -> str:
        u = unit_index.get(uid, {})
        return u.get("name") or u.get("statement") or uid

    scores_html = render_scores(m.get("scores"), baseline_keys, unit_index=unit_index, baseline_ids=baseline_ids)
    meta_bits = ""
    if head:
        meta_bits += f"<span class='m-meta'>evaluates <b>{escape(str(name_of(head)))}</b></span>"
    if ds_ids:
        meta_bits += f"<span class='m-meta'>on {escape(', '.join(name_of(d) for d in ds_ids))}</span>"

    headline = m.get("headline_result")
    headline_html = f"<div class='m-headline'>{escape(str(headline))}</div>" if headline else ""

    # Verbatim source-table blob, drawn once per distinct marker across the section.
    blob_html = ""
    marker = (m.get("source_table_marker") or "").strip()
    if marker:
        entry = source_tables.get(marker)
        if isinstance(entry, dict) and entry.get("html"):
            if rendered_markers is not None and marker in rendered_markers:
                blob_html = f"<div class='m-tableref'>source table {escape(marker)} shown above</div>"
            else:
                if rendered_markers is not None:
                    rendered_markers.add(marker)
                blob_html = render_table_prettify(entry.get("html", ""), entry.get("caption", ""), marker)
        else:
            # A marker that doesn't resolve (or resolves to an empty blob): under blob-primary the
            # baselines live only in that table, so say so instead of silently rendering nothing.
            blob_html = f"<div class='m-tableref'>source table {escape(marker)} unavailable</div>"

    # Mounted findings (0.12) — the table→finding link, replacing the Finding↔Measure edges.
    finding_links = []
    for fid in m.get("finding_ids") or []:
        if not isinstance(fid, str):
            continue
        label = name_of(fid)
        label = str(label)[:90] + ("…" if len(str(label)) > 90 else "")
        finding_links.append(
            f"<a class='m-finding' href='#u-{escape(fid)}' data-peer='{escape(fid)}'>{escape(label)}</a>"
        )
    findings_html = f"<div class='m-findings'>{''.join(finding_links)}</div>" if finding_links else ""

    prov_html = render_provenance(m.get("provenance", []))
    rels_html = render_unit_relations(mid, out_edges, in_edges, unit_index, unit_section)
    data_rel = " ".join(sorted(neighbors.get(mid, set())))

    return f"""
    <div class="unit metric-block" id="u-{escape(mid)}" data-uid="{escape(mid)}" data-rel="{escape(data_rel)}">
      <div class="m-head">
        <span class="u-badge" style="background:{TYPE_COLORS['Measure']}">Measure</span>
        <span class="m-name">{escape(m.get('name', ''))}</span>
        <span class="m-unit">{escape(str(m.get('unit', '')))}</span>
        {meta_bits}
      </div>
      {headline_html}
      {scores_html}
      {blob_html}
      {findings_html}
      {f'<div class="u-prov">{prov_html}</div>' if prov_html else ''}
      {rels_html}
    </div>"""


# --- Discovery arc (replaces the old Argumentative Spine view) ---

def _arc_chip(unit: dict, kind: str, mark: str = "") -> str:
    return (
        f"<span class='arc-chip arc-{kind}' data-peer='{escape(unit.get('id', ''))}'>"
        f"{mark}{escape(_unit_label(unit, 52))}</span>"
    )


def render_discovery_arc(data: dict, unit_index: dict, roles_final: dict, edges: list[dict]) -> str:
    problems = [
        u for s in data.get("sections") or [] if s.get("section_type") == "problem"
        for u in s.get("units") or [] if isinstance(u, dict) and u.get("type") == "Problem"
    ]
    problem = problems[0] if problems else None

    contrib_id = next((uid for uid, r in roles_final.items() if r == "contribution"), None)
    contrib = unit_index.get(contrib_id) if contrib_id else None

    # Headline finding: source of a `resolves` edge, else a Finding `about` the contribution.
    headline_id, resolved = None, False
    problem_id = problem.get("id") if problem else None
    for e in edges:
        if e.get("relation") == "resolves":
            headline_id = e.get("source_id")
            problem_id = problem_id or e.get("target_id")
            resolved = True
            break
    if not headline_id and contrib_id:
        for e in edges:
            if e.get("relation") == "about" and e.get("target_id") == contrib_id:
                src = unit_index.get(e.get("source_id"))
                if src and src.get("type") == "Finding":
                    headline_id = e.get("source_id")
                    break
    headline = unit_index.get(headline_id) if headline_id else None
    if problem is None and problem_id:
        problem = unit_index.get(problem_id)

    if not problem and not contrib:
        return ""

    parts = []
    if problem:
        parts.append(_arc_chip(problem, "problem"))
    if contrib:
        if parts:
            parts.append("<span class='arc-conn'>motivates &rarr;</span>")
        parts.append(_arc_chip(contrib, "method", "&#9733; "))
    if headline:
        parts.append("<span class='arc-conn'>answers &rarr;</span>")
        parts.append(_arc_chip(headline, "finding"))
    close = (
        "<span class='arc-close'>&#8617; resolves &#10003;</span>"
        if (resolved and headline and problem) else ""
    )
    track = "".join(parts)
    return f"""
    <div class="arc">
      <div class="arc-title">Discovery throughline</div>
      <div class="arc-track">{track}{close}</div>
      <div class="arc-legend">&rarr; outgoing &middot; &larr; incoming &middot; click any node to trace its links &middot; Esc clears</div>
    </div>"""


# --- Section + page chrome ---

def section_render_order(grouped: dict) -> list[str]:
    """Canonical three first, then any other section types present (forward/backward compat)."""
    order = [st for st in SECTION_ORDER if grouped.get(st)]
    order += sorted(t for t in grouped if t not in SECTION_ORDER and grouped.get(t))
    return order


def render_nav(grouped: dict, has_refs: bool) -> str:
    links = ""
    for st in section_render_order(grouped):
        cnt = sum(len(s.get("units") or []) for s in grouped.get(st, []))
        if cnt:
            color = SECTION_COLORS.get(st, "#64748b")
            label = SECTION_LABELS.get(st, st.replace("_", " ").title())
            links += (
                f'<a class="nav-link" href="#sec-{st}">'
                f'<span class="nav-dot" style="background:{color}"></span>'
                f'{escape(label)} <b>{cnt}</b></a>'
            )
    if has_refs:
        links += '<a class="nav-link" href="#references">References</a>'
    return f'<nav class="topnav"><span class="nav-brand">section-IR</span>{links}</nav>'


def render_section(
    section_type: str,
    sections: list[dict],
    unit_index: dict,
    *,
    out_edges: dict,
    in_edges: dict,
    neighbors: dict,
    unit_section: dict,
    roles_final: dict,
    baseline_keys: set[str],
    baseline_ids: set[str],
    subject_by_metric: dict,
    dataset_by_metric: dict,
    cite_by_unit: dict,
    source_tables: dict | None = None,
) -> str:
    color = SECTION_COLORS.get(section_type, "#64748b")
    label = SECTION_LABELS.get(section_type, section_type.replace("_", " ").title())
    subtitle = SECTION_SUBTITLES.get(section_type, "")
    source_tables = source_tables or {}

    # Dedup units across sections of the same type (id-less units are kept, never deduped).
    seen: set[str] = set()
    units: list[dict] = []
    for section in sections:
        for u in section.get("units") or []:
            if not isinstance(u, dict):
                continue
            uid = u.get("id")
            if uid in seen:
                continue
            if uid:
                seen.add(uid)
            units.append(u)

    count = len(units)
    common = dict(
        out_edges=out_edges, in_edges=in_edges, neighbors=neighbors, unit_section=unit_section,
        roles_final=roles_final, baseline_keys=baseline_keys, baseline_ids=baseline_ids,
        cite_by_unit=cite_by_unit,
    )

    body = ""
    if section_type == "evidence":
        # Measures as comparison blocks first, then findings/other as cards.
        measures = [u for u in units if u.get("type") == "Measure"]
        others = [u for u in units if u.get("type") != "Measure"]
        rendered_markers: set[str] = set()  # dedup a shared source-table blob across measures
        for m in measures:
            body += render_metric_block(
                m, unit_index, subject_by_metric, dataset_by_metric, roles_final,
                baseline_keys, baseline_ids, out_edges, in_edges, neighbors, unit_section,
                source_tables=source_tables, rendered_markers=rendered_markers,
            )
        for u in others:
            body += render_unit_card(u, unit_index, section_type=section_type, **common)
    else:
        ordered = units
        if section_type == "method":
            ordered = sorted(units, key=lambda u: METHOD_ROLE_RANK.get(roles_final.get(u.get("id"), "other"), 2))
        for u in ordered:
            body += render_unit_card(u, unit_index, section_type=section_type, **common)

    return f"""
    <section class="sec" id="sec-{section_type}" style="--accent:{color}">
      <div class="sec-head">
        <span class="sec-dot" style="background:{color}"></span>
        <span class="sec-title">{escape(label)}</span>
        <span class="sec-sub">{escape(subtitle)}</span>
        <span class="sec-count">{count}</span>
        <span class="sec-chevron">&#9660;</span>
      </div>
      <div class="sec-body">{body or '<div class="empty">No units.</div>'}</div>
    </section>"""


def render_metadata_panel(metadata: dict | None, doc: dict | None) -> str:
    doc = doc or {}
    title = (metadata or {}).get("title") or doc.get("title", "Untitled")
    authors_html = resources_html = ""
    if metadata:
        authors = metadata.get("authors") or []
        if authors:
            parts = []
            for a in authors:
                name = a.get("name", "")
                affils = a.get("affiliations", [])
                parts.append(
                    f"{escape(name)} <span class='affil'>({escape(', '.join(affils))})</span>"
                    if affils else escape(name)
                )
            authors_html = f'<div class="authors">{" &middot; ".join(parts)}</div>'
        resources = metadata.get("resources") or []
        res_parts = []
        for r in resources:
            url = r.get("url", "")
            if url:
                icon = RESOURCE_ICONS.get(r.get("type", "paper"), "&#128279;")
                res_parts.append(f'<a href="{escape(url)}" class="res" target="_blank">{icon} {escape(r.get("type", "link"))}</a>')
        if res_parts:
            resources_html = f'<div class="resources">{" ".join(res_parts)}</div>'

    thesis = (doc.get("thesis") or "").strip()
    thesis_html = f'<div class="thesis"><span class="thesis-l">Thesis</span> {escape(thesis)}</div>' if thesis else ""
    headline = (doc.get("headline_result") or "").strip()
    headline_html = (
        f'<div class="thesis"><span class="thesis-l">Result</span> {escape(headline)}</div>'
        if headline else ""
    )
    return f"""
    <header class="paper-header">
      <h1>{escape(title)}</h1>
      {authors_html}
      {thesis_html}
      {headline_html}
      {resources_html}
    </header>"""


def render_references_panel(
    references: dict | None, unit_index: dict | None = None, references_blob: str | None = None,
    blob_primary: bool = False,
) -> str:
    refs = (references.get("references") or []) if isinstance(references, dict) else []
    # Blob-primary references: the structured `refs` are only the graph-linked entries; the full
    # bibliography is the code-sliced verbatim blob, shown beneath them. With neither, nothing to render.
    if not refs and not references_blob:
        return ""
    unit_index = unit_index or {}
    rows, linked = "", 0
    for r in refs:
        if not isinstance(r, dict):
            continue
        rid = r.get("id", "")
        authors = r.get("authors") or []
        author_str = f"{authors[0]} et al." if len(authors) > 3 else ", ".join(authors)
        title = r.get("title") or ""
        venue = r.get("venue", "")
        year = r.get("year", "")
        venue_year = ", ".join(escape(str(v)) for v in (venue, year) if v)
        venue_str = f" &mdash; {venue_year}" if venue_year else ""
        relation = r.get("relation") or {}
        unit_ids = relation.get("provides_unit_ids") or []
        roles = relation.get("roles") or []
        entry_cls = "ref central" if relation.get("salience") == "central" else "ref"
        link_html = ""
        if unit_ids:
            linked += 1
            parts = []
            for uid in unit_ids:
                name = escape((unit_index.get(uid) or {}).get("name") or str(uid))
                if uid in unit_index:  # only clickable when the target is actually on the page
                    parts.append(f"<a class='ref-link' data-peer='{escape(str(uid))}'>{name}</a>")
                else:
                    parts.append(f"<span class='ref-link rel-dangling'>{name}</span>")
            link_html = f"<div class='ref-links'>&rarr; {''.join(parts)}</div>"
        roles_html = f"<span class='ref-roles'>{escape(', '.join(roles))}</span>" if roles else ""
        rows += (
            f'<div class="{entry_cls}">'
            f'<span class="ref-id">[{escape(str(rid))}]</span> {escape(author_str)} '
            f'<span class="ref-title">&ldquo;{escape(title)}&rdquo;</span>{venue_str}{roles_html}'
            f'{link_html}</div>\n'
        )
    extra = f" &middot; {linked} linked to units" if linked else ""
    # Blob-primary: the verbatim full bibliography (code-sliced) shown beneath the structured linked
    # entries — the completeness backstop for the background refs the references pass no longer transcribes.
    blob_html = ""
    if references_blob:
        title_n = f" &middot; {len(refs)} linked above" if refs else ""
        # Display-only prettifier: split the run-together verbatim blob into one entry per
        # reference for readability. Falls back to the raw <pre> when the split isn't confident
        # ("never worse than raw"); the extraction path never sees this — it always gets the raw blob.
        formatted = format_references_blob(references_blob)
        if formatted and formatted.entries:
            items = ""
            for marker, body in formatted.entries:
                mark_html = f'<span class="ref-blob-mark">{escape(marker)}</span> ' if marker else ""
                items += f'<li class="ref-blob-item">{mark_html}{escape(body)}</li>\n'
            body_html = f'<ul class="ref-blob-list">{items}</ul>'
        else:
            body_html = f'<pre class="ref-blob-body">{escape(references_blob)}</pre>'
        blob_html = (
            f'<div class="ref-blob"><div class="ref-blob-head">Full bibliography (verbatim){title_n}</div>'
            f'{body_html}</div>\n'
        )
    elif blob_primary:
        # Blob-primary was on but no bibliography could be sliced from the paper: the structured
        # list is graph-linked entries only, so flag the gap instead of looking like a complete list.
        blob_html = (
            '<div class="ref-blob"><div class="ref-blob-head ref-blob-warn">Graph-linked references only '
            '&mdash; the full verbatim bibliography could not be sliced from the paper, so background '
            'references are not shown.</div></div>\n'
        )
    label = "Graph-linked references" if (references_blob or blob_primary) else "References"
    return f"""
    <section class="sec collapsed refs-sec" id="references">
      <div class="sec-head">
        <span class="sec-title">{label} ({len(refs)}){extra}</span>
        <span class="sec-chevron">&#9660;</span>
      </div>
      <div class="sec-body">{rows}{blob_html}</div>
    </section>"""


# --- Page assembly ---

def render_html(pipeline_data: dict[str, Any]) -> str:
    data = pipeline_data["extraction"]
    metadata = pipeline_data.get("metadata")
    references = pipeline_data.get("references")

    unit_index = build_unit_index(data)
    unit_section = build_unit_section_map(data)
    out_edges, in_edges, neighbors = build_edge_index(data, unit_index)
    all_links = collect_all_links(data)
    subject_by_metric = build_metric_subjects(data)
    dataset_by_metric = build_metric_datasets(data, unit_index)
    roles_final = classify_methods(data, unit_index)

    baseline_ids = {
        uid for uid, u in unit_index.items()
        if u.get("type") == "Method" and (u.get("role") == "compared_against" or roles_final.get(uid) in ("compared_against", "baseline"))
    }
    baseline_keys = {_norm(unit_index.get(uid, {}).get("name", "")) for uid in baseline_ids}
    baseline_keys.discard("")

    # reference -> units it provides, inverted to unit -> [reference ids] for cite badges.
    cite_by_unit: dict[str, list[str]] = defaultdict(list)
    if isinstance(references, dict):
        for ref in references.get("references", []) or []:
            if not isinstance(ref, dict):
                continue
            rid = ref.get("id")
            for uid in (ref.get("relation") or {}).get("provides_unit_ids", []) or []:
                if isinstance(uid, str) and isinstance(rid, str) and rid not in cite_by_unit[uid]:
                    cite_by_unit[uid].append(rid)

    grouped = group_sections_by_type(data)
    doc = data.get("document") or {}
    notes = data.get("extraction_notes") or {}
    ir_version = notes.get("ir_version", "")
    source_tables = notes.get("source_tables") if isinstance(notes.get("source_tables"), dict) else {}

    total_units = sum(1 for u in unit_index.values() if u.get("type") != "Document")
    total_sections = len(data.get("sections") or [])
    total_links = len(all_links)
    plan_coverage = notes.get("plan_coverage", {})
    cov_value = (
        f"{plan_coverage.get('must_covered', 0)}/{plan_coverage.get('must_total', 0)}"
        if isinstance(plan_coverage, dict) and plan_coverage else "n/a"
    )

    header_html = render_metadata_panel(metadata, doc)
    nav_html = render_nav(grouped, has_refs=bool(
        (isinstance(references, dict) and references.get("references")) or notes.get("references_blob")
    ))
    arc_html = render_discovery_arc(data, unit_index, roles_final, all_links)

    section_html = ""
    for st in section_render_order(grouped):
        secs = grouped.get(st, [])
        if not secs:
            continue
        section_html += render_section(
            st, secs, unit_index,
            out_edges=out_edges, in_edges=in_edges, neighbors=neighbors, unit_section=unit_section,
            roles_final=roles_final, baseline_keys=baseline_keys, baseline_ids=baseline_ids,
            subject_by_metric=subject_by_metric, dataset_by_metric=dataset_by_metric,
            cite_by_unit=cite_by_unit, source_tables=source_tables,
        )

    references_html = render_references_panel(
        references, unit_index, references_blob=notes.get("references_blob"),
        blob_primary=notes.get("blob_primary_references") is True,
    )

    notes_html = ""
    for ua in notes.get("uncertain_assignments") or []:
        notes_html += f"<li>{escape(str(ua))}</li>"
    for item in notes.get("uncovered_items") or []:
        if isinstance(item, dict):
            notes_html += f"<li>uncovered {escape(str(item.get('item_id', '')))}: {escape(str(item.get('reason', '')))}</li>"
        else:
            notes_html += f"<li>uncovered {escape(str(item))}</li>"
    notes_block = f'<section class="notes"><h2>Extraction notes</h2><ul>{notes_html}</ul></section>' if notes_html else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(doc.get('title', 'Extraction'))} &mdash; section-IR</title>
<style>{CSS}</style>
</head>
<body>
{nav_html}
<div class="container">
  {header_html}
  <div class="stats">
    <div class="stat"><div class="sv">{total_sections}</div><div class="sl">sections</div></div>
    <div class="stat"><div class="sv">{total_units}</div><div class="sl">units</div></div>
    <div class="stat"><div class="sv">{total_links}</div><div class="sl">relations</div></div>
    <div class="stat"><div class="sv">{escape(cov_value)}</div><div class="sl">must coverage</div></div>
    <div class="stat ir">{escape(ir_version)}</div>
  </div>
  {arc_html}
  {section_html}
  {references_html}
  {notes_block}
</div>
<script>{JS_CODE}</script>
</body>
</html>"""


# --- Styles & behaviour (no external dependencies) ---

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0b1220; color:#e2e8f0; line-height:1.55; }
a { color:inherit; text-decoration:none; }
.container { max-width:1080px; margin:0 auto; padding:20px 24px 60px; }

/* Sticky nav */
.topnav { position:sticky; top:0; z-index:20; display:flex; align-items:center; gap:6px; flex-wrap:wrap;
  background:rgba(11,18,32,.92); backdrop-filter:blur(8px); border-bottom:1px solid #1e293b; padding:9px 24px; }
.nav-brand { font-weight:700; font-size:.78rem; letter-spacing:.06em; text-transform:uppercase; color:#64748b; margin-right:10px; }
.nav-link { font-size:.82rem; color:#cbd5e1; padding:4px 10px; border-radius:6px; display:inline-flex; align-items:center; gap:6px; }
.nav-link:hover { background:#1e293b; }
.nav-link b { color:#f8fafc; }
.nav-dot { width:8px; height:8px; border-radius:50%; }

/* Header */
.paper-header { margin:18px 0 14px; padding-bottom:14px; border-bottom:1px solid #1e293b; }
.paper-header h1 { font-size:1.5rem; font-weight:700; color:#f8fafc; }
.authors { font-size:.84rem; color:#94a3b8; margin-top:6px; }
.affil { font-size:.74rem; color:#64748b; }
.thesis { font-size:.92rem; color:#dbeafe; margin-top:10px; padding:8px 12px; border-left:3px solid #3b82f6; background:#0f1b30; border-radius:0 6px 6px 0; }
.thesis-l { font-size:.66rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:#60a5fa; margin-right:6px; }
.resources { display:flex; gap:8px; margin-top:10px; flex-wrap:wrap; }
.res { font-size:.78rem; color:#93c5fd; padding:3px 10px; background:#1e293b; border-radius:5px; }
.res:hover { background:#334155; }

/* Stats */
.stats { display:flex; gap:10px; margin:14px 0 4px; flex-wrap:wrap; align-items:stretch; }
.stat { background:#111c30; border:1px solid #1e293b; border-radius:8px; padding:8px 14px; min-width:84px; }
.sv { font-size:1.05rem; font-weight:700; color:#f1f5f9; }
.sl { font-size:.66rem; color:#94a3b8; text-transform:uppercase; letter-spacing:.05em; }
.stat.ir { display:flex; align-items:center; color:#64748b; font-size:.72rem; font-family:ui-monospace,monospace; }

/* Discovery arc */
.arc { background:linear-gradient(180deg,#101d33,#0d1729); border:1px solid #1e293b; border-radius:10px; padding:14px 16px; margin:18px 0 22px; }
.arc-title { font-size:.68rem; text-transform:uppercase; letter-spacing:.07em; color:#64748b; font-weight:700; margin-bottom:10px; }
.arc-track { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
.arc-chip { font-size:.84rem; font-weight:600; padding:7px 12px; border-radius:8px; cursor:pointer; border:1px solid transparent; max-width:340px; }
.arc-chip:hover { filter:brightness(1.15); }
.arc-problem { background:#3a2a0c; color:#fcd34d; border-color:#a16207; }
.arc-method  { background:#10243f; color:#93c5fd; border-color:#1d4ed8; }
.arc-finding { background:#0f2e1c; color:#86efac; border-color:#15803d; }
.arc-conn { font-size:.72rem; color:#64748b; white-space:nowrap; }
.arc-close { font-size:.74rem; color:#fcd34d; font-weight:600; margin-left:2px; }
.arc-legend { font-size:.7rem; color:#475569; margin-top:11px; }

/* Sections */
.sec { background:#0f1829; border:1px solid #1e293b; border-radius:10px; margin-bottom:14px; overflow:hidden; }
.sec-head { display:flex; align-items:center; gap:10px; padding:13px 16px; cursor:pointer; user-select:none; border-left:4px solid var(--accent,#334155); }
.sec-head:hover { background:#13203a; }
.sec-dot { width:11px; height:11px; border-radius:50%; }
.sec-title { font-weight:700; font-size:1rem; color:#f8fafc; }
.sec-sub { font-size:.76rem; color:#64748b; flex:1; }
.sec-count { font-size:.74rem; color:#94a3b8; background:#1e293b; border-radius:10px; padding:1px 9px; }
.sec-chevron { font-size:.66rem; color:#64748b; transition:transform .18s; }
.sec.collapsed .sec-body { display:none; }
.sec.collapsed .sec-chevron { transform:rotate(-90deg); }
.sec-body { padding:8px 16px 16px; }
.empty { color:#475569; font-size:.82rem; padding:8px 0; }

/* Unit cards (also used for Measure blocks) */
.unit { background:#0b1424; border:1px solid #25324a; border-radius:8px; padding:11px 13px; margin-top:9px;
  transition:opacity .15s, box-shadow .15s, border-color .15s; }
.unit:hover { border-color:#3b4a66; }
body.focusing .unit:not(.focus):not(.related) { opacity:.26; }
.unit.focus { border-color:#f59e0b; box-shadow:0 0 0 2px rgba(245,158,11,.55); }
.unit.related { border-color:#38bdf8; box-shadow:0 0 0 1px rgba(56,189,248,.5); }
.u-head { display:flex; align-items:center; gap:8px; cursor:pointer; }
.u-badge { font-size:.58rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:#fff; padding:2px 6px; border-radius:4px; }
.role { font-size:.56rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; padding:2px 6px; border-radius:4px; background:#334155; color:#cbd5e1; }
.role-contribution { background:#f59e0b; color:#1a1300; }
.role-component { background:#1d4ed8; color:#dbeafe; }
.role-compared_against, .role-builds_on { background:#334155; color:#94a3b8; }
.u-id { font-size:.7rem; color:#5b6b85; font-family:ui-monospace,monospace; }
.u-chevron { margin-left:auto; font-size:.62rem; color:#475569; transition:transform .15s; }
.unit.open .u-chevron { transform:rotate(90deg); }
.u-label { font-size:.9rem; color:#e2e8f0; margin-top:6px; }
.u-prov { margin-top:5px; }
.prov { font-size:.62rem; background:#1e293b; color:#94a3b8; padding:1px 6px; border-radius:3px; margin-right:3px; }
.tags { display:flex; gap:5px; flex-wrap:wrap; margin-top:6px; }
.tag { font-size:.62rem; background:#1e293b; color:#94a3b8; border:1px solid #2c3a52; padding:1px 7px; border-radius:3px; }

/* Relation pills (the contextual logic flow) */
.rels { display:flex; gap:6px; flex-wrap:wrap; margin-top:9px; }
.rel { font-size:.72rem; background:#101a2e; border:1px solid #25324a; border-left:3px solid #64748b;
  padding:3px 9px; border-radius:5px; cursor:pointer; color:#cbd5e1; display:inline-flex; align-items:center; gap:5px; }
.rel:hover { background:#16233c; border-color:#3b4a66; }
.rel-dangling { cursor:default; opacity:.6; }
.rel-arrow { color:#64748b; font-weight:700; }
.rel-verb { color:#94a3b8; }
.rel-peer { color:#e2e8f0; font-weight:500; }
.rel.sec-problem .rel-peer { color:#fcd34d; }
.rel.sec-method .rel-peer { color:#93c5fd; }
.rel.sec-evidence .rel-peer { color:#86efac; }

/* Unit detail (collapsed) */
.u-detail { display:none; margin-top:9px; padding-top:9px; border-top:1px dashed #25324a; }
.unit.open .u-detail { display:block; }
.fg { margin-top:8px; }
.fl { font-size:.62rem; color:#64748b; text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }
.prose { font-size:.82rem; color:#cbd5e1; }
.chips { display:flex; gap:5px; flex-wrap:wrap; }
.chip { font-size:.72rem; background:#1e293b; color:#cbd5e1; border:1px solid #2c3a52; padding:2px 8px; border-radius:10px; }
.payload { width:100%; font-size:.76rem; border-collapse:collapse; }
.payload td { padding:3px 7px; border-bottom:1px solid #16233c; vertical-align:top; }
.pk { color:#94a3b8; font-family:ui-monospace,monospace; width:120px; }
.payload pre { margin:0; font-size:.7rem; white-space:pre-wrap; color:#cbd5e1; }

/* Formulas */
.formula { background:#0a1322; border:1px solid #25324a; border-radius:6px; padding:8px 10px; margin-bottom:6px; }
.f-name { font-size:.66rem; color:#94a3b8; margin-bottom:4px; }
.f-expr { font-family:'SF Mono','Fira Code',Consolas,monospace; font-size:.82rem; color:#e2e8f0; white-space:pre-wrap; word-break:break-word; }
.f-desc { font-size:.74rem; color:#94a3b8; margin-top:4px; }
.symbols { margin-top:6px; border-collapse:collapse; font-size:.74rem; }
.symbols td { padding:2px 8px 2px 0; vertical-align:top; color:#cbd5e1; }
.symbols .sym { font-family:'SF Mono',Consolas,monospace; color:#93c5fd; white-space:nowrap; }

/* Measure blocks */
.metric-block .m-head { display:flex; align-items:baseline; gap:9px; flex-wrap:wrap; }
.m-name { font-weight:700; font-size:.92rem; color:#f1f5f9; }
.m-unit { font-size:.72rem; color:#2dd4bf; font-weight:700; font-variant-numeric:tabular-nums; }
.m-meta { font-size:.72rem; color:#94a3b8; }
.m-meta b { color:#cbd5e1; }
.scores { width:100%; border-collapse:collapse; font-size:.8rem; margin-top:8px; }
.scores th { text-align:left; padding:4px 8px; border-bottom:1px solid #25324a; color:#64748b; font-size:.64rem; text-transform:uppercase; letter-spacing:.04em; }
.scores td { padding:4px 8px; border-bottom:1px solid #16233c; }
.score-val { font-weight:700; color:#2dd4bf; font-variant-numeric:tabular-nums; }
.score-var { color:#64748b; font-variant-numeric:tabular-nums; }
.score-row.baseline-row td { color:#94a3b8; }
.score-row.baseline-row .score-val { color:#64748b; font-weight:600; }
.basetag { font-size:.54rem; background:#334155; color:#94a3b8; padding:1px 5px; border-radius:3px; text-transform:uppercase; letter-spacing:.04em; }
.score-sys { font-size:.62rem; color:#5b6b85; font-family:ui-monospace,monospace; margin-left:4px; }
a.score-sys { cursor:pointer; }
a.score-sys:hover { color:#93c5fd; }
.score-set { color:#94a3b8; font-size:.72rem; }

/* Blob-primary evidence (0.12): headline pill, mounted findings, verbatim source-table blob */
.m-headline { margin-top:8px; padding:6px 10px; border-left:3px solid #2dd4bf; background:#0f2a2a; color:#d1faf4; font-size:.82rem; border-radius:4px; }
.m-findings { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; }
a.m-finding { font-size:.72rem; color:#cbd5e1; background:#1e293b; border:1px solid #334155; padding:2px 8px; border-radius:10px; text-decoration:none; cursor:pointer; }
a.m-finding:hover { color:#93c5fd; border-color:#3b82f6; }
.m-tableref { margin-top:8px; font-size:.72rem; color:#64748b; font-style:italic; }
.kb-measure-table { margin-top:10px; }
.kb-mt-cap { font-size:.72rem; color:#94a3b8; margin-bottom:5px; font-weight:600; }
.kb-mt-src { display:inline-block; margin-top:4px; font-size:.6rem; color:#5b6b85; font-family:ui-monospace,monospace; }
.kb-mt-wrap { overflow-x:auto; border:1px solid #25324a; border-radius:6px; }
.kb-mt-raw { margin:0; padding:6px 8px; font-size:.72rem; color:#94a3b8; white-space:pre-wrap; word-break:break-word; }
.kb-measure-table table { border-collapse:collapse; font-size:.74rem; width:100%; color:#cbd5e1; }
.kb-measure-table th, .kb-measure-table td { border:1px solid #1e293b; padding:3px 7px; text-align:left; white-space:nowrap; }
.kb-measure-table th { background:#16233c; color:#94a3b8; font-weight:700; }
.kb-measure-table tr:nth-child(even) td { background:#0e1726; }

/* References */
.refs-sec .sec-body { max-height:440px; overflow-y:auto; }
.ref { font-size:.78rem; color:#94a3b8; padding:5px 0; border-bottom:1px solid #16233c; }
.ref-id { color:#64748b; font-family:ui-monospace,monospace; font-size:.7rem; margin-right:6px; }
.ref-title { color:#cbd5e1; }
.ref.central { border-left:2px solid #fbbf24; padding-left:8px; }
.ref-roles { color:#475569; font-size:.68rem; margin-left:6px; }
.ref-links { margin-top:3px; }
.ref-link { color:#60a5fa; font-size:.72rem; margin-right:8px; cursor:pointer; }
.ref-link:hover { text-decoration:underline; }
.ref-blob { margin-top:10px; padding-top:8px; border-top:1px solid #16233c; }
.ref-blob-head { font-size:.72rem; color:#64748b; font-weight:600; margin-bottom:5px; }
.ref-blob-warn { color:#fbbf24; }
.ref-blob-body { font-size:.72rem; color:#94a3b8; white-space:pre-wrap; word-break:break-word; margin:0; font-family:inherit; }
.ref-blob-list { list-style:none; margin:0; padding:0; }
.ref-blob-item { font-size:.72rem; color:#94a3b8; line-height:1.5; padding:4px 0 4px 1.7em; text-indent:-1.7em; word-break:break-word; border-bottom:1px solid #0e1726; }
.ref-blob-item:last-child { border-bottom:none; }
.ref-blob-mark { color:#64748b; font-family:ui-monospace,monospace; }

/* Citation badges */
.cite-badges { display:inline-flex; gap:3px; }
.cite-badge { color:#fbbf24; background:#3a2a0c; font-family:ui-monospace,monospace; font-size:.64rem; padding:1px 5px; border-radius:3px; cursor:pointer; }
.cite-badge:hover { background:#5a3f12; }

/* Notes */
.notes { margin-top:18px; background:#0f1829; border:1px solid #1e293b; border-radius:10px; padding:14px 16px; }
.notes h2 { font-size:.84rem; color:#94a3b8; margin-bottom:8px; }
.notes li { font-size:.78rem; color:#64748b; list-style:none; padding-left:14px; position:relative; margin-bottom:3px; }
.notes li::before { content:"\\2022"; position:absolute; left:0; color:#475569; }
"""

JS_CODE = r"""
(function () {
  var cur = null;
  function clearFocus() {
    document.body.classList.remove('focusing');
    var marked = document.querySelectorAll('.focus, .related');
    for (var i = 0; i < marked.length; i++) marked[i].classList.remove('focus', 'related');
    cur = null;
  }
  function focusUnit(id, navigate) {
    var card = document.getElementById('u-' + id);
    if (!card) return;
    clearFocus();
    document.body.classList.add('focusing');
    card.classList.add('focus');
    var rel = (card.getAttribute('data-rel') || '').split(' ');
    for (var i = 0; i < rel.length; i++) {
      if (!rel[i]) continue;
      var n = document.getElementById('u-' + rel[i]);
      if (n) n.classList.add('related');
    }
    cur = id;
    if (navigate) {
      card.classList.add('open');
      var sec = card.closest('.sec');
      if (sec) sec.classList.remove('collapsed');
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  document.addEventListener('click', function (ev) {
    var peer = ev.target.closest('[data-peer]');
    if (peer) { focusUnit(peer.getAttribute('data-peer'), true); ev.preventDefault(); return; }
    var cite = ev.target.closest('.cite-badge');
    if (cite) {
      var refs = document.getElementById('references');
      if (refs) { refs.classList.remove('collapsed'); refs.scrollIntoView({ behavior: 'smooth' }); }
      return;
    }
    var head = ev.target.closest('.sec-head');
    if (head) { head.parentElement.classList.toggle('collapsed'); return; }
    var unit = ev.target.closest('.unit');
    if (unit) { unit.classList.toggle('open'); focusUnit(unit.getAttribute('data-uid'), false); return; }
    clearFocus();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') clearFocus(); });
})();
"""


# --- CLI ---

def main() -> None:
    parser = argparse.ArgumentParser(description="Render a section-IR extraction to a self-contained HTML page")
    parser.add_argument("input", type=Path, help="Extraction JSON file or production output directory")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path (default: alongside input)")
    parser.add_argument("--metadata", type=Path, default=None, help="Metadata JSON sidecar")
    parser.add_argument("--references", type=Path, default=None, help="References JSON sidecar")
    parser.add_argument("--open", action="store_true", help="Open the rendered page in a browser")
    args = parser.parse_args()

    pipeline_data = load_pipeline_data(args.input, args.metadata, args.references)

    if args.output:
        output_path = args.output
    elif args.input.is_dir():
        output_path = args.input / "extraction.html"
    else:
        output_path = args.input.with_suffix(".html")

    html_out = render_html(pipeline_data)
    output_path.write_text(html_out, encoding="utf-8")
    print(f"Rendered: {output_path} ({len(html_out):,} bytes)")

    if args.open:
        webbrowser.open(output_path.resolve().as_uri())


if __name__ == "__main__":
    main()
