---
name: contract-dev:solidity-patterns
description: This skill should be used when writing new Solidity code for systemcontracts/, or when reviewing whether new code follows this codebase's existing conventions. Covers the GovBase inheritance pattern, custom-error style, the ACTION_* governance-action convention, OpenZeppelin usage boundaries, and how v1 vs v2 contracts coexist. This is the "match the existing codebase" lens — for correctness use solidity-security, for gas use solidity-gas-optimization.
version: 0.1.0
---

# Solidity Patterns & Conventions (systemcontracts/)

Codebase-specific conventions for `systemcontracts/solidity/`. The goal of this skill is
consistency with existing code, not general Solidity best-practice advocacy — when this skill and
generic Solidity style advice disagree, follow what's already in the repo unless there's a
correctness or security reason not to (route that to `solidity-security`).

## Governance contract shape

Every governance contract (`GovValidator`, `GovMinter`, `GovMasterMinter`, `GovCouncil`) follows
the same shape:

1. `contract X is GovBase { ... }` — inherits shared member/proposal/approval machinery.
2. A block of `error` declarations at the top (custom errors, not `require` strings).
3. Storage variables with trailing hex-slot comments, starting after `GovBase`'s reserved
   `0x0`–`0x31` range (see `systemcontracts-structure`).
4. `bytes32 public constant ACTION_*` constants (`keccak256` of an action name string) for every
   governance action this contract supports.
5. `_executeProposalAction()` override that switches on the action constant and routes to a
   private handler.

New governance contracts, or new actions on existing ones, should follow this exact shape. A
proposal handler that doesn't validate its inputs as strictly as its siblings is both a style
deviation and a likely security gap — flag it in both lenses.

## v1 vs v2 coexistence

`v2/GovMinter.sol` exists alongside `v1/GovMinter.sol` — v2 is a newer governance revision, v1
stays deployed for contracts that haven't migrated. When asked to modify "the minter", **check
which version is actually in scope** — don't assume v1 is legacy-and-ignorable or that v2 is a
drop-in replacement; they may differ in action set or validation logic. If a change should apply
to both, say so explicitly rather than silently editing only one.

## OpenZeppelin usage

`openzeppelin/` is vendored, not a package dependency — contracts import it with relative paths
(see `GovValidator.sol`'s `import "@openzeppelin/contracts/utils/structs/EnumerableSet.sol";` —
resolved via the vendored copy, not npm/forge deps). Do not suggest `npm install @openzeppelin/contracts`
or a Foundry `forge install` — there is no package manager step; the vendored files are the
source of truth for this repo. Never edit `openzeppelin/` (see `systemcontracts-structure`'s "what
NOT to edit").

## Custom errors, not require-strings

Every existing contract declares typed `error X();` (or `error X(uint256 got, uint256 want);`
where a value is useful for debugging) rather than `require(cond, "message")`. New code should
match this — it's both the existing style and cheaper (see `solidity-gas-optimization`).

## Interfaces

`interfaces/{IFiatToken,IMinterManagement,IBlacklistManagement}.sol` define the external contract
surface consumed by the token/adapter layer. A change to a governance contract's public function
signature that's part of one of these interfaces is a breaking change for every consumer — check
`interfaces/` before renaming or resigning a public function, not just the implementation file.
