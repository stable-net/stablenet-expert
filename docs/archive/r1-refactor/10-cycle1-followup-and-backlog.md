# 10 — R1' Cycle 1: follow-up and backlog

> **Date**: 2026-06-08. **Status**: Cycle 1 closed (9 PRs squash-merged,
> 36 verified entries, 112 `governed_by` edges in ckg). This document
> tracks (a) follow-up items surfaced during the closing session — fixes
> that did not block Cycle 1 but should be revisited — and (b) the
> backlog the next cycle starts from.
>
> The Cycle 1 docs that this entry sits alongside:
> [06](06-integration-verification.md) (integration audit),
> [07](07-domain-knowledge-curation.md) (curation spec),
> [08](08-p0c-foundations-t2-and-internalization.md) (T2 traps + skill),
> [09](09-alignment-deep-dive.md) (ckv alignment + cross-module defects),
> [plans/TEMPLATE.md](plans/TEMPLATE.md) (post-Cycle plan template).

---

## 1. What closed in Cycle 1 (summary)

| Repo | PR | Outcome |
|---|---|---|
| ckg | #15 | `score_contract_test.go` — SearchFTS / go-stablenet M2.d guards |
| ckv | #4 | `internal/ckgalign` — 4-step in-process alignment (98.4% symbol coverage) |
| cks | #8 | r1-refactor: 13 domain entries + composer Hit metadata + governs qualifier |
| coding-agent | #6 | r1-refactor: 06 audit + 09 alignment + plans/TEMPLATE |
| cks | #9 | `cks-promotion-worksheet` tool + STATUS_LIFECYCLE wiring |
| cks | #10 | promote 29 entries to verified (P0 #8 closed) |
| ckv | #5 | regenerate `policy/stablenet.yaml` from 36 verified entries (14 categories) |
| ckg | #16 | add `policies/stablenet/policy.yaml` (36 per-entry policies) |
| cks | #11 | fix `base_fee_redistribution` summary line drift (`:174 → :180`) |
| coding-agent | #7 | `.gitignore` parity — ignore `.claude/settings.local.json` |

Activation observable in ckg after the closing build:
- 220,655 nodes / 1,930,117 edges
- **36 Policy nodes** (1:1 with verified entries)
- **112 `governed_by` edges** (Cycle 1 baseline was 30; +273%)
- Representative anchor: `validator.defaultSet.QuorumSize` is governed
  by four entries (`A1.wbft_core.quorum_calc`,
  `A14.foundations.equal_power`, `A14.theory.3f1_intersection`,
  `A14.theory.flp_partial_synchrony`) — the quorum surface fans out to
  every invariant that depends on it, which is the intended retrieval
  shape.

## 2. Follow-up items (Cycle 1 surfaces, not blockers)

These were observed while finishing Cycle 1 but did not justify a
re-open. They belong in the next available cleanup PR or in Cycle 2's
opening sweep.

### 2.1 `A14.foundations.wkrc_not_eth` — anchor has no `symbol`

The entry's two `code_anchors[]` carry `file` + `line` + `reason` but
no `symbol`. `cks-domain-sync` emits `governs[]` only when the anchor
resolves to a qualified name; with no symbol it emits an empty
`governs[]`, and ckg in turn produces **zero `governed_by` edges**
for this policy.

Quick fix (single edit to the entry):

```yaml
code_anchors:
  - file: params/config.go
    symbol: NativeCoinAdapter             # ADD
    line: 100
    reason: "WKRC native-coin definition..."
```

The `NativeCoinAdapter` field is the right qualification: `params/config.go:100` is the literal map inside its `Params` field. Adding the symbol gives `cks-domain-sync` a qname to emit and ckg a node to anchor on. Expected outcome on rebuild: ≥ 1 new `governed_by` edge.

The second anchor (`core/genesis_mainnet.json:58`) is JSON; ckg doesn't index JSON at symbol level, so leaving it without a symbol is correct.

### 2.2 `cks-domain-sync` — 9 `governs[] target not found` warnings

Build log at 2026-06-08 03:26:58 emitted nine `policy governs[] target not found` warnings during ckg's policy enrichment pass. Each is a qname `cks-domain-sync` constructed that ckg's graph couldn't resolve:

