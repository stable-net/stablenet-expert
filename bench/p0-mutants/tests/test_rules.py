#!/usr/bin/env python3
"""Tests for the P0 mutant-corpus harness.

Run:  python3 bench/p0-mutants/tests/test_rules.py
(or)  python3 -m unittest discover -s bench/p0-mutants/tests
"""
import json
import sys
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import contracts          # noqa: E402
import render             # noqa: E402
from mutate import MUTATIONS, normalize   # noqa: E402
from rules import after_p0, before_p0, detected_by   # noqa: E402
from score import run     # noqa: E402

CORPUS = _PKG / "corpus"


def _load(case_id):
    return normalize(json.loads((CORPUS / f"{case_id}.json").read_text()))


def _op(label):
    return next(op for lbl, _c, op, _b, _a in MUTATIONS if lbl == label)


class TestEngines(unittest.TestCase):
    def setUp(self):
        self.case = _load("feepayer-truncate")

    def test_clean_is_silent_both(self):
        self.assertEqual(before_p0(self.case), [])
        self.assertEqual(after_p0(self.case), [])

    def test_impl_drop_site_only_after(self):
        m = _op("impl_drop_site")(self.case)
        self.assertFalse(detected_by(before_p0(m), ["implementer§4.2b"]))
        self.assertTrue(detected_by(after_p0(m), ["implementer§4.2b"]))

    def test_uncover_site_only_after(self):
        for label in ("uncover_blank", "uncover_badname"):
            m = _op(label)(self.case)
            self.assertEqual(before_p0(m), [], label)          # before stays silent
            self.assertTrue(detected_by(after_p0(m), ["evaluator§4.6c"]), label)

    def test_missing_tests_caught_by_both(self):
        for label, mech in (("drop_invariant_test", "evaluator§4.6a"),
                            ("drop_adversarial_test", "evaluator§4.6b")):
            m = _op(label)(self.case)
            self.assertTrue(detected_by(before_p0(m), [mech]), label)
            self.assertTrue(detected_by(after_p0(m), [mech]), label)

    def test_plan_malformed_heading_only_after(self):
        m = _op("plan_malformed_heading")(self.case)
        self.assertEqual(before_p0(m), [])
        self.assertTrue(detected_by(after_p0(m), ["implementer§2.1"]))

    def test_contract_underdeclare_is_residual(self):
        """Honest boundary: neither ruleset catches planner under-declaration."""
        m = _op("contract_underdeclare")(self.case)
        self.assertEqual(before_p0(m), [])
        self.assertEqual(after_p0(m), [])


class TestAggregate(unittest.TestCase):
    def test_after_strictly_beats_before_no_false_positives(self):
        cases = [_load(p.stem) for p in sorted(CORPUS.glob("*.json"))]
        s = run(cases)["summary"]
        self.assertGreater(s["after_rate"], s["before_rate"])
        self.assertEqual(s["before_false_positives"], 0)
        self.assertEqual(s["after_false_positives"], 0)
        self.assertEqual(s["after_detected"], s["hard_total"])   # 100% on hard


class TestContractsRoundTrip(unittest.TestCase):
    """render.py output must parse back via the real contracts.py parser."""
    def test_write_site_contract_round_trip(self):
        case = _load("feepayer-truncate")
        design_md = render.render_design(case)
        parsed = contracts.find_write_site_contract(design_md)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["derived_state"],
                         case["design"]["write_site_contract"]["derived_state"])
        self.assertEqual(len(parsed["sites"]),
                         len(case["design"]["write_site_contract"]["sites"]))

    def test_plan_contract_round_trip(self):
        case = _load("feepayer-truncate")
        plan_md = render.render_plan(case)
        parsed = contracts.find_plan_contract(plan_md)
        self.assertIsNotNone(parsed)
        self.assertEqual(len(parsed["steps"]), len(case["plan"]["contract_steps"]))
        # prose-heading count matches the contract on a clean case
        self.assertEqual(contracts.count_prose_step_headings(plan_md),
                         len(parsed["steps"]))

    def test_malformed_heading_breaks_prose_count_not_contract(self):
        case = _op("plan_malformed_heading")(_load("feepayer-truncate"))
        plan_md = render.render_plan(case)
        parsed = contracts.find_plan_contract(plan_md)
        # the contract still has all steps, but the heading parser loses one →
        # exactly the mismatch implementer §2.1 escalates on.
        self.assertGreater(len(parsed["steps"]),
                           contracts.count_prose_step_headings(plan_md))


if __name__ == "__main__":
    unittest.main(verbosity=2)
