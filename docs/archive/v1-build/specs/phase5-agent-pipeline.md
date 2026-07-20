# Phase 5: Agent Pipeline

> Orchestrator, Planner, Implementer 에이전트의 상세 설계.
> 상태 전이, 에이전트 간 핸드오프, 구현 checkpoint, hook 연동을 구체화한다.

## 1. Agent 간 통신 모델

### 1.1 통신 매체

에이전트 간 통신은 **파일 시스템**(state.json + 아티팩트)을 통해 이루어진다. 직접 메시지 전달은 없다.

```
Orchestrator                 Planner                    Implementer
     │                          │                           │
     │  state.json 업데이트     │                           │
     │  + Planner 디스패치      │                           │
     ├─────────────────────────►│                           │
     │                          │  state.json 읽기          │
     │                          │  → ANALYSIS 시작          │
     │                          │  analysis.md 생성          │
     │                          │  plan.md 생성              │
     │                          │  design-v{N}.md 생성       │
     │                          │  state.json 업데이트       │
     │  Hook: planner 완료     │                           │
     │◄─────────────────────────│                           │
     │                          │                           │
     │  state.json 읽기         │                           │
     │  → READY_FOR_IMPL 확인  │                           │
     │  Implementer 디스패치    │                           │
     ├──────────────────────────┼──────────────────────────►│
     │                          │                           │
     │                          │   state.json 읽기         │
     │                          │   plan.md + design 로드    │
     │                          │   브랜치 생성              │
     │                          │   코드 구현 + 분할 커밋    │
     │                          │   step progress 업데이트   │
     │  Hook: implementer 완료 │                           │
     │◄─────────────────────────┼───────────────────────────│
```

### 1.2 에이전트 디스패치 방법

Claude Code 플러그인에서 에이전트를 디스패치하는 방법:

```
Orchestrator (자체가 에이전트)가 서브 에이전트를 디스패치할 때:
  → Agent tool 사용: subagent_type으로 planner/implementer/evaluator 지정
  → prompt에 workspace_dir 경로와 현재 상태 전달
  → 서브 에이전트는 독립 컨텍스트에서 실행

반환:
  → 서브 에이전트 완료 시 결과 메시지 반환
  → Orchestrator가 결과를 확인하고 다음 상태로 전이
```

---

## 2. Orchestrator Agent 상세

### 2.1 plugin/agents/orchestrator.md

```markdown
---
name: orchestrator
model: opus-4.7
description: |
  파이프라인 상태 머신 컨트롤러. state.json을 읽고
  적절한 에이전트를 디스패치한다.
tools:
  - Agent (planner, implementer, evaluator 디스패치)
  - Read, Write, Edit (state.json 관리)
  - Bash (git 명령)
  - mcp: atlassian (Jira 쓰기: 댓글, 상태)
  - mcp: jira-gateway (Jira 읽기: 티켓, 코멘트)
skills:
  - state-machine
---
```

### 2.2 Orchestrator 동작 로직

