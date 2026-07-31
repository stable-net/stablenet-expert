# contract-dev

A Claude Code plugin for writing, reviewing, and auditing the Solidity smart contracts embedded
in **go-stablenet**'s `systemcontracts/` — governance (`GovValidator`/`GovMinter`/
`GovMasterMinter`/`GovCouncil`), the native-coin adapter, and the shared libraries/interfaces they
depend on.

`contract-dev` is the **Contract Development** plugin of the
[`stablenet-expert`](../../README.md) marketplace — the counterpart of `compact-core` in
[midnight-expert](../../../references/midnight-expert), scoped to Solidity/EVM instead of Compact
(see [ADR-0005 §2.4](../../docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)).

## Scope: 1st stage only

This plugin currently covers **only** `systemcontracts/` inside the go-stablenet repo — not
general Solidity/EVM development against arbitrary Foundry/Hardhat projects. That's a deliberate,
phased scope decision; see
[ADR-0009](../../docs/adr/ADR-0009-contract-dev-plugin-design.md) for why, and for what
a later general-EVM stage would need to add.

**This repo doesn't use Foundry or Hardhat.** `systemcontracts/` has its own toolchain: a custom
Go wrapper around `solc` for compiling, and Go tests (not `.t.sol`/JS test suites) for testing.
Every agent and skill here is written against that actual toolchain — see the
`systemcontracts-structure` skill for the details.

## No MCP server, by design

Unlike `core-dev`, this plugin registers **no MCP servers**. It reads `systemcontracts/` directly
via `Read`/`Grep`/`Glob`. This isn't a missing feature — it's a direct consequence of a bug found
while building this plugin: registering a second connection to `core-dev`'s `stablenet-knowledge`
MCP server under a different plugin name breaks one of the two plugins whenever both are enabled
together (which is the normal case for someone doing full go-stablenet development, contracts
included). See ADR-0009 §2.3 for the full account.

## Commands

| Command | What it does |
|---|---|
| `/contract-dev:test-contract [pattern]` | Compile (`go run ./systemcontracts/compile`) and run the real Go test suite (`go test ./systemcontracts/test/...`), optionally scoped to one test. |
| `/contract-dev:review-contract [path]` | Parallel patterns + gas review (no security). |
| `/contract-dev:audit-contract [path]` | Adversarial security review, with Critical/High findings mechanically confirmed by actually running a `go test` against the claim. |

## Agents

| Agent | Role |
|---|---|
| `contract-dev` | Writes/modifies Solidity following this codebase's conventions, verifies its own change against the real test suite. Directly invocable. |
| `reviewer` | Category-scoped review (`patterns` or `gas`), dispatched by `/review-contract`. Not for direct use. |
| `security-reviewer` | Adversarial security specialist — access control, reentrancy, signature/replay, storage-slot collisions, unbounded iteration. Emits Verification Requests instead of self-verifying (can't spawn subagents). Directly invocable. |

## Skills

- `systemcontracts-structure` — repo layout, build/test commands, storage-slot convention,
  governance action-type pattern. Load this first for anything in `systemcontracts/`.
- `solidity-patterns` — codebase conventions (GovBase shape, custom errors, v1/v2 coexistence,
  OpenZeppelin vendoring boundary).
- `solidity-security` — the adversarial threat model (access control, reentrancy, signatures,
  storage collisions, DoS, trust boundaries) and the Verification Requests protocol.
- `solidity-gas-optimization` — gas review, explicitly subordinate to correctness/upgrade-safety.

## Install

```bash
claude plugin install --scope user contract-dev@stablenet-expert
```
