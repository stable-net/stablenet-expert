"""report.py — report aggregation for the CKG Benchmark harness.

Reads all per-cell result.json files from an experiment directory,
aggregates metrics by method, and writes:
  - report/report.md   — Markdown summary with method rollup table,
                         per-question matrix, and M4-vs-M1 delta table
  - report/report.json — Full structured data
  - report/report.csv  — Method rollup as CSV

Report sections:
  1. Method rollup:
     method | n | loc_p | loc_r | loc_f1 | correct_rate | hallucs | avg_input_tokens
  2. Per-question matrix:
     question | M1_loc_f1 | M2_loc_f1 | M3_loc_f1 | M4_loc_f1 | ...
  3. Delta table (M4 vs M1):
     Δ_correct_rate | token_reduction_pct

Missing cell → "—" in the table; never crashes.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_all_results(exp_dir: str) -> List[Dict[str, Any]]:
    """Load all result.json files from cells/ subdirectory."""
    cells_dir = os.path.join(exp_dir, "cells")
    results = []
    if not os.path.isdir(cells_dir):
        return results
    for cell_key in sorted(os.listdir(cells_dir)):
        result_path = os.path.join(cells_dir, cell_key, "result.json")
        if os.path.isfile(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as fh:
                    results.append(json.load(fh))
            except Exception:
                pass
    return results


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _rollup_by_method(
    results: List[Dict[str, Any]],
    method_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Aggregate metrics by method_id."""
    buckets: Dict[str, List[Dict]] = {mid: [] for mid in method_ids}
    for r in results:
        mid = r.get("method_id") or r.get("ask", {}).get("method_id")
        if mid and mid in buckets:
            buckets[mid].append(r)

    rollup = {}
    for mid, cells in buckets.items():
        n = len(cells)
        if n == 0:
            rollup[mid] = {
                "method": mid, "n": 0,
                "loc_p": None, "loc_r": None, "loc_f1": None,
                "correct_rate": None, "hallucs": None, "avg_input_tokens": None,
            }
            continue
        loc_p = sum(_safe_float(c.get("location", {}).get("precision")) for c in cells) / n
        loc_r = sum(_safe_float(c.get("location", {}).get("recall")) for c in cells) / n
        loc_f1 = sum(_safe_float(c.get("location", {}).get("f1")) for c in cells) / n
        correct_count = sum(1 for c in cells if c.get("correctness") is True)
        correct_rate = correct_count / n
        hallucs = sum(
            _safe_int(c.get("hallucinations", {}).get("hallucination_count")) for c in cells
        )
        avg_tokens = sum(
            _safe_int(c.get("info_volume_tokens")) for c in cells
        ) / n
        rollup[mid] = {
            "method": mid, "n": n,
            "loc_p": round(loc_p, 4),
            "loc_r": round(loc_r, 4),
            "loc_f1": round(loc_f1, 4),
            "correct_rate": round(correct_rate, 4),
            "hallucs": hallucs,
            "avg_input_tokens": round(avg_tokens, 1),
        }
    return rollup


