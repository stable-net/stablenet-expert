#!/usr/bin/env python3
"""Tests for --scope and --uninstall.

Every run gets its own HOME. setup.py falls back to the global ~/.claude/settings.json, and
--scope user *writes* there, so without isolation these tests would read and edit the
developer's own settings.

Run:  python3 plugins/core-dev/scripts/tests/test_uninstall.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
SETUP_PY = _SCRIPTS / "setup.py"
MANIFEST = ".stablenet-expert-managed.json"


class Sandbox:
    """A throwaway HOME + git project, and a runner bound to them."""

    def __init__(self, stack):
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.home = root / "home"
        self.proj = root / "proj"
        self.home.mkdir()
        self.proj.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True)

    def run(self, *flags, cwd=None):
        return subprocess.run(
            [sys.executable, str(SETUP_PY), *flags], cwd=str(cwd or self.proj),
            capture_output=True, text=True,
            env={"PATH": os.environ.get("PATH", ""), "HOME": str(self.home)})

    def env_of(self, base: Path, name="settings.json") -> dict:
        p = base / ".claude" / name
        return (json.loads(p.read_text()).get("env") or {}) if p.is_file() else {}

    def write_env(self, base: Path, **values):
        p = base / ".claude" / "settings.json"
        doc = json.loads(p.read_text()) if p.is_file() else {}
        doc.setdefault("env", {}).update(values)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=2))


class SandboxCase(unittest.TestCase):
    def setUp(self):
        import contextlib
        self._stack = contextlib.ExitStack()
        self.addCleanup(self._stack.close)
        self.box = Sandbox(self._stack)


class TestScope(SandboxCase):
    def test_env_goes_to_the_user_settings_by_default(self):
        """Machine-level values -- one chainbench checkout -- belong to the machine, not to
        whichever project happened to run setup. This also matches set-mcp-env.sh, which has
        defaulted to user scope all along."""
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.assertEqual(self.box.env_of(self.box.home).get("CHAINBENCH_DIR"), "/opt/cb")
        self.assertNotIn("CHAINBENCH_DIR", self.box.env_of(self.box.proj))

    def test_repo_root_env_stays_project_local_even_at_user_scope(self):
        """"Which checkout is the target" is per project by definition; writing it globally
        would make a second checkout silently build the first."""
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.assertIn("GO_STABLENET_ROOT", self.box.env_of(self.box.proj))
        self.assertNotIn("GO_STABLENET_ROOT", self.box.env_of(self.box.home))

    def test_scope_project_keeps_everything_local(self):
        self.box.run("--fix", "--scope", "project", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.assertEqual(self.box.env_of(self.box.proj).get("CHAINBENCH_DIR"), "/opt/cb")
        self.assertEqual(self.box.env_of(self.box.home), {})


class TestUninstall(SandboxCase):
    def test_dry_run_by_default(self):
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        r = self.box.run("--uninstall")
        self.assertIn("dry run", r.stdout)
        self.assertEqual(self.box.env_of(self.box.home).get("CHAINBENCH_DIR"), "/opt/cb")

    def test_yes_removes_what_setup_wrote(self):
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.box.run("--uninstall", "--yes")
        self.assertNotIn("CHAINBENCH_DIR", self.box.env_of(self.box.home))
        self.assertNotIn("GO_STABLENET_ROOT", self.box.env_of(self.box.proj))

    def test_a_value_the_user_changed_is_kept(self):
        """The reason the manifest stores values, not just key names. Reverting an edit the
        user made after setup ran is worse than leaving a stale key behind -- one is a
        surprise, the other is tidy-up they can do themselves."""
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.box.write_env(self.box.home, CHAINBENCH_DIR="/my/own/path")
        r = self.box.run("--uninstall", "--yes")
        self.assertIn("KEEP", r.stdout)
        self.assertEqual(self.box.env_of(self.box.home).get("CHAINBENCH_DIR"), "/my/own/path")

    def test_keys_we_never_wrote_are_untouched(self):
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.box.write_env(self.box.home, UNRELATED_KEY="keep-me")
        self.box.run("--uninstall", "--yes")
        self.assertEqual(self.box.env_of(self.box.home).get("UNRELATED_KEY"), "keep-me")

    def test_no_manifest_removes_nothing_and_says_why(self):
        """Without provenance there is no way to tell our keys from the user's, and guessing
        means deleting their values. Refusing is the safe direction."""
        self.box.write_env(self.box.home, CHAINBENCH_DIR="/opt/cb")
        r = self.box.run("--uninstall", "--yes")
        self.assertIn("no manifest", r.stdout)
        self.assertEqual(self.box.env_of(self.box.home).get("CHAINBENCH_DIR"), "/opt/cb")

    def test_manifest_is_dropped_once_applied(self):
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.box.run("--uninstall", "--yes")
        self.assertFalse((self.box.home / ".claude" / MANIFEST).is_file())

    def test_running_it_twice_is_harmless(self):
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        self.box.run("--uninstall", "--yes")
        r = self.box.run("--uninstall", "--yes")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no manifest", r.stdout)

    def test_the_shared_atlassian_plugin_is_not_removed_silently(self):
        """It may be serving the user's own Jira work, and another plugin may need it. The
        commands are printed for them to run, not run for them."""
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        r = self.box.run("--uninstall", "--yes")
        self.assertIn("claude plugin uninstall atlassian@claude-plugins-official", r.stdout)
        self.assertIn("claude mcp logout", r.stdout)

    def test_autonomous_permissions_are_recorded_and_taken_back(self):
        self.box.run("--autonomous")
        local = self.box.proj / ".claude" / "settings.local.json"
        self.assertTrue(json.loads(local.read_text())["permissions"]["allow"])
        self.box.run("--uninstall", "--yes")
        self.assertEqual(json.loads(local.read_text())["permissions"]["allow"], [])


class TestRunFromAnywhere(SandboxCase):
    """--uninstall has to be runnable from outside the project.

    The project directory is derived from the current one, so without --repo a run started
    somewhere else cleans the user scope, finds no project manifest, and looks like it
    succeeded -- the project's own keys silently survive.
    """

    def test_repo_flag_reaches_a_project_from_an_unrelated_cwd(self):
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        outside = self.box.home            # any directory that is not the project
        r = self.box.run("--repo", str(self.box.proj), "--uninstall", "--yes", cwd=outside)
        self.assertNotIn("CHAINBENCH_DIR", self.box.env_of(self.box.home))
        self.assertNotIn("GO_STABLENET_ROOT", self.box.env_of(self.box.proj))
        self.assertEqual(r.returncode, 0)

    def test_it_prints_the_directories_it_examined(self):
        """A wrong project directory is only visible if the command says which one it used."""
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        r = self.box.run("--uninstall")
        self.assertIn("looking in:", r.stdout)
        self.assertIn(str(self.box.proj), r.stdout)

    def test_a_cwd_outside_any_repo_says_the_project_is_not_in_scope(self):
        self.box.run("--fix", "--set", "CHAINBENCH_DIR=/opt/cb")
        r = self.box.run("--uninstall", cwd=self.box.home)
        self.assertIn("--repo", r.stdout, "must point the user at how to include a project")
        self.assertIn("GO_STABLENET_ROOT", self.box.env_of(self.box.proj),
                      "the project's key must survive a run that never looked at it")

    def test_a_bad_repo_path_is_rejected(self):
        r = self.box.run("--repo", "/nonexistent-xyz", "--uninstall")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
