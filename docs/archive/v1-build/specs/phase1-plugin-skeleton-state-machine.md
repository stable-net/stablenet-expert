# Phase 1: Plugin Skeleton + State Machine

> coding-agent 플러그인의 기본 골격과 상태 머신 엔진.
> 이 Phase가 완료되면 /work, /review, /status 커맨드가 인식되고,
> 작업 폴더 생성 + state.json 관리가 동작한다.

## 1. Plugin Manifest

### 1.1 plugin/.claude-plugin/plugin.json

Claude Code는 `.claude-plugin/plugin.json`에서 매니페스트를 탐색하고,
`commands/`, `skills/`, `agents/` 디렉토리를 자동 검색(auto-discovery)한다.

```jsonc
{
  "name": "coding-agent",
  "version": "0.1.0",
  "description": "go-stablenet Jira-driven automated development pipeline",
  "author": {
    "name": "mhha"
  },
  "license": "Apache-2.0"
}
```

### 1.2 디렉토리 구조

```
coding-agent/
├── plugin/                              # Claude Code 플러그인 (설치 단위)
│   ├── .claude-plugin/
│   │   └── plugin.json                  # 매니페스트
│   ├── commands/
│   │   ├── work.md                      # frontmatter: description + argument-hint
│   │   ├── review.md
│   │   ├── status.md
│   │   └── merge.md
│   ├── skills/
│   │   ├── state-machine/SKILL.md       # 디렉토리 구조, SKILL.md가 진입점
│   │   ├── template-parse/SKILL.md
│   │   └── stablenet-context/SKILL.md
│   ├── agents/
│   │   ├── orchestrator.md
│   │   ├── planner.md
│   │   ├── implementer.md
│   │   └── evaluator.md
│   ├── hooks/                           # Phase 5에서 구현
│   ├── mcp/                             # MCP 서버 등록 설정
│   └── rules/
├── tools/                               # 빌드 대상 MCP 서버 프로젝트
│   ├── jira-gateway-mcp/                # Phase 2 (TypeScript)
│   └── cks-mcp/                         # Phase 3-4 (Go)
├── shared/
│   └── patterns.json
└── docs/
    └── superpowers/
        └── specs/
            └── (설계 문서들)
```

---

## 2. Command 상세 설계

### 2.1 /work Command

**파일**: `plugin/commands/work.md`

**시그니처**: `/coding-agent:work <JIRA-ID>`

**동작 흐름**:

```
1. 인자 검증
   - JIRA-ID 형식 검증: /^[A-Z]+-\d+$/ (예: STABLE-1234)
   - 형식 불일치 → 에러 메시지 + 사용법 안내

2. 중복 작업 체크
   - .coding-agent/tickets/ 하위에서 동일 JIRA-ID로 시작하는
     BLOCKED/in_progress 상태의 폴더가 있는지 확인
   - 존재 시:
     a. 상태가 BLOCKED → "이전 작업이 BLOCKED 상태입니다. 재개하시겠습니까?" 확인
     b. 상태가 in_progress → "진행 중인 작업이 있습니다. 재개합니다." + 해당 폴더에서 복구
     c. 상태가 completed → 새 작업 폴더 생성 (동일 티켓 재작업 가능)

3. 작업 폴더 생성
   - 경로: .coding-agent/tickets/{JIRA-ID}_{YYYYMMDD_HHmmss}/
   - 하위 logs/ 디렉토리 생성

4. state.json 초기화
   - current_state: "TICKET_INTAKE"
   - 모든 states를 pending으로 초기화
   - config 기본값 설정

5. Orchestrator Agent 디스패치
   - workspace_dir 경로를 인자로 전달
   - 에이전트가 TICKET_INTAKE부터 시작
```

**에러 처리**:
- JIRA-ID 미입력 → 사용법 출력
- .coding-agent/ 디렉토리 미존재 → 자동 생성
- 권한 오류 → 에러 메시지

### 2.2 /review Command

**파일**: `plugin/commands/review.md`

**시그니처**: `/coding-agent:review <PR-URL>`

**동작 흐름**:

```
1. 인자 검증
   - PR URL 형식: https://github.com/{owner}/{repo}/pull/{number}
   - 또는 단축형: #{number} (현재 레포 기준)

2. PR 정보 수집
   - gh pr view {number} --json title,body,reviews,comments
   - 리뷰 코멘트 중 "changes requested" 또는 구체적 수정 요청 추출

3. 관련 Jira 티켓 탐색
   - PR 브랜치명에서 JIRA-ID 추출: feature/STABLE-1234 → STABLE-1234
   - 또는 PR body에서 JIRA-ID 패턴 검색
   - .coding-agent/tickets/에서 해당 티켓의 가장 최근 작업 폴더 탐색

4. 리뷰 내용을 작업 폴더에 기록
   - review-feedback-{N}.md 생성
   - 코멘트별로 파일 경로, 라인 번호, 내용 구조화

5. 상태 전이
   - state.json의 current_state → ANALYSIS (review cycle)
   - failure_log에 리뷰 사이클 기록
   - Orchestrator Agent 디스패치 (리뷰 피드백 기반 재작업)
```

