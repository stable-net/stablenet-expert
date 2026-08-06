# ADR-0013 — `jira-gateway` 폐기, 공식 Atlassian MCP로 전환 (ADR-0006 인바운드 절 개정)

문서 성격: **ADR / 설계 결정 (Accepted 2026-08-04).**
짝 문서: [ADR-0006](ADR-0006-proxy-mcp-gateway-security-model.md)(이 ADR이 인바운드 절만 개정·supersede,
아웃바운드는 그대로 유효) · [ADR-0008](ADR-0008-new-plugin-scaffolding-contract.md) §2.2(jira-gateway를
`packages/`로 승격시킨 기준) · [ADR-0009](ADR-0009-contract-dev-plugin-design.md)(jira-gateway 재사용을
전제한 대목, 이 ADR로 무효화) · `packages/jira-gateway-mcp/`(삭제 대상) ·
`plugins/core-dev/.mcp.json` · `plugins/core-dev/skills/pr-sanitize/SKILL.md`(변경 없음).

> **결정 한 줄:** 자체 구축한 `jira-gateway` MCP(Go, `packages/jira-gateway-mcp/`)를 폐기하고, 이미
> 사용자 세션에 설치된 공식 Atlassian MCP 플러그인(`atlassian@claude-plugins-official`)을 `core-dev`의
> Jira 백엔드로 쓴다. 이에 따라 ADR-0006이 보장하던 **인바운드(읽기) 서버단 민감정보 필터링을
> 잃는다는 것을 명시적으로 감수**한다 — 아웃바운드(`pr-sanitize`)는 `jira-gateway`와 무관하게
> 독립적으로 동작해왔으므로 변경 없이 유지된다.
> **상태:** Accepted · **구현 완료 (2026-08-06)**
>
> 구현 시 §2.2 에서 한 가지가 바뀌었다: 상태 전이 매칭 스킬의 이름을
> `core-dev:jira-status-transition` 이 아니라 **`jira-via-atlassian`** 으로 두고, 전이 매칭뿐
> 아니라 cloudId 해석과 도구 매핑까지 한 곳에 담았다. 세 가지 모두 "Jira 를 부르기 직전에
> 알아야 하는 것"이고, 호출부가 스킬을 세 번 찾게 만들 이유가 없다.

---

## 1. Context (왜)

`packages/jira-gateway-mcp/`는 Jira REST API를 감싸는 자체 Go MCP 서버로, ADR-0006의 인바운드 절
(티켓/댓글 내용을 LLM에 닿기 전에 `sensitive-guard` 정책으로 REDACT/BLOCK)을 구현하는 유일한 지점이다.
사용자가 이 서버의 유지보수를 중단하고, 대신 이미 별도로 설치해 쓰고 있는 공식 Atlassian MCP 플러그인
(`mcp__plugin_atlassian_atlassian__*` 도구 — `getJiraIssue`, `searchJiraIssuesUsingJql`,
`addCommentToJiraIssue`, `transitionJiraIssue`, `getTransitionsForJiraIssue`,
`getAccessibleAtlassianResources`, `lookupJiraAccountId`, `editJiraIssue` 등)를 쓰기로 결정했다.

### 1.1 조사 결과 요약 (Explore 에이전트 스코핑, 2026-08-04)

- **영향 범위**: `.mcp.json`, `scripts/setup.py`(REQUIRED 7개 중 4개가 jira 전용이고 그중 `JIRA_API_TOKEN`이
  테이블의 유일한 SECRET 항목), `scripts/doctor.py`, `orchestrator.md`(6곳 호출)·`merge.md`(2곳)·
  `work.md`(1곳, 티켓 인입)의 실제 호출부, `template-parse` skill이 전제하던 ADF→Markdown 변환,
  `SETUP.md`/`OVERVIEW.md`/`VISION.md`, ADR-0002/0005/0006/0008/0009/0012, `go.work`,
  `scripts/contract/agent-mcp.schema.json`의 jira-gateway provider 블록.
- **cloudId 필요**: `jira-gateway`는 `JIRA_BASE_URL` env var로 사이트가 고정돼 있었지만, 공식 MCP의
  도구들은 `cloudId` 파라미터를 요구한다 — `getAccessibleAtlassianResources`로 세션당 한 번 해석해야 한다.
- **상태 전이 로직 공백**: `jira_update_status`는 서버 내부에서 `target` 문자열(`"Done"`, `"Complete"` 등)을
  전이명→목표상태명→statusCategory key 순으로 대소문자 무시 퍼지 매칭했다(RI-05,
  `packages/jira-gateway-mcp/internal/jira/client.go`). 공식 MCP는 `getTransitionsForJiraIssue`로 후보
  목록만 주고, 이 매칭은 호출부가 직접 해야 한다 — 이 로직이 리포 어디에도 없어 새로 구현이 필요하다.
- **인바운드 필터링 공백** (§2.2에서 다룸): 공식 MCP의 읽기 도구들은 원본 내용을 그대로 반환하고,
  서버단 스캔이 전혀 없다.
