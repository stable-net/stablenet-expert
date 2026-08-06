---
description: 승인된 PR을 squash merge하고, Jira를 Complete로 전이하고, 로컬 브랜치를 정리한다.
argument-hint: "<JIRA-ID, 예: STABLE-1234>"
---

# /core-dev:merge

코드 리뷰를 통과한 PR을 squash-merge하고, 이어서 Jira와 로컬 워크스페이스에서
후속 마무리를 진행한다.

이 커맨드는 플러그인에서 `main`을 건드리는 유일한 커맨드이므로, 전제조건이
엄격하고 모든 외부 액션이 로그로 남는다.

§3의 전제조건(PR APPROVED + 필수 체크 green + MERGEABLE)은 하드(HARD) 안전
게이트이며, `state.config.autonomy.auto_merge == true`인 경우조차 **절대**
우회되지 않는다. auto_merge가 통제하는 범위는 오직 (1) 사람이 직접
`/core-dev:merge`를 입력하지 않고도 파이프라인이 이 커맨드에 도달하는지 여부,
(2) sanitize REDACTED 프롬프트를 처리하는지 여부(§4.3) 뿐이며 — merge 안전
체크를 완화하는 일은 절대 없다.

---

## 1. 인자 검증

```
1.1. <JIRA-ID>가 /^[A-Z]+-\d+$/ 형식과 일치해야 함. 불일치 시 사용법 출력:
     "사용법: /core-dev:merge STABLE-1234"
1.2. 레포 루트 확인:
     bash: git rev-parse --show-toplevel → repo_root
     git 레포가 아니면 → 명확한 메시지와 함께 중단.
```

---

## 2. 워크스페이스 + PR 찾기

```
2.1. 가장 최근 티켓 워크스페이스 찾기:
     {repo_root}/.stablenet-expert/tickets/{jira_id}_* 스캔(timestamp 역순)
     state.current_state가 {"COMPLETION","COMPLETED"} 중 하나인 첫 번째 항목을 취함.
     없으면 중단:
       "{jira_id}에 대한 COMPLETION 단계 워크스페이스를 찾을 수 없습니다.
        먼저 /core-dev:work로 PR을 생성하세요."

2.2. workspace/state.json 읽기 → state
     pr_url = state.states.COMPLETION.pr_url
     pr_url이 비어 있으면:
       "이 티켓에는 기록된 PR이 없습니다.
        먼저 /core-dev:work로 파이프라인을 완료하세요."

2.3. pr_url에서 PR 번호 추출(정규식 /pull/(\d+)).
     branch = state.states.IMPLEMENTATION.branch
```

---

## 3. 전제조건 체크 (전부 통과해야 함)

각 체크는 `{workspace}/logs/merge-precheck.log`에 기록된다. 하나라도
실패하면 `main`을 건드리기 전에 중단한다.

```
3.1. gh CLI 인증
     bash: gh auth status
     인증 안 됐으면: "gh auth login을 실행하세요" 힌트와 함께 중단.

3.2. PR이 존재하고 열려 있는지
     bash: gh pr view {pr_number} --json state,reviewDecision,mergeable,statusCheckRollup
     JSON 파싱.
     pr.state != "OPEN"이면: state 값과 함께 중단
       (MERGED → "이미 머지됐습니다."; CLOSED → "머지 없이 PR이 닫혔습니다.").

3.3. 리뷰 승인
     pr.reviewDecision != "APPROVED"이면:
       중단:
         "PR이 승인되지 않았습니다(state: {reviewDecision}). 필요 상태: APPROVED."
         reviewDecision == "CHANGES_REQUESTED"이면:
           힌트: "피드백 반영을 위해 /core-dev:review {pr_url}을 실행하세요."

3.4. 필수 상태 체크
     pr.statusCheckRollup의 각 check에 대해:
       check.status != "COMPLETED" 이거나
       check.conclusion이 {"SUCCESS","NEUTRAL","SKIPPED"}에 없으면:
         failing_checks에 추가
     failing_checks가 비어있지 않으면:
       실패한 체크 목록("ci/build", "ci/test", …)과 함께 중단.

3.5. Mergeable 여부
     pr.mergeable != "MERGEABLE"이면:
       값과 함께 중단(CONFLICTING → "브랜치의 충돌을 해결하세요.";
                       UNKNOWN → "GitHub이 아직 mergeability를 계산 중입니다. 재시도하세요.").
```

