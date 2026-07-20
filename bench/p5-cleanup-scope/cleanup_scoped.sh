#!/usr/bin/env bash
# cleanup_scoped.sh — reference PID-scoped leftover cleanup for evaluator §7.6.
#
# The pre-P5 §7.6 killed EVERY process matching `pgrep -f 'gstable|wbft-node'`,
# which also kills a developer's unrelated local node — and can even match the
# very shell running the loop (its argv contains the pattern). This reference
# implementation only terminates processes that
#   (a) match the pattern, AND
#   (b) were NOT already running when we snapshotted before starting the network,
#   (c) are not this script or its parent.
# So a pre-existing instance is never touched. Best-effort; never errors out.
#
# Usage:
#   cleanup_scoped.sh snapshot <pattern>                 # print matching PIDs (one/line)
#   cleanup_scoped.sh cleanup  <pattern> <prepids-file>  # TERM then KILL (matching - pre - self)
set -u

cmd="${1:-}"
case "$cmd" in
  snapshot)
    pattern="${2:?pattern required}"
    pgrep -f "$pattern" 2>/dev/null || true
    ;;
  cleanup)
    pattern="${2:?pattern required}"
    prefile="${3:?prepids file required}"
    # Spare set: pre-existing PIDs + this script ($$) + its parent ($PPID).
    spare=" $(tr '\n' ' ' < "$prefile" 2>/dev/null) $$ $PPID "
    targets=()
    for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
      case "$spare" in *" $pid "*) continue ;; esac   # pre-existing / self → spare
      targets+=("$pid")
    done
    if [ "${#targets[@]}" -eq 0 ]; then
      echo "scoped-cleanup: nothing of ours to kill"
      exit 0
    fi
    echo "scoped-cleanup: terminating ours: ${targets[*]}"
    for pid in "${targets[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
    sleep 1
    for pid in "${targets[@]}"; do kill -KILL "$pid" 2>/dev/null || true; done
    ;;
  *)
    echo "usage: cleanup_scoped.sh snapshot <pattern> | cleanup <pattern> <prepids-file>" >&2
    exit 2
    ;;
esac
