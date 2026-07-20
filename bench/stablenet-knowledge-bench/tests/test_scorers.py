"""test_scorers.py — unit tests for all four scorers."""

import os
import sys
import tempfile
import unittest

_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from bench_io.envelope import Citation
from scorers.location import score_location, LocationScore
from scorers.correctness import score_correctness
from scorers.hallucination import score_hallucination
from scorers.info_volume import score_info_volume


class TestLocationScorer(unittest.TestCase):
    def _cite(self, file, start=None, end=None, symbol=None):
        return Citation(file=file, start_line=start, end_line=end, symbol=symbol)

    def test_perfect_match(self):
        pred = [self._cite("consensus/wbft/validator/default.go", 226, 229)]
        exp = [self._cite("consensus/wbft/validator/default.go", 226, 229)]
        s = score_location(pred, exp)
        self.assertAlmostEqual(s.precision, 1.0)
        self.assertAlmostEqual(s.recall, 1.0)
        self.assertAlmostEqual(s.f1, 1.0)

    def test_partial_overlap(self):
        pred = [self._cite("consensus/wbft/validator/default.go", 220, 230)]
        exp = [self._cite("consensus/wbft/validator/default.go", 226, 229)]
        s = score_location(pred, exp)
        self.assertAlmostEqual(s.recall, 1.0)  # overlap exists

    def test_no_match_different_file(self):
        pred = [self._cite("core/genesis.go", 1, 10)]
        exp = [self._cite("consensus/wbft/validator/default.go", 226, 229)]
        s = score_location(pred, exp)
        self.assertAlmostEqual(s.precision, 0.0)
        self.assertAlmostEqual(s.recall, 0.0)
        self.assertAlmostEqual(s.f1, 0.0)

    def test_null_lines_match(self):
        """Null lines on either side → file match is sufficient."""
        pred = [self._cite("consensus/wbft/validator/default.go")]
        exp = [self._cite("consensus/wbft/validator/default.go", 226, 229)]
        s = score_location(pred, exp)
        self.assertAlmostEqual(s.recall, 1.0)

    def test_no_expected_citations(self):
        """No expected citations → perfect score when predicted is also empty."""
        s = score_location([], [])
        self.assertAlmostEqual(s.recall, 1.0)

    def test_no_predicted_citations(self):
        exp = [self._cite("foo.go")]
        s = score_location([], exp)
        self.assertAlmostEqual(s.precision, 0.0)
        self.assertAlmostEqual(s.recall, 0.0)
        self.assertAlmostEqual(s.f1, 0.0)

    def test_leading_dot_slash_normalized(self):
        pred = [self._cite("./consensus/wbft/validator/default.go")]
        exp = [self._cite("consensus/wbft/validator/default.go")]
        s = score_location(pred, exp)
        self.assertAlmostEqual(s.recall, 1.0)


class TestCorrectnessScorer(unittest.TestCase):
    def _loc(self, recall):
        p = recall  # just set p==r for simplicity
        return LocationScore(precision=p, recall=recall, f1=p)

    def test_correct(self):
        ok = score_correctness(
            "The QuorumSize uses 2F+1 formula",
            self._loc(1.0),
            ["QuorumSize", "2F+1"],
        )
        self.assertTrue(ok)

    def test_fails_on_low_recall(self):
        ok = score_correctness(
            "QuorumSize uses 2F+1",
            self._loc(0.3),  # below 0.5 threshold
            ["QuorumSize"],
        )
        self.assertFalse(ok)

    def test_fails_on_missing_first_keyword(self):
        ok = score_correctness(
            "The formula uses 2F+1",
            self._loc(1.0),
            ["QuorumSize"],  # not in answer
        )
        self.assertFalse(ok)

    def test_fails_on_parse_failed(self):
        ok = score_correctness(
            "QuorumSize is 2F+1",
            self._loc(1.0),
            ["QuorumSize"],
            parse_failed=True,
        )
        self.assertFalse(ok)

    def test_no_keywords_passes_with_good_recall(self):
        ok = score_correctness(
            "Some answer",
            self._loc(1.0),
            [],
        )
        self.assertTrue(ok)

    def test_case_insensitive(self):
        ok = score_correctness(
            "quorumsize uses the formula",
            self._loc(1.0),
            ["QuorumSize"],
        )
        self.assertTrue(ok)

    def test_empty_answer_fails(self):
        ok = score_correctness("", self._loc(1.0), ["QuorumSize"])
        self.assertFalse(ok)


