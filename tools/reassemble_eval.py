"""Free (no-LLM) A/B for the DETERMINISTIC assembly fixes (FD-1/2/3/6).

Re-runs assemble_extraction over the saved per-paper intermediates (census, stage-B relations, raw
05_sections) with the CURRENT code, and compares the result to the on-disk baseline 06_extraction.json.
Isolates the effect of assembly-stage changes without re-calling the LLM.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/Users/wxy/projects/knowledge-ontology-ai-focused")
sys.path.insert(0, str(ROOT))
from section_pipeline import assemble_extraction, validate_section_ir  # noqa: E402

OUT = ROOT / "production-outputs/eval_8x100_sample100_v0.17"
SRC = ROOT / "production-outputs/eval_sample100_v017_inputs"
SECTION_ORDER = ["problem", "method", "evidence"]


def reassemble(paper_dir: Path, paper_id: str):
    census = json.loads((paper_dir / "01_census.json").read_text())
    relations = json.loads((paper_dir / "04_relations.json").read_text()).get("relations", [])
    section_results = []
    for t in SECTION_ORDER:
        f = paper_dir / "05_sections" / f"{t}.json"
        if f.exists():
            section_results.append({"section": json.loads(f.read_text())})
    paper_content = (SRC / f"{paper_id}.md").read_text(errors="ignore")
    ext = assemble_extraction(census, relations, section_results, paper_content, verify_scores=True)
    return ext


def n_resolves(ext):
    return sum(1 for r in ext.get("relations", []) if r.get("relation") == "resolves")


def empty_measures(ext):
    n = 0
    for sec in ext.get("sections", []):
        for u in sec.get("units", []):
            if u.get("type") == "Measure":
                scores = u.get("scores", [])
                if scores and not any((s.get("value") not in ("", None)) or (s.get("value_num") is not None) for s in scores):
                    n += 1
    return n


def main():
    dirs = sorted(d for d in OUT.iterdir() if d.is_dir() and (d / "06_extraction.json").exists())
    agg = {
        "papers": 0,
        "base_valid": 0, "new_valid": 0,
        "base_resolves": 0, "new_resolves": 0,
        "base_multi_resolve": 0, "new_multi_resolve": 0,
        "prov_total": 0, "prov_resolved": 0,
        "base_empty_meas": 0, "new_empty_meas": 0,
    }
    newly_valid, newly_invalid = [], []
    low_prov = []
    for d in dirs:
        pid = d.name
        base = json.loads((d / "06_extraction.json").read_text())
        try:
            new = reassemble(d, pid)
        except Exception as e:
            print(f"  REASSEMBLE FAIL {pid[:40]}: {e}")
            continue
        agg["papers"] += 1
        b_issues = validate_section_ir(base)
        n_issues = validate_section_ir(new)
        agg["base_valid"] += not b_issues
        agg["new_valid"] += not n_issues
        if b_issues and not n_issues:
            newly_valid.append(pid[:42])
        if not b_issues and n_issues:
            newly_invalid.append((pid[:42], n_issues[:2]))
        br, nr = n_resolves(base), n_resolves(new)
        agg["base_resolves"] += br; agg["new_resolves"] += nr
        agg["base_multi_resolve"] += br > 1; agg["new_multi_resolve"] += nr > 1
        pr = new.get("extraction_notes", {}).get("provenance_resolution", {})
        agg["prov_total"] += pr.get("chunk_markers", 0)
        agg["prov_resolved"] += pr.get("resolved_to_chunk", 0)
        if pr.get("rate") is not None and pr["rate"] < 0.9:
            low_prov.append((pid[:38], pr["rate"], pr.get("unresolved_sample", [])[:3]))
        agg["base_empty_meas"] += empty_measures(base)
        agg["new_empty_meas"] += empty_measures(new)

    p = agg["papers"]
    print(f"\n=== Re-assembly A/B over {p} papers (baseline vs new code) ===")
    print(f"valid:            {agg['base_valid']}/{p}  ->  {agg['new_valid']}/{p}")
    print(f"resolves edges:   {agg['base_resolves']}  ->  {agg['new_resolves']}  (avg {agg['base_resolves']/p:.2f} -> {agg['new_resolves']/p:.2f})")
    print(f"papers >1 resolve:{agg['base_multi_resolve']}  ->  {agg['new_multi_resolve']}")
    print(f"empty measures:   {agg['base_empty_meas']}  ->  {agg['new_empty_meas']}")
    rate = agg["prov_resolved"] / agg["prov_total"] if agg["prov_total"] else 0
    print(f"provenance §N markers resolving to a real chunk (NEW): {agg['prov_resolved']}/{agg['prov_total']} = {rate:.1%}")
    print(f"\nnewly VALID ({len(newly_valid)}): {newly_valid}")
    print(f"newly INVALID ({len(newly_invalid)}): {newly_invalid}")
    print(f"\npapers with NEW provenance resolve-rate <90% ({len(low_prov)}):")
    for pid, r, sample in low_prov[:15]:
        print(f"  {r:.0%}  {pid}  unresolved={sample}")


if __name__ == "__main__":
    main()