하나라도 중단되면, 맨 위에 한 줄 요약을 출력하고 아래에 체크별 상세를
출력한다. git 상태는 건드리지 않는다.

---

## 4. squash 커밋 본문 조립

```
4.1. 티켓과 plan progress 읽기
     workspace/ticket.json 읽기 → ticket
     plan_progress = state.states.IMPLEMENTATION.plan_progress
     commits = flatten(plan_progress.steps[*].commits)

4.2. 크기에 따라 전략을 달리해 본문 작성

     # 2-tier 포맷터
     plan_progress.total_steps <= 10이면:
       body = "{ticket_id}: {ticket.summary}\n\n"
       plan_progress.steps의 각 step에 대해:
         step.commits의 각 hash에 대해:
           subject = bash: git -C {repo_root} log -1 --format=%s {hash}
           body += "* " + subject + "\n"
     아니면:
       # 카테고리 버킷팅
       description에서 유추한 카테고리로 step을 그룹핑:
                 (interface|api|type|signature) → "Interface changes"
                 (impl|logic|finalize|...) → "Implementation"
                 (test|fixture|race|integration) → "Tests"
                 (doc|godoc|changelog|comment) → "Docs"
                 기본값 → "Misc"
       body = "{ticket_id}: {ticket.summary}\n\n"
       [Interface, Implementation, Tests, Docs, Misc] 순서의 각 버킷 이름에 대해:
         steps_in = bucket[name]
         steps_in이 비어 있으면: 건너뜀
         total_commits = sum(len(step.commits) for step in steps_in)
         body += f"* {name} ({total_commits} commits)\n"
         steps_in의 각 step에 대해:
           body += "  - {step.description}\n"

     body += "\nJira: {jira_site_url}/browse/{ticket_id}\n"   # site URL from cloudId resolution
     body += "PR: #{pr_number}\n"

4.3. 게시 전 sanitize(P7-7)
     result = pr-sanitize.scan(text=body, context="squash_commit_body")
     result.ok가 아니면:
       pr-sanitize의 block 메시지와 함께 중단; merge로 진행하지 **않는다**.
     result.scan_result == "REDACTED"이면:
       state.config.autonomy.auto_merge == true이면:
         계속 진행 — body에 이미 redaction이 적용됨(프롬프트 없음).
       아니면:
         계속하기 전에 사용자 확인(pr-sanitize 호출자 가이드에 따라
         소스 자체를 고치는 쪽을 우선함).
     body = result.text
```

---

## 5. squash merge 실행

```
5.1. GitHub 브랜치 보호가 지켜지도록 raw git이 아니라 gh를 사용한다.
     subject = "{ticket_id}: {ticket.summary}"
     # 혹시 몰라 subject도 sanitize한다.
     subject = pr-sanitize.scan(text=subject, context="squash_commit_subject").text

     bash: gh pr merge {pr_number} --squash --delete-branch \
       --subject "{subject}" \
       --body  "$(cat <<'PR_BODY_EOF'
{body}
PR_BODY_EOF
)"

5.2. merge 커밋 해시 확보
     bash: gh pr view {pr_number} --json mergeCommit -q '.mergeCommit.oid' → merge_hash
     merge_hash가 비어 있으면(GitHub eventual consistency):
       3초 sleep 후 최대 3회 재시도.

5.3. 성공 로그
     {workspace}/logs/merge.log에 추가:
       "{ts} merge ok pr=#{pr_number} hash={merge_hash}"
```

