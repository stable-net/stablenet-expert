#!/usr/bin/env python3
"""score.py — the deterministic P0 measurement (no LLM).

For every (corpus case × mutation), run the before-P0 and after-P0 rule engines
and record whether each *detected* the injected defect (mechanism-matched). Emit
the before-vs-after detection-rate report that answers "did the P0 patch actually
close the gap?" — reproducibly, without burning tokens.

    python3 bench/p0-mutants/score.py [--corpus DIR] [--out DIR] [--json]

Headline metric: detection rate over `hard` mutants (defects P0 is meant to
close), before vs after. Plus a false-positive guard on `clean` controls and an
honest `residual` list (defects P0 does NOT close).

Run from the repo root so `bench` is importable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Hyphenated dir (matches stablenet-knowledge-bench/stablenet-knowledge-eval) — not importable as a package, so
# put this dir on the path and import siblings directly.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mutate import MUTATIONS, normalize       # noqa: E402
from rules import ENGINES, detected_by        # noqa: E402


def load_corpus(corpus_dir: Path) -> list[dict]:
    cases = [json.loads(p.read_text()) for p in sorted(corpus_dir.glob("*.json"))]
    if not cases:
        raise SystemExit(f"no corpus cases under {corpus_dir}")
    return [normalize(c) for c in cases]


def run(cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        for label, category, op, exp_before, exp_after in MUTATIONS:
            mutant = op(case)
            fb = ENGINES["before_p0"](mutant)
            fa = ENGINES["after_p0"](mutant)
            rows.append({
                "case": case["case_id"],
                "mutant": label,
                "category": category,
                "before": {
                    "findings": fb,
                    "detected": detected_by(fb, exp_before),
                    "n_findings": len(fb),
                },
                "after": {
                    "findings": fa,
                    "detected": detected_by(fa, exp_after),
                    "n_findings": len(fa),
                },
                "expected_before": exp_before,
                "expected_after": exp_after,
            })

    hard = [r for r in rows if r["category"] == "hard"]
    clean = [r for r in rows if r["category"] == "clean"]
    residual = [r for r in rows if r["category"] == "residual"]
    soft = [r for r in rows if r["category"] == "soft"]

    def rate(items, profile):
        if not items:
            return 0.0
        return sum(1 for r in items if r[profile]["detected"]) / len(items)

    summary = {
        "hard_total": len(hard),
        "before_detected": sum(1 for r in hard if r["before"]["detected"]),
        "after_detected": sum(1 for r in hard if r["after"]["detected"]),
        "before_rate": rate(hard, "before"),
        "after_rate": rate(hard, "after"),
        # false positive = a control "clean" mutant produced ANY finding
        "clean_total": len(clean),
        "before_false_positives": sum(1 for r in clean if r["before"]["n_findings"] > 0),
        "after_false_positives": sum(1 for r in clean if r["after"]["n_findings"] > 0),
        "residual_total": len(residual),
        "residual_caught_after": sum(1 for r in residual if r["after"]["detected"]),
        "soft_total": len(soft),
    }
    summary["improvement_pp"] = round((summary["after_rate"] - summary["before_rate"]) * 100, 1)
    return {"rows": rows, "summary": summary}


def _mark(detected: bool, n_findings: int, expected: list[str]) -> str:
    if not expected:                       # control / residual: success == silence
        return "ok(silent)" if n_findings == 0 else "FALSE-POS"
    return "DETECT" if detected else "MISS"


def to_markdown(result: dict) -> str:
    s = result["summary"]
    lines = ["# P0 mutant-corpus — before vs after detection", "",
             f"- hard mutants: **{s['hard_total']}**",
             f"- before-P0 detection: **{s['before_detected']}/{s['hard_total']}** "
             f"({s['before_rate']*100:.0f}%)",
             f"- after-P0 detection: **{s['after_detected']}/{s['hard_total']}** "
             f"({s['after_rate']*100:.0f}%)",
             f"- improvement: **+{s['improvement_pp']}pp**",
             f"- false positives on clean controls: before {s['before_false_positives']}/{s['clean_total']}, "
             f"after {s['after_false_positives']}/{s['clean_total']}",
             f"- residual (P0 does NOT close): {s['residual_total']} "
             f"(caught after: {s['residual_caught_after']})", "",
             "| case | mutant | cat | before | after | catching mechanism (after) |",
             "|---|---|---|---|---|---|"]
    for r in result["rows"]:
        mech = ",".join(sorted({f["mechanism"] for f in r["after"]["findings"]})) or "—"
        b = _mark(r["before"]["detected"], r["before"]["n_findings"], r["expected_before"])
        a = _mark(r["after"]["detected"], r["after"]["n_findings"], r["expected_after"])
        lines.append(f"| {r['case']} | {r['mutant']} | {r['category']} | {b} | {a} | {mech} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="P0 mutant-corpus deterministic scorer")
    ap.add_argument("--corpus", default=str(HERE / "corpus"))
    ap.add_argument("--out", default=str(HERE / "report"))
    ap.add_argument("--json", action="store_true", help="also print raw JSON to stdout")
    args = ap.parse_args(argv)

    cases = load_corpus(Path(args.corpus))
    result = run(cases)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "p0-detection.json").write_text(json.dumps(result, indent=2) + "\n")
    md = to_markdown(result)
    (out / "p0-detection.md").write_text(md)

    print(md)
    if args.json:
        print(json.dumps(result["summary"], indent=2))

    s = result["summary"]
    # Non-zero exit if the patch failed its own guarantee: after must strictly
    # beat before and never introduce a false positive.
    ok = (s["after_rate"] > s["before_rate"]
          and s["after_false_positives"] == 0
          and s["before_false_positives"] == 0)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
