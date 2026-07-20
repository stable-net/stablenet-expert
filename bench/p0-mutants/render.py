#!/usr/bin/env python3
"""render.py — case (+ mutants) → plan.md / design.md artifacts.

The deterministic scorer (score.py) measures the *rules*. To also measure
*spec-following fidelity* (does the real implementer/evaluator agent honor the
contract?), render each case/mutant into the markdown artifacts a real planner
would produce, then dispatch the agents on them — the eval-gate pattern, one
level automated. This module produces those artifacts; the dispatch + verdict
capture is documented in README.md (agent-in-the-loop layer).

    python3 bench/p0-mutants/render.py --case feepayer-truncate [--mutant uncover_blank] --out DIR

Writes {out}/plan.md and {out}/design.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mutate import MUTATIONS, normalize   # noqa: E402


def _yaml_block(marker: str, payload: dict) -> str:
    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100).rstrip()
    return f"```yaml\n# --- {marker} ---\n{body}\n```"


def render_plan(case: dict) -> str:
    plan = case["plan"]
    prose = "\n".join(f"{s}\n- (design detail in design.md)" for s in plan["prose_steps"])
    parts = [f"# Plan — {case['case_id']}", "", prose, "", "## Verification Plan",
             "- go build ./... after every step; go test on touched packages.", "",
             "## Risks", "- derived-state drift on non-feature paths (see write-site-contract).", ""]
    if plan.get("contract_steps") is not None:
        parts.append("Machine-readable plan contract (authoritative for Implementer §2.1):")
        parts.append("")
        parts.append(_yaml_block("plan-contract (machine-readable; authoritative for Implementer §2.1)",
                                 {"steps": plan["contract_steps"]}))
    return "\n".join(parts) + "\n"


def render_design(case: dict) -> str:
    wsc = case["design"].get("write_site_contract")
    parts = [f"# Design v1 — {case['case_id']}", "",
             "### Step 2: maintain the derived state at every mutation site", "",
             "#### Side-effect checklist",
             "- [x] introduces derived/parallel state → §5.2b REQUIRED", ""]
    if wsc:
        parts.append("Write-site completeness (planner §5.2b):")
        parts.append("")
        parts.append(_yaml_block("write-site-contract (machine-readable)", wsc))
    return "\n".join(parts) + "\n"


def _load(case_id: str) -> dict:
    p = HERE / "corpus" / f"{case_id}.json"
    if not p.exists():
        raise SystemExit(f"no such case: {case_id} ({p})")
    return normalize(json.loads(p.read_text()))


def _apply_mutant(case: dict, label: str) -> dict:
    for lbl, _cat, op, _eb, _ea in MUTATIONS:
        if lbl == label:
            return op(case)
    raise SystemExit(f"no such mutant: {label}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="render P0 case/mutant to plan.md + design.md")
    ap.add_argument("--case", required=True)
    ap.add_argument("--mutant", default="clean")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case = _apply_mutant(_load(args.case), args.mutant)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.md").write_text(render_plan(case))
    (out / "design.md").write_text(render_design(case))
    print(f"wrote {out}/plan.md, {out}/design.md  (case={args.case} mutant={args.mutant})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
