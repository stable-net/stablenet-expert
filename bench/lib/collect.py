"""Per-cell result extraction for the comparison tool.

Reads one experiment directory (.stablenet-expert/bench/{experiment}/) and turns each
cell (one task under one mode) into a RunResult: correctness, safety, latency,
token usage, and cost. The correctness/safety signals are read from the
pipeline's own structured outputs (state.json, the evaluator's results) rather
than scraping log text — structured-over-grep, per the case-10 review of
oh-my-claudecode's fragile log-substring extraction.

Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .usage import CanonicalUsage, ModelPrice, estimate_cost
from .capture import collect_cell_usage

# Pipeline states that mean the modified code passed verification.
_PASS_STATES = {"EVALUATION_PASS", "COMPLETED", "COMPLETION"}
_FAIL_STATES = {"EVALUATION_FAIL", "BLOCKED"}

# A bug-cycle is one EVALUATION failure that sent the pipeline back to ANALYSIS.
# The single source of truth is failure_log (orchestrator.md §5 counts the same).
_EVAL_STATE = "EVALUATION"

# Regression / side-effect classes: an EVALUATION failure that broke something
# *beyond* the task's own unit acceptance — i.e. collateral damage the planner's
# info regime failed to prevent. Detected from the structured one-liner the
# evaluator writes into failure_log[].actual_outcome.summary (evaluator.md §9).
# Lower is better; cks's value-prop is fewer of these (complete info → right
# first fix). This is the only place per-cycle stage info is persisted, so the
# classifier is a documented heuristic over a *structured* field, not raw logs.
_SIDE_EFFECT_MARKERS = ("chainbench", "race", "regression", "derived state",
                        "derived-state", "panic", "data race")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class RunResult:
    task: str
    mode: str
    status: str = "unknown"          # done | failed | incomplete
    pipeline_state: str | None = None
    correct: bool | None = None      # final-code correctness (None = never evaluated)
    correctness_detail: dict = field(default_factory=dict)
    bug_cycles: int = 0              # EVALUATION_FAIL→re-plan re-entries (0 = passed first eval)
    side_effect_failures: int = 0    # bug-cycles caused by a regression/collateral break (lower=better)
    usage: CanonicalUsage = field(default_factory=CanonicalUsage)
    usage_by_model: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    cost_status: str = "unknown"     # actual | estimated | unknown
    usage_source: str = "none"
    latency_s: float | None = None
    safety_flags: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "mode": self.mode,
            "status": self.status,
            "pipeline_state": self.pipeline_state,
            "correct": self.correct,
            "correctness_detail": self.correctness_detail,
            "bug_cycles": self.bug_cycles,
            "side_effect_failures": self.side_effect_failures,
            "usage": self.usage.as_dict(),
            "usage_by_model": {m: u.as_dict() for m, u in self.usage_by_model.items()},
            "cost_usd": self.cost_usd,
            "cost_status": self.cost_status,
            "usage_source": self.usage_source,
            "latency_s": self.latency_s,
            "safety_flags": self.safety_flags,
        }


def _correctness(state: dict) -> tuple[bool | None, dict]:
    """Derive final-code correctness from the pipeline state + evaluator results."""
    cur = state.get("current_state")
    detail: dict = {}
    results = (state.get("states", {}).get("EVALUATION", {}) or {}).get("results", {}) or {}
    if results:
        # Per-stage statuses from the evaluator (unit_test/lint/security/chainbench).
        for stage in ("unit_test", "lint", "security", "chainbench"):
            st = results.get(stage)
            if isinstance(st, dict) and "status" in st:
                detail[stage] = st["status"]
            elif isinstance(st, str):
                detail[stage] = st
    if cur in _PASS_STATES:
        return True, detail
    if cur in _FAIL_STATES:
        return False, detail
    return None, detail  # never reached EVALUATION


def _bug_cycles(state: dict) -> tuple[int, int]:
    """(bug_cycles, side_effect_failures) from the structured failure_log.

    bug_cycles = number of EVALUATION failures (each sends the pipeline back to
    ANALYSIS for a re-plan, per orchestrator.md §5). side_effect_failures = the
    subset whose evaluator summary names a regression/collateral class.
    """
    log = state.get("failure_log")
    if not isinstance(log, list):
        return 0, 0
    cycles = 0
    side_effects = 0
    for entry in log:
        if not isinstance(entry, dict) or entry.get("state") != _EVAL_STATE:
            continue
        cycles += 1
        outcome = entry.get("actual_outcome") or {}
        summary = str(outcome.get("summary", "")).lower()
        if any(marker in summary for marker in _SIDE_EFFECT_MARKERS):
            side_effects += 1
    return cycles, side_effects


def _safety(state: dict) -> list[str]:
    flags: list[str] = []
    intake = (state.get("states", {}).get("TICKET_INTAKE", {}) or {}).get("sensitive_check", {}) or {}
    # sensitive_check should be an object, but tolerate a bare string verdict —
    # one malformed cell must not take down the whole experiment report
    # (the no-truncation rule: failed/odd cells still get counted).
    if isinstance(intake, str):
        intake = {"result": intake}
    if not isinstance(intake, dict):
        intake = {}
    if intake.get("result") in ("REDACTED", "BLOCKED"):
        flags.append(f"sensitive_{str(intake.get('result')).lower()}")
    results = (state.get("states", {}).get("EVALUATION", {}) or {}).get("results", {}) or {}
    sec = results.get("security")
    sec_status = sec.get("status") if isinstance(sec, dict) else sec
    if sec_status == "FAIL":
        flags.append("security_fail")
    ut = results.get("unit_test")
    if isinstance(ut, dict) and ut.get("race_detected"):
        flags.append("race_detected")
    return flags


def collect_cell(cell_dir: Path, prices: dict[str, ModelPrice] | None = None,
                 session_path: Path | None = None) -> RunResult:
    meta = _read_json(cell_dir / "run-meta.json")
    state = _read_json(cell_dir / "state.json")

    rr = RunResult(
        task=meta.get("task") or state.get("ticket_id") or cell_dir.name,
        mode=meta.get("mode") or "unknown",
        status=meta.get("status") or ("done" if state else "incomplete"),
        pipeline_state=state.get("current_state"),
    )

    rr.correct, rr.correctness_detail = _correctness(state)
    rr.bug_cycles, rr.side_effect_failures = _bug_cycles(state)
    rr.safety_flags = _safety(state)

    # Latency: prefer run-meta start/end, else pipeline timestamps.
    start = _parse_iso(meta.get("started_at") or state.get("created_at"))
    end = _parse_iso(meta.get("ended_at") or state.get("updated_at"))
    if start and end:
        rr.latency_s = max(0.0, (end - start).total_seconds())

    # Tokens + cost (per model, then summed).
    by_model, source = collect_cell_usage(cell_dir, session_path=session_path)
    rr.usage_by_model = by_model
    rr.usage_source = source
    total = CanonicalUsage()
    cost_sum = 0.0
    statuses = set()
    for model, u in by_model.items():
        total = total + u
        cr = estimate_cost(u, model, source, prices)
        cost_sum += cr.amount_usd
        statuses.add(cr.status)
    rr.usage = total
    rr.cost_usd = round(cost_sum, 6)
    rr.cost_status = (
        "actual" if statuses == {"actual"}
        else "estimated" if "estimated" in statuses
        else "unknown" if statuses <= {"unknown"} else "mixed"
    )
    return rr


def collect_experiment(experiment_dir: str | Path,
                       prices: dict[str, ModelPrice] | None = None,
                       sessions: dict[str, str] | None = None) -> list[RunResult]:
    """Collect every cell of an experiment into RunResults.

    `sessions` optionally maps a cell name ("{task}__{mode}") to a Claude
    session JSONL path so real token usage is used instead of the estimate.
    """
    exp = Path(experiment_dir)
    state = _read_json(exp / "state.json")
    results: list[RunResult] = []
    cells = state.get("cells")
    if isinstance(cells, list) and cells:
        for cell in cells:
            name = cell.get("workspace") or f"{cell.get('task')}__{cell.get('mode')}"
            cell_dir = exp / Path(name).name if "/" not in name else exp / name
            cell_dir = (exp / "cells" / Path(name).name) if not cell_dir.exists() else cell_dir
            sp = (sessions or {}).get(Path(name).name)
            rr = collect_cell(cell_dir, prices=prices, session_path=Path(sp) if sp else None)
            # state.json cell row may carry the authoritative status/task/mode.
            rr.task = cell.get("task") or rr.task
            rr.mode = cell.get("mode") or rr.mode
            if cell.get("status"):
                rr.status = cell["status"]
            results.append(rr)
        return results
    # Fallback: glob the cells/ dir.
    cells_dir = exp / "cells"
    if cells_dir.is_dir():
        for cell_dir in sorted(p for p in cells_dir.iterdir() if p.is_dir()):
            results.append(collect_cell(cell_dir, prices=prices))
    return results
