# ADR-0021 — Bedrock tier values live in the shell, not in settings

Document type: **ADR / design decision (Accepted 2026-08-11).**
Companion files: `plugins/core-dev/scripts/bedrock_tiers.py`,
`plugins/core-dev/scripts/tests/test_bedrock_tiers.py`,
`plugins/core-dev/scripts/doctor.py` (REMEDIATION, `bedrock_tiers` section)

> **The decision in one line:** the model ids that `opus`/`sonnet` resolve to are written
> to `~/.claude/bedrock-models.env`, a 0600 file the user's shell profile sources and
> that no-ops off Bedrock — not to `~/.claude/settings.json`, which every other env value
> uses (ADR-0018).
> **Status:** Accepted (implemented)

## 1. Context

ADR-0020 moved agent frontmatter from concrete model ids to tier aliases, and closed by
saying the alias-to-model mapping "is the deployment's own job". That left the actual
question open: **where does a Bedrock deployment put its model ids?** Every user of this
plugin runs on Bedrock, so "the deployment's job" is not a detail — it is the setup path.

The mapping lives in `ANTHROPIC_DEFAULT_<TIER>_MODEL`. On Bedrock its value is a
region-prefixed inference profile or an ARN, which under the group security policy is an
internal cloud resource identifier: it cannot be committed. So the value has to reach the
process from somewhere outside the repo, and there are only two candidates.

## 2. Why not `~/.claude/settings.json`

`setup --fix` writes every other env value into the user-scope settings file (ADR-0018),
so that is the obvious place, and it is the wrong one. It was tried and reverted.

**It is unconditional.** The file has no notion of "only when Bedrock is active". A
Bedrock inference-profile ARN recorded there is applied to every session on that machine,
including sessions that are on the first-party API, where the ARN is not a valid model.
Configuring Bedrock this way breaks not-Bedrock.

**It takes literals only.** Claude Code expands `${VAR}` in HTTP-hook headers and MCP
arguments; it does **not** expand anything in the settings `env` block. So the value
cannot be a reference to a variable the user already has — the ARN has to be written out
in full, in a file that is easy to share, diff, or copy into a repo by accident.

A third option, `modelOverrides` + `availableModels`, has the same two properties and
adds a second indirection (alias → canonical id → override → ARN) for no benefit: an ARN
is accepted directly as a model id, so the canonical-id hop buys nothing.

## 3. Decision

Keep the value in the **shell environment**, which is the one layer that is already
per-machine, already conditional, and already holds `CLAUDE_CODE_USE_BEDROCK` itself —
the variable that decides whether any of this applies. `bedrock_tiers.py` manages a file
the profile sources:

```bash
# ~/.claude/bedrock-models.env   (0600, written by core-dev)
if [ -n "$CLAUDE_CODE_USE_BEDROCK" ]; then
  export ANTHROPIC_DEFAULT_OPUS_MODEL="<this account's opus profile>"
  export ANTHROPIC_DEFAULT_SONNET_MODEL="<this account's sonnet profile>"
fi
```

```bash
# ~/.zshrc — one line
[ -f ~/.claude/bedrock-models.env ] && source ~/.claude/bedrock-models.env
```

The repo holds variable **names**; the machine holds **values**. Nothing in this
repository has to change when a deployment's account, region, or profile changes.

**The guard mirrors Claude Code's own rule, deliberately.** Claude Code selects the
provider with a bare JavaScript truthiness test, so `CLAUDE_CODE_USE_BEDROCK=0` still
means Bedrock; only unsetting it (or setting it empty) does not. `[ -n "$..." ]` is that
same test. A guard that read `0` as "off" would leave the tiers unmapped on a machine the
CLI still considers Bedrock — the exact silent failure ADR-0020 exists to prevent.

### Registering values without putting them in shell history

```bash
python3 scripts/bedrock_tiers.py --set opus="$MY_OPUS_ARN" --set sonnet="$MY_SONNET_ARN" --fix
```

The shell expands the variables, so the ARN reaches the script but the **name** is what
lands in history. This is why the interface takes `TIER=VALUE` rather than prompting.

## 4. The generated file is executed, not parsed

A shell sources it at startup, so a recorded value is code, and `bedrock_tiers.py` is a
program that writes code from input. Values are therefore accepted only if they match
`[A-Za-z0-9._:/-]+` — the character set a model id or ARN actually uses. Anything
containing a quote, `$`, backtick, semicolon, or newline is **rejected rather than
escaped**: a value outside that set is not a model id, so there is no case where quoting
it harder is the right answer.

Supporting properties, each pinned by a test:

- the file is created at 0600 via a private temp file and `os.replace`, so there is no
  window where it is world-readable or half-written
- a rejected value writes nothing at all
- re-running with the same values is byte-identical, so the file can be regenerated
- `doctor` reports the mode and flags it if it has been widened

## 5. Nothing prints a value

`bedrock_tiers.py` follows the rule `setup_checks/model_pins.py` already set: every
report is *is this tier mapped*, never *what it maps to*. That extends to failure paths —
the exception raised for a malformed value does not include the value, because a
malformed ARN is still an ARN. Tests assert that a realistic ARN placed in the input
produces no id, account number, or region fragment in stdout, stderr, `--json`, or the
returned dicts.

## 6. Consequences

**Good.** A first-party machine is unaffected: no file, or a file whose guard is false.
The repo carries no identifiers. `doctor` now reports the whole chain — provider, whether
each tier is mapped, whether the file exists, whether a profile sources it, and its mode
— so the "changed something, restarted, saw nothing" loop ADR-0020 §5 describes is
closed on the configuration side.

**Cost.** One line in a shell profile is manual. It is not automated because appending to
a user's shell profile without asking is a worse default than one documented line, and
because which profile is correct (`.zshrc`, `.zshenv`, `.bash_profile`) is the user's to
know. `doctor` detects whether the line is present and says so when it is not.

**Restart is still required.** The shell is read at process start, so a change takes
effect in the next session. This ADR does not change that; it makes the state visible
beforehand instead.

**Not covered.** Discovering profiles automatically via `aws bedrock
list-inference-profiles` was considered and deferred — it adds an AWS CLI and credentials
dependency to `doctor`, which is otherwise offline and read-only. The `--set` interface
is a superset of what discovery would produce, so adding it later changes nothing here.

## 7. Related

- ADR-0020 — tier aliases in frontmatter; this ADR supplies the values they resolve to
- ADR-0018 — `setup` scope; this is a deliberate exception to "env values go to settings"
