#!/usr/bin/env python3
"""scenarios.py — the cks fault corpus.

Each scenario is a (health, calls) run with an expected after-P2 decision. The
spread covers: healthy control, backend-down controls, and per-call faults at each
tier × {transient, persistent} — the cases the pre-patch silent best-effort missed.
"""

# (id, scenario, expected_after_decision, note)
SCENARIOS = [
    ("healthy", {"health": "serviceable", "calls": {}},
     "CLEAN", "control: all ok → both proceed clean"),

    ("backend_down", {"health": "down", "calls": {}},
     "BLOCKED", "control: health down → both BLOCKED"),

    ("ckv_down_at_start", {"health": "degraded", "calls": {}},
     "BLOCKED", "control: ckv down at start (degraded backend = non-serviceable) → both BLOCKED"),

    ("primary_transient", {"health": "serviceable", "calls": {"get_for_task": "transient"}},
     "CLEAN", "get_for_task flaps; before=silent-incomplete, after retry recovers → CLEAN"),

    ("primary_persistent", {"health": "serviceable", "calls": {"get_for_task": "persistent"}},
     "BLOCKED", "PRIMARY lost; before=silent-incomplete, after BLOCKED (no evidence base)"),

    ("completeness_persistent", {"health": "serviceable", "calls": {"impact_analysis": "persistent"}},
     "DEGRADED", "blast-radius evidence lost; before=silent-incomplete, after DEGRADED+flag"),

    ("completeness_transient", {"health": "serviceable", "calls": {"find_callers": "transient"}},
     "CLEAN", "write-site evidence flaps; before=silent-incomplete, after retry → CLEAN"),

    ("enhancement_persistent",
     {"health": "serviceable", "calls": {"semantic_search": "persistent", "freshness": "persistent"}},
     "CLEAN", "only enhancement lost; correctly NOT silent — both proceed (after notes it)"),

    ("mixed",
     {"health": "serviceable",
      "calls": {"find_callers": "persistent", "get_subgraph": "transient", "freshness": "persistent"}},
     "DEGRADED", "find_callers persistent (DEGRADED), get_subgraph recovers, freshness noted"),

    ("intermittent_all_recover",
     {"health": "serviceable", "calls": {"get_for_task": "transient", "impact_analysis": "transient"}},
     "CLEAN", "both core calls flap but recover on retry; before=silent-incomplete, after CLEAN"),
]