| Entry | Target qname emitted | Likely issue |
|---|---|---|
| A10.codegen.contract_regen_procedure | `compiler.compiledTy.ExportContractCode` | `compiledTy` is a Go type, not a package — qname should be `compiler.ExportContractCode` (method on the type) |
| A10.codegen.contract_regen_procedure | `compiler.solcVersion` | Package-private constant; may not be indexed by ckg (unexported in same package) |
| A13.sealing.reorg_serialization | `legacypool.queueTxEvent` | Probably needs file-package qname mapping (`legacypool` is folder name, package name might differ) |
| A14.foundations.cherry_pick_principle | `docs.StableNet 고유 코드 식별` | Pseudo-qname from a markdown section heading; ckg doesn't parse markdown |
| A3.validator_set.epoch_transition | `backend.Backend.GetValidators` | The entry's anchor symbol is `Backend.GetValidators`; qname collision with package name `backend` |
| A3.validator_set.epoch_transition | `params.WBFTConfig.Epoch` | Same shape — `WBFTConfig.Epoch` is a field, ckg may index fields under a different qname |
| A9.istanbul_p2p.protocol_architecture | `eth.EthPeerRegistered` | Field on struct; qname collision |
| A9.istanbul_p2p.protocol_architecture | `eth.quorumConsensusProtocolLengths` | Unexported package variable |
| A9.istanbul_p2p.protocol_architecture | `eth.wbft.ErrStoppedEngine` | Double-package qname (`eth.wbft.…`) — `cks-domain-sync` may be emitting a folder-derived prefix instead of the imported-package symbol |

Net cost today: ~9 missed `governed_by` edges (small fraction of the
112 that do land). The fix lives in `cks-domain-sync`'s qname
construction (`pkg/sync/qname.go` or wherever the file→package
heuristic sits) or in the entries themselves (add an explicit
`qualified_name` override field). Pick one of:

- **A. Tighten the heuristic in `cks-domain-sync`**: handle field
  qnames, type-method qnames, and unexported symbols. Higher upfront
  cost; benefits every future project.
- **B. Add a per-anchor override field**: e.g.
  `anchor.qualified_name: "<exact qname>"` that bypasses the heuristic.
  Smaller code change; pushes the burden onto curators.

A is the cleaner long-term fix; B is the right Cycle-2-opening sweep.

### 2.3 `A14.foundations.base_fee_redistribution.summary` — `:174` reference (FIXED in PR #11)

Already closed. Listed here only so the reader doesn't go looking for
it as an open item.

### 2.4 ckg's `runIncremental` path is unexpectedly slow

The first attempt at the closing `ckg build --force` ran for 11m 50s
before exiting. A sample profile showed the time was spent inside a
single SQL query:

```
buildpipe.runIncremental
 → persist.(*sqliteStore).ReverseDepsForFiles
   → SELECT … (sqlite VDBE step, 8+ minutes)
```

A clean rebuild (`rm -rf .ckg-stablenet/` then `ckg build` without
`--force`) finished in **1m 28s** — about 8× faster — because the
incremental path was skipped entirely.

The incremental path is supposed to be the fast path. That it ends up
slower than a full rebuild for this project size points at either a
missing index on the table that `ReverseDepsForFiles` queries, or a
query plan that fans out across an unbounded set of file paths. Both
are diagnosable from the SQL plan; neither requires schema changes.

