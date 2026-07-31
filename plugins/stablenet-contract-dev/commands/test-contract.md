---
name: stablenet-contract-dev:test-contract
description: Compile and run the real systemcontracts/ test suite (Go-based — not Foundry/Hardhat). Reports pass/fail per test and surfaces compile errors clearly before running tests.
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[test name pattern, e.g. TestTransferLog — defaults to running the full suite]"
---

Compile and test go-stablenet's embedded Solidity system contracts, using this repo's actual
toolchain (a custom Go wrapper around `solc`, and Go tests — not `forge`/`hardhat`).

## Step 1: Compile

```bash
go run ./systemcontracts/compile
```

If this fails, report the `solc` error output directly and stop — do not proceed to Step 2 with a
stale or partial `artifacts/` output. Common causes: a syntax error in a recently-edited `.sol`
file, or a version pragma mismatch (`pragma solidity ^0.8.14;` is the convention across this
codebase — check `solidity-patterns` before assuming a version bump is needed).

## Step 2: Test

```bash
go test ./systemcontracts/test/...$([ -n "$ARGUMENTS" ] && echo " -run $ARGUMENTS")$([ -n "$ARGUMENTS" ] && echo " -v")
```

Run the full suite by default; if `$ARGUMENTS` names a pattern, scope to it with `-run` and add
`-v` for per-test output (matches how a human would iterate on one failing test).

## Step 3: Report

```
Compile: OK | FAILED (<error summary if failed>)
Tests:   <N passed> / <N run>  [FAILED: <names>, if any]
```

For any failure, quote the actual `go test` failure output (assertion diff, panic, etc.) rather
than summarizing it away — the exact expected-vs-actual is what the caller needs to act on.

If nothing was specified in `$ARGUMENTS` and the full suite passes, that's sufficient confirmation
for routine changes. For anything touching governance-action routing, storage layout, or
signature verification, remind the caller that a green test suite here is necessary but not
sufficient — `/stablenet-contract-dev:audit-contract` is the adversarial check those changes need.
