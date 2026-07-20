#!/usr/bin/env python3
"""score_retrieval.py — Step 1: pack-direct retrieval scoring (no LLM).

Measures cks RETRIEVAL quality directly, decoupled from AI generation: for
each golden question it calls cks ``get_for_task(prompt)`` and scores the
returned EvidencePack ``citations`` against the golden ``expected_citations``
using the same overlap location scorer the end-to-end benchmark uses.

This answers "does the DB/graph surface the answer?" without the AI in the
loop — so it isolates retrieval quality from the AI's re-emission/scoring
losses. Uses only local cks calls; no LLM, fully reproducible.

Usage:
    python3 score_retrieval.py [--out runs/ckg-bench-live/retrieval-report.md]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

_BENCH_ROOT = os.path.dirname(os.path.abspath(__file__))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from bench_io.envelope import Citation
from scorers.location import score_location


def _load_golden():
    try:
        import yaml
    except ImportError:
        yaml = None
    out = {}
    for f in sorted(glob.glob(os.path.join(_BENCH_ROOT, "golden-set", "G*.yaml"))):
        if yaml is not None:
            q = yaml.safe_load(open(f))
        else:  # minimal fallback not needed if PyYAML present
            raise SystemExit("PyYAML required")
        out[q["id"]] = q
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(_BENCH_ROOT, "runs", "ckg-bench-live", "retrieval-report.md"))
    args = ap.parse_args(argv)

    golden = _load_golden()
    from stablenet_knowledge_client import make_stablenet_knowledge_client_from_env
    ctx = make_stablenet_knowledge_client_from_env()
    if ctx is None:
        print("cks unavailable (STABLENET_KNOWLEDGE_MCP_URL unset)")
        return 1

    rows = []
    sum_p = sum_r = sum_f1 = 0.0
    recall_hit = 0
    with ctx as cks:
        for qid in sorted(golden):
            q = golden[qid]
            expected = [Citation.from_dict(c) for c in (q.get("expected_citations") or []) if isinstance(c, dict)]
            r = cks("get_for_task", {"prompt": q["prompt"]})
            pack = r.get("citations") or [] if isinstance(r, dict) else []
            pack_cites = [Citation.from_dict(c) for c in pack if isinstance(c, dict)]
            loc = score_location(pack_cites, expected)
            hit = loc.recall > 0
            recall_hit += 1 if hit else 0
            sum_p += loc.precision; sum_r += loc.recall; sum_f1 += loc.f1
            rows.append((qid, q.get("bucket", "?"), loc.precision, loc.recall, loc.f1, len(pack_cites), hit))

    n = len(rows)
    lines = []
    lines.append("# cks 검색 품질 (팩 직접 채점, LLM 미개입)\n")
    lines.append(f"get_for_task 팩 citations vs 골든 expected_citations · {n}문항\n")
    lines.append(f"- **검색 recall(정답 위치를 팩이 포함): {recall_hit}/{n} = {100*recall_hit/n:.0f}%**")
    lines.append(f"- 평균 precision={sum_p/n:.3f} · recall={sum_r/n:.3f} · f1={sum_f1/n:.3f}\n")
    lines.append("| 문항 | 버킷 | P | R | F1 | 팩인용수 | 정답포함 |")
    lines.append("|------|------|---|---|----|---------|---------|")
    for qid, bk, p, rc, f1, npc, hit in rows:
        lines.append(f"| {qid} | {bk} | {p:.2f} | {rc:.2f} | {f1:.2f} | {npc} | {'O' if hit else 'X'} |")
    report = "\n".join(lines) + "\n"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out, "w").write(report)
    print(report)
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
