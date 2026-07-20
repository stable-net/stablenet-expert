# 06 — R1′ Integration Verification Report

> **Date:** 2026-06-04 · **Method:** read-only audit across the five repos (no code modified).
> **Scope:** Verify, case by case, whether the implemented R1′ system actually delivers the
> integration capabilities it was built for. Derives the gap list and the prioritized next actions.
> **Repos audited:**
> - cks — `code-knowledge-system`
> - ckv — `code-knowledge-vector`
> - ckg — `code-knowledge-graph`
> - chainbench — `chainbench`
> - coding-agent — `coding-agent`
> - go-stablenet (source under test) — `stable-net/go-stablenet-latest`

---

## 0. Executive summary

**The engineering (wiring/features) is essentially complete; the shortfalls are content and
measurement, not architecture.**

- cks uses ckv+ckg in-process and exposes them over a 13-tool MCP surface that an external
  consumer (coding-agent) reaches end-to-end. ✅ (cases 1, 2, 3)
- The feature to build ckv/ckg datasets from go-stablenet code + reference docs exists. ✅ (case 4)
- coding-agent is a loadable Claude Code plugin that covers the full development lifecycle. ✅ (cases 6, 8-pipeline)
- **Three real gaps remain:**
  1. **Domain-knowledge content is empty at runtime** — 23 curated entries, **0 verified**, so the
     delivery path emits nothing; 3 expert dimensions are unauthored (case 8-domain). **Highest leverage.**
  2. **MCP existence/health checking is partial** — registered but mostly assumed-connected (case 5).
  3. **The 3-way performance/cost comparison harness does not exist** — the foundation for continuous,
     measurable self-improvement is unbuilt (case 10). **Largest net-new build.**

Verdict legend: **DONE** (capability present & wired) · **PARTIAL** (present but with a load-bearing gap) ·
**MISSING** (capability absent).

---

## 1. Case-by-case findings

### Case 1 — Can cks sufficiently USE ckv and ckg? — **DONE**

- cks imports ckv `pkg/ckv` and ckg `pkg/store` + `pkg/impact` + `pkg/evidence` + `pkg/concurrency`
  **in-process** (normal Go module requires; no `os/exec` in the client dirs).
- All client methods implemented against real backend APIs, none stubbed:
  - ckv (4): `SemanticSearch`, `Health`, `Freshness`, `Close` — `internal/ckvclient/real.go:74,109,126,141`.
  - ckg (10): `BM25Search→SearchFTS`, `FindSymbol`, `Neighbors→NeighborhoodByQname`,
    `ImpactOfChange→impact.Compute`, `EvidenceForIntent→evidence.BuildPack`, `GetNodePRs`,
    `GetSubgraph→SubgraphByQname`, `ConcurrencyImpact→concurrency.Analyze`, `Health`, `Close`
    — `internal/ckgclient/real.go:200,259,315,362,377,409,530,577`.
