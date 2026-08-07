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


def _run(cwd: Path, *flags: str, home: Path | None = None) -> subprocess.CompletedProcess:
    """Run setup.py in `cwd`.

    HOME points at an empty directory by default. setup.py falls back to the *global*
    ~/.claude/settings.json when a key is not resolved locally, so without this a developer
    who has CHAINBENCH_DIR in their own settings sees different results from CI. That went
    unnoticed while REQUIRED held several keys -- some were always unresolvable -- and
    surfaced the moment it held one.
    """
    env = dict(_CLEAN_ENV, HOME=str(home or (cwd / "_isolated_home")))
    return subprocess.run([sys.executable, str(SETUP_PY), *flags],
                          cwd=str(cwd), capture_output=True, text=True, env=env)


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
        # deny shields secrets (the settings file that would hold any future token)
        self.assertIn("Read(.env)", setup.AUTONOMOUS_DENY)
        self.assertIn("Read(.claude/settings.local.json)", setup.AUTONOMOUS_DENY)


def _git_repo(d: Path) -> Path:
    """A real repository. These tests are about *which* repo gets pinned, so the directory has
    to be one -- a bare temp dir is now refused as NOT-A-REPO before the plugin-repo guard is
    ever reached."""
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    return d


class TestPluginRepoGuard(unittest.TestCase):
    """repo_root_env must NOT be pinned when cwd is the core-dev plugin repo."""

    def test_plugin_repo_reports_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            d = _git_repo(Path(d))
            (d / ".claude-plugin").mkdir()           # marker => is_plugin_repo
            r = _run(d, "--check")
            self.assertIn("MISMATCH", r.stdout)
            self.assertNotIn("REPO-ROOT", r.stdout)

    def test_target_repo_pins_repo_root(self):
        with tempfile.TemporaryDirectory() as d:
            d = _git_repo(Path(d))                   # no marker => target repo
            r = _run(d, "--check")
            self.assertIn("REPO-ROOT", r.stdout)
            self.assertIn("GO_STABLENET_ROOT", r.stdout)

    def test_fix_in_plugin_repo_skips_repo_root_env(self):
        with tempfile.TemporaryDirectory() as d:
            d = _git_repo(Path(d))
            (d / ".claude-plugin").mkdir()
            r = _run(d, "--fix")
            self.assertIn("skipped GO_STABLENET_ROOT", r.stdout)
            settings = d / ".claude" / "settings.json"
            env = json.loads(settings.read_text()).get("env", {}) if settings.exists() else {}
            self.assertNotIn("GO_STABLENET_ROOT", env)

    def test_project_override_pins_even_in_plugin_repo(self):
        with tempfile.TemporaryDirectory() as d:
            d = _git_repo(Path(d))
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
            r = _run(tmp, "--check", "--json")
            payload = json.loads(r.stdout)

            for field in ("plugin", "project", "rows", "missing", "auto_fixable"):
                self.assertIn(field, payload, f"caller reads {field}")
            for row in payload["rows"]:
                for field in ("key", "description", "how_to_find", "status",
                              "auto_fixable", "secret"):
                    self.assertIn(field, row, f"caller reads row.{field}")

            # No row is secret today -- Jira moved to OAuth (ADR-0013) and nothing else
            # here holds a credential. The contract still has to hold for whatever secret
            # comes next, so the invariant is asserted over whatever rows claim to be one.
            for row in payload["rows"]:
                self.assertIn("secret", row, f"{row['key']} must declare it")
                if row["secret"]:
                    self.assertNotIn("value", row,
                                     "a secret's value must never reach the caller")

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

            # The "unattended" rule is about *values*: nobody can write an env var whose
            # value is unknown, so offering to is a bug. It does not generalise to other
            # row kinds -- a missing plugin is missing in a different sense (not installed)
            # and installing it asks the user for no value at all.
            for row in [r for r in missing if r["row_kind"] == "env"]:
                self.assertFalse(row["auto_fixable"], "missing values cannot be written unattended")

    def test_non_env_rows_declare_their_kind_and_side_effects(self):
        """doctor branches on row_kind, and must be able to warn before a fix does something
        visible (an OAuth browser window). Both facts have to travel in the row."""
        with tempfile.TemporaryDirectory() as td:
            payload = json.loads(_run(Path(td), "--check", "--json").stdout)
            for row in payload["rows"]:
                self.assertIn(row["row_kind"], ("env", "plugin"), row["key"])
                self.assertIn("opens_browser", row, f"{row['key']} must say if it is visible")
            plugin_rows = [r for r in payload["rows"] if r["row_kind"] == "plugin"]
            self.assertTrue(plugin_rows, "the Atlassian dependency should be reported")

    def test_not_ready_is_reported_alongside_missing(self):
        """`missing` alone cannot express every unusable state -- an installed-but-
        unauthenticated plugin is present and still unusable -- so the caller gets a second
        list. Only its shape is asserted here: whether the Atlassian plugin happens to be
        installed on the machine running the tests is not this test's business, and
        test_atlassian.py pins that behaviour against an injected CLI."""
        with tempfile.TemporaryDirectory() as td:
            payload = json.loads(_run(Path(td), "--check", "--json").stdout)
            self.assertIn("not_ready", payload)
            keys = {r["key"] for r in payload["rows"]}
            self.assertTrue(set(payload["not_ready"]) <= keys, "not_ready must name rows")
            for key in payload["missing"]:
                self.assertIn(key, payload["not_ready"], "missing implies not ready")


