# stablenet-expert

The meta-plugin for the [`stablenet-expert`](../../README.md) marketplace. Named identically to
the marketplace itself, unlike every other plugin here — its job is to represent/diagnose the
marketplace as a whole, not one domain, so sharing the marketplace's own name reads as "the
plugin for this marketplace" rather than a redundant prefix.

## Scope

Three checks ([ADR-0010](../../docs/adr/ADR-0010-stablenet-expert-meta-plugin-design.md) +
[ADR-0011](../../docs/adr/ADR-0011-stablenet-expert-doctor-interactive-setup.md)):

1. **Plugin status** — is every plugin published in this marketplace's `marketplace.json`
   installed and enabled.
2. **MCP server conflicts** — do any two currently-*enabled* plugins register the identical
   underlying MCP server (same resolved command/args or HTTP URL) under different names. Claude
   Code appears to dedup/conflict by the resolved connection rather than by plugin+server-name, so
   this silently disconnects one of them for the whole session — see `docs/SETUP.md` §9.9 for the
   full story; this check automates that finding.
3. **Setup delegation** — which enabled plugins ship their own `/<plugin>:setup` for environment
   configuration (env vars, build artifacts). This plugin never reimplements that logic — it
   offers to run the other plugin's own setup and passes its report through unmodified.

For (1) and (2), `/stablenet-expert:doctor` offers interactive fixes (`AskUserQuestion` — never
applies anything silently): install/enable a plugin, or pick which side of an MCP conflict to keep
enabled. For (3) it offers to invoke the delegate and folds in whatever that plugin's own setup
reports; it never edits another plugin's environment directly.

No MCP server of its own — checking the very plugins that might be in conflict, while also
registering a server itself, would risk becoming part of the problem it's diagnosing. It reads
`~/.claude/settings.json`, `~/.claude/plugins/installed_plugins.json`, and each enabled plugin's
`.mcp.json`/`commands/setup.md` directly.

Deliberately narrow beyond that — no external CLI tool checks, npm registry checks, cross-plugin
doc reference validation, ecosystem-onboarding tooling, or issue automation. `stablenet-expert`
doesn't have an npm dependency surface, an external-repo onboarding workflow, or an
issue-automation need yet. Add any of that if/when it actually becomes necessary.

## Commands

| Command | What it does |
|---|---|
| `/stablenet-expert:doctor` | Runs all three checks, reports plugin status + MCP conflicts, offers interactive fixes, and offers to delegate to each installed plugin's own setup check. |

## Install

```bash
claude plugin install --scope user stablenet-expert@stablenet-expert
```