- `var _ Client = (*Real)(nil)` compile assertions hold; build + client tests pass.
- **Gap:** none. (Minor: the ckg real adapter's live-SQLite open path is exercised at runtime, not in unit tests.)

### Case 2 — External request (coding-agent) → cks → ckv+ckg, end-to-end? — **DONE (defaults to Smart Dummy)**

- The composer pipeline is sequential and each stage hits the stated backend (`internal/composer/composer.go:157-202`):
  intent → **stage1 = ckv `SemanticSearch`** → **stage2 = ckg `BM25Search`+`FindSymbol` (RRF)** →
  **stage3 = ckg `Neighbors`** → budget → sanitize.
- `cks.context.get_for_task` flows through all stages; the other 12 tools call `d.CKV.*`/`d.CKG.*` directly.
  All 13 tools registered (`internal/mcp/server.go:79-91`).
- **Gap (by design):** `config.Default()` ships empty backend paths (`internal/config/config.go:139-142`),
  so out-of-box every tool runs on the **Smart Dummy** (non-crashing placeholder + "run this skill" instructions)
  and `cks.ops.health` reports `degraded`. Real backends activate **iff** the operator points the config at
  built ckv/ckg datasets with a live embedder.

### Case 3 — Does cks run as an MCP server (+ usage)? — **DONE (usage doc gap)**

- `cmd/cks-mcp/main.go:111` serves stdio via `mark3labs/mcp-go v0.52.0`; builds (CGO required — sqlite-vec).
- 13 `cks.*` tools registered; `internal/mcp/schema_golden_test.go` pins the exact set and passes.
- Degraded mode boots without Ollama/bge-m3 (DegradedDummy / FakeEmbedder{Dim:1024}).
- **Run:** `make build-bins` → `./bin/cks-mcp -config ./policies/cks.yaml.example` (only flag is `-config`;
  stdio-only — exits if `listen.mcp_stdio:false`).
- **Gap:** **no client-registration example anywhere** (no `claude mcp add` / `.mcp.json` snippet);
  README is stale ("Pre-α / not yet wired"); `docs/coding-agent-mcp-mapping.md` says **11 tools** (missing
  `concurrency_impact`, `ops.index`).
  - Working registration would be:
    `claude mcp add cks -- /abs/bin/cks-mcp -config /abs/cks.yaml`.

### Case 4 — Build ckv/ckg datasets from go-stablenet code + docs (feature exists)? — **DONE (feature) / content-gated**

- `internal/mcp/ops_index.go` shells `ckv build/reindex` (`--src --out --embedder=ollama --model-name`) +
  `ckg build --src --out`; config-wired via `IndexConfig` (`cmd/cks-mcp/main.go:165-170`).
- `cmd/cks-domain-sync` derives the **ckv view** (`stablenet.yaml`) + **ckg view** (`policy.yaml`) from
  `docs/domain-knowledge/projects/go-stablenet/entries/*.yaml`.
- ckv `build`/`reindex` and ckg `build --src --out --policy-file` CLIs exist; ckg `--policy-file` consumes
  exactly the `governs[]` shape domain-sync emits.
- **Operator sequence:** `cks-domain-sync` → `ckv build … --model-name=bge-m3` → `ckg build … --policy-file` →
  point cks config at the outputs.
- **Gap:** 0 of 23 domain entries are `verified` → domain-sync emits empty today; `ops.index` does **not**
  thread `--policy-file` (governance edges require a manual `ckg build --policy-file`).

### Case 5 — coding-agent checks cks/jira/chainbench MCP existence? — **PARTIAL**

- All three registered in `plugin/.mcp.json` (jira-gateway, cks, chainbench).
- Only **chainbench** has a pre-flight: the evaluator lists tools and diffs against the expected C1 set
  (`plugin/agents/evaluator.md` §7.0) — but this checks tool *names*, not process liveness.
- **cks:** `cks.ops.health` is defined in the contract (`contract/agent-mcp.schema.json`) but **called nowhere**
  in the plugin. Only a freshness gate exists (staleness, not connectivity).
- **jira-gateway:** no connectivity/health/auth-error branch at all — `jira_read_ticket` is called and only the
  content scan result is handled.
- **Gap:** no orchestrator-level "all three servers reachable" pre-flight; `cks.ops.health` is an unused capability.

### Case 6 — Valid Claude Code plugin? — **DONE**

- `plugin/.claude-plugin/plugin.json` present and valid (name, version 0.1.0, description, author, license,
  `mcpServers`).
- commands/ (4), agents/ (4), skills/ (5), hooks/ (hooks.json + 2 executable scripts) all present; all JSON
  valid; all agent/command/skill frontmatter well-formed.
- **No loading blockers.** Unset env vars only prevent the affected server from starting, not plugin load.

### Case 7 — Harness engineering / autonomous operation? — **PARTIAL**

- The orchestrator self-dispatches planner→implementer→evaluator, auto-handles bug-cycle re-entry and BLOCKED,
  and bounds retries (`max_eval_cycles=3`, `max_design_revisions=3`). `state.json` + `get_resume_point` give
  checkpointed, resumable runs. `--local <ticket.json>` enables non-Jira automated runs.
- On a clean ticket, `/work` runs intake→PR with no human input.
- **Gaps to full automation:**
  - No scheduler/daemon launches `/work` itself; invocation is manual; hooks are **log-only** (do not drive state).
  - The "state machine" is **LLM-executed prose**, not a deterministic engine — replay/determinism is best-effort.
  - Human gates fire on: sanitize-REDACTED, release version tag/push, branch conflict, BLOCKED, destructive git.
  - `/merge` is a separate manual command; the pipeline stops at COMPLETION (no auto-merge by design).

### Case 8 (pipeline) — Do commands/skills cover the full lifecycle? — **DONE (9/9; 2 PARTIAL)**

| Stage | Owner | Verdict |
|---|---|---|
| 1. Requirement/issue analysis | `work.md` intake + `template-parse` → `planner.md` §3.1–3.3 | COVERED |
| 2. Identify actual relevant code (cks) | `planner.md` §3.2/§3.4 (semantic_search, get_subgraph, find_callers, concurrency_impact) | COVERED |
| 3. Analyze required modifications (code-grounded) | `planner.md` §3.5 (impact_analysis) → analysis.md/related-code.json | COVERED |
| 4. Design | `planner.md` §5 (per-step design + self-review revision loop) | COVERED |
| 5. Implementation plan | `planner.md` §4 (atomic steps, dependency DAG, verification plan) | COVERED |
| 6. Ralph-loop implementation | `implementer.md` §4 (per-step build verify, checkpoint/resume, split commits) | COVERED |
| 7. chainbench build + test built binary | `implementer.md` §6.1 (build/bin/gstable handoff) + `evaluator.md` §7 | **PARTIAL** (external MCP; absence → FAIL, no substitute) |
| 8. Test planning | `plan.md` §4.4 Verification Plan + `-race` scope from concurrency_impact | **PARTIAL** (embedded, not a discrete deliverable) |
| 9. Commit(s) + PR | `implementer.md` §4.4 + `orchestrator.md` §4 (PR assemble/sanitize/push/labels/Jira) | COVERED |

### Case 8 (domain depth) — Can cks make the LLM a senior go-stablenet expert? — **SCAFFOLD complete / CONTENT absent**

The machinery is built and correct; the knowledge base is shallow-to-empty and **inert at runtime**.

- **Entries:** 23 YAML files, **all `status: needs_verification` (0 verified)**; `cks-domain-sync` emits only
  verified entries → **executed live: 0 categories, 0 policies**. `glossary.yaml` is empty.
- **Source markers:** go-stablenet has **0** `INVARIANT:`/`CONSENSUS:`/`SECURITY:` markers, so the ckv Tier-2
  extractor (which exists) has nothing to extract.
- **Delivery disconnect:** ckv's Go code never references the domain-knowledge entries; the rich prose reaches
  runtime *only* via `cks-domain-sync` → policy `watch_out`/`governs`, which is empty today. `policy/stablenet.yaml`
  (284 lines) is **hand-authored**, not cks-derived.
- **Per-dimension coverage:**

| Dim | Topic | Verdict |
|---|---|---|
| (a) | Blockchain concepts (general) | COVERED-SHALLOW |
| (b) | Cryptography (esp. go-stablenet: signatures/hashing/fee-delegation) | COVERED-SHALLOW (BLS partial; no signature/hash/randao depth) |
| (c) | Philosophy/design vs Ethereum & Kaia (Klaytn) | **ABSENT** |
| (d) | Go concurrency patterns | **ABSENT** |
| (e) | Distributed-network timing / protocol impact | COVERED-SHALLOW (constants only) |
| (f) | Smart/system-contract analysis | COVERED-SHALLOW (addresses; no per-contract logic) |
| (g) | Consensus algorithm (WBFT/QBFT) detail | COVERED-DEEP *(best area; 8 expert entries — but unverified → inert)* |
| (h) | Policy/governance specifics | COVERED-SHALLOW |

- **Quality note:** the entries that exist are expert-grade (line-numbered `code_anchors`, real `invariants`,
  `pitfalls`, `constants`) — the problem is **breadth + verification**, not authoring quality.

### Case 9 — Logging/monitoring of module I/O for debugging? — **PARTIAL**

- **cks (debugging-grade):** `internal/footprint` emits per-stage JSONL events (intent/stage1..stage5 + per-stage
  timings) correlated by `trace_id`/`run_id`, **no sampling**; wired across all stages in `cmd/cks-mcp/main.go:315-345`.
  `internal/auditlog` is append-only + SHA-256 hash-chained. A cks retrieval is fully reconstructable after the fact.
- **coding-agent (artifact/state-grade):** the trace sink `.coding-agent/tickets/{id}_{ts}/logs/` holds `state.json`
  (status/timestamps/`plan_progress`/`failure_log`), `impl.log`, `eval-*.log`, `test-report.md`, and the planner/design
  artifacts. Hooks log subagent completion + git commits.
- **Gap:** coding-agent does **not** capture verbatim sub-agent prompts/responses — `on-agent-complete.sh` records only
  `subagent=<type>`. Reconstruction is artifact-level, not transcript-level. (The contract's "unify on slog across the
  three Go services" is aspirational; cks uses zap for footprint.)

### Case 10 — 3-way performance/safety/cost comparison + report? — **MISSING**

- **Exists (single-mode only):** `cmd/cks-eval` (retrieval P/R/F1 + budget utilization + latency, cks-on, no LLM),
  ckv `internal/eval/prregress` (plan quality, needs an injected LLM), ckg `cmd/eval-gate` (recall/precision regression gate).
- **Absent — everything the 3-way comparison needs:**
  - a **mode-switching runner** for (A) agent+cks, (B) code-only, (C) code+comprehension-skills — none exists;
    the pipeline is hardwired to the full cks path.
  - **LLM token + cost accounting** — the only "tokens" are retrieval-budget estimates, not input/output token usage or USD.
  - a **final-code correctness oracle** per mode (test/chainbench pass) wired as a comparable metric.
  - a **cross-mode safety metric** and an **A/B/C × {correctness, tokens, performance, safety, cost} report generator**.
- The system contract `00 §9` defines this as a **future agent-driven build→evaluate→debug loop, not built code**, and
  declares the underlying thesis (retrieval beats grep) **UNPROVEN**.

---

## 2. Prioritized next actions

> Effort is rough. "Machine" notes where the work must run (content authoring + heavy index builds need go-stablenet +
> a capable/Ollama machine; tooling/scaffold work runs here). P0 is the single highest-leverage item.

| Priority | Action | Why it matters | Effort | Machine |
|---|---|---|---|---|
| **P0** | **Populate + verify domain knowledge.** Promote the 23 entries to `verified`; author the 3 absent dimensions — (c) ETH/Kaia/WEMIX philosophy & divergence, (d) Go-concurrency patterns, and deepen (b) crypto (signature scheme, hashing, fee-delegation crypto, randao); seed `// INVARIANT:`/`// CONSENSUS:` markers in go-stablenet source; populate `glossary.yaml` (via `cks-glossary-gen`). | Opens the **only** path that delivers domain knowledge to the runtime LLM — without it cases 8-domain stays inert regardless of quality. A single `verified` promotion activates `cks-domain-sync` → ckv/ckg policy views. | High (authoring) | go-stablenet machine (+ domain expert session) |
| **P1** | **Build the 3-way comparison harness (case 10).** Net-new: a mode-switching runner (A/B/C), LLM input/output **token + cost accounting**, a per-mode **correctness oracle** (test/chainbench result), a safety metric, and an A/B/C report generator over {correctness, tokens, performance, safety, cost}. Combine with case-9 observability for a continuous-improvement loop. | The foundation for measurable, compounding efficiency gains — and the only way to settle the UNPROVEN "retrieval beats grep" thesis with data (`00 §9`). | High | here (tooling) → runs need Ollama/go-stablenet |
| **P2** | **MCP existence/health pre-flight (case 5).** Add `cks.ops.health` to the planner intake; add a jira transport/auth error branch in `work.md`; add an orchestrator-level "all three servers reachable" pre-flight before dispatch. | Turns three assumed-connected servers into checked dependencies — fewer silent mid-run failures; cheap, high-robustness. | Low | here |
| **P3** | **Index-pipeline + usage-doc fixes (cases 3, 4).** Thread `--policy-file` into `cks.ops.index` (full mode) so governance edges build automatically; add a `claude mcp add` / `.mcp.json` registration example for cks; refresh README + the mapping doc (11→13 tools). | Removes the manual `ckg build --policy-file` step and the first-run doc gap. | Low–Med | here |
| **P4** | **Transcript-grade observability (case 9).** Capture verbatim sub-agent prompt/response (not just `subagent=<type>`) into the per-ticket trace sink; consider a coding-agent footprint analogous to cks's JSONL. | Required substrate for the P1 token/correctness measurement and for debugging agent decisions. | Med | here |

### Sequencing note
P2/P3/P4 are independent, low-risk, and runnable on this machine now. P1 (harness) depends on P4 (token capture) for its
cost/accuracy metrics and is the natural pairing. P0 (content) is the highest-leverage but runs on the go-stablenet machine
with domain-expert input; it unblocks the *quality* the rest of the system measures.

---

## 3. Fact / Opinion

| Type | Statement | Confidence |
|---|---|---|
| Fact | cks imports ckv+ckg in-process; all 14 client methods are real (not stubs); cks-mcp serves 13 tools over stdio with a passing golden test and a degraded fallback. | None |
| Fact | 23 domain entries are all `needs_verification` (0 verified); `cks-domain-sync` emits 0/0; `glossary.yaml` empty; 0 source markers in go-stablenet. | None |
| Fact | `.mcp.json` registers all 3 servers; only chainbench has a pre-flight (tool-name) check; `cks.ops.health` is defined but called nowhere. | None |
| Fact | No A/B/C mode-switching harness, no LLM token/cost accounting, and no comparison-report generator exist in any repo; `00 §9` frames this as a future agent-driven loop. | None |
| Opinion | The engineering is sufficient for the goal; the binding shortfalls are domain content (P0) and the comparison harness (P1), not architecture. | High |
| Opinion | Verifying the entries is the single highest-leverage action — it activates the whole domain-delivery path. | High |
| Opinion | The 3-way comparison is the largest unbuilt capability and the keystone of a self-improving system; existing evals contribute only retrieval-metric primitives. | High |
| Opinion | Case-5 hardening is cheap and worth doing before any unattended/automated runs. | Mid |

---

## 4. 2026-06-07 갱신 (post-session integration)

> **Date:** 2026-06-07 · **Scope:** §1 케이스 verdict 재평가 + §2 우선순위 표 갱신 + §3 본 세션 신규 발견·해결 결함 + 갱신된 Fact/Opinion. 원본(2026-06-04) 본문은 보존; 본 섹션이 권위 있는 최신 상태.

### 4.1 Case-level verdict 재평가

| Case | 원본 (06-04) | 갱신 (06-07) | 근거 |
|---|---|---|---|
| Case 1 (cks↔ckv/ckg) | DONE | DONE+ | 실제 26k chunks 인덱스 + cks.context.semantic_search 한국어 검색 작동 검증 |
| Case 2 (외부 e2e) | DONE (defaults to Smart Dummy) | **DONE (real backends)** | cks.yaml 작성 + cks.ops.health=ok 검증, Smart Dummy 우회 |
| Case 3 (cks MCP) | DONE (usage doc gap) | DONE | usage doc gap은 P3 미완으로 잔여 |
| Case 4 (dataset build) | DONE / content-gated | **DONE / partially activated** | ckv 26,047 chunks + ckg 256k nodes 빌드. cks-domain-sync에서 governs[] qualifier fix(Task #16/#21) 후 ckg policy_nodes=7 / **governed_by_edges=30** (이전 0). 채널 ② 활성화 (domain 카테고리 196 chunks) |
| Case 5 (existence/health) | PARTIAL | **DONE (already implemented)** | orchestrator.md §2.0 'MCP pre-flight'(3-서버 registration + env vars UNSET 검증 + state.json 기록) + work.md §5.2(jira 호출 실패 → 진단+cleanup+중단) 모두 06-04 이후 구현됨. design은 분산 헬스 체크 (downstream live: planner §3.0 cks.ops.health + evaluator §7.0 chainbench pre-flight) |
| Case 6 (Claude Code plugin) | DONE | DONE | 변경 없음 |
| Case 7 (autonomous) | PARTIAL | PARTIAL | 변경 없음 (scheduler/daemon 미구현 그대로) |
| Case 8 (pipeline) | DONE (9/9; 2 PARTIAL) | DONE | 변경 없음 |
| Case 8 (domain depth) | SCAFFOLD / CONTENT absent | **SCAFFOLD / CONTENT partial** | 신규 13 entries 작성 (A12/A13/A14 subsystem + T2 trap 9 + theory 4); go-stablenet에 `// INVARIANT:/CONSENSUS:/SECURITY:` 마커 10건 시딩(8 anchors); stablenet-invariants SKILL이 5→11 invariants로 보강; cks-domain-sync 산출물에 신규 entries 포함. **잔여**: 16+13=29 needs_verification → verified 승격(도메인 전문가 세션). |
| Case 9 (logging) | PARTIAL | PARTIAL | 변경 없음 (transcript-grade 미완) |
| Case 10 (3-way harness) | MISSING | MISSING | 변경 없음 |

### 4.2 본 세션 신규 발견 + 해결된 R1' 통합 결함 (06-04 보고서에 없음)

원본 §1의 case별 분석에 포함되지 않은 **결함 3건**이 본 세션 검증 과정에서 신규 발견 → 모두 해결:

| # | 결함 | 측정값 (해결 후) |
|---|---|---|
| #17 | **ckv `--ckg` alignment 미구현** (옵션은 flag로 노출되지만 build pipeline에 전달되지 않음, ckg_node_id 0/26,036) | 새 패키지 `internal/ckgalign` + Builder.Options.CKGPath wiring. **23,213/26,036 (89.2%) 채워짐**. symbol chunks 기준 91.9%. 무작위 100 sample file_path 일치율 100% |
| #18 | **cks composer가 chunk metadata 미활용** (ckvclient가 contract.Hit으로 변환 시 symbol_name/ckg_node_id 버림 → extractKeywords가 file basename만 사용) | `contract.Hit{Symbol, CKGNodeID}` 추가 + ckvclient 변환 보강 + stage1 extractKeywords가 hit.Symbol 우선 사용. 영향 패키지 4/4 테스트 PASS. semantic_search 결과 모든 hit에 ckg_id 노출 검증 |
| #16 | **`governs[]` qname mismatch** (cks-domain-sync가 `DefaultAnzeonConfig`만 emit, ckg는 `params.DefaultAnzeonConfig`로 저장 → 27건 'no code node found') | `qualifyGovernsSymbol(file, symbol) → "<pkg>.<symbol>"` 추가 (file 디렉토리 마지막 segment → 패키지명 추정). unit test 7/7 PASS. ckg full rebuild 후 **governed_by 0 → 30** edges |

> 이 3건은 모두 plans/02-ckv-plan.md, plans/03-cks-plan.md spec에 명시되지 않은 신규 통합 결함이다. R1' 시스템의 핵심 정합성을 깨는 결함이었고, 사용자 질문("ckv↔ckg qname 규칙 적용?")으로 발견되었다.

### 4.3 우선순위 표 갱신

| 원본 | 작업 | 상태 (06-07) |
|---|---|---|
| P0 | Populate + verify domain knowledge | **부분 완료**: 13 신규 entries + 8 anchors marker 시딩 + stablenet-invariants 보강. **잔여**: 29 verified 승격 (도메인 전문가) + glossary `-status verified` 재생성 |
| P1 | 3-way comparison harness | 그대로 (큰 net-new build, 별도 세션) |
| ~~P2~~ | MCP existence/health pre-flight | ✅ **이미 구현 확인됨** (work.md §5.2 + orchestrator.md §2.0). 추가 작업 불필요 |
| P3 | Index-pipeline + usage-doc fixes | 부분 완료: cks.yaml에 `backends.ckg.policy_file` 명시(cks.ops.index full mode 시 forward됨). 미완: README 11→13 tools 업데이트, coding-agent-mcp-mapping.md tools 카운트 |
| P4 | Transcript-grade observability | 변경 없음 |

**4.3.1 신규 후속 작업 (06-04 시점 미식별)**

| 신규 # | 작업 | 비고 |
|---|---|---|
| (R1' 보강) | alignment 9% 실패 chunks 원인 분석 | 자동 생성 코드/멤버 redeclaration 패턴 추정. coverage 91.9 → 95%+ 가능 |
| (R1' 보강) | ckg→ckv 역참조 alignment (ckg nodes에 chunk_id) | 양방향 cross-reference |
| (검증) | cks 13 tools 전체 응답 형식 검증 | 본 세션은 health/freshness/semantic_search/impact_analysis만 실측 |

### 4.4 추가 회귀 방지 (본 세션 신규)

| 추가 가드 | 위치 |
|---|---|
| ckg `pkg/store/score_contract_test.go` (외부 store_test): `TestSearchFTS_ScoreContract` + `TestBuildGoStablenetSmoke_M2D` | plans/01 Step 2/12 요건 충족. CKG_GSN_GRAPH 환경변수 opt-in |
| chainbench `tests/unit/tests/adapter-mapping.sh` (06-04 이후 추가됨) | plans/04 M1 매핑 검증 |

### 4.5 갱신된 Fact / Opinion

| Type | Statement | Confidence |
|---|---|---|
| Fact | 36 domain entries (기존 23 + 신규 13). verified=7, needs_verification=29. cks-inventory-check 통과 (0 errors, 0 warnings) | None |
| Fact | go-stablenet에 `// INVARIANT:/CONSENSUS:/SECURITY:` 마커 10건 시딩 (8 파일, ckv invariant chunks 162→172) | None |
| Fact | ckv index: 26,047 chunks / bge-m3 / 1024-dim / indexed_head=9978930ba. ckg_node_id 채워진 비율 89.2%. 무작위 100 sample 정확도 100%. Tier-2 마커 추출 100% (10/10) | None |
| Fact | ckg index: 256k nodes / 2M edges / 587MB / **policy_nodes=7, governed_by_edges=30** (이전 0) | None |
| Fact | `.mcp.json` 3 servers + orchestrator.md §2.0 사전체크 + work.md §5.2 jira 실패 분기 모두 구현됨. case 5 PARTIAL → DONE 갱신 | None |
| Fact | 신규 발견 R1' 결함 3건(#17/#18/#16) 모두 본 세션에서 해결 (plans/02/03 spec에 미명시) | None |
| Opinion | 원본의 P0(domain content)가 여전히 가장 큰 잔여 항목 — 13 신규 entries 작성으로 구조는 채워졌으나 verified 승격 + glossary 활성화가 retrieval quality의 ceiling | High |
| Opinion | 본 세션 해결한 R1' 결함 3건은 **plans/02/03 작성 시점에 미식별된 통합 결함** — 향후 plans/spec 작성 시 cross-module data flow 점검 단계 추가 권장 | High |
| Opinion | P1 (3-way harness)는 본 세션의 정확도 측정 한계(retrieval recall/MRR 부재 — ground-truth 셋 없음)를 해결할 유일한 경로. ground-truth 셋 작성이 사전 조건 | High |
| Opinion | Case 5는 06-04 시점에는 PARTIAL이었지만, 그 사이 work.md/orchestrator.md가 보강되어 DONE. 06 작성 후 ~3일 만에 처리된 패턴은 다른 PARTIAL/MISSING도 산발적으로 해결될 수 있음을 시사 — 정기 재검증 필요 | Mid |
