#!/usr/bin/env python3
"""Tests for resolve-project.py — deterministic domain-pack routing.

Drive the resolver with throwaway git repos + a temp domains dir carrying `detect`
rules, and assert the right project_id (or unknown/ambiguous). Run:
  python3 plugins/core-dev/scripts/tests/test_resolve_project.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RESOLVER = os.path.abspath(os.path.join(HERE, "..", "resolve-project.py"))

_fail = []


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fail.append(name)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _make_repo(path, origin=None, module=None):
    os.makedirs(path, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    if origin:
        _git(path, "remote", "add", "origin", origin)
    if module:
        open(os.path.join(path, "go.mod"), "w").write(f"module {module}\n\ngo 1.22\n")
    open(os.path.join(path, "f"), "w").write("x")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")


def _make_domains(root):
    d = os.path.join(root, "domains")
    for pid, det in [
        ("go-stablenet", {"git_remote": ["go-stablenet"], "go_module": ["go-stablenet"], "priority": 10}),
        ("go-wbft", {"git_remote": ["go-wbft"], "go_module": ["go-wbft"], "priority": 10}),
    ]:
        os.makedirs(os.path.join(d, pid), exist_ok=True)
        json.dump({"project_id": pid, "detect": det},
                  open(os.path.join(d, pid, "domain-pack.json"), "w"))
    return d


def run(repo, domains, hook=False):
    args = [sys.executable, RESOLVER, "--repo", repo, "--domains", domains]
    if hook:
        args.append("--hook")
    p = subprocess.run(args, input="{}", capture_output=True, text=True, timeout=15)
    out = p.stdout.strip()
    return json.loads(out) if (out and not hook) else out


def main():
    with tempfile.TemporaryDirectory() as tmp:
        domains = _make_domains(tmp)

        # remote match
        r1 = os.path.join(tmp, "r1")
        _make_repo(r1, origin="https://github.com/x/go-stablenet.git")
        res = run(r1, domains)
        check("remote → go-stablenet", res["project_id"] == "go-stablenet" and res["source"] == "detect:git_remote")

        # go.mod match (no remote)
        r2 = os.path.join(tmp, "r2")
        _make_repo(r2, module="github.com/x/go-wbft")
        res = run(r2, domains)
        check("go.mod (no remote) → go-wbft", res["project_id"] == "go-wbft" and res["source"] == "detect:go_module")

        # different project → the RIGHT one, not a fallback
        r3 = os.path.join(tmp, "r3")
        _make_repo(r3, origin="git@github.com:x/go-wbft.git")
        res = run(r3, domains)
        check("go-wbft repo → go-wbft (not go-stablenet fallback)", res["project_id"] == "go-wbft")

        # no match → unknown (fail-loud), NOT a silent go-stablenet
        r4 = os.path.join(tmp, "r4")
        _make_repo(r4, origin="https://github.com/x/unrelated-thing.git", module="example.com/unrelated")
        res = run(r4, domains)
        check("unrelated repo → unknown (no fallback)",
              res["unknown"] is True and res["project_id"] is None)

        # hook mode: match → additionalContext; unknown → silent
        hout = run(r1, domains, hook=True)
        check("hook match → additionalContext w/ project", "go-stablenet" in hout and "additionalContext" in hout)
        hout2 = run(r4, domains, hook=True)
        check("hook unknown → silent (no nag)", hout2.strip() == "")

    print()
    if _fail:
        print(f"FAIL — {len(_fail)} resolver check(s): {_fail}")
        return 1
    print("resolve-project: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
