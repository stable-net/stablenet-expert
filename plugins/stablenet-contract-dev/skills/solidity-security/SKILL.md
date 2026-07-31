---
name: stablenet-contract-dev:solidity-security
description: This skill should be used when performing a security review or audit of Solidity smart contract code, or when reasoning about a contract's threat model. Covers reentrancy, access control, signature/replay attacks (EIP-712/EIP-2612/EIP-3009), upgradeable-storage collisions, unchecked external calls, denial-of-service via unbounded iteration, and governance/proposal-system-specific pitfalls (the pattern used throughout go-stablenet's systemcontracts/). Defines the Verification Requests protocol used by the security-reviewer agent. Load stablenet-contract-dev:systemcontracts-structure first for the repo-specific storage-slot and governance-action conventions this skill assumes.
version: 0.1.0
---

# Solidity Security Threat Model

This is the "how to think like an attacker" layer for `stablenet-contract-dev`. It assumes the
repo conventions from `systemcontracts-structure` (storage-slot discipline, governance
action-type routing) and adds the general Solidity/EVM threat model on top.

## Threat categories

### 1. Access control

- Every state-changing external/public function: who can call it, and is that check actually
  enforced (not just documented in a comment)?
- Governance actions (`_executeProposalAction()` handlers): does the new action require the same
  approval/quorum path as sibling actions, or does it bypass the proposal system entirely?
- `onlyOwner`/role-gated functions: confirm the modifier is actually applied, not just declared
  and unused (a classic copy-paste miss).

### 2. Reentrancy

- Any function that makes an external call (token transfer, low-level `call`, another contract's
  function) before finishing its own state updates — checks-effects-interactions violation.
- `NativeCoinAdapter` and any minting/burning path are the highest-value reentrancy targets in
  this codebase (they move value). Trace every external call in these paths explicitly.
- Cross-function reentrancy: an external call in function A that lets an attacker re-enter through
  function B while A's state is still mid-update.

### 3. Signature / replay attacks

`libraries/EIP712.sol`, `MessageHashUtils.sol`, `SignatureChecker.sol`, and `abstracts/eip/{EIP2612,EIP3009,EIP712Domain}.sol`
mean this codebase does meta-transactions and permit-style signed approvals. For any signature
-verification path:

- **Nonce/replay**: is there a nonce (or equivalent) that's consumed atomically with verification,
  so the same signature can't be replayed?
- **Domain separation**: does the EIP-712 domain separator bind chain ID and contract address, so
  a signature valid on one deployment can't be replayed on another (fork, testnet, upgraded
  contract)?
- **Signature malleability**: does `ECRecover`/`SignatureChecker` reject non-canonical `s` values
  and `v` outside `{27, 28}`?
- **BLS key handling** (`GovValidator.blsPoP`, `validatorToBlsKey`): is a submitted BLS key's
  proof-of-possession actually verified before it's trusted, or only length-checked
  (`InvalidBlsKeyLength` alone is not proof of a valid key)?

### 4. Upgradeable-storage collisions

See `systemcontracts-structure` for the slot-numbering convention. A security review of any diff
touching a governance contract's state variables MUST check: no existing slot number reused,
resized, or reordered. This is not a style nit — it's a live-upgrade-corrupting bug class, and it
does not show up in a normal Go test unless the test specifically exercises an upgrade path.

### 5. Unbounded iteration / DoS

`EnumerableSet.AddressSet` (validators, members) is iterated in several places. A function that
loops over an unbounded set in a single transaction (e.g. iterating all validators to tally votes)
is a DoS vector once the set grows large enough to exceed the block gas limit. Flag any loop whose
bound is user-growable state, not a fixed constant.

### 6. Untrusted external calls / integration boundaries

- `NativeCoinAdapter`: what does it trust from the native-coin side of the bridge, and what could
  a malicious or buggy counterpart on that side do to it?
- Blacklist checks (`Blacklistable`): are they applied on every value-transfer path, including
  ones added later (e.g. a new mint/burn variant that forgets the check)?

## Verification Requests protocol

For Critical/High findings, don't just assert them — propose a concrete, mechanical way to
confirm them:

- **Preferred**: a minimal Go test snippet (matching `systemcontracts/test/` conventions) that
  deploys the affected contract(s) and demonstrates the exploit or the missing check failing.
- **Acceptable**: a precise call sequence (function, args, expected vs. actual state) the caller
  can run manually via `go test -run` against a scratch test file.

The `security-reviewer` agent (see `agents/security-reviewer.md`) cannot run these itself — it
emits Verification Requests, and the `/stablenet-contract-dev:audit-contract` command runs them
via `test-contract.md`'s test harness and reports which findings were mechanically confirmed vs.
still theoretical.

## Severity grading

- **Critical**: funds can be stolen, minted arbitrarily, or governance can be taken over.
- **High**: a specific actor can bypass an intended restriction (blacklist, approval quorum,
  validator admission) under realistic conditions.
- **Medium**: correctness bug with no direct fund/governance impact, or a DoS requiring
  significant attacker resources.
- **Low/Info**: defense-in-depth, gas, or style — route to `solidity-gas-optimization` or
  `solidity-patterns` instead of inflating the security report.
