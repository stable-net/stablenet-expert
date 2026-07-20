# Phase 1: Plugin Skeleton + State Machine — 작업 상세

> 설계 문서: [phase1-plugin-skeleton-state-machine.md](../superpowers/specs/phase1-plugin-skeleton-state-machine.md)

---

## P1-1. 프로젝트 초기 구조 [INFRA] `S`

**상태**: ✅ 완료

plugin/.claude-plugin/plugin.json, 디렉토리 구조(plugin/commands, plugin/skills/{name}/SKILL.md, plugin/agents, tools/), .gitignore 등 초기 스캐폴딩.
플러그인 구조 수정 커밋에서 완료.

---

## P1-2. Command: /work [NEW] `M`

**상태**: ✅ 완료 (로직 구현 완료, RI-03 `--local` 옵션 포함)

**파일**: `plugin/commands/work.md`

**입력**: `jira_id: string` (예: STABLE-1234)

**출력**: Orchestrator Agent 디스패치 (workspace_dir 전달)

**핵심 로직**:
```
1. 형식 검증
   input: jira_id
   validate: /^[A-Z]+-\d+$/
   fail → "사용법: /work STABLE-1234"

2. 중복/복구 판별
   scan: .coding-agent/tickets/{jira_id}_*
   for each match, read state.json:
     if current_state == "BLOCKED":
       ask user: "이전 작업이 BLOCKED. 재개? (y/n)"
       y → resume with existing workspace
     if current_state in (in_progress states):
       log "진행 중인 작업 발견. 복구합니다."
       → call state-machine.get_resume_point(workspace)
       → resume
     if current_state == "COMPLETED":
       continue (새 작업 생성)

3. Jira 읽기 + 민감정보 필터
   call: jira-gateway MCP → jira_read_ticket(jira_id)
   response includes _filter_metadata:
     if scan_result == "BLOCKED" → abort, show redacted patterns
     if scan_result == "REDACTED" → warn user, proceed with sanitized data
     if scan_result == "CLEAN" → proceed

4. 작업 폴더 생성
   timestamp = UTC now, format YYYYMMDD_HHmmss
   path = .coding-agent/tickets/{jira_id}_{timestamp}/
   mkdir -p {path}/logs/
   write ticket.json from jira response

5. state.json 초기화
   call: state-machine.init_state(jira_id, ticket_type, path)
   ticket_type = template-parse 결과

6. Orchestrator 디스패치
   Agent(subagent_type="orchestrator", prompt="workspace_dir={path}")
```

**완료 기준**:
- [ ] 유효하지 않은 JIRA-ID에 에러 메시지 출력
- [ ] 기존 in_progress 작업 발견 시 복구 모드 진입
- [ ] BLOCKED 작업 발견 시 유저 확인 후 재개
- [ ] .coding-agent/tickets/ 하위에 올바른 폴더 생성
- [ ] state.json이 TICKET_INTAKE 상태로 초기화
- [ ] Orchestrator Agent가 workspace_dir와 함께 디스패치

---

## P1-3. Command: /review [NEW] `M`

**상태**: ✅ 완료 (로직 구현 완료, gh CLI 기반)

**파일**: `commands/review.md`

