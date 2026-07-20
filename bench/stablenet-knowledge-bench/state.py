"""state.py — Run state management for the CKG Benchmark harness.

Manages atomic read/write of a run's state.json file which tracks:
  - experiment metadata
  - cell (question × method) completion status
  - per-cell result file paths

Atomic write: write to a temp file, then os.replace() for crash safety.

Cell key: ``{question_id}__{method_id}`` (double underscore)
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple


# Cell status values
CELL_PENDING = "pending"
CELL_RUNNING = "running"
CELL_DONE = "done"
CELL_FAILED = "failed"


def _cell_key(question_id: str, method_id: str) -> str:
    return f"{question_id}__{method_id}"


def _cell_result_dir(exp_dir: str, question_id: str, method_id: str) -> str:
    return os.path.join(exp_dir, "cells", _cell_key(question_id, method_id))


def init_state(
    exp_dir: str,
    experiment: str,
    sha_pin: str,
    question_ids: List[str],
    method_ids: List[str],
) -> Dict[str, Any]:
    """Initialize a fresh run state and write state.json.

    If state.json already exists, it is returned unchanged (idempotent).
    """
    state_path = os.path.join(exp_dir, "state.json")
    if os.path.isfile(state_path):
        return load_state(exp_dir)

    cells: Dict[str, Any] = {}
    for qid in question_ids:
        for mid in method_ids:
            key = _cell_key(qid, mid)
            cells[key] = {
                "question_id": qid,
                "method_id": mid,
                "status": CELL_PENDING,
                "result_path": None,
                "error": None,
            }

    state: Dict[str, Any] = {
        "experiment": experiment,
        "sha_pin": sha_pin,
        "total_cells": len(cells),
        "completed_cells": 0,
        "failed_cells": 0,
        "cells": cells,
    }

    os.makedirs(exp_dir, exist_ok=True)
    _write_atomic(state_path, state)
    return state


def load_state(exp_dir: str) -> Dict[str, Any]:
    """Load and return state.json; raises FileNotFoundError if missing."""
    state_path = os.path.join(exp_dir, "state.json")
    with open(state_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(exp_dir: str, state: Dict[str, Any]) -> None:
    """Atomically write state.json."""
    state_path = os.path.join(exp_dir, "state.json")
    _write_atomic(state_path, state)


def mark_cell_running(state: Dict[str, Any], question_id: str, method_id: str) -> None:
    """Mark a cell as running (in-place mutation)."""
    key = _cell_key(question_id, method_id)
    if key in state["cells"]:
        state["cells"][key]["status"] = CELL_RUNNING
        state["cells"][key]["error"] = None


def mark_cell_done(
    state: Dict[str, Any],
    question_id: str,
    method_id: str,
    result_path: str,
) -> None:
    """Mark a cell as done with a result file path (in-place mutation)."""
    key = _cell_key(question_id, method_id)
    if key in state["cells"]:
        prev_status = state["cells"][key]["status"]
        state["cells"][key]["status"] = CELL_DONE
        state["cells"][key]["result_path"] = result_path
        state["cells"][key]["error"] = None
        if prev_status != CELL_DONE:
            state["completed_cells"] = state.get("completed_cells", 0) + 1


def mark_cell_failed(
    state: Dict[str, Any],
    question_id: str,
    method_id: str,
    error: str,
) -> None:
    """Mark a cell as failed with an error message (in-place mutation)."""
    key = _cell_key(question_id, method_id)
    if key in state["cells"]:
        prev_status = state["cells"][key]["status"]
        state["cells"][key]["status"] = CELL_FAILED
        state["cells"][key]["error"] = error
        if prev_status != CELL_FAILED:
            state["failed_cells"] = state.get("failed_cells", 0) + 1


def pending_cells(state: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return list of (question_id, method_id) tuples for pending/running cells."""
    result = []
    for key, cell in state["cells"].items():
        if cell["status"] in (CELL_PENDING, CELL_RUNNING):
            result.append((cell["question_id"], cell["method_id"]))
    return result


def is_complete(state: Dict[str, Any]) -> bool:
    """Return True when all cells are done or failed."""
    return all(
        c["status"] in (CELL_DONE, CELL_FAILED)
        for c in state["cells"].values()
    )


def write_cell_result(
    exp_dir: str,
    question_id: str,
    method_id: str,
    result: Dict[str, Any],
) -> str:
    """Write a per-cell result.json and return the file path."""
    cell_dir = _cell_result_dir(exp_dir, question_id, method_id)
    os.makedirs(cell_dir, exist_ok=True)
    result_path = os.path.join(cell_dir, "result.json")
    _write_atomic(result_path, result)
    return result_path


def load_cell_result(
    exp_dir: str, question_id: str, method_id: str
) -> Optional[Dict[str, Any]]:
    """Load a per-cell result.json; return None if missing."""
    result_path = os.path.join(
        _cell_result_dir(exp_dir, question_id, method_id), "result.json"
    )
    if not os.path.isfile(result_path):
        return None
    with open(result_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_atomic(path: str, data: Dict[str, Any]) -> None:
    """Write JSON data to path atomically via a temp file + rename."""
    dir_ = os.path.dirname(path) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
