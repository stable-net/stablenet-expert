# ADR-0022 — The provider flag is read as written, not as the CLI reads it

Document type: **ADR / design decision (Accepted 2026-08-12).**
Supersedes the detection rule in ADR-0020 §4.2.
Companion files: `plugins/core-dev/scripts/setup_checks/model_pins.py`
(`detect_provider`, `_truthy`, `provider_flag_disagrees`),
`plugins/core-dev/scripts/bedrock_tiers.py` (generated guard)

> **The decision in one line:** `CLAUDE_CODE_USE_BEDROCK=1` means Bedrock in core-dev and
> every other value means off — including `0`, which Claude Code itself still reads as
> Bedrock; the resulting gap is reported as `provider_flag_disagrees` rather than hidden.
> **Status:** Accepted (implemented)

## 1. Context

ADR-0020 §4.2 had `detect_provider()` copy the CLI's rule exactly. The CLI selects the
provider with a bare JavaScript truthiness test — verified verbatim in 2.1.228:

```js
function Wn() {
  if (GS() || K6i()) return "gateway";
  return re.CLAUDE_CODE_USE_BEDROCK ? "bedrock" : re.CLAUDE_CODE_USE_FOUNDRY ? ... ;
}
```

No comparison precedes `?`, so any non-empty string is true and `0` selects Bedrock.
Mirroring that made `doctor` agree with the runtime in every case.

It also made `doctor` disagree with its user. `0` is how people switch a flag off, and
someone who writes it has decided they are not using Bedrock right now. Reporting
`provider=bedrock` at them is technically right and practically confusing, and it happened
on this deployment: the flag was set to `0` deliberately, and `doctor` insisted otherwise.

## 2. Decision

`_truthy` accepts exactly `1` (trimmed). Every other value is off — `0` and `false` as
expected, but `true`, `yes`, and `on` as well.

One accepted spelling is the point, not an oversight. A set of synonyms has to be
restated in every language that reads the flag — Python here, `sh` in the generated
guard — and each restatement is a chance for the two to drift apart on some value nobody
tests. With a single value there is nothing to keep in sync and nothing to remember.

The generated `bedrock-models.env` guard is the same test, so core-dev is internally
consistent: if `doctor` says the provider is off, the tier exports are off too.

```sh
if [ "${CLAUDE_CODE_USE_BEDROCK:-}" = "1" ]; then
  export ANTHROPIC_DEFAULT_OPUS_MODEL="..."
fi
```

## 3. What this costs, stated plainly

**For every value except `1`, empty, and unset there is now a window where core-dev is
wrong about the runtime.** With `CLAUDE_CODE_USE_BEDROCK=0` — and equally with `true`:

| | reads it as |
|---|---|
| core-dev | first-party |
| Claude Code | **Bedrock** — requests go to Bedrock |

Every Bedrock check keys on `detect_provider()`, so in that window `tier_alias_unmapped`
and the whole `bedrock tiers` section are skipped while sub-agent pins can still be
collapsing silently. That is the exact failure ADR-0020 was written to catch, and this
decision reopens it for one specific value.

ADR-0020's reasoning against this was not wrong; it was weighed differently. The judgment
here is that `0` is rare and deliberate, whereas the confusion it caused was immediate.

## 4. Why the window is not silent

`provider_flag_disagrees()` returns any provider variable that is non-empty and not `1` —
precisely the set where the two rules differ — and `check()` raises it as an issue before
anything keyed on the provider runs:

```
model pins : provider=first_party tiers=opus,sonnet agents=10
  ⚠ [provider_flag_disagrees] CLAUDE_CODE_USE_BEDROCK is set to a value that is neither
    empty nor affirmative, so this check reads it as off — but Claude Code tests it with
    bare truthiness and still routes to that provider. The tier checks below were
    skipped ... Unset it (or set it empty) to actually switch off, or set it to 1 to
    keep using it.
```

So the report names the disagreement, which side each rule takes, what was skipped
because of it, and the two ways out. A reader who wanted Bedrock off learns their flag
did not do that; a reader who wanted it on learns to write `1`.

`_cli_truthy` is kept beside `_truthy` for this purpose only. The two rules live next to
each other so the difference stays visible in the code rather than becoming folklore.

## 5. Consequences

**Good.** `doctor` matches the operator's intent, which is what a diagnostic is read for.
core-dev's own components agree with each other. The one case where intent and runtime
diverge is reported rather than assumed away.

**Bad.** For that one value, core-dev's `provider` field does not describe where requests
go. Anything reading `provider` programmatically must treat `provider_flag_disagrees()`
as part of the answer, not as a cosmetic warning.

**Unchanged.** Unset, empty, and `1` mean the same thing under both rules. Those three
are the whole agreement.

## 6. One plugin's pins are not the blast radius

`ANTHROPIC_DEFAULT_<TIER>_MODEL` is a process-global environment variable, so it governs
alias resolution for **every** installed plugin's sub-agents, not just the plugin
`doctor` was pointed at. On this deployment nine installed plugins ship 35 pinned agents;
`core-dev` is ten of them.

Checking one plugin and printing "fine" would therefore be wrong in the ordinary case.
`check(..., scan_installed=True)` discovers every installed plugin's `agents/`
directory, unions their tier aliases into the set that must be mapped, and reports
plugins pinning concrete ids under `foreign_pin_is_concrete_id` — separate from
`pin_is_concrete_id` because those files are not editable from this repo; the fix is to
update or disable the plugin.

Discovery deduplicates: a plugin can appear under `marketplaces/` (source) and one or
more `cache/<version>/` unpacks. The source path wins, and each plugin is counted once.

This also surfaces version skew. A plugin whose installed copy predates a pin fix still
carries the old concrete ids, and the report names it — which is how the stale installed
`core-dev` was found after ADR-0020 landed in the repo.

## 7. Related

- ADR-0020 §4.2 — the superseded rule and the reasoning for it, kept for the record
- ADR-0021 — the tier values this gates
