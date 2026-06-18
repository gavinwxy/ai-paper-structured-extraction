"""Deterministic stratified sampler for the 100-paper framework-eval run.

- 8 venues, ~12-13 each = 100 total
- reserve a pre-2024 tail (2005-2023) of ~1-2 per venue where available (~12-15 total)
- exclude non-paper artifacts (title pages, prefaces, notices) and tiny stubs
- fixed seed for reproducibility; random.sample within strata gives topic spread
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path(
    "/Users/wxy/projects/paper-retrieval/downloads/"
    "ros_ai_mainstream_8x100_parsed/markdown_flat"
)
SEED = 20260618
VENUES = ["NeurIPS", "IJCAI", "ICML", "ICLR", "CVPR", "ACL", "AAAI", "KDD"]
TOTAL = 100
TAIL_PER_VENUE = 2          # cap of pre-2024 papers per venue
TAIL_MAX_YEAR = 2023        # tail = years in [TAIL_MIN_YEAR, TAIL_MAX_YEAR]
TAIL_MIN_YEAR = 2005
MODERN_MIN_YEAR = 2024
MIN_SIZE = 6000             # bytes; below this is almost certainly a stub/abstract-only

ARTIFACT_PAT = re.compile(
    r"Title_Page|Preface|Notice_of_Violation|Front_Matter|"
    r"Table_of_Contents|_Index|Proceedings|Conference_on.*Pattern_Recognition__Preface",
    re.I,
)

# Confirmed parse-contamination (a wrong document was concatenated in place of the paper):
#   067_IJCAI_2025 -> a computer-vision textbook; 027_ACL_2025 -> a Vicki Delany mystery novel.
EXCLUDE = {
    "067_IJCAI_2025_Understanding_Matters__Semantic-Structural_Determined_Visual_Relocalization_for_Large_Scenes.md",
    "027_ACL_2025_When_GPT_Spills_the_Tea__Comprehensive_Assessment_of_Knowledge_File_Leakage_in_GPTs.md",
}

STOP = set("the a an of for and to in on via with from is are be as at by or no not new our "
           "your this that what why when where how does do their its using based toward towards "
           "study analysis approach method methods model models framework learning".split())

_GENERIC_HEAD = re.compile(
    r'^(abstract|introduction|article|references?|appendix|\d|table|figure|'
    r'conclusion|related work|background|acknowledg|proposed approach|this page)',
    re.I,
)


def _toks(s):
    return [t for t in re.split(r"[_\W]+", s.lower()) if len(t) >= 4 and t not in STOP]


def _prefix_set(tokens):
    # prefix(5) matching absorbs plural/gerund morphology (recommendation/recommendations)
    return {t[:5] for t in tokens}


def faithfulness(path, title):
    """How well the file CONTENT matches its FILENAME title (0..1).

    The corpus has ~6% hard-mislabeled files (a different paper filed under this name) and
    ~16% ambiguous. We score by overlap of filename title-tokens against (a) the first plausible
    '# ' title heading and (b) the first 3 KB content region, taking the max so acronym-named
    papers (whose descriptive title lives in the abstract) are not wrongly rejected."""
    ftoks = _prefix_set(_toks(title))
    if not ftoks:
        return 1.0
    text = path.read_text(errors="ignore")
    # (a) first plausible title heading
    head = ""
    for m in re.finditer(r'^#\s+(.+)$', text, re.M):
        h = m.group(1).strip()
        if len(h) >= 12 and not _GENERIC_HEAD.match(h):
            head = h
            break
    cov_head = len(ftoks & _prefix_set(_toks(head))) / len(ftoks)
    # (b) header content region
    cov_region = len(ftoks & _prefix_set(_toks(text[:3000]))) / len(ftoks)
    return max(cov_head, cov_region)


FAITHFUL_MIN = 0.5

_ABS = re.compile(r'^#+\s*(abstract|introduction|1\.?\s+introduction)\b', re.I | re.M)
_REF = re.compile(r'^#+\s*(references|bibliography)\b', re.I | re.M)


def coherent(path):
    """A real academic paper has both an abstract/intro AND a references section. This catches
    lexically-similar contamination that faithfulness misses — e.g. a gym training guide filed
    under a CVPR title shares 'full body'/'foundation' tokens but has no References section."""
    text = path.read_text(errors="ignore")
    return bool(_ABS.search(text)) and bool(_REF.search(text))

# venue total allocation summing to 100 (four 13s, four 12s)
VENUE_TOTAL = {"NeurIPS": 13, "IJCAI": 13, "ICML": 13, "ICLR": 13,
               "CVPR": 12, "ACL": 12, "AAAI": 12, "KDD": 12}


def parse(files):
    rows = []
    for f in files:
        m = re.match(r"^(\d+)_([A-Za-z]+)_(\d{4})_(.*)\.md$", f.name)
        if not m:
            continue
        idx, venue, year, title = m.groups()
        size = f.stat().st_size
        small = size < MIN_SIZE
        fscore = 1.0 if small else faithfulness(f, title)
        is_coherent = False if small else coherent(f)
        # Restrict the pool to label-faithful, structurally-coherent papers so the venue/topic
        # stratification is real and we never burn extraction on a mislabeled or non-paper file
        # (novel / blank page / textbook / workout guide / wrong paper).
        artifact = (
            bool(ARTIFACT_PAT.search(f.name))
            or small
            or f.name in EXCLUDE
            or fscore < FAITHFUL_MIN
            or not is_coherent
        )
        rows.append({"name": f.name, "venue": venue, "year": int(year),
                     "title": title, "size": size, "artifact": artifact,
                     "fscore": round(fscore, 2)})
    return rows


def main():
    rng = random.Random(SEED)
    rows = parse(sorted(SRC.glob("*.md")))
    clean = [r for r in rows if not r["artifact"]]
    excluded = [r for r in rows if r["artifact"]]

    by_venue = defaultdict(list)
    for r in clean:
        by_venue[r["venue"]].append(r)

    chosen = []
    for v in VENUES:
        pool = by_venue[v]
        tail = sorted([r for r in pool if TAIL_MIN_YEAR <= r["year"] <= TAIL_MAX_YEAR],
                      key=lambda r: r["name"])
        modern = sorted([r for r in pool if r["year"] >= MODERN_MIN_YEAR],
                        key=lambda r: r["name"])
        total_v = VENUE_TOTAL[v]
        n_tail = min(TAIL_PER_VENUE, len(tail))
        pick_tail = rng.sample(tail, n_tail) if n_tail else []
        n_modern = total_v - len(pick_tail)
        pick_modern = rng.sample(modern, min(n_modern, len(modern)))
        # backfill if a venue is short on modern (shouldn't happen here)
        deficit = total_v - len(pick_tail) - len(pick_modern)
        if deficit > 0:
            extra_tail = [r for r in tail if r not in pick_tail]
            pick_tail += rng.sample(extra_tail, min(deficit, len(extra_tail)))
        chosen += pick_tail + pick_modern

    chosen.sort(key=lambda r: (r["venue"], r["year"], r["name"]))

    # report
    print(f"Total source: {len(rows)} | clean: {len(clean)} | excluded artifacts/stubs: {len(excluded)}")
    print(f"Chosen: {len(chosen)}")
    tail_n = sum(1 for r in chosen if r['year'] <= TAIL_MAX_YEAR)
    print(f"Pre-2024 tail in sample: {tail_n}")
    print("\n--- per-venue (total / tail) ---")
    cv = defaultdict(lambda: [0, 0])
    for r in chosen:
        cv[r["venue"]][0] += 1
        if r["year"] <= TAIL_MAX_YEAR:
            cv[r["venue"]][1] += 1
    for v in VENUES:
        print(f"  {v:8s}: {cv[v][0]:2d}  (tail {cv[v][1]})")
    print("\n--- year histogram ---")
    yh = defaultdict(int)
    for r in chosen:
        yh[r["year"]] += 1
    for y in sorted(yh):
        print(f"  {y}: {yh[y]}")
    print("\n--- chosen list ---")
    for r in chosen:
        print(f"  {r['venue']:8s} {r['year']}  {r['size']//1024:4d}KB  {r['name']}")

    out = Path("/Users/wxy/projects/knowledge-ontology-ai-focused/production-outputs/eval_sample100_v017_list.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([r["name"] for r in chosen], ensure_ascii=False, indent=2))
    print(f"\nWrote list -> {out}")

    if len(chosen) != TOTAL:
        print(f"WARNING: expected {TOTAL}, got {len(chosen)}", file=sys.stderr)


if __name__ == "__main__":
    main()
