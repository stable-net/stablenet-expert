#!/usr/bin/env bash
# core-dev — PostToolUse hook for the Bash tool.
#
# Fires after every Bash invocation. Filters for `git commit` calls (and only
# those) so it can log commit hashes into the appropriate workspace impl.log.
# Quiet by design: this hook never blocks the pipeline.

set -u

payload="$(cat 2>/dev/null || true)"

# Inspect only the actual command (PostToolUse Bash payload: .tool_input.command),
# NOT the whole payload — otherwise any tool whose output merely contains the text
# "git commit" (git log, echo, a help string, this comment) would trip the hook.
# Match a real `git [-C <path>] commit` invocation at the start of the command or
# after a shell separator. (Requires jq, like the sibling on-agent-complete hook;
# if jq is absent the command is empty and we exit without logging.)
command="$(printf '%s' "${payload}" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
if ! printf '%s' "${command}" | grep -Eq '(^|[;&|])[[:space:]]*git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?commit([[:space:]]|$)'; then
  exit 0
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "${repo_root}" ] || exit 0

tickets_dir="${repo_root}/.stablenet-expert/tickets"
[ -d "${tickets_dir}" ] || exit 0

# Most recent commit details. If the commit failed, git log will still surface
# the previous commit; we accept that — the hook is for tracking, not for
# verifying that the commit landed.
commit_hash="$(git -C "${repo_root}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
commit_subject="$(git -C "${repo_root}" log -1 --pretty=%s 2>/dev/null || echo unknown)"
changed_count="$(git -C "${repo_root}" show --stat HEAD 2>/dev/null | tail -1 || echo '0 changed')"

timestamp="$(date -u +%FT%TZ)"

# Try to extract the ticket id from the commit subject ("STABLE-1234: ...").
ticket_id="$(printf '%s' "${commit_subject}" | grep -oE '^[A-Z]+-[0-9]+' || true)"

# Pick a single workspace to log to:
#   - if ticket_id matched, prefer that ticket's most recent workspace
#   - else, log to every active workspace
target_workspaces=()
if [ -n "${ticket_id}" ]; then
  shopt -s nullglob
  matches=("${tickets_dir}/${ticket_id}"_*/)
  shopt -u nullglob
  if [ "${#matches[@]}" -gt 0 ]; then
    # Newest first.
    IFS=$'\n' sorted=($(printf '%s\n' "${matches[@]}" | sort -r))
    target_workspaces=("${sorted[0]}")
  fi
fi
if [ "${#target_workspaces[@]}" -eq 0 ]; then
  for ws in "${tickets_dir}"/*/ ; do
    [ -d "${ws}" ] || continue
    [ -f "${ws}state.json" ] || continue
    target_workspaces+=("${ws}")
  done
fi

for ws in "${target_workspaces[@]}"; do
  mkdir -p "${ws}logs"
  printf '%s [INFO] hook=on-commit hash=%s subject="%s" stat=%s\n' \
    "${timestamp}" "${commit_hash}" "${commit_subject}" "${changed_count}" \
    >> "${ws}logs/impl.log" 2>/dev/null || true
done

exit 0
