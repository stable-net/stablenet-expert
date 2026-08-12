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

**Credentials (tokens) must never enter this conversation**, whether printed or typed in —
those go through `set-mcp-env.sh`'s hidden-input prompt (Step 4), and nothing below overrides
that.

**Addresses and paths are not credentials, and the rule about them depends on which step you
are in.** #41 settled the direction — "addresses and paths are shown and asked for; credentials
are not" — and the two steps apply it differently:

- **Reporting status (Steps 0-2, and the final summary): name the variable, not its value.**
  A `pass` row needs no address to be informative, so resolving one into the transcript buys
  nothing. `check-mcp-connectivity.sh` already reports this way; print it verbatim rather than
  resolving the referenced variable yourself.
- **Configuring a value (Step 4): show `resolved_value` and let the user type a different one.**
  This is not the same act. Here the value *is* the subject of the question, and the user
  cannot judge a detected value they cannot see.

That distinction has to be stated because collapsing it broke the thing this file exists to do:
read as a blanket prohibition, it suppressed the Step 4 question's detected value **and** its
accept option, leaving *skip* and *do it yourself* — a question that cannot configure anything.
Whether the row is `missing` or already resolvable (`status: env`) makes no difference to which
step you are in.

Six steps, run in order:

## Step 0: Common environment check

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-environment.sh"
```

This is a **flat, ecosystem-wide** check — Go/C toolchain/git/gh/python3/Ollama+bge-m3, plus the
group security policy being installed *and imported* (the
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

The scan covers enabled plugins from **every** marketplace, not just this one, but grades them
differently (ADR-0019). A problem with one of this marketplace's plugins is `critical`. A
problem with a plugin from anywhere else is **`external`** — reported, because the diagnosis is
often exactly what the user is asking about, but never presented as something this command
fixes: it has no `setup.py` to delegate to (Step 4) and no business writing another
marketplace's env. Pass those rows through as information and say plainly that resolving them
means using that plugin's own setup, or disabling it if it is a leftover.

Report:

```
## MCP connectivity
<one line per server from check-mcp-connectivity.sh, or "✓ all declared servers configured and reachable" if ALL_MCP_CONNECTIVITY_PASS>
```

`ALL_MCP_CONNECTIVITY_PASS` covers this marketplace's servers only, so it can legitimately
appear alongside `external` rows. That is not a contradiction to smooth over — report both.

## Step 3: Confirm what to fix

Collect every actionable row from Steps 0-2 into **one** `AskUserQuestion` call with
`multiSelect: true` — a checkbox list, not a sequence of yes/no prompts. This is a selection-only
step: nothing is installed or changed yet, you're only finding out which of the outstanding items
the user wants handled this session. Options map 1:1 to the outstanding rows, phrased as the
concrete action, e.g.:

- `Install core-dev@stablenet-expert` (from a Step 1 `info` row)
- `Enable contract-dev` (from a Step 1 `info` row: installed but not enabled)
- `Pull the bge-m3 model (ollama pull bge-m3)` (from a Step 0 `warn` row)
- `Install Python 3.12 alongside your current interpreter` (from the Step 0 `python3` row —
  `critical` if none exists, `info` if one exists but predates 3.10)
- `Install and authenticate the Atlassian MCP plugin` (from a `row_kind: "plugin"` row — say
  that a browser opens for the OAuth consent)

**Actionable means: not `pass`, and not `external`.** An `external` row belongs to a plugin from
another marketplace — this command reports it (Step 2/Step 5) and stops there. Putting one on
the checkbox promises a repair that Step 4 cannot perform: its delegation is scoped to this
marketplace's plugins, and a foreign plugin ships no ADR-0014 `scripts/setup.py` to call. That
is not hypothetical — a leftover `coding-agent` install once put three unconfigured MCP servers
in front of a user as fixable items with nothing behind them (ADR-0019). Mention `external` rows
in the summary's *Left as-is*, never in this question.

**Every option label must name the action, and the question `header` must name the subject.** A
user reading a checkbox should not have to infer what installing is. `header: "Atlassian MCP"`
with a label starting `Install ...` — not a generic `header: "Setup"` with a label like
`Configure Jira`, which reads as a settings tweak rather than as installing a plugin into their
Claude Code and opening a browser.

**Pass the row's `description` through verbatim as the option description.** For a `plugin` row
it states what stops working if they decline; a shortened paraphrase turns an informed choice
into a blind one. Declining is legitimate — the free-text entry point needs no Jira — but only
when the cost is on screen.

If Steps 0-2 left nothing actionable, skip straight to Step 5 — there's nothing to select. A run
whose only non-`pass` rows are `external` counts as nothing to select: don't manufacture a
question out of them.

**Don't include Step 5's MCP conflict rows here.** Conflict resolution is a pick-one-of-several
decision (see Step 5), not an independent yes/no toggle, and it can only be evaluated correctly
after Step 4's installs/enables land — a plugin install in Step 4 can itself create a conflict
that doesn't exist yet at Step 3.

## Step 4: Apply what was selected

Process each item the user selected in Step 3, grouped by what it actually is — these are
different kinds of actions with different safety profiles, don't treat them uniformly:

- **Python install** (Step 0 `python3` row, if selected): **do this first, before any plugin
  install/enable.** The delegation later in this step runs a plugin's `scripts/setup.py`, so on a
  machine with no interpreter every other repair in this step is unavailable until this one lands
  (ADR-0015). Run:

  ```bash
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/install-python.sh" --install
  ```

  It is idempotent — if a suitable interpreter already exists it installs nothing and reports that
  one. On success the last stdout line is `INTERPRETER=<absolute path>`.

  Record that path as `STABLENET_EXPERT_PYTHON` under `env` in `~/.claude/settings.json`. This is
  a filesystem path, not a credential, so write it directly — the `set-mcp-env.sh` hidden-input
  route exists for secrets and does not apply here.

  Then, **for the remainder of this run**, substitute that absolute path wherever the steps below
  say `"$python_bin"`. Tell the user plainly that the hooks pick it up from the *next* session:
  Claude Code reads settings `env` at session start, so this run's already-loaded hooks keep using
  the interpreter they started with. Nothing is relinked and `PATH` is untouched, so there is
  nothing to undo later.
- **Plugin install/enable** (Step 1 items): run `claude plugin install <plugin>@stablenet-expert`
  or `claude plugin enable <plugin>@stablenet-expert` directly — safe, user-scoped, reversible via
  uninstall/disable.
- **`ollama pull bge-m3`** (Step 0 item, if selected): safe to run directly — user-scoped, purely
  additive.

  Only offer this when Ollama itself is present. When the Step 0 row says Ollama is *not
  installed*, pulling a model is not a step that exists yet — offer the install command instead
  (below) and say the model pull follows it. Offering a pull that cannot run is worse than
  offering nothing: it reads as an available fix.
- **`Security rules` (Step 0 `critical`)**: never fix this one. The file is organisation policy
  and this marketplace does not ship it — writing something plausible into
  `~/.claude/rules/SECURITY.md` would create a policy nobody approved, and adding the import
  line while the file is absent would load nothing while looking configured. Print what the row
  says and stop there.

  It is worth saying out loud which of the two failures the user has, because they read the
  same from a distance and are not the same problem. A missing file is visibly missing. A file
  that exists but is not imported looks installed while the rules are absent from every
  session — that is the one people do not think to check.
- **Any other Step 0 toolchain gap** (missing Go/Node/git/gh/C toolchain): **do not** auto-run a
  system package manager on the user's behalf — installing system-wide tooling is exactly the
  kind of hard-to-reverse, environment-affecting action that needs its own explicit confirmation,
  not a bulk multi-select nod. Print the platform-appropriate install command (from
  `docs/SETUP.md` §1) and let the user run it themselves.
- **A missing MCP server binary** (Step 2 `critical` row like `chainbench-mcp not found or not
  executable`): setting `CHAINBENCH_DIR` does not produce the binary, so writing the variable and
  stopping leaves the user with a configured path to nothing. Say what is actually missing and how
  it is built — `make` in the chainbench checkout, per `docs/SETUP.md` — and do not report the
  env row as resolved on its own. Building it is not run here for the same reason other toolchain
  installs are not: it is a build in a repository this command does not own.
- **MCP env not configured** (Step 2 `critical` items naming a URL/IP/token — e.g.
  `STABLENET_KNOWLEDGE_MCP_URL`, `CKS_MCP_URL`): where the value comes from is the owning
  plugin's knowledge, not this command's (ADR-0011 §2.2), so consult that plugin's own
  `/<plugin>:setup` for it — `core-dev/scripts/setup.py`'s `REQUIRED` table carries a
  `how-to-find` hint per key, surfaced as `how_to_find` in its `--check --json` (read in the
  delegation below). Fold that guidance into what you tell the user.

  **How the value is collected depends on what it is, and the owning plugin's `--check --json`
  says which — decide from its `secret`/`value_withheld` flags, never from the key name:**

  - **An address** (URL/IP/hostname endpoint, `secret: false`) is not a credential. Collect it
    the normal way — the per-server `AskUserQuestion` below, writing through
    `setup.py --fix --set KEY=VALUE`, which validates the shape (`validate.py`) and refuses
    anything that looks like a token. `STABLENET_KNOWLEDGE_MCP_URL` is this case: it is required,
    it is not secret, so it is asked for and written here rather than handed off.

    A user who would rather keep an internal address out of the transcript can run the same
    `setup.py --fix --set KEY=VALUE` themselves. Mention it **after** the options that collect
    the value, never in place of them: as the leading choice it reads as the recommended route
    and turns a question that configures the plugin into a question that hands the job back.
  - **A token** (`secret: true`, or `value_withheld: true`) must never enter this conversation.
    Point the user at `set-mcp-env.sh` and be explicit that **they** run it, not you:

    ```
    Run this yourself, in your own terminal (don't ask me to run it, and don't paste the value
    here — either would put it in this conversation):

        bash "${CLAUDE_PLUGIN_ROOT}/scripts/set-mcp-env.sh" <VAR_NAME>

    Add `--scope project` to scope it to this project only (writes the gitignored
    `.claude/settings.local.json` instead of the global `~/.claude/settings.json`). It prompts
    with hidden input and never echoes the value back — that's the only "input field" a secret
    should ever go through.
    ```

    `set-mcp-env.sh` belongs to *this* plugin, not to the one being configured, so the path uses
    `${CLAUDE_PLUGIN_ROOT}` (it resolves to `stablenet-expert`'s own directory while this command
    runs). Do not build it from the `$plugin_path` resolved earlier in this step: that points at
    whichever plugin is being set up, which does not ship this script, and the command then fails
    on a path that does not exist. The script is generic — it writes whatever `<VAR_NAME>` you
    pass — so this one copy handles a secret owned by any plugin. Never run `set-mcp-env.sh`
    yourself via the Bash tool — its whole point is a channel that bypasses this conversation, and
    invoking it as a tool call would put its prompt/stdin/stdout right back into that same
    conversation.

**Delegate by running the plugin's setup script, not by invoking its skill.** Claude Code
registers a plugin's `commands/`/`skills/` at session startup, so `Skill(skill: "<plugin>:setup")`
fails with `Unknown skill` for anything installed during this run (confirmed live 2026-08-04).
A script has no such constraint — `Bash` only needs a path, and `installPath` is written to
`~/.claude/plugins/installed_plugins.json` the moment the install completes. Per ADR-0014 every
plugin in this marketplace ships `scripts/setup.py` with `--check`, `--fix`, and `--json` for
exactly this reason, so **a plugin installed in Step 4 gets its setup in the same session.**

**Run this for every enabled plugin of this marketplace, not only the ones installed or
changed in this run.** Installation and configuration are different things: a plugin that has
been installed for weeks can still be missing a value, and an earlier version of this step only
delegated for plugins it had just touched — so a machine whose `core-dev` was already installed
got no setup questions at all, and the missing value stayed missing every time doctor ran. The
cost is one `--check --json` per plugin.

For each such plugin, resolve its path and check:

```bash
python_bin="${STABLENET_EXPERT_PYTHON:-python3}"
plugin_path=$("$python_bin" -c "import json,pathlib; print(json.load(open(pathlib.Path.home()/'.claude/plugins/installed_plugins.json'))['plugins']['<plugin>@stablenet-expert'][0]['installPath'])")
"$python_bin" "$plugin_path/scripts/setup.py" --check --json
```

The JSON carries one row per requirement: `key`, `row_kind`, `serves` (which MCP server it is
for), `description` (what the value is *for*), `how_to_find`, `status`, `resolved_value`,
`value_withheld`, `auto_fixable`, `opens_browser`, `secret`. That is the plugin's
own authoritative account of its requirements — this command has no env knowledge of any other
plugin (ADR-0011 §2.2) and must not second-guess it.

Read `not_ready` rather than `missing` when deciding whether the plugin is set up. They differ:
an external plugin that is installed but not authenticated is not "missing" and is not usable
either, so a caller checking only `missing` would call the setup done and send the user off to
restart into a pipeline that cannot read a ticket.

**Branch on `row_kind` first — the kinds are not interchangeable:**

- **`row_kind: "env"`** — a settings value. Handled by the three cases below.
- **`row_kind: "plugin"`** — an external Claude Code plugin this one depends on (today: the
  official Atlassian MCP, which is where the pipeline gets its ticket). Fixing it installs into
  the *user's* Claude Code and opens a browser for an OAuth consent, which is why the row
  carries `opens_browser`. Offer it in the same multi-select as the rest, but say in the option
  description that a browser will open — a consent window appearing unannounced is not a side
  effect to spring on someone. On confirmation, add `--with-plugins`:

  ```bash
  "$python_bin" "$plugin_path/scripts/setup.py" --fix --with-plugins
  ```

  `--fix` alone deliberately leaves external plugins untouched (it still *reports* them), so
  never pass `--with-plugins` for a row the user did not pick.

  The script re-reads the state from the CLI after acting instead of assuming the attempt
  worked, so trust what it prints. A `status` that comes back as anything other than
  `authenticated` means the consent was not completed — say so plainly in the Step 5 summary
  and repeat the command the script offers (`claude mcp login plugin:atlassian:atlassian`).
  Do not run that yourself: it needs a terminal, and a Bash tool call does not give it one.
  A `status` of `unknown` means the script could not consult the `claude` CLI at all — report
  that as a broken CLI, not as a missing plugin.

### How a typed value reaches you

Two channels exist and the question must offer **both**, because each one fails on its own.

- **"Other".** `AskUserQuestion` appends that entry itself and names it, and it is the only
  option that opens a text field directly. Name it in the question text, with the shape
  expected:

  > "…already know the address? Choose **Other** and type it (`http://host:port/mcp`)."

