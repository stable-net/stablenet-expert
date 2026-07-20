# R1′ System Integration Contract (Keystone Spec)

> **Status:** Draft for review · **Date:** 2026-06-01 · **Owner:** architecture consultation
> **Scope:** The single source of truth (SSoT) for how `coding-agent`, `code-knowledge-system` (cks), `code-knowledge-vector` (ckv), `code-knowledge-graph` (ckg), and `chainbench` connect to deliver the Jira→merge automation pipeline for the `go-stablenet` project.
> **Derives:** All five per-project refactoring docs (`01`–`05`) derive their required interfaces from this document. Do not change a cross-project contract in a per-project doc; change it here first.
> **Note (2026-06-28, doc-organize):** promoted from `r1-refactor/00-system-contract.md` to a live Tier-2 doc. The R1′ cycle's per-repo specs/plans (`01`–`05`, `plans/`) referenced below are archived under [`archive/r1-refactor/`](archive/r1-refactor/).

---

## 1. Purpose & Goals

- **G1 — Accuracy/efficiency:** Implement and maintain `go-stablenet` code via the Claude Code LLM more accurately and efficiently.
- **G2 — Economic efficiency:** Reduce time + token cost + human effort.
- **Root problem (a):** LLM-driven `grep/glob/read` retrieval is slow and token-heavy.
- **Root problem (b):** `go-stablenet`'s non-Ethereum policy/business/byzantine-fairness specifics are not reflected → wrong-direction designs, convention/policy violations, security holes, byzantine-unfair changes.
- **Thesis:** Mimic the LLM's iterative retrieval loop, but replace the *information-finding* step with pre-built knowledge (ckv semantic + ckg graph) so the LLM call frequency drops while accuracy rises.

> **Thesis is UNPROVEN as of this writing.** The only honest measurement (ckg δ on go-stablenet, N=1) underperformed a raw file dump (0.335 vs 0.399). That test was confounded: the production embedder was `FakeEmbedder`, ckv's prose→keyword stage was non-functional, and domain knowledge was not wired. The system is too broken to measure cheaply, so validation is a **post-implementation integrated evaluation + debug loop (§9)**, not a pre-refactor gate.

---

## 2. Architecture

### 2.1 Layers & dependency direction

```
[Claude Code Plugin]  coding-agent
  commands(work/status/review/merge) → orchestrator → {planner, implementer, evaluator}
  skills(state-machine, template-parse, stablenet-context*, pr-sanitize) · hooks
        │ MCP calls — names per C1 (SSoT). Agent NEVER talks to ckv/ckg/chainbench-internals directly.
        ▼
 ╔══════════ C1: AGENT-FACING MCP CONTRACT  (SSoT, language-neutral JSON Schema) ══════════╗
 ║   jira_*(6)            cks.context.* / cks.ops.*           chainbench_*(normalized)       ║
 ╚════════┬───────────────────────┬────────────────────────────────────┬═══════════════════╝
   jira-gateway-mcp        code-knowledge-system (cks)              chainbench (TS MCP +
    (Go, built)            ★ composes ckv+ckg via Go import ★        Go wire + bash adapter)
                                  │ C2: Go interfaces (in-process import)        │ C4
                          ┌───────┴────────┐                              gstable binary
                       pkg/ckv          pkg/store + pkg/mcphandlers       (build/bin/gstable)
                       + pkg/embed/ollama  (ckg)                                │
                          │ Ollama HTTP (bge-m3)  │ sqlite graph                │
                         ckv                     ckg                            │
                    (semantic → keywords)   (keywords → code/history/concurrency)│
                          └──── C3: index ──── go-stablenet ──── index ─────────┘
```
\* `stablenet-context` skill is deprecated/rewritten — see §6.

### 2.2 Core principle: **Binary = deterministic, Session = LLM**

The single most important architectural rule, and the one that fixes the `cli-wrapper`/`spawned-Claude` mess:

