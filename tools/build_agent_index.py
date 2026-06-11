#!/usr/bin/env python3
"""Build corpus-level agent-retrieval artifacts over an existing extraction run.

The per-paper outputs are deep nested trees an agent must open and join file-by-file; this tool
emits the missing access layers (issues/agent-usability-report-2026-06-11.md, RF-06/09/10/19/20):

  <root>/_manifest.json      RF-19  data dictionary / file contracts (same as fresh runs emit);
                                    ir_version reflects the corpus's OBSERVED per-paper
                                    extraction_notes.ir_version (retrofit-skipped papers count),
                                    not the current pipeline version — mixed/missing versions
                                    stamp 'mixed'/'unknown' + an ir_version_observed distribution
  <root>/_catalog.jsonl      RF-20  one routing record per paper (title/venue/year/spine/facets)
  <root>/_cards.jsonl        RF-06  one denormalized retrieval card per unit (embed_text ready)
  <root>/_result_rows.jsonl  RF-09  one flat (system, dataset, metric, value) row per score —
                                    source='transcribed' (LLM scores, full setup/system join) +
                                    source='table_blob' (numeric cells lifted from the verbatim
                                    baseline tables; best-effort row/col labels, no id join)
  <root>/_entity_index.json  RF-10  cross-paper citation clusters on normalized reference title

By default it first RETROFITS each paper dir in place with the same deterministic enrichments
fresh pipeline runs now apply (additive, idempotent, 0 LLM): metadata venue/year backfill +
has_code/has_data (RF-01), the 04_relations subset note (RF-03), score value_num +
has_quantitative_payload (RF-04), an always-present score_fidelity block (RF-05),
marker_namespaces (RF-11-lite), and the cite-key reconcile replay that stamps unit ref_ids
(RF-10 first half). 07_validation.json is refreshed from a re-run of the validator.

Usage:
    python tools/build_agent_index.py <output_root> [--no-retrofit] [--flatten-sections]
    python tools/build_agent_index.py production-outputs/agent_index_validation --flatten-sections
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from production.outputs import save_json  # noqa: E402
from section_pipeline import (  # noqa: E402
    ACCEPTED_IR_VERSIONS,
    CONTRIBUTION_ROLES,
    IR_VERSION,
    MARKER_NAMESPACES,
    STAGE_B_RELATIONS_NOTE,
    _annotate_quantitative_payload,
    _normalize_name,
    _numeric_keys,
    _parse_value_num,
    build_output_manifest,
    enrich_metadata,
    reconcile_reference_units,
    validate_section_ir,
)

# "Long Form (ACRO)" — the parenthetical must look like a short label (acronym/model name), not
# prose: no spaces beyond 3 tokens, and at least one uppercase letter or digit.
_ALIAS_PAREN_RE = re.compile(r"^(?P<long>.+?)\s*\((?P<short>[^()]{1,40})\)\s*$")


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def derive_aliases(name: Any) -> list[str]:
    """RF-13 (deterministic part): split a 'Long Form (ACRO)' unit name into both query surfaces.

    Returns [] when the name carries no recognizable parenthetical alias."""
    if not isinstance(name, str):
        return []
    match = _ALIAS_PAREN_RE.match(name.strip())
    if not match:
        return []
    long_form = match.group("long").strip()
    short_form = match.group("short").strip()
    if not long_form or not short_form:
        return []
    if len(short_form.split()) > 3 or not re.search(r"[A-Z0-9]", short_form):
        return []  # parenthetical is prose (e.g. "(ours)") — not an alias
    return [long_form, short_form]


def _iter_units(extraction: dict[str, Any]):
    for section in extraction.get("sections") or []:
        if not isinstance(section, dict):
            continue
        stype = section.get("section_type")
        for unit in section.get("units") or []:
            if isinstance(unit, dict):
                yield stype, unit


def _census_index(census: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    nodes = (census or {}).get("nodes") if isinstance(census, dict) else None
    return {
        node["node_id"]: node
        for node in nodes or []
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }


# ---------------------------------------------------------------------------
# Retrofit (in-place, additive, idempotent)
# ---------------------------------------------------------------------------

def retrofit_paper(
    paper_dir: Path,
    *,
    flatten_sections: bool,
    default_venue: str | None = None,
    accepted_versions: set[str] | None = ACCEPTED_IR_VERSIONS,
) -> dict[str, Any]:
    """Apply the deterministic agent-readiness enrichments to one already-extracted paper dir.

    Version gate (RF-21): only corpora whose ``extraction_notes.ir_version`` is in
    ``accepted_versions`` are touched. An out-of-version corpus (e.g. section-ir-0.10) is left
    completely untouched — otherwise retrofit would re-run the CURRENT ``validate_section_ir`` and
    overwrite ``07_validation.json`` with ``valid: false`` (its ir_version is not in
    ACCEPTED_IR_VERSIONS), silently corrupting a previously-valid corpus. Pass ``accepted_versions=
    None`` to retrofit regardless of version (the deliberate override).
    """
    stats = {"paper": paper_dir.name, "changed_files": []}

    extraction = _load(paper_dir / "06_extraction.json")
    if accepted_versions is not None:
        ir_version = (
            (extraction.get("extraction_notes") or {}).get("ir_version")
            if isinstance(extraction, dict)
            else None
        )
        if ir_version not in accepted_versions:
            stats["skipped"] = f"ir_version {ir_version!r} not in {sorted(accepted_versions)}"
            return stats

    metadata = _load(paper_dir / "02_metadata.json")
    before = _dumps(metadata)
    metadata = enrich_metadata(metadata, paper_dir.name, default_venue=default_venue)
    if _dumps(metadata) != before:
        save_json(paper_dir / "02_metadata.json", metadata)
        stats["changed_files"].append("02_metadata.json")

    relations_file = _load(paper_dir / "04_relations.json")
    if isinstance(relations_file, dict) and "note" not in relations_file:
        relations_file["note"] = STAGE_B_RELATIONS_NOTE
        save_json(paper_dir / "04_relations.json", relations_file)
        stats["changed_files"].append("04_relations.json")

    census = _load(paper_dir / "01_census.json")
    references = _load(paper_dir / "03_references.json")
    if isinstance(extraction, dict):
        ext_before = _dumps(extraction)
        refs_before = _dumps(references)
        _annotate_quantitative_payload(extraction.get("sections") or [])
        notes = extraction.setdefault("extraction_notes", {})
        if isinstance(notes, dict):
            notes.setdefault("marker_namespaces", dict(MARKER_NAMESPACES))
            if "score_fidelity" not in notes:
                notes["score_fidelity"] = {
                    "checked": False,
                    "located_pct": None,
                    "reason": "not checked at extraction time (retrofitted)",
                }
        if isinstance(references, dict):
            # Replays the cite-key reconcile: refreshes provides_unit_ids/backfilled edges AND
            # stamps unit ref_ids (the reverse join fresh runs now write).
            reconcile_reference_units(references, extraction, census)
        if _dumps(references) != refs_before:
            save_json(paper_dir / "03_references.json", references)
            stats["changed_files"].append("03_references.json")
        if _dumps(extraction) != ext_before:
            save_json(paper_dir / "06_extraction.json", extraction)
            stats["changed_files"].append("06_extraction.json")

        issues = validate_section_ir(extraction, census=census)
        validation = {"issues": issues, "valid": len(issues) == 0}
        if _dumps(_load(paper_dir / "07_validation.json")) != _dumps(validation):
            save_json(paper_dir / "07_validation.json", validation)
            stats["changed_files"].append("07_validation.json")
        stats["valid"] = validation["valid"]

    if flatten_sections:
        for section_file in sorted((paper_dir / "05_sections").glob("*.json")):
            data = _load(section_file)
            if isinstance(data, dict) and set(data.keys()) == {"section"} and isinstance(data["section"], dict):
                save_json(section_file, data["section"])
                stats["changed_files"].append(f"05_sections/{section_file.name}")

    return stats


# ---------------------------------------------------------------------------
# Corpus artifacts
# ---------------------------------------------------------------------------

def build_catalog_row(
    paper_id: str,
    census: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    extraction: dict[str, Any],
    valid: bool | None,
) -> dict[str, Any]:
    metadata = metadata if isinstance(metadata, dict) else {}
    spine = (census or {}).get("spine_summary") if isinstance(census, dict) else None
    spine = spine if isinstance(spine, dict) else {}
    document = extraction.get("document") if isinstance(extraction.get("document"), dict) else {}

    problem_description = None
    datasets: list[str] = []
    metrics: list[str] = []
    contribution_names: list[str] = []
    n_units = 0
    for _stype, unit in _iter_units(extraction):
        n_units += 1
        utype = unit.get("type")
        if utype == "Problem" and problem_description is None:
            problem_description = unit.get("description")
        elif utype == "ExperimentSetup" and unit.get("role") in {"dataset", "benchmark"}:
            if unit.get("name") and unit["name"] not in datasets:
                datasets.append(unit["name"])
        elif utype == "Measure":
            if unit.get("name") and unit["name"] not in metrics:
                metrics.append(unit["name"])
        elif utype == "Method" and unit.get("role") in CONTRIBUTION_ROLES:
            if unit.get("name") and unit["name"] not in contribution_names:
                contribution_names.append(unit["name"])

    authors = [
        a.get("name")
        for a in metadata.get("authors") or []
        if isinstance(a, dict) and a.get("name")
    ]
    resource_urls = [
        r.get("url")
        for r in metadata.get("resources") or []
        if isinstance(r, dict) and r.get("url")
    ]
    contribution_aliases = sorted(
        {alias for name in contribution_names for alias in derive_aliases(name)}
    )
    return {
        "paper_id": paper_id,
        "title": metadata.get("title") or document.get("title"),
        # RF-07 census facets (0.13+; null on older extractions)
        "topics": document.get("topics"),
        "tasks": document.get("tasks"),
        "domain": document.get("domain"),
        "paper_type": document.get("role"),
        "venue": metadata.get("venue"),
        "year": metadata.get("year"),
        "venue_source": metadata.get("venue_source"),
        "year_source": metadata.get("year_source"),
        "authors": authors,
        "has_code": metadata.get("has_code"),
        "has_data": metadata.get("has_data"),
        "resource_urls": resource_urls,
        "central_contribution": spine.get("central_contribution"),
        "argument_flow": spine.get("argument_flow"),
        "headline_result": spine.get("headline_result"),
        "problem_description": problem_description,
        "contribution_names": contribution_names,
        "contribution_aliases": contribution_aliases,
        "datasets": datasets,
        "metrics": metrics,
        "n_units": n_units,
        "n_relations": len(extraction.get("relations") or []),
        "valid": valid,
    }


def _card_text(unit: dict[str, Any], gloss: str | None) -> str:
    utype = unit.get("type")
    if utype == "Problem":
        return unit.get("description") or gloss or ""
    if utype == "Finding":
        text = unit.get("statement") or ""
        effect = unit.get("effect_size")
        return f"{text} (effect: {effect})" if effect else text
    if utype == "Measure":
        text = unit.get("headline_result") or gloss or ""
        unit_label = unit.get("unit")
        return f"{text} [unit: {unit_label}]" if unit_label and unit_label != "unitless" else text
    # Method / ExperimentSetup
    return unit.get("description") or gloss or ""


def build_cards(
    paper_id: str,
    paper_title: str | None,
    census: dict[str, Any] | None,
    extraction: dict[str, Any],
) -> list[dict[str, Any]]:
    nodes = _census_index(census)
    cards: list[dict[str, Any]] = []
    for stype, unit in _iter_units(extraction):
        uid = unit.get("id")
        node = nodes.get(uid, {})
        gloss = node.get("gloss")
        name = unit.get("name") or node.get("name") or uid
        text = _card_text(unit, gloss)
        aliases = derive_aliases(name)
        role = unit.get("role") or node.get("role")
        head = f"{unit.get('type')}/{role}" if role else f"{unit.get('type')}"
        embed_text = f"{paper_title or paper_id} | {head}: {name}"
        if text:
            embed_text += f" — {text}"
        card = {
            "paper_id": paper_id,
            "paper_title": paper_title,
            "unit_id": uid,
            "section": stype,
            "type": unit.get("type"),
            "role": role,
            "name": name,
            "text": text,
            "gloss": gloss,
            "aliases": aliases,
            "salience": node.get("salience"),
            "cite_keys": unit.get("cite_keys") or node.get("cite_keys") or [],
            "ref_ids": unit.get("ref_ids") or [],
            "embed_text": embed_text,
        }
        cards.append(card)
    return cards


def build_result_rows(paper_id: str, extraction: dict[str, Any]) -> list[dict[str, Any]]:
    units_by_id = {u.get("id"): u for _s, u in _iter_units(extraction) if u.get("id")}
    rows: list[dict[str, Any]] = []
    for _stype, unit in _iter_units(extraction):
        if unit.get("type") != "Measure":
            continue
        metric = unit.get("name")
        direction = unit.get("comparison_direction")
        table_role = unit.get("table_role")
        for score in unit.get("scores") or []:
            if not isinstance(score, dict):
                continue
            setup = units_by_id.get(score.get("setup_id") or "", {})
            system = units_by_id.get(score.get("system_id") or "", {})
            setup_name = setup.get("name")
            dataset = setup_name if setup.get("role") in {"dataset", "benchmark"} else None
            system_name = system.get("name") or score.get("variant")
            value_num = score.get("value_num")
            if value_num is None and "value_num" not in score:
                value_num = _parse_value_num(score.get("value"))
            rows.append({
                "paper_id": paper_id,
                "source": "transcribed",
                "measure_id": unit.get("id"),
                "metric": metric,
                "metric_norm": _normalize_name(metric),
                "unit": unit.get("unit"),
                "dataset": dataset,
                "dataset_norm": _normalize_name(dataset) if dataset else None,
                "setup": setup_name,
                "setup_id": score.get("setup_id") or None,
                "system": system_name,
                "system_id": score.get("system_id") or None,
                "system_role": system.get("role"),
                "is_paper_contribution": system.get("role") in CONTRIBUTION_ROLES,
                "variant": score.get("variant"),
                "value_raw": score.get("value"),
                "value_num": value_num,
                "variance": score.get("variance") or None,
                "direction": direction,
                "table_role": table_role,
            })
    return rows


# ---------------------------------------------------------------------------
# RF-09 second half: lift baseline rows out of the verbatim table blobs
# ---------------------------------------------------------------------------

class _TableGridParser(HTMLParser):
    """Parse table html into per-table grids of cell dicts {text, is_header, rowspan, colspan}.

    A source_tables entry may concatenate several <table> blobs under one marker — each becomes
    its own grid. Best-effort on malformed markup (a dangling row is flushed, a cell outside a
    <tr> opens an implicit row)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.grids: list[list[list[dict[str, Any]]]] = []
        self._rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None
        self._buf: list[str] = []

    @staticmethod
    def _span(value: Any) -> int:
        try:
            return max(1, int(str(value)))
        except (TypeError, ValueError):
            return 1

    def _flush_table(self) -> None:
        if self._row:
            self._rows.append(self._row)
            self._row = None
        if self._rows:
            self.grids.append(self._rows)
            self._rows = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._flush_table()
        elif tag == "tr":
            if self._row:
                self._rows.append(self._row)
            self._row = []
        elif tag in ("td", "th"):
            amap = dict(attrs)
            self._cell = {
                "is_header": tag == "th",
                "rowspan": self._span(amap.get("rowspan", 1)),
                "colspan": self._span(amap.get("colspan", 1)),
            }
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            self._cell["text"] = " ".join("".join(self._buf).split())
            if self._row is None:
                self._row = []
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._flush_table()

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._buf.append(data)


