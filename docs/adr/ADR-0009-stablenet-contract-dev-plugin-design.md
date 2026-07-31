# ADR-0009 — `stablenet-contract-dev` 플러그인 설계 (1단계: go-stablenet 내장 systemcontracts/)

문서 성격: **ADR / 설계 결정 (Accepted 2026-07-31).**
짝 문서: [ADR-0005](ADR-0005-stablenet-expert-marketplace-split.md) §2.3/§2.4(범위·evaluator 재사용
불가 논증) · [ADR-0008](ADR-0008-new-plugin-scaffolding-contract.md)(신규 플러그인 체크리스트) ·
참조 사례 [`references/midnight-expert`](../../../references/midnight-expert)의 `compact-core` 플러그인
(ADR-0005가 명시한 "대응물").

> **결정 한 줄:** `stablenet-contract-dev`는 **단계적으로** 만든다 — 1단계(이 ADR)는 go-stablenet
> 리포에 이미 내장된 `systemcontracts/`(Solidity, 자체 Go 컴파일러 래퍼 + Go 테스트로 빌드/검증됨)
> 유지보수에 한정하고, `core-dev`의 Jira 파이프라인(orchestrator/planner/implementer/evaluator)은
> 채택하지 **않는다** — `compact-core`처럼 skills + 리뷰/감사 에이전트로만 구성한다. 일반
> Foundry/Hardhat 기반 EVM 개발 지원(2단계)은 실제 수요가 생길 때 별도 ADR로 재검토한다.
> **상태:** Accepted (설계만 — 구현은 이 ADR 승인 후 별도 스캐폴딩 작업)

---

## 1. Context (왜)

`docs/WORKLIST.md` §A는 `stablenet-contract-dev`(Solidity/EVM 스마트컨트랙트 작성·리뷰·보안 감사)의
다음 액션으로 "Solidity 툴체인(Foundry/Hardhat 등) 기준 자체 domain-pack류 구조 설계 ADR 작성"을
지정했다. 이 ADR은 그 착수 지점이다.

### 1.1 범위 재확인 (ADR-0005 §2.4)

`stablenet-contract-dev`는 go-stablenet(geth fork + WBFT)이 EVM 호환이라는 전제 위에서 **Solidity
스마트컨트랙트 작성/리뷰/보안감사**로 한정된다(`compact-core`의 대응물). WBFT·런타임 등 체인 코어
개발은 명시적으로 범위 밖.

### 1.2 실제 툴체인 확인 (2026-07-31, grep/find 검증) — WORKLIST 가정과 다름

WORKLIST는 "Foundry/Hardhat 등"이라고 썼지만, go-stablenet 리포(`cks-refactor-2` 체크아웃)의
`systemcontracts/`를 직접 열어보면 **Foundry/Hardhat을 전혀 쓰지 않는다**:

- **컴파일**: `systemcontracts/compile/main.go` + `systemcontracts/compile/compiler/compiler.go` —
  `solc`를 직접 호출하는 **자체 Go 래퍼**. `solcdownloader/` 서브패키지가 컴파일러 바이너리 관리.
- **테스트**: `systemcontracts/test/*.go`(예: `coin_adapter_test.go`,
  `gov_council_alloc_sync_test.go`) — **Go 테스트**가 컴파일된 컨트랙트를 배포·검증. `.t.sol`
  같은 Solidity 네이티브 테스트 파일은 없다(스키마의 `exclude_tests` 설명에 `*.t.sol`이 언급되지만
  실제로는 쓰이지 않음 — 범용 패턴 언급이지 이 리포 특정 사실이 아니었다).
- **소스**: `systemcontracts/solidity/{v1,v2,libraries,interfaces,abstracts,openzeppelin,test}/`에
  `.sol` 파일 24개.
- **이미 인덱싱됨**: `stablenet-knowledge`(cks) 인덱스가 이 Solidity 파일들을 이미 포함한다
  (`cks_context_*` 도구들의 `language` 파라미터가 `"solidity"`를 1급 값으로 받는다 — 벡터 빌드 로그의
  `languages` 통계에도 `solidity: 388` 청크로 잡혀 있었다, WORKLIST §B 검증 과정에서 확인).

이 사실이 ADR-0005 §2.3의 "evaluator는 Go 문법을 하드코딩해서 Solidity에 재사용 불가"라는 결론을
**부분적으로 재검토하게 만든다** — 최소한 *이 리포 안의* Solidity 작업(`systemcontracts/`)에 한해서는,
실제 빌드/테스트가 Go 명령(`go run systemcontracts/compile`, `go test ./systemcontracts/test/...`)이라
core-dev의 Go 중심 패턴과 표면적으로 안 맞지 않는다. 다만 ADR-0005의 논증 자체(변경된 테스트 함수
탐지가 `Test*`/`Fuzz*` 네이밍을 하드코딩)는 여전히 evaluator를 통째로 재사용하기엔 결합이 강하다 —
아래 §2.3에서 왜 그래도 전체 파이프라인을 그대로 가져오지 않는지 설명한다.

### 1.3 사용자 결정 — 단계적 범위 (2026-07-31)

