"""test_extract.py — unit tests for io.envelope and io.extract."""

import os
import sys
import unittest

_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from bench_io.envelope import Citation, ParsedResponse
from bench_io.extract import extract_response


class TestCitation(unittest.TestCase):
    def test_from_dict_full(self):
        c = Citation.from_dict({
            "file": "consensus/wbft/core/commit.go",
            "start_line": 10,
            "end_line": 20,
            "symbol": "handleCommit",
        })
        self.assertEqual(c.file, "consensus/wbft/core/commit.go")
        self.assertEqual(c.start_line, 10)
        self.assertEqual(c.end_line, 20)
        self.assertEqual(c.symbol, "handleCommit")

    def test_from_dict_nulls(self):
        c = Citation.from_dict({"file": "core/genesis.go"})
        self.assertIsNone(c.start_line)
        self.assertIsNone(c.end_line)
        self.assertIsNone(c.symbol)

    def test_to_dict_round_trip(self):
        c = Citation(file="a.go", start_line=1, end_line=5, symbol="Foo")
        d = c.to_dict()
        c2 = Citation.from_dict(d)
        self.assertEqual(c.file, c2.file)
        self.assertEqual(c.start_line, c2.start_line)


class TestExtractStrict(unittest.TestCase):
    def test_strict_json(self):
        text = '{"answer": "floor(2N/3)+1", "citations": [{"file": "consensus/wbft/validator/default.go", "start_line": 226, "end_line": 229, "symbol": "QuorumSize"}]}'
        r = extract_response(text)
        self.assertEqual(r.parse_mode, "strict")
        self.assertEqual(r.answer, "floor(2N/3)+1")
        self.assertEqual(len(r.citations), 1)
        self.assertEqual(r.citations[0].file, "consensus/wbft/validator/default.go")
        self.assertEqual(r.citations[0].start_line, 226)

    def test_strict_no_citations(self):
        text = '{"answer": "It is 42", "citations": []}'
        r = extract_response(text)
        self.assertEqual(r.parse_mode, "strict")
        self.assertEqual(r.citations, [])

    def test_strict_answer_only(self):
        text = '{"answer": "something"}'
        r = extract_response(text)
        self.assertEqual(r.parse_mode, "strict")
        self.assertEqual(r.answer, "something")


class TestExtractLenient(unittest.TestCase):
    def test_lenient_json_in_prose(self):
        text = (
            "Here is the answer: "
            '{"answer": "quorum", "citations": [{"file": "consensus/wbft/validator/default.go", "start_line": 5}]}'
            " End."
        )
        r = extract_response(text)
        self.assertIn(r.parse_mode, ("strict", "lenient"))
        self.assertTrue(len(r.citations) >= 1)

    def test_lenient_prose_with_citations(self):
        text = (
            "The QuorumSize function is defined in "
            "consensus/wbft/validator/default.go:226-229 "
            "and it uses the 2F+1 formula."
        )
        r = extract_response(text)
        self.assertIn(r.parse_mode, ("lenient",))
        self.assertTrue(len(r.citations) >= 1)
        files = [c.file for c in r.citations]
        self.assertIn("consensus/wbft/validator/default.go", files)

    def test_lenient_go_line(self):
        text = "See core/state_transition.go:100 for the gas logic."
        r = extract_response(text)
        self.assertIn(r.parse_mode, ("lenient",))
        self.assertTrue(any(c.file == "core/state_transition.go" for c in r.citations))

    def test_malformed_json_falls_to_lenient(self):
        text = '{"answer": "broken", "citations": [{"file": "consensus/wbft/core/commit.go"}'
        r = extract_response(text)
        # Malformed JSON — may be lenient (prose) or failed
        self.assertIn(r.parse_mode, ("lenient", "failed"))


class TestExtractFailed(unittest.TestCase):
    def test_prose_without_citations(self):
        text = "The answer is simply that the quorum is 2f+1 validators."
        r = extract_response(text)
        self.assertEqual(r.parse_mode, "failed")
        self.assertEqual(r.citations, [])
        self.assertEqual(r.answer, "")

    def test_empty_response(self):
        r = extract_response("")
        self.assertEqual(r.parse_mode, "failed")
        self.assertEqual(r.citations, [])

    def test_whitespace_only(self):
        r = extract_response("   \n  ")
        self.assertEqual(r.parse_mode, "failed")

    def test_never_raises(self):
        """extract_response must not raise on any input."""
        for bad in [None, 123, object()]:
            try:
                # Pass as string (force cast)
                extract_response(str(bad) if bad is not None else "")
            except Exception as exc:
                self.fail(f"extract_response raised on {bad!r}: {exc}")


class TestParsedResponse(unittest.TestCase):
    def test_ok_true_for_strict(self):
        r = ParsedResponse(answer="a", citations=[], parse_mode="strict")
        self.assertTrue(r.ok)

    def test_ok_false_for_failed(self):
        r = ParsedResponse(answer="", citations=[], parse_mode="failed")
        self.assertFalse(r.ok)

    def test_to_dict(self):
        c = Citation(file="foo.go")
        r = ParsedResponse(answer="ans", citations=[c], parse_mode="lenient")
        d = r.to_dict()
        self.assertEqual(d["answer"], "ans")
        self.assertEqual(len(d["citations"]), 1)
        self.assertEqual(d["parse_mode"], "lenient")


if __name__ == "__main__":
    unittest.main()
