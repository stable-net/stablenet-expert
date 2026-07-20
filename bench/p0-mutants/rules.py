#!/usr/bin/env python3
"""rules.py — the before-P0 and after-P0 contract-check rule engines.

A "case" is the normalized dict (see corpus/*.json):
  design.write_site_contract  : {derived_state, mirrors, sites[], invariant_test, adversarial_test}
  design.diff_has_add_sub_helpers : bool  (models §4.6 step-1 add/sub fallback detection)
  plan.contract_steps         : list | None   (None models a missing plan-contract block)
  plan.prose_step_count       : int  (how many `## Step N:` headings the heading parser sees)
  impl.maintained_sites       : [site]   (sites the implementation actually updates)
  impl.existing_tests         : [test]   (tests present in the tree/diff)

Each engine returns a list of findings:
  {mechanism, severity, detail}  severity ∈ {FAIL, FLAG, WARN}

`before_p0` = the spec BEFORE the stream-6 P0 patch:
  - evaluator §4.6 a/b only (require an invariant test + an adversarial test to EXIST)
  - implementer parsed plan.md headings silently; no §4.2b, no §4.6c, no plan-contract.

`after_p0` = the patched spec:
  + evaluator §4.6c   per-site coverage completeness
  + implementer §4.2b every declared site (action!=none) is actually maintained
  + implementer §2.1  plan-contract is authoritative; prose/contract step mismatch escalates.

The engines are pure functions of the case — no LLM, no I/O.
"""
from __future__ import annotations

from typing import Any

Finding = dict[str, Any]
ACTIONS_THAT_NEED_WORK = {"add", "sub", "rebuild"}


def _derived_state_present(case: dict) -> tuple[bool, dict | None]:
    design = case.get("design", {})
    wsc = design.get("write_site_contract")
    present = wsc is not None or bool(design.get("diff_has_add_sub_helpers"))
    return present, wsc


def _active_sites(wsc: dict | None) -> list[dict]:
    if not wsc:
        return []
    return [s for s in wsc.get("sites", []) if (s.get("action") or "none") in ACTIONS_THAT_NEED_WORK]


def _eval_46_ab(wsc: dict | None, existing: set[str]) -> list[Finding]:
    """Evaluator §4.6 a/b — present in BOTH profiles."""
    out: list[Finding] = []
    inv = (wsc or {}).get("invariant_test")
    adv = (wsc or {}).get("adversarial_test")
    if not inv or inv not in existing:
        out.append({"mechanism": "evaluator§4.6a", "severity": "FAIL",
                    "detail": f"consistency-invariant test missing/absent (declared={inv!r})"})
    if not adv or adv not in existing:
        out.append({"mechanism": "evaluator§4.6b", "severity": "FAIL",
                    "detail": f"adversarial-path test missing/absent (declared={adv!r})"})
    return out


def before_p0(case: dict) -> list[Finding]:
    findings: list[Finding] = []
    present, wsc = _derived_state_present(case)
    existing = set(case.get("impl", {}).get("existing_tests", []))
    if present:
        findings.extend(_eval_46_ab(wsc, existing))
    # Pre-P0 plan handling: silent heading parse. No contract to compare against,
    # so a dropped/malformed step produces NO finding (the failure mode P0 fixes).
    return findings


def after_p0(case: dict) -> list[Finding]:
    findings: list[Finding] = []
    present, wsc = _derived_state_present(case)
    impl = case.get("impl", {})
    existing = set(impl.get("existing_tests", []))
    maintained = set(impl.get("maintained_sites", []))

    if present:
        findings.extend(_eval_46_ab(wsc, existing))

        # §4.6c — per-site coverage completeness.
        for s in _active_sites(wsc):
            cov = s.get("covered_by_test", "")
            if not cov or cov not in existing:
                findings.append({"mechanism": "evaluator§4.6c", "severity": "FAIL",
                                 "detail": f"site {s['site']} (action={s['action']}) not covered "
                                           f"by an existing test (covered_by_test={cov!r})"})

        # implementer §4.2b — every declared active site is actually maintained.
        for s in _active_sites(wsc):
            if s["site"] not in maintained:
                findings.append({"mechanism": "implementer§4.2b", "severity": "FLAG",
                                 "detail": f"declared site {s['site']} (action={s['action']}) "
                                           f"not maintained by the implementation"})

    # implementer §2.1 — plan-contract is authoritative; mismatch escalates.
    plan = case.get("plan", {})
    contract_steps = plan.get("contract_steps")
    prose_parsed = plan.get("prose_step_count")
    if contract_steps is None:
        findings.append({"mechanism": "implementer§2.1", "severity": "WARN",
                         "detail": "no machine-readable plan-contract block; fell back to heading parse"})
    elif prose_parsed is not None and len(contract_steps) != prose_parsed:
        findings.append({"mechanism": "implementer§2.1", "severity": "FLAG",
                         "detail": f"plan-contract steps ({len(contract_steps)}) != prose headings "
                                   f"parsed ({prose_parsed}) — possible silent step drop"})
    return findings


ENGINES = {"before_p0": before_p0, "after_p0": after_p0}


def detected_by(findings: list[Finding], expected_mechanisms: list[str]) -> bool:
    """True iff a finding fired for one of the mechanisms that SHOULD catch the defect.

    Mechanism-matched (not just len>0) so a finding raised for an unrelated reason
    is not counted as detecting this defect.
    """
    if not expected_mechanisms:
        return False
    fired = {f["mechanism"] for f in findings}
    return any(m in fired for m in expected_mechanisms)
