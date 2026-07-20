#!/usr/bin/env python3
"""check.py — validate the domain-pack structure (overlay P1 Phase 1 gate).

Phase 1 moved go-stablenet domain content into plugin/domains/go-stablenet/ and made
the stablenet-* skills thin pointers, introducing the generic domain-pack loader.
This gate locks that structure so a later edit can't silently break it:

  - each plugin/domains/<id>/domain-pack.json has the required keys, and its
    referenced files (invariants, context_classifier) exist;
  - the generic `domain-pack` loader skill exists;
  - the stablenet-* pointer skills actually point at the domains/ files
    (so there is one source, not a stale duplicate).

It does NOT yet check the Phase-2 acceptance (core grep-clean / no-regression);
those land when agents are rewired. Pure structure check, no LLM.

    python3 bench/domain-pack/check.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                       # bench/domain-pack -> repo root
DOMAINS = REPO / "plugin" / "domains"
SKILLS = REPO / "plugin" / "skills"
AGENTS = REPO / "plugin" / "agents"

REQUIRED_KEYS = ("project_id", "ticket_namespace", "invariants", "context_classifier", "knowledge")
# Phase 2: agents must not load the (now-deleted) project-specific pointer skills as a
# frontmatter dependency — they resolve the active pack via the generic domain-pack loader.
FORBIDDEN_SKILL_REFS = ("stablenet-context", "stablenet-invariants")


def check(*, domains_dir: Path = DOMAINS, skills_dir: Path = SKILLS,
          agents_dir: Path = AGENTS, check_agents: bool = True) -> int:
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

    # generic loader skill present
    if not (skills_dir / "domain-pack" / "SKILL.md").is_file():
        problems.append(f"generic loader skill missing: {skills_dir}/domain-pack/SKILL.md")

    # Phase 2: no agent loads a deleted project-specific skill as a frontmatter dep;
    # the agents that need domain context reference the generic domain-pack loader.
    if check_agents:
        import re
        skill_line = re.compile(r"^\s*-\s*(\S+)\s*$", re.MULTILINE)
        wired = 0
        for md in sorted(agents_dir.glob("*.md")):
            # frontmatter skills block only: take lines up to the closing '---'
            text = md.read_text()
            fm = text.split("\n---", 2)
            head = fm[0] if len(fm) >= 2 else text
            refs = set(skill_line.findall(head))
            for forbidden in FORBIDDEN_SKILL_REFS:
                if forbidden in refs:
                    problems.append(f"{md.name} frontmatter still loads deleted skill '{forbidden}'")
            if "domain-pack" in refs:
                wired += 1
        if wired == 0:
            problems.append("no agent references the generic 'domain-pack' loader skill")

        # Phase 3 grep-clean: core agents must not hardcode domain coupling.
        allow = re.compile(r"go-stablenet|stablenet-review-code|stablenet-features\.md|policy/stablenet\.yaml")
        for md in sorted(agents_dir.glob("*.md")):
            for ln, line in enumerate(md.read_text().splitlines(), 1):
                if "go_stablenet_root" in line:
                    problems.append(f"{md.name}:{ln} hardcodes go_stablenet_root — use repo_root")
                elif "stablenet" in line and not allow.search(line):
                    problems.append(f"{md.name}:{ln} domain term 'stablenet' (generalize or allowlist)")

    if problems:
        print(f"DOMAIN-PACK STRUCTURE PROBLEMS ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    names = ", ".join(p.parent.name for p in packs)
    print(f"domain-pack structure OK — packs: [{names}]; loader present; agents wired (no stablenet-* deps)")
    return 0


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="validate domain-pack structure").parse_args(argv)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
