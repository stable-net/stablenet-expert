# ADR-0008 — 신규 플러그인 스캐폴딩 계약 + `packages/` vs `plugins/<name>/` 경계

문서 성격: **ADR / 설계 결정 (Accepted 2026-07-29).**
짝 문서: [ADR-0005](ADR-0005-stablenet-expert-marketplace-split.md)(마켓플레이스 분리) ·
[`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json) ·
[`scripts/contract/lint-tool-names.sh`](../../scripts/contract/lint-tool-names.sh)(이제 `plugins/*/agents`·
`plugins/*/commands`를 자동 탐색) · [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)(이제
`plugins/*/scripts/tests`·`packages/*/go.mod`를 자동 탐색).

> **결정 한 줄:** 새 플러그인이 최소한 갖춰야 할 것을 체크리스트로 고정하고, `packages/`(공유)
> vs `plugins/<name>/`(플러그인 전용)를 가르는 기준을 "기본은 플러그인 로컬, 두 번째 소비자가
> 실제로 생겼을 때만 `packages/`로 승격"으로 정한다.
> **상태:** Accepted (lint/CI 자동 탐색은 구현 반영됨 — 체크리스트/경계 기준은 아직 실제 플러그인
> #2가 없어 미검증 상태)

## 1. Context (왜)

`core-dev`는 `coding-agent` 단일 플러그인 리포를 그대로 옮겨와 만들어졌다 — 처음부터 "새 플러그인을
만드는 절차"로 설계된 게 아니라, 있던 걸 옮긴 것뿐이다. 그 결과 두 가지 공백이 생겼다:

1. **체크리스트 부재**: `contract-dev`/`tooling`/`qa` 중 무엇이든 실제로 착수하면, 담당자는
   `core-dev`의 파일 구조를 하나하나 역공학해서 "새 플러그인엔 뭐가 필요한가"를 알아내야 한다.
2. **`packages/` 재사용 기준 부재**: ADR-0005는 `jira-gateway-mcp`·`sensitive-guard`가 `packages/`로
   옮겨진다고만 적었지 *왜* 공유 대상인지, *다음* 플러그인도 그 기준을 따라야 하는지는 정하지 않았다.
   구체적으로: `contract-dev`가 Jira 연동이 필요해지면 `packages/jira-gateway-mcp`를 재사용해야
   하는가?

lint/CI가 `core-dev`에 하드코딩돼 있던 문제(예전 WORKLIST 항목)는 이미 `lint-tool-names.sh`를
`plugins/*/agents`·`plugins/*/commands` 자동 탐색으로, `ci.yml`을 `plugins/*/scripts/tests`·
`packages/*/go.mod` 자동 탐색으로 바꿔 해소했다 — 새 플러그인이 생겨도 이 두 파일은 **더 이상
수정할 필요가 없다**. 이 ADR은 남은 두 공백(체크리스트, 경계 기준)만 다룬다.

## 2. Decision (무엇)

### 2.1 신규 플러그인 체크리스트

`plugins/<name>/` 아래 최소 구성 (전부 `core-dev`의 실제 구조에서 역산):

- `.claude-plugin/plugin.json` — `name`/`version`/`description`/`author`/`license`/`mcpServers` 포인터.
  `version`은 신규 플러그인이므로 `0.1.0`부터(core-dev가 이관 시 확정한 관행 — ADR 근거는 없고
  사용자 결정).
- `.mcp.json` — 이 플러그인이 쓰는 MCP 서버 등록(공유 서버 재사용 여부는 §2.2 기준으로 판단).
- `agents/*.md`, `commands/*.md`, `skills/*/SKILL.md`, `hooks/*` — 필요한 것만(전부 필수는 아님).
  MCP 도구를 쓰는 agent/command라면 grant는 **서버 단위 와일드카드**
  (`mcp__plugin_<name>_<server>__*`)를 기본으로 한다 — 개별 도구 나열은 ADR-0005 이후 겪은
  namespace 리네임 취약점을 그대로 반복하므로 지양(WORKLIST §B 참고).
- `README.md` — 플러그인별 README(마켓플레이스 루트 README와 별개, `core-dev/README.md`가 선례).
- `.claude-plugin/marketplace.json`의 `plugins[]`에 항목 추가.
- MCP 도구를 쓴다면 `scripts/contract/agent-mcp.schema.json`의 `providers`에 등록 — 이 스키마는
  플러그인별로 쪼개지 않고 **전 플러그인 공유 SSoT로 유지**한다. 지금 provider 키가 서버 이름이지
  플러그인 이름이 아니므로, 서로 다른 플러그인이 같은 서버 이름을 등록하면 그때 재검토.
- 루트 `README.md`의 플러그인 표 갱신 — "Planned categories"에서 "Plugins" 섹션으로 행 이동.
- lint/CI 등록은 **불필요**(위 Context 참고 — 자동 탐색됨).

### 2.2 `packages/`(공유) vs `plugins/<name>/`(전용) 경계

기본값은 **플러그인 로컬**이다. `packages/`로 승격하는 조건: **두 번째 실제 소비자가 생겼을 때만**.
미리 "나중에 재사용할 수도 있으니" 공유로 만들지 않는다(추측성 공유는 결합만 늘린다 — ADR-0005
§2.3이 evaluator를 안 쪼갠 이유와 같은 원칙).

이미 `packages/`에 있는 두 사례로 기준을 역산하면:
- **`jira-gateway-mcp`**: Jira 프록시 + 민감정보 필터. 플러그인 특정 로직이 전혀 없다(어떤 티켓
  시스템 연동 플러그인이든 그대로 쓸 수 있음) — 처음부터 공유 후보였다.
  **적용**: `contract-dev`가 Jira 연동이 필요해지면 재사용한다(새로 만들지 않는다) — 이게
  이 경계 기준의 첫 검증 사례가 될 것.
- **`sensitive-guard`**(patterns.json): 민감정보 탐지 정책. 마찬가지로 플러그인 비의존적(무엇을
  가리는지의 문제이지 어떤 파이프라인인지의 문제가 아님).

대조 사례: `core-dev`의 evaluator(Go 문법 하드코딩)는 **로컬로 남았다** — Solidity용
`contract-dev`가 실제로 생겨도 그대로 재사용할 수 없기 때문(ADR-0005 §2.3). 이게
"공유해도 실제로 안 맞는" 경우의 대조 사례다.

## 3. Consequences (결과)

- **+**: 다음 플러그인 착수 시 "뭘 만들어야 하나"를 매번 core-dev에서 역공학하지 않아도 된다.
- **+**: `packages/` 재사용 여부를 매번 새로 논쟁하지 않고 기준으로 판단할 수 있다.
- **−/제약**: 이 체크리스트와 경계 기준은 **실제 플러그인 #2가 아직 없는 상태에서 쓰였다** —
  `contract-dev`/`tooling`/`qa` 중 하나가 실제로 착수되면 이 ADR을 근거로 진행하되, 실제로 안 맞는
  부분이 나오면(예: 체크리스트에 없는 게 필요하거나, 있는 게 불필요하거나) 이 ADR을 갱신하거나
  supersede한다 — 지금은 최선의 추정이지 검증된 사실이 아니다.
- 후속: 플러그인 #2 착수 시 이 ADR의 §2.1/§2.2를 실제로 따라가며 갭이 있으면 기록.
