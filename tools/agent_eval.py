#!/usr/bin/env python3
"""Scripted agent-readiness eval over the corpus index artifacts (RF report follow-up, T5).

Answers a fixed question set the way a QA agent would — using ONLY the corpus artifacts
(_catalog.jsonl, _cards.jsonl, _result_rows.jsonl, _entity_index.json; never the raw IR trees or
source papers) — and reports per-question answerability, hit counts, and which artifacts were
read. Deterministic (no LLM), so it can run before/after an emit change to quantify the delta.

Six task types (the RF report's task-fit table):
  facet        venue/year/has_code filtering              -> _catalog.jsonl
  lookup       a paper's central contribution             -> _catalog.jsonl
  sweep        topical recall over unit cards             -> _cards.jsonl
  leaderboard  who reports metric M on dataset D; best?   -> _result_rows.jsonl
  compare      cross-paper comparable (dataset, metric)   -> _result_rows.jsonl
  join         which papers cite entity E                 -> _entity_index.json

Usage:
    python tools/agent_eval.py <root> --set treatment2|cvpr_seg [--json]
    python tools/agent_eval.py production-outputs/cvpr_seg_50_v0.12 --set cvpr_seg
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from section_pipeline import _normalize_name  # noqa: E402

# ---------------------------------------------------------------------------
# Question sets. treatment2 = the RF report's 10 simulation themes, fixed; cvpr_seg = the
# same-domain set (T1 acceptance) where FACET/JOIN actually have >1 relevant paper.
# ---------------------------------------------------------------------------

QUESTION_SETS: dict[str, list[dict[str, Any]]] = {
    "treatment2": [
        {"id": "t2-q01", "task": "leaderboard", "desc": "best MSE on ETTh1 (the PARTIAL one)",
         "dataset": "etth1", "metric": "mse", "direction": "min"},
        {"id": "t2-q02", "task": "sweep", "desc": "papers on LLM hallucination / self-contradiction",
         "keywords": ["hallucination", "self contradict"]},
        {"id": "t2-q03", "task": "sweep", "desc": "papers about grasp detection",
         "keywords": ["grasp"]},
        {"id": "t2-q04", "task": "sweep", "desc": "papers addressing oversmoothing",
         "keywords": ["oversmoothing", "over smoothing"]},
        {"id": "t2-q05", "task": "sweep", "desc": "efficient attention / long-context methods",
         "keywords": ["efficient attention", "linear attention", "long context"]},
        {"id": "t2-q06", "task": "facet", "desc": "NeurIPS 2024 papers", "venue": "neurips",
         "year_min": 2024, "year_max": 2024},
        {"id": "t2-q07", "task": "facet", "desc": "papers with released code", "has_code": True},
        {"id": "t2-q08", "task": "lookup", "desc": "central contribution of the ReST-MCTS paper",
         "paper_substr": "rest mcts"},
        {"id": "t2-q09", "task": "join", "desc": "papers citing 'Attention Is All You Need'",
         "entity_substr": "attention is all you need", "min_papers": 2},
        {"id": "t2-q10", "task": "compare", "desc": "any cross-paper comparable (dataset, metric) cell",
         "min_pairs": 1},
    ],
    "cvpr_seg": [
        {"id": "cv-q01", "task": "leaderboard", "desc": "which systems report mIoU on Cityscapes; best?",
         "dataset": "cityscapes", "metric": "miou", "direction": "max", "min_hits": 3},
        {"id": "cv-q02", "task": "leaderboard", "desc": "mIoU on ADE20K",
         "dataset": "ade20k", "metric": "miou", "direction": "max"},
        {"id": "cv-q03", "task": "leaderboard", "desc": "mIoU on PASCAL VOC",
         "dataset": "voc", "metric": "miou", "direction": "max"},
        {"id": "cv-q04", "task": "leaderboard", "desc": "results on COCO",
         "dataset": "coco", "metric": "", "direction": "max"},
        {"id": "cv-q05", "task": "sweep", "desc": "weakly-supervised segmentation methods",
         "keywords": ["weakly supervised"], "min_hits": 3},
        {"id": "cv-q06", "task": "sweep", "desc": "domain-adaptation segmentation papers",
         "keywords": ["domain adaptation", "unsupervised domain"]},
        {"id": "cv-q07", "task": "sweep", "desc": "real-time / efficient segmentation",
         "keywords": ["real time", "efficient segmentation", "lightweight"]},
        {"id": "cv-q08", "task": "facet", "desc": "2020+ papers with released code",
         "year_min": 2020, "has_code": True},
        {"id": "cv-q09", "task": "join", "desc": "papers citing FCN (fully convolutional networks)",
         "entity_substr": "fully convolutional networks for semantic segmentation",
         "min_papers": 2},
        {"id": "cv-q10", "task": "join", "desc": "papers citing DeepLab",
         "entity_substr": "deeplab", "min_papers": 2},
        {"id": "cv-q11", "task": "compare", "desc": "cross-paper comparable (dataset, metric) cells",
         "min_pairs": 3},
        {"id": "cv-q12", "task": "lookup", "desc": "central contribution of a panoptic paper",
         "paper_substr": "panoptic"},
    ],
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


class Corpus:
    """The artifact files an agent is allowed to read, with read-tracking."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, Any] = {}
        self.reads: set[str] = set()

    def catalog(self) -> list[dict[str, Any]]:
        return self._jsonl("_catalog.jsonl")

    def cards(self) -> list[dict[str, Any]]:
        return self._jsonl("_cards.jsonl")

    def result_rows(self) -> list[dict[str, Any]]:
        return self._jsonl("_result_rows.jsonl")

    def entity_index(self) -> dict[str, Any]:
        self.reads.add("_entity_index.json")
        if "_entity_index.json" not in self._cache:
            path = self.root / "_entity_index.json"
            self._cache["_entity_index.json"] = (
                json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            )
        return self._cache["_entity_index.json"]

    def _jsonl(self, name: str) -> list[dict[str, Any]]:
        self.reads.add(name)
        if name not in self._cache:
            self._cache[name] = _load_jsonl(self.root / name)
        return self._cache[name]


