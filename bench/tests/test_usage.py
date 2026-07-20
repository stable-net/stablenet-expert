"""Tests for bench.lib.usage and bench.lib.capture. Stdlib unittest.

Run from the coding-agent repo root:
    python3 -m unittest bench.tests.test_usage
"""

import json
import tempfile
import unittest
from pathlib import Path

from bench.lib.usage import (
    CanonicalUsage,
    estimate_cost,
    load_prices,
    DEFAULT_PRICES,
)
from bench.lib.capture import (
    usage_by_model_from_transcript,
    usage_by_model_from_session,
    collect_cell_usage,
)


class TestCanonicalUsage(unittest.TestCase):
    def test_from_claude_usage(self):
        u = CanonicalUsage.from_claude_usage(
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 20,
                "cache_read_input_tokens": 10,
            }
        )
        self.assertEqual((u.input, u.output, u.cache_write, u.cache_read), (100, 50, 20, 10))
        self.assertEqual(u.total(), 180)

    def test_from_chars_ceil_divides(self):
        u = CanonicalUsage.from_chars(401, 0, divisor=4)  # ceil(401/4) = 101
        self.assertEqual(u.input, 101)
        self.assertEqual(u.output, 0)

    def test_add_aggregates(self):
        a = CanonicalUsage(input=10, output=5)
        b = CanonicalUsage(input=3, cache_read=7)
        s = a + b
        self.assertEqual((s.input, s.output, s.cache_read), (13, 5, 7))


class TestCost(unittest.TestCase):
    def test_known_model_actual_vs_estimated(self):
        u = CanonicalUsage(input=1_000_000, output=1_000_000)  # 1M each
        # opus-4-7: 15 in + 75 out per MTok -> $90.00
        real = estimate_cost(u, "claude-opus-4-7", "session_jsonl")
        self.assertAlmostEqual(real.amount_usd, 90.0, places=4)
        self.assertEqual(real.status, "actual")
        est = estimate_cost(u, "claude-opus-4-7", "char_estimate")
        self.assertEqual(est.status, "estimated")

    def test_cache_tiers_counted(self):
        u = CanonicalUsage(cache_write=1_000_000, cache_read=1_000_000)
        c = estimate_cost(u, "claude-sonnet-4-6", "session_jsonl")
        # sonnet: cache_write 3.75 + cache_read 0.30 = $4.05
        self.assertAlmostEqual(c.amount_usd, 4.05, places=4)

    def test_unknown_model(self):
        c = estimate_cost(CanonicalUsage(input=10), "no-such-model", "char_estimate")
        self.assertEqual(c.status, "unknown")
        self.assertEqual(c.amount_usd, 0.0)

    def test_load_prices_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prices.json"
            # _comment / metadata keys must be skipped, not parsed as a model.
            p.write_text(json.dumps({
                "_comment": "metadata, not a model",
                "claude-opus-4-7": {"input": 1, "output": 1},
            }))
            prices = load_prices(p)
            c = estimate_cost(CanonicalUsage(input=1_000_000), "claude-opus-4-7", "session", prices)
            self.assertAlmostEqual(c.amount_usd, 1.0, places=4)
        # default unchanged
        self.assertEqual(DEFAULT_PRICES["claude-opus-4-7"].input, __import__("decimal").Decimal("15"))


class TestCapture(unittest.TestCase):
    def _write_jsonl(self, path: Path, rows):
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def test_transcript_estimate_groups_by_model(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "agent-transcript.jsonl"
            self._write_jsonl(
                t,
                [
                    {"subagent_type": "planner", "prompt_chars": 400, "response_chars": 80},
                    {"subagent_type": "implementer", "prompt_chars": 40, "response_chars": 40},
                ],
            )
            by_model = usage_by_model_from_transcript(t)
            self.assertIn("claude-opus-4-8", by_model)  # planner
            self.assertIn("claude-sonnet-4-6", by_model)  # implementer
            self.assertEqual(by_model["claude-opus-4-8"].input, 100)  # 400/4

    def test_session_real_groups_by_model(self):
        with tempfile.TemporaryDirectory() as d:
            s = Path(d) / "session.jsonl"
            self._write_jsonl(
                s,
                [
                    {"type": "assistant", "message": {"model": "claude-opus-4-7",
                        "usage": {"input_tokens": 200, "output_tokens": 100}}},
                    {"type": "user", "message": {"role": "user"}},  # no usage, skipped
                    {"type": "assistant", "message": {"model": "claude-opus-4-7",
                        "usage": {"input_tokens": 50, "output_tokens": 10}}},
                ],
            )
            by_model = usage_by_model_from_session(s)
            self.assertEqual(by_model["claude-opus-4-7"].input, 250)
            self.assertEqual(by_model["claude-opus-4-7"].output, 110)

    def test_collect_prefers_session(self):
        with tempfile.TemporaryDirectory() as d:
            cell = Path(d)
            (cell / "logs").mkdir()
            self._write_jsonl(
                cell / "logs" / "agent-transcript.jsonl",
                [{"subagent_type": "planner", "prompt_chars": 4, "response_chars": 4}],
            )
            s = cell / "session.jsonl"
            self._write_jsonl(
                s, [{"message": {"model": "claude-opus-4-7", "usage": {"input_tokens": 999}}}]
            )
            by_model, source = collect_cell_usage(cell, session_path=s)
            self.assertEqual(source, "session_jsonl")
            self.assertEqual(by_model["claude-opus-4-7"].input, 999)
            # no session -> falls back to estimate
            by_model2, source2 = collect_cell_usage(cell, session_path=None)
            self.assertEqual(source2, "char_estimate")


if __name__ == "__main__":
    unittest.main()
