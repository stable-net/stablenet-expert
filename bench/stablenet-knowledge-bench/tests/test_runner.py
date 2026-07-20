"""test_runner.py — unit tests for runner.py and state.py.

Tests kill-and-resume: start a 4-cell run, interrupt after cell 2,
resume, verify idempotent skip.
"""

import json
import os
import sys
import tempfile
import unittest

_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

import state as state_mod
from state import (
    CELL_DONE, CELL_FAILED, CELL_PENDING,
    init_state, is_complete, load_state, mark_cell_done, mark_cell_failed,
    mark_cell_running, pending_cells, save_state, write_cell_result,
)
from drivers.replay import ReplayDriver
from runner import run as runner_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_minimal_manifest(
    exp_dir: str,
    replay_dir: str,
    question_ids=None,
    methods=None,
) -> dict:
    """Build a minimal manifest for testing with 2 questions × 2 methods."""
    if question_ids is None:
        question_ids = ["G01", "G02"]
    if methods is None:
        methods = ["M1_raw", "M1_raw"]  # same method twice to simplify
    # We use just M1_raw since it only needs disk files
    return {
        "experiment": "test_exp",
        "golden_set": {
            "source": "golden-set/index.yaml",
            "ids": question_ids,
            "buckets": [],
        },
        "methods": ["M1_raw"],
        "driver": "replay",
        "go_stablenet_root": "/nonexistent",  # M1 will log NOT FOUND but not crash
        "sha_pin": "9978930ba",
        "batch_size": 8,
        "driver_config": {
            "replay_dir": replay_dir,
            "strict": False,  # non-strict so REPLAY_MISS returns placeholder
        },
    }


# ---------------------------------------------------------------------------
# State tests
# ---------------------------------------------------------------------------