- **ckv / ckg / cks built binaries are pure deterministic services.** No LLM calls, no `anthropic-sdk-go`, no `cli-wrapper`, no spawning the `claude` CLI. They do embedding, graph build, query, reindex, and deterministic self-tests only.
- **All LLM-based work** (answer comparison/judging, ambiguous knowledge curation, plan synthesis) lives in the **coding-agent / Claude Code session** layer, driven through the cks MCP.
- This mirrors LangChain: `langchain-core` components are deterministic; the LLM orchestration lives in the agent/`langgraph` layer.

### 2.3 Retrieval control vs mechanics

| Concern | Owner | LangChain analogue |
|---|---|---|
| Retrieval **control** (when/what to retrieve, sufficiency judgement, follow-ups) | coding-agent `planner` | langgraph agent loop (agentic RAG) |
| Retrieval **mechanics** (semantic→keyword, keyword→code, pack) | cks (composes ckv+ckg) | core retriever (Runnable) |
| Tool/schema **contract** (C1) | neutral shared JSON Schema | langchain-core defines, partners implement |

The composer stays in cks because it collapses many would-be LLM `grep/read` steps into one LLM-free call (serves G2). The agent retains control by choosing tools and parameters (depth/budget) and deciding whether one call suffices.

---

## 3. The Five Contract Surfaces

### C1 — Agent-facing MCP contract (SSoT)

**Authority:** a single language-neutral JSON Schema file is the SSoT for every tool the coding-agent calls. Only three providers are agent-facing: **cks**, **chainbench**, **jira-gateway**. (ckv/ckg MCP servers are **dev-only**, behind a build tag — see §7; their tool names are NOT part of this contract.)

**SSoT file home & sync (S4):** the schema lives at **`stablenet-expert/scripts/contract/agent-mcp.schema.json`**, owned by the coding-agent repo (it is the consumer of record). Each provider validates against it:
- cks (Go): a unit test asserts its registered tool names + input/output JSON match the schema (golden test in `code-knowledge-system`).
- chainbench (TS): a vitest asserts the exposed tool subset matches the schema.
- coding-agent: agent/command prompts reference only names present in the schema; a pre-flight lint checks for drift.
Any contract change edits this file first, then the three providers' conformance tests fail until they conform.

**Authoring (collision resolved):** **coding-agent (`05`) authors the one canonical `agent-mcp.schema.json`.** cks and chainbench do **not** author it — they each add only a conformance test that *reads* it. Exactly one canonical copy exists; `03`/`04` reference it.

**Canonical naming decision:** adopt cks's existing dotted namespace. The coding-agent must be updated to call these names (it currently calls a removed shim's names — see `05-coding-agent-refactor.md`).

cks agent-facing tools (from `code-knowledge-system/internal/mcp`):

| Tool | Required input | Key optional | Returns |
|---|---|---|---|
| `cks.context.get_for_task` | `prompt` | budget/depth knobs | EvidencePack (composed) |
| `cks.context.semantic_search` | `query` | `k`, `language`, `path_glob`, `kinds` | ckv hits (semantic) |
| `cks.context.search_text` | `query` | `k`, `language`, `path_glob` | ckg BM25 hits |
| `cks.context.find_symbol` | `name` | `language`, `kinds` | definition site(s) |
| `cks.context.find_callers` / `find_callees` / `get_subgraph` | `symbol` | `depth`, `max_total` | call graph |
| `cks.context.impact_analysis` | `symbol` | `depth` | blast radius (call-graph) |
| `cks.context.concurrency_impact` **(NEW, S1)** | `symbol` | `depth`, `max_total` | modules that affect/are-affected via concurrency (goroutine/channel/lock) — backed by ckg `spawns`/`sends_to`/`recvs_from`/`acquires_lock`/`accessed_under_lock` edges. Required by pipeline stage-7. |
| `cks.context.change_history` | `intent` or `symbol` | `k`, `max_count` | PR-breadcrumb history |
| `cks.ops.health` / `cks.ops.freshness` | — | — | backend status / index freshness |
| `cks.ops.index` **(NEW, S2)** | — | `mode` (full\|incremental), `since_commit` | agent-triggered (re)index of go-stablenet for ckv+ckg. See C3 for the daemon alternative. |

