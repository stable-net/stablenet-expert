# go-stablenet — L2 in-process simulation building blocks

> Domain-pack content consumed by the `simulation-harness` skill. It lists the **L2**
> building blocks that let a reproduction drive the **real** subsystem objects in ONE process
> (no out-of-process nodes) — so a symptom that would otherwise escalate to L3 (chainbench)
> can often be reproduced in seconds while staying *faithful* (real engine/chain/pool, never a
> stub). The authority for exact symbols/signatures is this project's cks index — confirm with
> `find_symbol` before use; treat the names below as pointers, not a frozen API.

## When L2 is achievable here

A symptom is L2-reproducible when it can be exhibited with real in-process objects and a
deterministic driver — e.g.:
- a governance/header value change followed by an idle (empty-block) window, then asserting a
  consumer reads the new value;
- multi-engine consensus *round progression* in one process (proposer rotation, view dynamics)
  using the real WBFT engine — `N` engines, one or more brought down/delayed;
- send a tx and read the real effective-tip / pool decision;
- a single-node state transition or validation rule.

Still **L3 (chainbench)** when a necessary condition cannot be exhibited without faking it:
true cross-process P2P/discovery, snap/fast-sync between nodes, network partition + recovery,
process crash/restart, or cross-node head/state *divergence*. (This mirrors analyzer §5.0
rule-1 — `simulation-harness` does not loosen it.)

## Building blocks (in-process)

- **In-memory chain**: `rawdb.NewMemoryDatabase()` + `genesis.MustCommit(...)` +
  `core.NewBlockChain(memDB, nil, genesis, nil, engine, vm.Config{}, nil, nil)`.
- **Validator set / genesis**: `consensus/wbft/testutils/genesis.go` — `Genesis`,
  `GenesisWithSeals`, `GenesisAndKeys(n)`, `GenesisAndFixedKeys(n)`.
- **Real consensus engine, in-process**: `consensus/wbft/backend.New(config, nodeKey, memDB)`;
  the multi-engine driver pattern in `consensus/wbft/backend/multiengine_test.go` (`testEnv`:
  several engines, `GoNewRound`, `MustSucceed`, and scenario hooks such as
  `makeScenarioEngineDown` / `DisableCommitMsg` to inject down/delay faults).
- **Block sequence generation**: `core.GenerateChain` (used widely by core tests to build a
  precise block sequence — e.g. a change block followed by N empty blocks).

## Determinism (L2 is the flaky-risk tier)

`testEnv` is goroutine/channel/timer-driven. Keep the reproduction deterministic:
- synchronize on the engine's own signals (e.g. `newRoundReady` / `roundStartChan`), not sleeps;
- set `config.AllowedFutureBlockTime` large and `BlockPeriod = 1` to remove wall-clock coupling;
- run the regression test with `-count=1`;
- name the determinism technique in the test so a reviewer can judge flakiness.

## Mapping

L2 reproductions are `reproduction.json.tier = "simulation"` (an in-process Go test in the
go-stablenet tree) — same tier/contract as L1, authored and gated per the `reproduce-first`
skill. Escalation to `e2e` (L3 / chainbench) follows analyzer §5.0/§5b.
