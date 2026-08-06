# ADR-0018 — Settings scope, and taking them back

- Status: Accepted
- Date: 2026-08-06
- Extends: [ADR-0014](ADR-0014-plugin-setup-script-contract.md) (setup script contract),
  [ADR-0017](ADR-0017-setup-external-plugin-dependencies.md) (external plugin dependencies)

## Context

Several people are about to use this marketplace, and getting there means installing and
uninstalling repeatedly while things are debugged. That only works if a removal actually
removes — a half-cleaned machine poisons every diagnosis after it.

Two gaps stood in the way.

**Scope.** `setup.py` wrote only to the project's `.claude/`, while `scripts/set-mcp-env.sh`
has defaulted to the user-global file all along. The two disagreed, and the project-only
choice was the wrong one for what is actually being stored: `CHAINBENCH_DIR` names the one
chainbench checkout on this machine, not a property of whichever repository happened to run
setup.

**Removal.** `claude plugin uninstall` removes the plugin and nothing else. Env keys,
permission entries, and the gitignore line all survive it, and there is no CLI that removes
an env key — settings are edited by hand or by us, so cleaning up is ours to do.

The hard part is not deletion. It is knowing *what is ours*. A key we wrote and a key the
user set by hand are indistinguishable in a settings file, and deleting on a guess destroys
their configuration. Checking the CLI is not an option either: nothing records provenance.

There was also no plugin-lifecycle hook to hang cleanup on. The available events are
`SessionStart`, `SessionEnd`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`,
`UserPromptSubmit`, `Notification`, `PreCompact` — verified against the binary. Nothing fires
before an uninstall.

## Decision

**1. Env values are user-scoped; `repo_root_env` is project-scoped.** Not one flag for both,
because they answer different questions. An env value describes the machine — one checkout,
one server — so it belongs where every project sees it. `repo_root_env` answers "which
checkout is the target", which is per project by definition; writing it globally would make a
second checkout silently build the first. Project settings override global ones, so someone
with two checkouts can still pin each. `--scope project` forces both local, for a shared
machine or a checkout that must not touch the global file.

**2. `--fix` records what it wrote — key *and* value — in a manifest beside the settings.**
`.claude/.stablenet-expert-managed.json`, not a key inside `settings.json`: a settings file
should stay a settings file, with nothing downstream needing to learn to ignore our
bookkeeping.

**3. `--uninstall` removes only entries whose current value still matches what we recorded.**
A value that changed since is kept and reported. This is why the value is stored and not just
the name: reverting an edit the user made after setup ran is a surprise, while leaving a stale
key is tidy-up they can do themselves. It is the rule package managers apply to config files
they ship.

**4. No manifest means nothing is removed.** Not a silent no-op — it says why, and points the
user at doing it by hand. Guessing would mean deleting values we never wrote.

**5. Dry run by default; `--yes` applies.** The plan *is* the value of the manifest. Seeing
"3 to remove, 1 kept because you changed it" before anything happens is what makes this safe
to run on a machine you care about.

**6. The Atlassian plugin is never removed automatically.** setup may have installed it
(ADR-0017), but it is shared: the user may rely on it for their own Jira work, and another
plugin in this marketplace may need it. Uninstall prints `claude mcp logout` and
`claude plugin uninstall` for them to run. The same restraint applies to the `.gitignore`
line, which is harmless and may predate this plugin.

## Consequences

- Install → setup → uninstall is a round trip that ends where it started, which is what makes
  repeated debugging cycles usable.
- The manifest is a new file to keep in step. If `--fix` gains a kind of write that is not
  recorded, uninstall will silently leave it behind — so `manifest.record_*` belongs in the
  same commit as any new write path.
- Scope is a behaviour change: env values that used to land in the project now land in the
  user file. Someone who deliberately kept a per-project value needs `--scope project`.
- A `PreToolUse` hook could catch `claude plugin uninstall` typed inside a session and run
  cleanup first. It is not part of this decision: it only sees Bash tool calls, so a user in
  their own terminal is unprotected, and the hook ships with the plugin being removed.
  `--uninstall` is the mechanism; a hook would only be a reminder.
