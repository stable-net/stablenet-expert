#!/usr/bin/env python3
"""Resolve the active domain pack for the CURRENT project (stablenet-core-dev plugin).

The plugin's skills/agents live at a fixed install path and carry ZERO knowledge
of which project the Claude session is running in. This script is the deterministic
discovery step: it reads INTRINSIC, reproducible signals of the checked-out repo
(git remote origin URL + go.mod module path — nothing we plant in the target repo)
and matches them against the `detect` rule declared in each bundled domain pack
(`domains/*/domain-pack.json`). It never guesses a default project — no match is
reported as `unknown` (fail-loud), not a silent fallback.

Signals (in the repo, put there by the project itself — not by us):
  - git remote get-url origin      → the repo's identity, set on clone
  - go.mod `module <path>`          → intrinsic, survives a renamed/absent remote

Usage:
  resolve-project.py                       # print resolution JSON to stdout
  resolve-project.py --hook                # emit a SessionStart additionalContext block
  resolve-project.py --repo <dir>          # resolve for <dir> instead of cwd (tests)
  resolve-project.py --domains <dir>       # override the domains dir (tests)

Exit code is always 0 (a discovery tool must not break a session); the outcome is
in the JSON (`unknown`/`ambiguous`). Adding a new project = drop a
`domains/<id>/domain-pack.json` with a `detect` rule — no change to this script.
"""
import sys
import os
import re
import json
import glob
import subprocess


def _run(args, cwd=None):
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=3, cwd=cwd)
        return out.stdout.strip()
    except Exception:
        return ""


def _default_domains_dir():
    # this script is plugin/scripts/resolve-project.py → plugin/domains
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "domains")


def _repo_signals(repo_hint):
    repo_root = _run(["git", "rev-parse", "--show-toplevel"], cwd=repo_hint) or (repo_hint or os.getcwd())
    origin = _run(["git", "remote", "get-url", "origin"], cwd=repo_root)
    module = ""
    try:
        with open(os.path.join(repo_root, "go.mod"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*module\s+(\S+)", line)
                if m:
                    module = m.group(1)
                    break
    except Exception:
        pass
    return repo_root, origin, module


def _matches(patterns, value):
    if not value or not patterns:
        return False
    for p in patterns:
        try:
            if re.search(p, value):
                return True
        except re.error:
            if p in value:  # treat a bad regex as a plain substring
                return True
    return False


def resolve(repo_hint=None, domains_dir=None):
    domains_dir = domains_dir or _default_domains_dir()
    repo_root, origin, module = _repo_signals(repo_hint)

    candidates = []
    for pack_path in sorted(glob.glob(os.path.join(domains_dir, "*", "domain-pack.json"))):
        try:
            pack = json.load(open(pack_path, encoding="utf-8"))
        except Exception:
            continue
        pid = pack.get("project_id") or os.path.basename(os.path.dirname(pack_path))
        det = pack.get("detect") or {}
        hit = None
        if _matches(det.get("git_remote"), origin):
            hit = "git_remote"
        elif _matches(det.get("go_module"), module):
            hit = "go_module"
        if hit:
            candidates.append({
                "project_id": pid,
                "pack_root": os.path.dirname(pack_path),
                "matched_on": hit,
                "priority": det.get("priority", 0),
            })

    result = {"repo_root": repo_root, "origin": origin, "go_module": module,
              "domains_dir": domains_dir, "candidates": [c["project_id"] for c in candidates]}

    if not candidates:
        result.update({"project_id": None, "pack_root": None, "source": None,
                       "unknown": True, "ambiguous": False})
        return result

    candidates.sort(key=lambda c: -c["priority"])
    top = candidates[0]
    ambiguous = len(candidates) > 1 and candidates[1]["priority"] == top["priority"]
    result.update({
        "project_id": None if ambiguous else top["project_id"],
        "pack_root": None if ambiguous else top["pack_root"],
        "source": None if ambiguous else ("detect:" + top["matched_on"]),
        "unknown": False,
        "ambiguous": ambiguous,
    })
    return result


def _emit_hook(res):
    if res.get("unknown") or res.get("ambiguous") or not res.get("project_id"):
        # Do not nag on a non-stablenet-core-dev repo or an ambiguous match at session start;
        # the pipeline's own gate (domain-pack loader / analyzer §3.0) fails loud when it
        # actually needs a pack.
        return
    ctx = (f"Active stablenet-core-dev domain pack: {res['project_id']} "
           f"(matched {res['source']}). Domain-specific commands/build/tests/invariants come "
           f"from this pack at {res['pack_root']} and the project's cks index — the skills "
           f"themselves are project-agnostic.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": ctx}}))


def main(argv):
    hook = "--hook" in argv
    repo_hint = None
    domains_dir = None
    for i, a in enumerate(argv):
        if a == "--repo" and i + 1 < len(argv):
            repo_hint = argv[i + 1]
        if a == "--domains" and i + 1 < len(argv):
            domains_dir = argv[i + 1]
    try:
        if hook:
            try:
                json.load(sys.stdin)  # consume the SessionStart payload (unused)
            except Exception:
                pass
        res = resolve(repo_hint=repo_hint, domains_dir=domains_dir)
    except Exception as e:
        res = {"unknown": True, "ambiguous": False, "project_id": None,
               "pack_root": None, "error": str(e)}
    if hook:
        _emit_hook(res)
    else:
        print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
