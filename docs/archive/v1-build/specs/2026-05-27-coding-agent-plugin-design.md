# Coding Agent Plugin - System Design Spec

> go-stablenet 전용 Claude Code 플러그인.
> Jira 티켓 기반으로 코드 분석 → 계획 → 구현 → 검증 → PR 생성까지 자동화.

## 1. 개요

### 1.1 목적

Jira 티켓에 작성된 작업 내용(기능 추가, 버그 수정, 코드 리뷰, 릴리즈 등)을 Claude Code 플러그인이 읽고, 코드 분석 → 계획 수립 → 설계 → 코드 구현 → 테스트 검증 → PR 생성까지의 전체 개발 사이클을 자동화한다.

### 1.2 대상 프로젝트

- **go-stablenet**: geth(go-ethereum) fork 기반 블록체인 클라이언트
- consensus 변경, native coin이 stablecoin, system contract 지원
- 대규모 Go 코드베이스

### 1.3 설계 원칙

- **Document-Driven State Machine + Hook Trigger (B+C 하이브리드)**
  - 상태는 파일 시스템에 persist (state.json + 문서 아티팩트)
  - 에이전트 간 전이는 hook으로 트리거
- **Pre-LLM Security Gate**: 민감정보는 LLM 컨텍스트 도달 전에 차단
- **Checkpoint & Recovery**: 중단 시 마지막 체크포인트에서 재개
- **Fail-Safe**: 3회 반복 실패 시 자동 중단, 사용자 개입 대기

### 1.4 핵심 제약조건

| 제약 | 근거 |
|------|------|
| 민감정보는 tool/MCP 레벨에서 LLM 전에 필터링 | LLM에 전달되는 순간 유출로 간주 |
| 에이전트별 모델 라우팅 (Planner: Opus, Impl/Eval: Sonnet) | 비용 효율 + 추론 품질 균형 |
| 반복 실패 상한 3회 | CLAUDE.md 정책 준수: 무한 재시도 방지 |
| 구현 커밋 분할 | 코드 리뷰 편의 |

---

## 2. 전체 아키텍처

### 2.1 시스템 구성도

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Code Plugin "coding-agent"             │
│                                                                  │
│  Commands          Agents              Skills                    │
│  ─────────         ──────              ──────                    │
│  /work             orchestrator        template-parse            │
│  /review           planner             stablenet-context         │
│  /status           implementer         state-machine             │
│                    evaluator                                     │
│                                                                  │
│  Hooks: on-agent-complete, on-subcommit                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │              State Machine Engine                       │     │
│  │  .coding-agent/tickets/{ID}_{TS}/state.json            │     │
│  └────────────────────────────────────────────────────────┘     │
└──────┬──────────────┬──────────────┬──────────────┬─────────────┘
       │              │              │              │
  ┌────▼─────┐  ┌────▼─────┐  ┌────▼───┐  ┌──────▼──────┐
  │Jira GW   │  │CKS MCP   │  │Claude  │  │ChainBench   │
  │MCP       │  │(새 구축) │  │Models  │  │MCP (기존)   │
  │(프록시)  │  │CKV+CKG   │  │        │  │             │
  │   │      │  │ sensitive │  │        │  │             │
  │   ▼      │  │ filter   │  │        │  │             │
  │Sensitive │  │ 내장     │  │        │  │             │
  │Filter    │  │          │  │        │  │             │
  │   │      │  │          │  │        │  │             │
  │   ▼      │  │          │  │        │  │             │
  │Atlassian │  │          │  │        │  │             │
  │MCP(기존) │  │          │  │        │  │             │
  └──────────┘  └──────────┘  └────────┘  └─────────────┘
```

### 2.2 데이터 흐름 (6단계 상태 전이)

```
TICKET_INTAKE → ANALYSIS → PLANNING → IMPLEMENTATION → EVALUATION → COMPLETION
                    ▲                                       │
                    └───────── (fail/review cycle) ─────────┘
