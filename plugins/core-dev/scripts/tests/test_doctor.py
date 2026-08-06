#!/usr/bin/env python3
"""Tests for doctor.py — the read-only environment diagnostics helper.

Run:  python3 plugins/core-dev/scripts/tests/test_doctor.py
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import doctor  # noqa: E402

DOCTOR_PY = _SCRIPTS / "doctor.py"


def _make_plugin_root(tmp: Path, packs: dict) -> Path:
    """packs = {project_id: repo_root_env}. Build a minimal plugin-root."""
    root = tmp / "plugin-root"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": "9.9.9"}))
    for pid, rre in packs.items():
        d = root / "domains" / pid
        d.mkdir(parents=True)
        (d / "domain-pack.json").write_text(json.dumps(
            {"project_id": pid, "verification": {"repo_root_env": rre}}))
    return root


class TestDetectProjectId(unittest.TestCase):
    def test_single_pack(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_plugin_root(Path(d), {"go-stablenet": "GO_STABLENET_ROOT"})
            pid, packs = doctor.detect_project_id(root, "", None)
            self.assertEqual(pid, "go-stablenet")
            self.assertEqual(packs, ["go-stablenet"])

    def test_override_wins(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_plugin_root(Path(d), {"a": "A_ROOT", "b": "B_ROOT"})
            pid, _ = doctor.detect_project_id(root, "", "b")
            self.assertEqual(pid, "b")

    def test_multi_name_match(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_plugin_root(Path(d), {"alpha": "A", "beta": "B"})
            pid, _ = doctor.detect_project_id(root, "/work/repos/beta-service", None)
            self.assertEqual(pid, "beta")

    def test_multi_no_match_none(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_plugin_root(Path(d), {"alpha": "A", "beta": "B"})
            pid, _ = doctor.detect_project_id(root, "/work/repos/zeta", None)
            self.assertIsNone(pid)


class TestTextReport(unittest.TestCase):
    """The default output path had no test, which is how a stale key reference shipped:
    render() still read out["stablenet_knowledge_config"] after the section was removed, so
    `doctor.py` with no flags died with a KeyError while `--json` stayed green.

    A structural assertion on the JSON does not cover render() -- the two read the payload
    independently -- so the text path needs its own smoke test."""

    def _run(self, *extra):
        with tempfile.TemporaryDirectory() as d:
            root = _make_plugin_root(Path(d), {"go-stablenet": "GO_STABLENET_ROOT"})
            return subprocess.run(
                [sys.executable, str(DOCTOR_PY), "--plugin-root", str(root), *extra],
                cwd=d, capture_output=True, text=True)

    def test_default_output_renders_without_crashing(self):
        r = self._run()
        self.assertEqual(r.stderr, "", "the text report must not raise")
        self.assertIn("core-dev doctor", r.stdout)
        self.assertIn("env:", r.stdout)
        self.assertIn("permissions:", r.stdout)

    def test_exit_code_reflects_the_verdict_not_a_crash(self):
        """1 has to mean ATTENTION. A traceback also exits non-zero, so a caller reading only
        the status cannot tell a diagnosis from a broken script -- hence checking stderr too."""
        r = self._run()
        self.assertIn(r.returncode, (0, 1))
        self.assertNotIn("Traceback", r.stderr)

    def test_every_section_the_renderer_reads_is_present_in_json(self):
        """Pins the two paths together: whatever render() pulls out of the payload must be a
        key --json also emits, so removing a section cannot break one and not the other."""
        import re
        source = DOCTOR_PY.read_text()
        render_src = source[source.index("def render("):]
        render_src = render_src[:render_src.index("\ndef ", 1)] if "\ndef " in render_src[1:] else render_src
        keys = set(re.findall(r'out\["(\w+)"\]', render_src))
        payload = json.loads(self._run("--json").stdout)
        for k in keys:
            self.assertIn(k, payload, f"render() reads out[{k!r}] but --json does not emit it")


class TestSmoke(unittest.TestCase):
    def test_json_report_structure(self):
        with tempfile.TemporaryDirectory() as d:
            root = _make_plugin_root(Path(d), {"go-stablenet": "GO_STABLENET_ROOT"})
            r = subprocess.run(
                [sys.executable, str(DOCTOR_PY), "--plugin-root", str(root), "--json"],
                cwd=d, capture_output=True, text=True)
            out = json.loads(r.stdout)
            for key in ("plugin", "project", "domain_pack", "env",
                        "permissions", "verdict", "issues", "restart_needed", "remediations"):
                self.assertIn(key, out)
            # No stablenet_knowledge_config section: the server is remote (HTTP), so this
            # machine has no config yaml to stat. Its health is probed live by the command
            # through cks_ops_health, against the host that actually serves the index.
            self.assertNotIn("stablenet_knowledge_config", out)
            self.assertEqual(out["plugin"]["active_version"], "9.9.9")
            self.assertEqual(out["domain_pack"]["project_id"], "go-stablenet")
            self.assertEqual(out["domain_pack"]["repo_root_env"], "GO_STABLENET_ROOT")
            # GO_STABLENET_ROOT unset in this sandbox -> reported in env table
            self.assertIn("GO_STABLENET_ROOT", out["env"])

    def test_secret_masked(self):
        # SECRETS is empty now that Jira authenticates over OAuth (ADR-0013): the
        # masking helper still has to work, so it is exercised against a name that
        # *would* be a secret if one were ever added back.
        doctor.SECRETS.add("TEST_ONLY_TOKEN")
        try:
            self.assertEqual(doctor._mask("TEST_ONLY_TOKEN", "supersecret"), "********")
        finally:
            doctor.SECRETS.discard("TEST_ONLY_TOKEN")
        self.assertEqual(doctor._mask("CHAINBENCH_DIR", "/path"), "/path")


class TestRemediationTable(unittest.TestCase):
    """Gate: the fix table is the single source — every entry well-formed, no orphans."""

    def test_every_entry_well_formed(self):
        for kind, r in doctor.REMEDIATION.items():
            self.assertIn(r["klass"], doctor.KLASSES, f"{kind}: bad klass")
            # must give the user something actionable: a command or an action
            self.assertTrue(r.get("command") or r.get("action"), f"{kind}: empty fix")

    def test_no_orphan_issue_kinds(self):
        """Every kind passed to _add_issue() in doctor.py must exist in REMEDIATION."""
        src = (_SCRIPTS / "doctor.py").read_text()
        emitted = set(re.findall(r'_add_issue\(out,\s*"([^"]+)"', src))
        self.assertTrue(emitted, "no _add_issue calls found — regex/source drift")
        missing = emitted - set(doctor.REMEDIATION)
        self.assertEqual(missing, set(), f"issue kinds with no fix-table entry: {missing}")

    def test_remediation_kinds_resolve(self):
        """Every kind the remediation builder can add resolves in REMEDIATION."""
        src = (_SCRIPTS / "doctor.py").read_text()
        # kinds added via add("...") inside _remediations + the issue kinds
        added = set(re.findall(r'\badd\("([^"]+)"', src))
        for k in added:
            self.assertIn(k, doctor.REMEDIATION, f"remediation kind {k!r} not in fix table")


class TestRemediationRouting(unittest.TestCase):
    def _run_json(self, cwd, plugin_root):
        # strip required env so the fresh-repo path is deterministic
        import os
        env = {k: v for k, v in os.environ.items() if k not in doctor.ENV_KEYS}
        r = subprocess.run(
            [sys.executable, str(DOCTOR_PY), "--plugin-root", str(plugin_root), "--json"],
            cwd=str(cwd), capture_output=True, text=True, env=env)
        return json.loads(r.stdout)

    def test_fresh_repo_routes_to_setup(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            root = _make_plugin_root(d, {"go-stablenet": "GO_STABLENET_ROOT"})
            out = self._run_json(d, root)
            self.assertIn("remediations", out)
            self.assertEqual(out["verdict"], "ATTENTION")
            kinds = [r["kind"] for r in out["remediations"]]
            self.assertIn("repo_root_env_unset", kinds)
            # every remediation carries a klass and an actionable target
            for r in out["remediations"]:
                self.assertIn(r["klass"], doctor.KLASSES)
                self.assertTrue(r["command"] or r["action"])
            # the repo_root_env fix routes to our setup command
            rre = next(r for r in out["remediations"] if r["kind"] == "repo_root_env_unset")
            self.assertEqual(rre["klass"], "setup")
            self.assertIn("setup --fix", rre["command"])

    def test_repo_root_env_not_duplicated_in_env_unset(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            root = _make_plugin_root(d, {"go-stablenet": "GO_STABLENET_ROOT"})
            out = self._run_json(d, root)
            self.assertNotIn("GO_STABLENET_ROOT",
                             next((r["detail"] for r in out["remediations"]
                                   if r["kind"] == "env_unset"), ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