chainbench tools — **normalize** to the actual server names (`chainbench_init/start/stop/status/test_run/report/...`), register in `coding-agent/plugin/.mcp.json`, and lock the subset the `evaluator` agent uses (see `04-chainbench-refactor.md`). The evaluator currently expects `chainbench_setup/run_tests` which **do not exist** — fix in the contract, not by aliasing.

jira tools (6) — already aligned, no change: `jira_read_ticket`, `jira_read_comments`, `jira_search`, `jira_add_comment`, `jira_update_status`, `jira_update_assignee`.

### C2 — cks ↔ ckv/ckg Go-import boundary (in-process)

cks composes ckv and ckg as **in-process Go library imports**. No subprocess proxy.

**ckv (resolved by deep-dive D-a):**
- cks imports `github.com/0xmhha/code-knowledge-vector/pkg/ckv` → `Open(path, OpenOptions{Embedder})`, `Engine.SemanticSearch(ctx, intent, SearchOptions)`.
- The embedder is injected. Promote `internal/embed/ollama` → **`pkg/embed/ollama`** (pure HTTP, zero CGO). cks constructs `ollama.Open(ollama.Options{ModelName: "bge-m3"})` against a locally-running Ollama. Dimension auto-probed (1024).
- **Net effect:** cks build **avoids the ONNX/tokenizers native stack** (`libonnxruntime`, `bgeonnx`) and the `ckv` subprocess. It **does inherit ckv's store CGO (sqlite-vec)** via `pkg/ckv` — a standard, light CGO dep, not the heavy ONNX stack (live-code corrected: `pkg/ckv` is *not* CGO-free; only the *embedder* is). Delete cks's `internal/ckvclient` subprocess proxy (~543 LOC) and its 2/9 timeout failure mode.
- cks `go.mod` adds `require github.com/0xmhha/code-knowledge-vector`.

**ckg (already import-ready, T-14 done):**
- cks imports `pkg/store` (`Reader`, `OpenReadOnly`) and `pkg/mcphandlers` (8 `Register*` + `RegisterAll` + `NewLLMSafeReader`).
- ckg client interface cks needs: `BM25Search`, `FindSymbol`, `Neighbors`, plus the four currently-unwired (`ImpactOfChange`, `EvidenceForIntent`, `GetNodePRs`, `GetSubgraph`) — implement in `01-ckg-refactor.md` / wire in `03-cks-refactor.md`.

**Pipeline roles (the reason ckv & ckg are separate, principled):**
- **ckv = meaning→vocabulary.** A vague/Korean/English request → exact code keywords actually used in the codebase. Requires (i) a multilingual embedder (bge-m3) and (ii) a populated glossary (§6). Both are currently broken; fixing them is the load-bearing restoration.
- **ckg = vocabulary→code.** Keywords → exact related code + modification history + concurrency-impact modules.

### C3 — Indexing & freshness

