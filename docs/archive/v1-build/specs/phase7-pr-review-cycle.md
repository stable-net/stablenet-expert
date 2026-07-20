# Phase 7: PR + Review Cycle

> PR 생성 자동화, 코드 리뷰 피드백 반영, Jira 상태 업데이트,
> squash merge까지의 완료 흐름.

## 1. PR 생성 자동화

### 1.1 PR 생성 흐름

```
EVALUATION_PASS 이후 Orchestrator가 실행:

  1. 원격 push
     git push -u origin feature/{TICKET-ID}

  2. PR body 생성
     plan.md + test-report.md에서 내용 추출

  3. PR 생성
     gh pr create \
       --title "{TICKET-ID}: {ticket.summary}" \
       --body "{PR body}" \
       --base main \
       --head feature/{TICKET-ID}

  4. Jira 댓글 업데이트
     jira_add_comment(ticket_id, "PR created: {pr_url}")

  5. Jira 상태 변경
     jira_update_status(ticket_id, "In Review")

  6. state 업데이트
     state.COMPLETION.pr_url = pr_url
     state.current_state = "COMPLETION"
```

### 1.2 PR Body 구조

```markdown
## {TICKET-ID}: {ticket.summary}

### Jira
{JIRA_BASE_URL}/browse/{TICKET-ID}

### Summary
{analysis.md에서 추출한 작업 요약}

### Changes
{plan.md의 step 목록 - 완료된 순서대로}

- **Step 1**: {description} ({commit_hash})
- **Step 2**: {description} ({commit_hash})
- ...

### Test Results
| Stage | Status |
|-------|--------|
| Unit Test | ✅ PASS (coverage: {N}%) |
| Lint | ✅ PASS |
| Security | ✅ PASS |
| ChainBench | ✅ PASS |

### Impact Analysis
{ckg_impact 결과 요약}
- 영향 모듈: {modules}
- 리스크 레벨: {risk_level}

### Acceptance Criteria
{ticket.acceptance_criteria 체크리스트}
- [x] {criteria 1}
- [x] {criteria 2}
```

### 1.3 PR 라벨 자동 설정

```
작업 유형에 따른 라벨:
  Feature   → ["feature", "auto-generated"]
  Bug Fix   → ["bugfix", "auto-generated"]
  Release   → ["release", "auto-generated"]

리스크 레벨에 따른 추가 라벨:
  high/critical → ["needs-careful-review"]

변경 범위에 따른 라벨:
  consensus/* 수정 → ["consensus"]
  core/* 수정      → ["core"]
  p2p/* 수정       → ["p2p"]
```

---

## 2. /review Command 상세

### 2.1 동작 흐름

```
사용자: /review https://github.com/org/go-stablenet/pull/456

  1. PR 정보 수집
     gh pr view 456 --json number,title,body,headRefName,reviews,comments

  2. 리뷰 코멘트 수집
     gh api repos/{owner}/{repo}/pulls/456/comments
     → 파일별 인라인 코멘트
     
     gh api repos/{owner}/{repo}/pulls/456/reviews
     → 리뷰 전체 코멘트 + 상태 (APPROVED, CHANGES_REQUESTED, COMMENTED)

  3. 브랜치에서 TICKET-ID 추출
     headRefName: "feature/STABLE-1234" → STABLE-1234

  4. 기존 작업 폴더 탐색
     .coding-agent/tickets/STABLE-1234_* 에서 가장 최근 폴더

  5. 리뷰 피드백 문서 생성
     {workspace_dir}/review-feedback-{N}.md

  6. 상태 전이
     state → ANALYSIS (review cycle)
     failure_log에 review cycle 기록

  7. Orchestrator 디스패치 (리뷰 기반 재작업)
```

### 2.2 리뷰 코멘트 구조화

```markdown
# Review Feedback #{N}

## Reviewer: {reviewer_name}
## Status: CHANGES_REQUESTED
## Date: {review_date}

### Comments

#### File: consensus/wbft/finalize.go
- **Line 89**: "이 부분에서 nil 체크가 빠져있습니다. 
  GovStaking이 초기화되지 않은 상태에서 호출될 수 있습니다."
  → 유형: bug_fix
  → 심각도: high

#### File: consensus/wbft/finalize_test.go  
- **Line 120**: "edge case 테스트가 부족합니다.
  staking amount가 0인 경우도 테스트해주세요."
  → 유형: test_addition
  → 심각도: medium

### General Comments
- "전체적으로 로직은 좋지만, 에러 핸들링을 좀 더 꼼꼼하게 해주세요."
  → 유형: code_quality
  → 심각도: low
```

### 2.3 리뷰 피드백 분류

