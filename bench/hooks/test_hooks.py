#!/usr/bin/env python3
"""Regression tests for the coding-agent safety hooks (git-guard / on-stop /
session-context). Each hook is a standalone script that reads a JSON payload on
stdin and prints a JSON decision (or nothing = allow/silent). We drive them with
crafted payloads + throwaway git repos and assert the decision, so a later edit
that weakens a guard fails here instead of in a live autonomous run.

Run: python3 bench/hooks/test_hooks.py   (exit 0 = all pass)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HOOKS = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "core-dev", "hooks")
GIT_GUARD = os.path.abspath(os.path.join(HOOKS, "git-guard.py"))
ON_STOP = os.path.abspath(os.path.join(HOOKS, "on-stop.py"))
SESSION = os.path.abspath(os.path.join(HOOKS, "session-context.py"))

_failures = []


def run_hook(script, payload, cwd=None):
    p = subprocess.run([sys.executable, script], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=cwd, timeout=10)
    out = p.stdout.strip()
    return json.loads(out) if out else None


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _failures.append(name)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _init_repo(path, branch):
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    _git(path, "checkout", "-q", "-b", branch)
    open(os.path.join(path, "f"), "w").write("x")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def decision(out):
    return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")


# ---------------- git-guard ----------------
def test_git_guard():
    print("git-guard")
    # force-push -> deny
    check("force-push --force denied", decision(run_hook(GIT_GUARD, bash("git push --force origin x"))) == "deny")
    check("force-push -f denied", decision(run_hook(GIT_GUARD, bash("git push -f origin x"))) == "deny")
    check("force-with-lease NOT denied as force", decision(run_hook(GIT_GUARD, bash("git push --force-with-lease origin feature/x"))) != "deny")
    # push to protected -> deny
    check("push origin main denied", decision(run_hook(GIT_GUARD, bash("git push origin main"))) == "deny")
    check("push HEAD:master denied", decision(run_hook(GIT_GUARD, bash("git push origin HEAD:master"))) == "deny")
    check("push feature branch allowed", run_hook(GIT_GUARD, bash("git push origin feature/main-thing")) is None)
    # destructive -> ask
    check("reset --hard asks", decision(run_hook(GIT_GUARD, bash("git reset --hard HEAD~1"))) == "ask")
    check("clean -fd asks", decision(run_hook(GIT_GUARD, bash("git clean -fd"))) == "ask")
    check("branch -D asks", decision(run_hook(GIT_GUARD, bash("git branch -D old"))) == "ask")
    # tag push -> ask (no auto_merge workspace in a bare cwd)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "feature/x")
        check("tag push asks", decision(run_hook(GIT_GUARD, bash("git push --tags origin"), cwd=d)) == "ask")
    # unrelated / safe -> allow (None)
    check("normal push allowed", run_hook(GIT_GUARD, bash("git push origin feature/x")) is None)
    check("non-git command allowed", run_hook(GIT_GUARD, bash("rm -rf build")) is None)
    check("git status allowed", run_hook(GIT_GUARD, bash("git status")) is None)
    # commit on protected branch -> deny; on feature -> allow
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        check("commit on main denied", decision(run_hook(GIT_GUARD, bash("git commit -m x"), cwd=d)) == "deny")
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "feature/y")
        check("commit on feature allowed", run_hook(GIT_GUARD, bash("git commit -m x"), cwd=d) is None)


# ---------------- on-stop ----------------
def _workspace(root, ticket, state, mode="auto", cycle=1, maxc=3, recent=True):
    ws = os.path.join(root, ".stablenet-expert", "tickets", ticket)
    os.makedirs(ws, exist_ok=True)
    st = {
        "ticket_id": ticket,
        "current_state": state,
        "config": {"max_eval_cycles": maxc, "autonomy": {"mode": mode}},
        "states": {"EVALUATION": {"cycle": cycle}},
    }
    path = os.path.join(ws, "state.json")
    json.dump(st, open(path, "w"))
    if not recent:
        old = time.time() - 3 * 3600
        os.utime(path, (old, old))
    return path


def _stop_payload(active=False):
    return {"stop_hook_active": active, "hook_event_name": "Stop"}


def test_on_stop():
    print("on-stop")
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-1", "EVALUATION")
        out = run_hook(ON_STOP, _stop_payload(), cwd=d)
        check("auto + non-terminal -> block", (out or {}).get("decision") == "block")
        # stop_hook_active short-circuits
        check("stop_hook_active -> no block", run_hook(ON_STOP, _stop_payload(active=True), cwd=d) is None)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-2", "EVALUATION", mode="interactive")
        check("interactive -> no block", run_hook(ON_STOP, _stop_payload(), cwd=d) is None)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-3", "COMPLETION")
        check("terminal COMPLETION -> no block", run_hook(ON_STOP, _stop_payload(), cwd=d) is None)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-4", "EVALUATION", cycle=5, maxc=3)
        check("over cycle cap -> no block", run_hook(ON_STOP, _stop_payload(), cwd=d) is None)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-5", "EVALUATION", recent=False)
        check("stale workspace -> no block", run_hook(ON_STOP, _stop_payload(), cwd=d) is None)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        check("no workspace -> no block", run_hook(ON_STOP, _stop_payload(), cwd=d) is None)


# ---------------- session-context ----------------
def test_session_context():
    print("session-context")
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-9", "EVALUATION", mode="auto", cycle=2)
        out = run_hook(SESSION, {"hook_event_name": "SessionStart"}, cwd=d)
        ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
        check("in-flight workspace surfaced", "T-9" in ctx and "EVALUATION" in ctx)
        check("cycle shown", "2/3" in ctx)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-10", "COMPLETION")
        check("all terminal -> silent", run_hook(SESSION, {"hook_event_name": "SessionStart"}, cwd=d) is None)
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d, "main")
        _workspace(d, "T-11", "BLOCKED")
        out = run_hook(SESSION, {"hook_event_name": "SessionStart"}, cwd=d)
        ctx = (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")
        check("BLOCKED surfaced for attention", "T-11" in ctx and "BLOCKED" in ctx)


def main():
    test_git_guard()
    test_on_stop()
    test_session_context()
    print()
    if _failures:
        print(f"FAIL — {len(_failures)} hook check(s) regressed: {_failures}")
        return 1
    print("hooks: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
