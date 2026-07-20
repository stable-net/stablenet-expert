# VISION — coding-agent

> **Tier 1 (purpose/vision).** 이 문서는 *왜 이 프로젝트가 존재하는가*를 담는다.
> Append-mostly: 정리·아카이브 작업의 **읽기 전용 입력**이며, 줄어들거나 삭제되지 않는다.
> 아키텍처 설명은 [OVERVIEW.md](OVERVIEW.md), 시스템 계약은 [system-contract.md](system-contract.md)를 본다.

---

## 1. 한 문장

**coding-agent**는 하네스 엔지니어링(상태 머신 + 격리 에이전트 + 파일 산출물 + 결정론 백엔드)
위에서, **cks를 통한 Retrieval(RAG)** 로 코드베이스를 근거 있게 이해하고, 유저 요구사항(Jira
티켓 등)을 **분석 → 설계 → 구현 → 테스트 → PR**까지 자율 수행하는 다중 에이전트다.
(출처: [OVERVIEW.md](OVERVIEW.md) §1)

## 2. 목표 (왜)

`system-contract`가 규정하는 두 목표 — (출처: `archive/followup-plan.md:127`)

- **G1 — 정확성·효율**: go-stablenet 구현을 더 정확하고 효율적으로 한다.
- **G2 — 절감**: 시간·토큰·인력을 절감한다.

## 3. 핵심 thesis (증명 대상)

> **"cks 검색이 grep보다 정확하고 저렴한가?"** — 프로젝트의 존재 이유를 좌우하는 핵심 질문이며,
> 현재 **미증명**이다(이전 N=1 측정은 FakeEmbedder 등으로 confounded).
> (출처: `archive/followup-plan.md:128`, `:83`, `:152`)

thesis는 두 층위로 구분된다 — (출처: `archive/followup-plan.md:86`, `archive/followup-expected-outcomes.md:30-31`)

- **retrieval-thesis** (검색 레벨 α=grep / β·γ·δ=cks 비교): 대폭 측정 진행됨.
- **full-pipeline-thesis** (implement + chainbench까지 포함한 전체 A/B/C): **여전히 미실행**,
  chainbench e2e 회귀 환경(C)에 의존. 측정 harness는 `/coding-agent:bench`.

> thesis가 **반증**될 수도 있다("cks가 grep 대비 이득 없음"). 그 경우도 실패가 아니라
> **의사결정 데이터**다. (출처: `archive/followup-expected-outcomes.md:70`, `:113`)

## 4. 상태 전이 vision (Before → After)

이 프로젝트가 옮겨가려는 상태 — (출처: `archive/followup-expected-outcomes.md:122`,
`archive/followup-plan.md:162`)

> *"동작하지만 미검증"* → *"검증 가능하고 안전하며, 그리고 가치가 측정된"* 상태.

## 5. 설계 신념 (불변)

- **Binary = deterministic, Session = LLM**: 외부 백엔드(cks·chainbench) 바이너리는 LLM 호출이
  **0**이고 결정론적 작업만 한다. 모든 *판단*은 coding-agent 세션 레이어에 모인다.
  같은 입력이면 백엔드는 항상 같은 결과를 준다. (출처: [OVERVIEW.md](OVERVIEW.md) §5,
  [system-contract.md](system-contract.md) §2.2)
- **보안은 양방향 대칭**: 입력은 jira-gateway가 LLM에 닿기 *전에* 막고, 출력은 pr-sanitize가
  같은 패턴으로 스크럽한 뒤 내보낸다. (출처: [OVERVIEW.md](OVERVIEW.md) §5)
- **추측 대신 근거**: planner는 낯선 거대 코드베이스를 추측하지 않고 cks에 물어 실제 코드에
  근거한 설계를 한다. (출처: [OVERVIEW.md](OVERVIEW.md) §4 기둥 B)
