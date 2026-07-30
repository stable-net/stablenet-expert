#!/usr/bin/env python3
"""check.py — validate the domain-pack structure.

stablenet-expert is scoped to go-stablenet only (no multi-project portability
goal), so this gate validates only what that implies: each
plugins/core-dev/domains/<id>/domain-pack.json is well-formed — required
keys present, referenced files (invariants, context_classifier) exist, and the
Evaluator's verification contract is complete — plus the generic `domain-pack`
loader skill file it is read through exists. It does NOT check whether the core
agents avoid project-specific hardcoding: with a single permanent domain pack,
there is no other pack for such hardcoding to break, so that check would test a
property nobody needs. Pure structure check, no LLM.

    python3 bench/domain-pack/check.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                       # bench/domain-pack -> repo root
PLUGIN = REPO / "plugins" / "core-dev"
DOMAINS = PLUGIN / "domains"
SKILLS = PLUGIN / "skills"

REQUIRED_KEYS = ("project_id", "ticket_namespace", "invariants", "context_classifier", "knowledge")


def check(*, domains_dir: Path = DOMAINS, skills_dir: Path = SKILLS) -> int:
    problems: list[str] = []
    packs = sorted(domains_dir.glob("*/domain-pack.json"))
    if not packs:
        problems.append(f"no domain packs under {domains_dir}")

    for pack_path in packs:
        pid = pack_path.parent.name
        try:
            doc = json.loads(pack_path.read_text())
        except json.JSONDecodeError as e:
            problems.append(f"{pack_path}: invalid JSON ({e})")
            continue
        for key in REQUIRED_KEYS:
            if key not in doc:
                problems.append(f"{pid}: domain-pack.json missing required key '{key}'")
        if doc.get("project_id") not in (pid, None) and "project_id" in doc:
            if doc["project_id"] != pid:
                problems.append(f"{pid}: project_id '{doc['project_id']}' != directory name")
        # referenced files exist
        for ref_key in ("invariants", "context_classifier"):
            ref = doc.get(ref_key)
            if ref and not (pack_path.parent / ref).is_file():
                problems.append(f"{pid}: {ref_key} -> {ref} not found in {pack_path.parent}")
        # verification contract the Evaluator consumes (Phase 2b)
        ver = doc.get("verification")
        if not isinstance(ver, dict):
            problems.append(f"{pid}: missing 'verification' block (Evaluator Phase 2b contract)")
        else:
            if not ver.get("repo_root_env"):
                problems.append(f"{pid}: verification.repo_root_env missing")
            b = ver.get("build", {})
            for k in ("cmd", "binary_cmd", "artifact"):
                if not b.get(k):
                    problems.append(f"{pid}: verification.build.{k} missing")
            u = ver.get("unit_test", {})
            for k in ("full", "coverage_tmpl", "cover_report_tmpl", "race_tmpl"):
                if not u.get(k):
                    problems.append(f"{pid}: verification.unit_test.{k} missing")
            if not isinstance(ver.get("stages"), list) or not ver.get("stages"):
                problems.append(f"{pid}: verification.stages must be a non-empty list")

    # generic loader skill present — agents read the active pack through this file today,
    # so its absence breaks the one project we actually run, not just future portability.
    if not (skills_dir / "domain-pack" / "SKILL.md").is_file():
        problems.append(f"generic loader skill missing: {skills_dir}/domain-pack/SKILL.md")

    if problems:
        print(f"DOMAIN-PACK STRUCTURE PROBLEMS ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    names = ", ".join(p.parent.name for p in packs)
    print(f"domain-pack structure OK — packs: [{names}]; loader present")
    return 0


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="validate domain-pack structure").parse_args(argv)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
