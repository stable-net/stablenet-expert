---
name: doctor
description: Ecosystem health check for the stablenet-expert marketplace — common toolchain prerequisites, plugin install/enable status, per-server MCP connectivity, and cross-plugin MCP server registration conflicts — with interactive, multi-select fixes and delegation to each installed plugin's own /<plugin>:setup for environment configuration.
allowed-tools: Bash, Read, Skill, AskUserQuestion
argument-hint: ""
---

Diagnose the stablenet-expert plugin ecosystem, then walk through fixes interactively. Per
[ADR-0012](../../../docs/adr/ADR-0012-doctor-step-order-revision.md) (which supersedes
[ADR-0011](../../../docs/adr/ADR-0011-stablenet-expert-doctor-interactive-setup.md)'s step order
but keeps its delegation principle): this command owns marketplace-level and ecosystem-wide fixes
directly (toolchain gaps, plugin install/enable, MCP conflicts), but never reimplements a
plugin's own environment setup — it delegates to that plugin's `/<plugin>:setup` if one exists.

**Never print, echo, or paste a resolved MCP connection value (URL, IP, hostname, token) into
this conversation, at any step below.** A Bash tool call's output becomes part of this
conversation's context — an internal server's address has no more business there than a
password would. Report configuration status by referring to the *env var name*, never the
value it resolves to. See Step 2/4 for how this plays out concretely.

Six steps, run in order:

## Step 0: Common environment check

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-environment.sh"
```

This is a **flat, ecosystem-wide** check — Go/C toolchain/Node/git/gh/python3/Ollama+bge-m3 (the
same list as `docs/SETUP.md` §1) — not broken down per plugin. It runs unconditionally,
regardless of which plugins are installed, because these are shared prerequisites the whole
marketplace draws from, not any one plugin's private dependency.

Report:

```
## Environment
<one line per tool from check-environment.sh, or "✓ all common prerequisites present" if ALL_ENVIRONMENT_PASS>
```

## Step 1: Plugin install status

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-plugins.sh"
```

Report:

```
## Plugins
<one line per plugin from check-plugins.sh, or "✓ all installed and enabled" if ALL_PLUGINS_PASS>
```

