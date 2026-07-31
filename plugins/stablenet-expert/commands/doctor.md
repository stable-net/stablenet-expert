---
name: stablenet-expert:doctor
description: Ecosystem health check for the stablenet-expert marketplace — is every published plugin installed and enabled, and do any two currently-enabled plugins register the same MCP server under different names (which leaves one silently disconnected all session).
allowed-tools: Bash, Read
argument-hint: ""
---

Run both diagnostic checks and report a consolidated status. Read-only — this command never
modifies `settings.json` or any plugin.

## Step 1: Run the checks

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-plugins.sh"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-mcp-conflicts.sh"
```

Each line is `name | status | detail`, `status` one of `pass`/`info`/`warn`/`critical`.

## Step 2: Report

```
# stablenet-expert doctor

## Plugins
<one line per plugin from check-plugins.sh, or "✓ all installed and enabled" if ALL_PLUGINS_PASS>

## MCP server conflicts
<one line per conflict from check-mcp-conflicts.sh, or "✓ no conflicts" if ALL_MCP_CONFLICTS_PASS>
```

For any `critical` MCP conflict, be explicit about the fix: disable all but one of the named
plugins (`~/.claude/settings.json`'s `enabledPlugins`, or a project-local
`.claude/settings.local.json` override to scope it to one project directory) and restart the
session. Point at `docs/SETUP.md` §9.9 for the full explanation.

## Known limitations (say so if relevant, don't silently omit)

- Both checks read only the **global** `~/.claude/settings.json` — a project-local
  `.claude/settings.local.json` override (e.g. disabling a plugin for just one project directory)
  is not accounted for, so this can report a conflict that's actually already worked around
  locally. Don't treat a `critical` as unconditionally wrong if the user says they've already
  scoped it per-project — just note the check doesn't see that layer.
- `check-plugins.sh`'s plugin list comes from this repo's own `.claude-plugin/marketplace.json` —
  it only knows about `stablenet-expert`'s own plugins, not `coding-agent` or any other
  marketplace's.
