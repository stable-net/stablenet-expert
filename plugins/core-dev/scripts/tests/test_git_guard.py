#!/usr/bin/env python3
"""Tests for the git-guard hook — base-moving guard + existing deny rules.

Run:  python3 plugins/core-dev/scripts/tests/test_git_guard.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_HOOK = Path(__file__).resolve().parent.parent.parent / "hooks" / "git-guard.py"
spec = importlib.util.spec_from_file_location("git_guard", _HOOK)
git_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(git_guard)


def _run_hook(cmd: str, cwd: Path) -> dict | None:
    """Feed a Bash payload through main() with cwd as the repo root; return the
    emitted decision JSON (or None when the guard stayed silent)."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    old_cwd, old_stdin = os.getcwd(), sys.stdin
    os.chdir(cwd)                       # _git rev-parse fails in tmp -> falls back to cwd
    sys.stdin = io.StringIO(payload)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            git_guard.main()
        out = buf.getvalue().strip()
        return json.loads(out) if out else None
    finally:
        os.chdir(old_cwd)
        sys.stdin = old_stdin


def _workspace(root: Path, current_state="IMPLEMENTATION", branch="fix/LOCAL-1",
               base_ref="0bf2f4d1bfeb6605006d556957ef8c045d8f8ed8", base_policy="current"):
    ws = root / ".stablenet-expert" / "tickets" / "LOCAL-1_x"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "state.json").write_text(json.dumps({
        "ticket_id": "LOCAL-1",
        "current_state": current_state,
        "states": {"IMPLEMENTATION": {"branch": branch}},
        "config": {"base_ref": base_ref, "base_policy": base_policy},
    }))


def _decision(res):
    return (res or {}).get("hookSpecificOutput", {}).get("permissionDecision")


class TestBaseMoveGuard(unittest.TestCase):
    def test_checkout_named_branch_asks_when_ticket_in_flight(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); _workspace(d)
            for cmd in ("git checkout dev", "git checkout main",
                        "git switch dev", "git -C . checkout -q dev"):
                self.assertEqual(_decision(_run_hook(cmd, d)), "ask", cmd)

    def test_allowed_forms_stay_silent(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); _workspace(d)
            for cmd in (
                "git checkout -b fix/LOCAL-2",              # branch creation
                "git switch -c fix/LOCAL-2",
                "git checkout -- eth/gasprice/anzeon.go",   # file restore
                "git checkout fix/LOCAL-1",                 # the ticket's own branch
                "git checkout 0bf2f4d1b",                   # abbreviated base_ref sha
                "git checkout 4042c6b21",                   # detached commit (red-check)
                "git checkout HEAD~1",
                "git status", "git diff",                   # unrelated git
            ):
                self.assertIsNone(_run_hook(cmd, d), cmd)

    def test_pull_asks_when_ticket_in_flight(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); _workspace(d)
            self.assertEqual(_decision(_run_hook("git pull origin dev", d)), "ask")

    def test_silent_without_active_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)  # no workspace at all
            self.assertIsNone(_run_hook("git checkout dev", d))
            self.assertIsNone(_run_hook("git pull", d))

    def test_silent_when_workspace_terminal(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); _workspace(d, current_state="COMPLETION")
            self.assertIsNone(_run_hook("git checkout dev", d))   # /merge flow may switch now

    def test_latest_policy_optout(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); _workspace(d, base_policy="latest")
            self.assertIsNone(_run_hook("git pull origin dev", d))
            self.assertIsNone(_run_hook("git checkout dev", d))


class TestExistingRulesUnchanged(unittest.TestCase):
    def test_force_push_still_denied(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); _workspace(d)
            self.assertEqual(_decision(_run_hook("git push --force origin x", d)), "deny")

    def test_protected_branch_push_still_denied(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertEqual(_decision(_run_hook("git push origin main", d)), "deny")

    def test_reset_hard_still_asks(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertEqual(_decision(_run_hook("git reset --hard HEAD~1", d)), "ask")


def _repo(root: Path, name: str, branch=None) -> Path:
    """A real one-commit repo, optionally checked out on a feature branch."""
    path = root / name
    path.mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", "-C", str(path)] + list(a),
                                    capture_output=True, check=True)
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
        "--allow-empty", "-m", "x")
    if branch:
        run("checkout", "-q", "-b", branch)
    return path


class TestCommitGuardHonoursCd(unittest.TestCase):
    """`cd <path> && git commit` must be judged against the tree git will really touch.

    Reading the branch from the hook's own cwd was wrong in both directions: it denied
    legitimate commits in a feature worktree when the hook sat in a checkout on main, and it
    let a commit onto main through whenever the hook's cwd happened to be on a branch.
    """

    def test_cd_into_feature_worktree_is_allowed_from_a_main_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            on_main = _repo(d, "on-main")
            feature = _repo(d, "on-feature", branch="feat/work")
            self.assertIsNone(_run_hook(f"cd {feature} && git commit -m x", on_main))

    def test_cd_into_a_main_checkout_is_denied_from_a_feature_worktree(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            on_main = _repo(d, "on-main")
            feature = _repo(d, "on-feature", branch="feat/work")
            self.assertEqual(
                _decision(_run_hook(f"cd {on_main} && git commit -m x", feature)), "deny")

    def test_commit_without_cd_still_uses_the_hook_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            on_main = _repo(d, "on-main")
            self.assertEqual(_decision(_run_hook("git commit -m x", on_main)), "deny")

    def test_unresolvable_cd_falls_back_to_the_hook_cwd(self):
        """A path with substitution or globbing is not resolved -- fall back rather than skip,
        so an unparseable command cannot be used to slip past the guard."""
        with tempfile.TemporaryDirectory() as d:
            on_main = _repo(Path(d), "on-main")
            for cmd in ("cd $HOME && git commit -m x",
                        'cd "$SOME/dir" && git commit -m x',
                        "cd /nonexistent-xyz && git commit -m x"):
                with self.subTest(cmd=cmd):
                    self.assertEqual(_decision(_run_hook(cmd, on_main)), "deny")

    def test_path_containing_the_word_git_is_not_truncated(self):
        """A cd target like /home/me/github/repo contains "git"; splitting on the bare
        substring would cut the path in half and lose the directory."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            on_main = _repo(d, "on-main")
            feature = _repo(d, "github-work", branch="feat/work")
            self.assertIsNone(_run_hook(f"cd {feature} && git commit -m x", on_main))

    def test_last_cd_before_git_wins(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            on_main = _repo(d, "on-main")
            feature = _repo(d, "on-feature", branch="feat/work")
            self.assertIsNone(
                _run_hook(f"cd /tmp && cd {feature} && git add -A && git commit -m x", on_main))

    def test_git_dash_C_still_skips_the_check(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            on_main = _repo(d, "on-main")
            self.assertIsNone(_run_hook(f"git -C {on_main} commit -m x", on_main))


if __name__ == "__main__":
    unittest.main(verbosity=2)
