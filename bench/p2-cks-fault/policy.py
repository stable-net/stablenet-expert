#!/usr/bin/env python3
"""policy.py — before-P2 and after-P2 cks in-run retrieval policies.

P2 (stream-6) hardens the analyzer/planner §3.0 cks gate. BEFORE the patch the
gate was a single start-of-run health check: serviceable → proceed, else BLOCKED.
A per-call failure DURING the run ("record and continue best-effort", e.g. §3.3b)
left no decision change and no flag — so an analysis could ship with a missing
get_for_task / find_callers / impact_analysis and nobody knew (a *silent
incomplete*). AFTER the patch (analyzer §3.0b): retry, tier the failed primitive,
and never proceed "clean" with a core gap.

A "run" is (health, calls):
  health : "serviceable" | "degraded" | "down"      (cks_ops_health at start)
  calls  : {primitive: outcome}  outcome ∈ {"ok","transient","persistent"}
           "transient"  = fails once, succeeds on retry
           "persistent" = still fails after retries
           unlisted primitives default to "ok"

Decision ∈ {"CLEAN","DEGRADED","BLOCKED"}. Pure functions — no LLM, no I/O.
"""
from __future__ import annotations

PRIMARY = {"get_for_task"}
COMPLETENESS = {"find_callers", "impact_analysis", "concurrency_impact"}
ENHANCEMENT = {"semantic_search", "get_subgraph", "change_history", "freshness"}
ALL_PRIMS = PRIMARY | COMPLETENESS | ENHANCEMENT
CORE = PRIMARY | COMPLETENESS


def normalize(scn: dict) -> tuple[str, dict[str, str]]:
    calls = {p: "ok" for p in ALL_PRIMS}
    calls.update(scn.get("calls", {}))
    return scn.get("health", "serviceable"), calls


def before_p2(health: str, calls: dict[str, str]) -> dict:
    """Pre-patch: start-of-run health gate only; per-call failures continue silently."""
    if health != "serviceable":
        return {"decision": "BLOCKED", "missing": [], "reason": f"backend {health}"}
    # No retry, no per-call handling: proceed regardless of which calls dropped.
    return {"decision": "CLEAN", "missing": [], "reason": "serviceable at start"}


def after_p2(health: str, calls: dict[str, str]) -> dict:
    """Post-patch (analyzer §3.0b): retry → tier → decide, never silent on a core gap."""
    # 1. retry: a transient failure recovers.
    eff = {p: ("ok" if o == "transient" else o) for p, o in calls.items()}
    if health in ("down", "degraded"):
        return {"decision": "BLOCKED", "missing": [], "reason": f"backend {health} (non-serviceable)"}
    failed = [p for p, o in eff.items() if o != "ok"]   # persistent only
    if any(p in PRIMARY for p in failed):
        return {"decision": "BLOCKED", "missing": sorted(p for p in failed if p in PRIMARY),
                "reason": "PRIMARY get_for_task lost — no evidence base"}
    comp = sorted(p for p in failed if p in COMPLETENESS)
    if comp:
        return {"decision": "DEGRADED", "missing": comp,
                "reason": "COMPLETENESS evidence lost — flagged + propagated"}
    return {"decision": "CLEAN", "missing": [], "reason": "core intact (only enhancement lost, if any)"}


def missing_core_before(calls: dict[str, str]) -> list[str]:
    """Core primitives the pre-patch run actually dropped (no retry → anything != ok)."""
    return sorted(p for p, o in calls.items() if o != "ok" and p in CORE)


def missing_core_after(calls: dict[str, str]) -> list[str]:
    """Core primitives still missing after retry (persistent only)."""
    return sorted(p for p, o in calls.items() if o == "persistent" and p in CORE)


def is_silent_incomplete(decision: dict, missing_core: list[str]) -> bool:
    """The forbidden state: proceeding CLEAN while core evidence is actually missing."""
    return decision["decision"] == "CLEAN" and bool(missing_core)
