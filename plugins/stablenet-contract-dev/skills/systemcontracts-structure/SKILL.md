---
name: stablenet-contract-dev:systemcontracts-structure
description: This skill should be used whenever working on go-stablenet's embedded Solidity system contracts (systemcontracts/) — reading, writing, reviewing, auditing, or testing any file under systemcontracts/solidity/. Covers the repo layout (v1/v2/libraries/interfaces/abstracts), the custom Go-based compile pipeline (not Foundry/Hardhat), the Go-test-based test harness, and the storage-slot-numbered upgradeable-contract convention used throughout. Load this first, before any Solidity-specific skill, to orient in this codebase's specific toolchain (which differs from the generic Solidity ecosystem).
version: 0.1.0
---

# systemcontracts/ Structure

go-stablenet embeds its governance/token system contracts directly in the repo, at
`systemcontracts/`. This is **not** a Foundry or Hardhat project — it has its own toolchain.
Read this before touching anything under `systemcontracts/`, since the build/test commands and
project conventions here differ from generic Solidity tutorials and from what
`stablenet-contract-dev`'s other skills might otherwise assume from ecosystem defaults.

## Layout

```
systemcontracts/
├── solidity/
│   ├── v1/                 # GovCouncil, GovMasterMinter, GovMinter, GovValidator, NativeCoinAdapter
│   ├── v2/                 # GovMinter (v2) — newer governance revisions land here, v1 stays for compat
│   ├── abstracts/          # GovBase (shared governance base), AbstractFiatToken, Blacklistable, Mintable, eip/*
│   ├── interfaces/         # IFiatToken, IMinterManagement, IBlacklistManagement
│   ├── libraries/          # AddressSetLib, ECRecover, EIP712, MessageHashUtils, SignatureChecker
│   ├── openzeppelin/       # vendored OpenZeppelin contracts (do not edit — see below)
│   └── test/               # Solidity-side test doubles (e.g. MockFiatToken.sol) — NOT the real test suite
├── compile/
│   ├── main.go              # entry point: `go run ./systemcontracts/compile` (flags: -root, -openZeppelin)
│   ├── compiler/compiler.go  # wraps `solc` directly — no Foundry/Hardhat involved
│   └── solcdownloader/       # manages the solc binary
├── artifacts/{v1,v2}/       # compiled ABI/bytecode output
└── test/                    # the REAL test suite — Go tests (package `test`), e.g.
                              # coin_adapter_test.go, gov_council_alloc_sync_test.go
```

## Prerequisite: OpenZeppelin submodules

`systemcontracts/solidity/openzeppelin/contracts` and `.../openzeppelin/contracts-upgradeable` are
**git submodules** (see `.gitmodules` at repo root), not plain vendored files. A checkout that
never ran `git submodule update --init` has these as empty directories, and both compiling and
testing fail with a `solc: exit status 1` / "not found" panic that reads like a source-code
problem but is actually just an uninitialized submodule. Check `git submodule status` for those
two paths (a leading `-` means uninitialized) before debugging anything else. Confirmed live
2026-07-31 — this is exactly what an incomplete/scratch checkout (e.g. one cloned only to build a
`stablenet-knowledge` index, not to build code) looks like.

## Build & test commands

- **Compile**: `go run ./systemcontracts/compile -root=systemcontracts/solidity -openZeppelin=systemcontracts/solidity/openzeppelin`
  from repo root. The binary's own default flag values (`../solidity`) assume it's invoked with
  `systemcontracts/compile/` as the working directory — pass the flags explicitly instead of
  relying on the defaults from repo root, or they resolve to the wrong path and fail with a
  misleading "file not found" even when the source is fine.
- **Test**: `go test ./systemcontracts/test/...` from repo root. Tests import
  `systemcontracts/compile/compiler` directly and deploy compiled bytecode into a simulated
  go-ethereum backend (`types.GenesisAlloc` + friends) — there is no separate `forge test` /
  `hardhat test` step. A contract change is only actually exercised once a Go test deploys and
  calls it; reading the Solidity alone does not tell you it compiles or behaves.
- **No `foundry.toml`, no `hardhat.config.*`, no `package.json` test runner** in this directory.
  Do not suggest `forge`/`hardhat` commands for this codebase — they don't apply here (see
  ADR-0009 §1.2 in `stablenet-expert`'s `docs/adr/` for how this was confirmed).

## The storage-slot-numbered upgradeable pattern

Every governance contract (`GovValidator`, `GovMinter`, `GovMasterMinter`, `GovCouncil`) inherits
`GovBase` and annotates its own storage variables with a hex slot comment, e.g.:

```solidity
address public blsPoP; // 0x32; Precompiled contract address for BLS PoP verification
EnumerableSet.AddressSet private __validators; // 0x33, 0x34; validator addresses
```

`GovBase` reserves `0x0`–`0x31` for its own shared state (member management, proposal/approval
system). **This is a manual storage-layout discipline for upgradeable contracts** — there is no
OpenZeppelin `Initializable`/proxy-storage-gap tooling enforcing it. When reviewing any change to
a governance contract's state variables:

1. Never reorder, resize, or remove an existing numbered slot — it breaks the live upgrade.
2. A new state variable must get the next free slot number in a trailing comment.
3. If `GovBase` itself changes its reserved range, every derived contract's slot numbers shift —
   treat that as a breaking change requiring an explicit migration note, not a routine edit.

## Governance action-type pattern

Derived contracts (`GovMasterMinter`, `GovMinter`, `GovValidator`) define their own action
constants as `keccak256` hashes (e.g. `ACTION_SET_GAS_TIP = keccak256("SET_GAS_TIP")`) and
implement `_executeProposalAction()` to route proposals to the matching handler. When reviewing a
new governance action: check that its handler validates all inputs the same way sibling actions
do (this is where access-control and validation gaps most often hide — see the
`solidity-security` skill's access-control section), and that it's covered by a Go test in
`systemcontracts/test/`.

## What NOT to edit

`systemcontracts/solidity/openzeppelin/` is vendored — treat it as read-only. If a fix seems to
require touching it, that's a signal to re-scope the change to the calling contract instead, or
flag it explicitly as a vendor-code change (rare, needs extra scrutiny) rather than editing it
incidentally.
