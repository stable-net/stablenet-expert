# Continuous Learning Loop — Design

> Status: **DESIGN ONLY — implementation deferred.** This document specifies the
> closed loop that lets `coding-agent` get smarter the more it is used, by
> promoting validated outputs of finished tickets back into the `cks` knowledge
> corpus. It is written to be implementable later without re-deciding the shape.

| | |
|---|---|
| Author | design session, 2026-06-08 |
| Depends on | `docs/system-contract.md` (C1 boundary), `docs/archive/r1-refactor/07-domain-knowledge-curation.md` (entry model + promotion), `docs/archive/r1-refactor/10-cycle1-followup-and-backlog.md` (ROI gate) |
| Touches repos | `coding-agent` (capture + curate), `code-knowledge-system` (entry store + sync) |
| Non-goals | A hot-reload index; an auto-verify path; replacing the human curator |

---

## 1. Problem

Today the pipeline is **unidirectional**: the Planner *reads* cks (RAG + graph-RAG),
the Implementer writes code, the Evaluator tests. Nothing is ever written *back*.
Every hard-won fact a ticket produces — a newly confirmed invariant, the root
cause of a subtle bug, the reason a design path was rejected — evaporates when
the workspace is cleaned up. The next ticket on the same subsystem re-derives it
from scratch.

The cks corpus only improves when a human hand-authors a domain entry and flips
it to `verified`. There is no path from "a ticket just proved X about the
consensus engine" to "the corpus now knows X." This document designs that path.

**Goal:** each completed, merged ticket can *deposit candidate knowledge*; a
gated curation step promotes the good ones; retrieval quality compounds over
time. The compounding is measurable by the existing 3-way bench.

---

## 2. Hard constraints (do not violate)

These come from the system contract and the curation plan. The design is shaped
by them, not the other way around.

1. **Binary = deterministic, Session = LLM** (`00 §2.2`). cks binaries
   (`cks-domain-sync`, `ckv build`, `ckg build`) contain zero LLM calls. *All*
   judgment — "is this candidate true? is it worth keeping?" — lives in the
   coding-agent / Claude Code **session layer**.
2. **The cks agent contract is read-only.** `scripts/contract/agent-mcp.schema.json`
   exposes query / index / health only. There is **no** `cks.entry.write` or
   `cks.ops.promote`. Knowledge enters the corpus the same way human curation
   does today: an **entry YAML file is edited and committed** to
   `code-knowledge-system`, then a deterministic sync regenerates the views.
   The loop does not get a privileged write API; it produces a **pull request**.
3. **`status` is the single activation gate.** An entry is either
   `needs_verification` or `verified`. Only `verified` entries reach the runtime
   LLM (via `cks-domain-sync` → ckv policy + ckg `governed_by` edges). Anything
   the loop deposits starts as `needs_verification` and is **inert** until
   promoted.
4. **No auto-verify, ever.** A ticket's own output is low-trust evidence. The
   model must never promote its own candidate to `verified` without an
   independent gate (see §6, anti-drift). This is the difference between
   *learning* and *confirmation-bias amplification*.
5. **Reindex is slow and batched.** A full `bge-m3` rebuild is throughput-gated
   (hours). Promotions accumulate and activate on a scheduled `cks.ops.index`,
   not per-ticket.
6. **Outbound sanitization applies.** A candidate entry derived from ticket
   artifacts can carry secrets or internal detail. It crosses a trust boundary
   into a shared corpus, so it passes the **same** `pr-sanitize` /
   `packages/shared-patterns/patterns.json` scrubber that PR bodies and Jira comments do
   (`HANDOFF §3.3`). A candidate that does not come back `CLEAN` is dropped, not
   redacted-and-kept.

---

## 3. Architecture at a glance

