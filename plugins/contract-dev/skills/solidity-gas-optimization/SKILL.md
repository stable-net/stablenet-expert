---
name: solidity-gas-optimization
description: This skill should be used when reviewing Solidity code for gas efficiency, or when writing new contract code where gas cost matters (governance/token operations that run frequently). Covers storage packing, EnumerableSet iteration cost, custom errors vs require strings, calldata vs memory, and when NOT to micro-optimize at the expense of the storage-slot discipline documented in systemcontracts-structure. This is a Low/Info-severity lens, not a security lens — pair with solidity-security for anything touching correctness.
version: 0.1.0
---

# Solidity Gas Optimization (systemcontracts/)

Gas review for `systemcontracts/` — a Low/Info-severity lens layered on top of correctness and
security review, never a substitute for either.

## What's already good practice here (don't relitigate)

- Custom errors (`error InvalidValidator();` style) instead of `require(cond, "string")` — already
  used throughout `v1`/`v2`/`abstracts`. Don't flag missing custom errors as a finding; do flag a
  *new* function that reverts to `require`+string instead of following the existing convention.
- Storage-slot-numbered layout (see `systemcontracts-structure`) already forces deliberate
  thought about storage packing at the point a variable is added — don't suggest repacking
  existing slots for gas; that reopens the upgrade-safety risk the numbering exists to prevent.
  **Correctness/upgrade-safety wins over gas here, always.**

## What to actually check

- **Unbounded `EnumerableSet` iteration** (validators, members): flagged primarily as a DoS risk
  in `solidity-security`, but even below the DoS threshold it's the single biggest gas cost driver
  in this codebase — a gas review of any function touching validator/member iteration should
  quantify cost growth with set size, not just note "this loops."
- **Redundant external calls**: a governance action handler that re-reads the same storage
  variable multiple times, or re-derives a value already computed earlier in the same call.
- **calldata vs memory** for external function parameters that are only read, not modified —
  `calldata` avoids a copy.
- **Repeated `keccak256` of the same constant string** at call time instead of a compile-time
  `constant`/`immutable` — check new code against the existing `ACTION_*` constant pattern
  (`bytes32 public constant ACTION_SET_GAS_TIP = keccak256("SET_GAS_TIP");`), which already does
  this correctly; flag new action types that don't follow it.
- **Event parameter indexing**: indexed params cost more per-emit but are what off-chain governance
  tooling filters on — don't blanket-recommend removing `indexed`; check whether it's actually
  used for filtering before suggesting the gas trade-off either way.

## Reporting

Gas findings go in a separate section of the review output, ranked by "estimated frequency × cost"
(a function called once at deploy time is not worth the same attention as one called on every
governance vote), not folded into the security severity scale.
