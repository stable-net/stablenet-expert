# DOC-MAP — 문서 인덱스 (3-tier)

> 모든 문서를 tier로 분류한 단일 인덱스. 문서를 추가·이동·supersede할 때 **이 파일도 같은 변경에서 갱신**한다.
>
> - **Tier 1 — 목적/비전**: 왜 존재하는가. Append-mostly, 정리의 읽기 전용 입력.
> - **Tier 2 — 설계/계약/ADR**: 어떻게·왜 결정했는가. Supersede(삭제 금지).
> - **Tier 3 — 상태/잔여작업**: dated·disposable, 코드+git에서 재생성 가능.

마지막 정리: 2026-06-28 (`/coding-agent:doc-organize`, 브랜치 `docs/3-tier-reorg`).

---

## Tier 1 — 목적/비전

| 문서 | 내용 |
|---|---|
| [VISION.md](VISION.md) | 프로젝트 목적·목표(G1/G2)·핵심 thesis·상태전이 vision·설계 신념 |

## Tier 2 — 설계 / 계약 / 레퍼런스 (살아있음)

| 문서 | 종류 | 내용 |
|---|---|---|
| [OVERVIEW.md](OVERVIEW.md) | 아키텍처 개요 | coding-agent·stablenet-knowledge·Claude Code 관계, 동작 흐름, MCP 3종 |
| [SETUP.md](SETUP.md) | 설치 레퍼런스 | 빌드·env·Ollama·인덱스·smoke test·트러블슈팅 |
| [agent-architecture-and-plugin-guide.md](agent-architecture-and-plugin-guide.md) | 아키텍처 레퍼런스 | Claude Code query 루프 + 6-요소 플러그인 계약 |
| [bench-abc-mode-definitions.md](bench-abc-mode-definitions.md) | 벤치 계약 | A/B/C 3-way regime 정의·공정성 규칙·측정 축 |
| [adr/README.md](adr/README.md) | ADR 인덱스 | 아래 ADR 목록 + 템플릿 |

### ADR (`adr/`)

| ADR | 제목 | 상태 |
|---|---|---|
| [ADR-0001](adr/ADR-0001-domain-pack-contract.md) | Domain-Pack Contract | Accepted · 구현됨 |
| [ADR-0002](adr/ADR-0002-setup-and-doctor.md) | setup 확장 + doctor | Accepted · 구현됨 (v0.1.30) |
| [ADR-0003](adr/ADR-0003-reproduction-and-fix-validity.md) | Reproduction vs Fix-Validity + 2-티어 재현 | Accepted · 구현됨 (v0.1.25), 라이브 무회귀 잔여 |
| [ADR-0004](adr/ADR-0004-doctor-remediation-routing.md) | doctor→setup remediation routing | Accepted · 구현됨 |
| [ADR-0005](adr/ADR-0005-stablenet-expert-marketplace-split.md) | stablenet-expert 마켓플레이스 분리 + core-dev/cq 경계 | Accepted · 구현됨 (§2.3 cq 분리는 철회) |
| [ADR-0006](adr/ADR-0006-proxy-mcp-gateway-security-model.md) | Proxy MCP Gateway 보안 모델 | Accepted · 구현됨 (HANDOFF.md에서 추출) |
| [ADR-0007](adr/ADR-0007-bc-hybrid-harness-architecture.md) | B+C 하이브리드 하네스 아키텍처 | Accepted · 구현됨 (HANDOFF.md에서 추출) |
| [ADR-0008](adr/ADR-0008-new-plugin-scaffolding-contract.md) | 신규 플러그인 스캐폴딩 계약 + packages/plugins 경계 | Accepted · 부분 구현 (체크리스트는 플러그인 #2 착수 전까지 미검증) |
| [ADR-0009](adr/ADR-0009-contract-dev-plugin-design.md) | contract-dev 플러그인 설계 (1단계: go-stablenet 내장 systemcontracts/) | Accepted · 설계만 (스캐폴딩 미착수) |
| [ADR-0010](adr/ADR-0010-stablenet-expert-meta-plugin-design.md) | stablenet-expert 메타 플러그인 설계 (1단계: doctor만) | Accepted · 구현됨 (PR #12, 라이브 검증 완료) |
| [ADR-0011](adr/ADR-0011-stablenet-expert-doctor-interactive-setup.md) | stablenet-expert:doctor 2단계 (대화형 수정 + 플러그인별 setup 위임) | Accepted · 설계만 (구현 미착수) |

## Tier 3 — 상태 / 잔여작업

| 문서 | 내용 |
|---|---|
| [WORKLIST.md](WORKLIST.md) | 현재 시점 잔여 작업 체크리스트(dated 이력 아님 — 완료 시 항목 삭제) |