**에러 처리**:
- PR URL에서 JIRA-ID를 추출할 수 없는 경우 → 유저에게 JIRA-ID 입력 요청
- 해당 티켓의 작업 폴더가 없는 경우 → 새 작업 폴더 생성 후 진행

### 2.3 /status Command

**파일**: `plugin/commands/status.md`

**시그니처**: `/coding-agent:status [JIRA-ID]`

**동작 흐름**:

```
1. JIRA-ID 지정된 경우
   - .coding-agent/tickets/에서 해당 티켓의 모든 작업 폴더 탐색
   - 가장 최근 폴더의 state.json 로드
   - 상태 정보 출력

2. JIRA-ID 미지정 경우
   - .coding-agent/tickets/ 하위 모든 폴더 스캔
   - in_progress 또는 BLOCKED 상태인 작업 목록 출력

3. 출력 포맷
   ┌─ STABLE-1234 ─────────────────────────────┐
   │ 상태: IMPLEMENTATION (step 2/5)            │
   │ 브랜치: feature/STABLE-1234                │
   │ 시작: 2026-05-27 00:00                     │
   │ 마지막 활동: 2026-05-27 01:30              │
   │ 실패 이력: 1건 (unit_test)                 │
   │ 아티팩트: ticket.json, analysis.md,         │
   │          plan.md, design-v2.md              │
   │                                             │
   │ [Step 1] ✓ 인터페이스 추가                  │
   │ [Step 2] ◐ 로직 구현 (checkpoint: 70%)     │
   │ [Step 3] ○ 테스트 추가                      │
   │ [Step 4] ○ 통합 테스트 수정                 │
   │ [Step 5] ○ 문서 업데이트                    │
   └─────────────────────────────────────────────┘
```

---

## 3. State Machine Engine

### 3.1 Skills: state-machine.md

state-machine skill은 state.json의 CRUD와 상태 전이 로직을 제공한다.
Agent들이 이 skill을 호출하여 상태를 관리한다.

**제공 기능**:

```
1. init_state(ticket_id, ticket_type, workspace_dir)
   → state.json 생성 + 초기화

2. get_current_state(workspace_dir)
   → 현재 상태, 에이전트, 진행률 반환

3. transition(workspace_dir, from_state, to_state, artifacts?)
   → 전이 조건 검증 → 성공 시 state 업데이트
   → 조건 미충족 시 에러 (어떤 조건이 미충족인지 명시)

4. update_step_progress(workspace_dir, step_id, status, checkpoint?)
   → IMPLEMENTATION 단계의 step 진행 상태 업데이트

5. log_failure(workspace_dir, failure_entry)
   → failure_log에 실패 기록 추가
   → failure_summary 자동 업데이트 (by_state, by_type, recurring_patterns)

6. get_resume_point(workspace_dir)
   → 중단된 작업의 재개 지점 반환
   → (current_state, last_step, last_checkpoint)
```

### 3.2 전이 조건 검증 로직

```
validate_transition(from, to, workspace_dir):

  TICKET_INTAKE → ANALYSIS:
    assert file_exists(workspace_dir/ticket.json)
    assert state.sensitive_check.result == "CLEAN"

  ANALYSIS → PLANNING:
    assert file_exists(workspace_dir/analysis.md)
    assert file_exists(workspace_dir/related-code.json)

  PLANNING → DESIGN:
    assert file_exists(workspace_dir/plan.md)

  DESIGN → IMPLEMENTATION:
    assert glob(workspace_dir/design-v*.md).length > 0
    assert state.DESIGN.revision <= config.max_design_revisions

  IMPLEMENTATION → EVALUATION:
    assert all(step.status == "completed" for step in plan_progress.steps)
    assert no step has uncommitted_files
    assert plan_progress.completed == plan_progress.total_steps

  EVALUATION → COMPLETION:
    assert all(result == "PASS" for result in eval.results.values())

  EVALUATION → ANALYSIS (fail cycle):
    assert any(result == "FAIL" for result in eval.results.values())
    assert len(failure_log.filter(type="retry_cycle")) < config.max_eval_cycles

  * → BLOCKED:
    assert cycle_count >= config.max_eval_cycles
    OR design_revision >= config.max_design_revisions
```

