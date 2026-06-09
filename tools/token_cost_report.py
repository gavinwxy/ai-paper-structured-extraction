#!/usr/bin/env python3
"""Per-stage token & cost report over a production run's telemetry.

Reads each paper's ``status.json`` (``token_usage.by_stage`` recorded by
``production/llm.py``) and aggregates per-stage:

  prompt / cached / uncached(=prompt-cached) / completion / cache-hit%
  eff-cost proxy = uncached_prompt + 4*completion       (output ~4x input; cached ~free)
  $ (optional)   = uncached*in_rate + cached*cached_rate + completion*out_rate

Two jobs in one tool:

* **P3 readout** — ``--cache`` prints the per-stage cache-hit table plus a
  content-section diagnosis. The three content sections (problem/evidence/method)
  share a byte-identical paper-inclusive prefix but fire concurrently
  (``asyncio.gather``), so the server prefix-cache is cold when they race and each
  re-sends the whole paper uncached. The report quantifies the "warm-once" headroom.

* **X4 cost** — pass ``--in-rate/--cached-rate/--out-rate`` (USD per 1M tokens) to
  convert tokens -> $. Without rates the tool prints the unit-free eff-cost proxy.

Usage:
    python3 tools/token_cost_report.py <run_dir> [--cache] \
        [--in-rate R --cached-rate R --out-rate R]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CONTENT_STAGES = ("section:problem", "section:evidence", "section:method")
NUMERIC = ("calls", "prompt_tokens", "completion_tokens", "cached_prompt_tokens")


def load_run(run_dir: Path) -> tuple[list[dict], list[str]]:
    """Return (per-paper by_stage dicts, paper ids) for every status.json found."""
    papers, ids = [], []
    for status in sorted(run_dir.glob("*/status.json")):
        try:
            data = json.loads(status.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        by_stage = data.get("token_usage", {}).get("by_stage")
        if not by_stage:
            continue
        papers.append(by_stage)
        ids.append(status.parent.name)
    return papers, ids


def aggregate(papers: list[dict]) -> dict[str, dict]:
    """Sum each stage's token fields across all papers."""
    agg: dict[str, dict] = {}
    for by_stage in papers:
        for stage, e in by_stage.items():
            a = agg.setdefault(stage, {k: 0 for k in NUMERIC})
            for k in NUMERIC:
                a[k] += int(e.get(k, 0) or 0)
    return agg


def eff_cost(uncached: int, completion: int) -> int:
    """Unit-free proxy: output priced ~4x input, cached ~free."""
    return uncached + 4 * completion


def dollars(uncached, cached, completion, rates) -> float | None:
    if not rates:
        return None
    in_r, cached_r, out_r = rates
    return (uncached * in_r + cached * cached_r + completion * out_r) / 1_000_000


def fmt(n: float) -> str:
    return f"{n/1000:.1f}K" if abs(n) >= 1000 else f"{n:.0f}"


def report(run_dir: Path, rates: tuple[float, float, float] | None) -> None:
    papers, ids = load_run(run_dir)
    if not papers:
        print(f"No telemetry found under {run_dir}")
        return
    agg = aggregate(papers)
    n = len(papers)

    rows = []
    for stage, a in agg.items():
        prompt, cached = a["prompt_tokens"], a["cached_prompt_tokens"]
        comp = a["completion_tokens"]
        uncached = prompt - cached
        rows.append({
            "stage": stage, "prompt": prompt, "cached": cached,
            "uncached": uncached, "completion": comp,
            "hit": cached / prompt if prompt else 0.0,
            "eff": eff_cost(uncached, comp),
            "usd": dollars(uncached, cached, comp, rates),
        })
    tot_eff = sum(r["eff"] for r in rows) or 1
    tot_usd = sum(r["usd"] for r in rows) if rates else None
    rows.sort(key=lambda r: r["eff"], reverse=True)

    print(f"\n=== {run_dir.name}: {n} papers ===")
    hdr = f"{'stage':<18}{'prompt':>9}{'cached':>9}{'uncached':>9}{'compl':>8}{'hit%':>7}{'eff%':>7}"
    if rates:
        hdr += f"{'$':>10}"
    print(hdr)
    for r in rows:
        line = (f"{r['stage']:<18}{fmt(r['prompt']):>9}{fmt(r['cached']):>9}"
                f"{fmt(r['uncached']):>9}{fmt(r['completion']):>8}"
                f"{r['hit']*100:>6.0f}%{r['eff']/tot_eff*100:>6.0f}%")
        if rates:
            line += f"{r['usd']:>9.3f}"
        print(line)
    print("-" * len(hdr))
    sp = sum(r["prompt"] for r in rows)
    sc = sum(r["cached"] for r in rows)
    su = sum(r["uncached"] for r in rows)
    scomp = sum(r["completion"] for r in rows)
    tail = (f"{'TOTAL':<18}{fmt(sp):>9}{fmt(sc):>9}{fmt(su):>9}{fmt(scomp):>8}"
            f"{sc/sp*100:>6.0f}%{100:>6.0f}%")
    if rates:
        tail += f"{tot_usd:>9.3f}"
    print(tail)
    if rates:
        print(f"  (rates $/Mtok: in={rates[0]} cached={rates[1]} out={rates[2]}  "
              f"=> ${tot_usd/n:.4f}/paper)")
    else:
        print("  (pass --in-rate/--cached-rate/--out-rate for $; eff% is the unit-free proxy)")


