#!/usr/bin/env python3
"""compare.py — the deterministic measurement tool for the 3-way bench.

Invoked by the bench-orchestration skill (Bash) after a batch of cells runs:

    python3 bench/compare.py --experiment-dir .stablenet-expert/bench/{experiment} \
        [--prices bench/prices.json] [--sessions sessions.json]

Reads each cell's trace sink (state.json, run-meta.json, logs/agent-transcript.jsonl,
+ optional Claude session JSONL for real tokens), computes per-cell correctness /
safety / tokens / cost / latency, and writes a 3-way comparison report:
    {experiment-dir}/report/comparison.{json,md,csv}
It prints the Markdown summary to stdout. No LLM, read-only over the cells.

Run from the coding-agent repo root so `bench` is importable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python3 bench/compare.py` (repo root) or as a module.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bench.lib.usage import load_prices
from bench.lib.collect import collect_experiment
from bench.lib.report import build_report, to_markdown, to_csv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="3-way bench comparison report")
    ap.add_argument("--experiment-dir", required=True,
                    help="path to .stablenet-expert/bench/{experiment}")
    ap.add_argument("--prices", default=None,
                    help="price-table override JSON (defaults to a snapshot)")
    ap.add_argument("--sessions", default=None,
                    help="JSON mapping {cell_name: claude_session.jsonl} for real tokens")
    ap.add_argument("--out", default=None,
                    help="output dir (default: {experiment-dir}/report)")
    args = ap.parse_args(argv)

    exp_dir = Path(args.experiment_dir)
    if not exp_dir.is_dir():
        print(f"error: experiment dir not found: {exp_dir}", file=sys.stderr)
        return 2

    prices = load_prices(args.prices)
    sessions = json.loads(Path(args.sessions).read_text()) if args.sessions else None

    results = collect_experiment(exp_dir, prices=prices, sessions=sessions)
    if not results:
        print(f"warning: no cells found under {exp_dir}", file=sys.stderr)

    experiment = ""
    manifest = exp_dir / "manifest.json"
    if manifest.is_file():
        try:
            experiment = json.loads(manifest.read_text()).get("experiment", "")
        except json.JSONDecodeError:
            pass

    report = build_report(results, experiment=experiment)
    md = to_markdown(report)

    out_dir = Path(args.out) if args.out else exp_dir / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    (out_dir / "comparison.md").write_text(md + "\n")
    (out_dir / "comparison.csv").write_text(to_csv(results))

    print(md)
    print(f"\n[bench] wrote {out_dir}/comparison.{{json,md,csv}}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
