#!/usr/bin/env bash
# check-mcp-conflicts.sh — detect two *enabled* plugins registering the same underlying
# MCP server (same resolved command/args, or same resolved HTTP URL) under different
# plugin/server names. Claude Code appears to dedup/conflict by the resolved connection
# rather than by plugin+server-name, so this leaves one plugin's copy silently
# disconnected all session (see docs/SETUP.md §9.9 — this automates that manual finding,
# not present in references/midnight-expert's doctor since that ecosystem doesn't share
# servers across plugins the way coding-agent/core-dev do).
set -u

emit() {
  local name="$1" status="$2" detail="$3"
  detail="$(printf '%s' "$detail" | tr '\n' ';' | sed 's/  */ /g; s/; */; /g; s/; $//')"
  printf '%s | %s | %s\n' "$name" "$status" "$detail"
}

INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
SETTINGS="$HOME/.claude/settings.json"

if ! command -v python3 >/dev/null 2>&1; then
  emit "check-mcp-conflicts" "warn" "python3 not available — cannot run this check"
  exit 0
fi
if [ ! -f "$INSTALLED_PLUGINS" ]; then
  emit "Plugin registry" "critical" "~/.claude/plugins/installed_plugins.json not found"
  exit 0
fi
if [ ! -f "$SETTINGS" ]; then
  emit "Settings file" "critical" "~/.claude/settings.json not found"
  exit 0
fi

python3 - "$INSTALLED_PLUGINS" "$SETTINGS" <<'PYEOF'
import json, os, re, sys
from collections import defaultdict

installed_path, settings_path = sys.argv[1:3]

installed = json.load(open(installed_path)).get("plugins", {})
settings = json.load(open(settings_path))
enabled_map = settings.get("enabledPlugins", {})
env = dict(settings.get("env", {}))

def emit(name, status, detail):
    print(f"{name} | {status} | {detail}")

def resolve(s, plugin_root):
    if not isinstance(s, str):
        return s
    def sub(m):
        var = m.group(1)
        if var == "CLAUDE_PLUGIN_ROOT":
            return plugin_root
        return env.get(var, os.environ.get(var, m.group(0)))
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, s)

# identity -> list of (plugin_key, server_alias)
registry = defaultdict(list)
checked = 0

for key, enabled in enabled_map.items():
    if not enabled:
        continue
    entries = installed.get(key, [])
    if not entries:
        continue
    plugin_root = entries[0].get("installPath", "")
    mcp_path = os.path.join(plugin_root, ".mcp.json")
    if not os.path.isfile(mcp_path):
        continue
    try:
        servers = json.load(open(mcp_path)).get("mcpServers", {})
    except Exception as e:
        emit(f"MCP conflict: {key}", "warn", f".mcp.json unreadable: {e}")
        continue
    for alias, cfg in servers.items():
        checked += 1
        if cfg.get("type") == "http":
            identity = ("http", resolve(cfg.get("url", ""), plugin_root))
        else:
            identity = ("cmd", resolve(cfg.get("command", ""), plugin_root),
                        tuple(resolve(a, plugin_root) for a in cfg.get("args", [])))
        registry[identity].append((key, alias))

if checked == 0:
    emit("MCP conflict check", "info", "no enabled plugin registers any MCP server")
else:
    conflicts = {ident: entries for ident, entries in registry.items()
                 if len({k for k, _ in entries}) > 1}
    if not conflicts:
        emit("ALL_MCP_CONFLICTS_PASS", "pass",
             f"{checked} server registration(s) across enabled plugins, no duplicates")
    else:
        for ident, entries in conflicts.items():
            names = ", ".join(f"{k}:{a}" for k, a in entries)
            target = ident[1] if ident[0] == "http" else ident[1]
            emit("MCP conflict", "critical",
                 f"{names} all resolve to the same server ({target}) — enabling these "
                 "plugins together leaves one silently disconnected all session; "
                 "disable all but one (see docs/SETUP.md §9.9)")
PYEOF
