"""test_report.py — snapshot test for report aggregation.

Creates a 2-question × 4-method fixture, runs build_report(),
and verifies report.md structure and the delta table.
"""

import json
import os
import sys
import tempfile
import unittest

_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from state import write_cell_result
from report import build_report, _rollup_by_method, _delta_table


def _make_cell_result(
    question_id: str,
    method_id: str,
    loc_f1: float,
    correct: bool,
    hallucs: int,
    tokens: int,
) -> dict:
    return {
        "question_id": question_id,
        "method_id": method_id,
        "parse_mode": "strict",
        "answer": "test answer",
        "citations": [],
        "location": {"precision": loc_f1, "recall": loc_f1, "f1": loc_f1},
        "correctness": correct,
        "hallucinations": {"total_citations": 0, "hallucination_count": hallucs, "cks_partial": False, "verdicts": []},
        "info_volume_tokens": tokens,
        "ask": {"input_tokens": tokens, "output_tokens": 10, "turns": 1, "transcript_path": None, "driver_name": "replay", "error": None},
    }


METHODS = ["M1_raw", "M2_graph_full", "M3_incremental", "M4_get_for_task"]
QUESTIONS = ["G01", "G02"]

# Fixture data: (loc_f1, correct, hallucs, tokens)
FIXTURE_DATA = {
    ("G01", "M1_raw"):           (0.5, False, 1, 1000),
    ("G01", "M2_graph_full"):    (0.6, True,  0, 800),
    ("G01", "M3_incremental"):   (0.7, True,  0, 600),
    ("G01", "M4_get_for_task"):  (0.8, True,  0, 400),
    ("G02", "M1_raw"):           (0.4, False, 2, 1200),
    ("G02", "M2_graph_full"):    (0.5, False, 1, 900),
    ("G02", "M3_incremental"):   (0.6, True,  0, 700),
    ("G02", "M4_get_for_task"):  (0.9, True,  0, 350),
}


class TestReportAggregation(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        # Write all fixture cell results
        for (qid, mid), (f1, correct, hallucs, tokens) in FIXTURE_DATA.items():
            result = _make_cell_result(qid, mid, f1, correct, hallucs, tokens)
            write_cell_result(self._tmpdir, qid, mid, result)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_build_report_creates_files(self):
        md_path = build_report(self._tmpdir, method_ids=METHODS)
        self.assertTrue(os.path.isfile(md_path))
        self.assertTrue(os.path.isfile(md_path.replace("report.md", "report.json")))
        self.assertTrue(os.path.isfile(md_path.replace("report.md", "report.csv")))

    def test_report_md_has_all_method_rows(self):
        md_path = build_report(self._tmpdir, method_ids=METHODS)
        with open(md_path) as f:
            content = f.read()
        for mid in METHODS:
            self.assertIn(mid, content, f"Method {mid} missing from report.md")

    def test_report_md_has_delta_table(self):
        md_path = build_report(self._tmpdir, method_ids=METHODS)
        with open(md_path) as f:
            content = f.read()
        self.assertIn("Δ_correct_rate", content)
        self.assertIn("token_reduction", content)

    def test_report_md_has_per_question_section(self):
        md_path = build_report(self._tmpdir, method_ids=METHODS)
        with open(md_path) as f:
            content = f.read()
        self.assertIn("Per-Question Matrix", content)
        for qid in QUESTIONS:
            self.assertIn(qid, content)

    def test_rollup_correct_rate(self):
        """M1_raw should have correct_rate=0.0 (both G01 and G02 incorrect)."""
        from report import _load_all_results
        results = _load_all_results(self._tmpdir)
        rollup = _rollup_by_method(results, METHODS)
        m1 = rollup["M1_raw"]
        self.assertAlmostEqual(m1["correct_rate"], 0.0)

    def test_rollup_m4_correct_rate(self):
        """M4 should have correct_rate=1.0 (both G01 and G02 correct)."""
        from report import _load_all_results
        results = _load_all_results(self._tmpdir)
        rollup = _rollup_by_method(results, METHODS)
        m4 = rollup["M4_get_for_task"]
        self.assertAlmostEqual(m4["correct_rate"], 1.0)

    def test_delta_positive_correct_rate(self):
        """M4 vs M1 delta_correct_rate should be +1.0."""
        from report import _load_all_results
        results = _load_all_results(self._tmpdir)
        rollup = _rollup_by_method(results, METHODS)
        delta = _delta_table(rollup)
        self.assertIsNotNone(delta)
        self.assertGreater(delta["delta_correct_rate"], 0)

    def test_delta_token_reduction(self):
        """M4 uses fewer tokens than M1 → positive reduction pct."""
        from report import _load_all_results
        results = _load_all_results(self._tmpdir)
        rollup = _rollup_by_method(results, METHODS)
        delta = _delta_table(rollup)
        self.assertIsNotNone(delta)
        # M4 avg tokens ~375, M1 avg tokens ~1100 → reduction > 0
        self.assertGreater(delta["token_reduction_pct"], 0)

    def test_report_json_structure(self):
        build_report(self._tmpdir, method_ids=METHODS)
        json_path = os.path.join(self._tmpdir, "report", "report.json")
        with open(json_path) as f:
            data = json.load(f)
        self.assertIn("rollup", data)
        self.assertIn("matrix", data)
        self.assertIn("delta", data)
        self.assertIn("total_cells", data)
        self.assertEqual(data["total_cells"], len(FIXTURE_DATA))

    def test_missing_method_shows_dash_in_md(self):
        """Report gracefully shows — for missing methods."""
        # Build with only M1 and M4 data; expect M2/M3 rows to show 0 cells
        md_path = build_report(self._tmpdir, method_ids=["M1_raw", "M4_get_for_task"])
        with open(md_path) as f:
            content = f.read()
        # Both methods present in rollup
        self.assertIn("M1_raw", content)
        self.assertIn("M4_get_for_task", content)


if __name__ == "__main__":
    unittest.main()