```
orchestrator(workspace_dir):

  1. state.json 로드
  2. current_state에 따라 분기:

  ┌─ TICKET_INTAKE ─────────────────────────────────────────┐
  │ ticket.json 존재 확인                                    │
  │ sensitive_check 결과 확인                                │
  │ → CLEAN: state → ANALYSIS, Planner 디스패치             │
  │ → DETECTED/BLOCKED: 유저에게 보고, 중단                 │
  └──────────────────────────────────────────────────────────┘

  ┌─ ANALYSIS / PLANNING / DESIGN ───────────────────────────┐
  │ Planner Agent에게 위임 (내부적으로 3단계 순회)           │
  │ Planner가 모든 단계 완료 후:                             │
  │ → state: READY_FOR_IMPL                                   │
  │ → Orchestrator에 plan.md + design-v{N}.md 위치 보고      │
  └──────────────────────────────────────────────────────────┘

  ┌─ READY_FOR_IMPL ─────────────────────────────────────────┐
  │ plan.md + design-v{final}.md 존재 검증                   │
  │ Implementer Agent 디스패치                                │
  │ → workspace_dir + plan + design 경로 전달                │
  └──────────────────────────────────────────────────────────┘

  ┌─ IMPLEMENTATION (진행 중) ────────────────────────────────┐
  │ Implementer가 처리 중 → 대기                             │
  │ Implementer 완료 시:                                      │
  │ → plan_progress 검증 (all steps completed?)              │
  │ → YES: state → EVALUATION, Evaluator 디스패치            │
  │ → NO: 오류 → 유저에게 보고                               │
  └──────────────────────────────────────────────────────────┘

  ┌─ EVALUATION_PASS ────────────────────────────────────────┐
  │ PR 생성:                                                  │
  │   git push -u origin feature/{TICKET-ID}                 │
  │   gh pr create --title "{TICKET-ID}: {summary}"          │
  │     --body "## Jira\n{ticket_url}\n## Changes\n..."      │
  │                                                           │
  │ Jira 업데이트:                                            │
  │   jira_add_comment(ticket_id, "PR: {pr_url}")            │
  │   jira_update_status(ticket_id, "In Review")             │
  │                                                           │
  │ state → COMPLETION                                        │
  └──────────────────────────────────────────────────────────┘

  ┌─ EVALUATION_FAIL ────────────────────────────────────────┐
  │ failure_log에 실패 상세 기록                              │
  │ cycle_count 확인:                                         │
  │ → < max_eval_cycles: state → ANALYSIS (재진입)           │
  │   → failure 정보를 Planner에게 전달                      │
  │ → >= max_eval_cycles: state → BLOCKED                    │
  │   → 유저에게 보고: "3회 반복 실패. 수동 개입 필요."     │
  │   → failure_summary 출력                                  │
  └──────────────────────────────────────────────────────────┘

  ┌─ BLOCKED ────────────────────────────────────────────────┐
  │ 유저에게 상태 보고:                                       │
  │ - 실패 이력 요약                                          │
  │ - recurring_patterns 분석                                 │
  │ - 권장 조치 사항                                          │
  │ 유저 지시 대기                                            │
  └──────────────────────────────────────────────────────────┘

  ┌─ COMPLETION ─────────────────────────────────────────────┐
  │ 최종 상태. 추가 동작 없음.                               │
  │ /status로 결과 조회 가능.                                 │
  └──────────────────────────────────────────────────────────┘
```

---

## 3. Planner Agent 상세

### 3.1 plugin/agents/planner.md

```markdown
---
name: planner
model: opus-4.7
description: |
  ANALYSIS → PLANNING → DESIGN 3단계를 수행한다.
  코드 분석, 작업 계획 수립, 정밀 설계 문서 작성.
tools:
  - mcp: cks (ckv_search, ckg_query, ckg_impact)
  - mcp: jira-gateway (티켓 재참조)
  - Read, Write, Edit (문서 생성)
  - Bash (git log, git diff 등)
skills:
  - state-machine
  - template-parse
  - stablenet-context
---
```

### 3.2 ANALYSIS 단계 상세

```
analysis(workspace_dir, ticket_json):

  1. 티켓 파싱
     template-parse skill로 티켓 유형/필드 구조화
     → work_type, requirements, scope, acceptance_criteria

  2. 1차 의미 검색 (CKV)
     query = ticket.summary + ticket.description에서 핵심 키워드/문장 추출
     ckv_search(query, top_k=15, filters={package: scope.modules})
     → 관련 코드 후보 15건

  3. 도메인 분류 (Sonnet 검토)
     stablenet-context skill을 활용하여:
     → 어떤 도메인에 해당하는지 분류
        (consensus, core, p2p, rpc, governance, txpool, state, ...)
     → 작업 복잡도 추정 (simple / moderate / complex)

  4. 2차 구조 검색 (CKG)
     CKV 결과에서 핵심 심볼 추출
     ckg_query(symbols, depth=2, include_history=true, include_concurrency=true)
     → 호출 관계, 의존성, 히스토리, 동시성 영향

  5. 영향 범위 분석 (CKG Impact)
     수정 대상 심볼에 대해:
     ckg_impact(symbol, change_type=작업유형에서 추론)
     → 영향 받는 모듈, 리스크 레벨, 필요 테스트 범위

  6. 산출물 생성
     analysis.md:
       - 티켓 요약
       - 도메인 분류
       - 관련 코드 목록 (CKV 결과)
       - 의존성/호출 관계 (CKG 결과)
       - 동시성 영향 분석
       - 히스토리 요약 (과거 이 영역에서 발생한 이슈)
       - 리스크 평가

     related-code.json:
       - CKV 검색 결과 상세
       - CKG 그래프 데이터 (nodes, edges)
       - 영향 범위 데이터

  7. state 전이: ANALYSIS → PLANNING
```

