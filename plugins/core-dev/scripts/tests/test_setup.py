#!/usr/bin/env python3
"""Tests for setup.py extensions — repo_root_env resolution + allowlist merge.

Run:  python3 plugins/core-dev/scripts/tests/test_setup.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import setup  # noqa: E402

SETUP_PY = _SCRIPTS / "setup.py"

# A clean env: REQUIRED keys unset so resolution is deterministic regardless of
# the developer's shell. PATH is kept so `chainbench-mcp`/`git` lookups behave.
_CLEAN_ENV = {"PATH": os.environ.get("PATH", "")}


def _run(cwd: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SETUP_PY), *flags],
                          cwd=str(cwd), capture_output=True, text=True, env=_CLEAN_ENV)


def _plugin_root(tmp: Path, packs: dict) -> Path:
    root = tmp / "plugin-root"
    for pid, rre in packs.items():
        d = root / "domains" / pid
        d.mkdir(parents=True)
        (d / "domain-pack.json").write_text(json.dumps(
            {"project_id": pid, "verification": {"repo_root_env": rre}}))
    return root


class TestRepoRootEnv(unittest.TestCase):
    def test_single_pack(self):
        with tempfile.TemporaryDirectory() as d:
            root = _plugin_root(Path(d), {"go-stablenet": "GO_STABLENET_ROOT"})
            self.assertEqual(setup._repo_root_env(root, Path("/x/repo"), None), "GO_STABLENET_ROOT")

    def test_override(self):
        with tempfile.TemporaryDirectory() as d:
            root = _plugin_root(Path(d), {"a": "A_ROOT", "b": "B_ROOT"})
            self.assertEqual(setup._repo_root_env(root, Path("/x/repo"), "b"), "B_ROOT")

    def test_name_match(self):
        with tempfile.TemporaryDirectory() as d:
            root = _plugin_root(Path(d), {"alpha": "AL", "beta": "BE"})
            self.assertEqual(setup._repo_root_env(root, Path("/x/beta-svc"), None), "BE")

    def test_no_pack_none(self):
        with tempfile.TemporaryDirectory() as d:
            root = _plugin_root(Path(d), {"alpha": "AL", "beta": "BE"})
            self.assertIsNone(setup._repo_root_env(root, Path("/x/zeta"), None))


class TestMergeAllow(unittest.TestCase):
    def test_merge_and_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.local.json"
            added1 = setup._merge_allow(p, ["mcp__x__*", "Bash(ls:*)"])
            self.assertEqual(set(added1), {"mcp__x__*", "Bash(ls:*)"})
            # re-merge: nothing new (dedup)
            added2 = setup._merge_allow(p, ["mcp__x__*", "Bash(cat:*)"])
            self.assertEqual(added2, ["Bash(cat:*)"])
            doc = json.loads(p.read_text())
            self.assertEqual(doc["permissions"]["allow"], ["mcp__x__*", "Bash(ls:*)", "Bash(cat:*)"])

    def test_preserves_existing_doc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.local.json"
            p.write_text(json.dumps({"env": {"FOO": "bar"}, "permissions": {"allow": ["keep"]}}))
            setup._merge_allow(p, ["new"])
            doc = json.loads(p.read_text())
            self.assertEqual(doc["env"], {"FOO": "bar"})          # untouched
            self.assertEqual(doc["permissions"]["allow"], ["keep", "new"])

    def test_deny_merges_alongside_allow(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.local.json"
            setup._merge_allow(p, ["Bash(ls:*)"])
            added = setup._merge_deny(p, ["Read(.env)", "Read(.secrets)"])
            self.assertEqual(added, ["Read(.env)", "Read(.secrets)"])
            # re-merge: dedup, allow untouched
            self.assertEqual(setup._merge_deny(p, ["Read(.env)"]), [])
            doc = json.loads(p.read_text())
            self.assertEqual(doc["permissions"]["allow"], ["Bash(ls:*)"])
            self.assertEqual(doc["permissions"]["deny"], ["Read(.env)", "Read(.secrets)"])


class TestAutonomousIndependentOfFix(unittest.TestCase):
    """--autonomous must register the allowlist even without --fix (bug fix)."""

    def test_autonomous_alone_writes_allow_no_env(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            r = _run(d, "--autonomous")
            local = json.loads((d / ".claude" / "settings.local.json").read_text())
            self.assertEqual(local["permissions"]["allow"], setup.AUTONOMOUS_ALLOW)
            self.assertEqual(local["permissions"]["deny"], setup.AUTONOMOUS_DENY)
            # no --fix -> no env block, no settings.json
            self.assertNotIn("env", local)
            self.assertFalse((d / ".claude" / "settings.json").exists())
            # secret-file path is gitignored
            self.assertIn(".claude/settings.local.json", (d / ".gitignore").read_text())
            self.assertIn("registered", r.stdout)

    def test_autonomous_covers_pipeline_write_path(self):
        """The allowlist must cover implementer/evaluator tool use (edits, build, git),
        and must NOT include merge/tag/release entries — those stay prompted."""
        for entry in ("Write", "Edit", "Bash(go test:*)", "Bash(make:*)",
                      "Bash(git commit:*)", "Bash(git push:*)", "Bash(gh pr create:*)"):
            self.assertIn(entry, setup.AUTONOMOUS_ALLOW)
        joined = " ".join(setup.AUTONOMOUS_ALLOW)
        for forbidden in ("gh pr merge", "git tag", "git merge", "Bash(git:*)", "Bash(gh:*)"):
            self.assertNotIn(forbidden, joined)
        # deny shields secrets (incl. the settings file that stores JIRA_API_TOKEN)
        self.assertIn("Read(.env)", setup.AUTONOMOUS_DENY)
        self.assertIn("Read(.claude/settings.local.json)", setup.AUTONOMOUS_DENY)


class TestPluginRepoGuard(unittest.TestCase):
    """repo_root_env must NOT be pinned when cwd is the core-dev plugin repo."""

    def test_plugin_repo_reports_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / ".claude-plugin").mkdir()           # marker => is_plugin_repo
            r = _run(d, "--check")
            self.assertIn("MISMATCH", r.stdout)
            self.assertNotIn("REPO-ROOT", r.stdout)

    def test_target_repo_pins_repo_root(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)                              # no marker => target repo
            r = _run(d, "--check")
            self.assertIn("REPO-ROOT", r.stdout)
            self.assertIn("GO_STABLENET_ROOT", r.stdout)

    def test_fix_in_plugin_repo_skips_repo_root_env(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / ".claude-plugin").mkdir()
            r = _run(d, "--fix")
            self.assertIn("skipped GO_STABLENET_ROOT", r.stdout)
            settings = d / ".claude" / "settings.json"
            env = json.loads(settings.read_text()).get("env", {}) if settings.exists() else {}
            self.assertNotIn("GO_STABLENET_ROOT", env)

    def test_project_override_pins_even_in_plugin_repo(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / ".claude-plugin").mkdir()
            # explicit --project means the user asserts the active pack -> pin it
            r = _run(d, "--check", "--project", "go-stablenet")
            self.assertIn("REPO-ROOT", r.stdout)


class TestJSONOutput(unittest.TestCase):
    """--json is what /stablenet-expert:doctor drives the fix interaction from.

    It exists because delegating by skill name cannot reach a plugin installed in
    the same session — Claude Code registers a plugin's commands at startup — while
    running this script by path can. The contract the caller depends on is pinned
    here: the fields it reads, and that a secret's value is never among them.
    """

    def test_shape_and_no_secret_value(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / ".claude").mkdir()
            (tmp / ".claude" / "settings.local.json").write_text(json.dumps(
                {"env": {"JIRA_API_TOKEN": "super-secret-token-value"}}))
            r = _run(tmp, "--check", "--json")
            payload = json.loads(r.stdout)

            for field in ("plugin", "project", "rows", "missing", "auto_fixable"):
                self.assertIn(field, payload, f"caller reads {field}")
            for row in payload["rows"]:
                for field in ("key", "description", "how_to_find", "status",
                              "auto_fixable", "secret"):
                    self.assertIn(field, row, f"caller reads row.{field}")

            self.assertNotIn("super-secret-token-value", r.stdout,
                             "a secret's value must never reach the caller's transcript")
            secrets = [row for row in payload["rows"] if row["secret"]]
            self.assertTrue(secrets, "JIRA_API_TOKEN should be marked secret")
            for row in secrets:
                self.assertNotIn("value", row)

    def test_json_suppresses_the_text_report(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            r = _run(tmp, "--check", "--json")
            self.assertNotIn("KEY", r.stdout, "text table must not be mixed into JSON stdout")
            json.loads(r.stdout)   # parses as a whole — nothing appended around it

    def test_missing_key_carries_its_description_and_hint(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            payload = json.loads(_run(tmp, "--check", "--json").stdout)
            missing = [row for row in payload["rows"] if row["status"] == "missing"]
            self.assertTrue(missing, "a bare temp dir resolves nothing")
            for row in missing:
                self.assertTrue(row["description"], f"{row['key']} needs a description to offer")
                self.assertFalse(row["auto_fixable"], "missing values cannot be written unattended")


if __name__ == "__main__":
    unittest.main(verbosity=2)
