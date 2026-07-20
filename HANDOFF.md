# Coding Agent — Cross-Session Handoff

> ⚠️ **SUPERSEDED (2026-07-05):** 이 문서는 **2026-06-05 스냅샷**(R1′ 직후)이며 이후 갱신되지 않았다.
> 현재 작업 SSoT = [`docs/WORKLIST.md`](docs/WORKLIST.md), 재개 컨텍스트 =
> [`docs/HANDOFF-phase2-pr77-2026-07-03.md`](docs/HANDOFF-phase2-pr77-2026-07-03.md), 문서 인덱스 =
> [`docs/DOC-MAP.md`](docs/DOC-MAP.md). §3(시스템 개요)·§5(설계 결정 Why)는 여전히 유효한 레퍼런스이나,
> §1/§6/§7/§10(상태·완료작업·남은작업·위험)은 stale — 현재 상태로 믿지 말 것.

> 다른 머신/다른 세션에서 작업을 이어받기 위한 자기완결적 컨텍스트 문서.
> 이 저장소를 clone 한 새 세션이 이 문서만으로 같은 목적·같은 규칙으로 작업을 계속할 수 있도록 작성됨.

| 항목 | 값 |
|------|----|
| 작성일 (최초) | 2026-05-29 |
| 최종 갱신 | 2026-06-05 — R1′ refactor 적용 + Step 1~9 + 후속 4개 PR(통합검증·MCP health·3-way bench·도메인 큐레이션 plan) 반영 |
| 마지막 커밋 | `31e42da docs(r1-refactor): add the domain-knowledge curation plan (#4)` |
| 브랜치 | `main` (origin과 동기화) |
| 작업 진행률 | R1′ Step 1~9 + 후속 PR #2/#3/#4 완료. 자체 stablenet-knowledge shim 삭제 + 외부 stablenet-knowledge/chainbench 위임 + 3-way bench harness + transcript observability. **남은 격차** = P0 도메인 콘텐츠 작성(외부 `code-knowledge-system` 저장소 소관) + 외부 03/04 출하 후 E2E 검증 |

---

## 1. 1분 요약 (TL;DR)

**프로젝트 정체성**: `go-stablenet` 전용 Claude Code plugin. Jira 티켓을 입력으로 받아 자동으로 분석→설계→구현→테스트→PR→리뷰 반영→merge 까지 수행하는 다중 에이전트 파이프라인.

**대상 코드베이스**: `go-stablenet` — geth fork. WBFT consensus, ETH 대신 stable coin native, system contracts 다수.

**기술 스택**: Claude Code Plugin (auto-discovery) + Jira Gateway Go MCP (in-tree) + **외부 stablenet-knowledge/chainbench MCP** (R1′ 이후 sibling repos) + Bash hooks + Python 3-way bench harness (in-tree). 임베딩은 Ollama + `bge-m3` (다국어, 1024-dim, R1′ 필수).

**핵심 보안 원칙**: 민감 정보(시크릿/사내 정보)는 LLM에 도달하기 전에 차단해야 한다 → 모든 외부 데이터는 **Proxy MCP Gateway** 패턴으로 필터링.

**R1′ 이후 아키텍처 원칙**: **Binary = deterministic, Session = LLM**. 외부 백엔드(ckv/ckg/stablenet-knowledge/chainbench) 바이너리는 결정론(임베딩·그래프·검증). 모든 LLM 작업은 coding-agent 세션 레이어에 거주.

**현재 상태**: R1′ Step 1~9 + 후속 PR(통합검증·MCP health pre-flight·transcript observability·3-way bench harness·도메인 큐레이션 plan) 적용 완료. **남은 잠금 작업** = (1) 외부 stablenet-knowledge 저장소의 도메인 entry 작성·verified 승격 (P0, 외부), (2) 외부 03(real stablenet-knowledge)/04(chainbench D1) 출하 대기, (3) E2E 검증.

---

## 2. 사용자 규칙 (Critical — 반드시 준수)

이 규칙은 글로벌 CLAUDE.md(`~/.claude/CLAUDE.md`)에 기록된 사용자 명시 선호. 새 머신에도 동일 글로벌 설정이 있다는 가정. 없다면 이 문서를 글로벌 룰의 일부로 취급할 것.

1. **사용자가 한국어로 메시지를 보내면 한국어로 응답.** 영어로 보내면 영어로 응답.
2. **Git commit 메시지는 영어로 작성, 간결하게.**
3. **Commit 메시지에 `Co-Authored-By:` 또는 "Generated with [Claude Code]" attribution 절대 포함하지 않음.**
4. **작업 종료 시 uncommitted 변경사항이 있으면 사용자에게 커밋 여부를 먼저 확인.** 자율 커밋·자율 폐기 금지.
5. **파괴적 git 작업(force push, reset --hard, branch -D)은 사용자 명시 승인 없이 절대 수행하지 않음.**
6. **Reflect-Verify-Fix 프로토콜**: 코드 수정/명령 실행 직후 검증을 *별도 스텝*으로. 3회 연속 동일 오류 또는 2회 수정 후에도 실패하면 중단하고 사용자에게 보고.
7. **민감 정보(secrets/PII)는 grep으로 확인 가능 — 커밋 전 항상 점검.**

---

## 3. 시스템 개요

### 3.1 무엇을 자동화하는가

```
Jira 티켓 (STABLE-xxxx)
  │
  ▼
TICKET_INTAKE → ANALYSIS → PLANNING → DESIGN → IMPLEMENTATION → EVALUATION → COMPLETION
  │              │           │          │        │                │              │
  │              │           │          │        │                │              ▼
  │              │           │          │        │                │           PR + Jira 댓글 + 상태 전이
  │              │           │          │        │                │
  │              │           │          │        │                ▼
  │              │           │          │        │           Pass/Fail → fail 시 사이클 (max 3회) 또는 BLOCKED
  │              │           │          │        ▼
  │              │           │          │     단일/원자 step 단위 커밋
  │              │           │          ▼
  │              │           │       design-v{N}.md (self-review, max revisions 3)
  │              │           ▼
  │              │        plan.md (atomic/reviewable/verifiable steps + verification plan)
  │              ▼
  │           analysis.md + related-code.json (CKV + CKG + stablenet-context)
  ▼
ticket.json (Jira description ADF→Markdown + 민감정보 필터링)
```