class TestStateModule(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_init_creates_state_json(self):
        state = init_state(
            self._tmpdir, "exp1", "abc123", ["G01", "G02"], ["M1_raw", "M2_graph_full"]
        )
        self.assertEqual(state["total_cells"], 4)
        self.assertEqual(state["completed_cells"], 0)
        self.assertTrue(os.path.isfile(os.path.join(self._tmpdir, "state.json")))

    def test_init_idempotent(self):
        """Calling init_state twice returns the existing state."""
        state1 = init_state(self._tmpdir, "exp1", "abc", ["G01"], ["M1_raw"])
        state2 = init_state(self._tmpdir, "exp1", "abc", ["G01"], ["M1_raw"])
        self.assertEqual(state1["total_cells"], state2["total_cells"])

    def test_mark_cell_done_increments_completed(self):
        state = init_state(self._tmpdir, "exp1", "abc", ["G01"], ["M1_raw"])
        result_path = write_cell_result(self._tmpdir, "G01", "M1_raw", {"score": 1})
        mark_cell_done(state, "G01", "M1_raw", result_path)
        self.assertEqual(state["completed_cells"], 1)
        self.assertEqual(state["cells"]["G01__M1_raw"]["status"], CELL_DONE)

    def test_mark_cell_failed(self):
        state = init_state(self._tmpdir, "exp1", "abc", ["G01"], ["M1_raw"])
        mark_cell_failed(state, "G01", "M1_raw", "some error")
        self.assertEqual(state["cells"]["G01__M1_raw"]["status"], CELL_FAILED)
        self.assertEqual(state["failed_cells"], 1)

    def test_pending_cells_excludes_done(self):
        state = init_state(self._tmpdir, "exp1", "abc", ["G01", "G02"], ["M1_raw"])
        result_path = write_cell_result(self._tmpdir, "G01", "M1_raw", {})
        mark_cell_done(state, "G01", "M1_raw", result_path)
        pending = pending_cells(state)
        self.assertEqual(len(pending), 1)
        self.assertIn(("G02", "M1_raw"), pending)

    def test_is_complete_false_while_pending(self):
        state = init_state(self._tmpdir, "exp1", "abc", ["G01"], ["M1_raw"])
        self.assertFalse(is_complete(state))

    def test_is_complete_true_when_all_done(self):
        state = init_state(self._tmpdir, "exp1", "abc", ["G01"], ["M1_raw"])
        rp = write_cell_result(self._tmpdir, "G01", "M1_raw", {})
        mark_cell_done(state, "G01", "M1_raw", rp)
        self.assertTrue(is_complete(state))

    def test_atomic_write_and_load(self):
        state = init_state(self._tmpdir, "exp1", "abc", ["G01"], ["M1_raw"])
        state["custom_field"] = "hello"
        save_state(self._tmpdir, state)
        loaded = load_state(self._tmpdir)
        self.assertEqual(loaded["custom_field"], "hello")

    def test_write_cell_result(self):
        result_path = write_cell_result(self._tmpdir, "G01", "M1_raw", {"score": 42})
        self.assertTrue(os.path.isfile(result_path))
        with open(result_path) as f:
            data = json.load(f)
        self.assertEqual(data["score"], 42)


# ---------------------------------------------------------------------------
# Runner integration tests
# ---------------------------------------------------------------------------

class TestRunnerResumeReplay(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._replay_dir = os.path.join(self._tmpdir, "replay")
        os.makedirs(self._replay_dir, exist_ok=True)
        self._exp_dir = os.path.join(self._tmpdir, "exp")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run_with_batch(self, batch_size, continue_run=False):
        manifest = _build_minimal_manifest(
            self._exp_dir,
            replay_dir=self._replay_dir,
            question_ids=["G01", "G02"],
        )
        manifest["batch_size"] = batch_size
        return runner_run(
            manifest,
            self._exp_dir,
            continue_run=continue_run,
            batch_size=batch_size,
        )

    def test_run_2_questions_completes(self):
        """2 questions × 1 method (M1_raw) with non-strict replay = all done."""
        state = self._run_with_batch(batch_size=8)
        done = sum(1 for c in state["cells"].values() if c["status"] == CELL_DONE)
        self.assertEqual(done, 2)
        self.assertTrue(is_complete(state))

    def test_resume_skips_completed_cells(self):
        """Batch of 1 then resume: second run should complete the remaining cell."""
        # First run: batch_size=1 → processes only 1 cell
        state1 = self._run_with_batch(batch_size=1)
        done_before = sum(1 for c in state1["cells"].values() if c["status"] == CELL_DONE)
        self.assertEqual(done_before, 1)
        self.assertFalse(is_complete(state1))

        # Resume: batch_size=8 → processes remaining 1 cell
        state2 = self._run_with_batch(batch_size=8, continue_run=True)
        done_after = sum(1 for c in state2["cells"].values() if c["status"] == CELL_DONE)
        self.assertEqual(done_after, 2)
        self.assertTrue(is_complete(state2))

    def test_idempotent_skip_already_done(self):
        """Running again on a complete experiment changes nothing."""
        self._run_with_batch(batch_size=8)
        state_before = load_state(self._exp_dir)

        # Run again
        self._run_with_batch(batch_size=8, continue_run=True)
        state_after = load_state(self._exp_dir)

        self.assertEqual(
            state_before["completed_cells"],
            state_after["completed_cells"],
        )

    def test_cell_result_written(self):
        """result.json is written for each completed cell."""
        self._run_with_batch(batch_size=8)
        cell_dir = os.path.join(self._exp_dir, "cells", "G01__M1_raw")
        result_path = os.path.join(cell_dir, "result.json")
        self.assertTrue(os.path.isfile(result_path))
        with open(result_path) as f:
            data = json.load(f)
        self.assertIn("location", data)
        self.assertIn("correctness", data)
        self.assertIn("hallucinations", data)
        self.assertIn("info_volume_tokens", data)


if __name__ == "__main__":
    unittest.main()
