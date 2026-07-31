# WORKLIST — 잔여 작업 (Tier 3)

> **Tier 3 (상태/잔여작업).** dated·disposable, 코드+git에서 재생성 가능. 완료된 항목은
> 삭제한다(이력 보존이 목적이 아니다 — 그건 git log가 한다). 새 항목은 발견 즉시 추가한다.
>
> 최근 정리: 2026-07-31. §B는 namespace 4단계 검증까지 끝나서 사실상 해소됐고, 남은 유일한 항목
> (`docs/SETUP.md` 정정)은 실제 빌드 절차 테스트 이후로 보류하기로 사용자가 결정함. §A는
> `stablenet-contract-dev`가 1단계 퍼블리시 + 커맨드 3개(`test-contract`/`review-contract`/
> `audit-contract`) 전부 라이브 검증까지 끝나서 항목 삭제(완료 정책). 감사 과정에서 실제
> `GovValidator.sol`의 보안 결함 2건(High, 기계적 확인됨)을 찾았는데 — 이건 `stablenet-expert`가
> 아니라 go-stablenet 자체의 이슈라 이 WORKLIST 범위 밖(사용자에게 별도 보고함, 여기 기록 안 함).
> 지금부터는 §A 남은 두 카테고리(`stablenet-tooling`/`stablenet-qa`)가 실작업 우선순위다.

---

## A. 마켓플레이스 로드맵 — 신규 플러그인 카테고리

README 기준 4-카테고리 로드맵 중 `core-dev`·`stablenet-contract-dev`(1단계) 구현 완료. 아래 두
카테고리는 여전히 미착수.

- [ ] **Toolchain & Infrastructure (`stablenet-tooling`)** — 노드/devnet/chainbench 설치, 진단,
  릴리즈 노트. 다음 액션: 스코프 확정(설치 스크립트만? doctor류 진단까지 포함?) 후 별도 설계 필요.
  core-dev의 `scripts/setup.py`/`scripts/doctor.py`는 참고할 수 있으나, 거기 담긴 체크 항목 자체가
  core-dev 전용 의존성(`JIRA_*`, `STABLENET_KNOWLEDGE_*`, `CHAINBENCH_DIR`, core-dev MCP 서버)이라
  그대로 재사용할 수 없다 — 새 플러그인은 다른 점검 대상(예: go 빌드 툴체인, devnet 포트)을 다뤄야
  하므로 값은 새로 정의해야 한다.
- [ ] **Test & QA (`stablenet-qa`)** — 크로스 프로젝트 테스트/품질게이트 툴링. **별도 플러그인으로
  분리할지 자체가 미정** — README가 명시하듯 "future-reconsideration candidate"일 뿐, 현재
  evaluator는 `core-dev` 안에 있고 이 결정을 뒤집을 근거(예: `stablenet-contract-dev`가 자체
  verification이 필요해지는 시점)가 아직 없음. 다음 액션 없음 — 위 두 카테고리 중 하나가 구체화될 때
  재논의.
- [ ] **`stablenet-expert` 메타 플러그인** (ecosystem doctor, 크로스플러그인 의존성 감사) — `core-dev`
  외에 최소 1개 플러그인(위 3개 중 하나)이 published 상태가 되어 감사 대상이 2개 이상 생기기
  전까지는 설계할 근거 자체가 없음 — 착수 대상 아님.

## B. 멀티플러그인 확장성 인프라 (플러그인 #2 착수 전 반드시 정리)

`stablenet-expert`는 coding-agent(단일 플러그인)의 기능을 그대로 옮기는 것에 더해, **여러
플러그인을 지원하는 마켓플레이스 구조로 확장성을 추가한 프로젝트**다. 이 확장성이 실제로 갖춰졌는지
검증하는 작업이었다 — 플러그인-개수 축(lint/CI 자동 탐색, 신규 플러그인 체크리스트, `packages/` 경계)은
[ADR-0008](adr/ADR-0008-new-plugin-scaffolding-contract.md)로, namespace 축(MCP 도구 prefix가
서버 코드 하드코딩이 아니라 실행 시점 설정값이 되도록 그랜트 계층 와일드카드화 + SSoT/sync 스크립트
도입)은 4단계 외부 검증(coding-agent 연결 → stablenet-knowledge-mcp 특화판 연결 → stablenet-expert
플러그인 연결 → namespace `cks`→`stablenet-knowledge` 전환, 코드 수정 없이 동작 확인)으로 각각 완전히
해소했다. 남은 건 이 검증 과정에서 스코프 밖으로 미뤄둔 문서 정정 하나뿐.

- [ ] **(보류 — 실제 빌드 절차 테스트 이후 진행, 2026-07-31 사용자 결정)** `docs/SETUP.md`가
  sibling repo를 여전히 `code-knowledge-system`으로 안내 (9곳: 11·48·52·76·96·
  151·152·158·455줄)** — `stablenet-expert`가 실제로 붙어야 할 건 `stablenet-knowledge-mcp`다.
  `git clone` 안내(52줄), sibling repo 설명(11·48·76줄), 빌드 절차 진입(96줄),
  `STABLENET_KNOWLEDGE_MCP_BIN`/`STABLENET_KNOWLEDGE_CONFIG` 경로 예시(151·152·158줄), prerequisites
  목록(455줄)까지 총 9곳이 구식 이름을 쓰고 있다. namespace 4단계 검증이 전부 끝나서 이제 실제 빌드
  절차·바이너리명·config 파일명을 확인하며 고칠 수 있다 — 다음 액션으로 착수 가능. 이때
  `coding-agent`와 `core-dev`를 동시에 활성화하면 안 된다는 것도 같이 문서화할 것: 두 플러그인이
  같은 MCP 서버(같은 `JIRA_GATEWAY_BIN`/`stablenet-knowledge-mcp` URL)를 각자 다른 이름으로 등록하는
  구조라 동시 활성화 시 한쪽 연결이 세션 내내 실패한다(2026-07-31 발견, 재현 확인).
