#!/usr/bin/env python3
"""score.py — deterministic P2 measurement (no LLM).

Runs the fault corpus through the before-P2 and after-P2 retrieval policies and
reports the property that matters: **silent-incomplete runs** (proceeding CLEAN
while core cks evidence is actually missing). P2 must drive that to zero without
over-blocking the runs a retry can recover.

    python3 bench/p2-cks-fault/score.py [--json]

Exit 0 only if: after silent-incomplete == 0  AND  after over-block == 0  AND
before silent-incomplete > 0 (the gap existed and is now closed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from policy import (after_p2, before_p2, is_silent_incomplete,        # noqa: E402
                    missing_core_after, missing_core_before, normalize)
from scenarios import SCENARIOS                                        # noqa: E402


def run() -> dict:
    rows = []
    for sid, scn, expected_after, note in SCENARIOS:
        health, calls = normalize(scn)
        b, a = before_p2(health, calls), after_p2(health, calls)
        mcb, mca = missing_core_before(calls), missing_core_after(calls)
        b_silent, a_silent = is_silent_incomplete(b, mcb), is_silent_incomplete(a, mca)
        # over-block: after escalates (BLOCKED/DEGRADED) a run that, post-retry on a
        # serviceable backend, has no real core gap → should have been CLEAN.
        recoverable_clean = health == "serviceable" and not mca
        over_block = recoverable_clean and a["decision"] != "CLEAN"
        rows.append({
            "id": sid, "health": health, "note": note,
            "before": b, "before_silent_incomplete": b_silent, "before_missing_core": mcb,
            "after": a, "after_silent_incomplete": a_silent, "after_missing_core": mca,
            "expected_after": expected_after, "after_matches_expected": a["decision"] == expected_after,
            "over_block": over_block,
        })

    summary = {
        "scenarios": len(rows),
        "before_silent_incomplete": sum(r["before_silent_incomplete"] for r in rows),
        "after_silent_incomplete": sum(r["after_silent_incomplete"] for r in rows),
        "after_over_block": sum(r["over_block"] for r in rows),
        "after_decision_mismatches": sum(0 if r["after_matches_expected"] else 1 for r in rows),
        "retry_recovered": sum(1 for r in rows
                               if r["before_silent_incomplete"] and not r["after_silent_incomplete"]
                               and r["after"]["decision"] == "CLEAN"),
    }
    return {"rows": rows, "summary": summary}


def to_markdown(result: dict) -> str:
    s = result["summary"]
    lines = ["# P2 cks-fault corpus — before vs after retrieval policy", "",
             f"- scenarios: **{s['scenarios']}**",
             f"- silent-incomplete (CLEAN while core evidence missing): "
             f"**before {s['before_silent_incomplete']} → after {s['after_silent_incomplete']}**",
             f"- after over-block (escalated a retry-recoverable run): **{s['after_over_block']}**",
             f"- after decision mismatches vs expected: **{s['after_decision_mismatches']}**",
             f"- runs a retry rescued (silent→CLEAN): **{s['retry_recovered']}**", "",
             "| scenario | health | before | silent? | after | silent? | note |",
             "|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        bs = "SILENT" if r["before_silent_incomplete"] else "—"
        as_ = "SILENT" if r["after_silent_incomplete"] else "—"
        lines.append(f"| {r['id']} | {r['health']} | {r['before']['decision']} | {bs} | "
                     f"{r['after']['decision']} | {as_} | {r['note']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="P2 cks-fault deterministic scorer")
    ap.add_argument("--out", default=str(HERE / "report"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = run()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "p2-faults.json").write_text(json.dumps(result, indent=2) + "\n")
    md = to_markdown(result)
    (out / "p2-faults.md").write_text(md)
    print(md)
    if args.json:
        print(json.dumps(result["summary"], indent=2))

    s = result["summary"]
    ok = (s["after_silent_incomplete"] == 0 and s["after_over_block"] == 0
          and s["after_decision_mismatches"] == 0 and s["before_silent_incomplete"] > 0)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
