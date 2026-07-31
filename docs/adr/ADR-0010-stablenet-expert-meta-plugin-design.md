# ADR-0010 — `stablenet-expert` 메타 플러그인 설계 (1단계: doctor만)

문서 성격: **ADR / 설계 결정 (Accepted 2026-07-31).**
짝 문서: 참조 사례 [`references/midnight-expert`](../../../references/midnight-expert)의
`midnight-expert` 메타 플러그인(`plugins/midnight-expert/`) · [ADR-0008](ADR-0008-new-plugin-scaffolding-contract.md)
(신규 플러그인 체크리스트) · `docs/WORKLIST.md` §A · `docs/SETUP.md` §9.9(이 ADR이 자동화하려는
이중 등록 충돌 이슈의 수동 대응 문서).

> **결정 한 줄:** `stablenet-expert` 메타 플러그인은 `midnight-expert@midnight-expert`와 같은 이름
> 패턴(마켓플레이스 이름 = 메타 플러그인 이름, 유일한 예외)으로 만들되, 1단계는 **doctor 체크 하나만**
> — midnight-expert의 `doctor` 스킬(5개 체크: 플러그인/MCP/외부툴/크로스레퍼런스/npm)을 그대로
> 포팅하지 않고, 지금 실제로 있는 문제(플러그인 설치 상태 + **MCP 서버 이중 등록 충돌**, 후자는
> midnight-expert에도 없는 새 체크)만 다룬다. `add-to-ecosystem`/`feedback` 스킬은 포팅하지 않는다.
> **상태:** Accepted (설계만 — 스캐폴딩은 별도 작업)

---

## 1. Context (왜)

