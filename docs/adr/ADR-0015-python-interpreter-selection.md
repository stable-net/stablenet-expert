# ADR-0015 — Python interpreter selection

- Status: Accepted
- Date: 2026-08-05
- Related: [ADR-0014](ADR-0014-plugin-setup-script-contract.md) (setup script contract),
  [ADR-0012](ADR-0012-doctor-step-order-revision.md) (doctor step order)

## Context

Python is not one prerequisite among several here. Doctor's Step 4 delegation runs
`python3 <plugin>/scripts/setup.py` (ADR-0014), so on a machine without an interpreter doctor
cannot set up *any* plugin it installs — the repair mechanism itself is missing, not one feature
of it. Go, Node, and gh do not have this property: when they are absent, the affected pipeline
stage fails and everything else still works.

Two facts shaped the decision.

**The requirement is lower than it looks.** Every runtime script in this repository begins with
`from __future__ import annotations`, so `X | None` annotations are never evaluated and the
scripts run on Python 3.9. Only the test suite needs 3.10+ (`test_git_guard.py` annotates
`-> dict | None` without that import). CI pins 3.12. So an old interpreter is not a defect; it
just cannot run the tests locally.

**Installing Python does not, by itself, make our code use it.** Homebrew states this in its own
caveats for `python@3.12`:

> Python is installed as `/opt/homebrew/bin/python3.12`
> Unversioned and major-versioned symlinks `python`, `python3`, … are installed into
> `/opt/homebrew/opt/python@3.12/libexec/bin`

That directory is not on `PATH`. After a successful install, `python3` still resolves to whatever
it resolved to before — and every call site here spells `python3` literally (five hook commands,
three check scripts, three doctor steps). The install would have no effect.

The obvious remedy — put the new interpreter ahead of the old one on `PATH`, or relink `python3`
— was rejected. It is a global, invisible change: it reaches the user's other terminals, other
sessions, and unrelated projects. A variant that saves the old value and restores it when the
session ends was also rejected, for three reasons: a crash or reboot skips the restore and leaves
the machine altered; the mutation is live for other processes during the whole window; and
"when the work finishes" has no definition, since hooks keep running for the life of the session.

## Decision

**1. No version gate.** `check-environment.sh` reports `pass` at 3.10+, `info` below it, and
`critical` only when no interpreter exists at all. `info` rather than `warn` is deliberate — a
working 3.9 is not a defect. Doctor never blocks on the Python row.

**2. Install only with consent, and only what was selected.** The Python row appears in doctor's
Step 3 multi-select like any other actionable item. Because the delegation mechanism depends on
it, it is applied *before* the other selections in Step 4.

**3. Install through the channel already trusted on the host.** `scripts/install-python.sh`
prefers `brew install python@3.12` when Homebrew is present, and falls back to `uv` otherwise
(`uv` installs a standalone interpreter under the user's home directory without sudo). The script
is bash-only, since it is the one repair step that cannot assume Python exists. It is idempotent:
if any interpreter ≥ 3.10 is already available it installs nothing and reports that one.

**4. Reach the interpreter by absolute path, never by changing PATH.** Doctor records the
resolved path as `STABLENET_EXPERT_PYTHON` in Claude Code settings. Every call site becomes:

```
"${STABLENET_EXPERT_PYTHON:-python3}"
```

Unset, this is exactly today's behaviour, so existing users are unaffected. Set, only this
repository's hooks and scripts use the new interpreter. Nothing global changes, and therefore
there is nothing to restore.

**5. The system `python3` is never relinked.** Not even when none exists — the setting above
already resolves the interpreter, so linking would buy nothing and cost a global mutation.

## Verified before adopting

Two assumptions in (4) were measured rather than assumed, in a throwaway project with a
`SessionStart` hook that wrote what it received to a file:

- Claude Code settings `env` reaches hook processes, from both the project and the user-global
  settings file.
- `${VAR:-default}` survives in a `hooks.json` command string. Claude Code substitutes
  `${CLAUDE_PLUGIN_ROOT}` by name and passes string-form commands to a shell, so the default-value
  syntax is expanded by bash: a set variable resolved to its value, an unset one to the default.

## Consequences

- A machine with no Python at all is repairable by doctor in one pass, without a restart and
  without touching `PATH`.
- `STABLENET_EXPERT_PYTHON` written during a session does not reach *that* session's hooks —
  settings `env` is read at session start. Doctor uses the resolved absolute path directly for
  the rest of the run and says plainly that hooks pick it up from the next session.
- A wrong or stale value fails loudly (`No such file or directory`) rather than silently, since
  the shell cannot execute a missing path.
- `install-python.sh` is the only script here allowed to fetch and execute a remote installer,
  and only on the uv fallback path, only after the user selected the item.
