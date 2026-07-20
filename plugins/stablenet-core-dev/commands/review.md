---
description: PR 코드리뷰 피드백 반영. 리뷰 코멘트 수집 → 구조화 → 수정 작업 사이클 진입.
argument-hint: "<PR URL 또는 #number, 예: #456>"
---

# /stablenet-core-dev:review

PR 코드 리뷰 피드백을 읽고 수정 작업을 수행한다.

---

## 1. 인자 검증 및 PR 파싱

```
1.1. 인자 형식 확인
   - 빈 인자 → 사용법 출력 후 중단:
     "사용법: /stablenet-core-dev:review <PR-URL 또는 #number>
      예: /stablenet-core-dev:review #456
      또는: /stablenet-core-dev:review https://github.com/org/repo/pull/456"

1.2. PR 번호 추출
   case input:
     "#<digits>":
       pr_number = digits
       owner/repo는 현재 git remote에서 추출:
         bash: gh repo view --json owner,name
     
     "https://github.com/<owner>/<repo>/pull/<num>":
       owner, repo, pr_number = regex 추출
     
     기타:
       에러: "PR URL 또는 #번호 형식이 올바르지 않습니다."
```

---

## 2. gh CLI 인증 확인

```
2.1. gh CLI 설치 + 인증 확인
   bash: gh auth status 2>&1
   "Logged in" 미포함 → 중단:
     "GitHub CLI 인증이 필요합니다. `gh auth login` 실행 후 다시 시도하세요."
```

---

## 3. PR 정보 수집

```
3.1. PR 기본 정보
   bash: gh pr view {pr_number} \
     --json number,title,body,headRefName,baseRefName,reviewDecision,state,url

   결과를 pr_info 변수에 저장.
   pr_info.state == "MERGED" → 알림: "이미 머지된 PR입니다. 새 작업이 필요한 경우 /stablenet-core-dev:work를 사용하세요." + 중단
   pr_info.state == "CLOSED" → 알림 + 중단

3.2. 리뷰 코멘트 수집 (파일별 인라인)
   bash: gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --paginate
   
   결과: [
     {
       "id": ...,
       "path": "consensus/wbft/finalize.go",
       "line": 89,
       "body": "...",
       "user": { "login": "..." },
       "created_at": "..."
     },
     ...
   ]
   → inline_comments 배열에 저장

3.3. 리뷰 전체 코멘트 수집
   bash: gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews --paginate
   
   결과: [
     {
       "id": ...,
       "state": "APPROVED" | "CHANGES_REQUESTED" | "COMMENTED",
       "body": "...",
       "user": { "login": "..." },
       "submitted_at": "..."
     },
     ...
   ]
   → reviews 배열에 저장

3.4. 코멘트 없음 처리
   inline_comments + reviews가 모두 비어있으면:
     알림: "리뷰 코멘트가 없습니다. 작업이 필요하지 않습니다."
     중단
```

---

## 4. JIRA-ID 추출

```
4.1. 브랜치명에서 추출
   pattern: /[A-Z]+-\d+/
   pr_info.headRefName 예: "feature/STABLE-1234"
   매치 발견 → jira_id 결정 → 5단계로 진행

4.2. PR body에서 추출 (브랜치명 실패 시)
   pr_info.body 에서 첫 번째 /[A-Z]+-\d+/ 매치
   매치 발견 → jira_id 결정 → 5단계로 진행

4.3. 추출 실패 시 유저 입력 요청
   "PR에서 JIRA-ID를 자동 추출할 수 없습니다.
    이 PR에 연관된 JIRA-ID를 입력하세요 (예: STABLE-1234):"
   입력 검증: /^[A-Z]+-\d+$/
```

---

## 5. 작업 폴더 탐색

```
5.1. 기존 작업 폴더 탐색
   bash: ls -d {repo_root}/.stablenet-expert/tickets/{jira_id}_* 2>/dev/null | sort -r
   
   결과 있음 → 가장 최신 폴더 선택
     workspace = 최신 폴더 경로
     read workspace/state.json
   
   결과 없음 → 알림:
     "이 PR에 대응하는 stablenet-core-dev 작업 폴더가 없습니다.
      /stablenet-core-dev:work {jira_id} 를 먼저 실행했어야 합니다.
      그래도 진행하시겠습니까? (y/n)"
     y → 새 작업 폴더 생성 (P1-2의 4단계 절차 따름)
     n → 중단
```

---

## 6. 리뷰 코멘트 분류 + 구조화