def _parse_table_grids(table_html: str) -> list[list[list[dict[str, Any]]]]:
    parser = _TableGridParser()
    try:
        parser.feed(table_html or "")
        parser.close()
    except Exception:
        return []
    parser._flush_table()
    return [g for g in parser.grids if g]


def _expand_grid(rows: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    """Expand rowspan/colspan into a rectangular grid (cell objects shared across spanned slots)."""
    grid: list[list[dict[str, Any]]] = []
    pending: dict[int, tuple[dict[str, Any], int]] = {}  # col -> (cell, rows remaining below)
    for raw_row in rows:
        out: list[dict[str, Any]] = []
        col = 0

        def _fill() -> None:
            nonlocal col
            while col in pending:
                cell, remaining = pending.pop(col)
                out.append(cell)
                if remaining > 1:
                    pending[col] = (cell, remaining - 1)
                col += 1

        _fill()
        for cell in raw_row:
            _fill()
            for _ in range(cell["colspan"]):
                out.append(cell)
                if cell["rowspan"] > 1:
                    pending[col] = (cell, cell["rowspan"] - 1)
                col += 1
            _fill()
        grid.append(out)
    return grid


def _split_header(grid: list[list[dict[str, Any]]]) -> tuple[list[str | None], int]:
    """Detect leading header rows; return (per-column labels, body start index).

    A row is a header when its cells are <th>-tagged, or (parser fallback — many corpora emit
    headers as plain <td>) when at most ~25% of its non-empty cells parse as numbers, limited to
    the first 3 rows so a qualitative body never swallows the whole table."""
    n_header = 0
    for i, row in enumerate(grid[:3]):
        texts = [c["text"] for c in row if c["text"]]
        if not texts:
            break
        numeric = sum(1 for t in texts if _parse_value_num(t) is not None)
        all_th = all(c["is_header"] for c in row if c["text"])
        if all_th or numeric <= max(0, len(texts) // 4):
            n_header = i + 1
        else:
            break
    width = max((len(r) for r in grid), default=0)
    labels: list[str | None] = []
    for col in range(width):
        parts: list[str] = []
        for row in grid[:n_header]:
            if col < len(row):
                text = row[col]["text"]
                if text and (not parts or parts[-1] != text):
                    parts.append(text)
        labels.append(" / ".join(parts) if parts else None)
    return labels, n_header


def _transcribed_value_keys(extraction: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for _stype, unit in _iter_units(extraction):
        if unit.get("type") != "Measure":
            continue
        for score in unit.get("scores") or []:
            if isinstance(score, dict):
                keys.update(_numeric_keys(str(score.get("value", ""))))
    return keys


def lift_blob_rows(paper_id: str, extraction: dict[str, Any]) -> list[dict[str, Any]]:
    """RF-09 second half: parse extraction_notes.source_tables html into flat typed rows.

    In blob-primary mode the contribution rows are LLM-transcribed (source='transcribed') and the
    baseline/competitor grid stays verbatim html — opaque to a leaderboard query. This lifts every
    numeric data cell into the same row shape, best-effort: row_label = the row's first non-numeric
    cell, col_label from the detected header rows. `value_in_transcribed` marks cells whose value
    also appears in a structured score (likely the same number seen twice — filter on it for the
    unmatched-baseline view). Lifted rows never claim a system join: system_id/ is_paper_contribution
    stay null."""
    notes = extraction.get("extraction_notes") or {}
    source_tables = notes.get("source_tables") if isinstance(notes, dict) else None
    if not isinstance(source_tables, dict) or not source_tables:
        return []
    transcribed = _transcribed_value_keys(extraction)
    rows: list[dict[str, Any]] = []
    for marker, table in sorted(source_tables.items()):
        if not isinstance(table, dict):
            continue
        caption = (table.get("caption") or "").strip() or None
        for grid_rows in _parse_table_grids(table.get("html", "")):
            grid = _expand_grid(grid_rows)
            labels, body_start = _split_header(grid)
            body = grid[body_start:]
            # A body cell spanning rows in column 0 is a row-group label (e.g. a 'Weak/Full
            # supervision' band over method rows) — _expand_grid carries it into every spanned
            # row, where it would shadow the real per-row name. Treat column 0 as a group column
            # for the whole table (single-row groups carry rowspan=1, so detection is per-grid).
            group_col = any(row and row[0]["rowspan"] > 1 for row in body)
            for row in body:
                seen: set[int] = set()  # colspan/rowspan expansion shares cell objects
                leading: list[dict[str, Any]] = []  # distinct non-numeric cells among row[:2]
                for cell in row[:2]:
                    if cell["text"] and _parse_value_num(cell["text"]) is None \
                            and all(cell is not c for c in leading):
                        leading.append(cell)
                if group_col and len(leading) == 2:
                    row_label = f"{leading[0]['text']} / {leading[1]['text']}"
                    label_cells = leading
                elif leading:
                    row_label = leading[0]["text"]
                    label_cells = leading[:1]
                else:
                    row_label = None
                    label_cells = []
                label_cell_ids = {id(c) for c in label_cells}
                for col, cell in enumerate(row):
                    if id(cell) in seen or id(cell) in label_cell_ids:
                        continue
                    seen.add(id(cell))
                    text = cell["text"]
                    if not text:
                        continue
                    value_num = _parse_value_num(text)
                    if value_num is None:
                        continue
                    keys = _numeric_keys(text)
                    rows.append({
                        "paper_id": paper_id,
                        "source": "table_blob",
                        "measure_id": None,
                        "metric": labels[col] if col < len(labels) else None,
                        "metric_norm": _normalize_name(labels[col]) if col < len(labels) and labels[col] else None,
                        "unit": None,
                        "dataset": None,
                        "dataset_norm": None,
                        "setup": None,
                        "setup_id": None,
                        "system": row_label,
                        "system_id": None,
                        "system_role": None,
                        "is_paper_contribution": None,
                        "variant": None,
                        "value_raw": text,
                        "value_num": value_num,
                        "variance": None,
                        "direction": None,
                        "table_role": "baseline",
                        "table_marker": marker or None,
                        "table_caption": caption,
                        "value_in_transcribed": bool(keys) and any(k in transcribed for k in keys),
                    })
    return rows


def build_entity_index(per_paper_refs: list[tuple[str, dict[str, Any] | None]]) -> dict[str, Any]:
    """RF-10: cluster cited works across papers on the normalized reference title — the only
    structured cross-paper join key the outputs carry (~92% of refs have a title)."""
    entities: dict[str, dict[str, Any]] = {}
    skipped_no_title = 0
    for paper_id, references in per_paper_refs:
        if not isinstance(references, dict):
            continue
        for ref in references.get("references") or []:
            if not isinstance(ref, dict):
                continue
            title = ref.get("title")
            norm = _normalize_name(title)
            if not norm:
                skipped_no_title += 1  # link-only stubs and title-less entries are not joinable
                continue
            relation = ref.get("relation") if isinstance(ref.get("relation"), dict) else {}
            record = entities.setdefault(norm, {
                "canonical_key": norm,
                "title": title,
                "surface_titles": [],
                "year": ref.get("year"),
                "venue": ref.get("venue"),
                "papers": [],
            })
            if title not in record["surface_titles"]:
                record["surface_titles"].append(title)
            record["papers"].append({
                "paper_id": paper_id,
                "ref_id": ref.get("id"),
                "roles": relation.get("roles") or [],
                "stance": relation.get("stance"),
                "salience": relation.get("salience"),
                "provides_unit_ids": relation.get("provides_unit_ids") or [],
            })
    ordered = sorted(entities.values(), key=lambda e: (-len(e["papers"]), e["canonical_key"]))
    return {
        "note": (
            "cited works clustered on normalized reference title; node/reference ids are "
            "paper-local — this file is the cross-paper join surface. Title-less entries "
            "(e.g. graph-consistency stubs) are not clustered."
        ),
        "n_entities": len(ordered),
        "n_skipped_no_title": skipped_no_title,
        "entities": ordered,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def stamp_observed_ir_version(
    manifest: dict[str, Any], observed_versions: list[str | None]
) -> str | None:
    """Replace the manifest's hardcoded current-pipeline ir_version with what the corpus carries.

    ``build_output_manifest`` stamps ``IR_VERSION``; over an older corpus (which the retrofit
    version gate deliberately leaves untouched) that would tell a consuming agent the wrong schema
    for the files beside it. Every catalogued paper's ``extraction_notes.ir_version`` counts as
    observed — including retrofit-skipped ones, because the manifest describes the corpus as it
    sits on disk. Uniform version → stamped verbatim. Mixed or missing versions → ``ir_version``
    becomes the sentinel ``'mixed'``/``'unknown'`` (never a version the corpus does not uniformly
    carry) and ``ir_version_observed`` records the {version: paper count} distribution. Returns a
    warning for stdout when the result differs from the current pipeline version, else None."""
    counts = Counter(v if isinstance(v, str) and v else "unknown" for v in observed_versions)
    if not counts:
        return None
    if len(counts) == 1 and "unknown" not in counts:
        version = next(iter(counts))
        manifest["ir_version"] = version
        if version == IR_VERSION:
            return None
        return (
            f"corpus ir_version is {version!r}, not the current pipeline {IR_VERSION!r} — "
            "manifest stamped with the observed version"
        )
    distribution = dict(sorted(counts.items()))
    manifest["ir_version"] = "mixed" if len(counts) > 1 else "unknown"
    manifest["ir_version_observed"] = distribution
    return (
        f"corpus ir_version is not uniform: {distribution} — manifest ir_version set to "
        f"{manifest['ir_version']!r} (per-paper counts in ir_version_observed)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Output root containing per-paper subdirectories")
    ap.add_argument("--no-retrofit", action="store_true",
                    help="Only build corpus artifacts; do not touch per-paper files")
    ap.add_argument("--flatten-sections", action="store_true",
                    help="Also rewrite legacy {'section': {...}}-wrapped 05_sections files flat")
    ap.add_argument("--default-venue", default=None,
                    help="Corpus-level venue fallback when dirnames carry no venue token "
                         "(stamped venue_source='corpus_default'); e.g. --default-venue CVPR")
    ap.add_argument("--retrofit-any-version", action="store_true",
                    help="Retrofit/revalidate paper dirs regardless of extraction_notes.ir_version. "
                         f"By default only {sorted(ACCEPTED_IR_VERSIONS)} are touched; an older "
                         "corpus is left untouched so its 07_validation.json is not flipped to "
                         "invalid by the current validator.")
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"Not a directory: {args.root}", file=sys.stderr)
        return 2

    paper_dirs = sorted(
        p for p in args.root.iterdir() if p.is_dir() and (p / "06_extraction.json").exists()
    )
    if not paper_dirs:
        print(f"No paper dirs (with 06_extraction.json) under {args.root}", file=sys.stderr)
        return 2

    catalog: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    per_paper_refs: list[tuple[str, dict[str, Any] | None]] = []
    observed_versions: list[str | None] = []
    retrofit_changed = 0
    retrofit_skipped = 0
    blob_refs_seen = False
    fidelity_checked_seen = False
    wrapped_sections_seen = False

    for pdir in paper_dirs:
        if not args.no_retrofit:
            stats = retrofit_paper(
                pdir,
                flatten_sections=args.flatten_sections,
                default_venue=args.default_venue,
                accepted_versions=None if args.retrofit_any_version else ACCEPTED_IR_VERSIONS,
            )
            if stats.get("skipped"):
                retrofit_skipped += 1
            elif stats["changed_files"]:
                retrofit_changed += 1

        census = _load(pdir / "01_census.json")
        metadata = _load(pdir / "02_metadata.json")
        references = _load(pdir / "03_references.json")
        extraction = _load(pdir / "06_extraction.json")
        validation = _load(pdir / "07_validation.json")
        if not isinstance(extraction, dict):
            continue
        notes = extraction.get("extraction_notes") or {}
        observed_versions.append(notes.get("ir_version"))
        blob_refs_seen = blob_refs_seen or bool(notes.get("blob_primary_references"))
        fidelity = notes.get("score_fidelity") or {}
        fidelity_checked_seen = fidelity_checked_seen or bool(fidelity.get("checked"))
        for section_file in (pdir / "05_sections").glob("*.json"):
            data = _load(section_file)
            if isinstance(data, dict) and set(data.keys()) == {"section"}:
                wrapped_sections_seen = True
            break

        valid = validation.get("valid") if isinstance(validation, dict) else None
        row = build_catalog_row(pdir.name, census, metadata, extraction, valid)
        catalog.append(row)
        cards.extend(build_cards(pdir.name, row.get("title"), census, extraction))
        result_rows.extend(build_result_rows(pdir.name, extraction))
        result_rows.extend(lift_blob_rows(pdir.name, extraction))
        per_paper_refs.append((pdir.name, references))
        n_refs = len((references or {}).get("references") or []) if isinstance(references, dict) else 0
        catalog[-1]["n_references"] = n_refs

    manifest = build_output_manifest(
        blob_primary_evidence=True,
        blob_primary_references=blob_refs_seen,
        verify_scores=fidelity_checked_seen,
        flattened_sections=not wrapped_sections_seen,
    )
    version_warning = stamp_observed_ir_version(manifest, observed_versions)
    if version_warning:
        print(f"WARNING: {version_warning}")
    save_json(args.root / "_manifest.json", manifest)
    _write_jsonl(args.root / "_catalog.jsonl", catalog)
    _write_jsonl(args.root / "_cards.jsonl", cards)
    _write_jsonl(args.root / "_result_rows.jsonl", result_rows)
    entity_index = build_entity_index(per_paper_refs)
    save_json(args.root / "_entity_index.json", entity_index)

    n_numeric = sum(1 for r in result_rows if r["value_num"] is not None)
    n_transcribed = sum(1 for r in result_rows if r["source"] == "transcribed")
    n_lifted = sum(1 for r in result_rows if r["source"] == "table_blob")
    n_lifted_new = sum(
        1 for r in result_rows
        if r["source"] == "table_blob" and not r.get("value_in_transcribed")
    )
    multi = [e for e in entity_index["entities"] if len({p["paper_id"] for p in e["papers"]}) > 1]
    print(f"papers indexed       : {len(catalog)}")
    if not args.no_retrofit:
        skipped_note = f", {retrofit_skipped} skipped (out-of-version)" if retrofit_skipped else ""
        print(f"papers retrofitted   : {retrofit_changed} changed{skipped_note}")
    print(f"catalog rows         : {len(catalog)} -> _catalog.jsonl")
    print(f"unit cards           : {len(cards)} -> _cards.jsonl")
    print(f"result rows          : {len(result_rows)} ({n_numeric} with value_num; "
          f"{n_transcribed} transcribed + {n_lifted} blob-lifted, {n_lifted_new} net-new) "
          f"-> _result_rows.jsonl")
    print(f"entity clusters      : {entity_index['n_entities']} ({len(multi)} cited by >1 paper) -> _entity_index.json")
    print(f"manifest             : _manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
