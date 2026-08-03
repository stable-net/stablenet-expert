# stablenet-expert

The meta-plugin for the [`stablenet-expert`](../../README.md) marketplace. Named identically to
the marketplace itself, unlike every other plugin here — its job is to represent/diagnose the
marketplace as a whole, not one domain, so sharing the marketplace's own name reads as "the
plugin for this marketplace" rather than a redundant prefix.

## Scope

Four checks, run as six steps
([ADR-0010](../../docs/adr/ADR-0010-stablenet-expert-meta-plugin-design.md) +
[ADR-0012](../../docs/adr/ADR-0012-doctor-step-order-revision.md), which supersedes
[ADR-0011](../../docs/adr/ADR-0011-stablenet-expert-doctor-interactive-setup.md)):

0. **Common environment** — the flat, ecosystem-wide toolchain prerequisites (Go/C
   toolchain/Node/git/gh/python3/Ollama+bge-m3, same list as `docs/SETUP.md` §1), checked
   unconditionally regardless of which plugins are installed — not broken down per plugin.
1. **Plugin status** — is every plugin published in this marketplace's `marketplace.json`
   installed and enabled.
2. **MCP connectivity** — for every MCP server a currently-*enabled* plugin declares: is its
   required env actually configured (no missing/placeholder values), and is it reachable. Never
   prints the resolved value (URL/IP/token) — only which env var it's configured through, since
   that output becomes part of this conversation's context and an internal address has no
   business there.
3. **MCP server conflicts** — do any two currently-*enabled* plugins register the identical
   underlying MCP server (same resolved command/args or HTTP URL) under different names. Claude
   Code deduplicates MCP server declarations by resolved endpoint rather than by
   plugin+server-name, and only the highest-precedence one connects — see `docs/SETUP.md` §9.9
   for the full story; this check automates that finding. Run last, after any installs/enables
   from this session, since those can themselves introduce a conflict that didn't exist before.

Steps 3 (decide) and 4 (execute) are split: Step 3 collects every outstanding item from Steps
0-2 into one `AskUserQuestion` multi-select (checkbox) prompt — nothing changes yet, it's
selection only. Step 4 then applies whatever was selected: plugin install/enable and
`ollama pull bge-m3` run directly (safe, reversible); other toolchain gaps get the install
command printed, not auto-run (a system-wide, hard-to-reverse change needs its own explicit
confirmation); missing MCP env gets pointed at `scripts/set-mcp-env.sh` — a script the *user*
runs themselves, directly in their own terminal, that prompts for the value with hidden input
and writes it straight into `~/.claude/settings.json` (or a project-scoped, gitignored
`.claude/settings.local.json`). This plugin never asks for the value through chat and never
runs that script on the user's behalf — either would put a network address or secret into the
conversation, which is the whole problem it exists to avoid. As each plugin is installed/enabled
in Step 4, if it ships its own
`/<plugin>:setup`, this plugin offers to invoke it and folds in that report unmodified — it
never reimplements another plugin's environment setup logic itself.

No MCP server of its own — checking the very plugins that might be in conflict, while also
registering a server itself, would risk becoming part of the problem it's diagnosing. It reads
`~/.claude/settings.json`, `~/.claude/plugins/installed_plugins.json`, and each enabled plugin's
`.mcp.json`/`commands/setup.md` directly.

Deliberately narrow beyond that — no npm registry checks, cross-plugin doc reference validation,
ecosystem-onboarding tooling, or issue automation. `stablenet-expert` doesn't have an npm
dependency surface, an external-repo onboarding workflow, or an issue-automation need yet. Add
any of that if/when it actually becomes necessary.

## Commands

| Command | What it does |
|---|---|
| `/stablenet-expert:doctor` | Runs all four checks (environment, plugins, MCP connectivity, MCP conflicts), lets you multi-select which outstanding items to fix, applies them, and delegates to each installed plugin's own setup check as it's processed. |

## Install

```bash
claude plugin install --scope user stablenet-expert@stablenet-expert
```