- **미사용 도구**: `jira_update_assignee`(실제 호출부 없음, Planner에서 명시적으로 금지됨),
  `jira_read_comments`(직접 호출부 없음, 문서/스키마에만 존재) — 둘 다 이관 불필요.
- **`atlassian` 플러그인은 이 리포 밖의 존재**: `.claude-plugin/marketplace.json`도, 다른 어떤 문서도
  이 플러그인을 모른다 — 사용자가 개인적으로 설치한, 다른 마켓플레이스(`claude-plugins-official`)의
  플러그인이다. `core-dev`가 이를 전제로 하게 되면, 이 리포의 표준 설치 절차
  (`claude plugin marketplace add stable-net/stablenet-expert` → 플러그인 설치)만으로는 채워지지 않는
  **리포 밖 소프트 디펜던시**가 새로 생긴다 — `docs/SETUP.md`에 새 필수 전제조건으로 명시해야 한다.

---

## 2. Decision (무엇)

### 2.1 지운다

- `packages/jira-gateway-mcp/` 전체 삭제 (Go 모듈), `go.work`의 해당 멤버 라인 제거.
- `plugins/core-dev/.mcp.json`의 `jira-gateway` 서버 블록 전체 삭제(`command`, `args`,
  `env.{JIRA_BASE_URL,JIRA_API_TOKEN,JIRA_USER_EMAIL,PATTERNS_PATH}` 포함).
- `scripts/setup.py`의 `REQUIRED`에서 `JIRA_GATEWAY_BIN`/`JIRA_BASE_URL`/`JIRA_USER_EMAIL`/
  `JIRA_API_TOKEN` 4개 제거, `_detect()`의 `JIRA_GATEWAY_BIN` 자동탐지 블록 제거,
  `AUTONOMOUS_ALLOW`의 `mcp__plugin_core-dev_jira-gateway__*` 제거.
- `scripts/doctor.py`의 `SECRETS`/`ENV_KEYS`에서 `JIRA_BASE_URL`/`JIRA_USER_EMAIL`/`JIRA_API_TOKEN` 제거.
- `scripts/contract/agent-mcp.schema.json`의 `jira-gateway` provider 블록 제거(이 스키마는 이 리포가
  **직접 소유한** MCP 서버의 도구 계약 SSoT다 — 외부 플러그인인 공식 Atlassian MCP의 도구는 이 리포가
  계약을 정의할 대상이 아니므로, 빈 자리를 대체 없이 그냥 제거한다).
- 각 command/agent frontmatter의 `mcp__plugin_core-dev_jira-gateway__*` grant 제거
  (`orchestrator.md`, `analyze.md`, `work.md`, `doctor.md`).

### 2.2 무엇으로 대체한다

- **도구 매핑**:
  - `jira_read_ticket(ticket_id)` → `getJiraIssue(cloudId, issueIdOrKey, responseContentFormat: "markdown")`
    — `responseContentFormat: "markdown"`을 요청하면 `jira-gateway`가 직접 구현했던 ADF→Markdown 변환
    (`docs/OVERVIEW.md`의 "ADF→Markdown 자체 구현" 결정 로그 행)이 통째로 불필요해진다 —
    `template-parse` skill §8의 "Jira Gateway가 markdown으로 변환해서 넘겨준다"는 전제는 그대로 유지된다,
    변환 주체만 바뀔 뿐.
  - `jira_search(jql, max_results)` → `searchJiraIssuesUsingJql(cloudId, jql, maxResults, nextPageToken?)`.
  - `jira_add_comment(ticket_id, body)` → `addCommentToJiraIssue(cloudId, issueIdOrKey, commentBody)`.
  - `jira_update_status(ticket_id, target)` → `getTransitionsForJiraIssue(cloudId, issueIdOrKey)`로 후보를
    받은 뒤, **`jira-gateway`가 하던 것과 동일한 3-tier 매칭**(전이명 → 목표상태명 → statusCategory key,
    대소문자 무시, 순서대로 시도)을 호출부에서 재현하고 `transitionJiraIssue(cloudId, issueIdOrKey,
    transition:{id})`를 호출한다. `orchestrator.md`와 `merge.md` 양쪽에서 쓰이므로, 매칭 로직은
    한 곳(신규 skill, 예: `core-dev:jira-status-transition`)에 두고 두 호출부가 공유한다 — 로직을
    두 프롬프트 파일에 중복 기술하지 않는다.
- **cloudId 해석**: 세션(또는 파이프라인 실행) 시작 시 `getAccessibleAtlassianResources`를 한 번 호출해
  캐시한다. 접근 가능한 사이트가 1개면 자동 선택. 여러 개면, `setup.py`에 선택적
  `ATLASSIAN_CLOUD_ID`(PUBLIC) 엔트리를 추가해 고정하거나, 최초 호출 시 사용자에게 물어본다 —
  `JIRA_BASE_URL`이 하던 "이 리포는 항상 이 사이트를 쓴다"는 고정 역할의 대체.
