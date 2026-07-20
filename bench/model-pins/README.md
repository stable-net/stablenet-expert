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

## How

- **`models.json`** — the single source: `tiers` (deep/exec → model id) + `agents`
  (agent → tier). Edit one tier value to upgrade a generation.
- **`bench/lib/capture.py`** reads `models.json` at runtime (no second copy; literal
  fallback only if the file is unreadable, so the bench still runs).
- **`check.py`** verifies frontmatter == models.json (both directions), that
  capture.py resolves the same map, and that prices.json covers each tier model.
  `--apply` rewrites the frontmatter `model:` lines to match.

## Run

```
python3 bench/model-pins/check.py            # verify; exit 1 on any drift (CI/pre-commit gate)
python3 bench/model-pins/check.py --apply     # propagate models.json to agent frontmatter
python3 bench/model-pins/tests/test_check.py  # unit + sandbox + real-repo conformance
```

## Upgrade recipe (the "single edit")

1. edit the tier value in `models.json` (e.g. `"deep": "claude-opus-4-9"`),
2. `python3 bench/model-pins/check.py --apply` — rewrites all deep-tier agent files,
3. capture.py follows automatically; if `prices.json` lacks the new id, check.py
   fails until you add its price row (so cost accounting can't silently break).

## Note

This is the centralization half of overlay P3; the 4-7→4-8 *bump* was done earlier
(commit `304afba`). The deterministic guarantee here: 9 agents + capture.py + prices
all conform to one file, drift is caught (exit 1), and an upgrade is one edit +
`--apply`. Frontmatter staying literal is a Claude Code constraint, not a choice —
see the mechanism finding above.