**별도 진입점**:
- `/review <PR#>`: PR 코멘트 수집 → 7유형 × 4심각도 분류 → review-feedback-{N}.md → bugfix 모드로 ANALYSIS 재진입
- `/merge <PR#>`: 5단계 전제조건 검증 → squash merge → Jira 완료 처리
- `/status [JIRA-ID]`: 활성 워크스페이스 또는 단일 티켓 상세 확인
- **`/bench <manifest> | <experiment-id> --continue`** (R1′ 후속, PR #3): 동일 태스크를 A(stablenet-knowledge)/B(code-only)/C(code+skills) 3 정보 regime으로 자율 실행. 결정론적 도구 `bench/compare.py`가 토큰·비용·정확성·안전성 비교. token limit 인지 배치+재개. `bench-orchestration` skill이 오케스트레이션 계약 보유

**파이프라인 변종 (RI-18, RI-19)**:
- `feature` (기본): 위의 풀 사이클
- `code_review`: TICKET_INTAKE → ANALYSIS → PLANNING(review-report.md) → COMPLETION
- `release`: TICKET_INTAKE → ANALYSIS → EVALUATION → COMPLETION(git tag + CHANGELOG)
- `bugfix` (review cycle 재진입): PLANNING(plan-fix-{N}.md) → DESIGN → IMPLEMENTATION

### 3.2 아키텍처: B+C 하이브리드

여러 후보 중 사용자가 **B+C 하이브리드** 선택. 의미:
- **B**: Document-driven 상태 머신 (state.json + analysis.md/plan.md/design-v{N}.md/test-report.md를 파일로 보존). 컨텍스트가 truncate 되어도 다음 세션이 파일에서 복원.
- **C**: Multi-agent (Orchestrator + Planner + Implementer + Evaluator). 각 에이전트는 격리 컨텍스트로 dispatch. Orchestrator만 전체 흐름을 본다.

### 3.3 보안 모델: Proxy MCP Gateway

**핵심 결정의 Why**:
- 처음에는 sensitive-check skill로 LLM이 정보를 보고 판단하는 안을 검토. 사용자가 "Skill로 처리하면 정보가 이미 LLM에 도달한 순간 노출이다"라고 지적.
- 결론: **MCP server level**에서 LLM에 도달하기 전에 필터링해야 함. 모든 외부 데이터(Jira description/comments, search results)는 `packages/jira-gateway-mcp/internal/filter`가 정규식 + 엔트로피 + 화이트리스트로 스캔해 REDACTED/BLOCKED 결정 후 sanitized 텍스트만 LLM에 노출.
- **Outbound도 대칭으로 처리**: PR body, squash commit body, Jira 댓글 — `plugins/stablenet-core-dev/skills/pr-sanitize/SKILL.md`가 동일 `packages/shared-patterns/patterns.json`을 적용.

---

## 4. 저장소 레이아웃

> **2026-07-20 이관 메모**: 이 문서는 `coding-agent` 단일-플러그인 리포 시절의 핸드오프 스냅샷이다.
> `stablenet-expert` 마켓플레이스로 이관되며 최상위 경로가 바뀌었다(아래 트리는 최상위만 갱신,
> 중첩 세부 경로는 원 시점 기준 그대로 — 상세는 [ADR-0005](docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)).
> `plugin/` → `plugins/stablenet-core-dev/`, `tools/` → `packages/`, `contract/` → `scripts/contract/`,
> `shared/` → `packages/shared-patterns/`.

```
stablenet-expert/
├── HANDOFF.md                       ← 이 문서. 새 세션 진입점
├── go.work                          ← jira-gateway-mcp 단일 멤버 (R1′로 stablenet-knowledge-mcp 멤버 삭제)
├── packages/
│   ├── shared-patterns/
│   │   └── patterns.json            ← 14개 민감정보 패턴 (CRITICAL/HIGH/MEDIUM + entropy)
│   └── jira-gateway-mcp/            ← in-tree MCP 서버
├── scripts/contract/                ← R1′ Step 1 신규
│   ├── agent-mcp.schema.json        ← C1 SSoT — 26 tools (13 stablenet-knowledge + 7 chainbench + 6 jira)
│   └── lint-tool-names.sh           ← agent/command 마크다운의 도구 참조 vs schema drift 검출
├── plugins/stablenet-core-dev/      ← Claude Code Plugin 본체
│   ├── .claude-plugins/stablenet-core-dev/plugin.json   ← Plugin manifest
│   ├── .mcp.json                    ← 3개 서버: jira-gateway (in-tree), stablenet-knowledge/chainbench (외부)
│   ├── commands/
│   │   ├── work.md                  ← /work — 메인 진입점 (--local 지원, jira 실패 분기)
│   │   ├── review.md                ← /review — PR 코멘트 수집/분류
│   │   ├── status.md                ← /status — 활성/단일 티켓 상태
│   │   ├── merge.md                 ← /merge — squash merge + post-merge
│   │   └── bench.md                 ← /bench — 3-way harness (R1′ PR #3)
│   ├── agents/
│   │   ├── orchestrator.md          ← 상태 전이 dispatch + §2.0 MCP pre-flight (R1′ PR #2)
│   │   ├── planner.md               ← ANALYSIS/PLANNING/DESIGN (4 modes) + §3.0 cks.ops.health
│   │   ├── implementer.md           ← 브랜치 관리 + per-step 구현 + §6.1 build/bin/gstable
│   │   ├── evaluator.md             ← 4-stage 검증 (unit/lint/security/chainbench), C1 도구 이름
│   │   ├── bench-planner-codeonly.md   ← bench mode B (grep/read만, no stablenet-knowledge) (R1′ PR #3)
│   │   └── bench-planner-skills.md     ← bench mode C (grep/read + comprehension skills) (R1′ PR #3)
│   ├── skills/
│   │   ├── state-machine/SKILL.md       ← state.json 읽기/쓰기/get_resume_point/transition guards
│   │   ├── template-parse/SKILL.md      ← 4가지 work-type 파싱 (ADF 참고)
│   │   ├── stablenet-context/SKILL.md   ← path→module 경량 분류기로 deprecate (R1′ Step 3)
│   │   ├── stablenet-invariants/SKILL.md ← L3 always-on 비잔틴 공정성 invariant (R1′ Step 4)
│   │   ├── pr-sanitize/SKILL.md         ← outbound 민감정보 스크러버
│   │   └── bench-orchestration/SKILL.md ← 3-way harness 오케스트레이션 (R1′ PR #3)
│   └── hooks/
│       ├── hooks.json               ← PostToolUse 매핑
│       ├── on-agent-complete.sh     ← verbatim prompt/response → agent-transcript.jsonl (R1′ PR #2)
│       └── on-commit.sh             ← 커밋 hash/subject/stat을 impl.log 기록
│   (jira-gateway-mcp 상세: packages/jira-gateway-mcp/go.mod, cmd/server/main.go,
│    internal/{jira,filter,server,types}/ — Phase 2, 43 tests pass, R1′ 변경 없음)
├── bench/                           ← R1′ PR #3 — 3-way 비교 harness (Python)
│   ├── compare.py                   ← A/B/C 결정론적 비교 + report 생성
│   ├── lib/{capture,collect,report,usage}.py
│   ├── manifest.schema.json         ← 실험 manifest 스키마
│   ├── manifests/example.json
│   ├── fixtures/tickets/STABLE-0001.json
│   ├── prices.json                  ← 모델별 토큰 단가
│   └── tests/test_{report,usage}.py
└── docs/
    ├── SETUP.md                     ← R1′ Step 9 재작성: bge-m3 필수, STABLENET_KNOWLEDGE_MCP_BIN/STABLENET_KNOWLEDGE_CONFIG/CHAINBENCH_DIR
    ├── r1-refactor/                 ← R1′ 설계 문서 (다른 세션이 작성)
    │   ├── 00-system-contract.md    ← keystone spec
    │   ├── 01-ckg-refactor.md ~ 05-coding-agent-refactor.md
    │   ├── 06-integration-verification.md  ← 2026-06-04 5-저장소 감사 보고서
    │   ├── 07-domain-knowledge-curation.md ← 7-persona 도메인 큐레이션 plan (P0)
    │   └── plans/                   ← 01~05의 상세 구현 plan
    ├── superpowers/specs/           ← 8개 Phase 설계 문서 (역사 기록 보존)
    └── plan/
        ├── WORK_BREAKDOWN.md
        ├── REVIEW_ISSUES.md         ← 23개 RI (증거 경로 R1′ 적용 후 일부 stale, 작업 별도)
        ├── IMPLEMENTATION_VERIFICATION.md ← 2026-05-31 스냅샷 (R1′가 흡수, Superseded)
        ├── common-tasks.md
        └── phase{1..7}-tasks.md
```

---

## 5. 설계 결정과 Why

새 세션이 임의로 뒤집지 말아야 할 결정들. 각 항목은 *왜* 그렇게 했는지를 기록.

| 결정 | Why | 위치 |
|------|-----|------|
| **Jira Gateway MCP 언어 = Go** | 처음 TypeScript로 시작 → 사용자가 "다른 TS 사용처 없는데 Go로 충분하지 않냐"고 지적. 단일 바이너리, 빠른 시작, geth 생태계 동일 언어 | `packages/jira-gateway-mcp/go.mod` |
| **B+C 하이브리드 아키텍처** | A(B-only)는 LLM 호출 분리 어려움, C(C-only)는 컨텍스트 손실 시 복원 불가. 둘 다 채택 — 상태는 파일, 실행은 에이전트 격리 | `docs/superpowers/specs/2026-05-27-*.md` §2 |
| **Proxy MCP Gateway 패턴** | Sensitive check skill로 처리 시 이미 LLM에 데이터가 도달 → 무용. MCP 서버 내부에서 outbound 전에 filter | `packages/jira-gateway-mcp/internal/filter/` |
| **R1′ Binary = deterministic / Session = LLM** | 외부 백엔드(ckv/ckg/stablenet-knowledge/chainbench) 바이너리에 LLM 호출 0. 모든 LLM 작업은 coding-agent 세션 레이어 | `docs/r1-refactor/00-system-contract.md §2.2` |
| **R1′ stablenet-knowledge가 유일한 agent-facing 검색 MCP** | ckv(의미→키워드) + ckg(키워드→코드)는 stablenet-knowledge가 in-process로 컴포지션. agent는 13개 `cks.context.*`/`cks.ops.*` 도구만 사용. ckv/ckg MCP는 dev-only build tag | `docs/r1-refactor/00-system-contract.md §3 C1` + `scripts/contract/agent-mcp.schema.json` |
| **C1 SSoT JSON Schema + 도구 이름 lint** | 자체 stablenet-knowledge shim의 5 도구 → 외부 stablenet-knowledge의 13 도구로 명명 drift 방지. 모든 agent/command 도구 참조를 schema와 lint script로 결정론적 검증 | `scripts/contract/lint-tool-names.sh` (EXIT 0 = drift 없음) |
| **자체 stablenet-knowledge-mcp shim 폐기** | R1′ Step 6: 자체 in-tree 구현이 외부 stablenet-knowledge와 표면이 불일치. 외부 stablenet-knowledge가 더 풍부한 도메인 시스템을 제공하므로 in-tree 코드 통째 삭제 + `${STABLENET_KNOWLEDGE_MCP_BIN}` 외부 바이너리 위임 | `plugins/stablenet-core-dev/.mcp.json` (`stablenet-knowledge` 항목), `go.work` 멤버 1개 |
| **ADF→Markdown 자체 구현 (Option B)** | Option A(HTML 경유)는 HTML 변환 라이브러리 추가 의존. Option B(ADF 직접 파싱)가 의존성 그래프 가벼움 | `packages/jira-gateway-mcp/internal/jira/adf.go` |
| **transition 3-tier lookup (RI-05)** | Jira workflow의 transition name은 프로젝트별로 다름. name → status name → statusCategory key 순으로 case-insensitive 매칭 → 별도 설정 파일 없이 흡수 | `packages/jira-gateway-mcp/internal/jira/client.go:140 TransitionIssue` |
| **patterns.json 공유 = env 주입** | 빌드 시 embed 또는 symlink는 빌드 의존성 생성. env (`PATTERNS_PATH`) 주입 + 폴백 경로 탐색이 가장 단순 | `plugins/stablenet-core-dev/.mcp.json` env block |
| **bge-m3 (다국어, 1024-dim)** | nomic 모델은 영어 전용. 사용자가 한국어 사용 → 다국어 임베더 필요. 1024-dim은 bge-large와 동일 → 향후 swap 시 스키마 마이그레이션 없음 | `docs/SETUP.md §4.3` + R1′ `02-ckv-refactor.md` |
| **MCP pre-flight 3-layer** (R1′ PR #2) | 단일 SessionStart hook 부재 → 3 위치에서 분담: orchestrator §2.0 (config-level), work.md §5.2 (jira 실패 분기), planner §3.0 (`cks.ops.health`), evaluator §7.0 (chainbench 도구 lint) | `plugins/stablenet-core-dev/agents/{orchestrator,planner,evaluator}.md` |
| **L3 invariant backstop을 skill로** (R1′ Step 4) | Claude Code SessionStart 주입 없음 → planner+evaluator에 grant된 `stablenet-invariants` skill로 ~500토큰 invariant block을 always-on | `plugins/stablenet-core-dev/skills/stablenet-invariants/SKILL.md` |
| **stablenet-context 정적 deprecate** (R1′ Step 3) | 정적 contract 이름(`GovStaking` 등)은 시간에 따라 drift → path→module 분류기로만 축소. 도메인 지식은 stablenet-knowledge 라이브 검색 + `stablenet-invariants` backstop | `plugins/stablenet-core-dev/skills/stablenet-context/SKILL.md` |
| **implementer→evaluator binary handoff (S6)** (R1′ Step 5) | 자체 빌드 시 stale tree 위험. implementer가 `build/bin/gstable` + state.json 기록, evaluator는 commit 일치 시 그것을 사용, 아니면 fallback 빌드 | `plugins/stablenet-core-dev/agents/implementer.md §6.1` + `evaluator.md §7.1` |
| **3-way bench Python harness** (R1′ PR #3) | 결정론적 측정은 Python (Go agent와 분리). 모드 A(stablenet-knowledge)/B(code-only)/C(code+skills) 격리, 모델은 `claude-opus-4-7`로 고정 — 정보 regime만 비교 | `bench/compare.py` + `plugins/stablenet-core-dev/skills/bench-orchestration/SKILL.md` |
| **transcript-grade observability** (R1′ PR #4 of PRs / Step PR #2) | 06 보고서 P4: agent-transcript.jsonl에 verbatim prompt/response + char counts → 토큰/비용 사후 계산 가능. 3-way bench의 substrate | `plugins/stablenet-core-dev/hooks/on-agent-complete.sh` |
| **/merge body 2-tier 전략 (RI-14)** | step ≤10 → 전체 나열 / 11+ → [Interface, Implementation, Tests, Docs, Misc] 5-카테고리 버킷 | `plugins/stablenet-core-dev/commands/merge.md §4.2` |
| **commit 분할 (atomic / reviewable / verifiable)** | Planner가 step을 단일 책임 단위로 쪼개고, Implementer가 step당 1커밋. 리뷰어 시점에서 reasoning 추적 가능 | `plugins/stablenet-core-dev/agents/planner.md §4` + `implementer.md §4` |
| **race detector scope 제한 (RI-21)** | 전체 -race는 시간 폭발. CKG `concurrency_impact`에서 위험 패키지만 race_pkgs로 추출해 그쪽만 실행 | `plugins/stablenet-core-dev/agents/evaluator.md §4.4` |
| **release 변종에서 tag/push는 사용자 확인 게이트** | 자동 태깅·푸시는 되돌리기 어려움. orchestrator에 "Never tag or push tags without user confirmation" 명시 | `plugins/stablenet-core-dev/agents/orchestrator.md §6 safety policies` |

---

## 6. 완료한 작업 (검증된 사실)

### 6.1 Phase 단위 (R1′ 흡수 후, 2026-06-05 보정)

| Phase | 작업 수 | 상태 | 비고 |
|-------|---------|------|------|
| Phase 1 (Skeleton + State Machine) | 10 | ✅ 충실 | R1′ 변경 없음 (state-machine/template-parse 유지) |
| Phase 2 (Jira Gateway MCP) | 7 | ✅ 충실 (43 tests pass) | R1′ 변경 없음. 단 work.md §5.2에 jira 호출 실패 분기 추가 (PR #2) |
| Phase 3·4 (자체 CKV·CKG) | 19 | 🗑️ **삭제** (R1′ Step 6) | `packages/stablenet-knowledge-mcp/` 통째 폐기. 외부 `code-knowledge-system`(stablenet-knowledge)이 ckv+ckg를 in-process로 컴포지션. 우리 Phase 3·4 코드의 격차(F-2/F-3/F-4/F-6/F-8)는 외부 stablenet-knowledge/ckg/ckv 저장소가 흡수 |
| Phase 5 (Agent Pipeline) | 9 | ✅ R1′로 강화 | 도구 이름 C1으로 rename(Step 7), 모델 ID GA(Step 2), implementer→evaluator binary handoff(Step 5), planner §3.0 `cks.ops.health`(PR #2), orchestrator §2.0 pre-flight(PR #2) |
| Phase 6 (Evaluator) | 7 | ✅ R1′로 해소 | `chainbench_init/test_run/report` 이름 수정(Step 8), `.mcp.json` chainbench 등록(Step 6), `summary.failed` 파싱(Step 8). 04 D1 출하 대기 (텍스트 vs JSON 응답) |
| Phase 7 (PR + Review + Merge) | 7 | ✅ 충실 | R1′ 변경 없음 |
| 공통 (4) | 4 | ✅ | R1′ 변경 없음 |
| **R1′ Step 1~9** | 9 | ✅ 완료 (commit `76a285d`) | C1 SSoT 스키마 + lint, 모델 ID, stablenet-context deprecate, L3 invariant skill, binary handoff, stablenet-knowledge shim 삭제, planner rewiring, evaluator rewiring + chainbench 등록, SETUP 재작성 |
| **R1′ 후속 PR #2** (commit `386e1a9`) | — | ✅ | MCP pre-flight (orchestrator §2.0 + work.md §5.2 + planner §3.0) + transcript-grade observability (`on-agent-complete.sh`) |
| **R1′ 후속 PR #3** (commit `725c22e`) | — | ✅ | `/bench` 명령 + `bench/` Python harness + `bench-orchestration` skill + 2개 bench planner agent |
| **R1′ 후속 PR #4** (commit `31e42da`) | — | ✅ | `docs/r1-refactor/07-domain-knowledge-curation.md` plan 추가. 실 entry 작성은 외부 stablenet-knowledge 저장소 소관 (P0) |

### 6.2 Review Issue 감사 (R1′ 흡수 후, 2026-06-05 재평가)

`docs/plan/REVIEW_ISSUES.md`의 23개 RI 중 R1′가 처리한 항목:

| RI | 2026-06-01 상태 | 2026-06-05 실제 상태 | 처리 경로 |
|----|--------------|------------------|---------|
| RI-09 (인덱싱 시간) | PARTIALLY RESOLVED | **외부 ckv로 이관** | 자체 코드 삭제. 외부 `code-knowledge-vector` 02-plan Part D #4가 throughput 후속으로 다룸 |
| RI-10 (AST Tier-1 typed) | PARTIALLY RESOLVED | **외부 ckg로 이관** | 자체 코드 삭제. 외부 `code-knowledge-graph` `statements.go:206`이 이미 `types.Info` 사용 |
| RI-20 (ChainBench) | OPEN | **RESOLVED (구조)** | `.mcp.json`에 chainbench 등록(Step 6), evaluator §7.0 도구 이름 C1 정렬(Step 8). 단 04 D1(`report{format:"json"}` 실 JSON 반환)은 외부 출하 대기 |

증거 경로 갱신 필요 (10개 RI: 01/07/08/09/10/11/15/20/22/23): 본문은 유효하지만 `packages/stablenet-knowledge-mcp/...` 코드 경로가 부재. → 별도 작업으로 분리 (REVIEW_ISSUES.md 갱신).

### 6.3 SETUP.md (R1′ Step 9 재작성)

R1′ 토폴로지(3 서버: jira-gateway in-tree, stablenet-knowledge·chainbench 외부) + bge-m3 필수 + 환경변수(`STABLENET_KNOWLEDGE_MCP_BIN`/`STABLENET_KNOWLEDGE_CONFIG`/`CHAINBENCH_DIR`) 반영.

### 6.4 06 통합 검증 보고서 (commit `feeecc6`)

5 저장소 read-only 감사. 10 case 중 **6 DONE, 3 PARTIAL, 1 MISSING**. 3 격차:
- **P0 도메인 콘텐츠 비어 있음** — 23 entries 0 verified, 마커 0건. 도메인 지식 운영 view가 런타임에 inert (최고 leverage)
- **P2 MCP health 부분적** — chainbench만 pre-flight, `cks.ops.health` 정의되어 있으나 호출 안 됨 → PR #2로 해소
- **P1 3-way 비교 harness 부재** — 단일-모드 eval만 있고 A/B/C 비교 없음 → PR #3로 해소
- **P4 transcript observability** — sub-agent prompt/response verbatim 누락 → PR #2로 해소

### 6.5 R1′ 흡수의 정량적 영향

- **삭제**: `packages/stablenet-knowledge-mcp/` 디렉토리 (15 Go 파일 + go.mod/go.sum/README/.env.example)
- **추가**: `scripts/contract/` (2 파일), `bench/` (15 파일), `plugins/stablenet-core-dev/skills/{stablenet-invariants, bench-orchestration}/`, `plugins/stablenet-core-dev/agents/bench-planner-*` (2), `plugins/stablenet-core-dev/commands/bench.md`, `docs/r1-refactor/` (12 파일)
- **변경**: `plugins/stablenet-core-dev/.mcp.json` (3 서버 등록), `go.work` (멤버 1), `plugins/stablenet-core-dev/agents/{orchestrator,planner,implementer,evaluator}.md` (전면 rewiring), `plugins/stablenet-core-dev/skills/stablenet-context/SKILL.md` (309→93줄), `plugins/stablenet-core-dev/hooks/on-agent-complete.sh`, `plugins/stablenet-core-dev/commands/work.md`, `docs/SETUP.md` (409줄 갱신)
- **lint script EXIT 0**: 45 도구 참조 모두 C1 schema의 26 도구에 일치

---

## 7. 남은 작업 (Roadmap)

분류는 우선순위가 아니라 작업 성격. §7.6에 권장 순서.

### 7.1 F. 코드 격차 수정 — R1′가 흡수 (대부분 종결)

| ID | 원래 작업 | R1′ 처리 | 잔존? |
|----|---------|---------|------|
| F-1 ChainBench 등록 | `.mcp.json` 추가 | ✅ R1′ Step 6/8 — chainbench 등록 + evaluator 도구 이름 C1 | 종결 |
| F-2 CKG calls 타입 기반 | `packages/stablenet-knowledge-mcp` 수정 | ✅ 자체 코드 삭제. 외부 ckg가 이미 typed (`statements.go:206`) | 종결 |
| F-3 CKG channels 페어 | `packages/stablenet-knowledge-mcp` 수정 | ✅ 자체 코드 삭제. 외부 ckg가 이미 producer/consumer | 종결 |
| F-4 CKV 배치 임베딩 | `packages/stablenet-knowledge-mcp` 수정 | ⚠️ 자체 코드 삭제로 우리 저장소 영향 없음. 외부 ckv도 미해결 (02-plan Part D #4) | **외부 ckv 후속** |
| F-5 모델 ID | 4 frontmatter | ✅ R1′ Step 2 — claude-opus-4-7 / claude-sonnet-4-6 | 종결 |
| F-6 CKG incremental | `packages/stablenet-knowledge-mcp` 수정 | ✅ 자체 코드 삭제. 외부 ckg 소관 | 종결 |
| F-7 문서 TS 잔재 정리 | `common-tasks.md`, RI-15/22 | ❌ 미처리 (이 동기화 작업에 포함) | **이 commit에 흡수** |
| F-8 code_snippet/const-var | `packages/stablenet-knowledge-mcp` 수정 | ✅ 자체 코드 삭제. 외부 ckg는 `blobs` 테이블 사용 | 종결 |

### 7.2 P. 06 통합 검증 보고서 잔존 격차 (외부/콘텐츠 의존)

| ID | 작업 | 차단 요인 | 비고 |
|----|------|---------|------|
| **P0** | **도메인 entry 작성·verified 승격** | 외부 `code-knowledge-system` 저장소 + 도메인 전문가 세션 | 23 entry 0 verified → `cks-domain-sync`가 빈 출력. 가장 큰 leverage. 07 plan이 7-persona × 2-tier 전략 제공 |
| P1 | 3-way bench harness 운영 | bge-m3 인덱싱 (~10시간) + 외부 stablenet-knowledge 출하 | ✅ 구조 구현 (R1′ PR #3 — `bench/`, `/bench`, bench-orchestration skill). 실 사용은 외부 환경 의존 |
| P2 | MCP health pre-flight | — | ✅ R1′ PR #2 — orchestrator §2.0 + planner §3.0 + work.md §5.2 |
| P3 | `ops.index --policy-file` + 사용 doc | 외부 `code-knowledge-system` `internal/mcp/ops_index.go` | 외부 작업 — `cks.ops.index` 호출 시 governance 엣지 자동 빌드 안 됨 |
| P4 | transcript observability | — | ✅ R1′ PR #2 — `on-agent-complete.sh`가 agent-transcript.jsonl 기록 |

### 7.3 외부 03/04 출하 의존 (E2E 게이트)

| ID | 차단 요인 | 영향 |
|----|---------|------|
| X-1 | **03: 실 stablenet-knowledge-mcp 바이너리 + `policies/cks.yaml.example`** | `.mcp.json`의 `${STABLENET_KNOWLEDGE_MCP_BIN}`/`${STABLENET_KNOWLEDGE_CONFIG}` resolve, planner의 stablenet-knowledge 도구 13개 호출 |
| X-2 | **04 D1: `chainbench_report{format:"json"}` 실 JSON 반환** | evaluator §7의 `summary.failed` 파싱. 텍스트면 silent mis-parse |
| X-3 | 04: `test:"basic/tx-send"` catalog 존재 | evaluator `:373` 호출 — 부재 시 이름 수정 필요 |

### 7.4 A. 품질 향상 (선택적, R1′ 무관)

| ID | 작업 | 범위 | 차단 요인 |
|----|------|------|---------|
| Q-1 | `workspace-helper` skill 추출 | 현재 `/work`, `/status`, `/review`, `/merge`에 4중 복제된 `.stablenet-expert/tickets/{id}_*` 패턴을 단일 skill로 추출 | 없음. 순수 리팩토링 |
| Q-2 | 에이전트별 통일 로깅 | 현재 evaluator만 `{ws}/logs/eval-*.log` 출력. orchestrator/planner/implementer도 `{ws}/logs/{agent}.log` 패턴 적용 | 없음. SKILL/agent 문서 수정만 |

### 7.5 C. 운영성 / 배포

| ID | 작업 | 범위 | 차단 요인 |
|----|------|------|---------|
| O-1 | `README.md` | 프로젝트 1페이지 요약 (SETUP.md는 절차서) | 없음 |
| O-2 | `LICENSE` | Apache-2.0 또는 MIT 권장 | 사용자 선택 |
| O-3 | GitHub Actions CI | jira-gateway-mcp 빌드+테스트 + `bash scripts/contract/lint-tool-names.sh` + `python -m pytest bench/tests/` | 없음 |
| O-4 | v0.1.0 첫 릴리즈 | jira-gateway 바이너리 Releases 첨부 + plugin 메타 v0.1.0 | O-3 통과 후 |

### 7.6 권장 진행 순서 (2026-06-05 재조정)

이전 "모두 홀드" 지시 잔존 — R1′ 외 작업은 사용자 명시 승인 후에만 진행. 그 가정 위에서:

1. **이 commit: HANDOFF/REVIEW_ISSUES/IMPLEMENTATION_VERIFICATION 동기화 + F-7 흡수** — 현 작업
2. **F-4 외부 ckv 이슈 제기** — 사용자 명시 위임 후. 외부 저장소 GitHub issue
3. **외부 03/04 출하 대기** — 다른 세션 소관
4. **P0 도메인 entry 작성** — 외부 `code-knowledge-system` + 도메인 전문가
5. **(03/04 출하 후) X-1/X-2/X-3 검증** — `.mcp.json` 환경변수 실측 + chainbench D1 응답 형식 확인
6. **E2E 풀 사이클** — `/work` → `/review` → `/merge` + `/bench` 첫 실행
7. **O-3 CI, O-1 README, Q-1/Q-2, O-2/O-4** — R1′ 외 운영성/품질. 사용자 명시 승인 시

---

## 8. 다음 세션 시작 가이드

### 8.1 최소 읽기 순서 (15분 안에 컨텍스트 확보)

1. **이 문서** (HANDOFF.md) — 전체 그림
2. **`docs/r1-refactor/00-system-contract.md`** — R1′ keystone spec. C1~C5 contract, "Binary=deterministic / Session=LLM" 원칙
3. **`docs/r1-refactor/06-integration-verification.md`** — 2026-06-04 5-저장소 감사 보고서. 실 격차의 진실 소스. P0~P4 우선순위 근거
4. **`docs/r1-refactor/07-domain-knowledge-curation.md`** — P0 도메인 콘텐츠 작성 plan (7-persona × 2-tier)
5. **`docs/SETUP.md`** — 실행/빌드/디버깅 방법 (R1′ Step 9 재작성)
6. **`docs/plan/REVIEW_ISSUES.md`** — RI 의사결정 근거 (단, §6.2 표를 먼저 보고 보정된 상태로 해석)
7. **`plugins/stablenet-core-dev/agents/orchestrator.md`** — 상태 전이의 진실 소스 (state machine + R1′ §2.0 pre-flight)
8. **`docs/superpowers/specs/2026-05-27-coding-agent-plugin-design.md`** — 시스템 설계 원본 (역사 기록)

세부 작업 진입 시:
- 에이전트 사양 변경 → `plugins/stablenet-core-dev/agents/*.md` + `docs/r1-refactor/05-coding-agent-refactor.md` + `docs/r1-refactor/plans/05-coding-agent-plan.md`
- jira-gateway 변경 → `packages/jira-gateway-mcp/internal/...`
- C1 도구 이름 변경 → **반드시 `scripts/contract/agent-mcp.schema.json` 먼저 갱신**, 그 후 `bash scripts/contract/lint-tool-names.sh`로 검증
- 새 RI 발견 → `docs/plan/REVIEW_ISSUES.md`에 RI-24+ 형태로 추가
- 외부 stablenet-knowledge/ckg/ckv/chainbench 변경 필요 → 우리 저장소가 아니라 sibling repo 작업

### 8.2 환경 재구축 절차

**`docs/SETUP.md`로 위임** (R1′ Step 9에서 재작성됨). 요점:
1. Prerequisites: Go ≥1.25, Node ≥18, Ollama+`bge-m3`, C 툴체인 (stablenet-knowledge sqlite-vec용), `gh` CLI
2. Clone sibling repos: `code-knowledge-system`, `chainbench`
3. Build: jira-gateway (in-tree), 외부 stablenet-knowledge `bin/stablenet-knowledge-mcp`, 외부 chainbench `mcp-server/dist/index.js`
4. Env: `STABLENET_KNOWLEDGE_MCP_BIN`, `STABLENET_KNOWLEDGE_CONFIG`, `CHAINBENCH_DIR`, `JIRA_*`
5. Plugin install: `claude mcp add` 또는 plugin 자동 발견

### 8.3 새 세션 첫 prompt 예시

> 이 저장소 루트의 `HANDOFF.md`를 먼저 읽고 §7.6 권장 순서대로 진행해줘. 작업 시작 전 §2 사용자 규칙 준수 여부를 확인하고, uncommitted 변경사항이 있으면 커밋 여부를 먼저 물어봐. R1′ 이후 외부 작업(03/04 출하, P0 도메인)이 차단된 상태일 수 있으니 작업 시작 전 사용자에게 진행 가능 여부 확인.

### 8.4 멘탈 모델 점검

새 세션이 다음 질문에 답할 수 있어야 함:
- Q: 왜 agent-facing MCP 서버가 3개인가? (jira-gateway / stablenet-knowledge / chainbench)
  - A: 책임 분리. jira-gateway=inbound 외부 데이터 필터링 (이 저장소 in-tree), stablenet-knowledge=코드 지식 컴포저 (외부, ckv+ckg in-process), chainbench=결정론적 테스트 실행 (외부, TS+Go). C1 SSoT는 `scripts/contract/agent-mcp.schema.json`
- Q: 왜 자체 stablenet-knowledge-mcp 코드를 삭제했나?
  - A: R1′ Step 6. 자체 in-tree 구현이 외부 stablenet-knowledge의 표면(13 dotted tools, in-process ckv+ckg)과 불일치. 외부 stablenet-knowledge가 더 풍부한 도메인 시스템 보유 → in-tree 코드 통째 폐기 + `${STABLENET_KNOWLEDGE_MCP_BIN}` 외부 바이너리 위임
- Q: 왜 LLM이 patterns.json을 직접 안 보는가?
  - A: §3.3 보안 모델. LLM에 도달하기 전에 차단해야 함
- Q: state.json이 손상되면?
  - A: state-machine SKILL.md §2.6 get_resume_point — sub_status(fresh/partial/review_pending) 복구. 아티팩트 파일이 있으면 그쪽이 우선
- Q: stablenet-knowledge가 degraded 모드일 때 어떻게 되나?
  - A: bge-m3/Ollama 미가용 → `cks.ops.health`가 `degraded` 반환 → planner §3.0이 analysis.md에 "DEGRADED" 기록 + 직접 Read 의존. 파이프라인 크래시 없이 계속 (`00 §C2 / §6` Smart Dummy fallback)
- Q: 3-way bench는 무엇을 비교하나?
  - A: 동일 태스크를 A=stablenet-knowledge 검색 / B=code-only(grep/read만) / C=code+comprehension skills 3 정보 regime으로 자율 실행 → `bench/compare.py`가 {정확성, 토큰, 비용, 지연, 안전성} 결정론 비교. 모델은 `claude-opus-4-7`로 고정 — 정보 regime만 격리

---

## 9. 환경 변수 / 외부 의존성

### 9.1 필수 (R1′ 후)

| 변수 | 용도 | 비고 |
|------|------|------|
| `JIRA_BASE_URL` | `https://yourorg.atlassian.net` | jira-gateway-mcp. `--local` 모드 시 생략 가능 |
| `JIRA_API_TOKEN` | Atlassian API token | 절대 커밋 금지 |
| `JIRA_USER_EMAIL` | API 토큰 발급 계정 | |
| `STABLENET_KNOWLEDGE_MCP_BIN` | 외부 stablenet-knowledge-mcp 바이너리 절대 경로 | sibling repo `code-knowledge-system`에서 빌드 |
| `STABLENET_KNOWLEDGE_CONFIG` | 외부 stablenet-knowledge의 `cks.yaml` 절대 경로 | ckv/ckg 데이터 경로, ollama URL, embed model 명시 |
| `CHAINBENCH_DIR` | 외부 chainbench 체크아웃 절대 경로 | `mcp-server/dist/index.js`와 Go wire 바이너리 위치 base |

### 9.2 선택 / 옵션

| 변수 | 효과 |
|------|------|
| `PATTERNS_PATH` | jira-gateway-mcp의 patterns.json override |
| `CUSTOM_PATTERNS_PATH` | 사용자 커스텀 패턴 merge |
| (cks.yaml 내부) Ollama URL/`bge-m3` 모델명 | stablenet-knowledge degraded 모드 분기점 — 부재 시 Smart Dummy 임베더로 폴백, `cks.ops.health`가 `degraded` 보고 |

### 9.3 외부 도구

- `go` ≥1.25 (jira-gateway-mcp + 외부 stablenet-knowledge/ckg/ckv 빌드)
- C 툴체인 (cc/clang) — 외부 stablenet-knowledge의 sqlite-vec CGO
- Node ≥18 + npm — 외부 chainbench MCP server
- `git` ≥2.40
- `gh` CLI ≥2.50 (PR 생성/병합)
- Ollama + `bge-m3` (다국어, 1024-dim) — **stablenet-knowledge 정상 동작 필수** (없으면 degraded)
- Python 3 — `bench/` harness + `lint-tool-names.sh` 호출 시 ad-hoc JSON inspection
- (선택, evaluator stages) `golangci-lint`, `gofmt`, `goimports`, `gosec`

---

## 10. 알려진 위험 / 미실증 가정

새 세션이 의심해야 할 가정들 (2026-06-05 R1′ 후):

1. **ChainBench 도구 호출이 작동한다는 가정**: ⚠️ 구조는 해결(R1′ Step 6/8 — `.mcp.json` 등록 + C1 이름), 단 **04 D1 출하 대기**. `chainbench_report{format:"json"}`이 실 JSON 반환하는지 미검증 → 텍스트면 silent mis-parse (X-2)
2. **외부 stablenet-knowledge 바이너리가 우리 `.mcp.json` 인자(`-config ${STABLENET_KNOWLEDGE_CONFIG}`)와 호환된다는 가정**: ⚠️ 03 출하 대기. 외부 `cmd/cks-mcp/main.go`의 실 flag/env 이름 확인 필요 (X-1)
3. **에이전트 모델 ID가 런타임에 resolve된다는 가정**: ✅ R1′ Step 2 — `claude-opus-4-7` / `claude-sonnet-4-6` 채택. 실 GA alias가 다르면 별도 확인 필요
4. **`bge-m3`가 외부 ckv 임베더로 정확 동작한다는 가정**: ⚠️ Ollama 설치 + `bge-m3` pull 필요. 부재 시 stablenet-knowledge `degraded` 모드 — pipeline 크래시 안 함, 단 retrieval 품질 저하 (`cks.ops.health` 보고)
5. **ADF 변환기가 모든 노드 타입을 커버한다는 가정**: 8+ 노드 타입 테스트했지만 color/inline card/mention/emoji 등 누락 가능. 실 Jira 인스턴스로 검증 필요
6. **bge-m3 풀 인덱싱 시간 (~10시간 추정, 02-plan Part D #4)**: 26K 청크 × 0.74 청크/s. CI 부적합 — overnight run. F-4 (배치 임베딩)은 외부 ckv 후속
7. **도메인 entry가 LLM에 도달한다는 가정**: ❌ 사실이 아님. 23 entries 0 verified → `cks-domain-sync`가 빈 출력. P0 (외부 stablenet-knowledge + 도메인 전문가) 작성 전까지 inert
8. **`test:"basic/tx-send"`가 chainbench catalog에 존재한다는 가정**: ⚠️ 04 출하 시 확인 필요 (X-3)
9. **/merge가 squash로만 동작한다는 가정**: merge commit / rebase 지원 안 함. 사용자 합의 결정 — 뒤집지 말 것
10. **state.json 구조의 후방 호환성**: 스키마 변경 시 마이그레이션 로직 없음. 큰 변경 전 사용자 확인 필요

---

## 11. 메모리 / 히스토리

이 저장소는 사용자의 글로벌 메모리 시스템(`~/.claude/projects/-Users-.../-coding-agent/memory/`)에 다음과 같이 등록되어 있음 (이전 머신 기준):

- `project_coding-agent.md` — go-stablenet 전용 Jira 기반 자동화 플러그인. B+C 하이브리드.
- `user_stablenet-dev.md` — 보안 민감, 설계 우선, 실패 복구 중시, 커밋 분할 선호.
- `feedback_commit-style.md` — English, concise, no co-author attribution.
- `reference_buddy-project.md` — `~/Work/github/study/ai/buddy`의 154 skill 컬렉션. 일부 패턴이 이 프로젝트에 적응됨 (auto-create-pr, finish-development-branch, iterate-fix-verify 등).

새 머신에서는 메모리가 없으므로 이 HANDOFF.md가 그 역할을 대체. 새 세션이 사용자 선호를 학습하면 글로벌 메모리에 동일 항목 저장 권장 (§2 규칙 4·5는 글로벌 CLAUDE.md에도 있어야 안전).

---

## 12. 변경 이력

| 날짜 | 커밋 | 변경 요약 |
|------|------|----------|
| 2026-05-27 | (다수) | Phase 1~7 설계 문서 작성 |
| (이어서) | scaffold + plugin 구조 정립 + packages/ 분리 |
| (이어서) | Phase 1~7 구현 (TypeScript → Go 전환 포함) |
| (이어서) | 통합 검증 + jsonschema 태그 fix |
| 2026-05-29 | `9c68bbf` | SETUP.md + RI-16 RESOLVED |
| 2026-05-29 | `2d9cec6` | 23개 RI 최종 감사 + 모두 RESOLVED 선언 |
| 2026-05-29 | `a8cab77` | HANDOFF.md 초안 작성 |
| 2026-05-31 | `9226b34` | (다른 머신) code-level implementation verification 보고서 추가. Phase 3/4/6 격차 발견 |
| 2026-06-01 | `f0c0f38` | HANDOFF.md §6.1·§6.2·§7.1 F·§7.6·§8·§10 보정. 보고서 발견을 작업 계획에 통합 |
| 2026-06-01 | `4d9335b` | (다른 세션) R1′ system contract (00) + per-project refactor specs (01-05) 작성 |
| 2026-06-02 | `65d6dfc` | (다른 세션) R1′ live-code implementation plans (plans/01-05) 작성 |
| 2026-06-02 | `76a285d` (PR #1) | (다른 세션) R1′ Step 1~9 완료 — C1 SSoT 스키마 + lint, 모델 ID, stablenet-context deprecate, L3 invariant skill, binary handoff, **stablenet-knowledge shim 삭제**, planner/evaluator rewiring, SETUP 재작성 |
| 2026-06-04 | `feeecc6` | (다른 세션) `06-integration-verification.md` 추가 — 5 저장소 read-only 감사. P0~P4 격차 식별 |
| 2026-06-04 | `386e1a9` (PR #2) | (다른 세션) MCP health pre-flight + transcript observability — orchestrator §2.0, planner §3.0, work.md §5.2, `on-agent-complete.sh` verbatim 캡처 |
| 2026-06-04 | `725c22e` (PR #3) | (다른 세션) 3-way bench harness — `bench/` Python, `/bench` 명령, `bench-orchestration` skill, 2 bench planner agents |
| 2026-06-05 | `31e42da` (PR #4) | (다른 세션) `07-domain-knowledge-curation.md` — 7-persona × 2-tier 도메인 큐레이션 plan (P0) |
| 2026-06-05 | (이 커밋) | HANDOFF.md 전면 동기화 — R1′ Step 1~9 + 후속 PR #2/#3/#4 반영, F-7 TS 잔재 흡수, 디렉토리 트리 / 결정 표 / Phase 표 / RI 보정 / §7 F·P·X·A·C·D 재구성 / §8 읽기 순서 / §9 환경 변수 / §10 위험 / §12 이력 |

---

**이 문서가 stale 되면 가장 먼저 update**: §1 마지막 커밋, §6 완료 작업, §7 남은 작업, §12 변경 이력.
