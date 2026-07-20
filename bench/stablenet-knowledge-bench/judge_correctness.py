#!/usr/bin/env python3
"""judge_correctness.py — Step 2b: LLM-judge correctness (hybrid).

Re-grades the CORRECTNESS dimension only, using an LLM judge given the golden
reference (correct location + key facts) + the candidate answer. Location and
hallucination stay deterministic (objective, reproducible); correctness is the
one genuinely SEMANTIC axis where a keyword heuristic is too crude.

Controls for the known LLM-judge risks:
  - reference-based: the judge is shown the golden answer, not asked to know it.
  - cheap model (haiku) — the task is a bounded yes/no with reference.
  - recorded in a SEPARATE field ``correctness_llm`` so the objective metrics
    and their reproducibility are untouched.
  - does NOT re-run the answerer (uses stored answers) — no new answer cost.

Usage:
    python3 judge_correctness.py --exp-dir runs/ckg-bench-live [--model claude-haiku-4-5]
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

_JUDGE_SYS = (
    "You grade whether a candidate answer to a go-stablenet (Go blockchain) "
    "code question is CORRECT. You are given the QUESTION, a REFERENCE (the "
    "correct code location and key facts), and the CANDIDATE answer. Mark it "
    "correct if the candidate identifies/explains the right thing, even if the "
    "wording, file path, or line numbers differ from the reference, as long as "
    "the substance matches. Mark it incorrect if it is wrong, empty, evasive, "
    "or about the wrong code. Respond with ONLY strict JSON: "
    '{"correct": true|false, "reason": "<one short sentence>"}'
)


def _load_golden():
    import yaml
    out = {}
    for f in glob.glob(os.path.join(_BENCH_ROOT, "golden-set", "G*.yaml")):
        q = yaml.safe_load(open(f))
        out[q["id"]] = q
    return out


def _ref_block(q):
    cites = q.get("expected_citations") or []
    loc = "; ".join(
        f"{c.get('file')}:{c.get('start_line')}-{c.get('end_line')} {c.get('symbol') or ''}".strip()
        for c in cites
    )
    kw = ", ".join(q.get("expected_keywords") or [])
    return f"correct location(s): {loc}\nkey facts/keywords: {kw}\nintent: {q.get('intent','')}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--model", default="claude-haiku-4-5")
    args = ap.parse_args(argv)

    exp = args.exp_dir if os.path.isabs(args.exp_dir) else os.path.join(_BENCH_ROOT, args.exp_dir)
    cells = sorted(glob.glob(os.path.join(exp, "cells", "*", "result.json")))
    golden = _load_golden()

    from drivers.claude_cli import ClaudeCLIDriver
    from bench_io.extract import extract_response
    driver = ClaudeCLIDriver(model=args.model, timeout=120)

    judged = 0
    for f in cells:
        d = json.load(open(f))
        a = d.get("ask", {})
        if a.get("error"):
            d["correctness_llm"] = None
            json.dump(d, open(f, "w"), ensure_ascii=False, indent=1)
            continue
        q = golden.get(d.get("question_id"))
        if q is None:
            continue
        user = (
            f"QUESTION:\n{q['prompt']}\n\n"
            f"REFERENCE:\n{_ref_block(q)}\n\n"
            f"CANDIDATE ANSWER:\n{d.get('answer','')}"
        )
        res = driver.ask(_JUDGE_SYS, user, max_turns=1)
        verdict = None
        if not res.error and res.response_text:
            parsed = extract_response(res.response_text)
            txt = (parsed.answer or res.response_text).lower()
            try:
                obj = json.loads(res.response_text[res.response_text.find("{"): res.response_text.rfind("}") + 1])
                verdict = bool(obj.get("correct"))
            except Exception:
                if '"correct": true' in res.response_text.lower() or '"correct":true' in res.response_text.lower():
                    verdict = True
                elif '"correct": false' in res.response_text.lower() or '"correct":false' in res.response_text.lower():
                    verdict = False
        d["correctness_llm"] = verdict
        json.dump(d, open(f, "w"), ensure_ascii=False, indent=1)
        judged += 1
        print(f"{d['question_id']} {d['method_id']:<16} heuristic={d.get('correctness')} llm={verdict}")

    print(f"\njudged {judged} cells with model={args.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
