#!/usr/bin/env python3
"""mutate.py — mutation operators over a clean baseline case.

Each operator injects ONE realistic defect into a copy of a clean case and
declares, per ruleset, which mechanism *should* catch it. The scorer then asks
each ruleset whether it actually did — yielding a before-vs-after detection rate.

Categories:
  clean    — control: no defect; both rulesets must stay silent (false-positive guard)
  hard     — a real defect P0 is meant to close; counts in the headline detection rate
  residual — a real defect P0 does NOT close (honest boundary; neither ruleset catches)
  soft     — degraded-but-tolerated; surfaced as WARN, reported but not in the rate

Operators are pure: deepcopy in, mutated copy out.
"""
from __future__ import annotations

import copy
import re
from typing import Callable

_HEADING = re.compile(r"^##\s+Step\s+\d+\s*:")


def normalize(case: dict) -> dict:
    """Derive plan.prose_step_count from plan.prose_steps (heading-regex count)."""
    case = copy.deepcopy(case)
    plan = case.setdefault("plan", {})
    prose = plan.get("prose_steps", [])
    plan["prose_step_count"] = sum(1 for line in prose if _HEADING.search(line))
    return case


def _sneaky_site_index(wsc: dict) -> int:
    """The capacity/eviction/reorg site that feature-focused work most often drops."""
    for i, s in enumerate(wsc.get("sites", [])):
        if re.search(r"truncate|evict|reorg|demote", s["site"], re.I):
            return i
    return min(2, len(wsc.get("sites", [])) - 1)


# --- operators ---------------------------------------------------------------

def op_clean(case: dict) -> dict:
    return copy.deepcopy(case)


def op_impl_drop_site(case: dict) -> dict:
    c = copy.deepcopy(case)
    wsc = c["design"]["write_site_contract"]
    site = wsc["sites"][_sneaky_site_index(wsc)]["site"]
    c["impl"]["maintained_sites"] = [s for s in c["impl"]["maintained_sites"] if s != site]
    return c


def op_uncover_blank(case: dict) -> dict:
    c = copy.deepcopy(case)
    wsc = c["design"]["write_site_contract"]
    wsc["sites"][_sneaky_site_index(wsc)]["covered_by_test"] = ""
    return c


def op_uncover_badname(case: dict) -> dict:
    c = copy.deepcopy(case)
    wsc = c["design"]["write_site_contract"]
    wsc["sites"][_sneaky_site_index(wsc)]["covered_by_test"] = "TestThatDoesNotExist"
    return c


def op_drop_invariant_test(case: dict) -> dict:
    c = copy.deepcopy(case)
    inv = c["design"]["write_site_contract"]["invariant_test"]
    c["impl"]["existing_tests"] = [t for t in c["impl"]["existing_tests"] if t != inv]
    return c


def op_drop_adversarial_test(case: dict) -> dict:
    c = copy.deepcopy(case)
    adv = c["design"]["write_site_contract"]["adversarial_test"]
    c["impl"]["existing_tests"] = [t for t in c["impl"]["existing_tests"] if t != adv]
    return c


def op_plan_malformed_heading(case: dict) -> dict:
    """Drop the colon on the last step heading so the legacy regex skips it."""
    c = copy.deepcopy(case)
    prose = c["plan"]["prose_steps"]
    prose[-1] = prose[-1].replace(":", " -", 1)
    return normalize(c)


def op_plan_block_absent(case: dict) -> dict:
    c = copy.deepcopy(case)
    c["plan"]["contract_steps"] = None
    return c


def op_contract_underdeclare(case: dict) -> dict:
    """Planner omits a ground-truth mutation site from the contract (and impl
    follows the contract, so it's unmaintained too). The site stays in
    ground_truth — a genuine defect — but neither machine check iterates over
    ground truth, so P0 does NOT catch it. Honest boundary."""
    c = copy.deepcopy(case)
    wsc = c["design"]["write_site_contract"]
    idx = _sneaky_site_index(wsc)
    dropped = wsc["sites"].pop(idx)["site"]
    c["impl"]["maintained_sites"] = [s for s in c["impl"]["maintained_sites"] if s != dropped]
    c.setdefault("_meta", {})["underdeclared_site"] = dropped
    return c


# (label, category, operator, expected_before[], expected_after[])
MUTATIONS: list[tuple[str, str, Callable[[dict], dict], list[str], list[str]]] = [
    ("clean",                  "clean",    op_clean,                 [],                  []),
    ("impl_drop_site",         "hard",     op_impl_drop_site,        [],                  ["implementer§4.2b"]),
    ("uncover_blank",          "hard",     op_uncover_blank,         [],                  ["evaluator§4.6c"]),
    ("uncover_badname",        "hard",     op_uncover_badname,       [],                  ["evaluator§4.6c"]),
    ("drop_invariant_test",    "hard",     op_drop_invariant_test,   ["evaluator§4.6a"],  ["evaluator§4.6a"]),
    ("drop_adversarial_test",  "hard",     op_drop_adversarial_test, ["evaluator§4.6b"],  ["evaluator§4.6b"]),
    ("plan_malformed_heading", "hard",     op_plan_malformed_heading,[],                  ["implementer§2.1"]),
    ("plan_block_absent",      "soft",     op_plan_block_absent,     [],                  ["implementer§2.1"]),
    ("contract_underdeclare",  "residual", op_contract_underdeclare, [],                  []),
]
