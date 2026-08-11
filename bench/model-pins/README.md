# model-pins — single source of truth for coding-agent model pins (overlay P3)

## Why

Model pins lived literally in **three** places that had to be kept in sync by hand:
the `model:` frontmatter of 9 agent `.md` files, a mirror dict in
`bench/lib/capture.py` (cost accounting), and `bench/prices.json`. On a generation
upgrade any of them could drift — the worst case being the bench's A-arm `analyzer`
pinned differently from production, **silently biasing the thesis measurement**.

True runtime centralization is **not possible** in Claude Code: agent frontmatter
`model:` takes no `${VAR}`/central-config indirection, and the only global override
(`CLAUDE_CODE_SUBAGENT_MODEL`) would flatten this plugin's two tiers (deep=opus,
exec=sonnet) to one model. So the pins must stay literal — but they are now derived
from / checked against one source.

**What is literal there is the tier ALIAS (`opus`/`sonnet`), not a concrete model id.**
A concrete id is provider-specific — on Bedrock the same model is a region-prefixed
inference profile or an ARN — and a pin that does not resolve is not an error: Claude
Code falls back to the parent model and logs at `warn`. So an id in frontmatter
silently disables the pin off the first-party API. The concrete id lives on here as
`reference_model`, for pricing only. See ADR-0020.

## How

- **`models.json`** — the single source: `tiers` (deep/exec → `{alias, reference_model}`)
  + `agents` (agent → tier). The alias is what reaches frontmatter; the reference model
  is the concrete id the alias resolves to on the first-party API, used to key
  `prices.json`.
- **`bench/lib/capture.py`** reads `models.json` at runtime (no second copy; literal
  fallback only if the file is unreadable, so the bench still runs).
- **`check.py`** verifies frontmatter == the tier alias (both directions), that
  capture.py resolves the same reference models, and that prices.json covers each
  reference model. `--apply` rewrites the frontmatter `model:` lines to match. It runs
  in CI (`python-tests` job) — it was unwired until ADR-0020, and had been failing on
  `main` since `review-adjudicator` arrived with an unregistered pin.

## Run

```
python3 bench/model-pins/check.py            # verify; exit 1 on any drift (CI/pre-commit gate)
python3 bench/model-pins/check.py --apply     # propagate models.json to agent frontmatter
python3 bench/model-pins/tests/test_check.py  # unit + sandbox + real-repo conformance
```

## Upgrade recipe (the "single edit")

1. edit the tier's `reference_model` in `models.json` (e.g.
   `"deep": {"alias": "opus", "reference_model": "claude-opus-4-9"}`),
2. `python3 bench/model-pins/check.py --apply`,
3. capture.py follows automatically; if `prices.json` lacks the new id, check.py
   fails until you add its price row (so cost accounting can't silently break).

Note the alias rarely changes — a generation upgrade is a `reference_model` edit, and
frontmatter usually stays put. That is the intended shape: the deployment decides which
model an alias means.

## Will the pins take effect?

`check.py` is static — it cannot see that the runtime resolved something else. For that:

```
python3 plugins/core-dev/scripts/doctor.py --plugin-root plugins/core-dev   # before a run
python3 plugins/core-dev/scripts/session_models.py                          # after one
```

Neither prints a model id (ADR-0020 §3c/§3d).

## Note

This is the centralization half of overlay P3; the 4-7→4-8 *bump* was done earlier
(commit `304afba`). The deterministic guarantee here: 10 agents + capture.py + prices
all conform to one file, drift is caught (exit 1), and an upgrade is one edit +
`--apply`. Frontmatter staying literal is a Claude Code constraint, not a choice —
see the mechanism finding above.

What that guarantee does **not** cover is whether the pin survives contact with the
provider. It is a static check; the runtime can resolve something else and say nothing.
ADR-0020 is what closes that gap.