class TestHallucinationScorer(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        # Create a synthetic Go file
        self._go_file = os.path.join(self._tmpdir, "validator.go")
        with open(self._go_file, "w") as f:
            f.write("package validator\n\nfunc QuorumSize(n int) int {\n\treturn 2*n/3 + 1\n}\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_existing_file_no_hallucination(self):
        cite = Citation(file="validator.go", start_line=3, end_line=5)
        hs = score_hallucination([cite], self._tmpdir)
        self.assertEqual(hs.hallucination_count, 0)

    def test_nonexistent_file_is_hallucination(self):
        cite = Citation(file="nonexistent_function.go")
        hs = score_hallucination([cite], self._tmpdir)
        self.assertEqual(hs.hallucination_count, 1)

    def test_out_of_range_lines_not_hallucination(self):
        # Per the ticket definition, hallucination = a made-up nonexistent
        # file/function NAME. A wrong/over-range line for a real file is a
        # LOCATION precision error (captured by loc_f1), NOT a fabrication.
        cite = Citation(file="validator.go", start_line=100, end_line=200)
        hs = score_hallucination([cite], self._tmpdir)
        self.assertEqual(hs.hallucination_count, 0)

    def test_prose_symbol_not_checkable(self):
        # A prose description in the symbol field (not an identifier) must not
        # be treated as a fabricated function name.
        cite = Citation(file="validator.go", symbol="system contract address constants")
        hs = score_hallucination([cite], self._tmpdir, cks_tool=None)
        self.assertEqual(hs.hallucination_count, 0)

    def test_real_symbol_in_other_file_not_hallucination(self):
        # cks confirms the symbol EXISTS (in another file). A wrong-file
        # attribution of a real symbol is a location error, not a fabrication.
        def fake_cks(tool, args):
            return {"symbol": args["name"],
                    "citations": [{"file": "consensus/wbft/core/core.go", "start_line": 1, "end_line": 9}]}
        cite = Citation(file="validator.go", symbol="core.newRoundChangeTimer")
        hs = score_hallucination([cite], self._tmpdir, cks_tool=fake_cks)
        self.assertEqual(hs.hallucination_count, 0)

    def test_nonexistent_symbol_is_hallucination(self):
        # cks returns empty AND grep finds nothing → genuine fabrication.
        def fake_cks(tool, args):
            return {"symbol": args["name"], "citations": []}
        cite = Citation(file="validator.go", symbol="totallyMadeUpFunc")
        hs = score_hallucination([cite], self._tmpdir, cks_tool=fake_cks)
        self.assertEqual(hs.hallucination_count, 1)

    def test_fabricated_symbol_is_hallucination(self):
        """A citation with a symbol that doesn't appear in the file should hallucinate."""
        cite = Citation(file="validator.go", symbol="nonexistent_function")
        hs = score_hallucination([cite], self._tmpdir, cks_tool=None)
        # grep falls back: nonexistent_function is not in the file
        self.assertEqual(hs.hallucination_count, 1)

    def test_known_symbol_not_hallucination(self):
        cite = Citation(file="validator.go", symbol="QuorumSize")
        hs = score_hallucination([cite], self._tmpdir, cks_tool=None)
        self.assertEqual(hs.hallucination_count, 0)

    def test_empty_citations(self):
        hs = score_hallucination([], self._tmpdir)
        self.assertEqual(hs.total_citations, 0)
        self.assertEqual(hs.hallucination_count, 0)

    def test_to_dict(self):
        cite = Citation(file="validator.go")
        hs = score_hallucination([cite], self._tmpdir)
        d = hs.to_dict()
        self.assertIn("hallucination_count", d)
        self.assertIn("verdicts", d)


class TestInfoVolumeScorer(unittest.TestCase):
    def test_positive_tokens(self):
        self.assertEqual(score_info_volume(1234), 1234)

    def test_zero(self):
        self.assertEqual(score_info_volume(0), 0)

    def test_negative_clamped(self):
        self.assertEqual(score_info_volume(-5), 0)

    def test_float_truncated(self):
        self.assertEqual(score_info_volume(99), 99)


if __name__ == "__main__":
    unittest.main()
