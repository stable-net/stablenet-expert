# WORKLIST — 잔여 작업 (Tier 3)

> **Tier 3 (상태/잔여작업).** dated·disposable, 코드+git에서 재생성 가능. 완료된 항목은
> 삭제한다(이력 보존이 목적이 아니다 — 그건 git log가 한다). 새 항목은 발견 즉시 추가한다.
>
> 최근 정리: 2026-07-29. `core-dev` 플러그인 이관(coding-agent → stablenet-expert)은 구조·내용·
> 게이트 검증 전부 완료 상태(§C는 그 위에서 남은 마이너 정비). §A(마켓플레이스 로드맵 콘텐츠)와
> §B(멀티플러그인 확장성 인프라)가 지금부터 진행해야 할 실작업이다 — §A의 어떤 항목이든 실제
> 착수하기 전에 §B부터 정리해야 두 번 일하지 않는다.

---

## A. 마켓플레이스 로드맵 — 신규 플러그인 카테고리 (착수 전, 0%)

README 기준 현재 4-카테고리 로드맵(`core-dev`=구현 완료 + 아래 3개=미착수) 중 `core-dev` 1개만
구현됐다. 나머지는 README에 이름·스코프만 적혀 있고 실제 에이전트/스킬/MCP 설계는 아직 없다.

- [ ] **Contract Development (`stablenet-contract-dev`)** — Solidity/EVM 스마트컨트랙트 작성·리뷰·
  보안 감사. 다음 액션: Solidity 툴체인(Foundry/Hardhat 등) 기준 자체 domain-pack류 구조 설계
  ADR 작성부터 시작. 재사용 불가 범위는 **evaluator뿐**([ADR-0005 §2.3](adr/ADR-0005-stablenet-expert-marketplace-split.md):
  변경된 테스트 함수 탐지가 Go 문법을 하드코딩하므로 Solidity에 안 맞음) — orchestrator/planner/
  implementer 같은 Jira-driven 상태 머신 패턴 자체는 재검토 대상이지 "불가"로 확정된 바 없음.
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
플러그인을 지원하는 마켓플레이스 구조로 확장성을 추가한 프로젝트**다. 아래 두 항목은 그 확장성이
실제로 갖춰졌는지 검증하다 남은 것들 — 플러그인-개수 축(lint/CI 자동 탐색, 신규 플러그인 체크리스트,
`packages/` 경계)은 [ADR-0008](adr/ADR-0008-new-plugin-scaffolding-contract.md)로 정리하고
`lint-tool-names.sh`/`ci.yml`을 `plugins/*/...`·`packages/*/...` 자동 탐색으로 고쳐 해소했다.
남은 건 **namespace 축**(플러그인 개수와 무관 — core-dev 하나만 계속 쓰더라도 해당) 하나뿐.