def cache_diagnosis(run_dir: Path) -> None:
    """P3: quantify the content-section concurrency cache-miss + warm-once headroom."""
    papers, ids = load_run(run_dir)
    if not papers:
        print(f"No telemetry under {run_dir}")
        return
    print(f"\n=== P3 content-section cache diagnosis ({len(papers)} papers) ===")

    # Is the cached amount constant across the 3 content sections within a paper?
    # If so it is the cross-paper system prefix only -- the paper itself is uncached x3.
    constant_cache = 0
    sys_prefix_samples = []
    total_redundant_uncached = 0   # upper bound on warm-once saving
    realistic_saving = 0           # 2 of 3 sections recover (SHARED - SYS)
    per_paper = []
    for by_stage, pid in zip(papers, ids):
        cs = [by_stage.get(s) for s in CONTENT_STAGES if by_stage.get(s)]
        if len(cs) < 2:
            continue
        cached_vals = [c["cached_prompt_tokens"] for c in cs]
        uncached_vals = [c["prompt_tokens"] - c["cached_prompt_tokens"] for c in cs]
        if len(set(cached_vals)) == 1:
            constant_cache += 1
            sys_prefix_samples.append(cached_vals[0])
        # warm-once model: keep the largest-completion section first (it must run anyway),
        # the other (n-1) sections then cache the SHARED paper-inclusive prefix.
        order = sorted(range(len(cs)), key=lambda i: cs[i]["completion_tokens"], reverse=True)
        recovered = [uncached_vals[i] for i in order[1:]]   # non-first sections
        sys_pref = min(cached_vals)
        # SHARED - SYS for a non-first section = its current uncached - its variable tail.
        # Tail (section_focus) is unknown; bound it by the inter-section uncached spread.
        spread = max(uncached_vals) - min(uncached_vals)
        for u in recovered:
            total_redundant_uncached += u
            realistic_saving += max(0, u - spread)   # conservative: subtract a full spread as tail
        per_paper.append((pid, sys_pref, uncached_vals))

    n = len(per_paper)
    print(f"content sections with IDENTICAL cached-prefix across all 3: {constant_cache}/{n} papers")
    if sys_prefix_samples:
        lo, hi = min(sys_prefix_samples), max(sys_prefix_samples)
        print(f"  that constant prefix (= cross-paper system prompt, paper NOT cached): "
              f"{lo}-{hi} tok (median {sorted(sys_prefix_samples)[len(sys_prefix_samples)//2]})")
    print(f"\nwarm-once headroom (run 1 content section to warm the prefix, then the rest hit cache):")
    print(f"  upper bound (all redundant uncached prompt): {fmt(total_redundant_uncached)} tok "
          f"({fmt(total_redundant_uncached/n)}/paper)")
    print(f"  realistic (minus section_focus tails):       {fmt(realistic_saving)} tok "
          f"({fmt(realistic_saving/n)}/paper)")
    # express against the run's total eff-cost proxy
    agg = aggregate(papers)
    tot_eff = sum(eff_cost(a["prompt_tokens"] - a["cached_prompt_tokens"],
                           a["completion_tokens"]) for a in agg.values())
    print(f"\n  vs total eff-cost proxy {fmt(tot_eff)}:  "
          f"upper {total_redundant_uncached/tot_eff*100:.1f}%  |  "
          f"realistic {realistic_saving/tot_eff*100:.1f}%")
    print("  (saving is uncached prompt -> cached; in $ terms scale by in_rate vs out_rate)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--cache", action="store_true", help="P3 content-section cache diagnosis")
    ap.add_argument("--in-rate", type=float, help="USD per 1M uncached prompt tokens")
    ap.add_argument("--cached-rate", type=float, help="USD per 1M cached prompt tokens")
    ap.add_argument("--out-rate", type=float, help="USD per 1M completion tokens")
    a = ap.parse_args()
    rates = None
    if a.in_rate is not None and a.cached_rate is not None and a.out_rate is not None:
        rates = (a.in_rate, a.cached_rate, a.out_rate)
    report(a.run_dir, rates)
    if a.cache:
        cache_diagnosis(a.run_dir)


if __name__ == "__main__":
    main()
