# 07 — Domain-Knowledge Curation Plan

> **Derives from:** `00-system-contract.md` (§4 Domain-Knowledge Subsystem) + `06-integration-verification.md`
> (which flagged empty domain content as P0). **Date:** 2026-06-05 · **Method:** 7-persona expert analysis of
> go-stablenet (code + `.claude/docs` + audits/postmortems).
> **Owns:** the system-level *strategy* (clusters, subsystems, activation channels, goal, roadmap). The per-entry
> *execution ledger* (which entry is authored/verified) lives in cks
> `docs/domain-knowledge/projects/go-stablenet/inventory.md`, next to the entries it tracks.

What domain knowledge to collect, how to format/store/activate it, and in what order — so an LLM adding or
modifying go-stablenet code hallucinates less and designs the StableNet way.

---

## 1. Goal & guardrails (the north star — keep in every authoring decision)

go-stablenet = **Ethereum(geth) base + a QBFT-variant consensus renamed WBFT**, whose native coin is a
**KRW stablecoin (symbol `WKRC`, currency `KRW`** — `params/config.go:100`, `core/genesis_mainnet.json:58`),
**not ETH**. Coin **mint/burn is linked to bank deposit/withdrawal** (real-asset backing, via GovMinter
multisig). It targets stablecoin **payments / finance**, and its features evolve under a
**regulation(per-country) ↔ decentralization ↔ privacy** trade-off (hence blacklist/authorize,
governance-controlled validators/minting, governed gas-tip).

**Two load-bearing design constraints every entry must reinforce:**
1. **Ethereum upstream cherry-pick-ability** — StableNet-unique code is *isolated* (added files like
   `eth/handler_istanbul.go`, not edits to `eth/handler.go`) so upstream geth bug-fixes can be cherry-picked.
   `.claude/docs/build-source-files.md` "StableNet 고유 코드 식별" is this principle made concrete.
2. **Ethereum interoperability** — divergence is explained **only against Ethereum** (no Kaia/Klaytn contrast).

The curated knowledge is one half of the larger goal: a cks + coding-agent + bench system that develops this
regulated stablecoin chain quickly and safely with LLM-assisted testing, verification, analysis, and debugging.

---

## 2. Two-tier knowledge model

