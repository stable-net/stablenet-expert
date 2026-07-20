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
| [OVERVIEW.md](OVERVIEW.md) | 아키텍처 개요 | coding-agent·cks·Claude Code 관계, 동작 흐름, MCP 3종 |
| [system-contract.md](system-contract.md) | 시스템 계약 (SSoT) | 5개 저장소 통합 계약 C1–C5, binary=deterministic 원칙 (R1' 00에서 승격) |
| [SETUP.md](SETUP.md) | 설치 레퍼런스 | 빌드·env·Ollama·인덱스·smoke test·트러블슈팅 |
| [agent-architecture-and-plugin-guide.md](agent-architecture-and-plugin-guide.md) | 아키텍처 레퍼런스 | Claude Code query 루프 + 6-요소 플러그인 계약 |
| [bench-abc-mode-definitions.md](bench-abc-mode-definitions.md) | 벤치 계약 | A/B/C 3-way regime 정의·공정성 규칙·측정 축 |
| [design/continuous-learning-loop.md](design/continuous-learning-loop.md) | 미래 설계 (DESIGN ONLY) | 폐루프 지식 캡처. **미구현**(구현 스킬 없음 — 코드 확인) |
| [templates/refactor-plan-template.md](templates/refactor-plan-template.md) | 프로세스 템플릿 | per-repo 리팩터 플랜 템플릿(교차모듈 결함 방지) |
| [adr/README.md](adr/README.md) | ADR 인덱스 | 아래 ADR 목록 + 템플릿 |

### ADR (`adr/`)

| ADR | 제목 | 상태 |
|---|---|---|
| [ADR-0001](adr/ADR-0001-domain-pack-contract.md) | Domain-Pack Contract | Accepted · 구현됨 |
| [ADR-0002](adr/ADR-0002-setup-and-doctor.md) | setup 확장 + doctor | Accepted · 구현됨 (v0.1.30) |
| [ADR-0003](adr/ADR-0003-reproduction-and-fix-validity.md) | Reproduction vs Fix-Validity + 2-티어 재현 | Accepted · 구현됨 (v0.1.25), 라이브 무회귀 잔여 |
| [ADR-0004](adr/ADR-0004-doctor-remediation-routing.md) | doctor→setup remediation routing | Accepted · 구현됨 |
| [ADR-0005](adr/ADR-0005-stablenet-expert-marketplace-split.md) | stablenet-expert 마켓플레이스 분리 + core-dev/cq 경계 | Accepted · 구현됨 (§2.3 cq 분리는 철회) |

## Tier 3 — 상태 / 잔여작업 (살아있는 backlog)

| 문서 | 상태 | 비고 |
|---|---|---|
| [WORKLIST.md](WORKLIST.md) | **활성 SSoT** | 6개 워크스트림 통합 백로그. 잔여작업의 단일 기준점 |
| [cks-ckg-ckv-hardening-backlog-2026-06-19.md](cks-ckg-ckv-hardening-backlog-2026-06-19.md) | 활성 | A1·A2·B1 머지, B3–B5·확장 API 미착수 |
| [graph-reasoning-gap-and-fix-plan-2026-06-19.md](graph-reasoning-gap-and-fix-plan-2026-06-19.md) | 활성 | P0 흡수(analyzer), P1.5·P2·P3 잔존 |
| [rag-context-efficiency-proposals-2026-06-19.md](rag-context-efficiency-proposals-2026-06-19.md) | 활성 | 3.1·2.2·4.1 머지(#38·#40); 2.1 캐시 홀드; 2.3/2.4/3.2/3.3 잔여 |
| [harness-improvement-proposals-2026-06-17.md](harness-improvement-proposals-2026-06-17.md) | 활성 | 제안 1~3(git-guard·Stop·SessionStart) 머지(#41); 4~7 잔여 |
| [reproduction-verification-runbook-2026-06-23.md](reproduction-verification-runbook-2026-06-23.md) | 재사용 절차 | ADR-0003 라이브 검증 프로토콜 |
| [coordination-response-coding-agent-2026-06-29.md](coordination-response-coding-agent-2026-06-29.md) | 협의 스냅샷 | CKV §3 회신 — cks 도구 계약·bench·flow/invariant parity 갭·임베딩 A/B(Phase 2) |
| [HANDOFF-phase2-pr77-2026-07-03.md](HANDOFF-phase2-pr77-2026-07-03.md) | 핸드오프 (활성) | Phase 2 착수 대기 — cks/ckv 재인덱싱 의존·PR-77 통합 bench 절차·다른 머신 재개. **07-05 상단 STATUS: 선행 의존 해소, T-2 완료** |
| [coordination-outbound-2026-07-05.md](coordination-outbound-2026-07-05.md) | 발신 문안 | D-5 답 relay(→CKG, P3 종결 역질문) + flow/invariant 4종 완료출하·커버리지·inv_id 질문(→CKS/CKV) |

## 아카이브 (`archive/`) — 완료·superseded (이력 보존, 삭제 금지)

| 묶음 | 문서 | 사유 |
|---|---|---|
| 완료된 status/handoff | `followup-status-2026-06-15`, `remaining-work-detail`, `HANDOFF-2026-06-19-cks-ab-index`, `HANDOFF-bench-harness`, `p1-phase2b-3-plan-2026-06-23` | WORKLIST가 대체 / 머지 완료 / 머신종속 |
| 완료된 eval/분석 | `abc-3way-gastip-eval-2026-06-23`, `query-core-agent-evaluation-2026-06-19`, `knowledge-system-analysis-2026-06-17`, `coding-agent-overlay-improvements-and-eval-2026-06-22`, `test/pr-77/pr77-gastip-pipeline-fidelity-analysis-2026-06-24` | dated 스냅샷, 결론은 ADR/backlog로 흡수 |
| 초기 후속계획 (thesis 출처) | `followup-plan`, `followup-expected-outcomes` | VISION.md로 thesis·G1/G2 추출 완료 |
| R1' 완료 사이클 | `r1-refactor/01–10`, `r1-refactor/plans/01–05` | 9 PR 머지 완료. 계약은 `system-contract.md`로 승격, 템플릿은 `templates/`로 |
| 원래 v1 빌드 사이클 | `v1-build/plan/*` (12), `v1-build/specs/*` (8) | Phase 1–7 빌드 완료. 코드가 진실, 설계 근거는 OVERVIEW/system-contract가 대체 |
