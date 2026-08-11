# ADR-0022 — The provider flag is read as written, not as the CLI reads it

Document type: **ADR / design decision (Accepted 2026-08-12).**
Supersedes the detection rule in ADR-0020 §4.2.
Companion files: `plugins/core-dev/scripts/setup_checks/model_pins.py`
(`detect_provider`, `_truthy`, `provider_flag_disagrees`),
`plugins/core-dev/scripts/bedrock_tiers.py` (generated guard)

> **The decision in one line:** `CLAUDE_CODE_USE_BEDROCK=0` means off in core-dev, even
> though Claude Code itself still reads it as Bedrock; the resulting gap is reported as
> `provider_flag_disagrees` rather than hidden.
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

`_truthy` accepts `1`, `true`, `yes`, `on` (case-insensitive, trimmed). Everything
else — including `0`, `false`, `off`, `no` — is off.

The generated `bedrock-models.env` guard uses the same set, so core-dev is internally
consistent: if `doctor` says the provider is off, the tier exports are off too.

```sh
case "${CLAUDE_CODE_USE_BEDROCK:-}" in
  1|true|yes|on|TRUE|YES|ON)
    export ANTHROPIC_DEFAULT_OPUS_MODEL="..."
    ;;
esac
```

## 3. What this costs, stated plainly

**Between `0` and unset there is now a window where core-dev is wrong about the
runtime.** With `CLAUDE_CODE_USE_BEDROCK=0`:

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

`provider_flag_disagrees()` returns any provider variable that is non-empty but not
affirmative — precisely the set where the two rules differ — and `check()` raises it as
an issue before anything keyed on the provider runs:

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

**Unchanged.** Unset and empty still mean first-party in both rules; `1` still means
Bedrock in both. The rules agree everywhere except a non-empty non-affirmative value.

## 6. Related

- ADR-0020 §4.2 — the superseded rule and the reasoning for it, kept for the record
- ADR-0021 — the tier values this gates