# ---------------------------------------------------------------------------
# Task handlers — each returns {answered, n_hits, evidence}
# ---------------------------------------------------------------------------

def _norm_contains(haystack: Any, needle: str) -> bool:
    return needle in _normalize_name(haystack) if haystack else False


def run_facet(corpus: Corpus, q: dict[str, Any]) -> dict[str, Any]:
    hits = []
    for row in corpus.catalog():
        if q.get("venue") and _normalize_name(row.get("venue")) != _normalize_name(q["venue"]):
            continue
        year = row.get("year")
        if q.get("year_min") and (not isinstance(year, int) or year < q["year_min"]):
            continue
        if q.get("year_max") and (not isinstance(year, int) or year > q["year_max"]):
            continue
        if q.get("has_code") and row.get("has_code") is not True:
            continue
        hits.append(row["paper_id"])
    return {"n_hits": len(hits), "evidence": hits[:5]}


def run_lookup(corpus: Corpus, q: dict[str, Any]) -> dict[str, Any]:
    needle = q["paper_substr"]
    hits = []
    for row in corpus.catalog():
        if _norm_contains(row.get("title"), needle) or _norm_contains(row.get("paper_id"), needle):
            if row.get("central_contribution"):
                hits.append({"paper_id": row["paper_id"],
                             "central_contribution": row["central_contribution"][:120]})
    return {"n_hits": len(hits), "evidence": hits[:3]}


def run_sweep(corpus: Corpus, q: dict[str, Any]) -> dict[str, Any]:
    keywords = [_normalize_name(k) for k in q["keywords"]]
    papers: dict[str, int] = defaultdict(int)
    for card in corpus.cards():
        text = _normalize_name(card.get("embed_text"))
        if any(k in text for k in keywords):
            papers[card["paper_id"]] += 1
    # catalog surfaces (title/problem/contribution) count too — an agent would grep both files
    for row in corpus.catalog():
        surface = _normalize_name(" ".join(str(row.get(k) or "") for k in
                                           ("title", "problem_description", "central_contribution")))
        if any(k in surface for k in keywords):
            papers.setdefault(row["paper_id"], 0)
    return {"n_hits": len(papers),
            "evidence": sorted(papers, key=lambda p: -papers[p])[:5]}