```
  ┌─────────────────────── coding-agent session (LLM) ───────────────────────┐
  │                                                                           │
  │  EVALUATION_PASS / COMPLETION                                             │
  │        │                                                                  │
  │        ▼   (1) CAPTURE                                                    │
  │   capture-learning skill                                                  │
  │   reads: analysis.md, design-v{N}.md, test-report.md, related-code.json   │
  │   emits: candidates[] (needs_verification, with evidence + anchors)       │
  │        │                                                                  │
  │        ▼   (2) SANITIZE + DEDUP (deterministic where possible)            │
  │   pr-sanitize  →  CLEAN only                                              │
  │   dedup vs existing entries (cks.context.semantic_search on the claim)    │
  │        │                                                                  │
  │        ▼   candidates land in a durable queue                            │
  │   .stablenet-expert/learning/queue/{subsystem}/{ticket}-{n}.yaml             │
  │                                                                           │
  │        ▼   (3) CURATE  (/curate-knowledge — explicit, human-in-the-loop) │
  │   curator agent: judges each candidate against live code via cks +       │
  │   stablenet-invariants; rewrites to entry schema; assigns subsystem/type │
  │        │                                                                  │
  └────────┼──────────────────────────────────────────────────────────────────┘
           │   (4) PROMOTE = open a PR to code-knowledge-system
           ▼
  ┌──────────────── code-knowledge-system repo (deterministic) ──────────────┐
  │   entries/*.yaml  (status: needs_verification → human review → verified)  │
  │        │  cks-inventory-check (schema + anchor resolution gate)           │
  │        ▼                                                                  │
  │   cks-domain-sync → ckv policy/stablenet.yaml + ckg policy.yaml           │
  │        │                                                                  │
  │        ▼   (5) ACTIVATE: cks.ops.index{mode} on a schedule               │
  │   verified knowledge now retrievable by the Planner                      │
  └──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼   (6) MEASURE
                        3-way bench (A=cks / B=code-only / C=cks+skills)
                        ROI gate: does the grown corpus actually help?
```

Two repos, six stages. Stages 1–4 are new and live in `coding-agent` (session
layer). Stage 4's *output* is a PR; the entry store, sync, and activation in
stages 4–5 are **existing** `code-knowledge-system` machinery — the loop reuses
it, it does not reinvent it.

---

## 4. The candidate entry — data contract

A *candidate* is a proposed domain entry plus the evidence that produced it. It
is a superset of the existing entry schema (`07`): the extra `evidence` block is
what the curator and the human reviewer judge, and it is **stripped** before the
entry is committed to the corpus.

```yaml
# .stablenet-expert/learning/queue/A14/STABLE-1234-1.yaml
schema_version: 1
candidate_id: STABLE-1234-1
origin:
  ticket: STABLE-1234
  pr: "https://github.com/.../pull/42"     # merged PR — proof it shipped
  merged_commit: 9f2a1c0
  produced_at: 2026-06-08T00:00:00Z
  pipeline_stage: EVALUATION_PASS           # candidates only from passing work

# --- proposed entry (maps 1:1 onto the cks entry schema) ---
entry:
  subsystem: A14                            # curator confirms against subsystems.yaml
  knowledge_type: B3                        # invariant | pitfall | contract | ...
  title: "Validator power is equal-weight regardless of stake"
  summary: >
    ...
  status: needs_verification                # ALWAYS this at capture time
  priority: high
  code_anchors:
    - file: consensus/wbft/validator.go
      symbol: (*ValidatorSet).TotalPower    # required for T1 governs[] emission
      line: 188
      reason: "loop sums 1 per validator, not stake"
  invariants:
    - "Quorum is 2f+1 of validator COUNT, never of stake-weight."
  pitfalls:
    - "Do not introduce stake-weighting here; it breaks Byzantine fairness."

# --- evidence (NOT committed to the corpus; basis for the gate) ---
evidence:
  confidence: medium                        # capture-time self-rating (never 'verified')
  derived_from:
    - artifact: design-v2.md
      claim: "rejected a stake-weighted quorum because invariant INV-3 forbids it"
    - artifact: test-report.md
      claim: "race+unit pass with equal-weight; stake-weight variant failed INV-3 check"
  corroborated_by_invariant: INV-3          # cross-ref to stablenet-invariants (L3)
  sanitize_scan: CLEAN                       # pr-sanitize result; non-CLEAN ⇒ dropped
  dedup:
    nearest_existing: A14-e7                 # cks.context.semantic_search top hit
    similarity: 0.71                         # below merge threshold ⇒ new candidate
```

