"""test_e2e_replay.py — end-to-end replay integration test.

Runs a 2-question × 4-method benchmark with the replay driver (non-strict
placeholders) and asserts that:
  1. run.py produces report/report.md
  2. report.md contains all 4 method rows
  3. The M4-vs-M1 delta table is present
  4. All 8 cells are marked done in state.json
"""

import json
import os
import sys
import tempfile
import unittest

_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from runner import run as runner_run
from report import build_report
from state import load_state, is_complete


METHODS = ["M1_raw", "M2_graph_full", "M3_incremental", "M4_get_for_task"]


def _make_e2e_manifest(replay_dir: str, exp_dir: str) -> dict:
    return {
        "experiment": "e2e_test",
        "golden_set": {
            "source": "golden-set/index.yaml",
            "ids": ["G01", "G02"],
            "buckets": [],
        },
        "methods": METHODS,
        "driver": "replay",
        "go_stablenet_root": "/nonexistent",
        "sha_pin": "9978930ba",
        "batch_size": 8,
        "output_dir": exp_dir,
        "driver_config": {
            "replay_dir": replay_dir,
            "strict": False,
        },
        "cks_config": {"health_check": False},
    }


class TestE2EReplayRun(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._replay_dir = os.path.join(self._tmpdir, "replay")
        os.makedirs(self._replay_dir, exist_ok=True)
        self._exp_dir = os.path.join(self._tmpdir, "exp")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_full_run_2q_4m_produces_report(self):
        """2 questions × 4 methods → 8 cells done + report.md with all 4 rows."""
        manifest = _make_e2e_manifest(self._replay_dir, self._exp_dir)

        # Run
        final_state = runner_run(
            manifest=manifest,
            exp_dir=self._exp_dir,
            continue_run=False,
            batch_size=8,
        )

        # All 8 cells done
        self.assertTrue(is_complete(final_state))
        done = sum(1 for c in final_state["cells"].values() if c["status"] == "done")
        self.assertEqual(done, 8)

        # Build report
        md_path = build_report(self._exp_dir, method_ids=METHODS)
        self.assertTrue(os.path.isfile(md_path))

        with open(md_path) as f:
            content = f.read()

        # All 4 method rows present
        for mid in METHODS:
            self.assertIn(mid, content, f"Method {mid} not in report.md")

        # Delta table present
        self.assertIn("Δ_correct_rate", content)
        self.assertIn("token_reduction", content)

        # Per-question matrix present
        self.assertIn("G01", content)
        self.assertIn("G02", content)

    def test_resume_from_partial_run(self):
        """First batch_size=1, then resume. Final state should have 8 done."""
        manifest = _make_e2e_manifest(self._replay_dir, self._exp_dir)
        manifest["batch_size"] = 1

        # First run: 1 cell
        state1 = runner_run(manifest, self._exp_dir, continue_run=False, batch_size=1)
        done1 = sum(1 for c in state1["cells"].values() if c["status"] == "done")
        self.assertEqual(done1, 1)
        self.assertFalse(is_complete(state1))

        # Resume: remaining 7 cells
        state2 = runner_run(manifest, self._exp_dir, continue_run=True, batch_size=10)
        self.assertTrue(is_complete(state2))
        done2 = sum(1 for c in state2["cells"].values() if c["status"] == "done")
        self.assertEqual(done2, 8)

    def test_report_json_structure(self):
        """report.json has rollup, matrix, delta, total_cells=8."""
        manifest = _make_e2e_manifest(self._replay_dir, self._exp_dir)
        runner_run(manifest, self._exp_dir, continue_run=False, batch_size=8)
        build_report(self._exp_dir, method_ids=METHODS)

        json_path = os.path.join(self._exp_dir, "report", "report.json")
        self.assertTrue(os.path.isfile(json_path))
        with open(json_path) as f:
            data = json.load(f)
        self.assertEqual(data["total_cells"], 8)
        self.assertIn("rollup", data)
        self.assertIn("matrix", data)
        self.assertIn("delta", data)
        for mid in METHODS:
            self.assertIn(mid, data["rollup"])


if __name__ == "__main__":
    unittest.main()
