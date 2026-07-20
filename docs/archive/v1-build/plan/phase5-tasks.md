# Phase 5: Agent Pipeline — 작업 상세

> 설계 문서: [phase5-agent-pipeline.md](../superpowers/specs/phase5-agent-pipeline.md)

---

## P5-1. Orchestrator Agent 구현 [NEW] `L`

**상태**: ✅ 완료. `plugin/agents/orchestrator.md` — state dispatch 표, EVALUATION_PASS → PR+Jira, EVALUATION_FAIL → cycle vs BLOCKED, review_only/release 변형 분기, sub-agent dispatch contract, safety policies.

**파일**: `plugin/agents/orchestrator.md` 완성

**입력**: workspace_dir (작업 폴더 경로)

**출력**: 파이프라인 완료 (PR 생성 또는 BLOCKED)

**핵심 로직**:
```
orchestrator(workspace_dir):
  state = read state.json
  
  switch state.current_state:
    TICKET_INTAKE:
      verify ticket.json exists + sensitive_check CLEAN
      transition → ANALYSIS
      dispatch Agent(planner, "workspace={path}")
    
    READY_FOR_IMPL:
      verify plan.md + design-v{final}.md exist
      dispatch Agent(implementer, "workspace={path}")
    
    EVALUATION_PASS:
      push branch + create PR (gh pr create)
      jira_add_comment(PR URL)
      jira_update_status("In Review")
      transition → COMPLETION
    
    EVALUATION_FAIL:
      log_failure(failure details)
      if cycles < max_eval_cycles:
        transition → ANALYSIS (with failure context)
        dispatch Agent(planner, "workspace={path}, mode=bugfix, failure={fail_id}")
      else:
        transition → BLOCKED
        report to user: failure_summary + recurring_patterns
    
    BLOCKED:
      output failure report, await user instruction
```

**PR 생성 로직**:
```
1. git push -u origin feature/{TICKET-ID}
2. PR body 조합:
   - Jira 링크 (ticket.json에서)
   - 변경 요약 (analysis.md에서)
   - Step 목록 + 커밋 (plan_progress에서)
   - 테스트 결과 (test-report.md에서)
   - 영향 분석 (related-code.json + ckg_impact에서)
   - Acceptance Criteria (ticket.json에서)
3. gh pr create --title --body --base main --head feature/{ID}
4. 라벨 설정: 작업 유형 + 리스크 + 변경 모듈
```

**buddy 참고**: `plugin/skills/router/PROCEDURE.md` — 디스패치 패턴

**완료 기준**:
- [ ] state 별 올바른 에이전트 디스패치
- [ ] EVALUATION_PASS → PR 생성 + Jira 업데이트
- [ ] EVALUATION_FAIL → cycle 제한 체크 후 재진입 또는 BLOCKED
- [ ] BLOCKED → 유저에게 failure_summary 보고
- [ ] PR body에 Jira/변경/테스트/영향 정보 포함

---

## P5-2. Planner Agent — ANALYSIS [ADAPT] `L`

**상태**: ✅ 완료. `plugin/agents/planner.md §3` — template-parse → CKV → stablenet-context → CKG query → CKG impact → analysis.md + related-code.json (ckv/ckg/impacts 통합 JSON).

**파일**: `plugin/agents/planner.md` (ANALYSIS 섹션)

**입력**: workspace_dir, ticket.json

**출력**: analysis.md, related-code.json

