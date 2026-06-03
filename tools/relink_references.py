#!/usr/bin/env python3
"""Re-link references to spine units on existing production outputs, in place.

The cite-key join in `reconcile_reference_units` is what fills each reference's
`relation.provides_unit_ids` (and backfills the FG-12 dependency/comparison edges onto
`extraction["relations"]`). An earlier `_normalize_cite_key` only stripped brackets/whitespace,
so author-year papers — where the census echoes the in-text marker verbatim ("Warburg et al.,
2021") while the references pass compacts it ("Warburg2021") — lost ~half their cite-key joins.
With the author-year-aware normalizer now in `section_pipeline`, this script replays the
deterministic reconcile over an already-extracted batch so the existing corpus picks up the
recovered links without re-running any LLM stage.

It reads each paper dir's 01_census.json / 03_references.json / 06_extraction.json, replays
`reconcile_reference_units`, and (unless --dry-run) rewrites 03_references.json and
06_extraction.json when they change. With --render it also rebuilds extraction.html.

Usage:
    python tools/relink_references.py <output_root> [--dry-run] [--render]
    python tools/relink_references.py production-outputs/ros_ai_8x100_v0.10 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from production.outputs import save_json  # noqa: E402
from section_pipeline import reconcile_reference_units  # noqa: E402


def _load(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _linked_ref_count(references: dict | None) -> int:
    if not isinstance(references, dict):
        return 0
    return sum(
        1
        for r in references.get("references") or []
        if isinstance(r, dict)
        and isinstance(r.get("relation"), dict)
        and r["relation"].get("provides_unit_ids")
    )


def relink_paper(paper_dir: Path, *, dry_run: bool, render: bool) -> dict | None:
    """Replay reconcile on one paper dir. Returns a stats dict, or None if not a paper dir."""
    census = _load(paper_dir / "01_census.json")
    references = _load(paper_dir / "03_references.json")
    extraction = _load(paper_dir / "06_extraction.json")
    if not (isinstance(references, dict) and isinstance(extraction, dict)):
        return None

    refs_before = _linked_ref_count(references)
    edges_before = len(extraction.get("relations") or [])
    refs_json_before = json.dumps(references, ensure_ascii=False, sort_keys=True)
    ext_json_before = json.dumps(extraction, ensure_ascii=False, sort_keys=True)

    reconcile_reference_units(references, extraction, census)

    refs_after = _linked_ref_count(references)
    edges_after = len(extraction.get("relations") or [])
    refs_changed = json.dumps(references, ensure_ascii=False, sort_keys=True) != refs_json_before
    ext_changed = json.dumps(extraction, ensure_ascii=False, sort_keys=True) != ext_json_before

    if not dry_run and (refs_changed or ext_changed):
        if refs_changed:
            save_json(paper_dir / "03_references.json", references)
        if ext_changed:
            save_json(paper_dir / "06_extraction.json", extraction)
        if render and (refs_changed or ext_changed):
            try:
                from tools.render_extraction import load_pipeline_data, render_html

                pipeline_data = load_pipeline_data(paper_dir)
                (paper_dir / "extraction.html").write_text(
                    render_html(pipeline_data), encoding="utf-8"
                )
            except Exception as exc:  # rendering is best-effort; JSON is the source of truth
                print(f"  ! render failed for {paper_dir.name}: {exc}", file=sys.stderr)

    return {
        "paper": paper_dir.name,
        "refs_before": refs_before,
        "refs_after": refs_after,
        "edges_before": edges_before,
        "edges_after": edges_after,
        "changed": refs_changed or ext_changed,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Output root containing per-paper subdirectories")
    ap.add_argument("--dry-run", action="store_true", help="Report only; do not write files")
    ap.add_argument("--render", action="store_true", help="Also rebuild extraction.html for changed papers")
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"Not a directory: {args.root}", file=sys.stderr)
        return 2

    paper_dirs = sorted(p for p in args.root.iterdir() if p.is_dir())
    rows = []
    for pdir in paper_dirs:
        stats = relink_paper(pdir, dry_run=args.dry_run, render=args.render)
        if stats is not None:
            rows.append(stats)

    changed = [r for r in rows if r["changed"]]
    refs_gained = sum(r["refs_after"] - r["refs_before"] for r in rows)
    edges_gained = sum(r["edges_after"] - r["edges_before"] for r in rows)
    refs_before_total = sum(r["refs_before"] for r in rows)
    refs_after_total = sum(r["refs_after"] for r in rows)

    mode = "DRY-RUN (no files written)" if args.dry_run else "WROTE changes"
    print(f"\n{mode}")
    print(f"  papers scanned      : {len(rows)}")
    print(f"  papers changed      : {len(changed)}")
    print(f"  linked refs  before : {refs_before_total}")
    print(f"  linked refs  after  : {refs_after_total}  ({refs_gained:+d})")
    print(f"  graph edges  gained : {edges_gained:+d}")
    if changed:
        top = sorted(changed, key=lambda r: r["refs_after"] - r["refs_before"], reverse=True)[:10]
        print("\n  Top papers by newly-linked references:")
        for r in top:
            print(f"    +{r['refs_after'] - r['refs_before']:>3}  {r['paper'][:72]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
