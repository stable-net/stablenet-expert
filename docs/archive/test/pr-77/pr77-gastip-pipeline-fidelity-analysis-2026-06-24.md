# PR-77 GasTip Stall — Pipeline Fidelity & Reproduction-Misfire Analysis

- **Date:** 2026-06-24
- **Ticket:** LOCAL-20260623_042159 ("거버넌스 GasTip 복원 제안 시 트랜잭션 Pending Pool 정체")
- **Pipeline run:** coding-agent 0.1.30→0.1.31, autopilot, e2e reproduction tier, 2 bug cycles → EVALUATION_PASS
- **Workspace:** `analysis-test/.coding-agent/tickets/LOCAL-20260623_042159/`
- **Expert reference fix:** `pr-77-origin@98f05c2a0c161ac67a1d50f254ca4847c8fac2a5` (hmlee, "fix: refresh AnzeonTipEnv current block when GasTip changes (#77)")
- **Purpose:** research continuity. Captures (A) the pipeline-vs-expert fix comparison, (B) why the reproduction test did not verify the ticket's real problem, (C) the meta root-cause of the pipeline misfire (grounded in `findings.log`), (D) concrete harness improvements, (E) the re-run plan.

---

## 0. One-paragraph summary

The pipeline produced a fix that is **internally verified GREEN** (its e2e oracle goes red→green, all gates PASS) but **fixes a different defect than the ticket's true root cause.** The analyzer *initially diagnosed the correct root cause* — a stale `AnzeonTipEnv.currentBlock` (identical to the expert's fix) — but its reproduction attempt failed to trigger that staleness (it never recreated the sustained empty-block idle window the symptom requires). It mis-attributed the non-reproduction to "hypothesis falsified," **abandoned the correct root cause**, and pivoted to an *adjacent, reliably-reproducible* defect (`RemotesBelowTip` eviction scope). The fix then correctly solved that adjacent defect. The reproduction RED gate accepted this because it only checks "an assertion fails on base," not "the assertion encoding the ticket's symptom fails for the diagnosed reason."

---

## A. The two fixes

### A.1 Expert fix (`98f05c2a0c`) — upstream / source

Two parts:

1. **`eth/gasprice/anzeon.go` `SetCurrentBlock`** (the root cause). Previously `currentBlock` was refreshed only when `header.Root` changed. After a governance gasTip change, **empty blocks share the prior state root** but carry the new header GasTip — so `currentBlock` stayed pinned to the change block, whose header GasTip was stale. Unauthorized txs were then validated against a **stale GasTip**, keeping `EffectiveGasTip` below `minTip`. Fix: add `gasTipChanged(env.currentBlock.GasTip(), header.GasTip())` to the refresh condition so the env advances when the header GasTip changes even if the root is unchanged.
2. **`legacypool.RemotesBelowTip`** uses `tx.GetAnzeonTipCap()` (effective tip) with raw fallback, instead of raw `GasTipCapIntCmp`.

Net direction: **make the effective-tip computation correct at its source** → the stuck tx is correctly priced → it becomes minable again. ~30 lines, touches the gasprice/anzeon caching layer + one eviction comparison. `RemotesBelowTip` iteration scope is **unchanged** (remotes only).

### A.2 Pipeline fix (`ca/local-20260623-gastip`, HEAD `e780ede2a`) — downstream / consumer

- cycle 1: `RemotesBelowTip` raw→effective tip (`EffectiveGasTipIntCmp` + `anzeonTipEnv`), threaded from `SetGasTip`.
- cycle 2: add `lookup.AllBelowTip(threshold, anzeonTipEnv)` scanning **both** `locals` and `remotes` (`Range(f,true,true)`); `SetGasTip` raise branch dispatches on `pool.anzeonTipEnv.IsAnzeon()` → `AllBelowTip` (Anzeon) else `RemotesBelowTip` (preserve local exemption).
- `eth/gasprice/anzeon.go` **not touched.**

Net direction: **make the eviction scan remove the stuck tx** → the unminable unauthorized tx is evicted. ~214 lines (incl. tests), txpool layer only.

### A.3 Behavioral divergence

