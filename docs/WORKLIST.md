# WORKLIST — 잔여 작업 (Tier 3)

> **Tier 3 (상태/잔여작업).** dated·disposable, 코드+git에서 재생성 가능. 완료된 항목은
> 삭제한다(이력 보존이 목적이 아니다 — 그건 git log가 한다). 새 항목은 발견 즉시 추가한다.
>
> 최근 정리: 2026-07-31. §B(멀티플러그인 확장성 인프라)는 마지막 항목(`docs/SETUP.md` 정정, PR #10)
> 까지 끝나서 섹션 자체를 삭제함(완료 정책). §A는 `contract-dev`가 1단계 퍼블리시 + 커맨드 3개
> (`test-contract`/`review-contract`/`audit-contract`) 전부 라이브 검증까지 끝나서 항목 삭제. 감사
> 과정에서 실제 `GovValidator.sol`의 보안 결함 2건(High, 기계적 확인됨)을 찾았는데 — 이건
> `stablenet-expert`가 아니라 go-stablenet 자체의 이슈라 이 WORKLIST 범위 밖(사용자에게 별도 보고함,
> 여기 기록 안 함). 지금부터는 §A 남은 두 카테고리(`stablenet-tooling`/`stablenet-qa`)가 실작업
> 우선순위다.

---

## A. 마켓플레이스 로드맵 — 신규 플러그인 카테고리

README 기준 4-카테고리 로드맵 중 `core-dev`·`contract-dev`(1단계) 구현 완료. 아래 두
카테고리는 여전히 미착수.

- [ ] **Toolchain & Infrastructure (`stablenet-tooling`)** — 노드/devnet/chainbench 설치, 진단,
  릴리즈 노트. 다음 액션: 스코프 확정(설치 스크립트만? doctor류 진단까지 포함?) 후 별도 설계 필요.
  core-dev의 `scripts/setup.py`/`scripts/doctor.py`는 참고할 수 있으나, 거기 담긴 체크 항목 자체가
  core-dev 전용 의존성(`JIRA_*`, `STABLENET_KNOWLEDGE_*`, `CHAINBENCH_DIR`, core-dev MCP 서버)이라
  그대로 재사용할 수 없다 — 새 플러그인은 다른 점검 대상(예: go 빌드 툴체인, devnet 포트)을 다뤄야
  하므로 값은 새로 정의해야 한다.
- [ ] **Test & QA (`stablenet-qa`)** — 크로스 프로젝트 테스트/품질게이트 툴링. **별도 플러그인으로
  분리할지 자체가 미정** — README가 명시하듯 "future-reconsideration candidate"일 뿐, 현재
  evaluator는 `core-dev` 안에 있고 이 결정을 뒤집을 근거(예: `contract-dev`가 자체
  verification이 필요해지는 시점)가 아직 없음. 다음 액션 없음 — 위 두 카테고리 중 하나가 구체화될 때
  재논의.
- [ ] **`stablenet-expert` 메타 플러그인** (ecosystem doctor, 크로스플러그인 의존성 감사) — 블로킹
  조건("`core-dev` 외 최소 1개 published")이 `contract-dev` 퍼블리시로 충족됨(2026-07-31).
  다만 실제로 감사할 가치가 있는 크로스플러그인 이슈가 벌써 하나 나왔다 — namespace 검증 중 발견한
  "`coding-agent`/`core-dev`(또는 `contract-dev`) 동시 활성화 시 동일 MCP 서버 이중 등록 충돌"
  (`docs/SETUP.md` §9.9에 문서화됨)이 정확히 이 메타 플러그인이 doctor로 잡아줘야 할 종류의 문제.
  착수 여부는 여전히 사용자
  판단 필요(지금 2개뿐이라 아직 이르다고 볼 수도 있음) — 재검토 대상으로 격상.

---

## C. core-dev 커맨드 재구성 — 진입점을 입력 종류로 가른다

**왜.** 지금은 `work`(Jira 티켓)와 `analyze`(자유 텍스트)가 이름만 봐서는 무엇을 넣어야 하는지
알 수 없다. `review` 도 마찬가지로 PR 코멘트 반영과 PR 코드리뷰가 한 이름에 얹혀 있다. 커맨드
이름이 **입력의 종류**를 말하면 사용자가 고르기 전에 무엇을 준비해야 하는지 알 수 있다.

**공통 요건 (아래 전 항목).** 모든 커맨드는 `description` 에 *무엇을 하는지* 한 줄,
`argument-hint` 에 *무엇을 넣어야 하는지* 를 적는다. 지금 몇몇은 argument-hint 가 형식만 있고
의미가 없다(`"<manifest.json> | <experiment-id>"` 같은 것은 둘 중 무엇을 왜 고르는지 모른다).

- [ ] **C-1. `work` → `work-with-jira` + `work-with-prompt`**
  - `work-with-jira <TICKET>` — 지금의 `work`. Jira 티켓 번호를 받는다.
  - `work-with-prompt "<요구사항>"` — **지금의 `analyze` 를 이름만 바꾸면 된다.** 이미 자유
    텍스트를 받고 Jira 를 안 쓴다(`requirement_source: "local"`).
  - `work` 의 `--local <ticket.json>` 은 **제거한다**(2026-08-07 결정). 이 옵션의 유일한 고유
    역할은 "미리 써둔 ticket.json 으로 파이프라인을 돌려보기"였는데, `work-with-prompt` 가
    Jira 없이 같은 일을 하고 티켓 파일을 준비할 필요도 없다. 확인한 것: **벤치는 이 옵션을
    쓰지 않는다** — `bench-orchestration` SKILL.md §121 이 manifest 의 티켓 파일을 셀
    워크스페이스로 직접 복사하므로 커맨드를 거치지 않는다.
  - 제거하면 따라오는 것: `docs/SETUP.md` §7 스모크 테스트를 `work-with-prompt` 기준으로 다시
    쓰고(§7.1b 가 이미 같은 절차를 설명한다), `state-machine` 의 `sensitive_check` 허용값에서
    `"LOCAL_BYPASS"` 를 뺀다(그 값을 쓰는 유일한 경로가 사라진다).
  - 이름이 바뀌면 이것들도 같이 바뀐다: `atlassian.py` 의 skip 설명, `docs/SETUP.md` §7 스모크
    테스트, `core-dev/README.md` 커맨드 표, orchestrator/planner 프롬프트의 진입점 언급.

- [ ] **C-2. `review` → `review-jira` + `review-pr`**
  - `review-jira <TICKET>` — 티켓 기준 리뷰 피드백 반영(지금 `review` 가 PR 에서 JIRA-ID 를
    역추출하는 절차를 티켓 입력으로 바꾼 것).
  - `review-pr <PR-URL>` — **신규 기능.** PR 내용 + 코드 리뷰를 수행한다. 절차 설계가 필요하고,
    착수 시 별도로 자세히 정의하기로 함(범위: 무엇을 읽고, 무엇을 판정하고, 결과를 어디에
    남기는가 — PR 코멘트인지 로컬 리포트인지).

- [ ] **C-3. `merge` 가 PR URL 을 받는다**
  - 지금은 `<JIRA-ID>` 만 받고 워크스페이스에서 PR 을 역추적한다. 리뷰가 끝난 PR URL 을 직접
    주면 그 PR 을 스쿼시 머지하도록 한다.
  - 기존 승인·CI·mergeable 게이트는 그대로 유지한다(그게 `merge` 가 `main` 을 건드리는 유일한
    커맨드인 이유다).

- [ ] **C-4. 전 커맨드의 description / argument-hint 정비**
  - 10개 커맨드 전부. C-1~C-3 로 이름이 바뀌는 것들은 그 작업에 포함해서 처리한다.

---
