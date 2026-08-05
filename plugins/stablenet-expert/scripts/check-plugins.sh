#!/usr/bin/env bash
# check-plugins.sh — install/enable status of every published stablenet-expert plugin.
# Pattern ported from references/midnight-expert's plugins/midnight-expert/skills/doctor
# (check-plugins.sh), adapted: plugin list is read from .claude-plugin/marketplace.json
# instead of hardcoded, since this repo's own marketplace manifest is right here.
set -u

emit() {
  local name="$1" status="$2" detail="$3"
  detail="$(printf '%s' "$detail" | tr '\n' ';' | sed 's/  */ /g; s/; */; /g; s/; $//')"
  printf '%s | %s | %s\n' "$name" "$status" "$detail"
}

MARKETPLACE="stablenet-expert"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
SETTINGS="$HOME/.claude/settings.json"

# The installed marketplace clone (~/.claude/plugins/marketplaces/<name>/) is the real,
# production-accurate location — a plugin installed via `claude plugin install` runs from a
# standalone cache dir (~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/) that is NOT
# nested inside a full repo checkout, so deriving this path via `../../..` from this script's
# own location only ever worked when run directly from a git checkout during development, and
# silently broke the very first time this ran from an actual installed plugin (confirmed live
# 2026-08-03: it resolved to ~/.claude/plugins/cache/stablenet-expert/.claude-plugin/..., which
# doesn't exist). Prefer the installed marketplace clone; fall back to the checkout-relative
# path only for local dev/testing convenience.
MARKETPLACE_JSON="$HOME/.claude/plugins/marketplaces/$MARKETPLACE/.claude-plugin/marketplace.json"
if [ ! -f "$MARKETPLACE_JSON" ]; then
  CHECKOUT_JSON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd 2>/dev/null)/.claude-plugin/marketplace.json"
  [ -f "$CHECKOUT_JSON" ] && MARKETPLACE_JSON="$CHECKOUT_JSON"
fi

python_bin="${STABLENET_EXPERT_PYTHON:-python3}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  emit "check-plugins" "warn" "no Python interpreter available — cannot run this check"
  exit 0
fi

if [ ! -f "$MARKETPLACE_JSON" ]; then
  emit "marketplace.json" "critical" "$MARKETPLACE_JSON not found"
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

"$python_bin" - "$MARKETPLACE_JSON" "$INSTALLED_PLUGINS" "$SETTINGS" "$MARKETPLACE" <<'PYEOF'
import json, sys

marketplace_path, installed_path, settings_path, marketplace = sys.argv[1:5]

plugins = [p["name"] for p in json.load(open(marketplace_path))["plugins"]]
installed = json.load(open(installed_path)).get("plugins", {})
enabled_map = json.load(open(settings_path)).get("enabledPlugins", {})

def emit(name, status, detail):
    print(f"{name} | {status} | {detail}")

all_pass = True
for plugin in plugins:
    key = f"{plugin}@{marketplace}"
    entries = installed.get(key, [])
    if not entries:
        emit(plugin, "info", "not installed (install only what you need)")
        all_pass = False
        continue
    version = entries[0].get("version", "unknown")
    if not enabled_map.get(key, False):
        emit(plugin, "info", f"installed (v{version}) but not enabled")
        all_pass = False
        continue
    emit(plugin, "pass", f"v{version}")

if all_pass:
    emit("ALL_PLUGINS_PASS", "pass", "all stablenet-expert plugins installed and enabled")
PYEOF
