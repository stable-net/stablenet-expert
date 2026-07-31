---
name: contract-dev:audit-contract
description: Adversarial security audit of systemcontracts/ Solidity code. Runs a single security-reviewer specialist pass, then mechanically confirms Critical/High findings by running the emitted Verification Requests as real `go test` invocations, and synthesizes a consolidated security report. Security-only; for patterns/gas use /contract-dev:review-contract.
allowed-tools: Bash, Agent, Read, Glob, Grep, ToolSearch
argument-hint: "[path/to/contract.sol or directory, defaults to systemcontracts/solidity]"
---

Run a focused security audit: one deep `security-reviewer` pass, then main-thread mechanical
confirmation of Critical/High findings via the real test harness. You (the main thread) are the
orchestrator — `security-reviewer` cannot dispatch subagents or run its own verification, so you
run all confirmations yourself.

## Step 1: Identify files

Same file-discovery rule as `/contract-dev:review-contract` Step 1 — use `$ARGUMENTS` if
given, otherwise default to `systemcontracts/solidity/` excluding `openzeppelin/` and `test/`
doubles. For a governance-contract target, always include its `GovBase` parent in the file list —
the security reviewer needs it for the shared member/proposal machinery, not just the leaf
contract.

Present the file list for confirmation before dispatching.

## Step 2: Dispatch security-reviewer

Dispatch a single `security-reviewer` agent with the confirmed file list. Wait for its full
findings report plus its `## Verification Requests` block.

## Step 3: Confirm Critical/High findings

For each Verification Request in the agent's output:

1. If it includes a ready-to-run Go test snippet, write it to a scratch file under
   `systemcontracts/test/` (a throwaway name, clearly temporary — e.g.
   `zz_audit_scratch_test.go`) and run:
   ```bash
   go test ./systemcontracts/test/... -run <TestName> -v
   ```
2. If it's a manual call-sequence instead, run the equivalent via `go test -run` against the
   nearest existing test in `systemcontracts/test/` that already deploys the target contract, or
   write the minimal harness yourself following that file's conventions.
3. Record the verdict: **Confirmed** (test demonstrates the issue), **Not reproduced** (test ran
   but didn't show the claimed behavior — note this could mean the finding is wrong, or the
   verification harness didn't capture it; say which you believe and why), or **Blocked**
   (couldn't run — say why, e.g. missing fixture).
4. **Delete the scratch test file** once done, regardless of verdict — it must not linger in the
   repo as a side effect of an audit run.

## Step 4: Synthesize the report

```
# Security Audit: <scope>

## Summary
<N Critical, N High, N Medium, N Low/Info — plus how many Critical/High were Confirmed>

## Findings
<full findings list from security-reviewer, each annotated with its confirmation verdict from
Step 3 where applicable>
```

Confirmed Critical/High findings should be the most prominent thing in the report — they are the
ones a human needs to act on before this code ships.
