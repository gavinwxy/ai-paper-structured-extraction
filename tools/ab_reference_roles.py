#!/usr/bin/env python3
"""A/B test a citation-relation vocab change at the references stage.

A vocab change (e.g. the unification that renames the references roles onto the unit-graph
edge names: extends->builds_on, uses_component->uses, compares->compares_to, background unchanged)
touches ONLY the references stage — prompt + schema. So a faithful A/B runs references extraction
on the same papers twice:
  OLD = previous prompt+schema (dump git HEAD to a dir, pass via --old-*)
  NEW = working-tree prompt+schema (the default paths)
…then compares the role distributions the model emits under each. Same model, temperature,
max_tokens, and json_object contract path for both, so the only variable is the vocab.

Metrics (the gate for a pure rename is distribution stability, not recall gain):
  (a) evolution-role share — does the builds_on bucket hold steady vs the old `extends` (a rename
      should not shift it; bare `builds_on` is fuzzier than `extends`, so watch for drift)?
  (b) precision — the script dumps every NEW evolution-role assignment for manual spot-check.
  (c) use/context blow-up — does bare `uses` over-trigger, or the weak-signal `background` balloon?

The OLD/NEW BUCKETS below must match the two vocabularies actually being compared; update them
when the dumped git-HEAD vocab differs from what is listed here.

Usage:
  python tools/ab_reference_roles.py --papers <f1.md> <f2.md> ... \
      --old-prompt /tmp/ab_old/references-extraction.md \
      --old-schema /tmp/ab_old/references-output.schema.json \
      --out production-outputs/ab_tier1_refs
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

from section_pipeline import (  # noqa: E402
    load_prompt,
    build_response_format,
    _augment_prompt_for_json_object,
    _parse_llm_json,
    REFERENCES_PROMPT_PATH,
    REFERENCES_SCHEMA_PATH,
)
from production.llm import LLMClient  # noqa: E402

# Comparable buckets so the differing OLD/NEW vocabularies line up on the same four axes.
# Configured for the unification A/B: OLD = the committed 4-class references vocab,
# NEW = the unified vocab that reuses the unit-graph edge names. Adjust if comparing other vocabs.
BUCKETS = {
    "OLD": {
        "evolution": {"extends"},
        "use": {"uses_component"},
        "compare": {"compares"},
        "context": {"background"},
    },
    "NEW": {
        "evolution": {"builds_on"},
        "use": {"uses"},
        "compare": {"compares_to"},
        "context": {"background"},
    },
}


async def _run_one(llm, model, prompt_path, schema_path, paper_text, paper_id, label, max_tokens):
    system_prompt, user_template = load_prompt(Path(prompt_path))
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    resp_fmt = build_response_format(schema, name="references_output", model=model)
    system_prompt = _augment_prompt_for_json_object(system_prompt, schema, model)
    user_prompt = user_template.replace("{{paper_content}}", paper_text)
    raw = await llm.call(
        model=model, system_prompt=system_prompt, user_content=user_prompt,
        temperature=0.0, max_tokens=max_tokens, response_format=resp_fmt,
        paper_id=paper_id, stage=f"references-{label}",
    )
    return _parse_llm_json(raw)


def _tally(refs: dict, variant: str) -> dict:
    buckets = BUCKETS[variant]
    role_counts: Counter = Counter()
    n_refs = n_evo_refs = 0
    for r in (refs.get("references") or []):
        if not isinstance(r, dict):
            continue
        roles = (r.get("relation") or {}).get("roles") or []
        n_refs += 1
        role_counts.update(roles)
        if any(x in buckets["evolution"] for x in roles):
            n_evo_refs += 1
    return {
        "n_refs": n_refs,
        "n_evo_refs": n_evo_refs,
        "total_roles": sum(role_counts.values()),
        "role_counts": dict(role_counts),
        "bucket_counts": {b: sum(role_counts[x] for x in s) for b, s in buckets.items()},
    }


def _evolution_samples(refs: dict, variant: str, paper: str) -> list[dict]:
    evo = BUCKETS[variant]["evolution"]
    out = []
    for r in (refs.get("references") or []):
        if not isinstance(r, dict):
            continue
        rel = r.get("relation") or {}
        roles = rel.get("roles") or []
        hit = [x for x in roles if x in evo]
        if hit:
            out.append({
                "paper": paper, "id": r.get("id"), "roles": roles,
                "provides_name": rel.get("provides_name", ""),
                "title": (r.get("title") or "")[:80],
            })
    return out


async def _process(llm, model, paper_path: Path, args, out_dir: Path) -> dict | None:
    stem = paper_path.stem
    text = paper_path.read_text(encoding="utf-8", errors="ignore")
    try:
        old, new = await asyncio.gather(
            _run_one(llm, model, args.old_prompt, args.old_schema, text, stem, "old", args.max_tokens),
            _run_one(llm, model, REFERENCES_PROMPT_PATH, REFERENCES_SCHEMA_PATH, text, stem, "new", args.max_tokens),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {stem[:60]}: FAILED ({exc})", file=sys.stderr)
        return None
    (out_dir / f"{stem}__old.json").write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"{stem}__new.json").write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    to = _tally(old, "OLD")
    tn = _tally(new, "NEW")
    print(f"  ✓ {stem[:58]:58}  refs {to['n_refs']:>3}/{tn['n_refs']:>3}  "
          f"evo-refs {to['n_evo_refs']:>2}→{tn['n_evo_refs']:>2}")
    return {
        "paper": stem, "old": to, "new": tn,
        "new_evolution_samples": _evolution_samples(new, "NEW", stem),
        "old_evolution_samples": _evolution_samples(old, "OLD", stem),
    }


def _agg(rows: list[dict], variant: str) -> dict:
    key = variant.lower()
    bc: Counter = Counter()
    rc: Counter = Counter()
    n_refs = n_evo = total_roles = 0
    for r in rows:
        t = r[key]
        bc.update(t["bucket_counts"])
        rc.update(t["role_counts"])
        n_refs += t["n_refs"]
        n_evo += t["n_evo_refs"]
        total_roles += t["total_roles"]
    return {"n_refs": n_refs, "n_evo_refs": n_evo, "total_roles": total_roles,
            "bucket_counts": dict(bc), "role_counts": dict(rc)}


def _pct(x, tot):
    return f"{100*x/tot:5.1f}%" if tot else "  n/a"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--papers", nargs="+", required=True, type=Path)
    ap.add_argument("--old-prompt", required=True)
    ap.add_argument("--old-schema", required=True)
    ap.add_argument("--out", type=Path, default=REPO / "production-outputs" / "ab_tier1_refs")
    ap.add_argument("--model", default=os.getenv("MODEL", "deepseek-v4-pro"))
    ap.add_argument("--base-url", default=os.getenv("BASE_URL", "http://35.220.164.252:3888/v1"))
    ap.add_argument("--max-tokens", type=int, default=32768, help="references output cap (raised to avoid ref-list truncation)")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    load_dotenv()
    api_key = os.getenv("API_KEY") or os.getenv("API-KEY", "")
    if not api_key:
        print("No API_KEY/API-KEY in .env", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)

    llm = LLMClient(base_url=args.base_url, api_key=api_key, max_concurrency=args.concurrency)
    print(f"A/B references vocab — model={args.model}  papers={len(args.papers)}  out={args.out}")
    print(f"{'':2} {'paper':58}  {'OLD/NEW refs':>10}  evo-refs OLD→NEW")
    rows = await asyncio.gather(*[_process(llm, args.model, p, args, args.out) for p in args.papers])
    await llm.close()
    rows = [r for r in rows if r]
    if not rows:
        print("No successful papers.", file=sys.stderr)
        return 1

    ao, an = _agg(rows, "OLD"), _agg(rows, "NEW")
    (args.out / "summary.json").write_text(
        json.dumps({"papers": rows, "agg_old": ao, "agg_new": an}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 78)
    print(f"AGGREGATE over {len(rows)} papers      OLD vocab            NEW vocab (Tier-1)")
    print("-" * 78)
    print(f"  references parsed     {ao['n_refs']:>8}             {an['n_refs']:>8}")
    print(f"  total role tags       {ao['total_roles']:>8}             {an['total_roles']:>8}")
    print(f"  refs w/ evolution role{ao['n_evo_refs']:>8} {_pct(ao['n_evo_refs'], ao['n_refs'])}     "
          f"{an['n_evo_refs']:>8} {_pct(an['n_evo_refs'], an['n_refs'])}   (of refs)")
    print("\n  bucket share (of total role tags):")
    print(f"  {'bucket':10}  {'OLD':>16}     {'NEW':>16}")
    for b in ("evolution", "use", "compare", "context"):
        o, n = ao["bucket_counts"].get(b, 0), an["bucket_counts"].get(b, 0)
        print(f"  {b:10}  {o:>6} {_pct(o, ao['total_roles'])}     {n:>6} {_pct(n, an['total_roles'])}")
    print("\n  NEW evolution-role breakdown:")
    for r in sorted(BUCKETS["NEW"]["evolution"]):
        print(f"    {r:10} {an['role_counts'].get(r, 0)}")
    print(f"\n  OLD raw role_counts: {ao['role_counts']}")
    print(f"  NEW raw role_counts: {an['role_counts']}")

    samples = [s for r in rows for s in r["new_evolution_samples"]]
    print(f"\n  NEW evolution assignments for precision spot-check ({len(samples)} total):")
    for s in samples[:30]:
        print(f"    [{','.join(s['roles'])}] {s['provides_name'][:24]:24} | {s['paper'][:34]:34} {s['title'][:44]}")
    print(f"\n  full dumps + summary.json in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
