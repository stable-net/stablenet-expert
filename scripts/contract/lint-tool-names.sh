#!/usr/bin/env bash
# scripts/contract/lint-tool-names.sh — tool-name drift gate.
#
# Asserts that every `mcp__<server>__<tool>` reference in the plugin's agent
# and command prompts names a tool present in the schema
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

python3 - "$SCHEMA" "$REPORT_ONLY" "${DIR}/plugins" <<'PY'
import sys, json, re, os, glob

schema_path = sys.argv[1]
report_only = sys.argv[2] == "1"
plugins_root = sys.argv[3]

# Scan every plugin's agents/ and commands/, not just one hardcoded plugin —
# a plugin discovered here just by being a plugins/<name>/ directory, so a
# new plugin is covered automatically with no edit to this script.
dirs = sorted(
    d for pattern in ("*/agents", "*/commands")
    for d in glob.glob(os.path.join(plugins_root, pattern))
    if os.path.isdir(d)
)

with open(schema_path) as fh:
    schema = json.load(fh)

names = set()
for prov in schema["providers"].values():
    names.update(prov["tools"].keys())

# Match mcp__<server>__<tool>; the tool segment may contain dots (e.g.
# mcp__plugin_core-dev_stablenet-knowledge__cks_context_get_for_task —
# the server label is ours, the registered tool names keep their cks_* prefix)
# or be a bare server-level wildcard (mcp__plugin_core-dev_chainbench__*),
# which grants every tool on that server and is always valid — nothing to
# look up, since it isn't naming one specific tool.
token = re.compile(r'mcp__[A-Za-z0-9_-]+__([A-Za-z0-9_.]+|\*)')

unknown = []
seen = 0
wildcards = 0
for d in dirs:
    for path in sorted(glob.glob(os.path.join(d, "*.md"))):
        with open(path) as fh:
            for lineno, line in enumerate(fh, 1):
                for m in token.finditer(line):
                    name = m.group(1)
                    if name == "*":
                        wildcards += 1
                        continue
                    seen += 1
                    name = name.rstrip(".")  # trailing dot would be a typo
                    if name not in names:
                        unknown.append((path, lineno, name))

if unknown:
    print(f"tool-name drift: {len(unknown)} reference(s) not in the schema:")
    for path, lineno, name in unknown:
        rel = os.path.relpath(path, os.path.dirname(os.path.dirname(schema_path)))
        print(f"  {rel}:{lineno}  {name}")
    sys.exit(0 if report_only else 1)

print(f"OK: {seen} tool reference(s) + {wildcards} server-level wildcard grant(s), "
      f"all present in the schema ({len(names)} tools).")
PY
