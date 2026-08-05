#!/usr/bin/env bash
# check-mcp-conflicts.sh — detect two *enabled* plugins registering the same underlying
# MCP server (same resolved command/args, or same resolved HTTP URL) under different
# plugin/server names. Claude Code deduplicates MCP server declarations by resolved
# endpoint rather than by plugin+server-name, so this leaves one plugin's copy silently
# disconnected all session (see docs/SETUP.md §9.9 — this automates that manual finding,
# not present in references/midnight-expert's doctor since that ecosystem doesn't share
# servers across plugins the way coding-agent/core-dev do).
#
# HTTP identity is resolved internally (to actually detect the conflict) but NEVER printed —
# same reasoning as check-mcp-connectivity.sh: this script's stdout is Bash tool output that
# flows into the calling LLM's context, and an internal server's URL/IP has no business there.
# A resolved stdio command path is printed (it's a local file path, not a network address).
set -u

emit() {
  local name="$1" status="$2" detail="$3"
  detail="$(printf '%s' "$detail" | tr '\n' ';' | sed 's/  */ /g; s/; */; /g; s/; $//')"
  printf '%s | %s | %s\n' "$name" "$status" "$detail"
}

INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
SETTINGS="$HOME/.claude/settings.json"

python_bin="${STABLENET_EXPERT_PYTHON:-python3}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  emit "check-mcp-conflicts" "warn" "no Python interpreter available — cannot run this check"
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

"$python_bin" - "$INSTALLED_PLUGINS" "$SETTINGS" <<'PYEOF'
import json, os, re, sys
from collections import defaultdict

installed_path, settings_path = sys.argv[1:3]

installed = json.load(open(installed_path)).get("plugins", {})
settings = json.load(open(settings_path))
enabled_map = settings.get("enabledPlugins", {})
env = dict(settings.get("env", {}))

def emit(name, status, detail):
    print(f"{name} | {status} | {detail}")

VAR_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def var_refs(template):
    if not isinstance(template, str):
        return []
    return [v for v in VAR_REF_RE.findall(template) if v != "CLAUDE_PLUGIN_ROOT"]

def resolve(s, plugin_root):
    if not isinstance(s, str):
        return s
    def sub(m):
        var = m.group(1)
        if var == "CLAUDE_PLUGIN_ROOT":
            return plugin_root
        return env.get(var, os.environ.get(var, m.group(0)))
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, s)

# identity -> list of (plugin_key, server_alias, url_var_refs_or_None)
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
            template = cfg.get("url", "")
            identity = ("http", resolve(template, plugin_root))
            ref = ", ".join(var_refs(template)) or "a static URL"
        else:
            identity = ("cmd", resolve(cfg.get("command", ""), plugin_root),
                        tuple(resolve(a, plugin_root) for a in cfg.get("args", [])))
            ref = None
        registry[identity].append((key, alias, ref))

if checked == 0:
    emit("MCP conflict check", "info", "no enabled plugin registers any MCP server")
else:
    conflicts = {ident: entries for ident, entries in registry.items()
                 if len({k for k, _, _ in entries}) > 1}
    if not conflicts:
        emit("ALL_MCP_CONFLICTS_PASS", "pass",
             f"{checked} server registration(s) across enabled plugins, no duplicates")
    else:
        for ident, entries in conflicts.items():
            if ident[0] == "http":
                names = ", ".join(f"{k}:{a} (via {ref})" for k, a, ref in entries)
                emit("MCP conflict", "critical",
                     f"{names} all resolve to the same server — enabling these "
                     "plugins together leaves one silently disconnected all session; "
                     "disable all but one (see docs/SETUP.md §9.9)")
            else:
                names = ", ".join(f"{k}:{a}" for k, a, _ in entries)
                target = ident[1]
                emit("MCP conflict", "critical",
                     f"{names} all resolve to the same server ({target}) — enabling these "
                     "plugins together leaves one silently disconnected all session; "
                     "disable all but one (see docs/SETUP.md §9.9)")
PYEOF