- [ ] **MCP 도구 namespace가 서버 코드에 하드코딩이 아니라 실행 시점 설정값이 됨 — 그랜트 계층은
  와일드카드로 해소(완료), ToolSearch/스키마 계층은 여전히 설계 필요.** 배경: 예전엔 별도 3개
  저장소였던 것이 `knowledge-system`(일반화 베이스)과 `stablenet-knowledge-mcp`(그 위에 만든
  stablenet 전용 특화판)로 통합됐고, **MCP 서버가 어떤 namespace로 뜨느냐에 따라 도구 prefix가
  결정되는 구조**로 바뀌었다(`cks`로 띄우면 `cks_context_*`, `stablenet-knowledge`로 띄우면
  `stablenet_knowledge_context_*`). `stablenet-expert`가 붙어야 할 대상은 `stablenet-knowledge-mcp`
  (일반화 베이스 `knowledge-system`이 아니라).
  검증은 4단계로 진행 중: **(1) 완료** `knowledge-system` 통합 + namespace=`cks`로 기존
  `coding-agent`와 연결, 3-repo 분리 시절과 동일 동작 확인 / **(2) 완료** `stablenet-knowledge-mcp`
  특화판을 같은 방식으로 `coding-agent`와 연결, 동일 동작 확인 / **(3) 완료** `coding-agent` 대신
  `stablenet-expert` 플러그인을 `stablenet-knowledge-mcp`에 연결(단, 변수를 하나씩 바꾸기 위해
  namespace는 여전히 `cks` 유지), 동일 동작 확인 / **(4) 다음** namespace를
  `stablenet-knowledge`로 바꿔 재연결, `stablenet-expert` 플러그인이 **코드 수정 없이** 동작해야 함.

  **(3) 서버 측 검증 (2026-07-30)**: `mcp.yaml`을 `cks-refactor-1@current` → `cks-refactor-2@current`로
  전환하고 `system-mcp` 재기동 후, raw MCP 프로토콜(`initialize`→`tools/list`→`tools/call`)로 직접
  4개 도구를 호출해 확인했다 — `cks.ops.health`(`serviceable=true`, `alignment.ok=true`,
  `source_root=cks-refactor-2`), `cks.ops.freshness`(`fresh=true`, `indexed_head==current_head`),
  `cks.context.find_symbol("main")`(`cmd/gstable/main.go` 등 정확한 citation),
  `cks.context.search_text("NewBlockChain")`(`core/blockchain.go:464` 등 정확한 결과) — 전부 정상.

  **(3) 플러그인 등록 + end-to-end 확인 (2026-07-30/31, 완료)**: `settings.json`에 `stablenet-expert`
  마켓플레이스 등록 + `core-dev@stablenet-expert` 활성화 후 세션 재시작 — 플러그인 노출까지는 확인됨.
  `mcp__plugin_core-dev_stablenet-knowledge__cks_ops_health`/`cks_context_find_symbol("main")`을 실제
  플러그인 경로로 호출해 `cks-refactor-2` 기준 정상 응답(serviceable/alignment ok, `cmd/gstable/main.go`
  citation)까지 받아 end-to-end 확인 완료.

  **발견한 이슈 — 동일 서버 이중 등록 충돌**: `coding-agent`와 `core-dev`를 동시에 활성화하면, 두
  플러그인이 정확히 같은 MCP 서버(같은 `JIRA_GATEWAY_BIN` 경로, 같은 `stablenet-knowledge-mcp` URL)를
  각자 다른 서버 이름으로 등록하는 셈이 되어 **한쪽만 연결되고 다른 쪽은 세션 내내 연결 실패**한다(에이전트
  타입까지 통째로 안 뜸). 프로젝트 로컬 `.claude/settings.local.json`에
  `"enabledPlugins": {"coding-agent@coding-agent": false}`를 넣어 이 프로젝트 디렉터리에서만
  `coding-agent`를 끄자 `core-dev`가 즉시 정상 연결됨 — 원인이 확정됐다. 장기적으로 `coding-agent`에서
  `core-dev`(`stablenet-expert`)로 완전히 이관 완료되면 `coding-agent` 플러그인 자체를 끄면 되므로
  실사용에 지장은 없으나, **과도기(두 플러그인 병행 사용)에는 항상 하나만 켜야 한다**는 걸 여기 기록해둔다.

  **그랜트 계층 — 완료.** Claude Code 공식 문서 확인 결과 `tools:`/`allowed-tools:`는 서버 단위
  와일드카드(`mcp__plugin_core-dev_<server>__*`)를 지원한다(도구 이름 접두어 단위 부분 매칭은
  미지원 — `settings.json`의 `permissions.allow`에서만 가능, 다른 메커니즘). `analyzer`/`evaluator`/
  `orchestrator`/`planner`/`commands/doctor.md`의 개별 도구 나열 71곳(analyzer 41 + evaluator 8 +
  orchestrator 4 + planner 13 + doctor.md 5, git diff로 재확인)을 전부 서버 단위 와일드카드로
  전환했다. 트레이드오프로 `evaluator`(chainbench 8→26)·`orchestrator`(jira-gateway 4→6)·
  `planner`(stablenet-knowledge 13→15)의 grant 범위가 넓어졌는데, 이미 신뢰하는 자사 MCP
  서버들이라 실질 리스크가 낮다고 판단해 확대를 승인함(사용자 결정). `lint-tool-names.sh`도
  `*`를 항상 유효한 것으로 처리하도록 갱신, `overlay-gates.sh` 재검증 통과.

  **ToolSearch/스키마 계층 — 완료.** `scripts/contract/mcp-namespace.json`(SSoT: `server`/`tool_prefix`/
  `base_tool_names`)를 신설하고, `scripts/contract/sync-mcp-namespace.py`(`bench/model-pins/check.py`
  패턴 — `--apply`로 스키마 도구 키 19개 + `plugins/*/**/*.{md,py}` 안의 `cks_*` 리터럴을 전부 한 번에
  재작성, 미지정 시 drift만 보고)를 작성했다. `agent-mcp.schema.json`뿐 아니라 `analyzer.md`/`planner.md`의
  ToolSearch 문자열·bare 의사코드 호출·`doctor.md`/`doctor.py`의 프로즈 언급까지 전부 같은 스크립트로
  커버된다(당초 예상한 56곳보다 실제 대상이 더 넓었음 — `doctor.py`/`doctor.md`도 포함). 사이드박스에서
  `cks`→`stablenet_knowledge`→`cks` 왕복 적용을 검증(바이트 단위로 원본과 일치, `doctor.py` 구문 유효성
  확인)했고, `scripts/contract/tests/test_sync_mcp_namespace.py`(11 테스트)로 회귀 방지, `overlay-gates.sh`에
  P6 게이트로 편입. **주의**: 설계 과정에서 정규식 버그 2개를 직접 발견·수정함 — (1) 다단어 prefix(예:
  `stablenet_knowledge`)가 마지막 단어(`knowledge`)로만 잘못 캡처되는 문제, (2) 그 수정이 역으로
  `mcp__..._server__` 의 구조적 이중 언더스코어(`__`)까지 건너뛰어 `knowledge__cks`처럼 엉뚱하게
  합쳐 캡처하는 문제 — 두 경우 다 사이드박스 왕복 테스트로 잡아냈다. **실행은 여전히 (3)단계 대기**
  (namespace가 바뀌기 전까지 `--apply`를 실제로 돌릴 대상이 없음 — 스크립트는 준비됐지만 미실행).
  **2026-07-30 수정**: (3)단계 검증(coding-agent→stablenet-knowledge-mcp 연결) 도중 라이브 서버의
  `tools/list`를 실제로 떠서 대조해보니, 서버가 노출하는 `cks_context_*` 22개 중 `find_branches`/
  `get_flow`/`expand_flow`/`get_invariant_enforcement` 4개가 이미 서버 단위 와일드카드로 에이전트에
  grant돼 있는데도 SSoT(`base_tool_names`)와 두 저장소의 `agent-mcp.schema.json`(coding-agent,
  stablenet-expert) 모두에서 빠져 있었다 — namespace가 바뀌면 이 4개의 `cks_*` 리터럴은 치환 대상에서
  누락될 뻔했다. 양쪽 schema.json + `mcp-namespace.json`에 추가하고 sync check(19 tools)·lint(51
  tools)·11개 단위 테스트 전부 재검증 통과. `ops.reindex`/`ops.setup`/`ops.setup_status` 3개는 아직
  에이전트에 grant 안 돼 있어 범위 밖으로 남겨둠 — 나중에 grant되면 같이 추가할 것.

  **범위 밖 발견**: `bench/`에도 `cks_*` 참조가 30여 파일에 있다(자체 MCP 클라이언트 코드,
  `bench/stablenet-knowledge-{bench,eval}/*.py` 등). `bench/`는 "dev tooling, not shipped"라 이번
  스크립트의 범위에서 의도적으로 제외했다 — namespace가 실제로 바뀌면 `bench/`도 별도로 손봐야 한다는
  걸 여기 기록해둔다(아직 착수 안 함, 별도 스코프).
- [ ] **`docs/SETUP.md`가 sibling repo를 여전히 `code-knowledge-system`으로 안내 (9곳: 11·48·52·76·96·
  151·152·158·455줄)** — 위 정리에 따르면 `stablenet-expert`가 실제로 붙어야 할 건
  `stablenet-knowledge-mcp`다. `git clone` 안내(52줄), sibling repo 설명(11·48·76줄), 빌드 절차
  진입(96줄), `STABLENET_KNOWLEDGE_MCP_BIN`/`STABLENET_KNOWLEDGE_CONFIG` 경로 예시(151·152·158줄),
  prerequisites 목록(455줄)까지 총 9곳이 구식 이름을 쓰고 있다. 다만 위 (3)단계 검증이 아직 진행
  전이라 `stablenet-knowledge-mcp`의 실제 빌드 절차·바이너리명·config 파일명이 `code-knowledge-system`과
  동일한지 확인 안 됨 — (3) 검증 완료 후 실제 절차를 확인하며 같이 고칠 것(지금 섣불리 문자열만
  바꾸면 또 다른 부정확한 문서가 된다).
