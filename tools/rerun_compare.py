"""Compare baseline vs re-run (new code+prompts) on the 58 problematic papers.

NEW outputs are taken from eval_rerun_v018/ (the 50 freshly re-run) with a
fallback to ab_promptfix_v018/ (the 8 problematic papers already re-run in the
earlier prompt A/B). BASELINE is eval_8x100_sample100_v0.17/.

Per-paper it reports structural deltas (validity, resolves, provenance
resolution, formal findings, env mis-mints, setups) and attaches the specific
framework_design findings the verification raised, so each defect can be
checked against the new extraction.
"""
import json, sys
from pathlib import Path

ROOT = Path("/Users/wxy/projects/knowledge-ontology-ai-focused")
sys.path.insert(0, str(ROOT))
from section_pipeline import validate_section_ir  # noqa: E402

BASE = ROOT / "production-outputs/eval_8x100_sample100_v0.17"
NEW = ROOT / "production-outputs/eval_rerun_v018"
NEW_FALLBACK = ROOT / "production-outputs/ab_promptfix_v018"
VERIFY = ROOT / "production-outputs/eval_verify_papers.json"
FORMAL = {"theorem", "lemma", "bound"}


def metrics(ext):
    m = {"valid": 1, "resolves": 0, "formal_findings": 0, "con_data": 0,
         "setups": 0, "measures": 0, "findings": 0, "units": 0, "prov_rate": None}
    if ext is None:
        return None
    for sec in ext.get("sections", []):
        for u in sec.get("units", []):
            m["units"] += 1
            t = u.get("type")
            if t == "Finding":
                m["findings"] += 1
                if u.get("kind") in FORMAL:
                    m["formal_findings"] += 1
            if t == "Contribution" and u.get("kind") in ("dataset", "benchmark"):
                m["con_data"] += 1
            if t == "ExperimentSetup":
                m["setups"] += 1
            if t == "Measure":
                m["measures"] += 1
    m["resolves"] = sum(1 for r in ext.get("relations", []) if r.get("relation") == "resolves")
    m["valid"] = 0 if validate_section_ir(ext) else 1
    pr = ext.get("extraction_notes", {}).get("provenance_resolution", {})
    m["prov_rate"] = pr.get("rate")
    return m


def load(d):
    p = d / "06_extraction.json"
    return json.loads(p.read_text()) if p.exists() else None


def eff_attr(f):
    return (f.get("corrected_attribution") or f.get("attribution") or "").lower()


def kept(f):
    return (f.get("verdict") or "").lower() not in (
        "refuted", "rejected", "false_positive", "invalid")


def main():
    torun = json.loads((ROOT / "production-outputs/eval_rerun_list.json").read_text())
    reused = sorted(p.name for p in NEW_FALLBACK.iterdir()
                    if p.is_dir() and (p / "06_extraction.json").exists())
    # framework defects per paper id (resolve truncated ids to extraction dirs)
    extdirs = {p.name for p in BASE.iterdir() if p.is_dir()}

    def resolve(pid):
        if pid in extdirs:
            return pid
        cand = [e for e in extdirs if e.startswith(pid)]
        return cand[0] if cand else pid
    fw = {}
    for p in json.loads(VERIFY.read_text()):
        ff = [f for f in p.get("findings", []) if kept(f) and "framework" in eff_attr(f)]
        if ff:
            fw[resolve(p["paper_id"])] = ff

    papers = sorted(set(torun) | (set(reused) & set(fw)))
    keys = ["valid", "resolves", "formal_findings", "con_data", "setups",
            "measures", "findings", "units"]
    agg_b = {k: 0 for k in keys}
    agg_n = {k: 0 for k in keys}
    prov_b = []
    prov_n = []
    rows = []
    for pid in papers:
        b = metrics(load(BASE / pid))
        nd = NEW / pid
        if not (nd / "06_extraction.json").exists():
            nd = NEW_FALLBACK / pid
        n = metrics(load(nd))
        if b is None or n is None:
            rows.append((pid, "MISSING", b, n))
            continue
        for k in keys:
            agg_b[k] += b[k]
            agg_n[k] += n[k]
        if b["prov_rate"] is not None:
            prov_b.append(b["prov_rate"])
        if n["prov_rate"] is not None:
            prov_n.append(n["prov_rate"])
        rows.append((pid, "OK", b, n))

    print(f"{'paper':46s}| valid  resolv  fF   conD setups meas | prov")
    for pid, st, b, n in rows:
        if st != "OK":
            print(f"{pid[:46]:46s}| {st}")
            continue

        def d(k):
            return f"{b[k]}->{n[k]}"
        flag = ""
        if n["valid"] and not b["valid"]:
            flag += " ✓valid"
        print(f"{pid[:46]:46s}| {d('valid'):6s} {d('resolves'):7s} {d('formal_findings'):4s} "
              f"{d('con_data'):4s} {d('setups'):6s} {d('measures'):4s} | "
              f"{b['prov_rate']}->{n['prov_rate']}{flag}")

    print(f"\n=== AGGREGATE over {sum(1 for r in rows if r[1]=='OK')} papers (baseline -> new) ===")
    for k in keys:
        print(f"  {k:16s}: {agg_b[k]} -> {agg_n[k]}")
    if prov_b and prov_n:
        print(f"  prov_rate(mean) : {sum(prov_b)/len(prov_b):.3f} -> {sum(prov_n)/len(prov_n):.3f}")
    print(f"  framework-defect papers covered: {sum(1 for p in papers if p in fw)}")


if __name__ == "__main__":
    main()