```
6.1. 다음 review-feedback-{N} 번호 결정
   bash: ls {workspace}/review-feedback-*.md 2>/dev/null | wc -l
   N = 결과 + 1

6.2. 각 인라인 코멘트를 분류
   for each comment in inline_comments:
     LLM 분류 프롬프트:
       "다음 코드 리뷰 코멘트를 분류하세요.
        파일: {comment.path}
        라인: {comment.line}
        내용: {comment.body}
        
        유형 (다음 중 하나):
        - bug_fix: 버그/논리 오류 지적
        - security: 보안 취약점
        - test_addition: 테스트 추가/개선
        - code_quality: 스타일/품질
        - architecture: 구조적 변경
        - question: 코드에 대한 질문
        - nit: 사소한 개선
        
        심각도 (다음 중 하나):
        - critical: 반드시 수정 (보안, 심각한 버그)
        - high: 수정 필요 (논리 오류)
        - medium: 수정 권장
        - low: 선택적
        
        반환: JSON { type, severity, reasoning }"
     
     → classified_comments.push({
         original: comment,
         type: ...,
         severity: ...,
         reasoning: ...
       })

6.3. 리뷰 전체 코멘트(reviews[].body) 분류
   동일 방식으로 reviews 의 본문 코멘트 분류.
   여러 리뷰어가 있으면 reviewer별로 그룹화.

6.4. review-feedback-{N}.md 생성
   템플릿:
   ```markdown
   # Review Feedback #{N}
   PR: {pr_info.url}
   PR Title: {pr_info.title}
   Review Decision: {pr_info.reviewDecision}
   Collected at: {current ISO timestamp}
   
   ## Reviewers
   - {reviewer 이름}: {state (APPROVED/CHANGES_REQUESTED/COMMENTED)} ({submitted_at})
   
   ## Inline Comments
   
   ### File: consensus/wbft/finalize.go
   #### Line 89 [bug_fix / high]
   > "이 부분에서 nil 체크가 빠져있습니다. gov_validator가 초기화되지 않은 상태에서 호출될 수 있습니다."
   - reviewer: {user.login}
   - 분류 근거: {reasoning}
   
   #### Line 145 [test_addition / medium]
   > "..."
   ...
   
   ### File: ...
   
   ## General Comments
   - [code_quality / low] {reviewer}: "..."
   - [question / low] {reviewer}: "..."
   ```

6.5. 분류 통계 출력
   - 전체 코멘트 수
   - 심각도별 분포 (critical: N, high: N, ...)
   - 유형별 분포 (bug_fix: N, test_addition: N, ...)
```

---

## 7. 상태 전이 + Orchestrator 디스패치

```
7.1. failure_log에 review cycle 기록
   state-machine.log_failure(workspace, {
     state: state.current_state,
     agent: "external_reviewer",
     step: "code_review",
     attempted_action: {
       description: "PR 코드 리뷰 사이클",
       related_pr: pr_info.url
     },
     expected_outcome: "PR approved",
     actual_outcome: {
       type: "review_changes_requested",
       summary: "{critical 코멘트 수}건 critical, {high}건 high 수정 요청",
       details: "review-feedback-{N}.md 참조"
     },
     resolution: {
       action: "retry_cycle",
       transitioned_to: "ANALYSIS",
       retry_count: <기존 review cycle 수 + 1>
     }
   })

7.2. 상태 강제 전이 → ANALYSIS
   현재 상태에 관계없이 ANALYSIS로 진입:
     state.current_state = "ANALYSIS"
     state.states.ANALYSIS.status = "in_progress"
     state.states.ANALYSIS.started_at = now()
   Write state.json

7.3. Orchestrator 디스패치
   Agent(
     subagent_type="orchestrator",
     description="Apply review feedback for {jira_id}",
     prompt="
       workspace_dir={workspace}
       mode=review_cycle
       review_feedback_file=review-feedback-{N}.md
       pr_url={pr_info.url}
     "
   )

7.4. 완료 후 출력
   "PR 리뷰 피드백을 반영한 작업이 시작되었습니다.
    workspace: {workspace}
    review-feedback-{N}.md: {분류된 코멘트 수}건"
```

---

## 8. 완료 기준 (체크리스트)

- [ ] PR URL과 #number 양쪽 파싱 지원
- [ ] gh CLI 미인증 시 명확한 에러 메시지
- [ ] 리뷰 코멘트를 7개 유형으로 분류 (bug_fix/security/test_addition/code_quality/architecture/question/nit)
- [ ] 4개 심각도(critical/high/medium/low) 자동 태깅
- [ ] review-feedback-{N}.md에 파일별 인라인 코멘트 구조화 + 일반 코멘트 분리
- [ ] JIRA-ID 추출 실패 시 유저에게 입력 요청
- [ ] 작업 폴더 미존재 시 새 폴더 생성 옵션
- [ ] 머지된/닫힌 PR 차단
- [ ] 코멘트 없을 때 알림 + 중단
- [ ] failure_log에 review cycle 기록