def _per_question_matrix(
    results: List[Dict[str, Any]],
    question_ids: List[str],
    method_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Build a question × method dict of key metrics."""
    # index: (qid, mid) -> result
    index: Dict[Tuple[str, str], Dict] = {}
    for r in results:
        qid = r.get("question_id")
        mid = r.get("method_id")
        if qid and mid:
            index[(qid, mid)] = r

    matrix: Dict[str, Dict[str, Any]] = {}
    for qid in question_ids:
        row: Dict[str, Any] = {"question_id": qid}
        for mid in method_ids:
            r = index.get((qid, mid))
            if r is None:
                row[mid] = None
            else:
                row[mid] = {
                    "loc_f1": _safe_float(r.get("location", {}).get("f1")),
                    "correct": r.get("correctness"),
                    "hallucs": _safe_int(r.get("hallucinations", {}).get("hallucination_count")),
                    "tokens": _safe_int(r.get("info_volume_tokens")),
                    "parse_mode": r.get("parse_mode"),
                }
        matrix[qid] = row
    return matrix


def _delta_table(
    rollup: Dict[str, Dict[str, Any]],
    baseline_method: str = "M1_raw",
    target_method: str = "M4_get_for_task",
) -> Optional[Dict[str, Any]]:
    """Compute M4-vs-M1 delta metrics."""
    base = rollup.get(baseline_method)
    target = rollup.get(target_method)
    if not base or not target:
        return None
    if base["correct_rate"] is None or target["correct_rate"] is None:
        return None

    delta_correct = round(
        (_safe_float(target["correct_rate"]) - _safe_float(base["correct_rate"])), 4
    )
    base_tokens = _safe_float(base["avg_input_tokens"], default=1.0)
    target_tokens = _safe_float(target["avg_input_tokens"])
    if base_tokens > 0:
        token_reduction_pct = round(100 * (1 - target_tokens / base_tokens), 1)
    else:
        token_reduction_pct = 0.0

    return {
        "baseline": baseline_method,
        "target": target_method,
        "delta_correct_rate": delta_correct,
        "token_reduction_pct": token_reduction_pct,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _fmt(val: Any, default: str = "—") -> str:
    if val is None:
        return default
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


def _render_rollup_md(rollup: Dict[str, Dict[str, Any]], method_ids: List[str]) -> str:
    header = "| method | n | loc_p | loc_r | loc_f1 | correct_rate | hallucs | avg_input_tokens |"
    sep = "|--------|---|-------|-------|--------|--------------|---------|------------------|"
    rows = [header, sep]
    for mid in method_ids:
        row = rollup.get(mid, {})
        rows.append(
            f"| {mid} | {_fmt(row.get('n'))} | {_fmt(row.get('loc_p'))} "
            f"| {_fmt(row.get('loc_r'))} | {_fmt(row.get('loc_f1'))} "
            f"| {_fmt(row.get('correct_rate'))} | {_fmt(row.get('hallucs'))} "
            f"| {_fmt(row.get('avg_input_tokens'))} |"
        )
    return "\n".join(rows)


def _render_matrix_md(
    matrix: Dict[str, Dict[str, Any]], question_ids: List[str], method_ids: List[str]
) -> str:
    col_headers = " | ".join(f"{mid} f1" for mid in method_ids)
    header = f"| question | {col_headers} | correct ({method_ids[0] if method_ids else ''}) |"
    sep = "|---------|" + "|".join("------" for _ in method_ids) + "|--------|"
    rows = [header, sep]
    for qid in question_ids:
        row = matrix.get(qid, {})
        cols = []
        for mid in method_ids:
            cell = row.get(mid)
            if cell is None:
                cols.append("—")
            else:
                cols.append(_fmt(cell.get("loc_f1")))
        first_correct = "—"
        if method_ids:
            first_cell = row.get(method_ids[0])
            if first_cell is not None:
                first_correct = "Y" if first_cell.get("correct") else "N"
        rows.append(f"| {qid} | " + " | ".join(cols) + f" | {first_correct} |")
    return "\n".join(rows)


def _render_delta_md(delta: Optional[Dict[str, Any]]) -> str:
    if delta is None:
        return "_Delta table not available (M1 or M4 results missing)._\n"
    return (
        f"| metric | value |\n"
        f"|--------|-------|\n"
        f"| baseline | {delta['baseline']} |\n"
        f"| target | {delta['target']} |\n"
        f"| Δ_correct_rate | {delta['delta_correct_rate']:+.4f} |\n"
        f"| token_reduction_% | {delta['token_reduction_pct']:+.1f} |\n"
    )


# ---------------------------------------------------------------------------
# CSV rendering
# ---------------------------------------------------------------------------

def _render_rollup_csv(rollup: Dict[str, Dict[str, Any]], method_ids: List[str]) -> str:
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["method", "n", "loc_p", "loc_r", "loc_f1",
                    "correct_rate", "hallucs", "avg_input_tokens"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for mid in method_ids:
        row = rollup.get(mid, {"method": mid})
        writer.writerow(row)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_report(
    exp_dir: str,
    method_ids: Optional[List[str]] = None,
) -> str:
    """Build and write report files; return path to report.md.

    Parameters
    ----------
    exp_dir : path to the experiment directory (contains cells/ and state.json)
    method_ids : ordered list of method IDs. If None, inferred from results.
    """
    results = _load_all_results(exp_dir)

    # Infer method_ids and question_ids from results if not provided
    all_methods = []
    all_questions = []
    seen_methods: set = set()
    seen_questions: set = set()
    for r in results:
        mid = r.get("method_id")
        qid = r.get("question_id")
        if mid and mid not in seen_methods:
            all_methods.append(mid)
            seen_methods.add(mid)
        if qid and qid not in seen_questions:
            all_questions.append(qid)
            seen_questions.add(qid)

    if method_ids is None:
        method_ids = all_methods
    question_ids = all_questions

    rollup = _rollup_by_method(results, method_ids)
    matrix = _per_question_matrix(results, question_ids, method_ids)
    delta_m1_raw = _delta_table(rollup, baseline_method="M1_raw", target_method="M4_get_for_task")
    delta_m1_fair = _delta_table(rollup, baseline_method="M1_fair", target_method="M4_get_for_task")

    # Build report.md
    md_lines = [
        "# CKG Benchmark Report",
        "",
        f"Experiment: `{os.path.basename(exp_dir)}`",
        f"Total cells: {len(results)}",
        "",
        "## Method Rollup",
        "",
        _render_rollup_md(rollup, method_ids),
        "",
        "## M4 vs M1_raw Delta",
        "",
        _render_delta_md(delta_m1_raw),
        "",
        "## M4 vs M1_fair Delta",
        "",
        _render_delta_md(delta_m1_fair),
        "",
        "## Per-Question Matrix",
        "",
        _render_matrix_md(matrix, question_ids, method_ids),
        "",
    ]
    report_md = "\n".join(md_lines)

    # Write outputs
    report_dir = os.path.join(exp_dir, "report")
    os.makedirs(report_dir, exist_ok=True)

    md_path = os.path.join(report_dir, "report.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(report_md)

    json_path = os.path.join(report_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "rollup": rollup,
                "matrix": matrix,
                "delta": delta_m1_raw,
                "delta_m1_fair": delta_m1_fair,
                "total_cells": len(results),
            },
            fh, indent=2, ensure_ascii=False,
        )

    csv_path = os.path.join(report_dir, "report.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(_render_rollup_csv(rollup, method_ids))

    return md_path