### 3.3 PLANNING 단계 상세

```
planning(workspace_dir, analysis_md, related_code_json):

  1. 분석 결과 기반 작업 분해
     analysis.md를 읽고, 작업을 atomic step으로 분해:
     
     각 step:
       step_id: 순번
       description: 무엇을 수정하는지
       target_files: 수정 대상 파일 목록
       target_symbols: 수정 대상 심볼 목록
       rationale: 왜 이 수정이 필요한지
       dependencies: 이 step이 의존하는 이전 step
       verification: 이 step의 검증 방법 (테스트, 빌드 등)

  2. 우선순위 정렬
     의존성 기반 위상 정렬
     → 선행 조건이 없는 step부터
     → 테스트 관련 step은 구현 step 뒤에

  3. 검증 테스트 정의
     각 step에 대해:
     → 기존 테스트 중 영향 받는 것 목록
     → 새로 작성해야 할 테스트 정의
     → acceptance_criteria에서 유도된 검증 항목

  4. 리스크 체크포인트 정의
     복잡도가 높은 step 이후에 중간 검증 포인트 설정:
     → go build 성공 확인
     → 기존 테스트 regression 없음 확인

  5. 산출물 생성
     plan.md:
       ## 작업 계획
       ### Step 1: {description}
       - 대상: {target_files}
       - 이유: {rationale}
       - 의존: {dependencies}
       - 검증: {verification}
       
       ### Step 2: ...
       
       ## 검증 계획
       - 단위 테스트: {목록}
       - 통합 테스트: {목록}
       - 빌드 검증: go build ./...
       
       ## 리스크
       - {리스크 항목}

  6. state 전이: PLANNING → DESIGN
```

### 3.4 DESIGN 단계 상세

```
design(workspace_dir, plan_md):

  1. plan의 각 step에 대해 정밀 설계
     
     각 step의 설계:
       수정 전 코드 (현재 코드 인용)
       수정 후 코드 (의사 코드 또는 구체적 코드)
       변경 유형: 추가 / 수정 / 삭제 / 리팩토링
       side-effect 체크리스트:
         - [ ] 이 변경이 기존 호출자에 영향을 주는가?
         - [ ] 인터페이스 계약이 변경되는가?
         - [ ] 동시성 안전성이 유지되는가?
         - [ ] 에러 처리 경로가 완전한가?

  2. Self-Review (자체 검토)
     설계 문서를 처음부터 다시 읽으며:
     → 논리적 오류, 누락, 모순 탐색
     → 오류 발견 시:
        design-v{N+1}.md 새 버전 생성
        design-changelog.md에 변경 사유 기록:
          "v1 → v2: Step 3에서 mutex 보호 누락 발견. RLock 추가."

  3. 반복 제어
     revision_count <= max_design_revisions (기본: 3)
     상한 도달 시 → BLOCKED + 유저에게 보고

  4. 최종 설계 확정
     마지막 버전의 design-v{N}.md를 final로 표시
     state.DESIGN.revision = N

  5. state 전이: DESIGN → READY_FOR_IMPL
```

### 3.5 Bug Cycle 재진입 시 Planner 동작

```
EVALUATION_FAIL → ANALYSIS 재진입 시:

  1. 이전 failure_log 로드
     → 어떤 테스트가 왜 실패했는지 파악

  2. 현재 브랜치의 변경사항 수집
     git diff main...HEAD → 지금까지의 모든 변경
     git diff (unstaged) → 아직 커밋 안 된 변경

  3. CKS 검색 + 로컬 diff 종합
     CKS는 push 전 코드를 모르므로:
     → CKS로 원본 코드의 구조 정보 수집
     → 로컬 diff로 현재 변경 상태 파악
     → LLM이 두 정보를 종합하여 분석

  4. 수정 plan 수립
     기존 plan.md는 유지하되, 수정 사항만 추가:
     → plan-fix-{cycle_number}.md 생성
     → 새로운 step 정의 (기존 plan 참조)

  5. 설계 → 구현 → 평가 사이클 재진입
```