```

| 상태 | 입력 | 처리 | 출력 | 에이전트 | 모델 |
|------|------|------|------|---------|------|
| TICKET_INTAKE | Jira ticket # | Jira GW MCP read → Sensitive Filter | ticket.json | Command | - |
| ANALYSIS | ticket.json | CKS-CKV → Sonnet 검토 → CKS-CKG | analysis.md, related-code.json | Planner | Opus 4.7 |
| PLANNING | analysis 산출물 | Plan 수립 + Design 문서 + 반복 검토 | plan.md, design-v{N}.md | Planner | Opus 4.7 |
| IMPLEMENTATION | plan + design | 브랜치 생성 → 코드 수정 → 분할 커밋 | commits on branch | Implementer | Sonnet 4.6 |
| EVALUATION | impl branch | Unit → Lint → Security → ChainBench | test-report.md | Evaluator | Sonnet 4.6 |
| COMPLETION | eval pass | PR 생성 → Jira 댓글 → Jira 상태 변경 | PR URL | Orchestrator | - |

### 2.3 Pre-LLM Security Gate (Proxy MCP Gateway)

Atlassian MCP로부터의 응답이 LLM에 도달하기 전에, Jira Gateway MCP가 민감정보를 필터링한다.

```
Agent(LLM)
    │ tool call: jira_read_ticket
    ▼
┌──────────────────────┐
│  Jira Gateway MCP    │  ← 프록시 MCP 서버
│                      │
│  1. Atlassian MCP    │──→ Jira API ──→ 원본 응답
│     에게 요청 전달   │
│                      │
│  2. Sensitive Filter │  ← 패턴 매칭 (regex + 엔트로피)
│     (응답 스캔)      │
│                      │
│  3-a. CLEAN → 응답   │──→ Agent에게 전달 (안전)
│  3-b. DETECTED →     │──→ 마스킹 [REDACTED] + 경고
└──────────────────────┘
```

CKS MCP는 자체 구축이므로 내부에 sensitive filter를 기본 포함한다.

---

## 3. Plugin 구조

### 3.1 디렉토리 레이아웃

```
coding-agent/
├── plugin/                          # Claude Code 플러그인 (설치 단위)
│   ├── .claude-plugin/
│   │   └── plugin.json              # 매니페스트
│   ├── commands/
│   │   ├── work.md                  # /coding-agent:work <JIRA-ID>
│   │   ├── review.md                # /coding-agent:review <PR-URL>
│   │   ├── status.md                # /coding-agent:status [JIRA-ID]
│   │   └── merge.md                 # /coding-agent:merge <JIRA-ID>
│   ├── skills/
│   │   ├── state-machine/SKILL.md   # 상태 전이 로직
│   │   ├── template-parse/SKILL.md  # Jira 템플릿 파싱/검증
│   │   └── stablenet-context/SKILL.md # go-stablenet 도메인 지식
│   ├── agents/                      # 에이전트 정의
│   │   ├── orchestrator.md
│   │   ├── planner.md
│   │   ├── implementer.md
│   │   └── evaluator.md
│   ├── hooks/                       # Phase 5에서 구현
│   ├── mcp/                         # MCP 서버 등록 설정
│   └── rules/
├── tools/                           # 빌드 대상 MCP 서버 프로젝트
│   ├── jira-gateway-mcp/            # Phase 2 (TypeScript)
│   └── cks-mcp/                     # Phase 3-4 (Go)
├── shared/                          # 공유 리소스
│   └── patterns.json
└── docs/                            # 설계/계획 문서
```

### 3.2 Commands

**`/work <JIRA-ID>`** (메인 엔트리포인트)

1. Jira Gateway MCP로 티켓 읽기 (sensitive filter 적용)
2. 작업 폴더 생성: `.coding-agent/tickets/{JIRA-ID}_{YYYYMMDD_HHmmss}/`
3. state.json 초기화 (status: TICKET_INTAKE)
4. Orchestrator Agent 디스패치

**`/review <PR-URL>`** (코드 리뷰 피드백 반영)

1. PR 리뷰 코멘트 수집 (gh API)
2. 관련 Jira ticket의 작업 폴더 탐색
3. 리뷰 내용 → 수정 사항 분석
4. ANALYSIS 상태로 재진입 (review cycle)

**`/status [JIRA-ID]`** (작업 상태 조회)

- 현재 상태, 마지막 전이 시각, 생성된 아티팩트 목록
- plan_progress (Implementation 단계일 경우 step별 진행률)
- failure_summary (실패 이력 요약)

### 3.3 Hooks

```jsonc
{
  "hooks": [
    {
      "event": "on-agent-complete",
      "agent": "implementer",
      "action": "trigger-evaluator"
    },
    {
      "event": "on-agent-complete",
      "agent": "evaluator",
      "action": "check-eval-result"
    },
    {
      "event": "on-subcommit",
      "action": "log-progress"
    }
  ]
}
```

---

## 4. Agent 파이프라인

### 4.1 Orchestrator Agent

상태 머신 컨트롤러. state.json을 읽고 현재 상태에 따라 적절한 서브 에이전트를 디스패치한다.

```
동작:
1. state.json 읽기 → 현재 상태 확인
2. 상태별 분기:
   TICKET_INTAKE  → ticket.json 확인 → ANALYSIS 전이 → Planner 디스패치
   ANALYSIS~DESIGN → Planner가 내부 처리
   READY_FOR_IMPL → Implementer 디스패치
   EVAL PASS      → PR 생성 + Jira 업데이트 (COMPLETION)
   EVAL FAIL      → cycle count 확인 → ANALYSIS 재진입 또는 BLOCKED
   BLOCKED        → 유저에게 보고, 지시 대기
