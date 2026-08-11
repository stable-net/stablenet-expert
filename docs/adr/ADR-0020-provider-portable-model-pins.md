# ADR-0020 — Sub-agent model pins name a tier, not a model

Document type: **ADR / design decision (Accepted 2026-08-11).**
Companion files: `bench/model-pins/models.json`, `bench/model-pins/check.py`,
`plugins/core-dev/agents/*.md`, `plugins/core-dev/scripts/setup_checks/model_pins.py`,
`plugins/core-dev/scripts/session_models.py`,
`plugins/core-dev/commands/review-pr.md` §6.5

> **The decision in one line:** agent frontmatter pins a tier alias (`opus`/`sonnet`),
> never a concrete model id; a concrete id survives only in `models.json` as
> `reference_model`, for pricing. Because an unresolvable pin is silent, `doctor`
> reports pins that will not take effect, and `review-pr` verifies the adjudicator's
> independence instead of assuming it.
> **Status:** Accepted (implemented)

## 1. Context

Nine `core-dev` agents pinned concrete model ids (`model: claude-opus-4-8`,
`model: claude-sonnet-5`). Under AWS Bedrock the pins did not take effect.

The mechanism is in Claude Code's sub-agent model resolution, in this order:

1. `CLAUDE_CODE_SUBAGENT_MODEL` — outranks every frontmatter pin when set
2. an explicit override on the Agent call
3. frontmatter `model:` (default `inherit`)
4. normalization; **when the main loop model is a Bedrock model, the main model's
   region prefix is applied** — `claude-opus-4-8` becomes `us.anthropic.claude-opus-4-8`
5. an availability check against the provider's available-model list
6. **on a miss: the newest allowed model in the same family, else the parent model**

Step 6 is the problem. It is not an error. Claude Code logs

> `Subagent model "<X>" is not in the availableModels allowlist; {using the newest
> allowed model in its family | inheriting the parent model} instead`

at `warn`, which does not surface in normal use. The pipeline runs, reports success,
and every stage has quietly used one model.

Why it bites Bedrock and not the first-party API: the available set there is the
account's inference profiles, listed per account and region (falling back to a
hardcoded table when the listing fails). Enablement is granted per account, it lags
first-party releases, the region prefix must match what the account actually has, and
an organisation using custom or provisioned-throughput profiles has ARNs that no
canonical name will ever match.

Two further constraints came out of the deployment being configured:

- **A Bedrock model name is sensitive.** It carries a region prefix, and often an
  account id inside an ARN — an internal cloud resource identifier under the group
  security policy. It cannot be committed to this repo, so "add the Bedrock ids to
  `models.json`" is not available as a fix.
- **Model configuration takes effect only on restart.** Environment values are read at
  session start, and agent definitions are loaded at session start. Combined with a
  silent fallback, this makes the failure very hard to diagnose: you change something,
  restart, see no error either way, and cannot tell whether the change applied.

### 1.1 How the provider is selected (and why an account login cannot change it)

Claude Code picks the provider from environment variables alone:

```js
function Kn() {
  if (Sb()) return "gateway";
  return te.CLAUDE_CODE_USE_BEDROCK ? "bedrock"
       : te.CLAUDE_CODE_USE_FOUNDRY ? "foundry"
       : te.CLAUDE_CODE_USE_ANTHROPIC_AWS ? "anthropicAws"
       : ... : "firstParty";
}
```

Two consequences matter here.

**Authentication and provider are orthogonal.** No account state reaches this function.
Signing in with a different Claude account on a Bedrock-configured machine therefore
cannot move it off Bedrock — there is nothing in the login path that touches the
selection.

**`CLAUDE_CODE_USE_BEDROCK=0` does not disable Bedrock.** The test is bare JavaScript
truthiness, and `"0"` is a non-empty string. Only *unsetting* the variable (or setting
it empty) returns to the first-party API. This is worth stating because setting it to
`0` is the obvious thing to try and it silently does nothing — the same shape of
failure as the pin problem itself.

`detect_provider()` in `setup_checks/model_pins.py` mirrors this rule exactly rather
than applying a sensible-looking one. An earlier draft read `"0"` and `"false"` as
first-party, which would have reported the wrong provider on precisely the machine the
check exists for, hiding the misconfiguration instead of surfacing it.

The variable can come from a shell profile, the `env` block of `~/.claude/settings.json`
or a project `.claude/settings*.json`, or an administrator's managed settings
(`/Library/Application Support/ClaudeCode/managed-settings.json` on macOS,
`/etc/claude-code/managed-settings.json` plus `managed-settings.d` on Linux). Managed
settings are administrator-controlled by design, so where the variable comes from
decides whether toggling it is a user-level action at all.

## 2. What was actually broken

- **`review-adjudicator` lost its reason to exist.** It is defined as running on a
  different model from the reviewer, because the failure it guards against is a
  confident misreading, which a model rarely catches in itself. Collapsed onto the
  parent model it still returns verdicts and the review still reports itself as
  adjudicated.
- **Tiers broke in both directions.** With an opus main loop, `implementer`/`evaluator`
  (exec tier) silently cost opus rates. With a sonnet main loop, `analyzer`/`planner`
  (deep tier) silently reasoned at sonnet.
