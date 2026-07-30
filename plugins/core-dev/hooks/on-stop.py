#!/usr/bin/env python3
"""Stop hook — keep an autonomous pipeline moving (core-dev plugin).

The pipeline advances via the Orchestrator's own prompt loop. If the model stops
mid-pipeline (current_state non-terminal) the run silently stalls. This hook is
the deterministic convergence mechanism: when an AUTO-mode workspace is mid-flight
it returns {"decision":"block"} so the core injects the reason and runs one more
turn, continuing per state.json.

Safe by construction (no infinite loops, no nagging):
  - never block when stop_hook_active is set (the core's re-entry guard);
  - only in autonomy.mode == "auto";
  - only while current_state is non-terminal AND eval cycle <= max_eval_cycles;
  - skip workspaces untouched for > STALE_SECONDS (abandoned, not in-flight).
Generic across repos. Any parse failure -> exit 0 (never blocks).
"""
import sys
import json
import os
import glob
import time
import subprocess

TERMINAL = {"COMPLETION", "COMPLETED", "BLOCKED"}
STALE_SECONDS = 60 * 60  # don't nudge a workspace untouched for over an hour


def _repo_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=2)
        return out.stdout.strip() or os.getcwd()
    except Exception:
        return os.getcwd()


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    # Core re-entry guard: if we already blocked once in this stop chain, let it stop.
    if data.get("stop_hook_active"):
        return 0

    root = _repo_root()
    paths = glob.glob(os.path.join(root, ".stablenet-expert", "tickets", "*", "state.json"))
    paths.sort(key=lambda p: _safe_mtime(p), reverse=True)
    now = time.time()

    for p in paths:
        if now - _safe_mtime(p) > STALE_SECONDS:
            continue
        try:
            st = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        cs = st.get("current_state")
        if not cs or cs in TERMINAL:
            continue
        cfg = st.get("config") or {}
        if ((cfg.get("autonomy") or {}).get("mode")) != "auto":
            continue
        cycle = (((st.get("states") or {}).get("EVALUATION") or {}).get("cycle")) or 1
        maxc = cfg.get("max_eval_cycles") or 3
        if cycle > maxc:
            continue
        tid = st.get("ticket_id") or os.path.basename(os.path.dirname(p))
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"Pipeline incomplete: ticket {tid} is at state={cs} "
                f"(eval cycle {cycle}/{maxc}, autonomy=auto). Continue the next step "
                f"from state.json — do not stop until the workspace reaches COMPLETION "
                f"or BLOCKED."
            ),
        }))
        return 0
    return 0


def _safe_mtime(p):
    try:
        return os.path.getmtime(p)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