```

### 4.2 Planner Agent (모델: Opus 4.7)

ANALYSIS → PLANNING → DESIGN을 담당. 가장 높은 추론 품질 요구.

```
[ANALYSIS]
1. ticket.json 로드
2. CKS MCP - ckv_search: 티켓 내용으로 의미 검색 → 관련 코드 후보
3. Sonnet 모델로 2차 검토: 도메인 분류 + 작업 유형 결정
4. CKS MCP - ckg_query: 관련 심볼로 코드 관계 탐색
   → 의존성, 호출 관계, 동시성 영향, 수정 히스토리
5. 산출물: analysis.md, related-code.json

[PLANNING]
6. 작업 단계 수립 (각 단계: 수정 대상, 이유, 예상 영향)
7. 단계별 검증 테스트 정의
8. 우선순위 정렬
9. 산출물: plan.md

[DESIGN]
10. 정밀 코드 구현 설계 (수정 전/후 의사 코드, side-effect 체크리스트)
11. Self-review → 오류 시 design-v{N+1}.md + changelog 기록
12. 반복 (상한: 3회)
13. 산출물: design-v{N}.md (final), design-changelog.md
```

### 4.3 Implementer Agent (모델: Sonnet 4.6)

설계 문서 기반 코드 구현. Checkpoint 기반 복구 지원.

```
1. plan.md + design-v{final}.md 로드
2. 작업 브랜치 생성: feature/{TICKET-ID}
3. plan의 각 step 순회:
   a. state.json → step.status = "in_progress"
   b. 코드 수정 수행
   c. 주기적 checkpoint 기록 (last_checkpoint)
   d. 완료 시 분할 커밋 + step.status = "completed"
4. 모든 step completed → state 전이
5. Hook → Orchestrator에 완료 알림
```

복구: /work 재실행 시 첫 번째 non-completed step의 last_checkpoint에서 재개.

### 4.4 Evaluator Agent (모델: Sonnet 4.6)

구현 코드의 품질/정확성 검증 파이프라인.

```
순차 실행:
1. Unit Test:     go test ./... -v -count=1
2. Lint & Format: golangci-lint run + gofmt -d .
3. Security Scan: go vet + 보안 패턴 체크
4. ChainBench:    MCP 호출 → 로컬 네트워크 구성 → 블록 생성 확인 → tx 테스트

