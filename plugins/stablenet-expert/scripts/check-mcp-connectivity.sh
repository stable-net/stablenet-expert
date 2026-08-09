#!/usr/bin/env bash
# check-mcp-connectivity.sh — for every *enabled* plugin's declared MCP server(s), verify the
# env it needs is actually configured (no missing/placeholder values) and the server is
# reachable: HTTP servers get a live connectivity probe, stdio servers get a
# binary-exists-and-executable check. This is orthogonal to check-mcp-conflicts.sh (which
# detects two plugins pointing at the *same* server) — this one asks "does each declared
# server actually work on its own", independent of any conflict. Doctor Step 2.
#
# Scans every *enabled* plugin regardless of which marketplace it came from (a foreign plugin's
# server can still be the thing a user is asking about), but reports the two differently: a
# problem with one of THIS marketplace's plugins is `critical` — Step 4 can delegate to its
# ADR-0014 setup.py — while a problem with a foreign plugin is `external`, reported and never
# offered as a fix. A foreign plugin ships no setup.py this command can call and Step 4's
# delegation is scoped to this marketplace, so a `critical` row for one turned into a checkbox
# that led nowhere (ADR-0019; observed live 2026-08-09 with a leftover coding-agent install).
#
# NEVER prints a resolved network address (URL/host/IP) — this script's stdout is Bash tool
# output that flows straight into the calling LLM's context/transcript, and an internal
# server's IP has no business being sent to an LLM API just because doctor ran. Every line
# below reports reachability by referencing the *env var name* that configures it, never the
# resolved value. See scripts/set-mcp-env.sh for how a missing/placeholder value actually gets
# set (outside this conversation, never through it).
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
  emit "check-mcp-connectivity" "warn" "no Python interpreter available -- cannot run this check"
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
import json, os, re, shutil, socket, sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

installed_path, settings_path = sys.argv[1:3]

installed = json.load(open(installed_path)).get("plugins", {})
settings = json.load(open(settings_path))
enabled_map = settings.get("enabledPlugins", {})
env = dict(settings.get("env", {}))

def emit(name, status, detail):
    print(f"{name} | {status} | {detail}")

MARKETPLACE = "stablenet-expert"

def owned(plugin_key):
    """Does this plugin come from the marketplace this command speaks for?

    Registry keys are `<plugin>@<marketplace>`, which is the only ownership signal available
    here -- and the right one: it needs no marketplace.json read and stays correct for a
    plugin published later. A key without an `@` cannot be ours."""
    return "@" in plugin_key and plugin_key.rsplit("@", 1)[1] == MARKETPLACE

PLACEHOLDER_RE = re.compile(r'^CHANGE-ME', re.IGNORECASE)
VAR_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def var_refs(template):
    """Names of ${VAR} refs in an unresolved template string, for referring to a config value
    by name in output without ever resolving/printing it."""
    if not isinstance(template, str):
        return []
    return [v for v in VAR_REF_RE.findall(template) if v != "CLAUDE_PLUGIN_ROOT"]

def resolve(s, plugin_root):
    """Resolve ${VAR} refs (env then os.environ); collect names that are missing or still a
    CHANGE-ME placeholder so the caller can report exactly what to configure."""
    if not isinstance(s, str):
        return s, []
    missing = []
    def sub(m):
        var = m.group(1)
        if var == "CLAUDE_PLUGIN_ROOT":
            return plugin_root
        val = env.get(var, os.environ.get(var))
        if val is None:
            missing.append(var)
            return m.group(0)
        if PLACEHOLDER_RE.match(val):
            missing.append(f"{var} (still a CHANGE-ME placeholder)")
        return val
    resolved = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, s)
    return resolved, missing

owned_checked = 0
owned_pass = True

def problem(key, label, detail):
    """Emit a non-pass row for `label`, scoped by ownership.

    Returns True when the row counts against this marketplace's verdict -- i.e. only for our
    own plugins. A foreign plugin's broken server is reported (the diagnosis is still useful:
    it is often exactly what the user is asking about) but is neither a failure of this
    ecosystem nor something Step 4 can repair."""
    if owned(key):
        emit(label, "critical", detail)
        return True
    emit(label, "external",
         f"{detail} -- {key} is not a {MARKETPLACE} plugin, so this check reports it but "
         "cannot configure it; use that plugin's own setup, or disable it if it is a leftover")
    return False

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
        if problem(key, f"MCP connectivity: {key}", f".mcp.json unreadable: {e}"):
            owned_pass = False
        continue

    for alias, cfg in servers.items():
        if owned(key):
            owned_checked += 1
        label = f"{key}:{alias}"
        missing = []

        if cfg.get("type") == "http":
            template = cfg.get("url", "")
            ref = ", ".join(var_refs(template)) or "a static URL in .mcp.json"
            url, m = resolve(template, plugin_root)
            missing += m
            if missing:
                if problem(key, label, f"env not configured: {', '.join(missing)}"):
                    owned_pass = False
                continue
            try:
                urlopen(Request(url, method="GET"), timeout=2)
                emit(label, "pass", f"reachable (configured via {ref})")
            except HTTPError:
                # server answered with an HTTP error status -- still means it's up
                emit(label, "pass", f"reachable, server responded (configured via {ref})")
            except (URLError, socket.timeout, OSError):
                # deliberately not including the exception text -- URLError/OSError messages
                # often embed the resolved host/IP, which must not reach this script's stdout
                if problem(key, label,
                           f"unreachable (configured via {ref}) -- connection failed; "
                           "double-check the value yourself (this check won't print it) and "
                           "that the server process is running"):
                    owned_pass = False
        else:
            cmd, m = resolve(cfg.get("command", ""), plugin_root)
            missing += m
            for a in cfg.get("args", []):
                _, m2 = resolve(a, plugin_root)
                missing += m2
            for v in (cfg.get("env") or {}).values():
                _, m3 = resolve(v, plugin_root)
                missing += m3
            if missing:
                if problem(key, label, f"env not configured: {', '.join(missing)}"):
                    owned_pass = False
                continue
            resolved_bin = cmd if os.path.isabs(cmd) else shutil.which(cmd)
            if resolved_bin and os.access(resolved_bin, os.X_OK):
                emit(label, "pass", f"{cmd} found and executable")
            else:
                if problem(key, label,
                           f"{cmd} not found or not executable -- has it been built?"):
                    owned_pass = False

# The verdict covers this marketplace's own servers only. Foreign servers were reported above
# as `external` rows and deliberately do not decide it -- otherwise a leftover plugin from an
# unrelated marketplace would keep this ecosystem permanently "failing" for a reason no fix
# offered here could ever clear.
if owned_checked == 0:
    emit("MCP connectivity check", "info",
         f"no enabled {MARKETPLACE} plugin registers any MCP server")
elif owned_pass:
    emit("ALL_MCP_CONNECTIVITY_PASS", "pass",
         f"{owned_checked} server(s) configured and reachable")
PYEOF