`docs/WORKLIST.md` §A의 메타 플러그인 항목("`stablenet-expert` 메타 플러그인 — ecosystem doctor,
크로스플러그인 의존성 감사")은 `core-dev` 외 최소 1개 플러그인이 published되기 전까지 착수 근거가
없다고 보류돼 있었다. `contract-dev` 1단계 퍼블리시(2026-07-31)로 이 조건이 충족됐고, 사용자가
`stablenet-tooling`/`stablenet-qa`보다 이 항목을 우선하기로 결정했다.

### 1.1 이름 — 왜 "stablenet-expert"인가 (마켓플레이스 이름과 동일)

`contract-dev` 리네임(ADR-0009 이후 작업) 때 확립한 원칙은 "마켓플레이스 안 플러그인은 마켓플레이스
이름을 반복하지 않는다"(`core-dev`, `contract-dev` — `stablenet-` 접두어 없음)였다. 메타 플러그인만은
예외다 — **참조 사례에서 실제로 검증된 패턴**이기 때문:

- `midnight-expert` 마켓플레이스 안에 `midnight-expert`라는 이름의 플러그인이 실제로 있다
  (`plugins/midnight-expert/.claude-plugin/plugin.json`의 `"name": "midnight-expert"`).
- README 설치 안내가 그대로 `claude plugin install --scope user midnight-expert@midnight-expert`다.
- 의미상으로도 자연스럽다 — 이 플러그인의 역할 자체가 "마켓플레이스 전체를 대표해서 진단"하는
  것이므로, 마켓플레이스 이름을 그대로 쓰는 게 "이 마켓플레이스의 대표/진단 플러그인"이라는 뜻을
  전달한다. `contract-dev`의 중복(도메인 특정 플러그인에 의미 없이 마켓플레이스 접두어가 붙어있던
  경우)과는 성격이 다르다.

### 1.2 참조 사례 분석 — `midnight-expert`의 `doctor` 스킬

`plugins/midnight-expert/skills/doctor/`를 직접 읽었다. 커맨드 파일(`commands/*.md`) 없이 스킬만
있고(`SKILL.md` + `scripts/*.sh` 5개), 5개 진단을 **병렬 백그라운드 `general-purpose` 에이전트**로
동시 디스패치한 뒤(각 에이전트는 스크립트 하나 실행하고 raw 출력만 반환) 결과를 종합한다:

| 체크 | 스크립트 | 하는 일 |
|---|---|---|
| 플러그인 상태 | `check-plugins.sh` | `~/.claude/plugins/installed_plugins.json` + `settings.json`을 대조해, 하드코딩된 플러그인 목록(9개) 각각의 설치/활성화/버전 확인 |
| MCP 서버 | `check-mcp-servers.sh` | `claude mcp list` 출력에서 기대하는 서버(하드코딩 목록, 지금은 `octocode` 1개)가 연결됐는지 확인 |
| 외부 툴 | `check-ext-tools.sh` | (미조사 — 스코프 밖) |
| 크로스플러그인 레퍼런스 | `check-cross-refs.sh` | 플러그인 A의 문서/스킬이 플러그인 B를 이름으로 참조하는데 B가 설치 안 돼 있는 경우를 탐지 — **MCP 서버 등록 충돌과는 다른 문제**(문서 참조 무결성이지, 실행 시점 연결 충돌이 아님) |
| npm | `check-npm.sh` | (미조사 — 스코프 밖) |

**중요한 발견**: 이 5개 체크 중 어느 것도 오늘 우리가 실제로 겪은 문제
(`coding-agent`+`core-dev`가 동일 MCP 서버를 각자 다른 이름으로 등록해서 동시 활성화 시 한쪽이
연결 실패하는 것, `docs/SETUP.md` §9.9)를 잡지 못한다. `check-mcp-servers.sh`는 `claude mcp list`
(수동으로 `claude mcp add`한 서버용)를 보지, 플러그인이 `.mcp.json`으로 등록하는 서버는 다루지
않는다. `check-cross-refs.sh`는 문서 참조 무결성이지 실행 시점 서버 충돌이 아니다. **이 체크는
참조 사례에 없는, 이 리포에서 새로 설계해야 하는 부분이다.**

---

## 2. Decision (무엇)

### 2.1 1단계 범위

두 체크만:

1. **플러그인 설치/활성화 상태** — `check-plugins.sh` 패턴을 stablenet-expert 마켓플레이스의 실제
   플러그인 목록(`core-dev`, `contract-dev` — 하드코딩, 새 플러그인 생길 때마다 갱신 필요. 자동
   탐색은 `.claude-plugin/marketplace.json`을 파싱하면 가능하지만 1단계에서는 단순 하드코딩으로
   시작 — ADR-0008 §2.2 원칙과 동일하게 "실제로 필요해지면" 일반화)로 포팅.
2. **MCP 서버 이중 등록 충돌 탐지 (신규, 이 ADR의 핵심 기여)** — `~/.claude/settings.json`의
   `enabledPlugins`에서 활성화된 플러그인들의 `.mcp.json`을 각각 읽어, 서로 다른 플러그인이 같은
   서버 식별자(command+args+env 조합, 또는 http type이면 URL)를 등록하고 있는지 대조. 겹치는 게
   있고 그 플러그인들이 동시에 활성화돼 있으면 경고. `docs/SETUP.md` §9.9에서 수동으로 설명하던
   것을 자동 탐지로 승격.

`check-ext-tools.sh`/`check-npm.sh`/`check-cross-refs.sh`에 대응하는 체크, `add-to-ecosystem`
스킬, `feedback` 스킬은 **전부 1단계 범위 밖** — 지금 stablenet-expert엔 npm 패키지도, "외부
프로젝트를 이 마켓플레이스에 추가하는" 워크플로우도, 이슈 자동 리포팅 요구도 없다. 실제 필요가
생기면 그때 추가한다(추측성 포팅 금지 — ADR-0008 §2.2와 동일 원칙).

### 2.2 아키텍처

`midnight-expert`처럼 **스킬 우선**이지만, 이 리포의 기존 패턴(`core-dev`/`contract-dev` 둘 다
`commands/*.md`를 실제로 검증해서 쓰고 있음, `contract-dev`의 커맨드 3개가 이번 세션에 라이브
검증까지 끝난 상태)을 따라 **명시적 `commands/doctor.md`도 같이 둔다** — 스킬만으로 슬래시커맨드가
뜨는지는 이 리포에서 검증된 바 없고, 커맨드 파일 방식은 이미 검증됐다.

1단계는 체크가 2개뿐이라 `midnight-expert`처럼 병렬 백그라운드 에이전트로 쪼개지 않는다 — 커맨드가
직접 두 체크(각각 셸 스크립트 또는 인라인 로직)를 순차 실행하고 종합한다. 체크 개수가 늘어나면(예:
`stablenet-tooling`이 생겨서 세 번째 체크가 필요해지면) 그때 병렬 디스패치로 일반화 — 지금은
오버엔지니어링.

- **MCP 서버 없음** — `contract-dev`와 동일 이유(§2.3, ADR-0009 §2.3 참고): 진단 대상이 되는 바로 그
  플러그인들의 MCP 서버를 자기도 등록해버리면 자기 자신이 이중 등록 충돌의 원인이 될 수 있다.
  진단은 `settings.json`/`.mcp.json` 파일을 직접 읽는 것만으로 충분하다.
- **훅 없음(1단계)** — `midnight-expert`는 `UserPromptSubmit`/`compact-check` 훅이 있지만, 그건
  다른 스킬(`feedback`)과 연동된 것이라 1단계 범위 밖.

### 2.3 플러그인 구조 (ADR-0008 §2.1 체크리스트 적용)

```
plugins/stablenet-expert/
├── .claude-plugin/
│   └── plugin.json          # name: "stablenet-expert" (마켓플레이스와 동일, §1.1), mcpServers 없음
├── commands/
│   └── doctor.md             # 플러그인 상태 + MCP 이중 등록 충돌, 2체크 순차 실행+종합
├── scripts/
│   ├── check-plugins.sh      # settings.json + 마켓플레이스 플러그인 목록 대조
│   └── check-mcp-conflicts.sh # 활성 플러그인들의 .mcp.json 서버 식별자 충돌 탐지 (신규)
└── README.md
```

- `.claude-plugin/marketplace.json`의 `plugins[]`에 항목 추가.
- MCP 서버가 없으므로 `scripts/contract/agent-mcp.schema.json` 등록 불필요.
- 루트 `README.md`에 별도 섹션 추가(Core/Contract Development 섹션과 나란히, 혹은 최상단 — 메타
  플러그인이라 위치는 스캐폴딩 시점에 결정).

---

## 3. Consequences (결과)

- **+**: 오늘 실제로 겪은 문제(이중 MCP 등록)를 다음부터는 `/stablenet-expert:doctor` 한 번으로
  즉시 발견 가능 — `docs/SETUP.md` §9.9의 수동 트러블슈팅을 자동 탐지로 승격.
- **+**: `midnight-expert`의 검증된 명명 패턴을 따르되, 5체크 전부를 추측성으로 포팅하지 않고
  실제로 있는 문제만 다뤄서 스코프가 작다 — `contract-dev` 1단계와 같은 원칙.
- **−/제약**: 플러그인 목록이 하드코딩이라 새 플러그인(`stablenet-tooling` 등)이 생기면 스크립트를
  갱신해야 한다 — `marketplace.json` 파싱 자동화는 후속 과제로 남김.
- **후속**:
  1. 이 ADR 승인 후 §2.3 구조로 실제 스캐폴딩 — 별도 작업.
  2. `check-ext-tools`/`check-npm`/`check-cross-refs`/`add-to-ecosystem`/`feedback` 대응 기능은
     실제 필요(npm 패키지 등장, 외부 프로젝트 온보딩 요구, 이슈 자동화 요구)가 생겼을 때 별도 ADR.
  3. 체크가 3개 이상으로 늘면 `midnight-expert`식 병렬 백그라운드 에이전트 디스패치로 일반화 검토.
