#!/usr/bin/env bash
# scripts/contract/lint-tool-names.sh — C1 tool-name drift gate (M2.a).
#
# Asserts that every `mcp__<server>__<tool>` reference in the plugin's agent
# and command prompts names a tool present in the C1 SSoT schema
# (scripts/contract/agent-mcp.schema.json). This catches shim/renamed/hallucinated
# tool names before they reach a running agent.
#
# Usage:
#   scripts/contract/lint-tool-names.sh                # exit 1 on any drift
#   scripts/contract/lint-tool-names.sh --report-only  # always exit 0, just print drift
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCHEMA="${DIR}/scripts/contract/agent-mcp.schema.json"

REPORT_ONLY=0
[[ "${1:-}" == "--report-only" ]] && REPORT_ONLY=1

if [[ ! -f "$SCHEMA" ]]; then
  echo "lint: schema not found: $SCHEMA" >&2
  exit 2
fi

python3 - "$SCHEMA" "$REPORT_ONLY" "${DIR}/plugins/stablenet-core-dev/agents" "${DIR}/plugins/stablenet-core-dev/commands" <<'PY'
import sys, json, re, os, glob

schema_path = sys.argv[1]
report_only = sys.argv[2] == "1"
dirs = sys.argv[3:]

with open(schema_path) as fh:
    schema = json.load(fh)

names = set()
for prov in schema["providers"].values():
    names.update(prov["tools"].keys())

# Match mcp__<server>__<tool>; the tool segment may contain dots (e.g.
# mcp__plugin_stablenet-core-dev_stablenet-knowledge__cks_context_get_for_task —
# the server label is ours, the registered tool names keep their cks_* prefix).
token = re.compile(r'mcp__[A-Za-z0-9_-]+__([A-Za-z0-9_.]+)')

unknown = []
seen = 0
for d in dirs:
    for path in sorted(glob.glob(os.path.join(d, "*.md"))):
        with open(path) as fh:
            for lineno, line in enumerate(fh, 1):
                for m in token.finditer(line):
                    seen += 1
                    name = m.group(1).rstrip(".")  # trailing dot would be a typo
                    if name not in names:
                        unknown.append((path, lineno, name))

if unknown:
    print(f"tool-name drift: {len(unknown)} reference(s) not in the C1 schema:")
    for path, lineno, name in unknown:
        rel = os.path.relpath(path, os.path.dirname(os.path.dirname(schema_path)))
        print(f"  {rel}:{lineno}  {name}")
    sys.exit(0 if report_only else 1)

print(f"OK: {seen} tool reference(s), all present in the C1 schema ({len(names)} tools).")
PY
