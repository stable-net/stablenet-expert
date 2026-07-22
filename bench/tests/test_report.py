"""End-to-end test: synthetic experiment dir -> collect -> report -> CLI.

    python3 -m unittest bench.tests.test_report
"""

import json
import tempfile
import unittest
from pathlib import Path

from bench.lib.collect import collect_experiment
from bench.lib.report import build_report, aggregate, to_markdown, to_csv
from bench import compare


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def make_experiment(root: Path):
    """1 task x 3 modes; A & C pass, B fails. Estimated tokens via transcripts."""
    exp = root / "exp"
    cells = [
        ("STABLE-0001", "A_stablenet_knowledge_mcp", "EVALUATION_PASS"),
        ("STABLE-0001", "B_code_only", "EVALUATION_FAIL"),
        ("STABLE-0001", "C_code_skills", "EVALUATION_PASS"),
    ]
    _write(exp / "manifest.json", {"experiment": "unit-exp"})
    state_cells = []
    for task, mode, pstate in cells:
        wsname = f"{task}__{mode}"
        cell = exp / "cells" / wsname
        state_cells.append({"task": task, "mode": mode,
                            "workspace": f"cells/{wsname}", "status": "done"})
        _write(cell / "run-meta.json", {
            "experiment": "unit-exp", "task": task, "mode": mode,
            "started_at": "2026-06-04T10:00:00Z", "ended_at": "2026-06-04T10:05:00Z",
        })
        _write(cell / "state.json", {
            "ticket_id": task, "current_state": pstate,
            "states": {
                "TICKET_INTAKE": {"sensitive_check": {"result": "CLEAN"}},
                "EVALUATION": {"results": {
                    "unit_test": {"status": "PASS" if pstate == "EVALUATION_PASS" else "FAIL"},
                    "security": {"status": "PASS"},
                    "chainbench": {"status": "PASS" if pstate == "EVALUATION_PASS" else "FAIL"},
                }},
            },
        })
        # B (code-only) burns more tokens (bigger grep/read prompts).
        chars = 8000 if mode == "B_code_only" else 2000
        _write_jsonl(cell / "logs" / "agent-transcript.jsonl", [
            {"subagent_type": "analyzer" if mode == "A_stablenet_knowledge_mcp"
             else "bench-analyzer-codeonly" if mode == "B_code_only" else "bench-analyzer-skills",
             "prompt_chars": chars, "response_chars": 400},
            {"subagent_type": "implementer", "prompt_chars": 1000, "response_chars": 600},
            {"subagent_type": "evaluator", "prompt_chars": 1200, "response_chars": 300},
        ])
    _write(exp / "state.json", {"experiment": "unit-exp", "cells": state_cells})
    return exp