class TestRowsDeclareTheirServer(unittest.TestCase):
    """doctor groups its questions by `serves`. The grouping has to come from the plugin: doctor
    owns no knowledge of another plugin's environment (ADR-0011 §2.2), and inferring it from key
    names there would break the moment a plugin adds a second value for the same server."""

    def test_every_row_carries_serves(self):
        with tempfile.TemporaryDirectory() as td:
            payload = json.loads(_run(Path(td), "--check", "--json").stdout)
            for row in payload["rows"]:
                self.assertIn("serves", row, f"{row['key']} must say which server it is for")

    def test_the_three_servers_are_covered(self):
        with tempfile.TemporaryDirectory() as td:
            payload = json.loads(_run(Path(td), "--check", "--json").stdout)
            served = {r["serves"] for r in payload["rows"] if r["serves"]}
            self.assertEqual(served, {"atlassian", "stablenet-knowledge", "chainbench"})


class TestValueVisibility(unittest.TestCase):
    """A caller has to be able to show what it is about to write -- except where showing it is
    the problem."""

    def test_a_path_carries_its_value(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            r = _run(tmp, "--check", "--json", "--set", "CHAINBENCH_DIR=/opt/cb")
            row = next(x for x in json.loads(r.stdout)["rows"] if x["key"] == "CHAINBENCH_DIR")
            self.assertEqual(row["resolved_value"], "/opt/cb")
            self.assertFalse(row["value_withheld"])

    def test_an_endpoint_never_does(self):
        """commands/doctor.md: never print a resolved MCP connection value. That rule is not
        about credentials -- an endpoint names a machine on someone's network, and this output
        becomes a conversation transcript."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            r = _run(tmp, "--check", "--json",
                     "--set", "STABLENET_KNOWLEDGE_MCP_URL=http://10.1.2.3:9999/mcp")
            self.assertNotIn("10.1.2.3", r.stdout, "an endpoint must not reach the caller")
            row = next(x for x in json.loads(r.stdout)["rows"]
                       if x["key"] == "STABLENET_KNOWLEDGE_MCP_URL")
            self.assertIsNone(row["resolved_value"])
            self.assertTrue(row["value_withheld"], "must say it is set, just not shown")


class TestOnlyPersistedCountsAsReady(unittest.TestCase):
    def test_a_process_only_value_is_not_ready(self):
        """`env` means the value is in this process and nowhere on disk. Claude Code reads
        ${VAR} from settings, so such a value is gone at restart -- reporting it as ready is
        how a machine passes setup and then fails to start its MCP servers next session."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            env = dict(_CLEAN_ENV, HOME=str(tmp / "_h"), CHAINBENCH_DIR="/opt/cb")
            r = subprocess.run([sys.executable, str(SETUP_PY), "--check", "--json"],
                               cwd=str(tmp), capture_output=True, text=True, env=env)
            payload = json.loads(r.stdout)
            row = next(x for x in payload["rows"] if x["key"] == "CHAINBENCH_DIR")
            self.assertEqual(row["status"], "env")
            self.assertIn("CHAINBENCH_DIR", payload["not_ready"])
            self.assertTrue(row["auto_fixable"], "the value is known; only the writing is missing")

    def test_a_persisted_value_is_ready(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / ".claude").mkdir()
            (tmp / ".claude" / "settings.json").write_text(
                json.dumps({"env": {"CHAINBENCH_DIR": "/opt/cb"}}))
            payload = json.loads(_run(tmp, "--check", "--json").stdout)
            row = next(x for x in payload["rows"] if x["key"] == "CHAINBENCH_DIR")
            self.assertEqual(row["status"], "project")
            self.assertNotIn("CHAINBENCH_DIR", payload["not_ready"])


class TestRepoRootEnvIsChecked(unittest.TestCase):
    def test_a_directory_that_is_not_a_repo_is_refused(self):
        """_repo_root() falls back to the cwd when git says nothing, so running from a folder
        that merely contains checkouts would pin that folder -- and the Evaluator would run the
        pack's build and test commands in a directory that was never a project."""
        with tempfile.TemporaryDirectory() as td:
            r = _run(Path(td), "--check")
            self.assertIn("NOT-A-REPO", r.stdout)
            self.assertNotIn("REPO-ROOT", r.stdout)

    def test_a_real_repo_is_pinned(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            r = _run(tmp, "--check")
            self.assertIn("REPO-ROOT", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