이 리포 안(go-stablenet `systemcontracts/`) 우선이냐, 특정 리포에 안 묶인 일반 Foundry/Hardhat
지원이냐를 물었고, **둘 다 단계적으로**: 1단계는 go-stablenet 내장 컨트랙트 유지보수(가장 빠른
가치, core-dev 재사용 여지가 큼), 2단계는 일반 EVM 지원(실제 수요가 생기면 별도 ADR)로 결정됐다.

---

## 2. Decision (무엇)

### 2.1 1단계 범위

`systemcontracts/`(v1·v2 컨트랙트, 라이브러리, 인터페이스, OpenZeppelin 벤더 코드) 작성·리뷰·보안
감사. 대상 밖: WBFT/geth 코어, 리포 밖의 신규 Solidity 프로젝트(2단계 대상).

### 2.2 아키텍처 형태 — `compact-core` 형(스킬+리뷰 에이전트), `core-dev`형(Jira 파이프라인) 아님

`compact-core`(참조 사례)를 따른다: **`.mcp.json` 없음, orchestrator/state-machine 없음** —
skills(정적 지식) + 리뷰/감사 에이전트(명령으로 디스패치) 조합. 이유:

1. **범위가 "작성·리뷰·감사"이지 "Jira 티켓→구현→PR→머지"가 아니다.** `core-dev`의 5단계 파이프라인
   (analyzer→planner→implementer→evaluator→orchestrator)은 자율적 버그수정/기능구현 자동화를 위한
   것인데, 1단계 범위(기존 24개 컨트랙트 유지보수 지원)엔 그 정도 자동화가 필요 없다 — 사람이 컨트랙트를
   고치고 이 플러그인은 리뷰/감사/테스트 실행을 돕는 것으로 충분하다. WORKLIST가 언급한 "orchestrator/
   planner/implementer 재검토 대상"은 **아직 필요가 확인되지 않았으므로 채택하지 않는다** — 재검토는
   "불가는 아니다"이지 "지금 만들라"가 아니다.
2. **`compact-core`가 검증된 선례다.** 같은 스코프("스마트컨트랙트 작성·리뷰·보안감사·디버깅")를 이미
   이 구조(agents: `compact-dev`/`reviewer`/`security-reviewer`, commands: `review-compact`/
   `audit-compact`/`debug-contract`, skills: 언어참조·패턴·보안·토큰 등 14개)로 풀었고, 마켓플레이스
   대칭성(ADR-0005의 원래 취지)에도 맞는다.

### 2.3 MCP 서버 — 신설하지 않는다 (핵심 결정, 이번 세션에서 실증된 이유)

`stablenet-contract-dev`는 **자체 `.mcp.json`을 갖지 않는다.** `stablenet-knowledge` 인덱스가
이미 `systemcontracts/`를 포함하고 있으니 재사용하고 싶은 유혹이 있지만, 하면 안 된다:

- **실증된 충돌**: WORKLIST §B 검증(2026-07-30/31)에서, `coding-agent`와 `core-dev` 두 플러그인이
  **같은 MCP 서버(같은 URL/바이너리)를 각자 다른 서버 이름으로 등록**하자 동시 활성화 시 한쪽 연결이
  세션 내내 실패하는 걸 실제로 재현했다(원인: Claude Code가 연결 아이덴티티를 플러그인+서버이름이
  아니라 실제 연결 대상 기준으로 다루는 것으로 보임). `stablenet-contract-dev`가 core-dev와 동일한
  `stablenet-knowledge-mcp` URL을 자기 `.mcp.json`에 또 등록하면, **정확히 같은 문제를 재현한다** —
  그리고 이번엔 회피할 방법이 없다: go-stablenet Go 개발(core-dev)과 그 안의 Solidity 컨트랙트 작업
  (contract-dev)을 같은 세션에서 동시에 쓰는 게 오히려 **정상적인 흔한 사용 패턴**이라, "둘 중 하나만
  켜라"는 회피책이 실사용을 막는다.
- 대안(기각): 두 플러그인이 서버 alias를 완전히 동일하게 맞춰도 소용없다 — 도구 네임스페이스는
  `mcp__plugin_<플러그인명>_<서버alias>__*`라 플러그인명이 다르면 여전히 별개 등록으로 취급된다
  (실증 완료, §2.3 초안 검토 중 직접 확인).
- **채택**: 에이전트는 `Grep`/`Glob`/`Read`로 `systemcontracts/`를 직접 탐색한다. `compact-core`도
  MCP 없이 동일하게 동작한다(선례). 나중에 이 방식이 검색 스케일 문제로 실제로 부족해지면(예: 대규모
  변경 영향 분석에 그래프 탐색이 꼭 필요해지면), 그때 `core-dev`가 이미 켜져 있다는 전제하에
  cross-plugin 도구 참조(`mcp__plugin_core-dev_stablenet-knowledge__*`) 같은 방식을 별도 검토한다 —
  지금은 그 복잡도를 감수할 근거가 없다.

### 2.4 재사용 여부 정리

