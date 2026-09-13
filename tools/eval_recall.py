#!/usr/bin/env python3
"""Measure recall@k of bin/memory search against a frozen question set.

Usage: tools/eval_recall.py eval/questions.jsonl [-k 8] [--all]
Exit status 1 if recall is below --min (default 0, so it reports without gating).
"""
import argparse
import importlib.machinery
import importlib.util
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]


def load_memory():
    candidates = [REPO / "bin" / "memory", pathlib.Path(__file__).resolve().parent / "memory"]
    path = next(p for p in candidates if p.exists())
    loader = importlib.machinery.SourceFileLoader("memory_cli", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def recall(m, questions, k, include_archived):
    hits = 0
    misses = []
    with m.db() as c:
        for q in questions:
            rows = m.search(c, q["query"], q.get("project"), k, include_archived)
            ok = any(all(s.lower() in r["text"].lower() for s in q["expect"]) for r in rows)
            hits += ok
            if not ok:
                misses.append(q["query"])
    return hits, misses


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("questions")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--min", type=float, default=0.0)
    a = ap.parse_args(argv)
    questions = [json.loads(l) for l in pathlib.Path(a.questions).read_text().splitlines() if l.strip()]
    if not questions:
        sys.exit("no questions")
    m = load_memory()
    hits, misses = recall(m, questions, a.k, a.all)
    score = hits / len(questions)
    print(f"recall@{a.k}: {hits}/{len(questions)} = {score:.3f}")
    for q in misses:
        print(f"  miss: {q}")
    return 0 if score >= a.min else 1


if __name__ == "__main__":
    sys.exit(main())
