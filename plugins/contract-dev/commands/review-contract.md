---
name: contract-dev:review-contract
description: Review systemcontracts/ Solidity code for pattern/convention adherence and gas efficiency, using parallel category reviewers. Security is NOT covered here — use /contract-dev:audit-contract for that.
allowed-tools: Bash, Agent, Read, Glob, Grep, ToolSearch
argument-hint: "[path/to/contract.sol or directory, defaults to systemcontracts/solidity]"
---

Review Solidity code in `systemcontracts/` across two categories — patterns/conventions and gas —
using parallel `reviewer` agent dispatches. This command does not cover security; run
`/contract-dev:audit-contract` for an adversarial security pass.

## Step 1: Identify files

If `$ARGUMENTS` provides a path, use it. Otherwise default to everything under
`systemcontracts/solidity/` except the vendored `openzeppelin/` tree and test doubles:

```bash
find systemcontracts/solidity -name "*.sol" \
  -not -path "*/openzeppelin/*" \
  -not -path "*/test/*"
```

If this is being run against a diff (e.g. reviewing a pending change), prefer the actually-changed
files (`git diff --name-only` filtered to `*.sol`) plus each changed file's `GovBase` parent for
context, over a full-repo sweep.

Present the file list to the user for confirmation before dispatching reviewers.

## Step 2: Dispatch category reviewers in parallel

Dispatch two `reviewer` agents concurrently (single message, multiple `Agent` calls), each with
the same file list but a different `category`:

- `category=patterns` — loads `solidity-patterns`
- `category=gas` — loads `solidity-gas-optimization`

## Step 3: Consolidate

Merge both agents' findings into one report:

```
# Contract Review: <scope>

## Patterns & Conventions
<patterns reviewer's findings, or "No findings.">

## Gas
<gas reviewer's findings, or "No findings.">
```

If either reviewer reports zero findings, say so plainly rather than omitting the section.

## Step 4: Suggest next steps

If the diff touches governance-action routing, storage variables, or anything signature-related,
tell the user explicitly to also run `/contract-dev:audit-contract` — this command's
reviewers do not do adversarial security analysis.
