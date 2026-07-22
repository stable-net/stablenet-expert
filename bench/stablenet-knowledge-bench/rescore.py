#!/usr/bin/env python3
"""rescore.py — re-score stored cells WITHOUT new LLM calls.

The expensive LLM responses are already saved per cell (``citations`` +
``answer``). This re-runs the deterministic scorers over those stored
predictions — used to apply scorer fixes (e.g. hallucination symbol
normalization) to an existing experiment cheaply. Connects to stablenet-knowledge via env
so the hallucination scorer's find_symbol path is exercised for real.

Usage:
    python3 rescore.py --exp-dir runs/ckg-bench-live [--metric hallucination|all]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

_BENCH_ROOT = os.path.dirname(os.path.abspath(__file__))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from bench_io.envelope import Citation
from scorers.hallucination import score_hallucination
from scorers.location import LocationScore
from scorers.correctness import score_correctness


def _load_golden_keywords():
    """Map question id -> expected_keywords (for correctness re-scoring)."""
    import glob as _g
    out = {}
    try:
        import yaml
    except ImportError:
        return out
    for f in _g.glob(os.path.join(_BENCH_ROOT, "golden-set", "G*.yaml")):
        q = yaml.safe_load(open(f))
        out[q["id"]] = q.get("expected_keywords") or []
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--metric", default="hallucination", choices=["hallucination", "correctness", "all"])
    args = ap.parse_args(argv)

    exp = args.exp_dir if os.path.isabs(args.exp_dir) else os.path.join(_BENCH_ROOT, args.exp_dir)
    cells = sorted(glob.glob(os.path.join(exp, "cells", "*", "result.json")))
    if not cells:
        print(f"no cells under {exp}")
        return 1

    # go-stablenet checkout: env override, else the sibling of the coding-agent repo
    root = os.environ.get("GO_STABLENET_ROOT") or os.path.normpath(
        os.path.join(_BENCH_ROOT, "..", "..", "..", "go-stablenet"))

    # stablenet-knowledge domain-knowledge corpus: citations to a corpus doc are knowledge-source
    # references, not fabricated code (see scorers.hallucination).
    corpus = os.environ.get("CKS_DOMAIN_CORPUS_ROOT") or os.path.normpath(
        os.path.join(_BENCH_ROOT, "..", "..", "..", "code-knowledge-system",
                     "generated", "domain-corpus", "go-stablenet", "entries"))

    cks_tool = None
    cks_ctx = None
    try:
        from stablenet_knowledge_client import make_stablenet_knowledge_client_from_env
        cks_ctx = make_stablenet_knowledge_client_from_env()
        if cks_ctx is not None:
            cks_ctx.__enter__()
            cks_tool = cks_ctx
            print("stablenet-knowledge: connected")
        else:
            print("stablenet-knowledge: not available (STABLENET_KNOWLEDGE_MCP_URL unset) — grep fallback only")
    except Exception as exc:
        print(f"stablenet-knowledge: connect failed ({exc}) — grep fallback only")

    do_h = args.metric in ("hallucination", "all")
    do_c = args.metric in ("correctness", "all")
    kw_map = _load_golden_keywords() if do_c else {}

    changed = 0
    try:
        for f in cells:
            d = json.load(open(f))
            cites = [Citation.from_dict(c) for c in (d.get("citations") or []) if isinstance(c, dict)]
            ch = False
            if do_h:
                old = d.get("hallucinations", {}).get("hallucination_count")
                new_score = score_hallucination(cites, root, cks_tool, corpus)
                d["hallucinations"] = new_score.to_dict()
                ch = ch or (old != new_score.hallucination_count)
            if do_c:
                loc = d.get("location", {}) or {}
                ls = LocationScore(precision=loc.get("precision", 0.0),
                                   recall=loc.get("recall", 0.0), f1=loc.get("f1", 0.0))
                old_c = d.get("correctness")
                new_c = score_correctness(
                    d.get("answer", ""), ls, kw_map.get(d.get("question_id"), []),
                    parse_failed=(d.get("parse_mode") == "failed"),
                )
                d["correctness"] = new_c
                ch = ch or (old_c != new_c)
            json.dump(d, open(f, "w"), ensure_ascii=False, indent=1)
            if ch:
                changed += 1
    finally:
        if cks_ctx is not None:
            cks_ctx.__exit__(None, None, None)

    print(f"re-scored {len(cells)} cells, {changed} hallucination counts changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
