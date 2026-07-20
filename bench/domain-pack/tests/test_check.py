#!/usr/bin/env python3
"""Tests for the domain-pack structure check (overlay P1 Phase 1).

Run:  python3 bench/domain-pack/tests/test_check.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import check  # noqa: E402


def _sandbox(tmp: Path, *, with_invariants=True, drop_key=None):
    domains = tmp / "domains" / "proj-x"
    domains.mkdir(parents=True)
    skills = tmp / "skills"
    (skills / "domain-pack").mkdir(parents=True)
    (skills / "domain-pack" / "SKILL.md").write_text("---\nname: domain-pack\n---\nloader\n")
    pack = {"project_id": "proj-x", "ticket_namespace": "PX",
            "invariants": "invariants.md", "context_classifier": "context.md",
            "knowledge": {"stablenet_knowledge_config_env": "STABLENET_KNOWLEDGE_CONFIG"},
            "verification": {
                "repo_root_env": "PROJ_X_ROOT",
                "build": {"cmd": "go build ./...", "binary_cmd": "go build -o bin/x ./cmd/x", "artifact": "bin/x"},
                "unit_test": {"full": "go test ./...", "coverage_tmpl": "go test {pkgs} -coverprofile={cover_out}",
                              "cover_report_tmpl": "go tool cover -func={cover_out}", "race_tmpl": "go test -race {pkgs}"},
                "stages": [{"id": "unit", "kind": "builtin:unit_race"}]}}
    if drop_key:
        pack.pop(drop_key)
    (domains / "domain-pack.json").write_text(json.dumps(pack))
    if with_invariants:
        (domains / "invariants.md").write_text("# inv\n")
    (domains / "context.md").write_text("# ctx\n")
    return tmp / "domains", skills


def _run(domains, skills):
    return check.check(domains_dir=domains, skills_dir=skills, check_agents=False)


class TestSandbox(unittest.TestCase):
    def test_valid_pack_passes(self):
        with tempfile.TemporaryDirectory() as d:
            dm, sk = _sandbox(Path(d))
            self.assertEqual(_run(dm, sk), 0)

    def test_missing_referenced_file_fails(self):
        with tempfile.TemporaryDirectory() as d:
            dm, sk = _sandbox(Path(d), with_invariants=False)  # invariants.md absent
            self.assertEqual(_run(dm, sk), 1)

    def test_missing_required_key_fails(self):
        with tempfile.TemporaryDirectory() as d:
            dm, sk = _sandbox(Path(d), drop_key="ticket_namespace")
            self.assertEqual(_run(dm, sk), 1)

    def test_missing_loader_skill_fails(self):
        with tempfile.TemporaryDirectory() as d:
            dm, sk = _sandbox(Path(d))
            (sk / "domain-pack" / "SKILL.md").unlink()
            self.assertEqual(_run(dm, sk), 1)


class TestRealRepo(unittest.TestCase):
    def test_repo_domain_pack_structure_ok(self):
        """The live guarantee: go-stablenet pack + loader + pointers all conform."""
        self.assertEqual(check.check(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