- **The A/B/C bench measurement.** Its thesis needs all three arms on one model; a
  per-cell fallback breaks that premise, and `bench/prices.json` — keyed by first-party
  ids — records Bedrock runs as unknown models.
- **The existing guard could not see any of it.** `bench/model-pins/check.py` compares
  frontmatter to `models.json`. That is a static check; it cannot observe that the
  runtime resolved something else. It was also **not wired into CI**, and had in fact
  been failing on `main` since `review-adjudicator` was added in #49 with a pin that was
  never registered in `models.json`.

## 3. Decision

**a. Frontmatter pins a tier alias.** `opus` and `sonnet`, never a concrete id. An
alias is the only form Claude Code resolves per provider: on Bedrock and Vertex it
resolves through the deployment's own `ANTHROPIC_DEFAULT_<TIER>_MODEL`, so the
provider-specific id stays in the deployment's environment and never enters this repo.
`contract-dev`'s agents already did this; `core-dev` now matches.

**b. `models.json` keeps the concrete id as `reference_model`.** Each tier carries
`{alias, reference_model}`. The alias goes to frontmatter; the reference model keys
`prices.json` and labels `capture.py`'s estimate path. Where a session transcript
exists it records the real model and wins — the reference model is a first-party label,
correct only there, and is documented as such.

**c. `doctor` reports pins that will not take effect** (`setup_checks/model_pins.py`),
before a run rather than after. It detects the provider, and for a non-first-party one
reports whether each tier's `ANTHROPIC_DEFAULT_<TIER>_MODEL` is set. It also flags a
concrete id in frontmatter and a `CLAUDE_CODE_SUBAGENT_MODEL` that would flatten the
tiers. This is advisory and does not change the verdict: a collapsed tier still runs,
it just does not run what was asked for.

**The check reads presence, never values.** `os.environ.get(k)` is tested for
truthiness and discarded. This is enforced by a test that puts a realistic ARN in the
environment and asserts no fragment of it appears in either the result dict or the
rendered output.

**d. `review-pr` verifies the adjudicator ran on a different model** (§6.5, via
`session_models.py`). The session transcript records `message.model` per message and
marks sub-agent turns with `isSidechain`, which is enough. A failure is treated exactly
like an adjudicator failure: **post nothing**. Output is the model *family* only
(`opus`, `sonnet`), extracted by matching a known family name; an id no family matches
is reported as `unidentifiable` rather than echoed.

**e. An unreadable transcript fails the check.** `--require-distinct` exits 1 when the
transcript is missing, and "no sub-agent turns recorded" is not treated as
independence. Not knowing is not proof, and the adjudicator's own posture is
default-reject.

**f. The gate runs in CI.** `bench/model-pins/check.py` plus its tests, so the drift
that sat on `main` since #49 cannot recur silently.

## 4. Consequences

**Gained.** The pins survive a provider change. No cloud resource identifier need ever
be committed. The two silent failures — a collapsed tier, a non-independent adjudicator
— now produce output. The pre-flight check breaks the restart-blind debugging loop:
it can be run without restarting to see what *will* resolve.

**Given up.** Generation pinning in frontmatter. `model: opus` follows whatever the
deployment maps `opus` to, so the exact generation is no longer fixed by this repo —
which is the point, since a repo cannot know another account's model catalogue. For the
bench, where the exact model does matter, the session transcript already carries the
real one; the static map is only the estimate-path fallback.

**Not fixed here.** `prices.json` is still keyed by first-party ids, so a Bedrock run
still yields unknown-model cost rows. Adding the Bedrock ids would put sensitive
identifiers in the repo, so the fix has to be normalization at capture time —
recording the family and pricing off the reference model. That is deliberately left
out of this change; **as of this ADR a Bedrock bench run's cost figures are not
trustworthy**, and the same path can write a raw Bedrock id into
`bench/.../comparison.{json,csv,md}`, which is a committed artifact. Do not publish
bench outputs from a Bedrock run until that is closed.

## 5. Alternatives rejected

- **Concrete ids plus `ANTHROPIC_BEDROCK_REGION_PREFIX`.** Fixes only the prefix case.
  Enablement gaps, generation lag and custom profile ARNs remain, and the failure stays
  silent. Still worth setting where the prefix genuinely is the mismatch.
- **`ANTHROPIC_DEFAULT_<TIER>_MODEL` on its own.** Those variables feed *alias*
  resolution, so with concrete ids in frontmatter they do nothing. They are necessary
  but only alongside (a) — a distinction worth stating, because trying them alone looks
  like the fix and changes nothing.
- **`CLAUDE_CODE_SUBAGENT_MODEL`.** Guarantees a valid model but collapses both tiers to
  one, which is the failure being fixed, applied deliberately. Kept only as an emergency
  escape hatch, and now reported when set.
- **A provider-aware `models.json` holding Bedrock ids.** Ruled out by the sensitivity
  constraint: those ids cannot be committed.
- **Every agent on `inherit`.** Honest and simple, but abandons the exec tier's cost
  saving and the adjudicator's independence outright.
