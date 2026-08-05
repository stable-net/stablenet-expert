#!/usr/bin/env bash
# core-dev — PostToolUse hook for the Agent tool.
#
# Fires after a sub-agent (orchestrator/planner/implementer/evaluator) finishes.
# Reads the hook payload from stdin (Claude Code passes JSON) and writes two
# things to every active workspace under .stablenet-expert/tickets/ AND every active
# bench cell under .stablenet-expert/bench/*/cells/:
#   1. impl.log         — a one-line human-readable marker (quick index).
#   2. agent-transcript.jsonl — a transcript record carrying the VERBATIM
#      sub-agent prompt (input) and response (output), so a run can be replayed
#      and so input/output token+cost accounting can be derived after the fact
#      (the substrate for the 3-way comparison report).
#
# The hook never fails the pipeline. It exits 0 even when logging is impossible
# (e.g., outside a git repo, no jq) so the agent run is never blocked by it.

set -u

# Read the JSON payload (best-effort).
payload="$(cat 2>/dev/null || true)"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "${repo_root}" ]; then
  exit 0
fi

# Workspace roots: /work tickets + bench cells (both hold a state.json per
# workspace). Bench cells were silently skipped before 2026-07-05, which zeroed
# the token accounting compare.py derives from agent-transcript.jsonl.
tickets_dir="${repo_root}/.stablenet-expert/tickets"
bench_dir="${repo_root}/.stablenet-expert/bench"
[ -d "${tickets_dir}" ] || [ -d "${bench_dir}" ] || exit 0

timestamp="$(date -u +%FT%TZ)"

have_jq=0
command -v jq >/dev/null 2>&1 && have_jq=1

# Extract subagent_type, the verbatim prompt, and the verbatim response.
subagent_type="unknown"
transcript_line=""
if [ "${have_jq}" -eq 1 ]; then
  extracted="$(printf '%s' "${payload}" | jq -r '.tool_input.subagent_type // empty' 2>/dev/null || true)"
  [ -n "${extracted}" ] && subagent_type="${extracted}"

  # Build a compact JSONL record. tool_response may be a string or an object;
  # keep it as-is. prompt/description are captured verbatim (no truncation) so
  # token accounting is exact. Approx char counts are added as a cheap proxy.
  transcript_line="$(printf '%s' "${payload}" | jq -c \
    --arg timestamp "${timestamp}" \
    '{
       ts: $timestamp,
       subagent_type: (.tool_input.subagent_type // "unknown"),
       description: (.tool_input.description // null),
       prompt: (.tool_input.prompt // null),
       response: (.tool_response // null),
       prompt_chars: ((.tool_input.prompt // "") | tostring | length),
       response_chars: ((.tool_response // "") | tostring | length)
     }' 2>/dev/null || true)"
fi

# Write to every active workspace (state.json present and not COMPLETED).
for ws in "${tickets_dir}"/*/ "${bench_dir}"/*/cells/*/ ; do
  [ -d "${ws}" ] || continue
  state_file="${ws}state.json"
  [ -f "${state_file}" ] || continue

  current_state=""
  if [ "${have_jq}" -eq 1 ]; then
    current_state="$(jq -r '.current_state // empty' "${state_file}" 2>/dev/null || true)"
  fi
  [ "${current_state}" = "COMPLETED" ] && continue

  mkdir -p "${ws}logs"
  printf '%s [INFO] hook=on-agent-complete subagent=%s\n' \
    "${timestamp}" "${subagent_type}" >> "${ws}logs/impl.log" 2>/dev/null || true

  # Transcript JSONL (append one record per agent completion).
  if [ -n "${transcript_line}" ]; then
    printf '%s\n' "${transcript_line}" >> "${ws}logs/agent-transcript.jsonl" 2>/dev/null || true
  fi
done

exit 0
