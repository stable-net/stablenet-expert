#!/usr/bin/env python3
"""CKG Benchmark — top-level entry point.

Usage:
    python3 run.py --manifest manifests/default.json [options]

Options:
    --manifest PATH     Q&A manifest JSON file (required)
    --experiment NAME   Override experiment name from manifest
    --driver DRIVER     Override driver (claude_cli|replay)
    --batch-size N      Override batch_size from manifest
    --continue          Resume a previously interrupted run
    --dry-run           Validate + print plan, no LLM calls
    --output-dir DIR    Override output directory (default: runs/<experiment>)

Exit codes:
    0   success
    1   error (manifest not found, validation failure, etc.)
    130 interrupted (SIGINT) — state saved, run can be resumed
"""

import argparse
import json
import os
import sys
from typing import Optional

# Add bench root to path so imports work from any cwd
_BENCH_ROOT = os.path.dirname(os.path.abspath(__file__))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run.py",
        description=(
            "CKG Benchmark harness — evaluates 4 context-provision methods "
            "× 30 questions × 4 metrics."
        ),
    )
    p.add_argument(
        "--manifest",
        required=True,
        metavar="PATH",
        help="Path to the Q&A manifest JSON file (see qa-manifest.schema.json).",
    )
    p.add_argument(
        "--experiment",
        default=None,
        metavar="NAME",
        help="Override the experiment name from the manifest.",
    )
    p.add_argument(
        "--driver",
        choices=["claude_cli", "replay"],
        default=None,
        help="Override the driver specified in the manifest.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=None,
        metavar="N",
        help="Override batch_size from the manifest.",
    )
    p.add_argument(
        "--continue",
        dest="continue_run",
        action="store_true",
        default=False,
        help="Resume a previously interrupted run.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate manifest and golden-set; print plan; do not run any LLM calls.",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="Override output directory (default: runs/<experiment> inside stablenet-knowledge-bench/).",
    )
    return p


def _load_manifest(path: str) -> dict:
    """Load and do a minimal structural check on the manifest JSON."""
    if not os.path.isfile(path):
        print(f"error: manifest not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fh:
        try:
            manifest = json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"error: manifest is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(1)
    required = ["experiment", "golden_set", "methods", "driver", "go_stablenet_root", "sha_pin"]
    missing = [k for k in required if k not in manifest]
    if missing:
        print(f"error: manifest missing required keys: {missing}", file=sys.stderr)
        sys.exit(1)
    # Relative go_stablenet_root resolves against the coding-agent checkout root
    # (sibling layout: ../go-stablenet). Committed manifests must not embed
    # machine-specific absolute paths — see bench/manifest.schema.json.
    root = manifest["go_stablenet_root"]
    if not os.path.isabs(root):
        repo_root = os.path.normpath(os.path.join(_BENCH_ROOT, "..", ".."))
        manifest["go_stablenet_root"] = os.path.normpath(os.path.join(repo_root, root))
    if not os.path.isdir(manifest["go_stablenet_root"]):
        print(f"error: go_stablenet_root does not exist: {manifest['go_stablenet_root']}",
              file=sys.stderr)
        sys.exit(1)
    return manifest


def _resolve_exp_dir(manifest: dict, output_dir_override: Optional[str]) -> str:
    """Determine the experiment output directory."""
    if output_dir_override:
        return os.path.abspath(output_dir_override)
    # Use manifest output_dir if set
    manifest_outdir = manifest.get("output_dir", "").strip()
    if manifest_outdir:
        if os.path.isabs(manifest_outdir):
            return manifest_outdir
        return os.path.join(_BENCH_ROOT, manifest_outdir)
    # Default: runs/<experiment>
    exp_name = manifest.get("experiment", "default").replace(" ", "_")
    return os.path.join(_BENCH_ROOT, "runs", exp_name)


def _validate_golden_set(manifest: dict) -> int:
    """Run validate_golden.py offline. Return exit code."""
    from validate_golden import main as validate_main
    index_src = manifest.get("golden_set", {}).get("source", "golden-set/index.yaml")
    index_path = os.path.join(_BENCH_ROOT, index_src)
    repo_root = manifest.get("go_stablenet_root", "")
    argv = ["--index", index_path, "--offline"]
    if repo_root:
        argv += ["--repo-root", repo_root]
    return validate_main(argv)


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve manifest path relative to cwd or absolute
    manifest_path = args.manifest
    if not os.path.isabs(manifest_path):
        manifest_path = os.path.join(os.getcwd(), manifest_path)

    manifest = _load_manifest(manifest_path)

    # Apply CLI overrides
    if args.experiment is not None:
        manifest["experiment"] = args.experiment
    if args.driver is not None:
        manifest["driver"] = args.driver
    if args.batch_size is not None:
        manifest["batch_size"] = args.batch_size

    exp_dir = _resolve_exp_dir(manifest, args.output_dir)

    print(f"CKG Benchmark — experiment: {manifest['experiment']}")
    print(f"  driver    : {manifest['driver']}")
    print(f"  methods   : {manifest['methods']}")
    print(f"  sha_pin   : {manifest['sha_pin']}")
    print(f"  output_dir: {exp_dir}")
    print()

    # Validate golden-set before running
    print("Validating golden-set...")
    rc = _validate_golden_set(manifest)
    if rc != 0:
        print("error: golden-set validation failed; aborting", file=sys.stderr)
        return 1
    print()

    if args.dry_run:
        print("--dry-run: validation passed. No LLM calls made.")
        return 0

    # Run (or resume)
    from runner import run as runner_run
    batch_size = args.batch_size or manifest.get("batch_size", 8)

    # Construct cks_client for live drivers; replay does not need stablenet-knowledge.
    driver_name = manifest.get("driver", "replay")
    cks_tool = None
    cks_ctx = None
    if driver_name == "claude_cli":
        from stablenet_knowledge_client import make_stablenet_knowledge_client_from_env
        cks_ctx = make_stablenet_knowledge_client_from_env()
        if cks_ctx is not None:
            cks_ctx.__enter__()
            cks_tool = cks_ctx
            # cks_client prints a connected banner with the instance identity
            # (name / indexed_head / model) from cks.ops.health.
        else:
            print(
                "stablenet-knowledge: STABLENET_KNOWLEDGE_MCP_URL not set — "
                "M2/M3/M4 will run with cks_partial"
            )

    try:
        final_state = runner_run(
            manifest=manifest,
            exp_dir=exp_dir,
            continue_run=args.continue_run,
            batch_size=batch_size,
            cks_tool=cks_tool,
        )
    finally:
        if cks_ctx is not None:
            cks_ctx.__exit__(None, None, None)

    # Build report if complete
    from state import is_complete
    from report import build_report

    if is_complete(final_state):
        print("\nAll cells complete. Building report...")
        md_path = build_report(exp_dir, method_ids=manifest.get("methods"))
        print(f"Report written to: {md_path}")
    else:
        pending = [
            k for k, c in final_state["cells"].items()
            if c["status"] not in ("done", "failed")
        ]
        print(
            f"\n{len(pending)} cells remaining. "
            f"Re-run with --continue to resume."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
