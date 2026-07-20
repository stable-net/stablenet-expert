# p2-cks-fault — does the stream-6 P2 cks-hardening stop silent incompletes?

P2 (see `docs/coding-agent-overlay-improvements-and-eval-2026-06-22.md`) hardens the
analyzer/planner §3.0 cks gate. The pre-P2 gate was a single start-of-run health
check: serviceable → proceed, else BLOCKED. A per-call failure *during* the run was
handled as "record and continue best-effort" — so an analysis could ship missing a
`get_for_task` / `find_callers` / `impact_analysis` with no flag and no decision
change: a **silent incomplete** that then ships a bad fix. P2 adds (analyzer §3.0b):

- **retry** a dropped/timed-out cks call up to 2× before counting it failed,
- **tier** the failed primitive — PRIMARY (`get_for_task`), COMPLETENESS
  (`find_callers`/`impact_analysis`/`concurrency_impact`), ENHANCEMENT (the rest),
- **decide, never silent**: PRIMARY loss → BLOCKED; COMPLETENESS loss →
  `retrieval_health.degraded` flag + propagate; ENHANCEMENT loss → note + proceed,
- **propagate**: evaluator §4.0 won't skip §4.6 and broadens `-race`; orchestrator
  surfaces the degradation in the PR + adds `needs-careful-review`.

This harness measures the property deterministically (no LLM): drive a corpus of
fault patterns through the before-P2 and after-P2 policies and count silent
incompletes. Mirrors `bench/p0-mutants/` and the `bench/README.md` two-layer split.

## Layers

1. **Deterministic measurement (this dir, no LLM).** `policy.py` is the reference
   implementation of the before/after §3.0 decision logic; `scenarios.py` is the
   fault corpus; `score.py` reports silent-incomplete before vs after + an
   over-block guard. This is the headline number.
2. **Agent-in-the-loop fidelity (live, documented below).** A flaky cks proxy +
   the PR-77 oracle, to confirm the real analyzer agent honors §3.0b.

## Files

| file | role |
|---|---|
| `policy.py` | before/after §3.0 decision functions + primitive tiers (PRIMARY/COMPLETENESS/ENHANCEMENT) |
| `scenarios.py` | fault corpus: health × per-call {ok, transient, persistent} at each tier |
| `score.py` | run corpus × policies → `report/p2-faults.{md,json}` |
| `tests/test_policy.py` | unit tests (per-tier behavior + aggregate guarantee) |

## Run

```
python3 bench/p2-cks-fault/score.py            # prints report; exit 1 if P2 fails its guarantee
python3 bench/p2-cks-fault/tests/test_policy.py
```

`score.py` exits non-zero unless after silent-incomplete == 0 AND after over-block ==
0 AND before silent-incomplete > 0 — a regression gate if the §3.0 spec changes.

## Result (2026-06-22, corpus = 10 scenarios)

```
silent-incomplete (CLEAN while core evidence missing): before 6 → after 0
after over-block (escalated a retry-recoverable run): 0
after decision mismatches vs expected: 0
runs a retry rescued (silent→CLEAN): 3
```

The two failure axes P2 closes: (a) a **persistent** core loss is now an explicit
BLOCKED (primary) or DEGRADED+flag (completeness) instead of a silent CLEAN; (b) a
**transient** core loss is rescued by retry, so hardening does not over-block a
backend that merely flapped. Losing only ENHANCEMENT primitives stays CLEAN in both —
correctly *not* counted as a silent incomplete (those are optional refinements).

## Agent-in-the-loop (fidelity layer — live, not run here)

The deterministic layer proves the *policy* is sound. To prove the *analyzer agent*
follows §3.0b, inject faults into a live cks and measure root-cause accuracy against
a known oracle:

1. Front the cks MCP with a **flaky proxy** that drops/delays a configurable fraction
   of calls (and can target specific primitives, e.g. only `find_callers`).
2. Run the analyzer alone on the **PR-77 fair-input ticket** (oracle:
   `anzeon.go:54 SetCurrentBlock`, see `bench/fixtures/pr77/` and `test-data/pr-77/`)
   at fault rates 0 / 10 / 30 / 50%.
3. Record per rate: PR-77 oracle hit-rate, and — the key safety metric — the count of
   **silent wrong answers** (a confident root cause emitted while a core call was
   dropped). After P2 this must be **0**: the run either recovers (retry), BLOCKs, or
   emits a DEGRADED analysis that flags its own gap. Any silent wrong answer refutes P2.

This separates *insufficient policy* (caught by layer 1) from *agent ignored the
policy* (caught by layer 2).