```
각 코멘트를 자동 분류:

유형:
  - bug_fix: 버그나 논리적 오류 지적
  - security: 보안 취약점 지적
  - test_addition: 테스트 추가/개선 요청
  - code_quality: 코드 스타일/품질 개선
  - architecture: 구조적 변경 제안
  - question: 코드에 대한 질문 (코드 변경 불필요)
  - nit: 사소한 개선 (선택적)

심각도:
  - critical: 반드시 수정 (보안, 심각한 버그)
  - high: 수정 필요 (논리 오류, 누락)
  - medium: 수정 권장 (테스트, 품질)
  - low: 선택적 (nit, 스타일)
```

---

## 3. 리뷰 기반 재작업

### 3.1 Planner의 리뷰 모드

```
리뷰 피드백 기반 ANALYSIS:

  1. review-feedback-{N}.md 로드
  
  2. 리뷰 코멘트 분석
     → critical/high 코멘트 → 필수 수정 항목
     → medium → 권장 수정 항목
     → low/nit → 선택적 (plan에는 포함하되 우선순위 낮게)
     → question → 코드 주석 또는 PR 답변으로 해결

  3. 코멘트별 관련 코드 확인
     → 지적된 파일/라인의 현재 코드 읽기
     → CKG로 해당 심볼의 영향 범위 확인
     
  4. 수정 plan 생성
     plan-review-{N}.md:
     → 각 코멘트에 대한 수정 step 정의
     → 기존 plan.md 참조하되, 리뷰 피드백에 맞는 수정

  5. 설계 → 구현 → 평가 사이클
     → 기존 브랜치에서 이어서 작업
     → 추가 커밋으로 수정 반영
```

### 3.2 구현 후 PR 업데이트

```
리뷰 기반 수정 완료 후:

  1. 추가 커밋 push
     git push origin feature/{TICKET-ID}
     → PR에 자동으로 새 커밋 반영

  2. 리뷰 코멘트에 대한 응답
     각 코멘트에 대해 어떻게 수정했는지 응답:
     gh api repos/{owner}/{repo}/pulls/456/comments/{comment_id}/replies \
       -f body="수정 완료: {commit_hash}에서 nil 체크를 추가했습니다."
     
     또는 question 유형:
     gh api ... -f body="이 부분은 {설명}. 코드에 주석을 추가했습니다."

  3. re-review 요청
     gh pr ready 456  (draft → ready, 해당 시)
     
  4. Jira 댓글 업데이트
     jira_add_comment(ticket_id, "Review feedback addressed. See {commit_range}")
```

---

## 4. Squash Merge & 완료

### 4.1 Merge 전제 조건

```
모든 리뷰어가 Approve:
  gh pr view 456 --json reviewDecision
  → reviewDecision == "APPROVED"

CI 통과 (있는 경우):
  gh pr checks 456
  → 모든 check pass

머지 충돌 없음:
  gh pr view 456 --json mergeable
  → mergeable == "MERGEABLE"
```

### 4.2 Squash Merge 실행

```
코드 리뷰 완료 + 모든 조건 충족 시:

  Merge는 자동이 아닌 유저 트리거로 실행한다.
  
  이유:
  - 머지 타이밍은 인간 개발자의 판단
  - 릴리즈 일정, 다른 PR과의 순서 등 컨텍스트 필요
  - 자동 머지로 인한 실수 방지

  유저가 /merge STABLE-1234 또는 /work의 후속 지시로 요청 시:

  1. 전제 조건 재검증
  2. Squash merge 실행
     gh pr merge 456 --squash --delete-branch \
       --subject "{TICKET-ID}: {summary}" \
       --body "{squash commit body}"
  
  3. Squash commit body:
     모든 개별 커밋 메시지를 목록으로 포함:
     
     "STABLE-1234: staking reward overflow 방지
     
     * add GetStakerInfo to GovStaking interface
     * implement GetStakerInfo in wbft engine
     * add unit tests for GetStakerInfo
     * fix nil pointer in Finalize (review feedback)
     
     Jira: {JIRA_URL}/browse/STABLE-1234
     PR: #{456}"
```

### 4.3 Merge 후 처리

```
merge 성공 시:

  1. Jira 상태 변경
     jira_update_status(ticket_id, "Complete")

  2. Jira 댓글
     jira_add_comment(ticket_id, 
       "Merged via squash merge. Commit: {merge_commit_hash}")

  3. state.json 최종 업데이트
     state.current_state = "COMPLETED"
     state.COMPLETION = {
       pr_url: "...",
       merged_at: now(),
       merge_commit: "{hash}",
       squash_merged: true
     }

  4. 로컬 브랜치 정리
     git checkout main
     git pull origin main
     git branch -d feature/{TICKET-ID}  (--delete-branch로 이미 삭제됨)
```