---

## 4. Implementer Agent 상세

### 4.1 plugin/agents/implementer.md

```markdown
---
name: implementer
model: sonnet-4.6
description: |
  설계 문서 기반 코드 구현. 분할 커밋 + checkpoint 기반 복구.
tools:
  - Read, Write, Edit (코드 수정)
  - Bash (git, go build, go test 등)
skills:
  - state-machine
---
```

### 4.2 Implementer 동작 로직

```
implementer(workspace_dir):

  1. 초기 설정
     plan.md + design-v{final}.md 로드
     state.json에서 plan_progress 확인
     
     복구 모드 판별:
     → 모든 step이 pending: 새 작업 (브랜치 생성)
     → 일부 completed + in_progress 있음: 복구 (마지막 checkpoint에서 재개)

  2. 브랜치 관리
     새 작업:
       git checkout -b feature/{TICKET-ID}
     복구:
       git checkout feature/{TICKET-ID}
       last_checkpoint 확인 → 재개 지점 결정

  3. Step 순회
     for each step in plan_progress.steps:
       if step.status == "completed": skip
       if step.status == "in_progress" + checkpoint: resume from checkpoint
       
       a. step 시작
          state.json → step.status = "in_progress"
          state.json → step.started_at = now()
       
       b. 코드 수정 수행
          design-v{final}.md의 해당 step 설계를 참조
          → 파일 읽기 → 수정 → 검증(go build)
          
       c. 중간 checkpoint (5분 또는 의미 단위마다)
          state.json → step.last_checkpoint = {
            at: now(),
            work_in_progress: "현재 진행 상황 설명",
            uncommitted_files: [수정 중인 파일 목록]
          }
       
       d. Step 완료
          커밋 메시지: "{TICKET-ID}: {step.description}"
          git add {modified_files}
          git commit -m "{message}"
          
          state.json 업데이트:
            step.status = "completed"
            step.commits = [commit_hash]
            step.completed_at = now()
            step.last_checkpoint = null (삭제)
       
       e. 커밋 크기 검증
          단일 커밋의 변경이 과도한 경우:
          → 파일 수 > 10 또는 diff 줄 > 500 → 분할 경고
          → 가능하면 sub-step으로 분할하여 별도 커밋

  4. 모든 step 완료
     plan_progress 최종 검증:
     → all steps completed + no uncommitted files
     state.json → IMPLEMENTATION 상태 완료 표시
     
  5. 복귀
     Orchestrator에게 완료 알림 (Agent tool 반환)
```

### 4.3 커밋 분할 전략

```
분할 기준:
  1. 한 step = 한 커밋 (기본)
  2. step 내 변경이 큰 경우:
     → 파일 그룹별 분할 (같은 패키지의 파일끼리)
     → 또는 변경 유형별 분할 (인터페이스 추가 / 구현 / 테스트)

커밋 메시지 포맷:
  {TICKET-ID}: {step description}
  
  예:
  STABLE-1234: add GetStakerInfo to GovStaking interface
  STABLE-1234: implement GetStakerInfo in wbft engine
  STABLE-1234: add unit tests for GetStakerInfo
```

### 4.4 빌드 검증

```
각 step 완료 후 (커밋 전):
  go build ./...
  
  빌드 실패 시:
  → 에러 메시지 분석
  → 수정 시도 (최대 3회)
  → 3회 실패 → step을 failed로 표시 + failure_log 기록
  → Orchestrator에게 실패 보고
```

---

## 5. Hook 설계 상세

### 5.1 hooks.json 구현

```jsonc
{
  "hooks": [
    {
      "type": "PostToolUse",
      "toolName": "Agent",
      "description": "서브 에이전트 완료 시 state.json 업데이트",
      "command": "node hooks/on-agent-complete.js \"$TOOL_RESULT\""
    },
    {
      "type": "PostToolUse",
      "toolName": "Bash",
      "pattern": "git commit",
      "description": "커밋 발생 시 impl.log에 기록",
      "command": "node hooks/on-commit.js \"$TOOL_INPUT\""
    }
  ]
}
```

