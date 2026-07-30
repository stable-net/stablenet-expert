# bench — 3-way comparison harness

Measures whether the stablenet-knowledge system actually makes the coding-agent more
accurate and cheaper than working from code alone. It runs the **same**
go-stablenet task under three information regimes and compares the outcomes:

| mode | how it gathers information | agent |
|------|---------------------------|-------|
| **A_stablenet_knowledge_mcp** | stablenet-knowledge: semantic (ckv) + graph (ckg) + domain | real `analyzer` |
| **B_code_only** | grep / glob / read only (no stablenet-knowledge, no skills) | `bench-analyzer-codeonly` |
| **C_code_skills** | grep / read + comprehension skills (no stablenet-knowledge) | `bench-analyzer-skills` |

All three fix the model to the analyzer tier (`claude-opus-4-8`) so the
comparison isolates the *information regime*, not the model. The shared `planner`,
`implementer`, and `evaluator` consume the mode-blind artifacts. The analysis stage
is where the information regime decides quality, so it is the isolated component.
This directly answers the system contract's §9 thesis ("does retrieval beat
grep?") with data: final-code correctness, tokens, cost, latency, safety.

## Two halves

1. **Automation (plugin-native, in the Claude Code session).** The
   `/core-dev:bench` command + the `bench-orchestration` skill drive the
   experiment: for each (task, mode) cell they dispatch the mode's planner →
   shared implementer → shared evaluator, capture each sub-agent's I/O via the
   transcript hook, and checkpoint. It runs a **bounded batch per invocation**
   and resumes with `--continue`, because a plugin-native run lives inside the
   session's token budget (no headless spawning).

2. **Measurement (this directory — deterministic, no LLM).** `compare.py` reads
   each cell's trace sink and emits the comparison report.

## Run

```
# new experiment (runs the first batch)
/core-dev:bench bench/manifests/example.json
# continue (token-limit-aware)
/core-dev:bench <experiment-id> --continue
```

The skill calls the measurement tool after each batch:

```
python3 bench/compare.py --experiment-dir .stablenet-expert/bench/<experiment> \
    [--prices bench/prices.json] [--sessions sessions.json]
# -> <experiment>/report/comparison.{json,md,csv}
```

## Token / cost accounting

Two sources, distinguished by provenance (`cost_status`):

- **actual** — real per-message tokens from the Claude Code session JSONL
  (`~/.claude/projects/<cwd-slug>/<uuid>.jsonl`, `message.usage`). Pass a
  `{cell_name: session.jsonl}` map via `--sessions`.
- **estimated** — tokens from the transcript hook's char counts (chars/4) when a
  session JSONL isn't supplied.

Cost = tokens × a per-MTok price table (default snapshot in `usage.py`; override
with `bench/prices.json`). Claude does **not** write a cost field to the session
JSONL, so cost is always computed here.

## Tests

```
python3 -m unittest bench.tests.test_usage bench.tests.test_report
```

## Attribution

Patterns adapted (not copied) from the harness study: hermes-agent
`agent/usage_pricing.py` (CanonicalUsage buckets + CostResult provenance + price
table), oh-my-claudecode `src/hud/transcript.ts` and `benchmark/compare_results.py`
(Claude session-JSONL usage reading; A/B comparison report shape, generalized
2-way → 3-way here), oh-my-opencode token shape `{input,output,cache:{write,read}}`.