결과 종합 → test-report.md
ALL PASS → EVALUATION_PASS
ANY FAIL → EVALUATION_FAIL (failure_log에 상세 기록)
```

### 4.5 Bug/Review Cycle

```
EVALUATION_FAIL 또는 PR Review 피드백 발생 시:

1. 이슈 내용 + 현재 브랜치 diff 수집 (git diff)
   - CKS에 push 안 된 코드는 미반영 → git diff로 직접 읽기
2. CKS로 관련 원본 코드 정보 수집
3. [unpushed 변경 + 원본 코드 + 이슈]를 종합하여 Claude 모델로 추론
4. 수정 plan → design → impl → eval 사이클 재진입
5. 동일 작업 폴더에 기록 유지
```

---

## 5. CKS MCP (Code Knowledge Search)

### 5.1 아키텍처

```
┌─────────────────────────────────────────────┐
│                  CKS MCP Server              │
│                                              │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │   CKV Engine    │  │   CKG Engine     │  │
│  │ (Vector Search) │  │ (Graph Search)   │  │
│  │                 │  │                  │  │
│  │ Embedding Model │  │ AST Parser       │  │
│  │ Vector Store    │  │ Relation Extract │  │
│  │ Code Chunker    │  │ Graph Store      │  │
│  │ Reranker        │  │ Traversal Query  │  │
│  └────────┬────────┘  └────────┬─────────┘  │
│           │                    │             │
│  ┌────────▼────────────────────▼─────────┐  │
│  │          Indexing Pipeline             │  │
│  │  Git history → AST parse → Embed      │  │
│  │  → Store vectors + Build graph         │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  ┌───────────────────────────────────────┐  │
│  │        Sensitive Filter (내장)         │  │
│  └───────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 5.2 CKV (Code Knowledge Vector)

의미 기반 검색. Jira 티켓의 자연어 설명으로 관련 코드를 찾는다.

- **Code Chunker**: Go AST 기반, 함수/메서드/구조체 단위 분할
- **Embedding Model**: 코드 특화 임베딩 (CodeBERT, StarCoder 등)
- **Vector Store**: 로컬 우선 (SQLite+vector, ChromaDB, Qdrant 등)
- **Reranker**: Cross-encoder로 초기 결과 재순위화

```
MCP Tool:
ckv_search(query: string, top_k: int, filters?: {package, file_pattern})
→ [{file, function, snippet, score, git_history_summary}]
```

### 5.3 CKG (Code Knowledge Graph)

구조 기반 검색. 코드의 의존성, 호출 관계, 동시성 영향 범위 파악.

- **AST Parser**: 함수 호출, 타입 참조, 인터페이스 구현 관계 추출
- **Git History Analyzer**: 함수/파일별 변경 히스토리, 커밋 메시지 수집
- **Concurrency Analyzer**: goroutine, channel, mutex, sync 패턴 분석
- **Graph Store**: 로컬 그래프 DB 또는 in-memory graph

```
MCP Tool:
ckg_query(symbols: string[], depth: int, include_history: bool, include_concurrency: bool)
→ {
    nodes: [{symbol, file, type, code_snippet}],
    edges: [{from, to, relation_type}],
    history: [{symbol, commits: [{hash, message, date, diff_summary}]}],
    concurrency_impact: [{symbol, goroutine_context, shared_resources, sync_mechanisms}]
  }
```

### 5.4 인덱싱 전략

- **Full Index**: 최초 1회. 전체 .go 파일 AST parse → 그래프 구축 + 임베딩 생성
- **Incremental Index**: git diff 기반. 변경 파일만 re-parse → 그래프/벡터 업데이트

---

## 6. Sensitive Check (민감정보 필터)

### 6.1 위치

- **Jira Gateway MCP** 내장: Atlassian MCP 응답을 필터링
- **CKS MCP** 내장: 코드 검색 응답을 필터링
- 두 곳 모두 동일한 패턴 정의(patterns.json)를 공유

### 6.2 탐지 패턴

