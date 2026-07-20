# Phase 7: PR + Review Cycle — 작업 상세

> 설계 문서: [phase7-pr-review-cycle.md](../superpowers/specs/phase7-pr-review-cycle.md)

---

## P7-1. PR 자동 생성 [ADAPT] `M`

**상태**: ✅ 완료. `plugin/agents/orchestrator.md §4` — branch push → body 조립(Jira/Summary/Changes/Test/Impact/Acceptance) → pr-sanitize 적용 → `gh pr create` → 라벨 → state 업데이트. push 실패는 state 진행 금지.

**파일**: `plugin/agents/orchestrator.md`의 COMPLETION 처리

**입력**: EVALUATION_PASS 상태의 workspace

**출력**: GitHub PR URL

**핵심 로직**:
```
1. Push
   bash: git push -u origin feature/{TICKET-ID}

2. PR body 조합
   sections = [
     "## Jira\n{JIRA_BASE_URL}/browse/{TICKET-ID}",
     "## Summary\n{analysis.md 요약}",
     "## Changes\n{plan_progress steps + commit hashes}",
     "## Test Results\n{test-report.md 요약 테이블}",
     "## Impact\n{ckg_impact 요약}",
     "## Acceptance Criteria\n{ticket.acceptance_criteria 체크리스트}"
   ]

3. PR body 민감정보 스캔 (P7-7)
   body_text를 shared/patterns.json으로 스캔
   REDACTED 부분 제거 후 PR 생성

4. 생성
   bash: gh pr create --title "{TICKET-ID}: {summary}" \
     --body "{body}" --base main --head feature/{ID}

5. 라벨
   bash: gh pr edit {num} --add-label "{type},{risk},{modules}"
   type: feature/bugfix/auto-generated
   risk: needs-careful-review (high/critical 시)
   modules: consensus/core/governance/... (변경 모듈)
```

**buddy 참고**: `plugin/skills/auto-create-pr/PROCEDURE.md` — PR 자동 생성 패턴

**완료 기준**:
- [ ] PR body에 Jira/Summary/Changes/Test/Impact/Criteria 포함
- [ ] 민감정보 스캔 후 안전한 body만 PR에 포함
- [ ] 라벨 자동 설정

---

## P7-2. Jira 연동 (PR 후) [NEW] `S`

**상태**: ✅ 완료. `orchestrator.md §4 step 6` — jira_add_comment(PR URL) + jira_update_status("In Review"). 실패는 경고만, 파이프라인 중단하지 않음.

**핵심 로직**:
```
jira-gateway: jira_add_comment(ticket_id, "PR created: {pr_url}")
jira-gateway: jira_update_status(ticket_id, "In Review")
```

**에러 처리**: Jira 업데이트 실패 → 경고 (PR 생성은 이미 완료)

**완료 기준**:
- [ ] Jira 댓글에 PR URL 게시
- [ ] Jira 상태 "In Review"로 변경
- [ ] 실패 시 경고만 (파이프라인 중단 안 함)

---

## P7-3. /review 코멘트 파싱 + 구조화 [NEW] `L`

**상태**: ✅ 완료. `plugin/commands/review.md` — gh API로 inline+review 코멘트 수집, LLM으로 7유형 × 4심각도 분류, review-feedback-{N}.md 생성, ANALYSIS 재진입.

**파일**: `commands/review.md`의 내부 로직

**입력**: PR URL 또는 #number

**출력**: review-feedback-{N}.md

**핵심 로직**:
```
1. 코멘트 수집
   bash: gh api repos/{owner}/{repo}/pulls/{num}/comments
   → 파일별 인라인 코멘트 [{path, line, body, user, created_at}]
   
   bash: gh api repos/{owner}/{repo}/pulls/{num}/reviews
   → 리뷰 상태 + 전체 코멘트 [{state, body, user}]

2. 코멘트 분류 (LLM 기반)
   각 코멘트에 대해 Sonnet으로 분류:
   prompt: "다음 코드 리뷰 코멘트를 분류하세요: {comment}"
   
   유형:
     bug_fix — 버그/논리 오류 지적
     security — 보안 취약점
     test_addition — 테스트 추가/개선
     code_quality — 스타일/품질
     architecture — 구조적 변경
     question — 코드에 대한 질문
     nit — 사소한 개선
   
   심각도:
     critical — 반드시 수정 (보안, 심각한 버그)
     high — 수정 필요 (논리 오류)
     medium — 수정 권장 (테스트, 품질)
     low — 선택적

3. 구조화 문서 생성
   review-feedback-{N}.md:
     # Review Feedback #{N}
     ## Reviewer: {name}
     ## Status: {CHANGES_REQUESTED/COMMENTED}
     
     ### Comments
     #### File: {path}
     - **Line {line}**: "{body}"
       → 유형: {type}, 심각도: {severity}
```