- cks points ckv and ckg at the **real go-stablenet** working tree, not a self-index. (Current live indexes self-index — must be repointed.)
- ckv index built with `--embedder=ollama --model-name=bge-m3 --src=<go-stablenet>`; rebuild required (manifest model-name change).
- Incremental: reuse `ckv reindex` (git-diff based) and `ckg watch` (fsnotify). On a `go-stablenet` change, both refresh.
- **Reindex trigger ownership (S2):** two paths, both supported. (a) **Agent-triggered:** the planner calls `cks.ops.index{mode:"incremental"}` after detecting staleness via `cks.ops.freshness` (the in-loop path the old shim's `ckv_index`/`ckg_index` served). (b) **Daemon:** a background `ckg watch` + scheduled `ckv reindex` keeps indexes warm out-of-band. cks must implement `cks.ops.index` so the agent is never stuck "stale but cannot refresh."
- **Un-indexed-diff path (pipeline stage 12):** when looping back on a chainbench failure, the fix is in the working branch and NOT yet in the cks index. The coding-agent must combine `git diff` of the branch + cks retrieval of the *surrounding* (indexed) code + the failure log, and let the session LLM reason. cks does not need to index uncommitted code; the agent bridges it.

### C4 — chainbench binary handoff & report

- Input: built binary at `build/bin/gstable` convention, or explicit `binary_path` arg. Remove the 9 hardcoded `gstable` literals (adapter contract) so non-`gstable` binaries don't leak processes.
- Output: `chainbench report --format json` → `{summary:{passed,failed,assertions}, tests:[{status,...}]}`. The coding-agent parses `summary.failed > 0` to decide loop-back.
- chainbench stays a **deterministic test-runner MCP**; LLM judgement of results stays in the agent (consistent with §2.2).

### C5 — Artifacts & state (keep as-is)

coding-agent's `.stablenet-expert/tickets/{JIRA-ID}_{YYYYMMDD_HHMMSS}/` convention (state.json, plan.md, design-v{N}.md, test-report.md, logs/) is well-designed. **Keep it.** It is the trace sink for observability (§8).

---

## 4. Domain-Knowledge Subsystem (the root-problem-(b) fix)

### 4.1 Single source of truth

- **Master:** `code-knowledge-system/docs/domain-knowledge/projects/go-stablenet/entries/*.yaml` (structured entries with `code_anchors`, `risk_level`, `invariants`, `pitfalls`).
- **Derived operational view (live at query time):** `code-knowledge-vector/policy/stablenet.yaml` (`category` → `watch_out`/`also_review`/`required_tests`, injected on every ckv hit). This is the only channel live today — keep it as the runtime surface.
- **Derived graph view:** ckg `policy.yaml` (Policy nodes + `governed_by` edges) for impact-time surfacing.
- **Sync:** a small codegen script re-derives the ckv + ckg views whenever a cks entry transitions to `verified`. One edit in cks → both consumers update on next reindex.
- **Deprecate** `coding-agent/plugin/skills/stablenet-context` (net-negative: stale contract names `GovStaking/GovConfig/GovNCP` vs actual `gov_council/gov_minter/gov_validator`, assumes WEMIX staking). Replace with a pointer to cks entries + live ckv retrieval.

### 4.2 Extraction vs curation (hybrid)

- **Auto-extractable (~10 items, scales with reindex):** ProposerPolicy (RoundRobin/Sticky), `QuorumSize = ⌈N − (N−1)/3⌉`, `Power=1` PoA equal-power invariant, diligence constants, DefaultConfig (epoch=10, timeout=1000ms), fee-delegation fork gating, governance test invariants (TOCTOU, burn atomicity), `isJustified()` QBFT-locking docstring. **5 require seeding `// INVARIANT:` / `// CONSENSUS:` markers** in go-stablenet (mechanical, ~30 min) so ckv's invariant extractor indexes them.
- **Irreducibly manual (session-curated, ~6 items):** byzantine-fairness of epoch-length changes, quorum float-precision safety, round-change fork-safety argument, stabilization-epoch trigger semantics, PoA-vs-WEMIX staking distinction, Sticky-policy proposal-concentration risk. These are the exact knowledge that causes Ethereum-assuming / byzantine-unfair LLM designs. One focused domain-expert session.

### 4.3 Byzantine-fairness retrieval path (4 layers)

1. **L0 (now):** ckv `guidance.watch_out` fires on any `consensus/**` or `systemcontracts/**` chunk.
2. **L1 (after marker seeding):** Tier-2 marker chunks score high on queries containing `quorum/epoch/proposer/validator`.
3. **L2 (after ckg policy load):** `governed_by` edges surface the policy node during `impact_analysis`/`get_for_task` even when the query lacks the right keywords.
4. **L3 (always-on backstop):** session-start injection (~500 tokens) of the 3–5 highest-priority invariants (e.g. "all StableNet validators have equal power=1; epoch-length changes affect diligence asymmetrically").

---

## 5. Evaluation Strategy

Resolves "eval became a burden" by splitting along the §2.2 boundary:

- **Binary deterministic self-tests (stay in each repo):** recall@k, MRR, P/R/F1, citation accuracy, hallucination byte-check — pure computation against fixture ground truth. Run in CI. (ckv `eval` minus judge; ckg `internal/eval/retrieval`; stablenet-knowledge `cks-eval`.)
- **LLM-based quality eval (moves to agent/session):** "does retrieval beat grep?", "is the plan correct?", answer judging/comparison. Driven by coding-agent through the cks MCP. Remove `anthropic-sdk-go` + `cli-wrapper` from ckg; remove `internal/judge` + Claude scorers from ckv.
- **North-star:** ONE honest end-to-end go-stablenet eval (real bge-m3 + proper index + wired domain knowledge + N≥3) replaces the four siloed synthetic evals that gave false comfort (recall@5 1.0 on toy fixtures).

---

## 6. Migration / Build Order

Dependency-reverse (contract → backends → composer → consumer):

| Order | Doc | Gist | Depends on |
|---|---|---|---|
| 0 | `00` (this) | Lock C1–C5 + JSON Schema SSoT + domain SSoT + eval split | — |
| 1 | `01-ckg-refactor` | Implement 4 missing client methods; `pkg/bm25` stability; fill `code_snippet`; excise `internal/eval` LLM (drop anthropic+cli-wrapper); keep retrieval self-test | 0 |
| 2 | `02-ckv-refactor` | Promote `internal/embed/ollama`→`pkg/embed/ollama`; bge-m3 path; populate glossary (hybrid §4.2); excise judge/prregress-Claude; index go-stablenet | 0 |
| 3 | `03-cks-refactor` | Import pkg/ckv (Ollama bge-m3) + ckg in-process; delete subprocess proxy; lock C1 surface; domain sync script | 0,1,2 |
| 4 | `04-chainbench-refactor` | Normalize tool names to C1; remove `gstable` hardcoding (adapter); finish Go-wire init/start; register in `.mcp.json` | 0 |
| 5 | `05-coding-agent-refactor` | Delete cks shim, point `.mcp.json` at real cks; rename tool calls to C1; fix model IDs (`opus-4.7`→`claude-opus-4-7`); register chainbench; deprecate stablenet-context skill | 0,3,4 |

Each row is implementable in an isolated session against only that repo, because the cross-project contract is fixed here.

> **Evaluation timing (S7):** validation is **not** a pre-refactor gate. Implement rows 1–5 (each isolated session), then run the integrated evaluation + debug loop (§9). The system is too broken to measure a meaningful "before."

---

## 7. Decisions Locked

- **Strategy:** R1′ — keep the ckv→ckg→cks pipeline + roles; cks is the sole agent-facing MCP (Go import); binary=deterministic/session=LLM; bge-m3 via Ollama; domain knowledge wired.
- **ckv/ckg MCP servers:** kept **dev-only** behind a build tag (independent debug/validation), removed from the production agent path.
- **Glossary/domain population:** hybrid — code-extraction (auto) + session-curation (manual reasoning).
- **Embedder:** bge-m3 (multilingual, 8192-token, 1024-dim) served via Ollama; final choice ratified by the §9 integrated evaluation.

---

## 8. Observability

- Unify on structured logging (`slog`) across the three Go services.
- The per-ticket `.stablenet-expert/tickets/{id}_{ts}/logs/` directory is the trace sink (already implemented via hooks). OTel is optional/future.

---

## 9. Integrated Evaluation & Debug Loop (post-implementation)

**Why not a pre-refactor spike:** the thesis (knowledge-retrieval beats LLM grep/read) cannot be measured on the current codebase — too much is non-functional (`FakeEmbedder`, self-indexed, subprocess hangs, dead domain knowledge, chainbench unregistered). A "minimal measurable slice" would itself require building most of the ckv+cks retrieval core, so a pre-gate spike saves little. Validation therefore happens **after** the refactor, as an integrated evaluation + debug loop (the LangSmith workshop build→evaluate→debug pattern; matches the vision's stages 11–15).

1. **Implement** `01`–`05` per their detailed plans (each in an isolated session, dependency order `00` §6).
2. **Stand up the integrated system:** go-stablenet indexed (ckv bge-m3 + ckg), cks in-process, chainbench registered.
3. **Run integrated evaluation:**
   - *Retrieval quality:* agent-orchestrated cks primitives vs LLM grep/read on ~15 real go-stablenet tasks — accuracy + token cost, N≥3.
   - *End-to-end pipeline:* sample tickets through `/work` → plan → implement → chainbench, measuring the full loop.
4. **Debug from results:** triage failures, root-cause them (using the same cks retrieval), fix, re-evaluate. Iterate until the pipeline is green.
5. **Decision on the thesis:** if retrieval shows no accuracy/token win over grep, reopen the §2.3 control/mechanics split and composer design with real data before further investment. The integration value (jira→merge + chainbench validation) stands independent of the retrieval-savings thesis.

---

## 10. Open Risks

- Embedder A/B is throughput-gated (~0.74 chunks/s on dev machine → full go-stablenet embed ~6h+; 3-way A/B ~18h+). bge-m3 chosen to avoid a dimension migration and to keep the spike to one build.
- ckg `runIncremental` partial-cache path is disabled (correctness); cold rebuild is the fallback (~40s on go-stablenet) until the reverse-ref index lands.
- The thesis itself is unproven (§1) — the §9 integrated evaluation is non-optional; if it shows no token/accuracy win, the §2.3 split is revisited with real data before further investment.

## 11. Pipeline-completeness items (integrated audit, 2026-06-02)

Cross-checking the 11 docs against the original 15-stage vision surfaced items with weak/no owner. Resolved owners below; open judgment calls are flagged for ratification.

| Vision element | Status | Owner / action |
|---|---|---|
| **Stage 1 — Jira ticket TEMPLATE format** | **was unowned → ADD** | Author `stablenet-expert/scripts/contract/jira-ticket.template.md` defining required fields per ticket type (feature/bugfix/code_review/release); `template-parse` validates against it and reports `missing_fields`. Parsing was kept; the *template definition* was missing. |
| **Stage 4 — inbound sensitive-info check** | **already owned (audit miss)** | `jira-gateway-mcp` filter engine (14 patterns + entropy); `jira_read_ticket` returns `_filter_metadata.scan_result` (CLEAN/REDACTED/BLOCKED). `pr-sanitize` is the *outbound* counterpart (stage 13). No new work; reference it explicitly so it isn't lost. |
| **Stage 6 — rerank** | **RESOLVED → keep BM25 fusion** | Retain the existing CKV-semantic + CKG-BM25 (RRF) rerank in composer stage1. **If the §9 integrated eval shows a recall/accuracy shortfall, escalate** to a dedicated cross-encoder reranker (e.g. bge-reranker) then — validated alongside the embedder. No new work now. |
| **Stage 8 — PROTECTED folder** | **convention owned; protection unowned** | `.stablenet-expert/tickets/{id}_{ts}/` naming+logs kept (C5). **ADD** protection semantics: write-once perms / no-overwrite guard on the per-ticket dir so artifacts/logs aren't clobbered. Owner: coding-agent (state-machine skill). |
| **Stage 5 — Sonnet relevance pre-pass** | **RESOLVED → ADD** | A cheap **Sonnet** relevance gate runs **before** the opus planner: it reads the parsed ticket and decides "go-stablenet-related?" — non-relevant tickets are rejected/flagged early (token economy; G2). Owner: coding-agent **orchestrator** (new pre-planner step, after TICKET_INTAKE + sensitive-check, before dispatching Planner). The `05` implementation session adds this step + a Sonnet sub-agent or skill. |
| **Stage 14 — review-application command** | **assumed-mature → PIN** | `/review <PR-url>` is "kept" but never pinned. Pin its contract (input = PR url; reads review comments; produces fix plan) in `plans/05`. |
| **Intent (vi) — pre-cks ckv/ckg validation** | **RATIFIED** | Validation runs post-implementation as the §9 integrated loop (the current system is too broken to measure a meaningful "before"). Per-repo **deterministic self-tests** (§5) still guard each repo during its own session; the *thesis* validation is the post-build integrated eval. User-ratified 2026-06-02. |