- **A named option that means "ask me for it".** `Other` is labelled `Other` and nothing else,
  so a user reading the list sees *leave it* and *I'll do it myself* and concludes there is no
  way to supply the value. That is not hypothetical: it was reported three times running, on
  three separate questions, while the question text said "choose Other" every time. Prose in
  the question does not relabel the option. So carry the entry path as an option too:

  ```
  - "I already know it — enter it here"
      → description: "Ask me in your next message; I'll give you the <address|path> and you
                      write it."
  ```

  **Label it as a statement about the user, not an instruction to them.** `Type the address
  here` reads as a command — *type something* — next to two options that are self-descriptions
  (*leave it*, *I'll do it myself*), so it scans as the odd one out rather than as the third
  answer. The option is chosen by people who **have** the value, and its label has to say that
  condition out loud: *I already know it*. The imperative phrasing was reported as
  "type whatever" and skipped for exactly this reason.

  **Selecting it returns the label, never a value.** That is real, and it is why an earlier
  version of this file banned such options outright — the wrong conclusion from a correct
  observation. The option is a *signal*, not a channel. When it comes back, treat it as a
  request: **end the turn with one plain sentence asking for the value, and nothing else.**
  The user's reply is an ordinary message, and the message box always renders. Then write it
  with `--set` and confirm from the script's own output.

  Never write the label into settings, never guess the value, and never re-ask with
  `AskUserQuestion` — that returns to the list the user just told you was insufficient.

This applies to every question that collects a value, including the project checkout. It applies
to none that collects a secret: a credential has no type-it-here path at all, only
`set-mcp-env.sh`.

### The three options every value question carries

Every tab that collects a value offers the **same three**, in this order, whatever the key is.
A question that drops one of them removes an answer somebody needs, and one that words them
differently per tab makes three questions look like three unrelated decisions:

```
options:
  - "I'll run the command myself"
      → "Prints the exact setup.py --set command and writes nothing now. Use this to keep the
         value out of this conversation."
  - "Skip for now"
      → "<what stops working, taken from the row's own description>"
  - "I already know it — enter it here"
      → "Ask me in your next message; I'll give you the <address|path> and you write it."
```

Add **one** more only when the script already resolved a value — `"Use the detected value"`,
first in the list, showing the value. That is the four-option ceiling `AskUserQuestion` allows,
which is why nothing else may be added.

Each option is a different person's answer, and none substitutes for another:

| | for someone who | why it cannot be dropped |
|---|---|---|
| run it myself | wants the value off the transcript, or prefers their own terminal | the only path for a value that is sensitive but not a credential |
| skip | is not using this server today | without it, the only way out is answering a question they cannot answer |
| already know it | has the value in hand | without it, the question collects nothing — the failure that was reported |

The entry option stays **last**: the first two are what someone declines with, and the one that
finishes the setup reads as the conclusion of the list rather than as an instruction opening it.

**What each branch does when it comes back:**

- `I'll run the command myself` — print the exact command, with the real key and real paths
  filled in, and **write nothing**. No placeholder the user has to decode:

  ```bash
  "$python_bin" "$plugin_path/scripts/setup.py" --fix --set STABLENET_KNOWLEDGE_MCP_URL=<address>
  ```

  Say that a restart is needed afterwards, and that `/stablenet-expert:doctor` will confirm it.
  Do not offer to run it for them — choosing this option is the statement that they will.
- `Skip for now` — record nothing, and in the Step 5 summary name what stays unavailable, from
  the row's own `description`. Never call the setup complete when a row was skipped.
- `I already know it — enter it here` — end the turn with one plain sentence asking for the
  value, per **How a typed value reaches you**. It returns its label, never a value.

### Unattended runs

`setup.py --autonomous` writes the granular `permissions.allow`/`deny` that let the pipeline run
to a PR without stopping. Nothing was invoking it, so every install produced an environment that
asked for confirmation at each edit, build and commit — the pipeline works, it just cannot be
left alone, which is most of the point of it.

Offer it whenever a plugin ships the flag and the project's `.claude/settings.local.json` has no
`permissions.allow` yet. It is its own tab, because it is a different decision from configuring
a server:

```
header:   "Unattended runs"
question: "core-dev asks before each edit, build and commit unless a granular allowlist is
           registered. Grant it? Destructive git (force-push, push to main, commit on main)
           stays denied by the git-guard hook either way, and merge/tag/release stay prompted."
options:
  - "Grant it"           → setup.py --autonomous
  - "Keep confirming"    (say this means a prompt per step)
```

Write it into the project, not the user scope — an allowlist is a statement about one
repository, and carrying it to every project is not what the user agreed to:

```bash
"$python_bin" "$plugin_path/scripts/setup.py" --autonomous
```

### Ask by MCP server, one tab each

Group every outstanding row — from all plugins — by **which MCP server it is for**, and put
each group in its own `AskUserQuestion` question. `AskUserQuestion` renders each `header` as a
tab, so several subjects cost one call.

**It accepts at most four questions per call, and there are five possible subjects** — the three
servers, the project checkout, and unattended runs. They rarely all apply at once, but when more
than four do, ask in two calls rather than dropping one: split them so the first call carries
what blocks the pipeline outright (a server with no endpoint, a checkout that was not pinned)
and the second carries the rest. Silently omitting a question leaves the user believing they
were asked about everything.

**Group on the row's `serves` field, never on the key name.** Each row says which server it is
for, because the plugin owns that knowledge and this command owns none of it (ADR-0011 §2.2) —
reading it out of `STABLENET_KNOWLEDGE_MCP_URL` here would be the guess that principle forbids,
and it would break the moment a plugin adds a second value for the same server.

| `serves` | `header` | Also in this tab |
|---|---|---|
| `atlassian` | `Atlassian MCP` | — |
| `stablenet-knowledge` | `Knowledge MCP` | — |
| `chainbench` | `Chainbench MCP` | the `chainbench-mcp` binary, if Step 2 reported it missing |

`serves: null` means the row belongs to no server. Do not invent a tab for it — see below.

Grouping by server rather than by fix-kind is what makes the questions answerable: "set
CHAINBENCH_DIR and install a plugin and supply a URL" is three unrelated decisions in one list,
while "chainbench needs this" is one subject the user can accept or decline as a unit.

**Omit a tab entirely when its server has nothing outstanding.** An empty question invites a
search for something to answer. If only one server needs anything, ask a single question —
`AskUserQuestion` requires at least two *options*, not two questions, and a lone tab reads fine.

A row that is not tied to any server — the active pack's `repo_root_env`, e.g.
`GO_STABLENET_ROOT` — gets its own question when `setup.py` reports `NOT-A-REPO` or `MISMATCH`,
because in those cases it wrote nothing and the value has to come from the user.

```
header:   "Project repo"
question: "<KEY> — the checkout the pipeline builds and tests. setup.py declined to pin it
           because <NOT-A-REPO: the directory it would have used has no .git |
           MISMATCH: this is the plugin repo, not a target project>.
           Choose Other and type the path (e.g. ~/Work/github/go-stablenet), or pick the last
           option and I'll ask you for it."
options:
  - "I'll run the command myself"       (print the --repo … --fix command; write nothing)
  - "Skip for now"                      (the pipeline falls back to git rev-parse from
                                         wherever it runs)
  - "I already know it — enter it here" (→ ask in the next message, then write it)
```

The same three as everywhere else, and all three are required — not only because
`AskUserQuestion` refuses a single-option question. With *skip* alone the only way to answer
usefully is to notice `Other`, which is how this ended up needing a manual `setup.py --fix`
afterwards. `I already know it — enter it here` returns its own label like any option — read it
as the request to ask, per **How a typed value reaches you**.

Then write it — pass the path through as typed, `~` included; `setup.py` expands it:

```bash
"$python_bin" "$plugin_path/scripts/setup.py" --repo "<path>" --fix
```

`--repo` both aims the run at that checkout and records the variable inside it, so this is one
command, not two. Confirm from the script's own output that the line reads `REPO-ROOT` and names
the path you passed — `NOT-A-REPO` there means the path is still not a checkout, and nothing was
written.

The pipeline reads this variable to find the checkout it builds and tests (`evaluator.md` §2,
`implementer.md` §1), so a path given here is used — it is not merely recorded.

When `setup.py` pinned it successfully, say what it wrote and ask nothing: there was no choice to
make.

Within each tab, the rows still split by kind:

- **`auto_fixable` rows** — the value is already resolvable (detected on this machine, or
  present in global settings). One option per key inside that server's tab, using the row's
  `description` as the option description so the user can see what each value is for rather
  than guessing from the variable name. Use `multiSelect: true` when a tab holds more than one.

  **Show `resolved_value`, and invite a different one** per the rule above:

  ```
  header:  "Knowledge MCP"
  question: "stablenet-knowledge server endpoint — <description>.
             Detected: <resolved_value>.  Already know the address? Choose Other and type it
             (http://host:port/mcp), or pick the last option and I'll ask you for it."
  options:
    - "Use the detected value"            (only when resolved_value is present; show the value)
    - "I'll run the command myself"       (print the --set command; write nothing)
    - "Skip for now"                      (says what stops working, from the description)
    - "I already know it — enter it here" (→ ask in the next message; see "How a typed value
                                           reaches you" — it returns the label, not a value)
  ```

  **The entry option goes in even when `resolved_value` is present.** A detected value is a
  leftover process env or a stale checkout as often as it is the right answer, and the user is
  the only one who knows which — offering accept-or-skip against a value they did not choose is
  the exact shape that was reported broken.

  Detection lands on stale checkouts and a leftover process environment carries values nobody
  chose, so "shall I set CHAINBENCH_DIR?" without showing the value is not a question anyone can
  answer — and offering only *accept* or *skip* is not either, when the user is the one who knows
  the right value.

  When `value_withheld` is true the row is a credential and carries no value. Do not ask for it
  here — point at `set-mcp-env.sh`, which prompts with hidden input in the user's own terminal.
  Addresses and paths are not credentials and are asked for normally.

  **Write through `--set`, and let the script judge the value:**

  ```bash
  "$python_bin" "$plugin_path/scripts/setup.py" --fix --set KEY=VALUE
  ```

  `setup_checks/validate.py` checks the shape (a URL that parses, a directory that exists) and
  refuses anything that looks like a credential, exiting 2 with a reason that never repeats the
  value. Report that reason as-is and ask again — do not decide for yourself whether a value is
  acceptable, and do not re-print a value the script just refused.

  A row whose `status` is `env` is **not** persisted: the value exists in this session's process
  environment and nowhere on disk, so it vanishes at restart while Claude Code reads `${VAR}`
  from settings. It appears in `not_ready` for that reason. Offer it like any other — the value
  is known, only the writing is missing. On confirmation:
  `"$python_bin" "$plugin_path/scripts/setup.py" --fix`. Report which keys it wrote, from the script's own output.
- **`missing` rows that are not secret** — the value has to come from the user, but it is not a
  credential (`secret: false`, `value_withheld: false`), so collect it in this server's
  `AskUserQuestion` like the rest: show the key, its `description` and `how_to_find` verbatim,
  carry the three options from **The three options every value question carries**, and say in
  the question text to choose **Other** and type it — the same rule as above, and it matters
  more here: with no detected value the *only* useful answer is one the user types, so a
  question offering just *skip* and *I'll do it myself* collects nothing by construction.
  Then write it yourself:
  `"$python_bin" "$plugin_path/scripts/setup.py" --fix --set KEY=VALUE`. The script validates the
  shape and refuses anything that looks like a token, exiting 2 with a reason that never repeats
  the value — report that reason as-is and ask again; do not decide acceptability yourself.
  `STABLENET_KNOWLEDGE_MCP_URL` is this case. Running `--set` by hand stays available for a user
  who would rather keep the address out of the transcript — that is what `I'll run the command
  myself` is for, and printing the command is the whole of that branch. The option that collects
  the value is still the last one in the list, so the list does not end on a way out.
- **`missing` rows that are `secret: true`** — same as above except the value must never enter
  this conversation. Point at `set-mcp-env.sh` per the rules earlier in this step; do not offer
  `--set` for a secret and do not run it yourself.

If the user asks to *remove* a plugin rather than set one up, point them at its own
`setup.py --uninstall` **before** `claude plugin uninstall`: the plugin uninstall leaves env
keys and permission entries behind, and once the plugin is gone the script that knows which
ones were its own goes with it (ADR-0018).

```bash
# Absolute paths on both sides: the script lives in the plugin's install directory, and the
# project it should clean is named explicitly. Without --repo the target is inferred from the
# current directory, so a run started elsewhere cleans only the user scope and looks like it
# worked.
"$python_bin" "$plugin_path/scripts/setup.py" --repo "<project>" --uninstall        # plan only
"$python_bin" "$plugin_path/scripts/setup.py" --repo "<project>" --uninstall --yes  # apply
```

It prints the directories it examined before the plan. Check that the project line is the one
you meant — that is the only place a wrong target shows up.

`--check --json` never carries a secret's value, so reading it here is safe; `--fix` only writes
values that were already resolvable, so it cannot invent or expose one either.

If a plugin has no `scripts/setup.py` (a third-party plugin, or one predating ADR-0014), fall
back to reading `<installPath>/commands/setup.md`: if it exists and the plugin was already
registered at session start, `Skill(skill: "<plugin>:setup", args: "--check")` still works and
its report should be folded in verbatim. If the plugin was installed during this run and has no
script, say plainly that its setup needs a restart first — that is now the exception, not the
rule.

Collect the rows from every plugin before asking, then ask once (below). Asking per plugin
would put the same three subjects in front of the user twice as soon as a second plugin needs
anything.

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
## MCP server conflicts (check 5 of 5)
<one line per conflict from check-mcp-conflicts.sh, or "✓ no conflicts" if ALL_MCP_CONFLICTS_PASS>
```

This is a check heading, not the verdict — number it so a clean result here is not mistaken for
the run's conclusion. The verdict is the report that follows.

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

An `external` conflict row is a collision in which **no** plugin of this marketplace takes part.
Report it and stop — do not open the question above for it. The remedy is disabling one of two
plugins this command does not own, decided on the strength of a check that only saw them because
the scan is deliberately broad; that is the user's call to make elsewhere, not a prompt to answer
here (ADR-0019). `ALL_MCP_CONFLICTS_PASS` is emitted whenever no *our-plugin* conflict exists, so
it can appear alongside such a row — report both rather than suppressing either.

Finish with the report below. **The last thing on screen decides what the user does next**, so
the run's verdict opens it and the action they must take closes it. An earlier draft ended on
the conflict section, and a heading reading "MCP server conflicts" above a clean result was read
as a failure — a section title is not a conclusion.

```
## Doctor result — <one line: what state the environment is now in>

### Done this session
<what was installed/written, one line each; "nothing — everything was already in place" if none>

### Left as-is
<checks that passed and needed no action; items the user chose to skip, with how to get them later>

### Next action                      ← omit this heading entirely when there is nothing to do
<the single thing the user must do now, first and alone. If a restart is needed, say that and
stop — do not bury it under other notes, and do not add anything after this section.>
```

Rules for that last section:

- **One action, stated as an instruction**, not as an explanation of why it is needed. "Restart
  Claude Code" first; the reason after, if at all.
- **Nothing follows it.** Caveats, skipped items and known limitations go in *Left as-is* or
  before the summary. Anything printed after the action competes with it.
- **No heading when there is no action.** An empty "Next action" invites a search for one.

## Known limitations (say so if relevant, don't silently omit)

- `check-plugins.sh`/`check-mcp-conflicts.sh`/`check-mcp-connectivity.sh` read only the **global**
  `~/.claude/settings.json` — a project-local `.claude/settings.local.json` override (e.g.
  disabling a plugin, or supplying a real env value, for just one project directory) is not
  accounted for, so a `critical` row can be reported even when it's already worked around
  locally. Don't treat that as unconditionally wrong if the user says they've already scoped it
  per-project — just note the check doesn't see that layer.
- The three checks scan at deliberately different breadths, and the difference is visible in the
  output. `check-plugins.sh` reads this repo's own `.claude-plugin/marketplace.json`, so Step 1
  lists only this marketplace's plugins and says nothing about any other. `check-mcp-conflicts.sh`
  and `check-mcp-connectivity.sh` read `enabledPlugins` broadly and therefore *do* see plugins
  from other marketplaces — a foreign plugin can genuinely collide with one of ours, which is the
  case ADR-0010 was built on. Those foreign rows come back as `external` and are reported only
  (ADR-0019). So a plugin absent from Step 1 can still appear in Step 2/5; that is the design,
  not an inconsistency to reconcile.
- `check-mcp-connectivity.sh`'s HTTP reachability probe is a plain unauthenticated GET with a 2s
  timeout — any HTTP response (even an error status) counts as "reachable", since the goal is
  distinguishing "the server process is up" from "connection refused/timed out", not validating
  auth or protocol correctness.
- Step 4 delegation reaches a plugin only if it ships `scripts/setup.py` (ADR-0014) or was
  already registered at session start and ships `commands/setup.md`. A plugin with neither is
  treated as needing no further setup, which is only true if it genuinely has none (ADR-0011
  §2.2).
- `set-mcp-env.sh` only covers values referenced as `${VAR}` in a plugin's `.mcp.json` — a
  plugin that hardcodes a literal URL/IP in its own `.mcp.json` (instead of an env var
  reference) isn't something this command can fix; that plugin's `.mcp.json` itself needs
  fixing, which is a code change, not a doctor-time configuration step.
- `AskUserQuestion` requires at least 2 options per question — Step 3's multi-select checkbox
  only works when there are 2+ outstanding items. Confirmed live: with exactly one outstanding
  item, the multi-select call itself errors. If Steps 0-2 leave exactly one actionable item, ask
  about it as a plain two-option question (do it now / later) instead of forcing a multi-select
  with a single checkbox.
- The session-startup registration limit is real but no longer blocking: `Skill(skill:
  "<plugin>:setup")` still cannot reach a plugin installed in this run, which is why Step 4
  delegates through `scripts/setup.py` by path instead. Don't reintroduce the Skill call as the
  primary path — it will not succeed until after a restart. The script route does not replace a
  restart for the plugin's *other* surfaces: its MCP servers, agents, and slash commands still
  need one, so keep saying so.
