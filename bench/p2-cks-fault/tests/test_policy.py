#!/usr/bin/env python3
"""Tests for the P2 cks-fault harness.

Run:  python3 bench/p2-cks-fault/tests/test_policy.py
"""
import sys
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from policy import (after_p2, before_p2, is_silent_incomplete,   # noqa: E402
                    missing_core_after, missing_core_before, normalize)
from score import run   # noqa: E402


def _decide(scn):
    h, c = normalize(scn)
    return before_p2(h, c), after_p2(h, c), c


class TestPolicy(unittest.TestCase):
    def test_healthy_clean_both(self):
        b, a, _ = _decide({"health": "serviceable"})
        self.assertEqual(b["decision"], "CLEAN")
        self.assertEqual(a["decision"], "CLEAN")

    def test_backend_down_blocked_both(self):
        for h in ("down", "degraded"):
            b, a, _ = _decide({"health": h})
            self.assertEqual(b["decision"], "BLOCKED", h)
            self.assertEqual(a["decision"], "BLOCKED", h)

    def test_primary_persistent_before_silent_after_blocked(self):
        b, a, c = _decide({"calls": {"get_for_task": "persistent"}})
        self.assertTrue(is_silent_incomplete(b, missing_core_before(c)))   # before silently proceeds
        self.assertEqual(a["decision"], "BLOCKED")
        self.assertFalse(is_silent_incomplete(a, missing_core_after(c)))

    def test_completeness_persistent_after_degraded(self):
        b, a, c = _decide({"calls": {"impact_analysis": "persistent"}})
        self.assertTrue(is_silent_incomplete(b, missing_core_before(c)))
        self.assertEqual(a["decision"], "DEGRADED")
        self.assertIn("impact_analysis", a["missing"])

    def test_transient_recovered_by_retry(self):
        # a flapping core call is silent before, but retry rescues it after → CLEAN, not over-blocked.
        b, a, c = _decide({"calls": {"get_for_task": "transient", "find_callers": "transient"}})
        self.assertTrue(is_silent_incomplete(b, missing_core_before(c)))
        self.assertEqual(a["decision"], "CLEAN")

    def test_enhancement_loss_is_not_silent(self):
        # losing only enhancement primitives is a legitimate CLEAN — not a silent incomplete.
        b, a, c = _decide({"calls": {"freshness": "persistent", "semantic_search": "persistent"}})
        self.assertFalse(is_silent_incomplete(b, missing_core_before(c)))
        self.assertEqual(a["decision"], "CLEAN")


class TestAggregate(unittest.TestCase):
    def test_after_closes_silent_gap_without_over_blocking(self):
        s = run()["summary"]
        self.assertGreater(s["before_silent_incomplete"], 0)   # the gap existed
        self.assertEqual(s["after_silent_incomplete"], 0)      # and is closed
        self.assertEqual(s["after_over_block"], 0)             # without over-blocking
        self.assertEqual(s["after_decision_mismatches"], 0)    # every decision as designed
        self.assertGreater(s["retry_recovered"], 0)            # retry demonstrably helps


if __name__ == "__main__":
    unittest.main(verbosity=2)