### 3.3 failure_summary 자동 업데이트 로직

```
on log_failure(entry):

  1. failure_log.append(entry)
  2. failure_summary.total_failures += 1
  3. failure_summary.by_state[entry.state] += 1
  4. failure_summary.by_type[entry.actual_outcome.type] += 1
  
  5. recurring_patterns 갱신:
     - entry.actual_outcome.summary에서 핵심 키워드 추출
       (예: "nil pointer in consensus/wbft" → key: "nil_pointer:consensus/wbft")
     - 기존 patterns에서 동일 key 검색
     - 존재 → occurrences += 1, failure_ids에 추가
     - 미존재 + 유사 패턴 2건 이상 → 새 pattern 생성
```

---

## 4. 아티팩트 폴더 관리

### 4.1 폴더 생성 규칙

```
기본 경로: {project_root}/.coding-agent/tickets/

폴더명: {JIRA-ID}_{YYYYMMDD_HHmmss}
  - JIRA-ID: 대문자 + 하이픈 + 숫자 (예: STABLE-1234)
  - Timestamp: UTC 기준, 초 단위

예시:
  .coding-agent/tickets/STABLE-1234_20260527_000000/
  .coding-agent/tickets/STABLE-1234_20260527_120000/  ← 같은 티켓 재작업
```

### 4.2 .gitignore 처리

`.coding-agent/` 디렉토리는 프로젝트의 `.gitignore`에 추가한다.
이유: 작업 아티팩트(state.json, 분석 문서, 로그)는 프로젝트 레포에 포함되지 않아야 함.

```gitignore
# coding-agent work artifacts
.coding-agent/
```

### 4.3 폴더 탐색 유틸리티

```
find_workspace(ticket_id, status_filter?):
  1. .coding-agent/tickets/ 하위 스캔
  2. {ticket_id}_ 로 시작하는 폴더 필터
  3. status_filter 지정 시 state.json의 current_state로 필터
  4. timestamp 역순 정렬 (최신 우선)
  5. 결과 반환: [{workspace_dir, state, created_at}]

find_active_workspaces():
  1. 모든 하위 폴더 스캔
  2. state.json이 pending/in_progress인 폴더만 반환
  3. timestamp 역순 정렬
```

---

## 5. Hook 초기 설정

### 5.1 hooks.json

Phase 1에서는 hook의 골격만 정의한다. 실제 트리거 동작은 Phase 5(Agent Pipeline)에서 구현.

```jsonc
{
  "hooks": [
    {
      "type": "PostToolUse",
      "description": "Agent 완료 시 상태 전이 트리거 (Phase 5에서 구현)",
      "matcher": "Agent",
      "disabled": true
    }
  ]
}
```

---

## 6. 초기 에이전트/스킬 스텁

Phase 1에서는 에이전트와 스킬의 인터페이스만 정의한다. 구체적 로직은 이후 Phase에서 채운다.

### 6.1 plugin/agents/orchestrator.md (스텁)

```markdown
---
name: orchestrator
model: opus-4.7
description: 파이프라인 상태 머신 컨트롤러. state.json을 읽고 적절한 에이전트를 디스패치한다.
---

## 역할
- state.json에서 현재 상태를 읽는다
- 상태에 따라 적절한 서브 에이전트를 디스패치한다
- 에이전트 완료 후 상태 전이를 수행한다

## 입력
- workspace_dir: 작업 폴더 경로

## 동작
(Phase 5에서 구체화)
```

### 6.2 plugin/agents/planner.md, implementer.md, evaluator.md (스텁)

동일한 패턴으로 역할/입력/동작 골격만 정의.

### 6.3 plugin/skills/state-machine/SKILL.md

3.1절의 기능을 skill description으로 기술. Agent가 이 skill을 호출하여 상태를 관리.

### 6.4 plugin/skills/template-parse/SKILL.md, stablenet-context/SKILL.md (스텁)

역할만 정의, 구체적 로직은 이후 Phase에서.

---

## 7. Phase 1 완료 기준

- [ ] plugin/.claude-plugin/plugin.json이 유효한 Claude Code 플러그인 매니페스트
- [ ] /work, /review, /status 커맨드가 인식됨
- [ ] 작업 폴더 생성 + state.json 초기화 동작
- [ ] state.json의 상태 전이 조건 검증 로직 정의
- [ ] 중복 작업 체크 + 중단 복구 진입점 정의
- [ ] .gitignore에 .coding-agent/ 추가
- [ ] 에이전트/스킬 스텁 파일 존재
