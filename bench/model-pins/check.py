#!/usr/bin/env python3
"""check.py — enforce that every model pin matches the single source (models.json).

Claude Code agent frontmatter `model:` takes no runtime indirection, so the pins
live literally in the agent files AND were mirrored in bench/lib/capture.py — a
classic dual-source that drifts on upgrade (worst case: the bench's A-arm analyzer
pinned differently from production, silently biasing the thesis). This makes
models.json the one source: capture.py now READS it; this script verifies the
frontmatter matches it (and can --apply the fix), and that prices.json covers each
tier's reference model so cost accounting survives an upgrade.

Frontmatter carries a tier ALIAS ("opus"/"sonnet"), not a concrete model id. A
concrete id is provider-specific — on Bedrock the same model is a region-prefixed
inference profile or an ARN — and a pin that does not resolve is not an error:
Claude Code falls back to the parent model and logs at warn. So an id in
frontmatter silently disables the pin off the first-party API (ADR-0020). The
concrete id survives here as `reference_model`, for pricing only.

    python3 bench/model-pins/check.py            # verify; exit 1 on any drift
    python3 bench/model-pins/check.py --apply     # rewrite frontmatter to match, then verify

Upgrade recipe: edit a tier value in models.json → run with --apply.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                      # bench/model-pins -> repo root
AGENTS_DIR = REPO / "plugins" / "core-dev" / "agents"
PRICES = REPO / "bench" / "prices.json"
MODELS = HERE / "models.json"

_MODEL_LINE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)


def _tier_field(doc: dict, field: str) -> dict[str, str]:
    return {name: spec[field] for name, spec in doc["tiers"].items()}


def resolve(doc: dict) -> dict[str, str]:
    """{agent: alias} — what belongs in each agent's frontmatter."""
    alias = _tier_field(doc, "alias")
    return {agent: alias[tier] for agent, tier in doc["agents"].items()}


def resolve_reference_models(doc: dict) -> dict[str, str]:
    """{agent: reference_model} — the concrete first-party id each alias resolves to.

    For cost estimation only, and only on the path with no real model recorded.
    A run on another provider resolves the alias differently, so the session
    transcript is authoritative wherever it exists.
    """
    ref = _tier_field(doc, "reference_model")
    return {agent: ref[tier] for agent, tier in doc["agents"].items()}


def frontmatter_model(md_path: Path) -> str | None:
    m = _MODEL_LINE.search(md_path.read_text())
    return m.group(1) if m else None


def check(apply: bool, *, models_path: Path = MODELS, agents_dir: Path = AGENTS_DIR,
          prices_path: Path = PRICES, check_capture: bool = True) -> int:
    doc = json.loads(models_path.read_text())
    expected = resolve(doc)
    problems: list[str] = []
    fixed: list[str] = []

    # 1. frontmatter ↔ models.json (both directions)
    tracked = set(expected)
    on_disk = {p.stem for p in agents_dir.glob("*.md")}
    for stale in tracked - on_disk:
        problems.append(f"models.json lists '{stale}' but {agents_dir}/{stale}.md is missing")
    for untracked in on_disk - tracked:
        if frontmatter_model(agents_dir / f"{untracked}.md") is not None:
            problems.append(f"{agents_dir}/{untracked}.md has a model: pin but is not in models.json")

    for agent, want in sorted(expected.items()):
        md = agents_dir / f"{agent}.md"
        if not md.is_file():
            continue
        got = frontmatter_model(md)
        if got == want:
            continue
        if apply and got is not None:
            md.write_text(_MODEL_LINE.sub(f"model: {want}", md.read_text(), count=1))
            fixed.append(f"{agent}: {got} -> {want}")
        else:
            problems.append(f"{agents_dir}/{agent}.md model: {got!r} != models.json {want!r}")

    # 2. capture.py must resolve from the same source
    if check_capture:
        sys.path.insert(0, str(REPO))
        try:
            from bench.lib.capture import DEFAULT_AGENT_MODEL
            # capture.py labels the estimate path with the tier's reference_model, not
            # the alias -- prices.json is keyed by concrete id.
            if DEFAULT_AGENT_MODEL != resolve_reference_models(doc):
                problems.append("bench/lib/capture.py DEFAULT_AGENT_MODEL != models.json "
                                "reference models (it should read models.json at runtime)")
        except Exception as e:  # noqa: BLE001
            problems.append(f"could not import bench/lib/capture.py: {e}")

    # 3. prices.json must cover every tier model (cost accounting survives upgrade)
    prices = json.loads(prices_path.read_text())
    for model_id in sorted(set(_tier_field(doc, "reference_model").values())):
        if model_id not in prices:
            problems.append(f"{prices_path} has no price row for tier model '{model_id}'")

    for f in fixed:
        print(f"applied: {f}")
    if problems:
        print(f"\nMODEL-PIN DRIFT ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    tiers = ", ".join(f"{name}={spec['alias']} ({spec['reference_model']})"
                      for name, spec in doc["tiers"].items())
    print(f"model pins OK — {len(expected)} agents conform to models.json ({tiers})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="verify/apply coding-agent model pins")
    ap.add_argument("--apply", action="store_true", help="rewrite frontmatter to match models.json")
    args = ap.parse_args(argv)
    rc = check(apply=args.apply)
    if args.apply and rc == 1:
        # after applying frontmatter fixes, re-verify (capture/prices issues may remain)
        rc = check(apply=False)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