**입력**: `pr_url: string` (PR URL 또는 #number)

**출력**: Orchestrator Agent 디스패치 (review cycle 모드)

**핵심 로직**:
```
1. PR 파싱
   if input matches "#\d+":
     pr_number = extract number
   else if input matches github PR URL:
     pr_number = extract from URL
   else → error

2. PR 정보 수집
   bash: gh pr view {pr_number} --json number,title,body,headRefName,reviewDecision
   bash: gh api repos/{owner}/{repo}/pulls/{pr_number}/comments
   bash: gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews

3. JIRA-ID 추출
   from headRefName: "feature/STABLE-1234" → STABLE-1234
   fallback: body에서 /[A-Z]+-\d+/ 첫 번째 매치
   fallback: 유저에게 입력 요청

4. 작업 폴더 탐색
   call: find_workspace(jira_id, status_filter=null)
   가장 최근 폴더 선택
   미존재 시 → 새 폴더 생성

5. 리뷰 피드백 구조화
   각 comment를 분류:
     file, line, body → 유형/심각도 자동 태깅
   write: {workspace}/review-feedback-{N}.md
   (N = 기존 review-feedback-*.md 개수 + 1)

6. 상태 전이 + Orchestrator 디스패치
   state.json → current_state = ANALYSIS
   failure_log에 review_cycle 기록
   Agent(subagent_type="orchestrator", prompt="workspace_dir={path}, mode=review")
```

**완료 기준**:
- [ ] PR URL과 #number 양쪽 파싱 지원
- [ ] 리뷰 코멘트를 유형(bug_fix/security/test_addition/code_quality/architecture/question/nit)으로 분류
- [ ] 심각도(critical/high/medium/low) 자동 태깅
- [ ] review-feedback-{N}.md에 파일별 인라인 코멘트 구조화
- [ ] JIRA-ID 추출 실패 시 유저에게 입력 요청

---

## P1-4. Command: /status [NEW] `S`

**상태**: ✅ 완료 (로직 구현 완료, BLOCKED 강조 포함)

**파일**: `commands/status.md`

**입력**: `jira_id?: string` (선택)

**출력**: 상태 정보 텍스트 출력

**핵심 로직**:
```
1. jira_id 지정 시
   call: find_workspace(jira_id)
   latest = 가장 최근 폴더
   read: state.json
   output:
     - ticket_id, current_state, current_agent
     - branch name (if IMPLEMENTATION+)
     - started_at, last activity (가장 최근 state 변경 시각)
     - failure_summary (total, by_type)
     - artifact list (ls workspace, exclude logs/)
     - if IMPLEMENTATION: step progress table (✓/◐/○)

2. jira_id 미지정 시
   scan: .coding-agent/tickets/*/state.json
   filter: current_state not in ["COMPLETED"]
   for each: output one-line summary
   sort: most recent first
```

**완료 기준**:
- [ ] 특정 티켓 상세 상태 출력
- [ ] IMPLEMENTATION 단계에서 step별 진행률 (✓/◐/○)
- [ ] 전체 활성 작업 목록 출력
- [ ] 작업 없을 때 "활성 작업 없음" 메시지

---

## P1-5. Command: /merge [NEW] `S` ← RI-17 반영: 스텁만

**상태**: ✅ 골격 완료 (Phase 1에서는 스텁만)

**파일**: `commands/merge.md`

> ⚠️ **RI-17**: /merge가 동작하려면 PR URL이 필요한데, PR은 Phase 6 EVALUATION_PASS
> 이후에 생성된다. Phase 1에서는 커맨드 등록 + 스텁만 포함하고,
> **로직 구현은 Phase 7(P7-5)에서 수행한다.**

**Phase 1 범위**:
- plugin/.claude-plugin/plugin.json에 auto-discovery로 인식 (완료)
- plugin/commands/merge.md에 인터페이스 정의 (완료)
- 실행 시 "이 커맨드는 PR 생성 후 사용 가능합니다" 안내 메시지

**Phase 7(P7-5)에서 구현할 내용**:
- 전제조건 검증 (approved, checks, mergeable)
- squash merge 실행
- Jira 상태 Complete + 댓글
- 로컬 정리 + state 업데이트
- commit body 길이 관리 (RI-14: 10+ step 시 카테고리별 요약)

**완료 기준 (Phase 1)**:
- [ ] 커맨드가 인식됨
- [ ] PR 없는 상태에서 실행 시 안내 메시지 출력

---

## P1-6. Skill: state-machine [NEW] `L`

**상태**: ✅ 완료 (6개 함수 + RI-02/RI-13 반영)

**파일**: `plugin/skills/state-machine/SKILL.md`

**핵심 로직 — 각 함수별**:

### init_state(ticket_id, ticket_type, workspace_dir)
```
state.json 생성:
{
  ticket_id, created_at: now(), workspace_dir, ticket_type,
  current_state: "TICKET_INTAKE", current_agent: null,
  states: {
    TICKET_INTAKE: { status: "pending" },
    ANALYSIS: { status: "pending" },
    PLANNING: { status: "pending" },
    DESIGN: { status: "pending", revision: 0 },
    IMPLEMENTATION: { status: "pending", branch: null, plan_progress: null },
    EVALUATION: { status: "pending", results: {unit_test:null,lint:null,security:null,chainbench:null} },
    COMPLETION: { status: "pending", pr_url: null }
  },
  failure_log: [],
  failure_summary: { total_failures:0, by_state:{}, by_type:{}, recurring_patterns:[] },
  config: { max_design_revisions:3, max_eval_cycles:3, impl_model:"sonnet-4.6", planning_model:"opus-4.7" }
}
```

### transition(workspace_dir, from_state, to_state, artifacts?)
```
1. read state.json
2. assert current_state == from_state
3. validate transition conditions:
   (각 조건은 설계 문서 Section 8.2의 전이 규칙 그대로)
4. 조건 충족:
   states[from_state].status = "completed"
   states[from_state].completed_at = now()
   states[to_state].status = "in_progress"
   states[to_state].started_at = now()
   current_state = to_state
   write state.json
5. 조건 미충족:
   return { error: true, missing: ["analysis.md not found", ...] }
```

### log_failure(workspace_dir, failure_entry)
```
1. read state.json
2. failure_log.push(failure_entry)
3. failure_summary 업데이트:
   total_failures += 1
   by_state[entry.state] = (by_state[entry.state] || 0) + 1
   by_type[entry.actual_outcome.type] = ... + 1
4. recurring_patterns 갱신:
   key = normalize(entry.actual_outcome.summary) → "nil_pointer:consensus/wbft" 형태
   existing = patterns.find(p => p.pattern == key)
   if existing:
     existing.occurrences += 1
     existing.failure_ids.push(entry.id)
   else if similar patterns >= 2:
     patterns.push({ pattern: key, occurrences: 1, failure_ids: [entry.id] })
5. write state.json
```

### get_resume_point(workspace_dir)
```
1. read state.json
2. if current_state == "IMPLEMENTATION":
   find first step where status != "completed"
   if step.last_checkpoint:
     return { state: "IMPLEMENTATION", step: step, checkpoint: step.last_checkpoint }
   else:
     return { state: "IMPLEMENTATION", step: step, checkpoint: null }
3. else:
   return { state: current_state, step: null, checkpoint: null }
```

**buddy 참고**: `plugin/skills/status/PROCEDURE.md` — 라이프사이클 상태 추론 패턴

**완료 기준**:
- [ ] init_state가 올바른 state.json 스키마 생성
- [ ] transition이 모든 전이 조건을 검증하고, 미충족 시 구체적 에러 반환
- [ ] update_step_progress가 checkpoint를 포함하여 step 상태 업데이트
- [ ] log_failure가 failure_summary + recurring_patterns 자동 갱신
- [ ] get_resume_point가 중단 지점을 정확히 반환

---

## P1-7. Skill: template-parse [NEW] `M`

**상태**: ✅ 완료 (4개 유형 파싱 + RI-04 ADF 처리 명시)

**파일**: `plugin/skills/template-parse/SKILL.md`

**입력**: Jira 티켓의 description 텍스트 (markdown)

**출력**: 구조화된 JSON

**핵심 로직**:
```
1. 작업 유형 식별
   description에서 "## 작업 유형:" 라인 탐색
   value = trim(line.split(":")[1])
   mapping:
     "Feature" | "기능 추가" → "feature"
     "Bug Fix" | "버그 수정" → "bugfix"
     "Code Review" | "코드 리뷰" → "code_review"
     "Release" | "릴리즈" → "release"
   미인식 → "unknown" + 경고

2. 유형별 필드 추출
   각 "## 섹션명" 헤더를 기준으로 파싱:
   
   feature:
     summary     = "## 요약" 다음 텍스트
     background  = "## 배경" 다음 텍스트
     requirements = "## 요구사항" 하위 체크리스트 아이템 배열
     scope.modules = "## 영향 범위" 하위 "모듈:" 값 (comma split)
     scope.files   = "## 영향 범위" 하위 "예상 변경 파일:" 값
     acceptance    = "## 수용 기준" 하위 체크리스트 아이템 배열
     references    = "## 참고 자료" 하위 텍스트
   
   bugfix:
     summary, steps_to_reproduce, expected, actual,
     scope (modules + severity), acceptance
   
   code_review:
     summary, target (files + perspective), criteria
   
   release:
     version, changes (ticket-summary pairs), checklist

3. 파이프라인 분기 결정
   feature / bugfix → pipeline_variant = "full"
   code_review → pipeline_variant = "review_only"
   release → pipeline_variant = "release"
   unknown → pipeline_variant = "full" (기본, 경고 포함)

4. 필수 필드 검증
   유형별 필수 필드 누락 시 → missing_fields 배열 반환
```

**완료 기준**:
- [ ] 4개 유형(Feature/Bug Fix/Code Review/Release) 정상 파싱
- [ ] 한글/영문 섹션 헤더 양쪽 지원
- [ ] 체크리스트(- [ ] ...) 아이템을 배열로 추출
- [ ] 필수 필드 누락 시 missing_fields로 구체적 알림
- [ ] pipeline_variant 반환으로 Orchestrator 분기 가능

---

## P1-8. Skill: stablenet-context [NEW] `M`

**상태**: ✅ 완료 (일반 구조 모델링, 실제 프로젝트 경로 전달 시 동적 보강)

**파일**: `plugin/skills/stablenet-context/SKILL.md`

**핵심 로직**:
```
1. 도메인 분류
   input: analysis 대상 키워드, 파일 경로, 심볼명 등
   output: 해당 도메인 식별 (consensus/core/governance/p2p/rpc/txpool/state/params/cmd)
   
   분류 규칙:
     file path contains "consensus/" → consensus
     file path contains "governance-wbft/" → governance
     symbol name contains "Finalize", "WBFT", "Engine" → consensus
     symbol name contains "GovStaking", "GovConfig" → governance
     ... (프로젝트 탐색 후 확장)

2. 모듈별 컨텍스트 제공
   각 모듈에 대해:
     - 주요 진입점 함수
     - 동시성 패턴 (goroutine, channel, mutex)
     - 주의사항 (side-effect, 의존성)
     - 관련 테스트 패턴

3. 복잡도 추정
   scope.modules 개수 + 동시성 관련 여부 + cross-module 의존 여부:
     1 모듈, 동시성 무관 → "simple"
     1-2 모듈, 동시성 일부 → "moderate"
     2+ 모듈 또는 consensus 관련 → "complex"
```

**상세화 시점**: go-stablenet 프로젝트 경로가 전달된 후, 실제 코드를 탐색하여 모듈별 정보를 채움.

**완료 기준**:
- [ ] 파일 경로/심볼명 기반 도메인 분류 동작
- [ ] 모듈별 동시성 패턴 정보 제공
- [ ] 복잡도 추정 (simple/moderate/complex) 반환

---

## P1-9. Agent 스텁 파일 [INFRA] `S`

**상태**: ✅ 완료

4개 에이전트(orchestrator, planner, implementer, evaluator)의 역할/도구/동작 골격 정의.
Phase 5에서 구체 로직 구현.

---

## P1-10. Hook 골격 [INFRA] `S`

**상태**: ✅ 완료

hooks.json에 PostToolUse 이벤트 2건 정의 (disabled).
Phase 5에서 활성화 + 스크립트 구현.