- **권한**: 위 4개 command/agent의 `allowed-tools`/`tools:` frontmatter에
  `mcp__plugin_atlassian_atlassian__*`를 추가한다. 단 이건 이 리포가 등록하는 서버가 아니라 사용자가
  개인적으로 설치한 외부 플러그인의 네임스페이스이므로, **`docs/SETUP.md`에 새 필수 전제조건**으로
  "공식 Atlassian MCP 플러그인을 설치·인증해야 한다"를 명시한다(§1.1의 "리포 밖 소프트 디펜던시" 경고).

### 2.3 ADR-0006 인바운드 절 개정 — 필터링 공백을 감수한다

ADR-0006의 인바운드 절(§2의 "Inbound" 문단)을 이 ADR로 **개정(supersede, 인바운드에 한정)**한다.
`jira-gateway`가 없어지면서, Jira 티켓/댓글 내용에 대한 **서버단 사전 필터링(REDACT/BLOCK)이 완전히
사라진다** — 공식 MCP의 읽기 도구는 원본을 그대로 반환하고, 어떤 스캔도 거치지 않는다.

대안으로 "공식 MCP 앞단에 얇은 래퍼를 세워 `sensitive-guard` 필터를 그대로 적용"하는 방안도 검토했으나
**기각**했다 — 그 래퍼 자체가 곧 유지보수해야 할 커스텀 프록시이고, 이번 결정의 동기(자체 서버 유지보수
중단)를 그대로 무력화하기 때문이다. Skill 기반 사후 스크러빙도 ADR-0006 §1이 이미 기각한 접근과
동일한 이유로 채택하지 않는다(스킬이 개입하는 시점엔 이미 LLM 컨텍스트에 원본이 들어온 뒤다).

- **아웃바운드는 변경 없음**: `pr-sanitize` skill은 `jira-gateway`와 무관하게 독립적으로
  `packages/sensitive-guard/patterns.json`을 직접 읽어왔다(§1.1 조사로 확인) — PR body·squash commit
  body·Jira 댓글 게시 전 스크럽은 그대로 유지된다.
- **잔여 리스크**: 티켓 본문/댓글에 실수로 포함된 시크릿이 이제 LLM 컨텍스트에 그대로 노출될 수 있다
  (단, 그것이 PR/커밋/Jira 댓글로 **재게시**되는 것은 여전히 `pr-sanitize`가 막는다 — "본 적 없는
  정보는 유출할 수 없다"는 보장에서 "본 것을 다시 내보내지는 않는다"는 보장으로 후퇴). 이 리스크는
  이제 조직의 Jira 사용 규율(티켓에 시크릿을 적지 않기)에 의존한다.
- 사용자가 이 트레이드오프를 명시적으로 확인하고 감수하기로 결정했다(2026-08-04 대화).

### 2.4 이관하지 않는 것

- `jira_update_assignee`: 리포 어디에도 실제 호출부가 없다(Planner에서 명시적으로 금지). 필요해지면
  `lookupJiraAccountId` + `editJiraIssue(fields:{assignee})`로 그때 추가한다.
- `jira_read_comments`: 직접 호출부 없음. 필요해지면 `getJiraIssue(fields:["comment"])`로 대체 가능—
  단 `since` 기반 증분 조회와 댓글별 개별 필터링은 대응 도구가 없다(§1.1).

---

## 3. Consequences (결과)

- **+**: 유지보수 대상 Go 서비스(`packages/jira-gateway-mcp/`) 전체 제거 — 빌드·테스트·CI 부담 감소.
- **+**: 공식 MCP가 제공하는 부가 기능 확보(페이지네이션, 댓글 편집, 다중 사이트 지원 등) —
  `jira-gateway`엔 없던 능력.
- **+**: `template-parse` skill이 전제했던 자체 ADF→Markdown 변환 부담이 사라진다
  (`responseContentFormat: "markdown"`으로 대체).
- **−**: ADR-0006이 보장하던 인바운드 서버단 필터링을 잃는다(§2.3) — 의도적으로 감수한 트레이드오프.
- **−**: `core-dev`가 이 리포 밖의, 사용자별로 설치 상태가 다를 수 있는 외부 마켓플레이스 플러그인에
  소프트 의존하게 된다 — 표준 설치 절차만으로는 채워지지 않는다.
- **−**: `jira_update_status`의 3-tier 퍼지 매칭 로직을 새로 구현·테스트해야 한다(현재 리포에 없음).
- **후속**:
  1. 이 ADR 승인 후 실제 코드 마이그레이션 — 별도 PR(들).
  2. `docs/SETUP.md`/`OVERVIEW.md`/`VISION.md`/`README.md`/`docs/adr/README.md`/`docs/DOC-MAP.md` 갱신,
     ADR-0006 상태를 "Partially superseded by ADR-0013 (인바운드만)"로 표시.
  3. `ADR-0009` §"jira-gateway 재사용을 전제로 유보" 문구가 이 ADR로 무효화됐음을 그 문서에도 짧게 남길지
     검토(현재는 `contract-dev`가 Jira 통합을 아예 보류 중이라 급하지 않음).