| | Expert | Pipeline |
|---|---|---|
| Root cause located at | **producer** of the wrong value (stale cached block header) | **consumer/cleanup** (eviction scan scope) |
| Remediation | un-stale the env → tx **becomes minable** | evict the tx → tx **removed from pool** |
| Triggers on restore (decrease)? | yes (the actual symptom window) | no — pipeline eviction only runs on `newTip>old` (raise) |
| `eth/gasprice/anzeon.go` | fixed | untouched |
| Overlap | `RemotesBelowTip`→effective (== pipeline cycle-1) | same |
| Divergence | did NOT add locals scan (unnecessary once source is fixed) | added `AllBelowTip` locals scan; **missed the stale-env source** |

**Risk:** because `SetCurrentBlock` was never touched, the ticket's real-world symptom (stale-env stall during empty-block windows after a gasTip change) likely **still reproduces** in production. The pipeline's own faithful assertion for that symptom (AC#5) passed on the buggy base (see B), so the pipeline never saw it.

---

## B. Why the reproduction test did not verify the real problem

The e2e oracle `repro/LOCAL-20260623_042159-gastip-restore-stall.sh` is **mechanically valid** (reads header extradata `WBFTExtra.GasTip`; red_at_parent on AC#4; green_at_head on the fix) but **does not capture the ticket's described symptom.**

- The oracle's **own header comment (lines 28–37)** describes the true root cause exactly as the expert did: *"idle (empty) blocks M+1, M+2 … share [the state root] … carries the PRE-restore (stale, HIGHER) GasTip 30000 … a normal tx priced for the restored 27600 cannot afford the stale 30000 → excluded … RED (buggy base): the restore-window tx is NOT mined."* That symptom is **AC#5** ("post-restore normal tx is MINED").
- But the recorded base run was **`Pass:12 | Fail:1`, the lone failure being AC#4** (raise eviction). **AC#5 passed on the buggy base** — i.e. the ticket's described symptom did **not** reproduce in this test.
- Reason the staleness never fired: the scenario keeps the chain busy (clog tx, governance txs), so **every block changes the state root** → `currentBlock` advances → no stale window. The staleness only bites in a **sustained empty-block window**, which the test never constructs.
- The pipeline therefore took AC#4 (eviction on raise) — which fails on base for an *unrelated* reason (raw-vs-effective tip + locals scope) — as the RED, and `red_confirmed=true` was set on that.

**Conclusion:** the test verifies an adjacent anzeon gas-tip defect, not the ticket's stale-env stall. A faithful test must build the empty-block window after the restore and make **AC#5 the RED gate**.

---

## C. Meta root-cause: why the pipeline misfired (grounded in `findings.log`)

The diagnosis trail in `findings.log` is unusually clear about how the run went wrong:

| line | event |
|---|---|
| L6–11 | early static analysis; explored header timing + a `gasTipUpdater` off-by-one hypothesis |
| **L14–15** | **CORRECT root cause found** (matches expert): *"broken edge = AnzeonTipEnv.SetCurrentBlock (eth/gasprice/anzeon.go:54)… swaps currentBlock ONLY when header.Root differs… idle empty blocks … stale GasTip … Fix per AC: track every head by block number."* Cross-checked against existing regression `c-08-gastip-change-idle-stale-reject`. |
| **L16** | first repro run: *"AC#4 (restore-window tx MINED oracle) PASSED → my restore-direction stale-reject stall hypothesis did NOT reproduce"* (also: baseline polluted, gasTip=1000 from prior runs) |
| **L17–18** | *"FALSIFIED restore-stall hypothesis … repro test PASSED 10/10 on buggy base … ONLY c-09 (RemotesBelowTip eviction on RAISE) fails RED … ROOT CAUSE RE-CONFIRMED via runtime: RemotesBelowTip"* — **the correct hypothesis is abandoned; the run pivots to the reproducible adjacent defect** |
| L19–20 | RED confirmed on AC#4; ANALYSIS→PLANNING gate passes (`reproduction_confirmed=true, red_confirmed=true`) |
| L21–37 | cycle 2: correctly extends the eviction fix to `t.locals` (`AllBelowTip`) — deeper, but **still within the adjacent defect** |

From this, the distinct failure modes:

**C-1 (core). "Strong hypothesis won't reproduce" mis-attributed as "hypothesis wrong" instead of "test setup inadequate."**
The analyzer had a high-confidence, regression-corroborated root cause (L14–15) but its test never recreated the staleness precondition (a sustained empty-block window). The reproduce-first RED gate logic ("can't make it RED → the test or the understanding is wrong") was resolved in the *wrong direction*: it discarded the correct hypothesis rather than fixing the test setup. There is no methodology branch for "hypothesis is strong AND corroborated AND known-pattern → suspect the harness/setup first."

**C-2. The RED gate is decoupled from the ticket symptom / diagnosed root cause.**
`state-machine` ANALYSIS→PLANNING only requires `reproduction.json` + `reproduction_confirmed` + `red_confirmed` — i.e. *some* assertion fails on base. It does **not** require that the failing assertion encodes the ticket's described symptom, nor that it fails for the reason named in `## Root cause`. So "reproduced a different bug" satisfies the gate. (This is the meta-level of the original #19 fix: #19 enforced *that a reproduction exists*; it did not enforce *that the reproduction is of the right thing*.)

**C-3. "Symptom assertion passes on base" was not treated as a stop signal.**
AC#5 (the assertion encoding the ticket symptom) passing on the buggy base (L16) is a loud signal the reproduction is inadequate. Nothing in the pipeline flags "the assertion matching the ticket's described symptom is GREEN on base."

**C-4. A correctly-identified candidate site was silently dismissed.**
`related-code.json.affected_sites` contains `eth/gasprice/anzeon.go:50-63 (AnzeonTipEnv.SetCurrentBlock)` but marked `produces_symptom:false, must_fix:false`. The correct root-cause site was retained in the structured contract yet **down-classified** — because the (inadequate) RED didn't need it. No gate re-checks a dismissal of a site that an existing regression test (`c-08`) and a known staleness pattern both point at.

**C-5. e2e environment pollution added noise.**
L16: the shared chainbench chain was left at gasTip=1000 by prior `c-08/c-09` runs, producing spurious baseline failures the analyzer had to disentangle — extra noise around the exact moment of the pivot. Repro lacked a guaranteed-fresh baseline.

**Important nuance:** the cycle-2 work (L21–37) is *high quality* — it used cks + runtime routing evidence to correctly extend the eviction to `t.locals` and preserved the local-exemption regression (`TestRepricingKeepsLocals`) via the `IsAnzeon()` gate. The failure is **not** sloppiness; it is that all of that rigor was spent on the **wrong target**, locked in at C-1.

---

## D. Improvement points (harness)

Ranked by leverage.

**D-1 — Reproduction must be tied to the symptom/root-cause, not "any red."** *(analyzer §5.2 RED gate, reproduce-first skill, state-machine ANALYSIS→PLANNING gate)*
- The RED assertion(s) must encode the ticket's **described symptom**, and must fail for the reason in `## Root cause`. Add a `symptom_assertion` field to `reproduction.json` naming which assertion is the symptom, and require THAT assertion to be the one that is RED at parent.
- If the symptom assertion is GREEN on base while a different assertion is RED → status `reproduction_inadequate` (not `red_confirmed`); revise the **setup**, do not proceed.

**D-2 — "Strong hypothesis won't reproduce → fix the setup before abandoning the hypothesis."** *(analyzer §5.0 / §5.2; reproduce-first)*
- When a root cause is high-confidence (corroborated by an existing regression test or a known pattern such as a stale cache) and the test won't go RED, **first** enumerate the symptom's necessary runtime conditions (idle/empty-block window, timing, account class, fee relation) and systematically construct them — only after that may the hypothesis be downgraded. Never pivot to a *different* defect merely because it reproduces more easily; record both and resolve which is the ticket's.

**D-3 — First-class "idle / empty-block window" repro primitive for staleness / "persists-then-clears" symptoms.** *(analyzer §5b e2e tier; reproduce-first)*
- For symptoms that manifest only while the chain is idle (no state-changing txs) and self-heal on the next state change, the e2e setup must **hold a sustained empty-block window** and assert the symptom inside it. (§4 already says "trace the event that *clears* the symptom" — operationalize it as a test-construction requirement.)

**D-4 — Re-validate dismissed candidate sites.** *(analyzer §4.1 affected_sites; evaluator §4.8)*
- A site placed in `affected_sites` with `produces_symptom:false` that (a) matches a known failure pattern (stale cache/env) or (b) is implicated by an existing regression test must carry **runtime evidence for the dismissal** (a §5c probe targeting that site), not a static judgement that "the current RED doesn't need it."

**D-5 — Guaranteed-fresh / isolated e2e baseline.** *(reproduce-first e2e; evaluator §7 chainbench)*
- Repro runs must start from a known-clean baseline (fresh chain or asserted-and-restored policy state) so prior-run pollution cannot masquerade as (or mask) the symptom.

**D-6 — Symptom-faithfulness surfaced in the report.** *(evaluator §4.7)*
- `test-report.md` should state which assertion is the symptom oracle and confirm it (not a sibling) is the one that went red→green, so a reviewer can see the reproduction is of the right thing.

---

## E. Re-run plan (next step)

1. Apply D-1…D-6 (at least D-1, D-2, D-3 — the misfire-closing trio) to the source plugin (`coding-agent/plugin/agents/analyzer.md`, `skills/reproduce-first`, `state-machine` gate), commit, release/reload.
2. **Reset the target tree to a bug-reproducing, fix-unknown state**: `analysis-test` (or a clean go-stablenet checkout) at base `0bf2f4d1b`, discard the `ca/local-20260623-gastip` fix branch, fresh `.coding-agent` workspace, fresh/isolated chainbench chain.
3. Re-run the pipeline on the same ticket. **Success criterion:** the analyzer (a) builds the empty-block-window repro, (b) makes the **stale-env / restore-mine assertion** the RED, (c) converges on `eth/gasprice/anzeon.go SetCurrentBlock` (≈ expert `98f05c2a0c`), not (only) the eviction path.
4. Compare the new fix surface against the expert diff; record outcome here (append a §F).

---

## Evidence appendix

- Expert commit: `pr-77-origin@98f05c2a0c` — `eth/gasprice/anzeon.go` (+`gasTipChanged`, `SetCurrentBlock` condition) + `legacypool.go RemotesBelowTip` (GetAnzeonTipCap).
- Pipeline fix diffstat (`git diff main...HEAD`): `legacypool.go +60`, `legacypool_test.go +152`, `blobpool.go +6`. No `eth/gasprice/anzeon.go`.
- `reproduction.json`: tier=e2e, red_at_parent=true (AC#4), green_at_head=true (13/13), oracle_unmodified=true, reproduction_verdict=PASS, fix_validity_verdict=PASS.
- `findings.log`: L14–15 correct root cause; L16–18 the falsify-and-pivot; L21–37 cycle-2 locals extension.
- Oracle `repro/LOCAL-20260623_042159-gastip-restore-stall.sh`: header comment lines 28–37 (correct symptom), AC#4 lines 205–212 (the actual RED, eviction on raise), AC#5 lines 229–253 (faithful symptom, passed on base).

---

## F. Clean blind re-run (run-2) outcome + three-way comparison (2026-06-25)

Re-run on a fresh checkout (`analysis-test-2`) with the hardened harness (0.1.32 symptom-bound RED + anti-pivot + idle-window; 0.1.33 focused per-cycle unit), the answer-free/blind constraints, and the answer-leaking chainbench mechanism tests (`c-08`, `c-09`) quarantined. Ticket `LOCAL-20260625_011010`.

**Result: BLOCKED after 3 bug-cycles** (oracle RED all 3; `green_at_head=NO`, `Total 9 | Pass 8 | Fail 1`, the lone fail being the symptom assertion). No PR (FAIL never reaches COMPLETION; auto_merge=false).

### What the hardened harness got RIGHT (the validation)
- **Reproduction is genuine + symptom-bound.** Oracle `repro/LOCAL-20260625_011010-gastip-restore-stall.sh`; `symptom_assertion = "tip-27600 normal tx is included after restore (not stalled)"`; the symptom assertion is the *sole* RED on base (`symptom_red_confirmed=true`), timing assertions PASS. The cycle-2 evaluator's suspected nonce-gap/future-queue *oracle fragility* was **refuted by cycle-3 runtime instrumentation** → oracle correctly kept immutable. (Contrast run-1, which pivoted to an adjacent eviction defect.)
- **Diagnosis converged on the EXPERT's root cause — independently.** The §5c runtime loop confirmed: the add-gate compares `MinTip = pool.gasTip = 30000` (from imported header **N+1**) against `effective = currentBlock.GasTip() = 27600` (from `anzeonTipEnv.currentBlock`, which **lags at header N** because `SetCurrentBlock` is driven only by `Reset`/`Pending`/`reheap`, not the gasTip-update path). That lag IS the expert's `98f05c2a0c` primary edge (refresh `currentBlock` when GasTip changes).
- **The gate correctly refused to ship a wrong fix.** Three cycles, each a plausible fix that PASSED unit/lint/sec, were all held RED by the e2e symptom oracle and the run BLOCKED — it did **not** emit a false PASS. This is the central improvement over run-1 (which shipped a fix that greened the gates while fixing the wrong defect).
- **Speed (D-7) held.** Per-cycle focused unit ran in seconds (not the ~38-min whole-package suite); 3 full cycles completed.

### What still failed (the remaining weak link = FIX SYNTHESIS, not reproduce/diagnose/verify)
- All 3 cycles kept an **add-time DROP** for a non-local normal-account tx instead of removing it. Cycle-3's `rawSourced := cap==nil || cap.Cmp(tx.GasTipCap())==0` heuristic **false-positived on the exact oracle case**: the symptom tx's raw tip (27600) *equals* the lagging env header tip (27600) → `rawSourced=true` → the drop still fires → tx never pooled → `inclusion_block=NONE`.
- **A focused unit test masked it (recurring pattern).** Cycle-3's unit used raw=25000 (≠ header 27600), so it passed while the e2e (raw==header) failed — the same "unit green / e2e red" shape as run-1's remote-only unit test. The symptom-bound e2e oracle caught it each time; the unit test did not. (Validates e2e-oracle-as-acceptance; flags a unit-fidelity gap.)
- **Sound fix for a future run** (per cycle-3 evaluator): gate the add-time reject on account class (`AnzeonTipEnv.IsAuthorized(from)`) — or remove the add-time underprice check entirely for non-local Anzeon txs and let the retain-not-drop Pending filter govern inclusion — AND align the unit test to use raw == genesis/header tip (the real oracle condition). This is the spirit of the expert fix (make the gate not reject a header-sourced normal tx).

### Three-way comparison
| | run-1 (old harness, contaminated) | run-2 (hardened, clean blind) | expert `98f05c2a0c` |
|---|---|---|---|
| Reproduction | adjacent eviction defect (symptom passed on base) | **genuine, symptom-bound, oracle sound** | n/a |
| Root cause reached | eviction (wrong); dismissed SetCurrentBlock | **currentBlock lag = expert edge (runtime-confirmed)** | SetCurrentBlock stale + RemotesBelowTip raw |
| Fix shipped? | **yes — wrong fix passed all gates (false green)** | **no — BLOCKED after 3 cycles (no false green)** | yes (correct) |
| Outcome | bug not actually fixed, but looked PASS | bug not fixed, but **honestly reported BLOCKED** | bug fixed |

### Net research conclusion
The hardening (symptom-bound RED, anti-pivot, idle-window, focused unit) **closed the original failure mode**: the pipeline no longer ships a wrong fix behind a false PASS, it reproduces the real symptom, and it converges (via §5c) on the true root cause. The **unresolved gap is fix-synthesis**: the planner/implementer kept choosing an add-time-drop variant and a unit test that didn't exercise the raw==header case. Next harness iteration should target (a) implementer fix-pattern guidance for "retain-not-drop / account-class gating," and (b) a fix-validity/unit rule that the fix's own unit test must exercise the *exact* oracle-failing condition (here raw == header tip), not a convenient neighbor.