Belongs in the ckg repo's backlog (not cks). Reproducer is the
sequence above. The session-closing PR for ckg (#16) added the policy
file but did not touch the build pipeline.

### 2.5 `cks-promotion-worksheet` — `Maps to:` heuristic 50% accuracy

Documented when the worksheet generator landed (PR #9). The
session's audit confirmed: on this corpus, about half the entries
got the correct 07 §9 catalog item from token overlap; the rest the
reviewer corrected in-line during promotion.

Root cause: catalog items 1 (`stake-weighted voting`) and 3
(`ETH-denominated assumptions`) carry generic keyword sets
(`validator`, `power`, `ether`) that match many unrelated entries.
Tightening those two item keyword lists in `cmd/cks-promotion-worksheet/main.go`'s
`catalog` table would bring accuracy to ~70% at ~5 minutes of work.

Low priority: the worksheet design treats `Maps to:` as a starting
suggestion that the reviewer overwrites, so 50% accuracy was the
"acceptable" budget. Tighten only if a future promotion session
finds the reviewer spending non-trivial time correcting it.

## 3. Cycle 2 backlog

The big-ticket items the next cycle picks from.

### 3.1 P2 — Bench harness (3-way)

| Field | Value |
|---|---|
| Spec reference | 06 §P1 ("UNPROVEN thesis" measurement keystone) |
| Effort | 3–5h (initial 5–10 ground-truth queries; expansion ongoing) |
| Blocker | Needs a curated query set + correctness oracle |
| Outcome | Comparable A (cks) / B (code-only) / C (cks + skills) numbers on retrieval recall, MRR, nDCG, token cost, latency |
| Owner | Open |

Cycle 1 deliberately deferred bench because the measurement question
was downstream of having a real verified-entry corpus. That corpus is
now in place (36 verified, 112 edges), so the bench can finally tell
us whether the corpus *helps* — which is the only quantitative
question that justifies any further investment in the curation
pipeline.

### 3.2 ckg parser — CGO / asm support

| Field | Value |
|---|---|
| Spec reference | 09 §5 follow-up |
| Effort | 2–4h, ckg-maintainer decision required |
| Mechanism | `pkg.IgnoredFiles` AST-only secondary parse |
| Outcome | ~61 chunks recovered (symbol alignment 98.4% → ~99%) |
| Risk | Introduces `INFERRED` confidence nodes into the ckg graph (currently every node is `EXTRACTED`) |
| Owner | Open (ckg) |

Open question: does the ckg graph want a second confidence tier
(`INFERRED` / `EXTRACTED`)? Cleaner to add than to remove. Cycle 1
left this as deferred precisely because the impact (~1%) doesn't
obviously beat the complexity.

### 3.3 `claudedocs` integration decision

| Field | Value |
|---|---|
| Background | 2026-06-08 G1 attempt found that go-stablenet's `claudedocs/` lives outside the tree (operator-local), breaking portability when referenced from cks entries |
| Options | (A) Commit `claudedocs/` to go-stablenet · (B) Mirror into `cks/sources/go-stablenet-changelog/` · (C) Leave operator-local |
| Effort | 30 min – 2h depending on option |
| Decision needed from | Project owner (cross-repo policy) |

Cycle 1 left this as a deliberate non-decision because the curation
session didn't need it. Cycle 2 will need it to make `existing_doc_ref[]`
consistently resolvable.

### 3.4 06-style audit re-validation cadence

| Field | Value |
|---|---|
| Observation | Cycle 1 found 3 of 06's P3 items were already implemented at the time of audit |
| Implication | Audit reports go stale fast; reviewers waste cycles on items the implementation already addressed |
| Proposed fix | PR-merge-triggered re-validation, or quarterly audit refresh |
| Owner | Open |

This is a process item, not a code item. Cycle 2 should decide whether
it's worth standing up tooling or whether the manual re-validation in
PR #6 (06 §4 refresh) is enough.

### 3.5 `cks-domain-sync` follow-up (see §2.2)

Either tighten the qname heuristic (option A) or add per-anchor
override (option B). One PR.

### 3.6 ckg `runIncremental` SQL path (see §2.4)

Diagnose the slow `ReverseDepsForFiles` query and either add the
missing index or rewrite the plan. ckg-maintainer territory.

### 3.7 Operator-side activation (ckv / ckg refresh)

Cycle 1's last mile is the operator running `cks.ops.index { mode: "full" }`
in their MCP client so the new policy reaches ckv and ckg in lockstep.
Cycle 1 built `ckg` directly (see §1); ckv needs a re-load (its policy
file landed in #5 but the running binary needs a restart to pick it
up). Document but do not assign.

## 4. Fact / Opinion

| Type | Statement | Confidence |
|---|---|---|
| Fact | 9 Cycle 1 PRs merged (cks #8-#11, ckv #4-#5, ckg #15-#16, coding-agent #6-#7) | None |
| Fact | ckg post-closing build: 36 Policy nodes, 112 `governed_by` edges | None |
| Fact | 9 `governs[] target not found` warnings observed in the closing ckg build log | None |
| Fact | `wkrc_not_eth` has zero `governed_by` edges; the entry's anchors carry no `symbol` field | None |
| Fact | Incremental ckg build (with stale `.ckg-stablenet/`) took 11m 50s; clean rebuild took 1m 28s | None |
| Opinion | The 8× discrepancy between incremental and clean ckg build is a missing-index or query-plan bug, not a correctness issue | High |
| Opinion | `cks-domain-sync`'s qname heuristic is the right place to fix the 9 mismatches (§2.2 option A), not per-anchor overrides | Mid |
| Opinion | Tightening the `Maps to:` heuristic in `cks-promotion-worksheet` (§2.5) is below the worth-fixing threshold until a second promotion session complains | High |
| Opinion | The bench harness (§3.1) is the most important Cycle 2 item because every other curation investment is unmeasured without it | High |
