#!/usr/bin/env python3
"""Tests for the model-pin single-source check.

Run:  python3 bench/model-pins/tests/test_check.py
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


def _sandbox(tmp: Path, *, analyzer="claude-opus-4-8", evaluator="claude-sonnet-4-6",
             prices=("claude-opus-4-8", "claude-sonnet-4-6")):
    models = {"tiers": {"deep": "claude-opus-4-8", "exec": "claude-sonnet-4-6"},
              "agents": {"analyzer": "deep", "evaluator": "exec"}}
    (tmp / "models.json").write_text(json.dumps(models))
    agents = tmp / "agents"; agents.mkdir()
    (agents / "analyzer.md").write_text(f"---\nname: analyzer\nmodel: {analyzer}\n---\nbody\n")
    (agents / "evaluator.md").write_text(f"---\nname: evaluator\nmodel: {evaluator}\n---\nbody\n")
    (tmp / "prices.json").write_text(json.dumps({m: {"input": 1} for m in prices}))
    return (tmp / "models.json", agents, tmp / "prices.json")


def _run(tmp, apply=False):
    mp, ad, pp = (tmp / "models.json", tmp / "agents", tmp / "prices.json")
    return check.check(apply, models_path=mp, agents_dir=ad, prices_path=pp, check_capture=False)


class TestUnit(unittest.TestCase):
    def test_resolve(self):
        doc = {"tiers": {"deep": "O", "exec": "S"}, "agents": {"a": "deep", "b": "exec"}}
        self.assertEqual(check.resolve(doc), {"a": "O", "b": "S"})

    def test_frontmatter_parse(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("---\nname: x\nmodel: claude-opus-4-8\n---\n")
            self.assertEqual(check.frontmatter_model(p), "claude-opus-4-8")


class TestSandbox(unittest.TestCase):
    def test_conforming_sandbox_passes(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); _sandbox(tmp)
            self.assertEqual(_run(tmp), 0)

    def test_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); _sandbox(tmp, analyzer="claude-opus-4-7")   # stale pin
            self.assertEqual(_run(tmp), 1)

    def test_apply_fixes_drift(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); _sandbox(tmp, analyzer="claude-opus-4-7")
            self.assertEqual(_run(tmp), 1)               # drift before
            self.assertEqual(_run(tmp, apply=True), 0)   # --apply resolves it
            self.assertEqual(check.frontmatter_model(tmp / "agents" / "analyzer.md"),
                             "claude-opus-4-8")
            self.assertEqual(_run(tmp), 0)               # stays fixed

    def test_prices_gap_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); _sandbox(tmp, prices=("claude-sonnet-4-6",))  # missing opus price
            self.assertEqual(_run(tmp), 1)


class TestRealRepo(unittest.TestCase):
    def test_repo_pins_conform(self):
        """The live guarantee: the real repo's pins all match models.json."""
        self.assertEqual(check.check(apply=False), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