## Step 2: MCP connectivity check

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-mcp-connectivity.sh"
```

For every MCP server declared by a currently **enabled** plugin: is its required env actually
configured (no missing or still-`CHANGE-ME` values), and is it reachable (HTTP: live connectivity
probe; stdio: binary exists and is executable)? This is independent of Step 5 — a server can be
perfectly configured and reachable and *still* conflict with another plugin's identical
registration, which Step 5 alone checks.

`check-mcp-connectivity.sh` never resolves-and-prints a URL/IP in its output — it reports
`"reachable (configured via STABLENET_KNOWLEDGE_MCP_URL)"`, not the resolved address itself.
Print its output verbatim; don't "helpfully" resolve the referenced env var yourself and paste
the value into your report — that reintroduces exactly the leak the script avoids.

Report:

```
## MCP connectivity
<one line per server from check-mcp-connectivity.sh, or "✓ all declared servers configured and reachable" if ALL_MCP_CONNECTIVITY_PASS>
```

## Step 3: Confirm what to fix

Collect every actionable (non-`pass`) row from Steps 0-2 into **one** `AskUserQuestion` call with
`multiSelect: true` — a checkbox list, not a sequence of yes/no prompts. This is a selection-only
step: nothing is installed or changed yet, you're only finding out which of the outstanding items
the user wants handled this session. Options map 1:1 to the outstanding rows, phrased as the
concrete action, e.g.:

- `Install core-dev@stablenet-expert` (from a Step 1 `info` row)
- `Enable contract-dev` (from a Step 1 `info` row: installed but not enabled)
- `Pull the bge-m3 model (ollama pull bge-m3)` (from a Step 0 `warn` row)
- `Walk me through setting JIRA_API_TOKEN` (from a Step 2 `critical` row — see Step 4 for why
  this always means "point at `set-mcp-env.sh`", never "type the value here")

If Steps 0-2 were all `pass`, skip straight to Step 5 — there's nothing to select.

**Don't include Step 5's MCP conflict rows here.** Conflict resolution is a pick-one-of-several
decision (see Step 5), not an independent yes/no toggle, and it can only be evaluated correctly
after Step 4's installs/enables land — a plugin install in Step 4 can itself create a conflict
that doesn't exist yet at Step 3.

## Step 4: Apply what was selected

Process each item the user selected in Step 3, grouped by what it actually is — these are
different kinds of actions with different safety profiles, don't treat them uniformly:

- **Plugin install/enable** (Step 1 items): run `claude plugin install <plugin>@stablenet-expert`
  or `claude plugin enable <plugin>@stablenet-expert` directly — safe, user-scoped, reversible via
  uninstall/disable.
- **`ollama pull bge-m3`** (Step 0 item, if selected): safe to run directly — user-scoped, purely
  additive.
- **Any other Step 0 toolchain gap** (missing Go/Node/git/gh/C toolchain): **do not** auto-run a
  system package manager on the user's behalf — installing system-wide tooling is exactly the
  kind of hard-to-reverse, environment-affecting action that needs its own explicit confirmation,
  not a bulk multi-select nod. Print the platform-appropriate install command (from
  `docs/SETUP.md` §1) and let the user run it themselves.
- **MCP env not configured** (Step 2 `critical` items — `JIRA_API_TOKEN`,
  `STABLENET_KNOWLEDGE_MCP_URL`, `CKS_MCP_URL`, anything else naming a URL/IP/token): `set-mcp-env.sh`
  only covers the *mechanics* of persisting a value — it says nothing about where that value
  actually comes from, and this command has no business hardcoding that (it's exactly the
  domain knowledge ADR-0011 §2.2 says belongs to the owning plugin, not here). Before pointing
  at `set-mcp-env.sh`, check whether the owning plugin has its own `/<plugin>:setup` and, if so,
  invoke it (e.g. `Skill(skill: "core-dev:setup", args: "--check")`) — its report is expected to
  say where to obtain each missing value (`core-dev/scripts/setup.py`'s `REQUIRED` table carries
  a `how-to-find` hint per key for exactly this reason). Fold that guidance into what you tell
  the user, then point at `set-mcp-env.sh` for the actual write. If the owning plugin has no
  setup command, say plainly that you don't have "where to get this" guidance to offer and the
  user will need to know the value already (or check that plugin's own README/docs).

  Never ask the user to type the value itself into `AskUserQuestion` or into a Bash command
  you'll run — both put it straight into this conversation. Instead, point them at
  `scripts/set-mcp-env.sh`, and be explicit that **they** run it, not you:

  ```
  Run this yourself, in your own terminal (don't ask me to run it, and don't paste the value
  here — either would put it in this conversation):

      bash "<CLAUDE_PLUGIN_ROOT-for-the-owning-plugin>/scripts/set-mcp-env.sh" STABLENET_KNOWLEDGE_MCP_URL

  Add `--scope project` to scope it to this project only (writes the gitignored
  `.claude/settings.local.json` instead of the global `~/.claude/settings.json`). It prompts
  with hidden input and never echoes the value back — that's the only "input field" this value
  should ever go through.
  ```

  Never run `set-mcp-env.sh` yourself via the Bash tool — its whole point is a channel that
  bypasses this conversation, and invoking it as a tool call would put its prompt/stdin/stdout
  right back into that same conversation.

**Setup delegation only works for a plugin whose commands were already registered when this
session started** — Claude Code reads a plugin's `commands/`/`skills/` at session startup, not
live, so a plugin installed or enabled *during this same doctor run* has no invokable
`/<plugin>:setup` (or `Skill(skill: "<plugin>:setup", ...)`) until the session restarts.
Confirmed live (2026-08-04): invoking it right after an install fails with
`Unknown skill: <plugin>:setup`, not a graceful "not ready yet" — so don't attempt it. Branch on
whether the plugin was already `pass` in Step 1 **before** this run touched it:

- **Already installed+enabled before this run** (a pre-existing `pass` row, or one you didn't
  touch in Step 4): its commands were registered at session start, so delegation is safe right
  now. Check whether it ships `commands/setup.md` (`Read` `<installPath>/commands/setup.md` —
  `installPath` is in `~/.claude/plugins/installed_plugins.json`) and, if so, ask: "`<plugin>`
  has its own environment setup — run it now?" → yes invokes
  `Skill(skill: "<plugin>:setup", args: "--check")` and folds that skill's own report into this
  command's output verbatim (don't summarize or reinterpret it — it's that plugin's authoritative
  diagnosis, per ADR-0011 §2.2: this command has no MCP/env knowledge of any other plugin's
  requirements).
- **Installed or enabled by Step 4 in this same run**: do **not** attempt the Skill invocation —
  it will fail. Instead say plainly: "`<plugin>` was just installed — restart Claude Code, then
  run `/<plugin>:setup` yourself (or re-run `/stablenet-expert:doctor` after restarting, and
  delegation will work on that pass since the plugin will then already be registered)."

This is per-plugin, done as each plugin is processed — not a separate pass over every enabled
plugin at the end.

If a fix requires a session restart to take effect (plugin install/enable, `enabledPlugins`
changes — which is every case above where delegation was deferred), say so plainly and don't
claim it's "done" until the user confirms they've restarted.

## Step 5: MCP dual-registration conflict check

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-mcp-conflicts.sh"
```