class TestCollectReport(unittest.TestCase):
    def test_collect_correctness_and_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            exp = make_experiment(Path(d))
            results = collect_experiment(exp)
            self.assertEqual(len(results), 3)
            by_mode = {r.mode: r for r in results}
            self.assertIs(by_mode["A_stablenet_knowledge_mcp"].correct, True)
            self.assertIs(by_mode["B_code_only"].correct, False)
            self.assertIs(by_mode["C_code_skills"].correct, True)
            # All have positive token estimates and a latency of 300s.
            for r in results:
                self.assertGreater(r.usage.total(), 0)
                self.assertEqual(r.latency_s, 300.0)
                self.assertEqual(r.cost_status, "estimated")
            # B should cost more (bigger planner prompt).
            self.assertGreater(by_mode["B_code_only"].usage.total(),
                               by_mode["A_stablenet_knowledge_mcp"].usage.total())

    def test_string_sensitive_check_does_not_crash(self):
        """A malformed cell (bare-string sensitive_check) must not take down the
        whole experiment report — the no-truncation rule."""
        with tempfile.TemporaryDirectory() as d:
            exp = make_experiment(Path(d))
            state_path = exp / "cells" / "STABLE-0001__A_stablenet_knowledge_mcp" / "state.json"
            state = json.loads(state_path.read_text())
            state["states"]["TICKET_INTAKE"]["sensitive_check"] = "CLEAN"
            _write(state_path, state)
            results = collect_experiment(exp)
            self.assertEqual(len(results), 3)
            by_mode = {r.mode: r for r in results}
            self.assertEqual(by_mode["A_stablenet_knowledge_mcp"].safety_flags, [])
            # A bare-string REDACTED verdict is still flagged.
            state["states"]["TICKET_INTAKE"]["sensitive_check"] = "REDACTED"
            _write(state_path, state)
            by_mode = {r.mode: r for r in collect_experiment(exp)}
            self.assertIn("sensitive_redacted", by_mode["A_stablenet_knowledge_mcp"].safety_flags)

    def test_aggregate_and_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            exp = make_experiment(Path(d))
            results = collect_experiment(exp)
            roll = aggregate(results)
            self.assertEqual(roll["A_stablenet_knowledge_mcp"]["correct"], 1)
            self.assertEqual(roll["A_stablenet_knowledge_mcp"]["evaluated"], 1)
            self.assertEqual(roll["B_code_only"]["correct"], 0)
            md = to_markdown(build_report(results, experiment="unit-exp"))
            self.assertIn("A_stablenet_knowledge_mcp", md)
            self.assertIn("Mode rollup", md)
            self.assertIn("estimated", md)  # cost caveat present
            csv_text = to_csv(results)
            self.assertEqual(csv_text.strip().count("\n"), 3)  # header + 3 rows

    def test_bug_cycles_and_side_effects(self):
        """A passes first try (0 cycles); B reaches PASS after 2 bug-cycles,
        one of which is a regression-class (chainbench) side-effect."""
        with tempfile.TemporaryDirectory() as d:
            exp = Path(d) / "exp"
            _write(exp / "manifest.json", {"experiment": "cyc-exp"})
            _write(exp / "cells" / "T1__A_stablenet_knowledge_mcp" / "run-meta.json",
                   {"task": "T1", "mode": "A_stablenet_knowledge_mcp", "status": "done"})
            _write(exp / "cells" / "T1__A_stablenet_knowledge_mcp" / "state.json",
                   {"current_state": "EVALUATION_PASS", "failure_log": []})
            _write(exp / "cells" / "T1__B_code_only" / "run-meta.json",
                   {"task": "T1", "mode": "B_code_only", "status": "done"})
            _write(exp / "cells" / "T1__B_code_only" / "state.json", {
                "current_state": "EVALUATION_PASS",
                "failure_log": [
                    {"state": "EVALUATION",
                     "actual_outcome": {"summary": "unit test FAIL: assertion"}},
                    {"state": "EVALUATION",
                     "actual_outcome": {"summary": "chainbench basic/consensus regression"}},
                    {"state": "PLANNING",   # non-eval entries must not count
                     "actual_outcome": {"summary": "irrelevant"}},
                ],
            })
            _write(exp / "state.json", {"experiment": "cyc-exp", "cells": [
                {"task": "T1", "mode": "A_stablenet_knowledge_mcp", "workspace": "cells/T1__A_stablenet_knowledge_mcp", "status": "done"},
                {"task": "T1", "mode": "B_code_only", "workspace": "cells/T1__B_code_only", "status": "done"},
            ]})
            by_mode = {r.mode: r for r in collect_experiment(exp)}
            self.assertEqual(by_mode["A_stablenet_knowledge_mcp"].bug_cycles, 0)
            self.assertEqual(by_mode["A_stablenet_knowledge_mcp"].side_effect_failures, 0)
            self.assertEqual(by_mode["B_code_only"].bug_cycles, 2)  # only EVALUATION entries
            self.assertEqual(by_mode["B_code_only"].side_effect_failures, 1)  # chainbench one
            roll = aggregate(collect_experiment(exp))
            self.assertEqual(roll["B_code_only"]["bug_cycles_sum"], 2)
            self.assertEqual(roll["B_code_only"]["side_effect_failures"], 1)
            md = to_markdown(build_report(collect_experiment(exp)))
            self.assertIn("bug_cycles", md)
            self.assertIn("side_fx", md)

    def test_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as d:
            exp = make_experiment(Path(d))
            rc = compare.main(["--experiment-dir", str(exp)])
            self.assertEqual(rc, 0)
            for name in ("comparison.json", "comparison.md", "comparison.csv"):
                self.assertTrue((exp / "report" / name).is_file(), name)
            report = json.loads((exp / "report" / "comparison.json").read_text())
            self.assertEqual(report["experiment"], "unit-exp")
            self.assertEqual(len(report["cells"]), 3)


if __name__ == "__main__":
    unittest.main()