```jsonc
{
  "patterns": [
    { "id": "private_key", "regex": "-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----", "severity": "critical" },
    { "id": "aws_access_key", "regex": "AKIA[0-9A-Z]{16}", "severity": "critical" },
    { "id": "openai_key", "regex": "sk-[a-zA-Z0-9_-]{20,}", "severity": "critical" },
    { "id": "jwt_token", "regex": "eyJ[A-Za-z0-9_-]+\\.eyJ[A-Za-z0-9_-]+", "severity": "high" },
    { "id": "db_url", "regex": "(postgres|mongodb)(\\+srv)?://[^:]+:[^@]+@", "severity": "critical" },
    { "id": "webhook_secret", "regex": "(X-Hub-Signature|stripe_webhook_secret)", "severity": "high" },
    { "id": "high_entropy", "type": "entropy", "threshold": 4.5, "min_length": 20, "severity": "warning" }
  ]
}
```

### 6.3 동작

- **CLEAN**: 패턴 미탐지 → sanitized 데이터를 LLM에 전달
- **DETECTED**: 패턴 탐지 → 해당 부분 `[REDACTED]`로 마스킹 후 전달 + 유저에게 경고
- **CRITICAL**: critical severity 탐지 → 파이프라인 중단 + 유저에게 상세 알림

---

## 7. Jira 티켓 템플릿

### 7.1 Feature Add

```markdown
## 작업 유형: Feature
## 요약
[한 줄 요약]
## 배경
[왜 이 기능이 필요한지]
## 요구사항
- [ ] [구체적 요구사항]
## 영향 범위
- 모듈: [consensus / core / p2p / rpc / ...]
- 예상 변경 파일: [알고 있다면]
## 수용 기준 (Acceptance Criteria)
- [ ] [테스트로 검증 가능한 기준]
## 참고 자료
[관련 문서, 이전 티켓]
```

### 7.2 Bug Fix

```markdown
## 작업 유형: Bug Fix
## 요약
[한 줄 요약]
## 재현 방법
1. [단계]
## 기대 동작
[정상 동작]
## 실제 동작
[현재 동작]
## 영향 범위
- 모듈: [consensus / core / p2p / rpc / ...]
- 심각도: [critical / high / medium / low]
## 수용 기준
- [ ] [버그 수정 검증 기준]
```

### 7.3 Code Review

```markdown
## 작업 유형: Code Review
## 요약
[리뷰 대상 및 목적]
## 리뷰 대상
- 파일/모듈: [대상]
- 관점: [성능 / 보안 / 아키텍처 / 정확성]
## 리뷰 기준
- [ ] [구체적 확인 사항]
```

### 7.4 Release

```markdown
## 작업 유형: Release
## 버전
[v1.2.3]
## 포함 변경사항
- [STABLE-xxx: 요약]
## 릴리즈 체크리스트
- [ ] 모든 테스트 통과
- [ ] ChainBench 통합 테스트 통과
- [ ] CHANGELOG 업데이트
- [ ] 태그 생성
```

**작업 유형별 파이프라인 분기**:
- Feature / Bug Fix: 전체 6단계
- Code Review: ANALYSIS → PLANNING (리뷰 리포트 생성) → COMPLETION (구현 단계 생략)
- Release: 별도 릴리즈 플로우 (빌드 → ChainBench → 태깅)

---

## 8. State Machine 상세

### 8.1 state.json 전체 스키마