| Tier | Anchor | Reaches runtime via | Examples |
|------|--------|---------------------|----------|
| **T1 — code-anchored** | `code_anchors` (file:symbol:line) | policy guidance (path-keyed) **+** semantic embedding | seal scheme, blacklist 4 points, round-change timer |
| **T2 — concept-anchored** | contrast / theory (often no single file) | **semantic embedding only** (path-keys don't apply) + L3 backstop | 3f+1 safety, FLP, equal-power philosophy, cherry-pick principle |

T2 is the dimension `06` found ABSENT; it is what turns the LLM into a domain expert. It can only reach
runtime through **channel ②** (§5).

---

## 3. Cluster map (7 domains → subsystems, by name)

| Domain (persona) | Subsystem(s) | Covered (existing entries) | Gap (new) |
|------------------|--------------|----------------------------|-----------|
| go-stablenet protocol (system contracts, governance, state) | WBFT Validator Set & Epoch; System Contracts; Native Coin & Account Extra; Fee Delegation & Anzeon Gas; State Transition | A4/A5/A6/A11 (8 entries) | GovCouncil, GovValidator, GovMasterMinter, AccountManager write-gating |
| Consensus algorithm (WBFT state machine) | WBFT Consensus Core; Validator Set & Epoch | A1.* / A3.* | round-change timer (exp. backoff), F+1 view change, proposer seed, backlog matrix |
| BFT theory | **Protocol Foundations & Design Philosophy** | — | 3f+1 intersection, FLP/partial-synchrony, justification/locking, equivocation |
| Distributed network / timing | Istanbul P2P; Foundations | A9.* | future-block wait, backlog bounds, gossip dedup, timing sec↔ms seam |
| Cryptography | **Cryptographic Primitives & Validator Seals** | (none own `crypto/`) | seal scheme, SealerSet bitpack, randao, feepayer sigHash, BLS/secp256k1 foundations |
| Go concurrency | WBFT Core; (txpool); **Block Production & Sealing** | (none) | lock map, RWMutex discipline, round-change timer lifecycle, reorg-loop serialization, sealer race |
| Blockchain fundamentals + ETH divergence/philosophy | **Protocol Foundations & Design Philosophy** | — | equal-power, instant finality, base-fee redistribution, inert-reorg trap, WKRC≠ETH, **cherry-pick principle** |

---

## 4. New subsystems (approved; named, not coded)

The `id` is an append-only sort key per the subsystems.yaml convention; the **name** is the identifier we use.
Three additions (ids A12–A14, after the existing max A11):

| Name | id | code_paths | Why it's new |
|------|----|-----------|--------------|
| **Cryptographic Primitives & Validator Seals** | A12 | `crypto/` | No subsystem owned `crypto/` — the root cause crypto was ABSENT. Seal/randao/sigHash entries cross-reference `core/types/istanbul.go` (owned by A2) and tx signing (A6/A11) via `code_anchors`, not `code_paths` (non-overlap rule). |
| **Block Production & Sealing** | A13 | `miner/` | No subsystem owned `miner/` — the sealer concurrency entries had no home. |
| **Protocol Foundations & Design Philosophy** | A14 | (none — contrast/theory indexed) | T2 knowledge indexes by concept/contrast, not file ownership. Needs the schema to allow empty `code_paths`. Houses BFT theory, blockchain fundamentals, ETH divergence, the WKRC/regulatory WHY, and the cherry-pick principle. |

---

## 5. Data lifecycle — format, storage, activation

**Format (SSoT):** one YAML entry per file under cks
`docs/domain-knowledge/projects/go-stablenet/entries/*.yaml` (schema: `id, subsystem, knowledge_type B1–B7,
title, summary, status, priority, code_anchors, invariants, pitfalls, aliases, related_concepts`). T1 and T2
share the format; T2 entries leave `code_anchors` empty and carry a contrast table in `summary`.

**Storage modules (who keeps what):**

| Layer | Location | Nature |
|-------|----------|--------|
| Master / curation (SSoT) | cks `docs/domain-knowledge/projects/go-stablenet/{entries, subsystems.yaml, glossary.yaml}` | hand-authored + verified |
| Derived views (generated) | ckv `policy/stablenet.yaml` + ckg `policy.yaml` | `cks-domain-sync` (no hand edits) |
| Embedded | ckv vector store (semantic) + ckg graph (governed_by / concurrency edges) | `ckv build` / `ckg build` |
| Always-on backstop (L3) | coding-agent `plugin/skills/stablenet-invariants/SKILL.md` | index-independent |

**Activation — three channels:**

| Ch | Path | Applies to | Status |
|----|------|-----------|--------|
| ① Guidance injection | entry → cks-domain-sync → ckv policy `watch_out`/`required_tests`, injected on path/category-matched ckv hits | T1 | exists (verified-only) |
| ② **Direct semantic embedding** | entry prose (title+summary+invariants+pitfalls+aliases) indexed as a first-class ckv document → `semantic_search`/`get_for_task` return the entry itself | **T2 (mandatory)** + T1 | **approved — to build** (ckv build also ingests `entries/*.yaml`) |
| ③ Code markers | `// INVARIANT:` / `// CONSENSUS:` seeded in go-stablenet source → ckv Tier-2 extractor | top T1 invariants | optional (operator; 0 markers today) |

**Usage at design time:** the planner calls cks (`semantic_search` / `get_for_task` / `impact_analysis` /
`concurrency_impact`); cks composes an EvidencePack of the relevant invariants, pitfalls, divergence, and
code_anchors; the L3 backstop injects the top invariants regardless. The LLM's context is expanded with "what
must not break + the trap to avoid + the StableNet-way", reducing Ethereum-assuming designs.

---

## 6. Defects to correct first (verified against code, 2026-06-05)

| Defect | Evidence | Fix |
|--------|----------|-----|
| `A3.timing.wbft_config_defaults` says RequestTimeout = 2000ms | code `consensus/wbft/config.go:117` = **1000ms** (engine ms layer; chain-config `RequestTimeoutSeconds=2` — two layers bridged ×1000 at config.go:167) | correct the entry; document the sec↔ms seam |
| `A1.wbft_core.quorum_calc` `risk_level: low`, "int truncation still works for N=4" | quorum-float divergence is consensus-splitting for some N | raise to high; add per-N ceil-vs-int divergence table |
| `core/stablenet_genesis.go` cited in go-stablenet `CLAUDE.md:29` + `.claude/docs/{build-source-files,system-contract-flow,review-guide,code-convention}.md` (NOT in any cks entry — verified) | file **does not exist**; actual = `core/genesis.go` + `genesis_mainnet.json` + `genesis_testnet.json` + `genesis_alloc.go` | correct the 5 go-stablenet doc references (separate go-stablenet change) |

---

## 7. Priority roadmap

| Stage | Work | Effect | Machine |
|-------|------|--------|---------|
| **P0-a** | fix the 3 defects (§6) + move the verification-ready entries (§8) to `verified` + this plan doc | opens the codegen→embedding path (channel ①) | here (go-stablenet present) |
| **P0-b** | build channel ② (ckv embeds `entries/*.yaml`) | T2 knowledge becomes retrievable at all | here (ckv) |
| **P0-c** | register the 3 new subsystems + author the trap-blocking T2 entries (equal-power, instant finality, base-fee redistribution, inert-reorg, **cherry-pick principle**, feepayer sigHash, seal scheme, lock map, reorg serialization, quorum-float) | blocks the top hallucination risks | here / domain-expert |
| **P1** | T1 gaps (4 governance contracts, round-change quantitative, backlog, concurrency hotspots) | code correctness | here |
| **P1/P2** | T2 theory depth (FLP, justification, crypto foundations, distributed timing) | LLM expertise | here / domain-expert |

Rough scope: ~45–55 new entries + verify 23 existing + 3 defect fixes.

---

## 8. Verification-ready entries (promote first — `.claude/docs` + code confirm them)

`A4.system_contracts.addresses`, `A5.account_extra.bit_layout`, `A5.native_coin.issuance_burn_flow`,
`A11.state_transition.blacklist_check_points` (re-confirm 4 line numbers), `A8.genesis.inject_contracts_two_phase`
(fix the stablenet_genesis.go reference first), `A6.anzeon_gas.tip_override` (reconcile line :104 vs doc).
Hold `A7.hardfork.add_new_fork_procedure`: its "newest fork on top in ActiveNativeManagers" invariant is
design-intent, not yet observable in code (`native_manager.go:124` has only `IsAnzeon`) — flag for the verifier.

---

## 9. Top hallucination risks the curation must block (the why)

1. **Stake-weighted voting / slashing** — validators have no power field; equal power = 1.
2. **Reorg / probabilistic-finality logic** — geth `forker`/Td code persists but is inert under instant BFT finality (a trap).
3. **ETH-denominated assumptions** — native asset is WKRC (KRW stablecoin); base fee is **redistributed to validators, not burned**; `Ether=1e18` is geth residue.
4. **Quorum reimplementation** — `ceil(N−F)` "simplified" to int math → split-brain.
5. **Feepayer sigHash** — feepayer signs over `[[inner incl. sender V/R/S], FeePayer]`, not the bare inner tx.
6. **Missing a blacklist enforcement point** (4 points) when adding a tx/transfer path.
7. **Concurrency** — reading `Core.current` off the RWMutex; mutating txpool maps outside the reorg loop.
8. **Breaking cherry-pick-ability** — editing geth core in place instead of isolating StableNet code → upstream merges become impossible.
