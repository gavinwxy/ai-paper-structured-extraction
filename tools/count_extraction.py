#!/usr/bin/env python3
"""Count nodes (entities) and relations in section-IR extraction outputs.

The redesign's headline metric is raw recall: how many entities and how many
relations the pipeline captures. This tool measures that on existing on-disk
extraction JSON so a before/after comparison costs no API calls.

"Relations" live in different places across IR versions, and this tool counts all
of them so a 0.6 (before) batch and a 0.7 (after) batch are directly comparable:
  - top-level ``relations[]`` (section-ir-0.7: part_of / compares_to / evaluates /
    measured_on / about / supports) — the new global edge list
  - per-section ``links[]`` (section-ir-0.6: supports / part_of / compares_to)
  - field-encoded edges (Metric.subject_id, Claim.target_ids, Metric.evaluated_on
    — all promoted to global relations in 0.7 — plus the metric's local scoping
    field, named context_ids in 0.6/early-0.7 and setting_ids after the rename)
``Method.components`` is skipped: it is a derived projection of part_of and would
double-count. The relation total is the union of whatever edges a file carries, so
the same paper scores comparably whichever IR version produced it.

Usage:
    python tools/count_extraction.py <dir-or-file> [<dir-or-file> ...]
Each argument is a batch directory (walked for ``*extraction.json``) or a single
extraction JSON. One summary row per argument. Each logical paper counts once:
archived baselines / nested re-runs / backup copies map to the same paper key,
the shallowest copy wins, and the skipped duplicates are reported on stderr —
otherwise n_papers inflates and every per-paper average is silently skewed.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

UNIT_TYPES = ["Method", "ExperimentSetup", "Measure", "Finding", "Problem"]
FIELD_EDGES = ["subject_id", "target_ids", "evaluated_on", "context_ids", "setup_ids"]


def _paper_key(path: Path) -> str:
    """Logical paper identity for an extraction file.

    Two on-disk layouts exist: per-paper dirs holding the stage-numbered
    ``06_extraction.json`` (identity = parent dir name) and flat batch dirs
    holding ``<paper>_extraction.json`` (identity = stem). A stem that is empty
    or purely numeric once ``extraction`` is stripped is a stage number, not a
    paper id, so the parent dir names the paper.
    """
    base = path.name[: -len(".json")]
    base = base[: -len("extraction")].rstrip("_-. ")
    if base and not base.isdigit():
        return base
    return path.parent.name


def iter_extraction_files(arg: str) -> list[Path]:
    path = Path(arg)
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    by_key: dict[str, list[Path]] = {}
    for p in sorted(path.rglob("*extraction.json")):
        by_key.setdefault(_paper_key(p), []).append(p)
    files: list[Path] = []
    for key, copies in by_key.items():
        # Shallowest copy wins (archives/backups nest deeper); ties break
        # lexicographically so the choice is deterministic.
        copies.sort(key=lambda p: (len(p.relative_to(path).parts), str(p)))
        files.append(copies[0])
        for dup in copies[1:]:
            print(
                f"WARNING: duplicate extraction for paper '{key}': "
                f"counting {copies[0]}, skipping {dup}",
                file=sys.stderr,
            )
    return sorted(files)


def count_one(extraction: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    sections = extraction.get("sections", []) or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        for unit in section.get("units", []) or []:
            if not isinstance(unit, dict):
                continue
            utype = unit.get("type")
            if utype in UNIT_TYPES:
                counts[f"unit:{utype}"] += 1
                counts["nodes"] += 1
            # field-encoded edges
            for field in FIELD_EDGES:
                value = unit.get(field)
                if isinstance(value, str) and value:
                    counts[f"edge:{field}"] += 1
                    counts["field_edges"] += 1
                elif isinstance(value, list):
                    n = sum(1 for v in value if isinstance(v, str) and v)
                    counts[f"edge:{field}"] += n
                    counts["field_edges"] += n
        for link in section.get("links", []) or []:
            if isinstance(link, dict) and link.get("relation"):
                counts[f"link:{link['relation']}"] += 1
                counts["links"] += 1
    # Top-level global relations (section-ir-0.7).
    for relation in extraction.get("relations", []) or []:
        if isinstance(relation, dict) and relation.get("relation"):
            counts[f"rel:{relation['relation']}"] += 1
            counts["relations"] += 1
    counts["relations_total"] = counts["relations"] + counts["links"] + counts["field_edges"]
    return dict(counts)


def summarize(arg: str) -> None:
    files = iter_extraction_files(arg)
    if not files:
        print(f"\n## {arg}\n  (no extraction files found)")
        return
    agg: Counter[str] = Counter()
    n_papers = 0
    for f in files:
        try:
            extraction = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # pipeline.json wraps extraction under an "extraction" key
        if "sections" not in extraction and isinstance(extraction.get("extraction"), dict):
            extraction = extraction["extraction"]
        if "sections" not in extraction:
            continue
        n_papers += 1
        for key, value in count_one(extraction).items():
            agg[key] += value

    if n_papers == 0:
        print(f"\n## {arg}\n  (no parseable extractions)")
        return

    def per(key: str) -> str:
        return f"{agg[key] / n_papers:.1f}"

    print(f"\n## {arg}  (n={n_papers} papers)")
    print(f"  NODES   total={agg['nodes']:5d}  per-paper={per('nodes')}")
    for utype in UNIT_TYPES:
        k = f"unit:{utype}"
        if agg[k]:
            print(f"            {utype:10s} {agg[k]:5d}  ({per(k)}/paper)")
    rel_types = ["part_of", "compares_to", "evaluates", "about", "supports", "motivates", "resolves"]
    if agg["relations"]:
        print(f"  RELATIONS (top-level) total={agg['relations']:5d}  per-paper={per('relations')}"
              f"   [" + " ".join(f"{rt}={agg[f'rel:{rt}']}" for rt in rel_types if agg[f'rel:{rt}']) + "]")
    if agg["links"]:
        print(f"  LINKS (section-local) total={agg['links']:5d}  per-paper={per('links')}"
              f"   [supports={agg['link:supports']} part_of={agg['link:part_of']} compares_to={agg['link:compares_to']}]")
    print(f"  FIELD-EDGES total={agg['field_edges']:5d}  per-paper={per('field_edges')}"
          f"   [" + " ".join(f"{e.split(':')[0] if ':' in e else e}={agg[f'edge:{e}']}" for e in FIELD_EDGES) + "]")
    print(f"  RELATIONS_TOTAL (relations+links+field_edges) total={agg['relations_total']:5d}  per-paper={per('relations_total')}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    for arg in args:
        summarize(arg)


if __name__ == "__main__":
    main()
