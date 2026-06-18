"""Compare the prompt-fix A/B (new code+prompts) vs baseline (old code+prompts) on the same papers.

Prompt-effect metrics (LLM-driven, not touched by the deterministic assembly fixes):
  - formal-result Findings (kind theorem/lemma/bound)         FD-4
  - Components/Contributions with method_kind theorem/lemma/bound  FD-4
  - con:*-kind dataset/benchmark units                          FD-5 (env mis-mint -> want lower)
  - ExperimentSetup count                                       FD-5 (env recall -> want higher)
Code-effect sanity (should already hold from the free A/B): validity, resolves, provenance.
"""
import json, sys
from pathlib import Path

ROOT = Path("/Users/wxy/projects/knowledge-ontology-ai-focused")
sys.path.insert(0, str(ROOT))
from section_pipeline import validate_section_ir  # noqa: E402

BASE = ROOT / "production-outputs/eval_8x100_sample100_v0.17"
NEW = ROOT / "production-outputs/ab_promptfix_v018"
FORMAL = {"theorem", "lemma", "bound"}


def metrics(ext):
    m = {"formal_findings": 0, "formal_units": 0, "con_data": 0, "setups": 0,
         "resolves": 0, "valid": 0}
    for sec in ext.get("sections", []):
        for u in sec.get("units", []):
            t = u.get("type")
            if t == "Finding" and u.get("kind") in FORMAL:
                m["formal_findings"] += 1
            if t in ("Contribution", "Component") and u.get("method_kind") in FORMAL:
                m["formal_units"] += 1
            if t == "Contribution" and u.get("kind") in ("dataset", "benchmark"):
                m["con_data"] += 1
            if t == "ExperimentSetup":
                m["setups"] += 1
    m["resolves"] = sum(1 for r in ext.get("relations", []) if r.get("relation") == "resolves")
    m["valid"] = 0 if validate_section_ir(ext) else 1
    pr = ext.get("extraction_notes", {}).get("provenance_resolution", {})
    m["prov_rate"] = pr.get("rate")
    return m


def main():
    pids = sorted(d.name for d in NEW.iterdir() if d.is_dir() and (d / "06_extraction.json").exists())
    keys = ["valid", "formal_findings", "formal_units", "con_data", "setups", "resolves"]
    agg_b = {k: 0 for k in keys}
    agg_n = {k: 0 for k in keys}
    print(f"{'paper':42s} | valid  formalF formalU con_dat setups  resolv | prov_rate")
    for pid in pids:
        try:
            b = metrics(json.loads((BASE / pid / "06_extraction.json").read_text()))
            n = metrics(json.loads((NEW / pid / "06_extraction.json").read_text()))
        except FileNotFoundError:
            continue
        for k in keys:
            agg_b[k] += b[k]; agg_n[k] += n[k]
        def d(k):
            return f"{b[k]}->{n[k]}"
        print(f"{pid[:42]:42s} | {d('valid'):6s} {d('formal_findings'):7s} {d('formal_units'):7s} "
              f"{d('con_data'):7s} {d('setups'):7s} {d('resolves'):7s} | {n['prov_rate']}")
    print(f"\n=== AGGREGATE over {len(pids)} papers (baseline -> new) ===")
    for k in keys:
        print(f"  {k:16s}: {agg_b[k]} -> {agg_n[k]}")


if __name__ == "__main__":
    main()
