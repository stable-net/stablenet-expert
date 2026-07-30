# ADR-0007 — B+C 하이브리드 하네스 아키텍처 (문서 기반 상태 머신 + 격리 멀티에이전트)

문서 성격: **ADR / 설계 결정 (Accepted — historical, `HANDOFF.md` 2026-06-05 스냅샷 §3.2·§5에서 추출·승격).**
짝 문서: [`plugins/core-dev/skills/state-machine/SKILL.md`](../../plugins/core-dev/skills/state-machine/SKILL.md) ·
[`plugins/core-dev/agents/{orchestrator,planner,implementer,evaluator}.md`](../../plugins/core-dev/agents/) ·
[OVERVIEW.md §4](../OVERVIEW.md)의 "두 개의 기둥 — 기둥 A: 하네스".

> **결정 한 줄:** 후보 아키텍처 중 **B(문서 기반 상태 머신) + C(격리 멀티에이전트) 하이브리드**를 채택한다.
> 상태는 파일(state.json + `*.md` 산출물)로 영속화하고, 실행은 4개의 컨텍스트-격리 에이전트
> (orchestrator/planner/implementer/evaluator)로 나눈다.
> **상태:** Accepted (구현 반영됨 — OVERVIEW.md §4 기둥 A로 상시 문서화)

## 1. Context (왜)

검토한 후보:
- **A (단일 LLM, 상태 없음)**: 컨텍스트가 길어지거나 세션이 끊기면 처음부터 다시 시작해야 한다.
- **B-only (문서 기반 상태 머신, 단일 에이전트)**: 상태는 복원 가능하지만, 각 단계(분석/설계/구현/검증)의
  책임이 한 컨텍스트에 뒤섞여 LLM 호출을 단계별로 분리하기 어렵다.
- **C-only (멀티에이전트, 상태 없음)**: 단계별 책임은 깔끔히 나뉘지만, 컨텍스트가 끊기면 지금까지의
  진행을 복원할 방법이 없다 — 처음부터 재시작.

**B+C 하이브리드**을 선택: 상태는 파일에, 실행은 에이전트에 분리하면 두 문제를 동시에 해결한다.

## 2. Decision (무엇)

- **B — 문서 기반 상태 머신**: `ANALYSIS→analysis.md`, `PLANNING→plan.md`, `DESIGN→design-v{N}.md`,
  `EVALUATION→test-report.md`, 전 단계 상태는 `state.json`. 세션이 끊겨도 다음 세션이 파일에서
  정확히 이어받는다(resumable). 복구 로직은 `state-machine` skill의 `get_resume_point`가 담당한다.
- **C — 격리 멀티에이전트**: orchestrator(상태 전이 디스패치, 유일하게 전체 흐름을 봄) / planner
  (분석+설계, stablenet-knowledge 검색 소비) / implementer(구현, step당 1커밋) / evaluator(4단계 검증)로
  역할을 나눈다. 각 에이전트는 자기 컨텍스트만 본다.
- **관련 하위 결정 — commit 분할(atomic/reviewable/verifiable)**: planner가 step을 단일 책임 단위로
  쪼개고 implementer가 step당 1커밋을 만든다. 이는 B(상태 복원)와 C(단계 책임 분리) 양쪽을 함께
  지원한다 — 커밋 경계가 곧 복원 지점이자 리뷰 단위다.
- **관련 하위 결정 — implementer→evaluator binary 핸드오프**: 자체 빌드 시 stale tree 위험이 있으므로
  implementer가 `build/bin/gstable`을 만들고 `state.json`에 커밋 해시를 기록, evaluator는 커밋이
  일치하면 그 바이너리를 재사용하고 아니면 fallback 빌드한다. 이는 에이전트 간 격리(C)를 유지하면서도
  중복 빌드 비용을 없애는 절충이다.

## 3. Consequences (결과)

- **+**: 컨텍스트가 언제 끊겨도(모델 전환, 세션 재시작) 작업 손실이 없다 — 파일이 진실의 소스.
- **+**: 각 에이전트가 좁은 책임만 지므로 프롬프트가 짧고 판단이 흔들리지 않는다. orchestrator만
  전체 그림을 보므로 상태 전이 로직이 한 곳에 모인다.
- **−/제약**: 상태 파일 스키마가 바뀌면 마이그레이션 로직이 없다 — 큰 변경 전 사용자 확인이 필요하다
  (이 제약은 뒤집지 않는다).
- **−/제약**: 에이전트 간 통신이 파일 I/O를 경유하므로, 파일 쓰기 타이밍/락 문제가 생기면 상태 불일치
  위험이 있다(현재는 단일 세션 순차 실행 가정으로 미해당).
