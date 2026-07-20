#!/usr/bin/env bash
# verify.sh — binary safety test for evaluator §7.6 scoped cleanup (overlay P5).
#
# Proves, with real processes, that:
#   1. SCOPED cleanup spares a pre-existing ("developer's") instance and kills only
#      the one started after the snapshot ("ours").
#   2. The pre-P5 NAIVE `pkill -f <pattern>` would have killed the foreign one too
#      (the bug P5 fixes).
# Exits 0 only if scoped spares-foreign + kills-ours AND naive kills-foreign.
#
# Uses harmless `sleep` dummies tagged with a unique per-run marker — never touches
# anything but its own dummies.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
SCOPED="$HERE/cleanup_scoped.sh"
MARK="p5scopetest_$$_$(date +%s)"
TMP="$(mktemp -d)"
LAUNCHED=()
fail=0

SPAWNED_PID=""
spawn() {  # start a dummy whose argv contains $MARK; sets SPAWNED_PID.
  # NOTE: must run in the main shell (not in $(...)) — a command-substitution
  # subshell SIGHUPs its background child on exit, killing the dummy early.
  sh -c ": $MARK ; sleep 10" &
  SPAWNED_PID=$!
  LAUNCHED+=("$SPAWNED_PID")
}
alive() { kill -0 "$1" 2>/dev/null; }
cleanup_all() {
  for p in "${LAUNCHED[@]:-}"; do kill -KILL "$p" 2>/dev/null || true; done
  rm -rf "$TMP"
}
trap cleanup_all EXIT

echo "# P5 cleanup-scope — binary safety test (marker=$MARK)"

# --- 1. SCOPED cleanup -------------------------------------------------------
spawn; FPID=$SPAWNED_PID; echo "  foreign (pre-existing) pid=$FPID"
"$SCOPED" snapshot "$MARK" > "$TMP/pre.txt"
spawn; OPID=$SPAWNED_PID; echo "  ours (after snapshot)   pid=$OPID"

"$SCOPED" cleanup "$MARK" "$TMP/pre.txt" | sed 's/^/  /'
sleep 2
if alive "$FPID"; then echo "  PASS: foreign $FPID survived scoped cleanup"
else echo "  FAIL: scoped cleanup killed foreign $FPID"; fail=1; fi
if alive "$OPID"; then echo "  FAIL: ours $OPID still alive after scoped cleanup"; fail=1
else echo "  PASS: ours $OPID terminated by scoped cleanup"; fi

# --- 2. NAIVE cleanup (the pre-P5 bug) --------------------------------------
spawn; GPID=$SPAWNED_PID; echo "  naive-demo foreign pid=$GPID"
pkill -f "$MARK" 2>/dev/null || true     # this is what old §7.6 did
sleep 1
if alive "$GPID"; then echo "  UNEXPECTED: naive pkill spared foreign $GPID"; fail=1
else echo "  confirmed: naive pkill killed foreign $GPID (the pre-P5 bug)"; fi

echo
if [ "$fail" -eq 0 ]; then echo "P5 cleanup-scope: PASS"; else echo "P5 cleanup-scope: FAIL"; fi
exit "$fail"
