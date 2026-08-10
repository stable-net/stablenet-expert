---
description: PR 을 격리된 클론에서 받아 코드 리뷰한다 — 불변식·side effect·취약점을 보고, 결론을 문서로 남긴 뒤 승인하거나 코멘트를 단다.
argument-hint: "<PR URL 또는 #번호, 예: https://github.com/org/repo/pull/456>"
allowed-tools: Read, Write, Edit, Bash, Agent, Skill, TodoWrite, AskUserQuestion, mcp__plugin_core-dev_stablenet-knowledge, mcp__plugin_atlassian_atlassian
---

# /core-dev:review-pr

임의의 PR 을 읽고 리뷰한다. `review-jira` 와 달리 이 파이프라인이 만든 PR 일 필요가 없고,
워크스페이스도 쓰지 않는다.

> **이 커맨드는 PR 에 코멘트를 달고 승인까지 한다** — 되돌리기 어렵고 다른 사람에게 보이는
> 행동이다. §7 의 확인 절차를 건너뛰지 않는다.

---

## 1. 인자 검증

```
1.1. PR URL 또는 #번호
     "https://github.com/<owner>/<repo>/pull/<n>" → owner, repo, pr_number
     "#<n>" 또는 "<n>" → 현재 레포에서: bash: gh repo view --json owner,name
     그 외 → 사용법 출력 후 중단:
       "사용법: /core-dev:review-pr <PR URL 또는 #번호>"

1.2. bash: gh auth status   실패 시 중단 (`gh auth login` 안내)

1.3. bash: gh pr view {pr_number} --repo {owner}/{repo} \
       --json number,title,body,headRefName,baseRefName,state,url,headRepository,isCrossRepository
     state 가 MERGED/CLOSED → 알림 후 중단. 리뷰할 것이 없다.
```

---

## 2. 격리된 클론

리뷰는 **작업 중인 체크아웃이 아닌 곳**에서 한다. 브랜치를 바꾸거나 stash 를 건드리면 사용자가
하던 일을 망가뜨리고, 리뷰 대상 코드가 로컬 변경과 섞이면 무엇을 읽고 있는지 알 수 없게 된다.

```
2.1. 대상 경로 — PR 번호를 포함해 동시 리뷰가 서로를 덮지 않게 한다
     workdir = /tmp/core-dev-review-pr{pr_number}-{owner}-{repo}

2.2. 이미 있으면 지우고 새로 받는다. 이전 리뷰의 잔재 위에서 읽으면 안 된다.
     bash: rm -rf {workdir}

2.3. bash: gh repo clone {owner}/{repo} {workdir} -- --quiet
     (fork 에서 온 PR 이어도 base 레포를 클론한다. `gh pr checkout` 이 fork remote 를
      알아서 붙인다.)

2.4. bash: cd {workdir} && gh pr checkout {pr_number}
     실패 시 중단하고 gh 출력 그대로 보고.

2.5. 이후 모든 명령은 `git -C {workdir}` 또는 `cd {workdir} && ...` 로 실행한다.
     사용자의 원래 디렉터리에서 리뷰 작업을 하지 않는다.
```

---

## 3. 변경 범위 파악

```
3.1. base = pr_info.baseRefName
     bash: git -C {workdir} fetch -q origin {base}
     bash: git -C {workdir} merge-base HEAD origin/{base}   → merge_base

3.2. bash: git -C {workdir} diff --stat {merge_base}...HEAD
     bash: git -C {workdir} diff {merge_base}...HEAD
     bash: git -C {workdir} log --oneline {merge_base}..HEAD

     `...` 를 쓴다. `..` 는 base 에서 그 사이 일어난 일까지 diff 에 섞어 넣어,
     이 PR 이 하지 않은 변경을 리뷰하게 만든다.

3.3. 변경 파일 목록을 만든다. 생성·삭제·이름변경을 구분한다.
     diff 가 비어 있으면 그 사실을 보고하고 중단한다.
```

---

## 4. 리뷰 — 세 축

각 축은 `stablenet-knowledge` 로 **근거를 가져와서** 본다. 근거 없는 지적은 §6 에서 걸러진다.

```
4.1. 구현 시 주의사항 — 이 코드가 지켜야 하는 규칙이 있는가
     mcp: cks_context_find_invariants(변경된 모듈/심볼)
     mcp: cks_context_get_conventions(변경된 경로)
     mcp: cks_context_get_invariant_enforcement(관련 불변식)

     불변식을 어기는 변경은 지금 오동작하지 않더라도 결함이다. 인용할 근거가 있다.

4.2. side effect — 이 변경이 그래프상 어디까지 닿는가
     변경된 함수/타입마다:
       mcp: cks_context_find_callers(symbol)      호출하는 쪽이 가정을 깨는가
       mcp: cks_context_impact_analysis(symbol)   변경의 파급 범위
       mcp: cks_context_concurrency_impact(symbol) 잠금·순서 가정이 있는가

     시그니처가 그대로여도 **의미**가 바뀌면 호출부가 깨진다. 반환값의 조건, nil 허용 여부,
     호출 순서 같은 것이 여기서 드러난다.

4.3. 취약점 — 공격자가 이 변경으로 무엇을 할 수 있는가
     신뢰 경계를 먼저 정한다: 이 코드에 닿는 입력 중 외부에서 오는 것은 무엇인가.
       - 검증 없이 흘러가는 입력 (경로·명령·쿼리·역직렬화)
       - 권한 검사 우회 경로가 새로 생겼는가
       - 정수 오버플로/언더플로, 경계 계산 (합의·정족수 코드에서 특히)
       - 시크릿·키·토큰이 diff 에 들어왔는가
       - 서비스 거부: 무한 루프, 무제한 할당, 외부가 좌우하는 재시도

     "안전하지 않아 보인다" 는 지적이 아니다. **누가 무엇을 넣으면 무엇이 되는지** 를 쓴다.
```