```jsonc
{
  "ticket_id": "STABLE-1234",
  "created_at": "2026-05-27T00:00:00Z",
  "workspace_dir": ".coding-agent/tickets/STABLE-1234_20260527_000000",
  "ticket_type": "feature",
  
  "current_state": "IMPLEMENTATION",
  "current_agent": "implementer",
  
  "states": {
    "TICKET_INTAKE": {
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "artifacts": ["ticket.json"],
      "sensitive_check": { "result": "CLEAN", "scanned_at": "..." }
    },
    "ANALYSIS": {
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "artifacts": ["analysis.md", "related-code.json"],
      "model": "opus-4.7"
    },
    "PLANNING": {
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "artifacts": ["plan.md"]
    },
    "DESIGN": {
      "status": "completed",
      "revision": 2,
      "artifacts": ["design-v1.md", "design-v2.md", "design-changelog.md"]
    },
    "IMPLEMENTATION": {
      "status": "in_progress",
      "branch": "feature/STABLE-1234",
      "started_at": "...",
      "plan_progress": {
        "total_steps": 5,
        "steps": [
          {
            "step_id": 1,
            "description": "인터페이스 추가",
            "status": "completed",
            "commits": ["a1b2c3d"],
            "started_at": "...",
            "completed_at": "..."
          },
          {
            "step_id": 2,
            "description": "로직 구현",
            "status": "in_progress",
            "commits": [],
            "started_at": "...",
            "completed_at": null,
            "last_checkpoint": {
              "at": "...",
              "reason": "token_limit",
              "work_in_progress": "함수 구현 70% 완료. edge case 처리 남음",
              "uncommitted_files": ["consensus/wbft/finalize.go"]
            }
          },
          { "step_id": 3, "description": "테스트 추가", "status": "pending", "commits": [] },
          { "step_id": 4, "description": "통합 테스트 수정", "status": "pending", "commits": [] },
          { "step_id": 5, "description": "문서 업데이트", "status": "pending", "commits": [] }
        ]
      },
      "commits": [
        { "hash": "a1b2c3d", "message": "...", "step_id": 1, "at": "..." }
      ]
    },
    "EVALUATION": {
      "status": "pending",
      "results": {
        "unit_test": null,
        "lint": null,
        "security": null,
        "chainbench": null
      }
    },
    "COMPLETION": {
      "status": "pending",
      "pr_url": null
    }
  },
  
  "failure_log": [
    {
      "id": "fail-001",
      "occurred_at": "...",
      "state": "EVALUATION",
      "agent": "evaluator",
      "step": "unit_test",
      "attempted_action": {
        "description": "수정된 Finalize 함수에 대한 unit test 실행",
        "command": "go test ./consensus/wbft/... -v -count=1",
        "related_plan_step": "plan.md#step-3",
        "related_design": "design-v2.md#section-2.1",
        "modified_files": ["consensus/wbft/finalize.go"]
      },
      "expected_outcome": "TestFinalize_StableCoinTransfer PASS",
      "actual_outcome": {
        "type": "test_failure",
        "summary": "panic: nil pointer dereference",
        "details": "goroutine 1 [running]: ...",
        "exit_code": 2,
        "log_file": "logs/eval-fail-001.log"
      },
      "agent_analysis": {
        "root_cause_hypothesis": "GovStaking 주소 nil 상태에서 Finalize 호출",
        "confidence": "mid",
        "suggested_fix": "InjectContracts에서 초기화 순서 보장"
      },
      "resolution": {
        "action": "retry_cycle",
        "transitioned_to": "ANALYSIS",
        "retry_count": 1
      }
    }
  ],
  
  "failure_summary": {
    "total_failures": 1,
    "by_state": { "EVALUATION": 1 },
    "by_type": { "test_failure": 1 },
    "recurring_patterns": []
  },
  
  "config": {
    "max_design_revisions": 3,
    "max_eval_cycles": 3,
    "impl_model": "sonnet-4.6",
    "planning_model": "opus-4.7"
  }
}
```

### 8.2 상태 전이 규칙

```
TICKET_INTAKE → ANALYSIS
  조건: ticket.json 존재 + sensitive_check.result == "CLEAN"

ANALYSIS → PLANNING
  조건: analysis.md + related-code.json 존재

PLANNING → DESIGN
  조건: plan.md 존재

DESIGN → IMPLEMENTATION
  조건: design-v{N}.md (final) 존재 + revision ≤ max_design_revisions

IMPLEMENTATION → EVALUATION
  조건 (모두 충족):
  - plan_progress.steps 전체가 "completed"
  - uncommitted_files가 없음
  - total completed steps == total_steps

EVALUATION → COMPLETION
  조건: 모든 test result == PASS

EVALUATION → ANALYSIS (fail cycle)
  조건: 하나 이상 FAIL + cycles < max_eval_cycles

EVALUATION → BLOCKED
  조건: cycles >= max_eval_cycles → 유저 보고, 수동 개입 대기

IMPLEMENTATION 복구 (중단 후 재시작):
  1. state.json → current_state: IMPLEMENTATION 확인
  2. 첫 번째 non-completed step 탐색
  3. last_checkpoint 존재 시 → 해당 지점부터 재개
  4. last_checkpoint 없이 in_progress → commit 유무 확인 후 판단
```