def run_leaderboard(corpus: Corpus, q: dict[str, Any]) -> dict[str, Any]:
    dataset, metric = q["dataset"], q.get("metric", "")
    rows = []
    for row in corpus.result_rows():
        if row.get("value_num") is None:
            continue
        in_dataset = _norm_contains(row.get("dataset"), dataset) or (
            row.get("source") == "table_blob"
            and (_norm_contains(row.get("table_caption"), dataset)
                 or _norm_contains(row.get("metric"), dataset))
        )
        if not in_dataset:
            continue
        if metric and not (_norm_contains(row.get("metric"), metric)
                           or _norm_contains(row.get("unit"), metric)):
            continue
        rows.append(row)
    systems = {r.get("system") for r in rows if r.get("system")}
    best = None
    if rows:
        pick = min if q.get("direction") == "min" else max
        best_row = pick(rows, key=lambda r: r["value_num"])
        best = {"system": best_row.get("system"), "value": best_row.get("value_raw"),
                "paper_id": best_row.get("paper_id"), "source": best_row.get("source")}
    return {"n_hits": len(rows), "n_systems": len(systems), "best": best,
            "n_papers": len({r["paper_id"] for r in rows}),
            "evidence": [best] if best else []}


def run_compare(corpus: Corpus, q: dict[str, Any]) -> dict[str, Any]:
    cells: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in corpus.result_rows():
        if row.get("value_num") is None or row.get("source") != "transcribed":
            continue
        dataset, metric = row.get("dataset_norm"), row.get("metric_norm")
        if dataset and metric:
            cells[(dataset, metric)].add(row["paper_id"])
    comparable = {cell: papers for cell, papers in cells.items() if len(papers) > 1}
    return {"n_hits": len(comparable),
            "evidence": [{"dataset": d, "metric": m, "n_papers": len(p)}
                         for (d, m), p in sorted(comparable.items(),
                                                 key=lambda kv: -len(kv[1]))[:5]]}


def run_join(corpus: Corpus, q: dict[str, Any]) -> dict[str, Any]:
    needle = _normalize_name(q["entity_substr"])
    min_papers = q.get("min_papers", 1)
    hits = []
    for entity in corpus.entity_index().get("entities") or []:
        if needle in entity.get("canonical_key", ""):
            papers = {p["paper_id"] for p in entity.get("papers") or []}
            if len(papers) >= min_papers:
                hits.append({"title": entity.get("title"), "n_papers": len(papers)})
    return {"n_hits": len(hits), "evidence": hits[:3]}


HANDLERS = {
    "facet": run_facet,
    "lookup": run_lookup,
    "sweep": run_sweep,
    "leaderboard": run_leaderboard,
    "compare": run_compare,
    "join": run_join,
}


def run_eval(root: Path, questions: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for q in questions:
        corpus = Corpus(root)  # fresh read-tracking per question
        out = HANDLERS[q["task"]](corpus, q)
        threshold = q.get("min_hits", q.get("min_pairs", 1))
        out.update({
            "id": q["id"], "task": q["task"], "desc": q["desc"],
            "answered": out["n_hits"] >= threshold,
            "artifacts_read": sorted(corpus.reads),
        })
        results.append(out)
    answered = sum(1 for r in results if r["answered"])
    return {
        "root": str(root),
        "n_questions": len(results),
        "n_answered": answered,
        "by_task": {
            task: f"{sum(1 for r in results if r['task'] == task and r['answered'])}"
                  f"/{sum(1 for r in results if r['task'] == task)}"
            for task in sorted({r["task"] for r in results})
        },
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Run root containing the _*.jsonl index artifacts")
    ap.add_argument("--set", dest="qset", default="treatment2",
                    help="Built-in question set name (treatment2|cvpr_seg) or a path to a JSON "
                         "file holding a question list")
    ap.add_argument("--json", action="store_true", help="Emit the full JSON report")
    args = ap.parse_args()

    if args.qset in QUESTION_SETS:
        questions = QUESTION_SETS[args.qset]
    else:
        questions = json.loads(Path(args.qset).read_text(encoding="utf-8"))

    if not (args.root / "_catalog.jsonl").exists():
        print(f"No _catalog.jsonl under {args.root} — run tools/build_agent_index.py first",
              file=sys.stderr)
        return 2

    report = run_eval(args.root, questions)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"agent eval on {report['root']}: {report['n_answered']}/{report['n_questions']} answered")
    for task, score in report["by_task"].items():
        print(f"  {task:12} {score}")
    for r in report["results"]:
        mark = "PASS" if r["answered"] else "FAIL"
        extra = ""
        if r["task"] == "leaderboard" and r.get("best"):
            extra = f" best={r['best']['system']}={r['best']['value']} ({r['best']['source']})"
        print(f"  [{mark}] {r['id']} {r['task']:11} hits={r['n_hits']:4}  {r['desc']}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