**핵심 로직**:
```
analysis(workspace_dir):
  1. ticket = read ticket.json
     parsed = template-parse(ticket.description)
     → work_type, requirements, scope, acceptance_criteria

  2. CKV 의미 검색
     keywords = extract from parsed.summary + parsed.requirements
     results = mcp:cks → ckv_search(query=keywords, top_k=15, 
       filters={package: parsed.scope.modules})

  3. Sonnet 도메인 분류
     stablenet-context skill:
     → domain classification (consensus/core/governance/...)
     → complexity estimate (simple/moderate/complex)

  4. CKG 구조 탐색
     symbols = extract top symbols from CKV results
     graph = mcp:cks → ckg_query(symbols, depth=2, 
       include_history=true, include_concurrency=true)

  5. CKG 영향 분석
     for each target_symbol in modification candidates:
       impact = mcp:cks → ckg_impact(symbol, change_type)

  6. Write analysis.md:
     - 티켓 요약, 도메인, 복잡도
     - 관련 코드 목록 (CKV top 10)
     - 의존성/호출 그래프 (CKG)
     - 동시성 영향
     - 히스토리 (과거 이슈)
     - 리스크 평가

  7. Write related-code.json:
     - CKV 결과 전체
     - CKG 노드/엣지
     - impact 결과

  8. transition → PLANNING
```

**buddy 참고**:
- `plugin/skills/plan-build/PROCEDURE.md` — 기술 설계에서 태스크 그래프 생성 흐름

**완료 기준**:
- [ ] CKV + CKG 순차 호출로 관련 코드 수집
- [ ] analysis.md에 도메인/복잡도/리스크 포함
- [ ] related-code.json에 CKV+CKG 결과 구조화

---

## P5-3. Planner Agent — PLANNING [ADAPT] `M`

**상태**: ✅ 완료. `planner.md §4` — atomic/reviewable/verifiable 제약, topological order(테스트는 구현 뒤), verification plan (race scope from CKG concurrency_impact), plan.md.

**파일**: `plugin/agents/planner.md` (PLANNING 섹션)

**입력**: analysis.md, related-code.json

**출력**: plan.md

**핵심 로직**:
```
plan.md 구조:
  ## Step 1: {description}
  - target_files: [파일 목록]
  - target_symbols: [심볼 목록]
  - rationale: 왜 이 수정이 필요한지
  - dependencies: [선행 step]
  - verification: 이 step 검증 방법
  
  ## Step 2: ...
  
  ## 검증 계획
  - 단위 테스트: [목록]
  - go build 검증
  
  ## 리스크
  - [항목]

step 분해 규칙:
  - 1 step = 1 atomic 변경 (되돌릴 수 있는 단위)
  - step 간 의존성은 명시적
  - 테스트 step은 구현 step 뒤에 배치
```

**buddy 참고**:
- `plugin/skills/decompose-track-to-tasks/PROCEDURE.md` — 원자 태스크 분해
- `plugin/skills/map-task-dependencies/PROCEDURE.md` — 의존성 DAG + 크리티컬 패스

**완료 기준**:
- [ ] 작업이 atomic step으로 분해
- [ ] 의존성 기반 정렬
- [ ] 각 step에 verification 정의

---

## P5-4. Planner Agent — DESIGN [NEW] `L`

**상태**: ✅ 완료. `planner.md §5` — per-step before/after pseudocode, side-effect 체크리스트, self-review loop (max_design_revisions 적용 + BLOCKED 전이), design-v{N}.md + design-changelog.md.

**파일**: `plugin/agents/planner.md` (DESIGN 섹션)

**입력**: plan.md, related-code.json

**출력**: design-v{N}.md, design-changelog.md

**핵심 로직**:
```
각 step에 대해:
  1. 수정 대상 코드 로드 (Read, 줄 범위 지정)
  2. 수정 전 코드 인용
  3. 수정 후 의사 코드 또는 구체 코드 작성
  4. side-effect 체크리스트:
     - [ ] 기존 호출자 영향?
     - [ ] 인터페이스 계약 변경?
     - [ ] 동시성 안전성?
     - [ ] 에러 처리 경로 완전?

self-review loop:
  review design-v{N}.md from scratch
  if errors found:
    write design-v{N+1}.md
    append to design-changelog.md: "v{N}→v{N+1}: {reason}"
    N += 1
  if N > max_design_revisions (3):
    → BLOCKED
  if no errors:
    mark design-v{N}.md as final
    transition → READY_FOR_IMPL
```

**완료 기준**:
- [ ] 각 step의 수정 전/후 코드 명시
- [ ] side-effect 체크리스트 포함
- [ ] self-review 반복 (최대 3회)
- [ ] 버전 히스토리 design-changelog.md 기록

