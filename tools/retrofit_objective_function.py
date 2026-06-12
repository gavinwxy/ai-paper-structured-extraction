#!/usr/bin/env python3
"""Migrate the retired `objective_function` Method field into formulas[] on existing outputs.

section-ir-0.14 absorbed the standalone `objective_function` field into `formulas[]` as the
entry tagged `role="objective"` (carrying the one-line description of what is optimized): the
two fields overlapped ontologically — 27.6% of objective-bearing Method units transcribed the
same expression in both — and the 1-cardinality field could not represent multi-objective
methods. Assembly migrates legacy payloads on fresh runs (`_clean_method_equations`); this
script replays that deterministic repair over an already-extracted corpus so existing outputs
converge on the unified shape without re-running any LLM stage.

For each paper dir it rewrites 06_extraction.json in place (unless --dry-run): each Method's
`objective_function` becomes a `role="objective"` formulas entry, expressions transcribed twice
are merged (objective tag/description land on the surviving entry), and blank stubs are
dropped. Migration warnings are appended to extraction_notes.uncertain_assignments. A paper
already at an accepted post-blob version (0.12/0.13) is re-stamped to the current IR_VERSION —
the migrated shape is exactly the 0.14 contract; older corpora (0.9/0.10) keep their version
tag since they predate other 0.12+ features. Idempotent: a second run changes nothing.

Usage:
    python tools/retrofit_objective_function.py <output_root> [--dry-run] [--render] [--validate]
    python tools/retrofit_objective_function.py production-outputs/ros_ai_8x100_v0.10 --dry-run
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
from section_pipeline import (  # noqa: E402
    IR_VERSION,
    _clean_method_equations,  # the assembly repair this script replays; deterministic + idempotent
    validate_section_ir,
)

# Versions whose only structural delta vs IR_VERSION is the objective_function unification:
# after migration the file satisfies the current contract, so the tag moves forward.
RESTAMPABLE_VERSIONS = {"section-ir-0.12", "section-ir-0.13"}


def _load(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def retrofit_paper(paper_dir: Path, *, dry_run: bool, render: bool, validate: bool) -> dict | None:
    """Migrate one paper dir. Returns a stats dict, or None if not a paper dir."""
    extraction = _load(paper_dir / "06_extraction.json")
    if not isinstance(extraction, dict) or not isinstance(extraction.get("sections"), list):
        return None

    before = json.dumps(extraction, ensure_ascii=False, sort_keys=True)
    warnings = _clean_method_equations(extraction["sections"])
    migrated = sum(1 for w in warnings if w.startswith("migrated objective_function"))
    deduped = sum(1 for w in warnings if w.startswith("deduplicated formula"))
    dropped = sum(1 for w in warnings if w.startswith("dropped"))

    notes = extraction.get("extraction_notes")
    if warnings and isinstance(notes, dict):
        existing = notes.get("uncertain_assignments")
        if isinstance(existing, list):
            existing.extend(w for w in warnings if w not in existing)
        else:
            notes["uncertain_assignments"] = list(warnings)
    if (
        isinstance(notes, dict)
        and notes.get("ir_version") in RESTAMPABLE_VERSIONS
        and json.dumps(extraction, ensure_ascii=False, sort_keys=True) != before
    ):
        notes["ir_version"] = IR_VERSION

    changed = json.dumps(extraction, ensure_ascii=False, sort_keys=True) != before
    issues = len(validate_section_ir(extraction, census=_load(paper_dir / "01_census.json"))) if validate else None

    if changed and not dry_run:
        save_json(paper_dir / "06_extraction.json", extraction)
        if render:
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
        "migrated": migrated,
        "deduped": deduped,
        "dropped": dropped,
        "changed": changed,
        "issues": issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Output root containing per-paper subdirectories")
    ap.add_argument("--dry-run", action="store_true", help="Report only; do not write files")
    ap.add_argument("--render", action="store_true", help="Also rebuild extraction.html for changed papers")
    ap.add_argument("--validate", action="store_true", help="Re-validate each extraction and report issue counts")
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"Not a directory: {args.root}", file=sys.stderr)
        return 2

    rows = []
    for pdir in sorted(p for p in args.root.iterdir() if p.is_dir()):
        stats = retrofit_paper(pdir, dry_run=args.dry_run, render=args.render, validate=args.validate)
        if stats is not None:
            rows.append(stats)

    changed = [r for r in rows if r["changed"]]
    mode = "DRY-RUN (no files written)" if args.dry_run else "WROTE changes"
    print(f"\n{mode}")
    print(f"  papers scanned        : {len(rows)}")
    print(f"  papers changed        : {len(changed)}")
    print(f"  objectives migrated   : {sum(r['migrated'] for r in rows)}")
    print(f"  duplicate formulas merged : {sum(r['deduped'] for r in rows)}")
    print(f"  empty stubs dropped   : {sum(r['dropped'] for r in rows)}")
    if args.validate:
        bad = [r for r in rows if r["issues"]]
        print(f"  papers with validation issues : {len(bad)}")
        for r in bad[:10]:
            print(f"    {r['issues']:>3} issues  {r['paper'][:72]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
