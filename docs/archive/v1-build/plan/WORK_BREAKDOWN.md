# Coding Agent - Work Breakdown

> Phase 설계 문서 기반 전체 작업 목록.
> 각 작업의 출처(Phase), 유형, buddy 재사용 여부, 구현 상세를 명시.
> Phase별 상세는 하위 파일 참조.

## 작업 유형

| 유형 | 의미 |
|------|------|
| `NEW` | 새로 작성. 기존 코드/스킬 없음 |
| `ADAPT` | buddy 스킬의 PROCEDURE.md를 coding-agent 맥락에 맞게 적응 |
| `INFRA` | 프로젝트 설정, 디렉토리 구조, 설정 파일 |

## 난이도

| 등급 | 의미 | 예상 작업량 |
|------|------|-----------|
| `S` | 단순 파일 생성/설정 | < 1시간 |
| `M` | 로직 있는 단일 컴포넌트 | 1-4시간 |
| `L` | 여러 컴포넌트 연동, 외부 의존 | 4-8시간 |
| `XL` | 복잡한 시스템 구축 | 1-3일 |

---

## Phase별 상세

| Phase | 파일 | 작업 수 | 핵심 산출물 |
|-------|------|---------|-----------|
| [Phase 1](phase1-tasks.md) | Plugin Skeleton + State Machine | 10 | plugin/.claude-plugin/plugin.json, commands, skills, state.json 관리 |
| [Phase 2](phase2-tasks.md) | Jira Gateway MCP + Sensitive Filter | 7 | MCP 프록시 서버, 패턴 매칭 엔진 |
| [Phase 3](phase3-tasks.md) | CKS MCP - CKV Vector Search | 10 | Go AST 청커, 임베딩, 벡터 검색 |
| [Phase 4](phase4-tasks.md) | CKS MCP - CKG Graph Search | 9 | 관계 추출, 동시성 분석, 그래프 탐색 |
| [Phase 5](phase5-tasks.md) | Agent Pipeline | 9 | Orchestrator, Planner, Implementer 에이전트 |
| [Phase 6](phase6-tasks.md) | Evaluator + ChainBench | 7 | 4-stage 검증 파이프라인 |
| [Phase 7](phase7-tasks.md) | PR + Review Cycle | 7 | PR 자동화, 리뷰 반영, squash merge |
| [공통](common-tasks.md) | 공통/인프라 | 4 | patterns.json, 폴더 유틸, safeguard, 로깅 |

## 작업 통계

| Phase | NEW | ADAPT | INFRA | 합계 |
|-------|-----|-------|-------|------|
| Phase 1 | 6 | 0 | 3 | 9 |
| Phase 2 | 7 | 0 | 0 | 7 |
| Phase 3 | 9 | 1 | 0 | 10 |
| Phase 4 | 9 | 0 | 0 | 9 |
| Phase 5 | 3 | 5 | 0 | 8 |
| Phase 6 | 3 | 4 | 0 | 7 |
| Phase 7 | 2 | 4 | 0 | 6 |
| 공통 | 2 | 1 | 0 | 3 |
| **합계** | **41** | **15** | **3** | **59** |

## 의존 관계

```
Phase 1 ─┬─→ Phase 2 ─────────────────┐
         │                              │
         ├─→ Phase 3 ─┐                │
         │             ├─→ Phase 5 ─→ Phase 6 ─→ Phase 7
         └─→ Phase 4 ─┘                │
                                        │
         COMMON ─── (각 Phase에서 필요 시) ┘
```

## 설계 문서 참조

- [전체 시스템 설계](../superpowers/specs/2026-05-27-coding-agent-plugin-design.md)
- [Phase 1 설계](../superpowers/specs/phase1-plugin-skeleton-state-machine.md)
- [Phase 2 설계](../superpowers/specs/phase2-jira-gateway-mcp-sensitive-filter.md)
- [Phase 3 설계](../superpowers/specs/phase3-cks-mcp-ckv.md)
- [Phase 4 설계](../superpowers/specs/phase4-cks-mcp-ckg.md)
- [Phase 5 설계](../superpowers/specs/phase5-agent-pipeline.md)
- [Phase 6 설계](../superpowers/specs/phase6-evaluator-chainbench.md)
- [Phase 7 설계](../superpowers/specs/phase7-pr-review-cycle.md)
