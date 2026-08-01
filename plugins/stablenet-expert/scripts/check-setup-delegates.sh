#!/usr/bin/env bash
# check-setup-delegates.sh — for each enabled stablenet-expert plugin, report whether it
# ships its own /<plugin>:setup command. Gathers raw data only; the interactive delegation
# (asking the user, invoking the Skill) happens in commands/doctor.md, not here — a shell
# script can't drive AskUserQuestion/Skill tool calls (see ADR-0011 §2.2: this meta-plugin
# never reimplements a plugin's own env/setup logic, only points at it).
set -u

emit() {
  local name="$1" status="$2" detail="$3"
  detail="$(printf '%s' "$detail" | tr '\n' ';' | sed 's/  */ /g; s/; */; /g; s/; $//')"
  printf '%s | %s | %s\n' "$name" "$status" "$detail"
}

MARKETPLACE_JSON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/.claude-plugin/marketplace.json"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
SETTINGS="$HOME/.claude/settings.json"
MARKETPLACE="stablenet-expert"

if ! command -v python3 >/dev/null 2>&1; then
  emit "check-setup-delegates" "warn" "python3 not available — cannot run this check"
  exit 0
fi
for f in "$MARKETPLACE_JSON" "$INSTALLED_PLUGINS" "$SETTINGS"; do
  [ -f "$f" ] || { emit "$(basename "$f")" "critical" "$f not found"; exit 0; }
done

python3 - "$MARKETPLACE_JSON" "$INSTALLED_PLUGINS" "$SETTINGS" "$MARKETPLACE" <<'PYEOF'
import json, os, sys

marketplace_path, installed_path, settings_path, marketplace = sys.argv[1:5]

plugins = [p["name"] for p in json.load(open(marketplace_path))["plugins"]]
installed = json.load(open(installed_path)).get("plugins", {})
enabled_map = json.load(open(settings_path)).get("enabledPlugins", {})

def emit(name, status, detail):
    print(f"{name} | {status} | {detail}")

for plugin in plugins:
    key = f"{plugin}@{marketplace}"
    if not enabled_map.get(key, False):
        continue  # not enabled -- check-plugins.sh already reports this; nothing to delegate
    entries = installed.get(key, [])
    if not entries:
        continue
    root = entries[0].get("installPath", "")
    setup_path = os.path.join(root, "commands", "setup.md")
    if os.path.isfile(setup_path):
        emit(plugin, "delegate", f"has {plugin}:setup -- offer to run it")
    else:
        emit(plugin, "info", "no setup command -- nothing to configure")
PYEOF
