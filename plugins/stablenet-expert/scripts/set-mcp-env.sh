#!/usr/bin/env bash
# set-mcp-env.sh — set one MCP-related env var (a URL/IP-bearing endpoint, a token, etc.) into
# a Claude Code settings file's `env` map, via a hidden local prompt.
#
# IMPORTANT: run this yourself, directly in your own terminal. Do NOT ask Claude Code to run
# it for you (a Bash tool call's stdin/stdout both flow through the LLM's context), and do NOT
# paste the value into the chat/AskUserQuestion -- either path sends the value straight into
# the conversation, which is exactly what this script exists to avoid for internal network
# addresses and secrets (see check-mcp-connectivity.sh, which deliberately never prints a
# resolved value for the same reason). This script's own output never echoes the value back.
set -euo pipefail

usage() {
  echo "Usage: $0 <ENV_VAR_NAME> [--scope user|project]" >&2
  echo "  user    (default) -- writes ~/.claude/settings.json (applies to every project)" >&2
  echo "  project -- writes ./.claude/settings.local.json (this project only, gitignored)" >&2
  exit 1
}

[ $# -ge 1 ] || usage
VAR_NAME="$1"; shift
SCOPE="user"
while [ $# -gt 0 ]; do
  case "$1" in
    --scope) SCOPE="${2:?--scope needs a value}"; shift 2 ;;
    *) usage ;;
  esac
done

case "$SCOPE" in
  user)
    TARGET="$HOME/.claude/settings.json"
    ;;
  project)
    ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    TARGET="$ROOT/.claude/settings.local.json"
    ;;
  *)
    usage
    ;;
esac

echo "Setting $VAR_NAME in $TARGET (scope: $SCOPE)."
read -r -s -p "Value (input hidden, never echoed or logged): " VALUE
echo
if [ -z "$VALUE" ]; then
  echo "Empty value -- aborted, nothing written." >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
python3 - "$TARGET" "$VAR_NAME" "$VALUE" <<'PYEOF'
import json, os, sys

target, var, value = sys.argv[1:4]
data = {}
if os.path.isfile(target):
    with open(target) as f:
        data = json.load(f) or {}
data.setdefault("env", {})[var] = value
with open(target, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF

echo "$VAR_NAME written to $TARGET's env. Restart Claude Code for it to take effect."