---

## P5-5. Implementer Agent 구현 [ADAPT] `L`

**상태**: ✅ 완료. `plugin/agents/implementer.md` — bootstrap → branch 관리 (main/master 보호) → per-step loop (begin/implement/build verify/split commit/end) → 전이.

**파일**: `plugin/agents/implementer.md` 완성

**입력**: workspace_dir (plan.md + design 포함)

**출력**: feature/{TICKET-ID} 브랜치에 커밋된 코드

**핵심 로직**: Phase 5 설계 Section 4.2 참조

**buddy 참고**:
- `plugin/skills/iterate-fix-verify/PROCEDURE.md` — 수정→커밋→검증 루프
- `plugin/skills/build-with-tdd/PROCEDURE.md` — TDD 구현 패턴

**완료 기준**:
- [ ] plan의 모든 step 순회 + 구현
- [ ] step별 분할 커밋
- [ ] 커밋 전 go build 검증
- [ ] checkpoint 주기적 기록 (last_checkpoint)
- [ ] 빌드 실패 시 3회 수정 시도 후 실패 보고

---

## P5-6. Checkpoint/복구 메커니즘 [ADAPT] `M`

**상태**: ✅ 완료. `implementer.md §2.3 + §5` — get_resume_point 활용 fresh/resume 판별, 3가지 트리거(주기/마일스톤/사전 slow op) 체크포인트 작성, 재시작 시 work_in_progress + diff 복원.

**핵심 로직**: Phase 5 설계 Section 4.2 + 시스템 설계 Section 8 참조

**buddy 참고**:
- `plugin/skills/save-context/PROCEDURE.md` — 세션 체크포인트 저장
- `plugin/skills/restore-context/PROCEDURE.md` — 체크포인트 복구

**완료 기준**:
- [ ] /work 재실행 시 기존 작업 감지 + 복구 모드 진입
- [ ] last_checkpoint에서 정확한 지점 재개
- [ ] uncommitted_files 상태 확인 후 판단

---

## P5-7. Bug Cycle 재진입 [ADAPT] `M`

**상태**: ✅ 완료. `planner.md §6` — failure_log + test-report 로드, git diff(main..HEAD, unstaged, staged) 수집, CKS 원본과 종합하여 plan-fix-{cycle}.md 작성 후 PLANNING/DESIGN 통과.

**핵심 로직**: Phase 5 설계 Section 3.5 참조

**buddy 참고**: `plugin/skills/diagnose-bug/PROCEDURE.md` — 근본 원인 분석 프레임워크

**완료 기준**:
- [ ] failure_log에서 실패 원인 로드
- [ ] git diff(로컬) + CKS(원본) 종합
- [ ] plan-fix-{cycle}.md 생성
- [ ] 동일 작업 폴더에서 사이클 재진입

---

## P5-8. 작업 유형별 파이프라인 분기 [NEW] `L` ← RI-18, RI-19 반영으로 난이도 상향

**상태**: ✅ 완료. **RI-18**: `orchestrator.md §6.1 + planner.md §7` Code Review 변형 (review-report.md 포맷 + 종결 처리). **RI-19**: `orchestrator.md §6.2 + planner.md §8` Release 변형 (release-summary.md + EVALUATION 전체 수트 + 태그+CHANGELOG 종결, 사용자 확인 게이트).

**핵심 로직**:

### Code Review (pipeline_variant == "review_only")

> ⚠️ **RI-18**: review-report.md 포맷과 Planner 리뷰 모드 전환 로직을 구체화.