Run this last, after Step 4's installs/enables have landed, since a fix applied in Step 4 can
itself introduce a conflict that didn't exist before it. Report:

```
## MCP server conflicts
<one line per conflict from check-mcp-conflicts.sh, or "✓ no conflicts" if ALL_MCP_CONFLICTS_PASS>
```

For each conflict (`critical` row, naming two-or-more `plugin:server` pairs pointing at the same
resolved endpoint): this is **not** a case of a server being unable to handle multiple plugins —
shared MCP servers with many concurrent clients are completely normal. It's that Claude Code
deduplicates MCP server *declarations* by resolved endpoint (not by name), and only the
highest-precedence one (local > project > user > plugin-provided > connector) actually connects —
see `docs/SETUP.md` §9.9. When two plugin-provided declarations tie at that precedence level,
which one wins isn't something to rely on, so ask explicitly via `AskUserQuestion`: "`<A>` and
`<B>` both register the same MCP server — which do you want to keep enabled?" (options: each named
plugin, or "leave as-is"). Selecting one disables the others via `~/.claude/settings.json`'s
`enabledPlugins` (set the non-selected ones to `false`). Never guess which one the user wants.

Finish with a summary:

```
### Summary
- Fixed this session: <N> (or "none")
- Still needs attention: <N> — <what, and the exact next command>
- All clear: <list of checks that passed and needed nothing>
```

## Known limitations (say so if relevant, don't silently omit)

- `check-plugins.sh`/`check-mcp-conflicts.sh`/`check-mcp-connectivity.sh` read only the **global**
  `~/.claude/settings.json` — a project-local `.claude/settings.local.json` override (e.g.
  disabling a plugin, or supplying a real env value, for just one project directory) is not
  accounted for, so a `critical` row can be reported even when it's already worked around
  locally. Don't treat that as unconditionally wrong if the user says they've already scoped it
  per-project — just note the check doesn't see that layer.
- `check-plugins.sh`'s plugin list comes from this repo's own `.claude-plugin/marketplace.json` —
  it only knows about `stablenet-expert`'s own plugins, not `coding-agent` or any other
  marketplace's (even though `check-mcp-conflicts.sh`/`check-mcp-connectivity.sh` *do* see other
  marketplaces' enabled plugins, since they read `enabledPlugins` broadly).
- `check-mcp-connectivity.sh`'s HTTP reachability probe is a plain unauthenticated GET with a 2s
  timeout — any HTTP response (even an error status) counts as "reachable", since the goal is
  distinguishing "the server process is up" from "connection refused/timed out", not validating
  auth or protocol correctness.
- Step 4 delegation only works for plugins that ship `commands/setup.md` — a plugin without one is
  treated as needing no further setup, which is only true if it genuinely has none (see ADR-0011
  §2.2 for the "new plugins should write their own setup" expectation this rests on).
- `set-mcp-env.sh` only covers values referenced as `${VAR}` in a plugin's `.mcp.json` — a
  plugin that hardcodes a literal URL/IP in its own `.mcp.json` (instead of an env var
  reference) isn't something this command can fix; that plugin's `.mcp.json` itself needs
  fixing, which is a code change, not a doctor-time configuration step.
- `AskUserQuestion` requires at least 2 options per question — Step 3's multi-select checkbox
  only works when there are 2+ outstanding items. Confirmed live: with exactly one outstanding
  item, the multi-select call itself errors. If Steps 0-2 leave exactly one actionable item, ask
  about it as a plain two-option question (do it now / later) instead of forcing a multi-select
  with a single checkbox.
- Setup delegation (Step 4) cannot reach a plugin installed/enabled earlier in the *same* Step 4
  — see Step 4's branch on this. This isn't a workaround-able quirk, it's how Claude Code
  registers plugin commands (session-startup only), so don't try to be clever about retrying the
  Skill call within the same run — it will not succeed until after a restart.
