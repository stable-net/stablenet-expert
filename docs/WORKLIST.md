# WORKLIST — 잔여 작업 (Tier 3)

> **Tier 3 (상태/잔여작업).** dated·disposable, 코드+git에서 재생성 가능. 완료된 항목은
> 삭제한다(이력 보존이 목적이 아니다 — 그건 git log가 한다). 새 항목은 발견 즉시 추가한다.
>
> 최근 정리: 2026-08-07 — §C(커맨드 재구성)에서 C-1·C-3·C-4 완료분을 지우고 `review-pr` 만 남김.
> 그 이전: 2026-07-31. §B(멀티플러그인 확장성 인프라)는 마지막 항목(`docs/SETUP.md` 정정, PR #10)
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

## C. core-dev 커맨드 재구성 — 완료

C-1~C-4 전부 끝났다(PR #34, #35, 그리고 `review-pr`). 완료 항목은 이 파일의 정책대로 지운다 —
무엇을 했는지는 git log 가 안다. 결과만:

- `work` → `work-with-jira <TICKET>` / `work-with-prompt "<요구사항>"`, `--local` 제거
- `review` → `review-jira <TICKET>` + `review-pr <PR-URL>`(신규 — 격리 클론에서 코드 리뷰)
- `merge` 가 티켓과 PR URL 을 모두 받는다
- 11개 커맨드의 description / argument-hint 정비

