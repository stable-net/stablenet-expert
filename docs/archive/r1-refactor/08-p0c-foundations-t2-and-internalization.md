# 08 — P0-c: Foundations Subsystems, T2 Entries & coding-agent Internalization

> **Derives from:** `07-domain-knowledge-curation.md` (§4 new subsystems, §7 roadmap, §9 hallucination risks).
> **Date:** 2026-06-05 · **Status of predecessors:** P0-a merged (cks #5), P0-b channel ② merged
> (ckv #3 `build --docs`, cks #7 embedding). This document is the self-contained context + plan for
> executing **P0-c**.

P0-c turns the curated knowledge into a domain-expert layer: register the three missing subsystems,
author the concept-anchored (T2) entries that block the top hallucinations, and internalize the
always-on invariants into the coding-agent plugin — while keeping environment setup simple.

---

## 1. Where we are (recap — what is already merged)

| Capability | State | Where |
|---|---|---|
| 23 domain entries, 7 verified | merged (cks #5) | cks `docs/domain-knowledge/projects/go-stablenet/entries/*.yaml` |
| Entry doc-refs aligned to the #84 split `.claude/docs` | merged (cks #5) | same |
| **Channel ② live**: ckv embeds entries (status `verified`/`needs_verification`) + authoritative docs as markdown | merged (ckv #3 + cks #7) | `cks-domain-export` → `ckv build --docs`; orchestrated by `cks.ops.index` (full mode) |
| Corpus producer | merged | cks `internal/domainexport`, `cmd/cks-domain-export` |
| Subsystems A1–A11 | present | cks `subsystems.yaml` |
| L3 backstop skills (already exist) | present | coding-agent `plugin/skills/stablenet-invariants/SKILL.md`, `plugin/skills/stablenet-context/SKILL.md` |
| Baseline | go-stablenet `@9978930ba` (#84), `crypto/` and `miner/` confirmed present | — |

**Pipeline is ready:** any entry authored with status `verified` or `needs_verification` is embedded by
channel ② on the next `cks.ops.index` full build. P0-c's job is to fill that pipeline with the
concept-level knowledge and to mirror the non-negotiable invariants into the always-on L3 skill.

---

## 2. The central design decision (resolve this first)

**The schema/gating conflict.** `docs/domain-knowledge/shared/entry.schema.yaml` requires
`code_anchors` (`minItems: 1`) for **both** `verified` and `needs_verification` statuses (the verifier
needs something to check). But:

- Channel ② only embeds `verified` + `needs_verification` (P0-b D2).
- The whole point of T2 (07 §2) is that concept-anchored knowledge — *which often has no single code
  anchor* — must reach runtime, and channel ② is its only path.

So a purely concept-anchored entry cannot currently be both (a) embeddable and (b) schema-valid. This
must be resolved before authoring T2 entries.

| Option | Mechanism | Trade-off |
|---|---|---|
| **A (recommended)** | Give most T2 entries an **illustrative code_anchor** — the code region the concept governs (e.g. inert-reorg → `core/forkchoice.go`; base-fee → the finalize/fee path; feepayer-sigHash → `core/types/tx_fee_delegation.go`). They become `needs_verification` and embed normally. | Works for ~7 of 10 traps; faithful (the anchor *is* where the trap bites). Pure theory (FLP, 3f+1 intersection) still has no anchor. |
| B | Add a schema branch: a `concept_anchored: true` (or knowledge_type `B8: Theory`) entry may be `needs_verification`/`verified` with **0** code_anchors, requiring instead ≥1 `related_concepts` or `existing_doc_ref`. | One schema change + validator update; lets pure-theory entries embed. Most general. |
| C | Pure-theory traps live **only** in the L3 skill (always-on, index-independent), not in channel ②. | Zero schema change; but theory is not semantically retrievable, only injected wholesale. The L3 skill already carries the top ones. |

**Recommendation:** A for everything that has a governing code region; **B** for the handful of pure
theory entries we still want retrievable (3f+1 intersection, FLP/partial-synchrony, justification/
locking, equivocation); **C** as the safety net regardless (these invariants belong in L3 too). The
existing L3 skill already encodes EQUAL POWER, epoch asymmetry, round-change neutrality — so C is
partly done.

> Decide A-only vs A+B before authoring. If A+B, the schema change is its own small task (update
> `entry.schema.yaml` `allOf` + `internal/inventory/validate.go` + a test) and ships first.

---

## 3. New subsystems (append-only; ids A12–A14)

`subsystems.yaml` ids are an append-only sort key (never renumber); the **name** is the identifier.
Max existing id is A11. `code_paths` must not overlap with other subsystems' paths.

| id | name | code_paths | Rationale |
|---|---|---|---|
| **A12** | Cryptographic Primitives & Validator Seals | `crypto/` | No subsystem owned `crypto/` — root cause crypto knowledge was absent. Seal/randao/sigHash entries cross-reference `core/types/istanbul.go` (A2) and tx signing (A6) via `code_anchors`, not `code_paths` (non-overlap rule). `crypto/` confirmed present (crypto.go, signature_cgo.go, signature_nocgo.go). |
| **A13** | Block Production & Sealing | `miner/` | No subsystem owned `miner/` — the sealer-concurrency entries had no home. `miner/` confirmed present (miner.go, ordering.go, payload_building*). |
| **A14** | Protocol Foundations & Design Philosophy | *(none)* | T2 indexes by concept/contrast, not file ownership. Houses BFT theory, blockchain fundamentals, ETH divergence, the WKRC/regulatory WHY, the cherry-pick principle. The subsystem loader requires only a non-empty `id`; empty `code_paths` is accepted. Confirm `cks-inventory-check` does not warn on an empty `code_paths` (adjust the validator if it does). |

---

## 4. T2 entry catalog (the trap each one blocks)

Author these as `needs_verification` (carry the illustrative anchor per §2 Option A) unless marked
*pure-theory*. Each blocks a documented hallucination (07 §9). Re-confirm every anchor against
go-stablenet `@9978930ba` before setting status.

| Proposed id | Subsystem | Trap it blocks | Candidate code anchor / source |
|---|---|---|---|
| `A14.foundations.equal_power` | A14 | Stake-weighted voting / slashing — validators have **no power field**, power = 1 | `consensus/wbft/validator/` (no weight field). Already in L3 skill. |
| `A14.foundations.instant_finality_inert_reorg` | A14 | Reorg / probabilistic-finality logic is a **trap**: geth `forker`/Td code persists but is inert under instant BFT finality | `core/forkchoice.go`, `core/blockchain.go` (Td path) |
| `A14.foundations.base_fee_redistribution` | A14 | ETH assumption "base fee burned" — StableNet **redistributes base fee to validators** | the finalize/fee-settlement path (consensus/wbft engine finalize) |
| `A14.foundations.wkrc_not_eth` | A14 | ETH-denominated assumptions — native asset is **WKRC (KRW stablecoin)**; `Ether=1e18` is geth residue | `params/config.go:100`, `core/genesis_mainnet.json:58` |
| `A14.foundations.cherry_pick_principle` | A14 | Editing geth core in place instead of **isolating StableNet code** → upstream merges break | *pure-doc*: `.claude/docs/build-source-files.md` "StableNet 고유 코드 식별"; CLAUDE.md unique-code map |
| `A12.seals.feepayer_sighash` | A12 (xref A6) | Feepayer signs over `[[inner incl. sender V/R/S], FeePayer]`, **not** the bare inner tx | `core/types/tx_fee_delegation.go` (setSignatureValues / sigHash) |
| `A12.seals.bls_seal_scheme` | A12 (xref A2) | Seal scheme: BLS 96-byte seals, SealerSet bitpack, randao | `crypto/`, `core/types/istanbul.go` (WBFTExtra) |
| `A1.concurrency.core_lock_discipline` | A1 (xref A13) | Reading `Core.current` off the RWMutex; lock-map ordering | `consensus/wbft/core/` (RWMutex, current) |
| `A13.sealing.reorg_serialization` | A13 | Mutating txpool maps **outside the reorg loop**; sealer race | `core/txpool/`, `miner/` |
| `A1.wbft_core.quorum_calc` (exists) | A1 (xref A14) | `ceil(N−F)` "simplified" to `2f+1` → split-brain for N≠3f+1 | already authored; **held** `needs_verification` pending a correctness review (QBFT spec + N=1..20 unit test) — see §6 |
| *pure-theory (Option B):* `A14.theory.3f1_intersection`, `A14.theory.flp_partial_synchrony`, `A14.theory.justification_locking`, `A14.theory.equivocation` | A14 | The BFT safety/liveness reasoning behind the above | no code anchor — requires §2 Option B or lives in L3 only |

Rough scope: ~10 trap entries + ~4 theory entries + 3 subsystem registrations.

---

## 5. coding-agent internalization (the new requirement)

Per the 2026-06-05 direction (memory `go-stablenet-docs-distribution`): the curated invariants must be
**internalized into the coding-agent plugin** (always-on L3) **and** embedded in ckv via cks (channel
②, done) — and **environment setup must stay simple** (do not require every repo to be cloned/installed
at query time).

**What already exists (augment, don't recreate):**
- `plugin/skills/stablenet-invariants/SKILL.md` — already encodes EQUAL POWER, epoch-length asymmetry,
  round-change neutrality. It is the L3 backstop the 07 plan §5 describes.
- `plugin/skills/stablenet-context/SKILL.md` — companion context skill.

**P0-c work here:** extend `stablenet-invariants` with the remaining non-negotiable traps not yet
present — **instant-finality / inert-reorg, base-fee redistribution, WKRC≠ETH, cherry-pick principle,
feepayer sigHash, quorum-float** — phrased as "violating this is a bug even if tests pass," matching the
existing numbered style. Keep it in lockstep with the cks A14/A12 entries (same wording, so retrieval
and backstop agree). The skill is the index-independent layer; channel ② is the retrievable layer; they
must not contradict.

**Setup-simplicity constraint:** the go-stablenet `CLAUDE.md`/`.claude/docs` are distributed by a
**separate repo + install script** (untracked in go-stablenet) and are committed by the user. Treat
them as a *source* to internalize/embed, **not** a runtime dependency. Knowledge an agent needs while
working on go-stablenet should be carried by coding-agent (L3) + cks/ckv (channel ②), so a checkout
needs neither the docs-distribution repo nor every sibling repo present.

---

## 6. Carry-over open items (from P0-a/P0-b)

- **`A1.wbft_core.quorum_calc` correctness review** — its claim about `ceil(N−F)` vs `2f+1` divergence
  and int-precision was flagged for a QBFT-spec cross-check + an `N=1..20` unit test before promotion to
  `verified`. P0-c's quorum-float theory entry (A14) should be authored alongside this review.
- **`9f7fdf1` direct-to-main commit** (cks) — the channel-② stale-corpus-sweep fix was pushed directly
  to `main` after PR #7 merged (the local checkout had switched to main). It is small, tested, and green;
  flagged for the user to keep as-is or re-do via PR. Not a P0-c blocker.

---

## 7. Execution sequence

1. **Decide §2** (A-only vs A+B). If A+B: ship the schema change (`entry.schema.yaml` + `validate.go` +
   test) first.
2. **Register A12–A14** in `subsystems.yaml`; confirm `cks-inventory-check` passes (empty `code_paths`
   on A14 must not error — adjust validator if needed).
3. **Author the T2 entries** (§4) as `needs_verification` with verified anchors; run
   `cks-inventory-check -project ...` (with `GO_STABLENET_ROOT` set) to 0 errors.
4. **Augment `stablenet-invariants` SKILL** (§5) with the remaining traps, aligned to the entries.
5. **Refresh the index**: `cks.ops.index` (mode=full) regenerates the corpus and runs
   `ckv build --docs` so the new entries + subsystems embed. (Requires the Ollama daemon with bge-m3.)
6. **Verify retrieval**: a `semantic_search` for "is the native coin ETH?" / "can validators be
   stake-weighted?" / "is a reorg possible after finality?" should surface the matching A14 entry.

Commit per repo via branch→PR; English summaries; no co-author.

---

## 8. Quick reference — facts to author against

| Fact | Value | Source |
|---|---|---|
| Native coin | symbol `WKRC`, currency `KRW` (not ETH) | `params/config.go:100`, `core/genesis_mainnet.json:58` |
| Quorum | `QuorumSize = ceil(N − F)`, `F = (N−1)/3` in float64 | A1.quorum_calc; `consensus/wbft` |
| System contracts | `0x1000`–`0x1004` (config_wbft.go:32–44); precompiles `0xB00002`/`0xB00003` (protocol_params.go:219–220) | A4.addresses (verified) |
| Account Extra | bit 63 Blacklisted, bit 62 Authorized | `core/types/state_account_extra.go:33,36` (A5.bit_layout, verified) |
| Blacklist gates | 4 points: state_transition.go:504/509/577 + evm.go:213/217/480 | A11 (verified) |
| Fee delegation tx | type `0x16`, double-sig; feepayer signs `[[inner incl sender V/R/S], FeePayer]` | A6.signing_model; `core/types/tx_fee_delegation.go` |
| Genesis builders | `DefaultStableNetMainnet/TestnetGenesisBlock` in `core/genesis.go:617,626` (file `stablenet_genesis.go` does **not** exist) | A8.inject (verified) |
| crypto / miner dirs | both present at `@9978930ba` | go-stablenet |
| L3 backstop | `coding-agent plugin/skills/stablenet-invariants/SKILL.md` (already exists) | coding-agent |
| Channel ② gating | embeds `verified` + `needs_verification` only; each doc shows its Status | P0-b D2 |

---

## 9. Top hallucination risks this must close (the why — from 07 §9)

1. Stake-weighted voting / slashing — validators have equal power = 1.
2. Reorg / probabilistic-finality logic — inert under instant BFT finality (a trap).
3. ETH-denominated assumptions — native asset is WKRC; base fee **redistributed to validators**, not burned.
4. Quorum reimplementation — `ceil(N−F)` "simplified" to int/`2f+1` → split-brain.
5. Feepayer sigHash — signs the wrapped structure, not the bare inner tx.
6. Missing a blacklist enforcement point (4 points) on a new tx/transfer path.
7. Concurrency — reading `Core.current` off the RWMutex; mutating txpool maps outside the reorg loop.
8. Breaking cherry-pick-ability — editing geth core in place instead of isolating StableNet code.
