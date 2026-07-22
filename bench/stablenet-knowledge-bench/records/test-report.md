# Test Report: LOCAL-20260609_003552

Generated: 2026-06-09T01:19:44Z
Branch: feature/ckg-benchmark-harness
HEAD: 666466adc046132744dc16b68824c52698b74fdd

## Summary

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 0 — Go Build | PASS | `go build ./...` exit 0; one warning in transitive dependency test file (x/tools) — not production code |
| Stage 1 — Unit Test (Python) | PASS | 84/84 tests passed; Go race check N/A (no Go production changes) |
| Stage 2 — Lint & Format | PASS | 30/30 `.py` files compile cleanly; gofmt N/A (no `.go` files changed) |
| Stage 3 — Security Scan | PASS | No shell injection, no hardcoded secrets, no path traversal vulnerabilities |
| Stage 4 — ChainBench | SKIP | No consensus/governance/state/txpool production code changed; pure Python harness |
| **Overall** | **PASS** | All applicable stages pass; ChainBench skip is justified |

## Scope Verification

`git diff --stat dev...feature/ckg-benchmark-harness` confirms only `.stablenet-expert/bench/ckg-bench/**` files were added (188 files, 10546 insertions, 0 deletions to production code). No Go production source modified.

## Stage 0 — Go Build

Command: `go build ./...`
Exit code: 0
Note: One warning from `golang.org/x/tools@v0.21.1/internal/tokeninternal/tokeninternal.go:64` ("invalid array length") is in a transitive dependency's internal test helper, not in go-stablenet production code. The exit code is 0 and the Go tree is intact.
Log: `logs/eval-build.log`

## Stage 1 — Unit Test

Test runner: `python3 -m unittest discover -s .stablenet-expert/bench/ckg-bench/tests`
- passed: 84
- failed: 0
- skipped: 0
- exit code: 0

Test modules covered:
- `test_drivers` — AskResult, ClaudeCLIDriver, ReplayDriver (16 tests)
- `test_e2e_replay` — 2-question × 4-method full run, resume from partial, report.json structure (3 tests)
- `test_extract` — strict/lenient/failed extraction modes, Citation round-trip (12 tests)
- `test_report` — rollup, delta, per-question section, missing method graceful handling (10 tests)
- `test_runner` — runner batch/resume, state module CRUD (13 tests)
- `test_scorers` — location P/R/F1, correctness, hallucination (file/symbol/line checks), info_volume (30 tests)

Go `-race` scope: N/A. No Go production files were modified. The harness is pure Python with no concurrency.

Coverage: not measured (replay driver makes coverage meaningful only at integration level).
Log: `logs/eval-unit-test.log`

## Stage 2 — Lint & Format

Python syntax check (`python3 -m py_compile`) on all 30 `.py` files: 30/30 OK, exit 0.
gofmt/goimports check: N/A — zero `.go` files changed on this branch.
Log: `logs/eval-lint.log`

## Stage 3 — Security Scan

Go vet: `go vet ./...` exit 0 (one warning in transitive dependency test file only).
Log: `logs/eval-vet.log`

Diff-targeted pattern scan on all changed `.py` files:

| Check | Result |
|-------|--------|
| `shell=True` in subprocess | NONE — all subprocess.run calls use list form (safe) |
| Hardcoded secrets (password/token/key/apikey with literal ≥16 chars) | NONE |
| Path traversal (`../` in user-controlled path joins) | NONE — `..` appears only in internal hardcoded `os.path.join(..., "..", "..", "..")` calls resolved via `os.path.abspath()`, canonicalized before use |
| Silently-ignored errors (`_ = func()` pattern) | NONE — the one grep match (`state.py:177 dir_ = ...`) is a local variable assignment, not error suppression |
| Subprocess inputs (claude CLI + grep + git) | All constructed as fixed lists; no user input injected into shell args |

Findings: 0 critical, 0 high, 0 medium, 0 low.
Log: `logs/eval-security.log`

## Stage 4 — ChainBench

Status: SKIP (justified)

Justification: The branch adds only `.stablenet-expert/bench/ckg-bench/**` — a pure Python measurement harness with no modification to any Go production package. Specifically:
- `consensus/wbft/` — unchanged
- `core/txpool/` — unchanged (`.gitignore` and working-tree files from implementation branch unrelated to this feature)
- `systemcontracts/` — unchanged
- Any state machine, governance, or block-production path — unchanged

ChainBench is designed to validate chain production and transaction processing. Running it against an unmodified chain binary would produce identical results as the baseline and provides no signal about the harness's correctness. The skip is explicitly justified per the evaluation scope instructions.

## Acceptance Criteria Verification

### AC#1 — End-to-end reproducibility

Command: `python3 .stablenet-expert/bench/ckg-bench/run.py --manifest .stablenet-expert/bench/ckg-bench/manifests/default.json --driver replay --batch-size 200`

- Run 1: exit 0, 120 cells completed (30 questions × 4 methods), report.md written
- Run 2: exit 0, 120 cells completed, report.md written
- `diff report.json` between run1 and run2: IDENTICAL

AC#1: PASS

### AC#2 — report.md contains per-method rows with all 4 metrics

Report rollup table verified:
- All 4 method rows present: M1_raw, M2_graph_full, M3_incremental, M4_get_for_task
- Location accuracy (`loc_f1`, plus `loc_p`/`loc_r`): present
- Correctness rate (`correct_rate`): present
- Hallucination count (`hallucs`): present
- Info volume (`avg_input_tokens`): present

Note: With the replay driver, all scores are 0.0 / 100.0 — this is expected. The replay driver returns synthetic placeholder responses (no real citations or answers). The scoring infrastructure is exercised and returns deterministic results.

AC#2: PASS

### AC#3 — report.md contains M4-vs-M1 delta table

Delta table present in report.md:
- baseline: M1_raw
- target: M4_get_for_task
- Δ_correct_rate column: present
- token_reduction_% column: present

AC#3: PASS

### AC#4 — re-running reproduces metrics; drift re-resolution present in validate_golden.py

- Two successive runs produce byte-identical `report.json`
- `validate_golden.py` is called before every benchmark run (in `run.py:_validate_golden_set`) and exits 1 on any golden-set drift, aborting the run before any LLM calls
- 30/30 questions passed validation in both runs (disk-level checks; stablenet-knowledge checks require live stablenet-knowledge server, not available in offline mode)

AC#4: PASS

## Overall

Overall status: PASS

All applicable stages pass. The branch is ready for PR.
- Stage 0 (Go build): PASS
- Stage 1 (Python unit tests): PASS (84/84)
- Stage 2 (Lint/format): PASS (30/30 py_compile OK)
- Stage 3 (Security): PASS (0 findings)
- Stage 4 (ChainBench): SKIP (justified — no production code changed)
- AC#1–4: all PASS