Design rules embedded above:

- **`status` is hard-coded `needs_verification` at capture.** The capture skill
  cannot emit `verified`. Only the human review step in stage 4 may.
- **Provenance is mandatory.** `origin.pr` + `merged_commit` mean a candidate
  only exists for work that actually shipped and passed evaluation. Failed and
  abandoned tickets produce nothing.
- **`evidence` is the gate's input and is discarded on promotion.** The corpus
  stores knowledge, not the trail that justified it (that lives in git history).
- **Anchors carry `symbol`**, because T1 `governs[]` edge emission keys on the
  anchor qname (`07 §2.2`). Missing symbol ⇒ candidate is T2-shaped and is
  parked until the corpus's T2 schema branch (`08 §2`) lands — the loop must not
  block on it.

---

## 5. Lifecycle state machine

A candidate moves through explicit states. The transition out of `proposed` is
the one humans gate; everything before it is automatable.

```
   CAPTURED ──sanitize+dedup──▶ QUEUED ──/curate-knowledge──▶ PROPOSED
                  │                                              │
            (non-CLEAN or                                 human review
             dup ≥ merge thr)                              on the PR
                  ▼                                    ┌────────┴────────┐
              DROPPED / MERGED-INTO-EXISTING      PROMOTED          REJECTED
                                                  (status:verified)  (closed,
                                                       │              reason logged)
                                                  cks-domain-sync
                                                       │
                                                       ▼
                                                  ACTIVE (retrievable)
```

| State | Owner | Persistence |
|-------|-------|-------------|
| CAPTURED | `capture-learning` skill | in-memory → queue file |
| QUEUED | deterministic gate | `.stablenet-expert/learning/queue/...` |
| PROPOSED | `curator` agent (LLM) | PR to `code-knowledge-system` |
| PROMOTED / REJECTED | **human reviewer** | entry YAML `status` / closed PR |
| ACTIVE | `cks-domain-sync` + index | ckv/ckg views |

The queue is durable on purpose: capture happens at ticket-completion time, but
curation is batched (a human reviews a week of candidates at once). The queue
survives across sessions exactly like `state.json` does.

---

## 6. Anti-drift — the part that makes this safe

A naive write-back loop is dangerous: a model that learns from its own
unverified output drifts toward its own biases and amplifies its mistakes. The
gates below exist specifically to prevent that.

1. **Two-key promotion.** Capture (LLM) and promotion (human) are *different
   actors*. The capturing session can never set `verified`. A candidate becomes
   active only after a human flips `status` on the PR. This is the load-bearing
   gate — keep it even if everything else is automated.
2. **Independent re-judgment, not self-agreement.** The `curator` agent judges a
   candidate **against live code and `stablenet-invariants`**, from a clean
   context — it does not see the original session's reasoning, only the claim and
   the anchors. If the claim cannot be re-derived from code, it is REJECTED. A
   candidate that merely restates what the model already believed (no new code
   anchor, similarity to an existing entry above threshold) is dropped as
   redundant, not promoted.
3. **Invariant supremacy.** A candidate that contradicts an entry in
   `stablenet-invariants` (the L3 always-on backstop) is auto-REJECTED at the
   gate. The hand-verified backstop outranks anything the loop proposes —
   learning can extend the corpus, never override its safety floor.
4. **Provenance ≥ shipped.** Only `EVALUATION_PASS` + merged-PR work produces
   candidates. The corpus never learns from code that failed review.
5. **Sanitize-or-drop.** Non-`CLEAN` candidates are dropped, not redacted. A
   knowledge entry with a hole where a secret used to be is worse than no entry.