각 발견은 이 형태로 `{workdir}/review-findings.json` 에 모은다:

```json
{"id": "f1", "file": "consensus/wbft/core.go", "line": 214,
 "severity": "critical|major|minor",
 "axis": "invariant|side-effect|security",
 "claim": "무엇이 왜 문제인가 — 구체적 경로로",
 "evidence": "cks 도구 결과나 코드 인용",
 "suggestion": "어떻게 고치면 되는가 (선택)"}
```

---

## 5. 결론 문서

```
5.1. {workdir}/review-report.md 작성
     - PR 번호·제목·base·커밋 수·변경 규모
     - 세 축별로 본 것과 발견한 것 (발견이 없으면 "없음" 이라고 쓴다 — 빈 절은 검토를
       안 한 것과 구분되지 않는다)
     - 확인하지 못한 것: 인덱스에 없어서 못 본 모듈, 실행하지 못한 테스트 등
       리뷰의 한계를 적지 않으면 읽는 사람이 전수 검토로 오해한다
5.2. 사용자에게 경로를 알려준다. 이 문서는 PR 에 올라가지 않는다.
```

---

## 6. 2차 검토 — 다른 모델

```
6.1. Agent 도구로 `review-adjudicator` 를 띄운다 (다른 모델).
     전달: findings.json 경로, workdir, merge_base
     받는다: 발견마다 keep/drop + 이유 (+ 표현 교정)

6.2. drop 된 것은 **버린다.** 되살리지 않는다.
     이 단계는 "불필요한 수정 요청" 과 "코드 오독에 의한 지적" 을 막으려고 있는 것이지,
     한 번 더 물어보고 원래 결론을 유지하려고 있는 게 아니다.

6.3. correction 이 붙은 것은 그 표현으로 바꾼다.

6.4. adjudicator 가 실패하거나 응답이 비면 **코멘트를 달지 않는다.**
     검토되지 않은 리뷰를 올리는 것보다 리뷰를 안 올리는 편이 낫다. 리포트만 남기고 그
     사실을 보고한다.
```

---

## 7. 게시 — 확인을 받고

```
7.1. pr-sanitize 통과
     남은 발견의 claim/suggestion 전부에 대해:
       result = pr-sanitize.scan(text=..., context="pr_review_comment")
     BLOCKED → 게시하지 않고 중단, 무엇이 걸렸는지 보고.

7.2. 사용자 확인 — AskUserQuestion
     발견이 있으면:
       header: "PR 리뷰 게시"
       question: "{owner}/{repo}#{pr_number} 에 코멘트 {n}건을 답니다.
                  critical {a} / major {b} / minor {c}. 요약: ...
                  게시하면 다른 사람에게 보이고 알림이 갑니다."
       options:
         - "게시한다"
         - "게시하지 않는다 (리포트만 본다)"
     발견이 없으면:
       header: "PR 승인"
       question: "지적할 것을 찾지 못했습니다. {owner}/{repo}#{pr_number} 를 LGTM 으로
                  승인합니까? 승인은 다른 사람에게 보입니다."
       options:
         - "승인한다"
         - "승인하지 않는다 (리포트만 본다)"

     확인 없이 게시하거나 승인하지 않는다. 자동 승인은 이 커맨드가 하는 일이 아니다.

7.3. 발견이 없고 승인을 택했을 때
     bash: cd {workdir} && gh pr review {pr_number} --approve \
             --body "LGTM — {요약 한 줄}. 검토: 불변식 / side effect / 보안."

7.4. 발견이 있고 게시를 택했을 때
     줄 단위 코멘트를 단다:
       bash: cd {workdir} && gh pr review {pr_number} --comment \
               --body "{종합 코멘트}"
     각 발견은 파일·줄과 함께 본문에 적는다.
     **--request-changes 는 쓰지 않는다.** 사람이 판단할 여지를 남기고, 이 커맨드는
     차단자가 되지 않는다.

7.5. 승인하지 않는 경우에도 리포트 경로는 알려준다.
```

---

## 8. 정리

```
8.1. {workdir} 는 지우지 않는다. 리포트가 그 안에 있고, 사용자가 확인할 수 있어야 한다.
     경로를 출력하고, 다 봤으면 지우라고 안내한다:
       rm -rf {workdir}
8.2. 사용자의 원래 디렉터리는 이 커맨드가 시작할 때와 같아야 한다.
     브랜치·stash·인덱스를 건드리지 않았음을 확인한다.
```

---

## 9. 완료 기준 (체크리스트)

- [ ] `/tmp` 하위, PR 번호가 들어간 경로에 클론
- [ ] `gh pr checkout` 으로 PR 코드 체크아웃
- [ ] `{merge_base}...HEAD` 로 diff (`..` 아님)
- [ ] 세 축 전부 stablenet-knowledge 근거와 함께 검토
- [ ] `review-report.md` 작성, 한계 명시
- [ ] 다른 모델의 adjudicator 로 2차 검토, drop 은 버림
- [ ] 게시·승인 전 사용자 확인
- [ ] pr-sanitize 통과
- [ ] 사용자의 원래 체크아웃 무변경