### 5.2 Hook 스크립트

**hooks/on-agent-complete.js**:
```
역할: 서브 에이전트(planner/implementer/evaluator) 완료 시
      state.json을 업데이트하고 다음 단계를 트리거할 정보를 로깅

동작:
  1. Agent tool의 결과에서 에이전트 이름과 상태 추출
  2. state.json에서 해당 에이전트의 완료 상태 반영
  3. logs/에 에이전트 실행 요약 기록
```

**hooks/on-commit.js**:
```
역할: Implementer의 분할 커밋 발생 시 진행 상황 로깅

동작:
  1. 커밋 메시지에서 TICKET-ID 추출
  2. 해당 workspace의 impl.log에 커밋 정보 추가
  3. 타임스탬프 + 커밋 해시 + 변경 파일 수 기록
```

---

## 6. 작업 유형별 파이프라인 분기

### 6.1 Code Review 유형

```
Code Review 티켓은 구현 단계를 건너뛴다:

TICKET_INTAKE → ANALYSIS → PLANNING (리뷰 리포트) → COMPLETION

Planner가 Code Review 모드로 동작:
  → 분석 결과를 리뷰 리포트(review-report.md)로 작성
  → 발견 사항(findings), 개선 제안(suggestions), 리스크 평가
  → plan.md 대신 review-report.md 생성
  → 구현/평가 단계 없이 바로 COMPLETION
  → Jira 댓글에 리뷰 요약 게시
```

### 6.2 Release 유형

```
Release 티켓은 별도 흐름:

TICKET_INTAKE → ANALYSIS (포함 변경사항 확인) → EVALUATION (빌드 + ChainBench) → COMPLETION (태그 + 릴리즈)

Release 전용 단계:
  → ANALYSIS: 포함된 STABLE-xxx 티켓들의 변경 내용 취합
  → EVALUATION: 전체 테스트 + ChainBench 검증
  → COMPLETION:
      git tag v{version}
      git push origin v{version}
      CHANGELOG 업데이트
      Jira 티켓 상태 → Complete
```

---

## 7. 에이전트 컨텍스트 최적화

### 7.1 컨텍스트 크기 관리

각 에이전트가 로드하는 정보량을 최소화한다:

```
Orchestrator:
  - state.json (작음)
  - 필요 시 failure_summary만 (failure_log 전체는 파일 참조)

Planner:
  - ticket.json
  - CKV/CKG 검색 결과 (top_k로 제한)
  - 이전 failure 정보 (재진입 시)

Implementer:
  - plan.md
  - design-v{final}.md (이전 버전은 로드 안 함)
  - 현재 step의 target files만 읽기
  - state.json의 plan_progress만 (전체 state 아님)

Evaluator (Phase 6):
  - test-report 생성에 필요한 결과만
```

### 7.2 대형 파일 처리

go-stablenet의 일부 파일은 수천 줄일 수 있다:

```
전략:
  → Implementer가 파일을 읽을 때, design에 명시된 줄 범위만 읽기
     Read(file, offset=start_line, limit=end_line-start_line)
  → 전체 파일이 필요한 경우: AST 기반으로 관련 함수만 추출
  → CKG의 code_snippet (20줄)으로 미리보기 후, 필요시 전체 로드
```

---

## 8. Phase 5 완료 기준

- [ ] Orchestrator가 state.json 기반으로 올바른 에이전트를 디스패치
- [ ] Planner가 ANALYSIS → PLANNING → DESIGN 3단계를 순차 수행
- [ ] Planner가 CKV + CKG 결과를 기반으로 analysis.md 생성
- [ ] Planner가 plan.md에 atomic step 분해 + 우선순위 정렬
- [ ] Planner가 design-v{N}.md를 self-review하며 반복 개선
- [ ] Implementer가 plan 기반으로 분할 커밋 수행
- [ ] Implementer가 checkpoint를 주기적으로 기록
- [ ] 중단 후 /work 재실행 시 마지막 checkpoint에서 재개
- [ ] Bug cycle 재진입 시 failure 정보 + 로컬 diff를 종합하여 분석
- [ ] Code Review / Release 작업 유형별 파이프라인 분기
- [ ] Hook이 에이전트 완료/커밋 이벤트를 감지하여 로깅