6. **ROI gate before scaling.** Per `10 §3.1`, the 3-way bench is the only
   quantitative answer to "does the grown corpus help?". Run it on the corpus
   before and after a batch of promotions. If accuracy/token metrics do not
   improve, curation investment pauses — the loop is instrumented to be
   *falsifiable*, not assumed beneficial.

---

## 7. New components (what implementation would build)

All session-side; all deferred. Listed so the surface is fixed now.

| Component | Type | Responsibility |
|-----------|------|----------------|
| `capture-learning` | skill | Stage 1–2. Read passing-ticket artifacts → emit candidate YAML(s); run pr-sanitize; dedup via `cks.context.semantic_search`; write to queue. Invoked by the Orchestrator on COMPLETION (best-effort, never blocks PR). |
| `curator` | agent | Stage 3. Re-judge queued candidates against live code + invariants from a clean context; rewrite to entry schema; assemble a PR to `code-knowledge-system`. |
| `/curate-knowledge` | command | Explicit, human-triggered entry to stage 3–4 over the current queue. Batched; never automatic. |
| queue dir | convention | `.stablenet-expert/learning/queue/{subsystem}/{ticket}-{n}.yaml`, gitignored in this repo (it is staging, not source). |

**Reused, unchanged:** `cks-domain-sync`, `cks-inventory-check`,
`cks-glossary-gen`, `cks.ops.index`, the entry schema, `pr-sanitize`,
`stablenet-invariants`, the bench harness. The loop is mostly *wiring existing
deterministic machinery to a new capture front-end* — which is why the
constraints in §2 matter more than new code.

**Orchestrator touchpoint:** one new optional transition out of COMPLETION —
`COMPLETION → (capture) → COMPLETED`. Capture failure is logged and ignored; it
must never affect whether the ticket itself is considered done.

---

## 8. Phasing (when implementation resumes)

1. **P1 — Capture only.** Ship `capture-learning` writing candidates to the
   queue. No curation, no PR. Observe what the loop *would* learn for a few real
   tickets; tune the candidate schema against reality. Zero risk to the corpus.
2. **P2 — Manual curation.** Add `/curate-knowledge` + `curator` agent producing
   PRs. Human promotes. Measure with the bench before/after the first batch.
3. **P3 — Standing review cadence.** Scheduled reindex; queue triage routine;
   dedup tuning. Only if P2's bench shows the corpus actually helps.

Each phase is independently useful and independently abandonable. P1 alone
already answers "is there signal here?" without touching the shared corpus.

---

## 9. Open questions (decide at implementation time)

- **Queue location.** In-repo (`.stablenet-expert/learning/`, gitignored) vs a
  branch in `code-knowledge-system`. Leaning in-repo for P1 (staging is local),
  promote-time PR carries it across.
- **Dedup threshold + merge semantics.** When a candidate is ~similar to an
  existing entry, append an anchor/pitfall to the existing entry vs file a new
  one. Needs the real similarity distribution from P1 data.
- **T2 (concept) candidates.** Blocked on the corpus's T2 schema branch
  (`08 §2`). Park anchorless candidates until then; do not let them block T1.
- **Cross-ticket aggregation.** Three tickets each half-proving the same
  invariant — merge at capture, or let the curator consolidate at stage 3?
  Probably the curator, since it has the cross-candidate view.
- **`cks.ops.index` ownership.** Who triggers the scheduled reindex — a
  `/loop`/cron routine, or a human after a promotion batch? Tied to rebuild cost.

---

## 10. Summary

The loop closes coding-agent's biggest gap versus its stated identity — "smarter
the more you use it" — **without** breaking the two principles that keep the
system trustworthy: deterministic binaries stay deterministic, and no knowledge
goes live without an independent human gate. It does this by reusing the existing
human-curation machinery and adding only a capture front-end and a re-judgment
curator in the session layer. The bench keeps the whole thing honest: if the
corpus does not measurably help, the loop pauses itself.