**완료 기준**:
- [ ] 인라인 코멘트 + 리뷰 전체 코멘트 수집
- [ ] 유형(7종) + 심각도(4등급) 자동 분류
- [ ] review-feedback-{N}.md 구조화 생성
- [ ] 리뷰 코멘트 없을 때 빈 리뷰 알림

---

## P7-4. 리뷰 기반 재작업 [ADAPT] `L`

**상태**: ✅ 완료. `planner.md §6` bugfix 모드 (plan-fix-{N}.md → 추가 커밋) + `orchestrator.md §4.1` review_cycle re-publish (브랜치 push + 코멘트 reply + 리뷰 재요청). state는 COMPLETION 유지 (PR 그대로).

**핵심 로직**:
```
1. Planner 리뷰 모드
   review-feedback-{N}.md 로드
   critical/high → 필수 수정
   medium → 권장 수정
   low/nit → 선택적 (plan에 포함하되 낮은 우선순위)
   question → PR 답변 또는 코드 주석

2. 수정 plan 생성
   plan-review-{N}.md: 각 코멘트 → 수정 step

3. 구현 → 테스트 사이클 (기존 브랜치에서)

4. PR 업데이트
   bash: git push origin feature/{TICKET-ID}
   
   각 코멘트에 응답:
   bash: gh api repos/{owner}/{repo}/pulls/{num}/comments/{id}/replies \
     -f body="수정: {commit_hash}에서 {설명}"
```

**buddy 참고**: `plugin/skills/iterate-fix-verify/PROCEDURE.md`

**완료 기준**:
- [ ] 리뷰 코멘트 심각도별 우선순위 처리
- [ ] plan-review-{N}.md 생성
- [ ] 추가 커밋으로 PR 업데이트
- [ ] 각 코멘트에 자동 응답 게시

---

## P7-5. /merge 구현 [ADAPT] `M`

**상태**: ✅ 완료. `plugin/commands/merge.md` — 5단계 precondition(인증/PR open/approved/checks/mergeable) → **RI-14 두 단계 commit body** (≤10 step 전체 / 11+ step 카테고리 버킷) → pr-sanitize → `gh pr merge --squash --delete-branch`. 모든 외부 액션 로깅.

**파일**: `commands/merge.md`의 내부 로직

**핵심 로직**: Phase 1 P1-5 상세 참조

**buddy 참고**: `plugin/skills/finish-development-branch/PROCEDURE.md` — 완료 워크플로우

**완료 기준**:
- [ ] 3개 전제조건 검증 (approved + checks + mergeable)
- [ ] squash merge with commit body
- [ ] 실패 시 구체적 미충족 조건 알림

---

## P7-6. Merge 후 처리 [ADAPT] `M`

**상태**: ✅ 완료. `merge.md §6` — Jira status=Complete + 댓글(merge hash) + main pull --ff-only + 안전한 로컬 브랜치 정리(`--merged` 확인 후 `-d`만, 절대 `-D` 금지) + state.COMPLETION.{merged_at, merge_commit} + current_state="COMPLETED".

**핵심 로직**:
```
merge 성공 후:
  1. jira_update_status(ticket_id, "Complete")
  2. jira_add_comment(ticket_id, "Merged. Commit: {hash}")
  3. state.json → COMPLETED, merged_at, merge_commit
  4. bash: git checkout main && git pull
```

**buddy 참고**: `plugin/skills/automate-release-tagging/PROCEDURE.md` — 릴리즈 자동화

**완료 기준**:
- [ ] Jira 완료 처리
- [ ] state.json 최종 업데이트
- [ ] 로컬 main 동기화

---

## P7-7. PR body 민감정보 스캔 [NEW] `S`

**상태**: ✅ 완료. `plugin/skills/pr-sanitize/SKILL.md` — shared/patterns.json 기반 regex + entropy, REDACT/BLOCK/WARN 분류, fail-safe(파일 미존재 → BLOCKED). Orchestrator §4(PR body), /merge §4–§6(squash body/comment/title), §4.1(reply body)에서 모두 호출.

**핵심 로직**:
```
PR body + squash commit body 텍스트에 대해:
  shared/patterns.json 패턴 스캔
  코드 스니펫이 포함된 경우 민감정보 가능성
  
  REDACTED → 해당 부분 제거 후 PR 생성
  BLOCKED → PR body에서 해당 섹션 전체 제거 + 경고
```

**완료 기준**:
- [ ] PR body에 민감정보 포함 시 제거
- [ ] commit body에도 스캔 적용
