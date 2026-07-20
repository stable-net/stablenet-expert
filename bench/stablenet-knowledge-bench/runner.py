"""runner.py — per-cell runner with batch/resume support.

Usage:
    from runner import run
    run(manifest, exp_dir, continue_run=True, batch_size=8)

Per cell pipeline:
  1. Load question YAML from golden-set
  2. Instantiate method dispatcher (M1-M4)
  3. Call driver.ask() via method.run()
  4. Extract structured response (bench_io.extract)
  5. Score 4 metrics (location P/R/F1, correctness, hallucinations, info_volume)
  6. Write cells/<q>__<method>/result.json
  7. Update state.json atomically

SIGINT: write state, exit 130 (allows resume via --continue flag).
"""

from __future__ import annotations

import json
import os
import signal
import sys
from typing import Any, Dict, List, Optional

from bench_io.extract import extract_response
from drivers.base import AskResult
from scorers.correctness import score_correctness
from scorers.hallucination import score_hallucination
from scorers.info_volume import score_info_volume
from scorers.location import score_location
from state import (
    CELL_DONE,
    init_state,
    is_complete,
    load_state,
    mark_cell_done,
    mark_cell_failed,
    mark_cell_running,
    pending_cells,
    save_state,
    write_cell_result,
)

try:
    import yaml as _yaml
    def _load_yaml(path: str) -> Any:
        with open(path, "r", encoding="utf-8") as fh:
            return _yaml.safe_load(fh)
except ImportError:
    # Minimal fallback: use validate_golden's parser
    sys.path.insert(0, os.path.dirname(__file__))
    from validate_golden import load_yaml as _load_yaml


