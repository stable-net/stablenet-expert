# p0-mutants — does the stream-6 P0 contract-machine-check actually close the gap?

P0 (see `docs/coding-agent-overlay-improvements-and-eval-2026-06-22.md`) turned three
agent-to-agent contracts from prose into machine-checkable blocks:

- planner **§4.5** emits a `plan-contract` (`steps:`) block — authoritative for the Implementer.
- planner **§5.2b** emits a `write-site-contract` (`sites:` + `covered_by_test`) block.
- Implementer **§2.1** parses the plan-contract (prose/contract mismatch escalates),
  **§4.2b** cross-checks every declared site is actually maintained.
- Evaluator **§4.6c** verifies every declared site is covered by an existing test.

This harness measures whether those checks catch defects the *pre-P0* spec missed —
reproducibly, no LLM, no tokens. It extends the `bench/fixtures/eval-gate` pattern
(positive/negative diff + expected verdict) into a generated mutant corpus.

## Two layers (mirrors `bench/README.md`)

1. **Deterministic measurement (this dir, no LLM).** A clean baseline case ×
   mutation operators × two rule engines (`before_p0` / `after_p0`) → a
   before-vs-after detection-rate report. This is the headline number.
2. **Agent-in-the-loop fidelity (rendered, optional).** `render.py` emits the
   `plan.md` / `design.md` a real planner would write for any case/mutant; dispatch
   the real `implementer` / `evaluator` on them and compare their verdict to the
   corpus expectation. Measures whether the *agent* honors the spec, not just whether
   the *rule* is sufficient.

## Files

| file | role |
|---|---|
| `corpus/*.json` | clean baseline cases (contract == ground truth, all sites maintained + covered) |
| `mutate.py` | mutation operators + per-ruleset expected-catching-mechanism |
| `rules.py` | `before_p0` / `after_p0` rule engines (pure functions of a case) |
| `contracts.py` | reference parser for the `plan-contract` / `write-site-contract` yaml blocks |
| `render.py` | case/mutant → `plan.md` + `design.md` (for the agent-in-the-loop layer) |
| `score.py` | run corpus × mutations × engines → `report/p0-detection.{md,json}` |
| `tests/test_rules.py` | unit tests (engines, aggregate guarantee, render↔parse round-trip) |

## Run

```
python3 bench/p0-mutants/score.py            # prints the report; exit 1 if P0 fails its guarantee
python3 bench/p0-mutants/tests/test_rules.py # unit tests
```

`score.py` exits non-zero unless **after > before** detection AND **zero false
positives** on the clean controls — so it doubles as a regression gate if the
agent specs change.

## Mutation operators

| mutant | category | injected defect | before-P0 | after-P0 (mechanism) |
|---|---|---|---|---|
| `clean` | clean | none (control) | silent | silent |
| `impl_drop_site` | hard | impl omits maintenance at a declared site | **miss** | DETECT (implementer §4.2b) |
| `uncover_blank` | hard | a site's `covered_by_test` is empty | **miss** | DETECT (evaluator §4.6c) |
| `uncover_badname` | hard | `covered_by_test` names a nonexistent test | **miss** | DETECT (evaluator §4.6c) |
| `drop_invariant_test` | hard | consistency-invariant test absent | DETECT (§4.6a) | DETECT (§4.6a) |
| `drop_adversarial_test` | hard | adversarial-path test absent | DETECT (§4.6b) | DETECT (§4.6b) |
| `plan_malformed_heading` | hard | a `## Step N` heading malformed → heading parser silently drops it | **miss** | DETECT (implementer §2.1) |
| `plan_block_absent` | soft | no plan-contract block | miss | WARN (implementer §2.1 fallback) |
| `contract_underdeclare` | residual | planner omits a ground-truth site from the contract | miss | **miss** |

## Result (2026-06-22, corpus = 2 cases)

```
hard mutants: 12
before-P0 detection: 4/12 (33%)
after-P0  detection: 12/12 (100%)
improvement: +66.7pp
false positives on clean controls: before 0/2, after 0/2
residual (P0 does NOT close): 2
```

**Honest boundary.** `contract_underdeclare` is a real defect neither ruleset
catches: the machine checks iterate over the *contract*, so a site the planner never
declared is invisible to them. Closing it is the planner's §5.2b authoring discipline
(exhaustive `find_callers` + `impact_analysis`), not a downstream machine check — it
is **not** something P0 claims to fix. The harness reports it explicitly rather than
letting a 100% "hard" number imply total coverage.

## Agent-in-the-loop (fidelity layer)

```
python3 bench/p0-mutants/render.py --case feepayer-truncate --mutant uncover_blank --out /tmp/p0cell
# → /tmp/p0cell/{plan.md,design.md}
```

Then dispatch the real agent on the rendered artifacts (eval-gate style), stipulating
other stages green, and compare its verdict to the mutant's expected mechanism:

- `implementer` on a `impl_drop_site` / `plan_malformed_heading` cell → expect a
  `write_site_dropped` / `contract_mismatch` escalation (no transition).
- `evaluator` on an `uncover_*` cell → expect §4.6 **FAIL** (gate fires).

This separates two failure modes: *the rule is insufficient* (caught by layer 1) vs
*the agent ignored the rule* (caught by layer 2).