`gh pr merge`가 non-zero로 종료되면, merge는 일어나지 **않은** 것이다. gh
출력을 노출하고 중단한다 — §6의 merge 후 단계는 수행하지 않는다.

---

## 6. Merge 후 정리 (Phase 7 §6)

각 단계는 best-effort이며 merge를 절대 되돌리지 않는다. 여기서의 실패는
경고로만 처리된다 — 어느 쪽이든 사용자는 머지된 코드를 그대로 갖는다.

```
6.1. Jira: status → Complete
     transition ticket_id to "Complete" via the `jira-via-atlassian` skill §3
     (getTransitionsForJiraIssue -> three-tier match -> transitionJiraIssue)
     실패 시: 경고 + Jira를 수동으로 갱신하라는 제안 출력.

6.2. Jira: merge 해시로 코멘트
     comment_body = "Merged. Commit: {merge_hash}\nBranch: {branch} (deleted)"
     # 코멘트도 sanitize한다.
     result = pr-sanitize.scan(text=comment_body, context="jira_merge_comment")
     mcp__plugin_atlassian_atlassian__addCommentToJiraIssue(cloudId, ticket_id, result.text)

6.3. 로컬 브랜치 동기화
     # default_branch = 레포의 실제 기본 브랜치(origin/HEAD) — "main"이라고 절대 가정하지 않는다
     bash: default_branch=$(git -C {repo_root} symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||'); [ -n "$default_branch" ] || default_branch=main
     bash: git -C {repo_root} checkout {default_branch}
     bash: git -C {repo_root} pull --ff-only origin {default_branch}
     # 리모트 브랜치는 --delete-branch로 이미 삭제됐다. 로컬
     # 브랜치는 남아있을 수 있으니, 기본 브랜치에 완전히 merge된 경우에만 제거한다.
     bash: git -C {repo_root} branch --merged {default_branch} | grep -E "^\s*{branch}\s*$" \
           | xargs -r git -C {repo_root} branch -d
     수동으로 만든 미병합 버전이 남아있으면, 손대지 않는다 — 누군가의
     로컬 작업물에 `git branch -D`를 절대 쓰지 않는다.

6.4. state.json 마무리
     state.states.COMPLETION.status     = "completed"
     state.states.COMPLETION.merged_at  = ISO now UTC
     state.states.COMPLETION.merge_commit = merge_hash
     state.current_state = "COMPLETED"
     state.json 쓰기
```

---

## 7. 출력

```
✓ STABLE-1234 머지 완료
  PR:     {pr_url}
  Commit: {merge_hash}
  Branch: {branch} (삭제됨)
  Jira:   {ticket_id} → Complete
```

중단 시, 체크별 PASS/FAIL 전제조건 테이블과 처음 실패한 체크의 상세 라인을
출력한다. 다음에 취할 구체적인 액션을 제안한다
(예: "리뷰 코멘트 반영을 위해 /core-dev:review를 실행하세요.").

---

## 8. 안전 정책

- squash merge는 이 플러그인이 `main`을 건드리는 유일한 지점이다. 중단은
  눈에 띄게 알려야 하고, 성공 메시지는 간결해야 한다.
- 브랜치 보호를 절대 우회하지 않는다: `gh pr merge`를 사용하고, raw
  `git merge`나 `git push origin main`은 절대 쓰지 않는다.
- 체크를 무시하기 위해 `--no-verify`나 `--admin`을 절대 사용하지 않는다.
- 이 티켓의 feature 브랜치가 아닌 다른 무엇에도 `git branch -D`를 절대
  쓰지 않으며, `git branch --merged`로 완전히 merge됐음이 확인된 경우에만
  쓴다.
- 부분 실패 후에는 `gh pr view`로 pr.state를 먼저 재확인하지 않고
  `gh pr merge`를 절대 재실행하지 않는다 — 서버 쪽에서는 실제로 merge가
  이미 성공했을 수도 있다.
- 모든 Jira 및 gh API 호출은 사용자가 실행 내역을 감사할 수 있도록
  `{workspace}/logs/merge.log`에 기록된다.
