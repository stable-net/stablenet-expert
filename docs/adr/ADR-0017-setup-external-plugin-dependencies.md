# ADR-0017 — External plugin dependencies in the setup contract

- Status: Accepted
- Date: 2026-08-06
- Extends: [ADR-0014](ADR-0014-plugin-setup-script-contract.md) (setup script contract)
- Related: [ADR-0013](ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md) (adopt the official
  Atlassian MCP), [ADR-0011](ADR-0011-stablenet-expert-doctor-interactive-setup.md) §2.2
  (delegation principle)

## Context

ADR-0013 decided that core-dev takes its Jira access from the official Atlassian MCP plugin,
which lives in Anthropic's `claude-plugins-official` marketplace rather than this one. The
pipeline's input is a ticket, so this is a hard dependency: `/core-dev:work` cannot start
without it.

Nothing was set up to satisfy it. `docs/SETUP.md` §4.1 documented the install and OAuth steps
for a human to follow by hand, and doctor did not check for the plugin at all — the string
"atlassian" did not appear anywhere under `plugins/stablenet-expert/`. A user could complete
doctor and still have no way to read a ticket.

ADR-0014's `REQUIRED` table has no room for this. It is a table of **environment values**:
each row is a key, where to store it, what it means, and where to obtain it. An external
plugin is not a value. It is installed or not, authenticated or not, and the fix is an action
rather than a write.

Four properties of the `claude` CLI were measured on 2026-08-06 before designing around it:

1. **`claude mcp list` sees a just-installed plugin without a session restart.** The CLI is a
   fresh process reading config from disk; only the running session's server list is stale.
   Install and login can therefore happen in the same doctor pass, and the user waits for one
   restart at the end rather than two in the middle.

2. **Its output distinguishes installed from authenticated** — `✔ Connected` versus
   `! Needs authentication`. Nothing else does. An HTTP probe cannot substitute: an OAuth
   server answers while unauthenticated, so `check-mcp-connectivity.sh`'s reachability test
   would report a plugin nobody can use as fine.

3. **`claude mcp login` refuses to run when stdin is not a terminal — in both modes.** It opens
   the browser, starts waiting, then aborts with "stdin isn't a terminal". `--no-browser` is
   not the automation fallback its name suggests; it is *more* interactive, since it also wants
   the redirect URL pasted back.

4. **Allocating a pty satisfies that check**, and the browser callback then completes the flow
   on its own. The terminal has to exist, not to be typed into.

## Decision

**1. Rows gain a `row_kind`.** `env` keeps today's meaning. `plugin` means an external Claude
Code plugin. The caller branches on it, because the kinds are not interchangeable: an env value
can be written unattended, while a plugin install reaches outside the project and opens a
consent window.

**2. `auto_fixable` is per-kind, and the "unattended" rule stays with values.** For an `env`
row, `missing` and `auto_fixable` remain mutually exclusive — nobody can write a value nobody
supplied. That rule does not generalise: a missing *plugin* is missing in a different sense and
installing it asks the user for no value at all. The test that pinned the old invariant now
scopes itself to `env` rows and says why.

**3. A new `opens_browser` field.** `auto_fixable` says a fix needs no input from the user; it
does not say the fix is invisible. A browser window appearing unannounced is a side effect the
user should agree to first, so the flag exists to be read into the confirmation prompt.

**4. A new `not_ready` list beside `missing`.** `missing` cannot express "installed but not
authenticated" — present, and still unusable. A caller checking only `missing` would call the
setup done.

**5. Acting on external plugins is opt-in: `--fix --with-plugins`.** `--fix` alone reports them
and changes nothing. Two reasons. It reaches outside the project, into the user's Claude Code
and their Atlassian account, which is a different order of side effect from writing a settings
key. And a test suite that runs `--fix` must not install software on the machine running it —
this was not hypothetical: before the flag was inverted, running the suite installed the
Atlassian plugin and hung on OAuth attempts, taking the run from 5 seconds to 116.

**6. "Could not ask" is its own state.** When the CLI cannot be consulted — absent, timing out,
failing — the status is `unknown`, not `missing`, and nothing is offered or attempted. Treating
a failure to observe as an observation would offer to install a plugin that may already be
there. An environment that answers wrongly is not hypothetical either: `claude mcp list` run
without `HOME` reported an *uninstalled* plugin as `✔ Connected`.

**7. State is re-read after acting, never assumed.** `fix()` returns what the CLI says
afterwards, so an abandoned consent cannot be reported as success — which would send the user
off to restart into a pipeline that cannot read a ticket.

**8. Per-dependency modules.** `scripts/setup_checks/<name>.py`, imported by `setup.py`, which
keeps the contract surface (`--check`/`--fix`/`--json`, settings writes) and the `REQUIRED`
table about values. Running a script puts its directory on `sys.path[0]`, so the import needs
no packaging. Stdlib only still holds.

## Consequences

- Doctor can bring a fresh machine to a working core-dev in one pass: install the plugin,
  install its external dependency, authenticate it, write the settings, then one restart.
- The login timeout (180s) is ours, not the CLI's. The CLI waits indefinitely ("^C to cancel"),
  so without a deadline an unattended doctor run would hang forever.
- `--check` now costs a `claude mcp list`, which health-checks every configured server —
  measured at 1.7–3.0s. It carries a 45s leash so a hung CLI is reported rather than inherited.
- Detection depends on the CLI's human-readable output. If that format changes, detection
  degrades to `missing` and offers a redundant install. The observed lines are pinned verbatim
  in `test_atlassian.py` so the assumption is visible when it breaks.
- This ADR covers *setting up* the dependency. The pipeline still calls the retired
  `jira-gateway` tools; migrating those call sites is ADR-0013 §2.2 and remains open. Until
  then both servers are declared, which is transitional but safe.
- chainbench is deliberately not covered. Its test harness is being ported to Go in parallel,
  so a build-and-register flow written now would describe a shape that is changing.
