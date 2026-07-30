#!/usr/bin/env python3
"""Tests for the MCP tool-name namespace single-source sync.

Run:  python3 scripts/contract/tests/test_sync_mcp_namespace.py
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent  # scripts/contract

_spec = importlib.util.spec_from_file_location(
    "sync_mcp_namespace", _PKG / "sync-mcp-namespace.py")
sync_mcp_namespace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_mcp_namespace)


def _sandbox(tmp: Path, *, tool_prefix="cks", schema_prefix="cks",
             md_prefix="cks", base_tool_names=None):
    """Build a minimal sandbox: mcp-namespace.json + a 2-tool schema.json +
    one agent .md referencing both tools. schema_prefix/md_prefix let a test
    plant drift independently in either file."""
    base_tool_names = base_tool_names or ["ops_health", "context_get_for_task"]
    ns = {
        "server": "stablenet-knowledge",
        "tool_prefix": tool_prefix,
        "base_tool_names": base_tool_names,
    }
    (tmp / "scripts" / "contract").mkdir(parents=True)
    ns_path = tmp / "scripts" / "contract" / "mcp-namespace.json"
    ns_path.write_text(json.dumps(ns, indent=2))

    schema = {
        "providers": {
            "stablenet-knowledge": {
                "server": "stablenet-knowledge",
                "tools": {
                    f"{schema_prefix}_{b}": {"owner": "stablenet-knowledge", "description": "d"}
                    for b in base_tool_names
                },
            },
            "chainbench": {
                "server": "chainbench",
                "tools": {"chainbench_init": {"owner": "chainbench", "description": "d"}},
            },
        }
    }
    schema_path = tmp / "scripts" / "contract" / "agent-mcp.schema.json"
    schema_path.write_text(json.dumps(schema, indent=2))

    plugins_dir = tmp / "plugins"
    agents = plugins_dir / "core-dev" / "agents"
    agents.mkdir(parents=True)
    lines = "\n".join(
        f"call = mcp__plugin_core-dev_stablenet-knowledge__{md_prefix}_{b}()"
        for b in base_tool_names
    )
    (agents / "analyzer.md").write_text(f"---\nname: analyzer\n---\n{lines}\n")

    return ns_path, schema_path, plugins_dir


def _run(ns_path, schema_path, plugins_dir, apply=False):
    return sync_mcp_namespace.check(
        apply, namespace_path=ns_path, schema_path=schema_path, plugins_dir=plugins_dir)


class TestPattern(unittest.TestCase):
    def test_simple_prefix(self):
        pat = sync_mcp_namespace._pattern(["ops_health"])
        m = pat.search("cks_ops_health()")
        self.assertEqual(m.group(1), "cks")
        self.assertEqual(m.group(2), "ops_health")

    def test_multiword_prefix_not_truncated(self):
        # the bug this test guards against: a naive prefix regex captures
        # only "knowledge" (the last underscore-joined word) instead of the
        # full "stablenet_knowledge" — see sync-mcp-namespace.py's _pattern
        # docstring/comments for the two failure modes this was tuned against.
        pat = sync_mcp_namespace._pattern(["context_change_history"])
        m = pat.search("stablenet_knowledge_context_change_history")
        self.assertEqual(m.group(1), "stablenet_knowledge")

    def test_does_not_cross_mcp_double_underscore(self):
        # "stablenet-knowledge__cks_context_get_for_task": the "__" is the
        # structural mcp__<server>__<tool> delimiter, never part of a prefix.
        # A regression here would merge "knowledge__cks" into one bogus prefix.
        pat = sync_mcp_namespace._pattern(["context_get_for_task"])
        m = pat.search("mcp__plugin_core-dev_stablenet-knowledge__cks_context_get_for_task")
        self.assertEqual(m.group(1), "cks")


class TestSandbox(unittest.TestCase):
    def test_conforming_sandbox_passes(self):
        with tempfile.TemporaryDirectory() as d:
            ns, schema, plugins = _sandbox(Path(d))
            self.assertEqual(_run(ns, schema, plugins), 0)

    def test_schema_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            ns, schema, plugins = _sandbox(Path(d), tool_prefix="stablenet_knowledge",
                                            schema_prefix="cks")  # schema still stale
            self.assertEqual(_run(ns, schema, plugins), 1)

    def test_agent_file_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            ns, schema, plugins = _sandbox(Path(d), tool_prefix="stablenet_knowledge",
                                            schema_prefix="stablenet_knowledge",
                                            md_prefix="cks")  # agent .md still stale
            self.assertEqual(_run(ns, schema, plugins), 1)

    def test_apply_fixes_both_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            ns, schema, plugins = _sandbox(Path(d), tool_prefix="stablenet_knowledge",
                                            schema_prefix="cks", md_prefix="cks")
            self.assertEqual(_run(ns, schema, plugins), 1)                 # drift before
            self.assertEqual(_run(ns, schema, plugins, apply=True), 0)     # --apply resolves it
            self.assertEqual(_run(ns, schema, plugins), 0)                 # stays fixed
            self.assertEqual(_run(ns, schema, plugins, apply=True), 0)     # idempotent no-op

            schema_doc = json.loads(schema.read_text())
            self.assertIn("stablenet_knowledge_ops_health",
                           schema_doc["providers"]["stablenet-knowledge"]["tools"])
            self.assertIn("stablenet_knowledge_ops_health",
                           (plugins / "core-dev" / "agents" / "analyzer.md").read_text())

    def test_apply_is_reversible_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            ns, schema, plugins = _sandbox(Path(d))
            orig_schema = schema.read_text()
            orig_md = (plugins / "core-dev" / "agents" / "analyzer.md").read_text()

            ns_doc = json.loads(ns.read_text())
            ns_doc["tool_prefix"] = "stablenet_knowledge"
            ns.write_text(json.dumps(ns_doc))
            self.assertEqual(_run(ns, schema, plugins, apply=True), 0)

            ns_doc["tool_prefix"] = "cks"
            ns.write_text(json.dumps(ns_doc))
            self.assertEqual(_run(ns, schema, plugins, apply=True), 0)

            self.assertEqual(schema.read_text(), orig_schema)
            self.assertEqual((plugins / "core-dev" / "agents" / "analyzer.md").read_text(), orig_md)

    def test_chainbench_provider_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            ns, schema, plugins = _sandbox(Path(d), tool_prefix="stablenet_knowledge",
                                            schema_prefix="cks", md_prefix="cks")
            _run(ns, schema, plugins, apply=True)
            schema_doc = json.loads(schema.read_text())
            self.assertIn("chainbench_init", schema_doc["providers"]["chainbench"]["tools"])

    def test_unrecognized_schema_key_reported(self):
        with tempfile.TemporaryDirectory() as d:
            ns, schema, plugins = _sandbox(Path(d))
            schema_doc = json.loads(schema.read_text())
            schema_doc["providers"]["stablenet-knowledge"]["tools"]["cks_totally_unknown"] = \
                {"owner": "x", "description": "d"}
            schema.write_text(json.dumps(schema_doc))
            self.assertEqual(_run(ns, schema, plugins), 1)


class TestRealRepo(unittest.TestCase):
    def test_repo_conforms(self):
        """The live guarantee: every real cks_* reference matches mcp-namespace.json."""
        self.assertEqual(sync_mcp_namespace.check(apply=False), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