### 8.3 아티팩트 폴더 구조

```
.coding-agent/
└── tickets/
    └── STABLE-1234_20260527_000000/
        ├── state.json
        ├── ticket.json
        ├── analysis.md
        ├── related-code.json
        ├── plan.md
        ├── design-v1.md
        ├── design-v2.md
        ├── design-changelog.md
        ├── test-report.md
        └── logs/
            ├── analysis.log
            ├── planning.log
            ├── impl.log
            ├── eval.log
            └── eval-fail-001.log
```

### 8.4 Safeguards

| Safeguard | 조건 | 동작 |
|-----------|------|------|
| 무한 루프 방지 | eval fail-retry 3회 | BLOCKED 상태, 유저 보고 |
| 설계 수정 상한 | self-review 수정 3회 | BLOCKED 상태, 유저 판단 요청 |
| ChainBench 타임아웃 | 블록 생성 미시작 (시간제한) | FAIL + 네트워크 리소스 정리 |
| 브랜치 보호 | main/master 직접 커밋 | 강제 차단, feature/{ID} 브랜치만 허용 |
| 커밋 크기 제한 | diff 줄 수/파일 수 상한 | 분할 커밋 강제 |

---

## 9. 서브시스템 분해 (구현 순서)

전체 시스템을 아래 순서로 분해하여 순차 구현한다.

### Phase 1: Plugin Skeleton + State Machine
- plugin/.claude-plugin/plugin.json, commands, agents, skills 기본 구조
- state.json 관리 로직
- 아티팩트 폴더 생성/관리
- /status 커맨드

### Phase 2: Jira Gateway MCP + Sensitive Filter
- Proxy MCP 서버 구축
- Sensitive Check 패턴 매칭 엔진
- patterns.json
- Atlassian MCP 연동

### Phase 3: CKS MCP (CKV)
- Go AST 기반 Code Chunker
- Embedding + Vector Store
- Reranker
- ckv_search MCP tool

### Phase 4: CKS MCP (CKG)
- AST 기반 관계 추출
- Git History Analyzer
- Concurrency Analyzer
- Graph Store
- ckg_query MCP tool

### Phase 5: Agent Pipeline
- Orchestrator 상태 전이 로직
- Planner Agent (ANALYSIS → DESIGN)
- Implementer Agent (checkpoint, 분할 커밋)
- Hook 연동

### Phase 6: Evaluator + ChainBench 연동
- Evaluator Agent
- ChainBench MCP 연동
- test-report 생성
- Fail cycle 로직

### Phase 7: PR + Review Cycle
- PR 생성 자동화
- /review 커맨드
- Jira 상태 업데이트
- 리뷰 피드백 → 재작업 사이클

---

## 10. 미결정 사항 (구현 시 결정)

| 항목 | 후보 | 결정 시점 |
|------|------|----------|
| CKV Vector Store | SQLite+vector, ChromaDB, Qdrant | Phase 3 |
| CKV Embedding Model | CodeBERT, StarCoder, Claude 기반 | Phase 3 |
| CKG Graph Store | embedded Neo4j, SQLite adjacency, in-memory | Phase 4 |
| Jira GW MCP 구현 언어 | TypeScript, Python, Go | Phase 2 |
| CKS MCP 구현 언어 | Go (go-stablenet과 동일 생태계) | Phase 3 |
| 커밋 크기 상한 구체적 수치 | 파일 수 N개 또는 diff M줄 | Phase 5 |
| ChainBench 타임아웃 구체적 수치 | 분 단위 | Phase 6 |