def _load_question(golden_set_dir: str, q_meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Load a full question YAML from the golden-set directory."""
    q_file = q_meta.get("file")
    if not q_file:
        return None
    path = os.path.join(golden_set_dir, q_file)
    if not os.path.isfile(path):
        return None
    try:
        return _load_yaml(path)
    except Exception:
        return None


def _make_method(method_id: str, manifest: Dict[str, Any], cks_tool: Optional[Any] = None) -> Any:
    """Instantiate a method dispatcher from its ID."""
    from methods import METHOD_REGISTRY
    cls = METHOD_REGISTRY.get(method_id)
    if cls is None:
        raise ValueError(f"Unknown method: {method_id}")
    root = manifest["go_stablenet_root"]
    corpus_root = manifest.get("domain_corpus_root")
    # M2/M3/M4 accept cks_tool; M1 does not
    try:
        return cls(go_stablenet_root=root, cks_tool=cks_tool)
    except TypeError:
        return cls(go_stablenet_root=root)


def _make_driver(manifest: Dict[str, Any]) -> Any:
    """Instantiate the driver from the manifest."""
    driver_name = manifest.get("driver", "replay")
    if driver_name == "replay":
        from drivers.replay import ReplayDriver
        driver_cfg = manifest.get("driver_config", {}) or {}
        _bench_root = os.path.dirname(os.path.abspath(__file__))
        replay_dir_raw = driver_cfg.get("replay_dir") or os.path.join(
            _bench_root, "tests", "fixtures", "replay"
        )
        # Resolve relative paths against _bench_root
        if not os.path.isabs(replay_dir_raw):
            replay_dir = os.path.join(_bench_root, replay_dir_raw)
        else:
            replay_dir = replay_dir_raw
        # Create replay_dir if it doesn't exist (non-strict replay still works)
        os.makedirs(replay_dir, exist_ok=True)
        strict = driver_cfg.get("strict", True)
        return ReplayDriver(replay_dir=replay_dir, strict=strict)
    elif driver_name == "claude_cli":
        from drivers.claude_cli import ClaudeCLIDriver
        driver_cfg = manifest.get("driver_config", {}) or {}
        return ClaudeCLIDriver(
            claude_bin=driver_cfg.get("claude_bin", "claude"),
            timeout=driver_cfg.get("claude_cli_timeout", 120),
            model=driver_cfg.get("model"),
            transcript_dir=driver_cfg.get("transcript_dir"),
        )
    else:
        raise ValueError(f"Unknown driver: {driver_name}")


def _score_cell(
    question: Dict[str, Any],
    ask_result: AskResult,
    go_stablenet_root: str,
    cks_tool: Optional[Any] = None,
    domain_corpus_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract and score a single cell; return the result dict."""
    from bench_io.envelope import Citation

    parsed = extract_response(ask_result.response_text)
    expected_cites = [
        Citation.from_dict(c)
        for c in (question.get("expected_citations") or [])
        if isinstance(c, dict)
    ]
    predicted_cites = parsed.citations
    keywords = question.get("expected_keywords") or []

    loc = score_location(predicted_cites, expected_cites)
    correct = score_correctness(
        parsed.answer,
        loc,
        keywords,
        parse_failed=(parsed.parse_mode == "failed"),
    )
    halluc = score_hallucination(predicted_cites, go_stablenet_root, cks_tool, domain_corpus_root)
    info_vol = score_info_volume(ask_result.injected_tokens)

    return {
        "question_id": question.get("id"),
        "method_id": None,  # filled in by run()
        "parse_mode": parsed.parse_mode,
        "answer": parsed.answer[:500],  # truncate for storage
        "citations": [c.to_dict() for c in predicted_cites],
        "location": loc.to_dict(),
        "correctness": correct,
        "hallucinations": halluc.to_dict(),
        "info_volume_tokens": info_vol,
        "ask": {
            "input_tokens": ask_result.input_tokens,
            "injected_tokens": ask_result.injected_tokens,
            "output_tokens": ask_result.output_tokens,
            "turns": ask_result.turns,
            "transcript_path": ask_result.transcript_path,
            "driver_name": ask_result.driver_name,
            "error": ask_result.error,
        },
    }


def run(
    manifest: Dict[str, Any],
    exp_dir: str,
    continue_run: bool = False,
    batch_size: Optional[int] = None,
    cks_tool: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run (or resume) a benchmark experiment.

    Parameters
    ----------
    manifest : the loaded manifest dict
    exp_dir : experiment output directory (absolute path)
    continue_run : if True, skip already-completed cells
    batch_size : override manifest batch_size
    cks_tool : optional cks dispatcher (for M2/M3/M4)

    Returns
    -------
    state dict after this run's batch completes
    """
    if batch_size is None:
        batch_size = manifest.get("batch_size", 8)

    # Load golden-set index
    ckg_root = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(
        ckg_root,
        manifest.get("golden_set", {}).get("source", "golden-set/index.yaml"),
    )
    index = _load_yaml(index_path)
    questions_meta = index.get("questions", [])

    # Filter by manifest.golden_set.ids and .buckets
    ids_filter = set(manifest.get("golden_set", {}).get("ids") or [])
    buckets_filter = set(manifest.get("golden_set", {}).get("buckets") or [])
    if ids_filter:
        questions_meta = [q for q in questions_meta if q.get("id") in ids_filter]
    if buckets_filter:
        questions_meta = [q for q in questions_meta if q.get("bucket") in buckets_filter]

    question_ids = [q["id"] for q in questions_meta]
    method_ids: List[str] = manifest.get("methods", [])
    sha_pin: str = manifest.get("sha_pin", "")

    # Init or load state
    golden_set_dir = os.path.join(ckg_root, "golden-set")
    state = init_state(exp_dir, manifest["experiment"], sha_pin, question_ids, method_ids)

    # SIGINT handler: save state and exit 130
    _interrupted = [False]

    def _handle_sigint(sig, frame):  # noqa: ANN001
        _interrupted[0] = True

    orig_handler = signal.signal(signal.SIGINT, _handle_sigint)

    driver = _make_driver(manifest)
    root = manifest["go_stablenet_root"]
    corpus_root = manifest.get("domain_corpus_root")

    try:
        pending = pending_cells(state)
        cells_run = 0

        for qid, mid in pending:
            if _interrupted[0]:
                break
            if cells_run >= batch_size:
                break

            # Load question
            q_meta = next((q for q in questions_meta if q.get("id") == qid), None)
            if q_meta is None:
                mark_cell_failed(state, qid, mid, f"question {qid} not in index")
                save_state(exp_dir, state)
                cells_run += 1
                continue

            question = _load_question(golden_set_dir, q_meta)
            if question is None:
                mark_cell_failed(state, qid, mid, f"could not load question YAML for {qid}")
                save_state(exp_dir, state)
                cells_run += 1
                continue

            mark_cell_running(state, qid, mid)
            save_state(exp_dir, state)

            # Run method
            try:
                method = _make_method(mid, manifest, cks_tool)
                ask_result = method.run(question, driver)
            except Exception as exc:
                mark_cell_failed(state, qid, mid, f"method error: {exc}")
                save_state(exp_dir, state)
                cells_run += 1
                continue

            # Score
            try:
                cell_result = _score_cell(question, ask_result, root, cks_tool, corpus_root)
                cell_result["method_id"] = mid
            except Exception as exc:
                mark_cell_failed(state, qid, mid, f"scoring error: {exc}")
                save_state(exp_dir, state)
                cells_run += 1
                continue

            # Write result and update state
            result_path = write_cell_result(exp_dir, qid, mid, cell_result)
            mark_cell_done(state, qid, mid, result_path)
            save_state(exp_dir, state)
            cells_run += 1

    finally:
        signal.signal(signal.SIGINT, orig_handler)
        if _interrupted[0]:
            print(
                f"\nInterrupted after {cells_run} cells. "
                f"Resume with --continue flag.",
                file=sys.stderr,
            )

    if _interrupted[0]:
        sys.exit(130)

    return state