```
흐름: TICKET_INTAKE → ANALYSIS → PLANNING(리뷰 모드) → COMPLETION

Planner 리뷰 모드 (ticket_type == "code_review"):
  ANALYSIS는 동일: CKV/CKG로 대상 코드 분석
  PLANNING에서 plan.md 대신 review-report.md 생성:

  review-report.md 포맷:
    # Code Review Report: {TICKET-ID}
    
    ## 리뷰 대상
    - 모듈: {scope.modules}
    - 관점: {scope.perspective}
    
    ## 발견 사항 (Findings)
    ### [{severity}] {finding title}
    - 위치: {file}:{line}
    - 코드: (해당 코드 인용)
    - 설명: (문제 설명)
    - 권장 조치: (개선 방법)
    
    ## 개선 제안 (Suggestions)
    - {priority}: {suggestion}
    
    ## 코드 품질 요약
    - 전체 평가: {good / needs-improvement / critical}
    - 동시성 안전성: {평가}
    - 테스트 커버리지: {평가}
    - 에러 처리: {평가}

  COMPLETION:
    Jira 댓글에 리뷰 요약 게시
    state → COMPLETED (PR 없음, 구현 없음)
```

### Release (pipeline_variant == "release")

> ⚠️ **RI-19**: Release 파이프라인의 ANALYSIS, EVALUATION, COMPLETION 각 단계 상세.

```
흐름: TICKET_INTAKE → ANALYSIS → EVALUATION → COMPLETION

ANALYSIS (Release 모드):
  1. 티켓의 "포함 변경사항" 필드에서 STABLE-xxx 목록 추출
  2. 각 STABLE-xxx 티켓의 작업 폴더 탐색:
     → analysis.md에서 변경 요약 수집
     → test-report.md에서 테스트 결과 수집
  3. release-summary.md 생성:
     - 포함 변경사항 전체 목록
     - 영향 모듈 통합 목록
     - 각 변경의 리스크 레벨
  산출물: release-summary.md

EVALUATION (Release 모드):
  전체 코드베이스 대상 (변경 코드만이 아닌 전체):
  - go test ./... (전체 unit test)
  - golangci-lint
  - go vet
  - ChainBench 통합 테스트 (기본 genesis 설정)
  산출물: test-report.md (release 전용)

COMPLETION (Release 모드):
  1. git tag v{version}
  2. git push origin v{version}
  3. CHANGELOG.md 업데이트:
     ## v{version} ({date})
     ### Changes
     - STABLE-xxx: {summary}
     - STABLE-yyy: {summary}
  4. Jira 티켓 → Complete
  산출물: 태그, CHANGELOG 업데이트
```

**완료 기준**:
- [ ] Orchestrator가 ticket_type으로 3가지 분기 (full / review_only / release)
- [ ] Code Review: Planner가 리뷰 모드로 전환 + review-report.md 생성
- [ ] Code Review: review-report.md에 발견사항/제안/품질요약 포함
- [ ] Release: ANALYSIS에서 포함 변경사항 취합 + release-summary.md 생성
- [ ] Release: EVALUATION에서 전체 코드베이스 테스트
- [ ] Release: COMPLETION에서 태그 + CHANGELOG 업데이트
- [ ] Release: git push origin v{version} 전에 유저 확인 (안전장치)

---

## P5-9. Hook 구현 [NEW] `M`

**상태**: ✅ 완료. `plugin/hooks/hooks.json` PostToolUse 매핑 + `on-agent-complete.sh` (서브에이전트 종료 로깅) + `on-commit.sh` (커밋 hash + subject + stat을 ticket 워크스페이스 impl.log에 기록). 두 스크립트 모두 fail-open: 비-git 환경 등에서도 exit 0.

**파일**: `plugin/hooks/hooks.json` (활성화) + `plugin/hooks/on-agent-complete.js`, `plugin/hooks/on-commit.js`

**핵심 로직**:
```javascript
// on-agent-complete.js
// PostToolUse(Agent) hook
// 서브 에이전트 완료 시: 로그 기록 + 다음 상태 준비

// on-commit.js
// PostToolUse(Bash, pattern="git commit") hook
// 커밋 시: impl.log에 커밋 정보 추가
```

**완료 기준**:
- [ ] hook이 에이전트 완료 시 로그 기록
- [ ] hook이 커밋 시 진행 상황 로깅
- [ ] hook 실패가 파이프라인을 중단하지 않음 (로깅 전용)