---

## 5. /merge Command

### 5.1 commands/merge.md (추가)

**시그니처**: `/merge <JIRA-ID>`

```
/merge STABLE-1234

  1. 해당 티켓의 작업 폴더에서 PR URL 확인
  2. PR 상태 검증:
     → reviewDecision == "APPROVED"
     → 모든 checks PASS
     → mergeable == "MERGEABLE"
  3. 조건 미충족 시:
     → 어떤 조건이 미충족인지 유저에게 알림
     → 머지 중단
  4. 조건 충족 시:
     → squash merge 실행
     → Jira 업데이트
     → 완료 처리
```

### 5.2 커맨드 구조

Claude Code는 `plugin/commands/` 디렉토리를 자동 검색하므로
plugin.json에 명시적 등록은 불필요하다. /merge 커맨드는 `plugin/commands/merge.md`에 이미 정의됨.

---

## 6. 전체 Lifecycle 요약

```
[인간] Jira 티켓 작성 (템플릿 사용)
    │
    ▼
[인간] /work STABLE-1234
    │
    ▼
[Agent] 티켓 읽기 → 민감정보 필터 → 분석 → 계획 → 설계
    │
    ▼
[Agent] 코드 구현 (분할 커밋, checkpoint)
    │
    ▼
[Agent] 테스트 (unit → lint → security → ChainBench)
    │   ├─ FAIL → 재분석 + 재구현 + 재테스트 (최대 3회)
    │   └─ 3회 초과 → BLOCKED → [인간] 개입
    │
    ▼ PASS
[Agent] PR 생성 + Jira 댓글
    │
    ▼
[인간] 코드 리뷰 + 피드백
    │
    ▼
[인간] /review {PR-URL}
    │
    ▼
[Agent] 리뷰 피드백 반영 → 구현 → 테스트 → PR 업데이트
    │
    ▼ (반복, 모든 리뷰어 Approve)
    │
[인간] /merge STABLE-1234
    │
    ▼
[Agent] Squash merge + Jira Complete + 정리
```

---

## 7. 보안 고려사항

### 7.1 PR Body/Commit 메시지의 민감정보

```
PR body와 commit 메시지에는 코드 스니펫이 포함될 수 있다.
→ PR body 생성 전에 shared/patterns.json으로 스캔
→ 민감정보 발견 시 해당 부분 제거 후 PR 생성
```

### 7.2 GitHub API 인증

```
gh CLI의 기존 인증을 사용 (gh auth login)
→ 별도 토큰 관리 불필요
→ gh auth status로 인증 상태 확인 후 진행
```

### 7.3 Jira 상태 변경 권한

```
Jira API token의 권한 범위:
→ 티켓 읽기, 댓글 추가, 상태 변경
→ 티켓 삭제, 프로젝트 설정 변경 등은 불필요
→ 최소 권한 원칙 적용
```

---

## 8. 에러 처리

| 시나리오 | 처리 |
|----------|------|
| git push 실패 (권한) | 유저에게 push 권한 확인 요청 |
| git push 실패 (충돌) | rebase 시도 → 실패 시 유저에게 수동 해결 요청 |
| gh pr create 실패 | 에러 메시지 전달 + 수동 PR 생성 안내 |
| 리뷰 코멘트 파싱 실패 | 원본 텍스트 그대로 전달 + 유저에게 수동 분류 요청 |
| squash merge 실패 | 전제 조건 재검증 → 미충족 항목 알림 |
| Jira 업데이트 실패 | 경고 출력 (PR/merge는 이미 완료, Jira는 수동 업데이트 가능) |

---

## 9. Phase 7 완료 기준

- [ ] EVALUATION_PASS 후 자동 PR 생성 (gh pr create)
- [ ] PR body에 Jira 링크, 변경 요약, 테스트 결과, 영향 분석 포함
- [ ] PR 라벨 자동 설정 (작업 유형, 리스크, 변경 범위)
- [ ] Jira 댓글에 PR URL 업데이트
- [ ] Jira 상태 "In Review"로 변경
- [ ] /review 커맨드로 PR 리뷰 코멘트 수집 + 구조화
- [ ] 리뷰 피드백 기반 재작업 사이클 동작
- [ ] 수정 후 PR에 추가 커밋 push + 코멘트 응답
- [ ] /merge 커맨드로 squash merge 실행
- [ ] Merge 전제 조건 검증 (approved, checks pass, mergeable)
- [ ] Merge 후 Jira 상태 "Complete" + 로컬 브랜치 정리
- [ ] PR body/commit에 민감정보 스캔
