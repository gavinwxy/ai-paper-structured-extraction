#!/usr/bin/env python3
"""A/B comparison for the RF-07/08 census-prompt change (T2).

Baseline: production-outputs/ab_prompt_audit/treatment2 (current committed prompts, 13 papers).
Treatment: production-outputs/ab_rf078_treatment (facets + problem census node, 20 papers).

Per-paper regression guards on the 13-overlap set + new-feature fire rates on all treatment papers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TREAT = Path(sys.argv[1] if len(sys.argv) > 1 else "production-outputs/ab_rf078_treatment")
BASE = Path(sys.argv[2] if len(sys.argv) > 2 else "production-outputs/ab_prompt_audit/treatment2")


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def stats(paper_dir: Path) -> dict | None:
    ex = load(paper_dir / "06_extraction.json")
    census = load(paper_dir / "01_census.json")
    val = load(paper_dir / "07_validation.json")
    if not ex or not census:
        return None
    units = [u for s in ex.get("sections") or [] for u in s.get("units") or []]
    scores = sum(len(u.get("scores") or []) for u in units if u.get("type") == "Measure")
    cov = (ex.get("extraction_notes") or {}).get("plan_coverage") or {}
    cnodes = census.get("nodes") or []
    spine = census.get("spine_summary") or {}
    prb_nodes = [n for n in cnodes if str(n.get("node_id", "")).startswith("prb:")]
    problem_units = [u for u in units if u.get("type") == "Problem"]
    motivates = [r for r in ex.get("relations") or [] if r.get("relation") == "motivates"]
    stage_b = load(paper_dir / "04_relations.json") or {}
    b_edges = stage_b.get("relations") or []
    prb_in_b = [r for r in b_edges
                if str(r.get("source_id", "")).startswith("prb:")
                or str(r.get("target_id", "")).startswith("prb:")]
    reused = bool(prb_nodes) and any(
        u.get("id") == prb_nodes[0].get("node_id") for u in problem_units)
    return {
        "valid": bool(val and val.get("valid")),
        "n_census_nodes": len(cnodes),
        "n_units": len(units),
        "n_relations": len(ex.get("relations") or []),
        "n_scores": scores,
        "coverage": f"{cov.get('must_covered', '?')}/{cov.get('must_total', '?')}",
        "cov_full": cov.get("must_covered") == cov.get("must_total"),
        "has_topics": bool(spine.get("topics")),
        "has_tasks": bool(spine.get("tasks")),
        "has_domain": bool(spine.get("domain")),
        "n_prb_census": len(prb_nodes),
        "n_problem_units": len(problem_units),
        "n_motivates": len(motivates),
        "prb_id_reused": reused,
        "prb_in_stage_b": len(prb_in_b),
        "doc_facets": {k: (ex.get("document") or {}).get(k) for k in ("topics", "tasks", "domain")},
    }


def main() -> int:
    treat_dirs = sorted(p for p in TREAT.iterdir() if (p / "06_extraction.json").exists())
    base_dirs = {p.name: p for p in BASE.iterdir() if (p / "06_extraction.json").exists()}

    print(f"treatment papers: {len(treat_dirs)}; baseline papers: {len(base_dirs)}\n")

    # --- new-feature fire rates over ALL treatment papers
    fire = {"topics": 0, "tasks": 0, "domain": 0, "prb_census": 0, "prb_reused": 0,
            "motivates": 0, "prb_in_b": 0, "valid": 0, "cov_full": 0}
    for pdir in treat_dirs:
        s = stats(pdir)
        if not s:
            continue
        fire["topics"] += s["has_topics"]
        fire["tasks"] += s["has_tasks"]
        fire["domain"] += s["has_domain"]
        fire["prb_census"] += s["n_prb_census"] >= 1
        fire["prb_reused"] += s["prb_id_reused"]
        fire["motivates"] += s["n_motivates"] >= 1
        fire["prb_in_b"] += s["prb_in_stage_b"]
        fire["valid"] += s["valid"]
        fire["cov_full"] += s["cov_full"]
    n = len(treat_dirs)
    print(f"== treatment fire rates (n={n}) ==")
    print(f"  valid                : {fire['valid']}/{n}")
    print(f"  full must-coverage   : {fire['cov_full']}/{n}")
    print(f"  topics/tasks/domain  : {fire['topics']}/{fire['tasks']}/{fire['domain']} (per /{n})")
    print(f"  census prb: node     : {fire['prb_census']}/{n}")
    print(f"  prb id reused in 06  : {fire['prb_reused']}/{n}")
    print(f"  motivates edge       : {fire['motivates']}/{n}")
    print(f"  prb: edges in stage-B: {fire['prb_in_b']} (want 0)")

    # --- regression guards on the overlap
    print("\n== overlap vs baseline (Δ = treatment - baseline) ==")
    keys = ("n_census_nodes", "n_units", "n_relations", "n_scores")
    totals = {k: [0, 0] for k in keys}
    regressions = []
    for pdir in treat_dirs:
        if pdir.name not in base_dirs:
            continue
        t, b = stats(pdir), stats(base_dirs[pdir.name])
        if not t or not b:
            continue
        for k in keys:
            totals[k][0] += b[k]
            totals[k][1] += t[k]
        flag = ""
        if b["valid"] and not t["valid"]:
            flag += " VALID-REGRESSION"
        if b["cov_full"] and not t["cov_full"]:
            flag += " COVERAGE-REGRESSION"
        if t["n_scores"] < 0.8 * b["n_scores"]:
            flag += " SCORES-DROP>20%"
        if flag:
            regressions.append(pdir.name + flag)
        print(f"  {pdir.name[:46]:46} units {b['n_units']:3}->{t['n_units']:3} "
              f"rel {b['n_relations']:3}->{t['n_relations']:3} scores {b['n_scores']:3}->{t['n_scores']:3} "
              f"cov {b['coverage']}->{t['coverage']} valid {int(b['valid'])}->{int(t['valid'])}{flag}")
    for k in keys:
        b, t = totals[k]
        pct = f"{100 * (t - b) / b:+.1f}%" if b else "n/a"
        print(f"  TOTAL {k:16}: {b} -> {t} ({pct})")
    print("\nregression flags:", regressions or "NONE")

    # sample facets
    print("\n== facet samples (first 3 treatment papers) ==")
    for pdir in treat_dirs[:3]:
        s = stats(pdir)
        print(f"  {pdir.name[:40]}: {json.dumps(s['doc_facets'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
