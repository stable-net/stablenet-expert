# ADR-0006 — Proxy MCP Gateway 보안 모델 (양방향 민감정보 필터링)

문서 성격: **ADR / 설계 결정 (Accepted — historical, `HANDOFF.md` 2026-06-05 스냅샷 §3.3·§5에서 추출·승격).**
짝 문서: [`packages/jira-gateway-mcp/internal/filter/`](../../packages/jira-gateway-mcp/internal/filter/) ·
[`packages/sensitive-guard/patterns.json`](../../packages/sensitive-guard/patterns.json) ·
[`plugins/core-dev/skills/pr-sanitize/SKILL.md`](../../plugins/core-dev/skills/pr-sanitize/SKILL.md) ·
[OVERVIEW.md §5](../OVERVIEW.md)의 "보안은 양방향 대칭" 콜아웃.

> **결정 한 줄:** 민감정보(시크릿·사내정보)는 **MCP 서버 레벨**에서, LLM에 도달하기 *전에* 정규식+엔트로피
> 검사로 REDACT/BLOCK한다. Skill(=LLM이 보고 나서 판단하는 방식)로는 처리하지 않는다.
> **상태:** Accepted (구현 반영됨 — `packages/jira-gateway-mcp`, `pr-sanitize` skill 모두 존재)

## 1. Context (왜)

초기에는 "sensitive-check skill"로 LLM이 민감정보를 보고 스스로 판단해 거르는 방식을 검토했다.
그러나 이 방식은 skill이 개입하는 시점 자체가 이미 **LLM 컨텍스트에 정보가 들어온 뒤**이므로,
"차단"이 성립하지 않는다 — 노출은 이미 일어난 상태다. 이 문제를 지적받아 방향을 바꿨다.

## 2. Decision (무엇)

- **Inbound**: Jira description/comments 등 외부 데이터는 `packages/jira-gateway-mcp/internal/filter`가
  정규식 + 엔트로피 + 화이트리스트로 스캔해 REDACTED/BLOCKED 결정을 내린 뒤, **sanitized 텍스트만**
  MCP 응답으로 LLM에 노출한다. 판정 로직은 LLM 호출 없이 결정론적으로 동작한다.
- **Outbound도 대칭 처리**: PR body·squash commit body·Jira 댓글처럼 LLM이 만들어 외부로 내보내는
  텍스트도, `plugins/core-dev/skills/pr-sanitize/SKILL.md`가 같은 `packages/sensitive-guard/patterns.json`을
  적용해 게시 전에 스크럽한다.
- 두 방향이 **같은 patterns.json을 SSoT로 공유**한다 — 탐지 정책이 입력/출력에서 갈라지지 않도록.

## 3. Consequences (결과)

- **+**: "본 적 없는 정보는 유출할 수 없다"는 구조적 보장 — 필터가 스킵되거나 프롬프트에 의존하는
  실패 모드가 없다(MCP 서버가 강제하므로 우회 불가).
- **+**: 탐지 로직이 Go 코드(결정론)라 테스트 가능하고, LLM의 판단 편차에 영향받지 않는다.
- **−/제약**: 새 민감정보 패턴이 필요할 때마다 `patterns.json`을 갱신해야 한다(LLM이 즉석에서
  "이건 민감해 보이니 가리자"라고 판단할 수 없다 — 이건 의도된 트레이드오프다: 판단 없는 결정론이
  판단하는 비결정론보다 안전).
- 후속: 커스텀 패턴 병합(`CUSTOM_PATTERNS_PATH`), outbound 경로 확장 시에도 이 패턴을 그대로 재사용.
