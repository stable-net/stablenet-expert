# Architecture Decision Records (ADR)

> **Tier 2.** 하나의 결정 = 하나의 ADR. 결정이 바뀌면 **새 ADR**를 만들고 옛 ADR을
> `Superseded by ADR-NNNN`으로 표시한다(삭제하지 않는다).

## 인덱스

| ADR | 제목 | 상태 | 구현 검증 (코드 근거) |
|---|---|---|---|
| [ADR-0001](ADR-0001-domain-pack-contract.md) | Domain-Pack Contract (멀티프로젝트 확장) | Accepted (2026-06-22) | 구현됨 — `plugins/core-dev/domains/go-stablenet/`(domain-pack.json·context.md·invariants.md) 존재 |
| [ADR-0002](ADR-0002-setup-and-doctor.md) | `/coding-agent:setup` 확장 + `/coding-agent:doctor` | Accepted (2026-06-23) | 구현됨 — `plugins/core-dev/commands/{setup,doctor}.md`, PR #22·#23 머지 (v0.1.30) |
| [ADR-0003](ADR-0003-reproduction-and-fix-validity.md) | Reproduction vs Fix-Validity 분리 + 2-티어 재현 | Accepted (2026-06-23) | 구현·머지 — PR #18 (v0.1.25). 라이브 무회귀 잔여(§6) |
| [ADR-0004](ADR-0004-doctor-remediation-routing.md) | doctor→setup remediation routing + single-source fix table | Accepted (2026-06-26) | 구현됨 — PR #31·#33, `plugins/core-dev/scripts/doctor.py` REMEDIATION 테이블 |
| [ADR-0005](ADR-0005-stablenet-expert-marketplace-split.md) | stablenet-expert 마켓플레이스 분리 + core-dev/cq 경계 | Accepted (2026-07-20) | 구현됨 — `stablenet-expert` 리포로 이관 완료(§2.1/2.2/2.4). §2.3(cq 분리)은 재검토 후 철회. §5 dapp 로드맵 제외 반영 (4-카테고리로 축소) |
| [ADR-0006](ADR-0006-proxy-mcp-gateway-security-model.md) | Proxy MCP Gateway 보안 모델 (양방향 민감정보 필터링) | Accepted (historical, 2026-07-21 추출) | 구현됨 — `packages/jira-gateway-mcp/internal/filter/`, `pr-sanitize` skill |
| [ADR-0007](ADR-0007-bc-hybrid-harness-architecture.md) | B+C 하이브리드 하네스 아키텍처 (문서 기반 상태 머신 + 격리 멀티에이전트) | Accepted (historical, 2026-07-21 추출) | 구현됨 — `state-machine` skill, `orchestrator/planner/implementer/evaluator` agents |
| [ADR-0008](ADR-0008-new-plugin-scaffolding-contract.md) | 신규 플러그인 스캐폴딩 계약 + `packages/` vs `plugins/<name>/` 경계 | Accepted (2026-07-29) | 부분 구현 — lint/CI 자동 탐색은 반영됨, 체크리스트·경계 기준은 플러그인 #2 착수 전까지 미검증 |
| [ADR-0009](ADR-0009-contract-dev-plugin-design.md) | `contract-dev` 플러그인 설계 (1단계: go-stablenet 내장 systemcontracts/) | Accepted (2026-07-31) | 설계만 — `compact-core`형 구조(MCP 서버 없음, skills+리뷰/감사 에이전트) 결정, 실제 스캐폴딩은 별도 작업 |

의존 관계: ADR-0001 ← ADR-0002 ← ADR-0004 (도메인팩 → setup/doctor → remediation 라우팅).
ADR-0005는 ADR-0001(도메인팩)을 전제로 한다. ADR-0006·ADR-0007은 독립이며, `HANDOFF.md`(2026-06-05
스냅샷, 삭제됨)에 있던 설계 근거 중 재사용 가치가 있는 부분을 승격한 것이다. ADR-0008은 ADR-0005를
전제로 하며(마켓플레이스 분리가 먼저 결정돼야 "새 플러그인 만드는 법"이 의미가 있음), WORKLIST §B의
멀티플러그인 확장성 항목들을 해소한다. ADR-0009는 ADR-0005 §2.4(contract-dev 범위)와 ADR-0008(신규
플러그인 체크리스트)을 전제로 하며, WORKLIST §B 검증 중 실증된 MCP 서버 이중 등록 충돌(ADR-0008
§2.2의 첫 실제 사례)을 근거로 MCP 서버를 아예 두지 않기로 결정했다.
ADR-0003은 독립이며, 검증 절차는 [`../reproduction-verification-runbook-2026-06-23.md`](../reproduction-verification-runbook-2026-06-23.md).

> 비고: 이 ADR들은 각각 단일 토픽을 둘러싼 **응집된 결정 묶음**(보통 결정 4건)으로 작성돼 있어,
> 1결정=1ADR로 분할하지 않고 묶음 단위로 보존했다(문서 proliferation 방지).

---

## 새 ADR 템플릿

```markdown
# ADR-NNNN — <결정 제목>

문서 성격: **ADR / 설계 결정 (<Proposed|Accepted|Superseded> YYYY-MM-DD).**
짝 문서: <관련 코드/문서 링크>

> **결정 한 줄:** <무엇을 왜 이렇게 정했는가>
> **상태:** <Accepted (구현 반영됨) | Proposed | Superseded by ADR-MMMM (이유)>

## 1. Context (왜)
<문제·배경. 코드 근거 cite>

## 2. Decision (무엇)
<결정 내용. 하나의 결정. 대안과 trade-off>

## 3. Consequences (결과)
<긍정·부정 영향, 후속 작업, 검증 방법>
```
