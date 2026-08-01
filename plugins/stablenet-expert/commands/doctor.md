---
name: stablenet-expert:doctor
description: Ecosystem health check for the stablenet-expert marketplace — plugin install/enable status, cross-plugin MCP server registration conflicts — with interactive fixes and delegation to each installed plugin's own /<plugin>:setup for environment configuration.
allowed-tools: Bash, Read, Skill, AskUserQuestion
argument-hint: ""
---

Diagnose the stablenet-expert plugin ecosystem, then walk through fixes interactively. Per
[ADR-0011](../../../docs/adr/ADR-0011-stablenet-expert-doctor-interactive-setup.md): this command
owns marketplace-level fixes (installing/enabling plugins, resolving MCP conflicts) directly, but
never reimplements a plugin's own environment setup — it delegates to that plugin's `/<plugin>:setup`
if one exists.

## Step 1: Run the checks

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-plugins.sh"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-mcp-conflicts.sh"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-setup-delegates.sh"
```

Each line is `name | status | detail`. `check-plugins`/`check-mcp-conflicts` use
`pass`/`info`/`warn`/`critical`; `check-setup-delegates` uses `delegate`/`info`.

## Step 2: Report

```
# stablenet-expert doctor

## Plugins
<one line per plugin from check-plugins.sh, or "✓ all installed and enabled" if ALL_PLUGINS_PASS>

## MCP server conflicts
<one line per conflict from check-mcp-conflicts.sh, or "✓ no conflicts" if ALL_MCP_CONFLICTS_PASS>
```

Don't print `check-setup-delegates.sh`'s raw output here — it's an input to Step 4, not a report
section (per-plugin setup status is that plugin's own `doctor`/`setup`'s business, not this one's).

## Step 3: Offer fixes for what this command owns

For each issue found in Step 1, ask about it individually via `AskUserQuestion` (don't batch
unrelated fixes into one question) — **never apply any of these silently**, they're all
user-curated decisions:

- **Plugin not installed** (`info` row): "Install `<plugin>@stablenet-expert`?" → yes runs
  `claude plugin install <plugin>@stablenet-expert`.
- **Plugin installed but not enabled** (`info` row): "Enable `<plugin>`?" → yes runs
  `claude plugin enable <plugin>@stablenet-expert`.
- **MCP conflict** (`critical` row, names two-or-more `plugin:server` pairs): "`<A>` and `<B>` both
  register the same MCP server — which do you want to keep enabled?" (options: each named plugin,
  or "leave as-is"). Selecting one disables the others via
  `~/.claude/settings.json`'s `enabledPlugins` (set the non-selected ones to `false`). Never guess
  which one the user wants — this is exactly the kind of decision `docs/SETUP.md` §9.9 says a
  human must make.

If a fix requires a session restart to take effect (plugin install/enable, `enabledPlugins`
changes), say so plainly and don't claim it's "done" until the user confirms they've restarted.

## Step 4: Offer to delegate per-plugin setup checks

For each `delegate` row from `check-setup-delegates.sh`: "`<plugin>` has its own environment setup
— check it now?" → yes invokes `Skill(skill: "<plugin>:setup", args: "--check")` and folds that
skill's own report into this command's output verbatim (don't summarize or reinterpret it — it's
that plugin's authoritative diagnosis). If it reports missing configuration, tell the user the
exact command to run (e.g. `/core-dev:setup --fix`) rather than attempting to fix it here — this
command has no MCP/env knowledge of any other plugin's requirements (ADR-0011 §2.2).

For each `info` row (no setup command), report "`<plugin>`: no environment setup needed" and move
on — nothing to offer.

## Step 5: Re-verify and summarize

After applying any fix from Step 3, re-run only the check(s) that had issues (not the full Step 1)
to confirm resolution. Present:

```
### Summary
- Fixed this session: <N> (or "none")
- Still needs attention: <N> — <what, and the exact next command>
- All clear: <list of checks that passed and needed nothing>
```

## Known limitations (say so if relevant, don't silently omit)

- `check-plugins.sh`/`check-mcp-conflicts.sh` read only the **global** `~/.claude/settings.json` —
  a project-local `.claude/settings.local.json` override (e.g. disabling a plugin for just one
  project directory) is not accounted for, so a `critical` MCP conflict can be reported even when
  it's already worked around locally. Don't treat that as unconditionally wrong if the user says
  they've already scoped it per-project — just note the check doesn't see that layer.
- `check-plugins.sh`'s plugin list comes from this repo's own `.claude-plugin/marketplace.json` —
  it only knows about `stablenet-expert`'s own plugins, not `coding-agent` or any other
  marketplace's (even though `check-mcp-conflicts.sh` *does* detect conflicts against
  other-marketplace plugins like `coding-agent`, since it reads `enabledPlugins` broadly).
- Delegation (Step 4) only works for plugins that ship `commands/setup.md` — a plugin without one
  is reported as needing no setup, which is only true if it genuinely has none (see ADR-0011 §2.2
  for the "new plugins should write their own setup" expectation this rests on).
