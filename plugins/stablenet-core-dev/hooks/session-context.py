#!/usr/bin/env python3
"""SessionStart context injection (stablenet-core-dev plugin).

At session start, surface any in-flight pipeline workspaces so the assistant knows
what is resumable without the user running /stablenet-core-dev:status. Injected via
additionalContext, so it rides on every query that session. Silent when there is
nothing in flight. Generic across repos.

Cost guard: at most MAX_WS workspaces (newest first), one line each.
"""
import sys
import json
import os
import glob
import subprocess

TERMINAL = {"COMPLETION", "COMPLETED"}  # BLOCKED is shown (it needs attention)
MAX_WS = 5


def _repo_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=2)
        return out.stdout.strip() or os.getcwd()
    except Exception:
        return os.getcwd()


def _safe_mtime(p):
    try:
        return os.path.getmtime(p)
    except Exception:
        return 0


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass  # SessionStart payload is unused; proceed regardless

    root = _repo_root()
    paths = glob.glob(os.path.join(root, ".stablenet-expert", "tickets", "*", "state.json"))
    paths.sort(key=lambda p: _safe_mtime(p), reverse=True)

    lines = []
    for p in paths:
        if len(lines) >= MAX_WS:
            break
        try:
            st = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        cs = st.get("current_state")
        if not cs or cs in TERMINAL:
            continue
        tid = st.get("ticket_id") or os.path.basename(os.path.dirname(p))
        if cs == "BLOCKED":
            lines.append(f"- {tid}: BLOCKED — needs attention (see its workspace).")
        else:
            cfg = st.get("config") or {}
            cyc = (((st.get("states") or {}).get("EVALUATION") or {}).get("cycle")) or 1
            maxc = cfg.get("max_eval_cycles") or 3
            mode = ((cfg.get("autonomy") or {}).get("mode")) or "interactive"
            lines.append(f"- {tid}: {cs} (eval cycle {cyc}/{maxc}, autonomy={mode})")

    if not lines:
        return 0

    ctx = ("Active stablenet-core-dev pipeline workspace(s) — resume with /stablenet-core-dev:work "
           "or continue per state.json:\n" + "\n".join(lines))
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
