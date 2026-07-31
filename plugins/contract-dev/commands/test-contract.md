---
name: contract-dev:test-contract
description: Compile and run the real systemcontracts/ test suite (Go-based — not Foundry/Hardhat). Reports pass/fail per test and surfaces compile errors clearly before running tests.
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[test name pattern, e.g. TestTransferLog — defaults to running the full suite]"
---

Compile and test go-stablenet's embedded Solidity system contracts, using this repo's actual
toolchain (a custom Go wrapper around `solc`, and Go tests — not `forge`/`hardhat`).

## Step 0: OpenZeppelin submodules

`systemcontracts/solidity/openzeppelin/{contracts,contracts-upgradeable}` are git submodules. A
checkout that never ran `git submodule update --init` has these as empty directories, and both
Step 1 and Step 2 fail with a confusing `solc: exit status 1` / "not found" panic that looks like
a source-file problem but isn't. Check first and fix before proceeding:

```bash
git submodule status systemcontracts/solidity/openzeppelin/contracts systemcontracts/solidity/openzeppelin/contracts-upgradeable
# a leading "-" on either line means uninitialized:
git submodule update --init systemcontracts/solidity/openzeppelin/contracts systemcontracts/solidity/openzeppelin/contracts-upgradeable
```

## Step 1: Compile

```bash
go run ./systemcontracts/compile -root=systemcontracts/solidity -openZeppelin=systemcontracts/solidity/openzeppelin
```

Pass `-root`/`-openZeppelin` explicitly (from repo root) — the binary's own default flag values
(`../solidity`) assume it's invoked with `systemcontracts/compile/` as the working directory, which
`go run` from repo root does not do; omitting the flags fails with a misleading "file not found"
even when nothing is actually wrong with the source. Confirmed live 2026-07-31 against
`cks-refactor-2`.

If this fails (after confirming Step 0 passed), report the `solc` error output directly and stop —
do not proceed to Step 2 with a stale or partial `artifacts/` output. Common causes: a syntax
error in a recently-edited `.sol` file, or a version pragma mismatch (`pragma solidity ^0.8.14;`
is the convention across this codebase — check `solidity-patterns` before assuming a version bump
is needed).

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
sufficient — `/contract-dev:audit-contract` is the adversarial check those changes need.