| core-dev 구성요소 | 1단계에서 재사용? | 이유 |
|---|---|---|
| orchestrator/planner/implementer/evaluator (Jira 파이프라인) | ✗ | §2.2 — 스코프가 자동화 파이프라인을 요구하지 않음 |
| domain-pack 메커니즘 | ✗ | 멀티프로젝트 확장이 아니라 단일 리포 내 컨트랙트 세트 — 오버엔지니어링 |
| `stablenet-knowledge` MCP 서버 | ✗ (직접 등록 안 함) | §2.3 — 이중 등록 충돌 실증됨 |
| `packages/jira-gateway-mcp` | 보류(미필요) | ADR-0008 §2.2가 지정한 첫 검증 사례이지만, 1단계 스코프(리뷰/감사)엔 Jira 연동 자체가 불필요. Jira 연동이 필요해지는 시점(예: 컨트랙트 감사 결과를 티켓화)이 오면 그때 재사용 |
| ADR-0008 §2.1 스캐폴딩 체크리스트 | ✓ | 플러그인 구조 자체는 그대로 따름(§2.5) |
| `compact-core`의 에이전트/커맨드/스킬 *형태* | ✓ (패턴만, 내용은 새로 작성) | §2.2 |

### 2.5 플러그인 구조 (ADR-0008 §2.1 체크리스트 적용)

```
plugins/stablenet-contract-dev/
├── .claude-plugin/
│   └── plugin.json          # name/version(0.1.0)/description/author/license(AGPL-3.0)/mcpServers 없음
├── agents/
│   ├── contract-dev.md       # 컨트랙트 작성/수정 보조(compact-core의 compact-dev 대응)
│   ├── reviewer.md           # 카테고리별 리뷰(구조/가스/테스트/문서 — 보안 제외)
│   └── security-reviewer.md  # 적대적 보안 감사 전담(재진입·접근제어·정수오버플로우·업그레이드 안전성 등)
├── commands/
│   ├── review-contract.md    # 다카테고리 종합 리뷰(reviewer 디스패치)
│   ├── audit-contract.md     # 보안 전담 감사(security-reviewer 디스패치 + 기계적 확인)
│   └── test-contract.md      # systemcontracts/ 컴파일+테스트 실행 래퍼(go run compile, go test)
├── skills/
│   ├── systemcontracts-structure/SKILL.md   # 이 리포 특정: v1/v2 레이아웃, 컴파일 파이프라인, 테스트 관례
│   ├── solidity-security/SKILL.md           # 재진입/접근제어/정수/업그레이드/서명검증 등 취약점 패턴
│   ├── solidity-gas-optimization/SKILL.md
│   └── solidity-patterns/SKILL.md           # OpenZeppelin 관례, 이 리포의 기존 컨트랙트 컨벤션
└── README.md
```

- `.claude-plugin/marketplace.json`의 `plugins[]`에 항목 추가.
- MCP 서버가 없으므로 `scripts/contract/agent-mcp.schema.json` 등록 불필요(§2.3).
- 루트 `README.md`의 "Planned categories" 표에서 "Plugins" 섹션으로 행 이동.
- lint/CI는 `plugins/*/...` 자동 탐색이라(ADR-0008) 별도 등록 불필요.

---

## 3. Consequences (결과)

- **+**: `core-dev`의 Jira 파이프라인·domain-pack·MCP 서버 복잡도를 전혀 가져오지 않아 1단계를
  빠르게 만들 수 있다 — `compact-core`가 이미 같은 스코프에서 검증한 형태를 그대로 따르므로 설계
  리스크가 낮다.
- **+**: 이중 MCP 등록 충돌(§2.3)을 사전에 피해서, `core-dev`와 `stablenet-contract-dev`를 동시에
  켜두고 쓰는 정상적인 사용 패턴이 막히지 않는다.
- **−/제약**: `Grep`/`Glob`/`Read` 기반 탐색은 `stablenet-knowledge`의 그래프/시맨틱 검색보다 약하다
  — `systemcontracts/`(파일 24개)처럼 작은 대상에선 문제없지만, 나중에 대상이 커지면 재검토 필요.
- **후속**:
  1. 이 ADR 승인 후, §2.5 구조로 실제 스캐폴딩(플러그인 파일 생성) — 별도 작업.
  2. 2단계(일반 Foundry/Hardhat EVM 지원)는 리포에 안 묶인 실제 수요가 생겼을 때 별도 ADR로 설계 —
     이 ADR은 1단계만 다룬다.
  3. Jira 연동(`packages/jira-gateway-mcp` 재사용, ADR-0008 §2.2의 검증 사례)이 필요해지는 시점이
     오면 그때 반영.
  4. `stablenet-knowledge` 재사용이 §2.3 사유로 막혀 있다는 점 자체가 반복되는 패턴이면(플러그인
     #3·#4에서도 같은 문제가 나오면), Claude Code MCP 서버 dedup 동작 자체에 대한 근본 해법(예:
     공유 서버를 별도 `packages/`급 "provider" 플러그인으로 한 번만 등록하고 나머지가 참조하는 구조)을
     별도 ADR로 검토할 것 — 지금은 사례가 하나뿐이라 이 ADR 범위 밖.
