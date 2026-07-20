# RAG · 컨텍스트 엔지니어링 효율 개선 제안 — coding-agent (2026-06-19)

> **STATUS (2026-06-29): 우선순위 1·3·4 구현·머지됨 (PR #38·#40).**
> **3.1 Implementer EvidencePack 재사용**(#38, v0.1.38 — implementer §4.2 scoped Read) ·
> **2.2 적응형 검색 깊이**(#38 — analyzer §3.4/§3.5 complexity tier 게이트) ·
> **4.1 검색 충분성 게이트**(#40, v0.1.40 — analyzer §6.0) 완료.
> **홀드: 2.1 검색 캐시** — 새 메커니즘·stale 위험으로 베이스 검증(Phase 2) 후로 보류.
> **잔여: 2.3 evidence 증류 · 2.4 자기-과거 RAG · 3.2 필드 분할 · 3.3 prompt-cache prefix.**
> 효과(총비용 절감)는 Phase 2 bench(A′ 모드)로 측정.

문서 성격: **분석 + 제안 (일부 구현·status/proposal)**. 퍼포먼스·경제성 개선 근거/합의용.
대상: `coding-agent` 플러그인 파이프라인 — `analyzer`(RAG 진입점) → `planner` → `implementer` → `evaluator`.
근거: 실제 에이전트 마크다운 + cks 사용 패턴 + EvidencePack(`related-code.json`) 소비 추적
(grep 확인) + `bench-orchestration` 측정 하네스.
관련 문서: `knowledge-system-analysis-2026-06-17.md`(cks/ckv/ckg 갭), `OVERVIEW.md`.

> **요약:** cks 검색 *품질*은 좋다. 문제는 **검색 결과를 재사용하는 컨텍스트 엔지니어링이 비어
> 있다**는 것 — 같은 코드 span이 파이프라인을 지나며 2~3회 중복 적재되고, 검색은 bug-cycle·
> 티켓마다 매번 처음부터 재실행되며, 큰 아티팩트는 필요 없는 필드까지 통째로 로드된다.
> 가장 큰 경제적 손실은 *retrieval 품질*이 아니라 **retrieval 재사용의 부재**다.
> 즉효 개선 3가지: ① Implementer가 EvidencePack 재사용 ② 검색 캐시(index-head 무효화)
> ③ 복잡도 기반 적응형 검색 깊이. 모든 변경은 이미 존재하는 `bench` 하네스로 총비용 회귀를 검증한다.

---

## 1. 비용 모델 — 토큰·비용이 실제로 새는 곳

비용을 줄이려면 어디서 쓰는지부터 정확히 봐야 한다. 코드 기준 토큰 흐름:

```
analyzer:   get_for_task(~1.5k) + impact/concurrency/subgraph/semantic
              → related-code.json (raw, 큼)
              └ 같은 코드 span이 pack 본문으로 ①차 적재

planner:    analysis.md + related-code.json(통째) + ticket-parsed.json 로드
              └ design "Current code excerpt"(file:line)로 같은 span ②차 적재

implementer: design 블록 + target_file **전체 Read**   ← related-code.json 안 읽음(grep 확인)
              └ 같은 파일 span ③차 적재 (이번엔 디스크에서 풀로)

evaluator:  related-code.json 통째 로드하지만 실제 사용은 ckg.concurrency_impact 한 필드뿐
```

### 진단 (냉정한 버전)

| 손실 유형 | 내용 | 증거 |
|----------|------|------|
| **중복 적재** | 동일 span이 파이프라인서 2~3회 적재 | analyzer §3.1b · planner design · implementer §4.2 |
| **재사용 부재** | bug-cycle·티켓마다 검색 처음부터 재실행 | analyzer §3b 재진입, 캐시 없음 |
| **과적재** | 큰 아티팩트를 필요 없는 필드까지 통째 로드 | evaluator는 1필드만 쓰며 전체 로드 |

### 이미 잘 된 점 (계측 기반 개선이 가능한 이유)

- analyzer §3.1c: "이번 턴 토큰이 아니라 *옳은 수정까지의 총비용*을 최적화" 원칙 명문화.
- analyzer §3.1b: "pack이 준 span은 재-Read 금지" (가장 큰 토큰 낭비 회피).
- `bench-orchestration`: A/B/C 모드를 **Σ(전 cycle 토큰)·비용·정확성**으로 이미 측정.
  → 아래 제안은 전부 A/B 검증 가능. 추측이 아니라 측정으로 채택한다.

---

## 2. RAG(검색) 레이어 개선

### 🥇 2.1 검색 결과 캐시 (index-head 키 무효화) — 최대 경제 레버리지

- **문제**: bug-cycle 재진입(§3b)·동일 모듈(consensus/wbft) 반복 티켓마다 `get_for_task`/
  `impact_analysis`를 매번 재호출. cks 내부 캐시와 별개로 *에이전트 측 재사용*이 0.
- **아이디어**: `.stablenet-expert/evidence-cache/` 도입.
  키 = `(cks indexed_head, query_hash)` → EvidencePack JSON.
  analyzer는 검색 전 `cks_ops_freshness`로 이미 `indexed_head`를 받으므로 **무효화 키가 공짜로 존재**.
  head 동일 + query 동일 → MCP 왕복·임베딩·그래프 순회 전부 스킵.
- **효과**: 반복 MCP 호출/지연 직접 절감(경제+성능). bug-cycle이 많을수록 이득 누적.

### 🥇 2.2 복잡도 기반 적응형 검색 깊이 (retrieval router)

- **문제**: 공유/파생 상태를 건드리면 `impact_analysis`+`concurrency_impact`+`get_subgraph`를
  *기본으로* 다 쏜다(가장 비싼 그래프 호출). `estimate_complexity`는 있지만 **비싼 검색 *후*(§3.3)**
  호출된다 — 순서가 거꾸로다.
- **아이디어**: 결정적·무료인 `stablenet-context`(경로 분류)를 **검색 전 라우터**로 끌어올려
  작업을 tier(trivial / local / shared / concurrency)로 먼저 분류 → 그 tier가 정당화하는
  그래프 도구만 호출.
- **효과**: 단순 작업에서 최고가 호출 제거, 복잡 작업은 그대로 완전성 유지.

### 🥈 2.3 broad-retrieve → narrow-inject (evidence 증류)

- **문제**: `semantic_search(k=15)`·`get_subgraph(max_total=200)`의 **raw 덤프**가
  `related-code.json`에 들어가고 planner가 그걸 읽는다. 검색은 넓은데 주입도 넓다.
- **아이디어**: analyzer가 검색 후 "design에 실제 필요한 5~10 span"만 추린 **evidence digest**를
  별도 작성, planner는 raw 그래프가 아니라 digest를 읽는다. (RAG 정석: retrieve broad, inject narrow.)
- **효과**: planner 입력 토큰 절감 + 신호/잡음비 개선 → 설계 품질도 향상.

### 🥉 2.4 자기-과거 RAG ("이거 전에 고쳤었나")

- **문제**: `failure_log`/`recurring_patterns`가 티켓 단위로만 존재. 과거 유사 수정 지식 재사용 0.
- **아이디어**: 완료된 `analysis.md`/`plan.md`를 경량 벡터 스토어(또는 cks)에 인덱싱 →
  analyzer가 ticket·failure 요약으로 "유사 과거 티켓과 해법" 검색.
- **효과**: 재유도 비용 절감 + 지능 향상 (RAG over own-history).

---

## 3. 컨텍스트(아티팩트 흐름) 레이어 개선 — 즉효성 높음

### 🥇 3.1 Implementer가 EvidencePack 재사용 (중복 적재 #3 제거)

- **문제(확정)**: grep 결과 implementer는 `related-code.json`을 **안 읽는다**. §4.2가 `target_file`을
  **전체 Read**한다. analyzer가 pack 본문으로, planner가 design excerpt(`file:line`)로 이미 끌어온
  코드를 디스크에서 풀로 다시 읽는다.
- **아이디어**: design의 `Current code (excerpt) file:path lines start-end`를 implementer가
  **범위 지정 Read(offset/limit)** 로 좁혀 읽거나, analyzer가 "이미 증거에 있는 span 목록"
  (context manifest)을 넘겨 implementer는 **델타만** 읽는다.
- **효과**: implementer 입력 토큰 최다 절감(전체 파일 → 필요 span). 가장 손쉬운 즉효 개선.

### 🥈 3.2 필드 스코프 아티팩트 분할

- **문제**: `related-code.json`이 `pack+ckv+ckg.subgraphs+concurrency_impact+impacts`를 다 담는데,
  evaluator는 **`ckg.concurrency_impact` 한 필드만** 쓰면서 통째로 로드한다.
- **아이디어**: `related-code.pack.json` / `.graph.json` / `.impacts.json`로 분할 → 소비자가
  필요한 것만 Read.
- **효과**: 단계별 로드 토큰 절감(특히 evaluator).

### 🥉 3.3 프롬프트-캐시 친화적 디스패치 프리픽스

- **문제**: 각 sub-agent는 fresh `query()`라 공유 컨텍스트(ticket+analysis)가 매 디스패치 재전송된다.
  fork(부모 프롬프트 상속 → 캐시 히트)를 안 쓴다.
- **아이디어**: analyzer→planner→implementer 디스패치 프롬프트의 **안정 프리픽스(ticket+analysis
  요약)를 동일하게 front-load** → 서버측 prompt caching으로 후속 단계 입력 비용 절감.
- **효과**: 입력 토큰 단가 하락(순수 경제).

---

## 4. 하네스(오케스트레이션·측정) 레이어

### 4.1 검색 충분성 게이트 (RED 게이트의 검색판)

- **문제**: analyzer의 완전성 판단이 휴리스틱. "추측 없이 설계 가능한가"를 명시 확인하는 게이트가
  없다 → 불완전 분석이 그대로 넘어가 bug-cycle(가장 비쌈)을 유발.
- **아이디어**: ANALYSIS→PLANNING 전에 "미해결 unknown 목록" 자기-체크. 비어있지 않으면
  **타깃 검색 1회 추가** 후 통과. (재현 RED 게이트와 동일 철학.)
- **효과**: bug-cycle 1회만 줄여도 retrieval 절약분을 압도(§3.1c 총비용 논리 그대로).

### 4.2 모든 개선은 bench로 검증

`bench-orchestration`이 A(cks)/B(code)/C(skills)를 Σ(전 cycle 토큰)·비용·정확성으로 비교한다.
2~3장 아이디어는 **새 모드(예: A′ = cks + cache + adaptive)로 추가**해 A 대비 회귀 없이 비용↓인지
측정 가능. 채택은 측정으로 결정한다.

---

## 5. 우선순위 (레버리지 × 노력)

| 순위 | 아이디어 | 레버리지 | 노력 | 범위 |
|------|---------|---------|------|------|
| 1 | 3.1 Implementer EvidencePack 재사용 ✅ **머지 #38** | 높음 | 낮음 | coding-agent only |
| 2 | 2.1 검색 캐시(index-head 무효화) ⏸ **홀드** | 높음 | 중간 | coding-agent only |
| 3 | 2.2 적응형 검색 깊이(라우터) ✅ **머지 #38** | 높음 | 낮음 | coding-agent only |
| 4 | 4.1 검색 충분성 게이트 ✅ **머지 #40** | 중간 | 낮음 | coding-agent only |
| 5 | 2.3 evidence 증류 / 3.2 필드 분할 | 중간 | 중간 | coding-agent only |
| 6 | 3.3 프롬프트-캐시 프리픽스 | 중간 | 중간 | coding-agent only |
| 7 | 2.4 자기-과거 RAG | 중간(지능) | 높음 | +벡터스토어 |
| — | parity 갭(find_invariants/flow 도구) | **검색품질 최대** | 높음 | **cks 측**(교차 repo) |

> ⚠️ 검색 *품질*의 가장 큰 레버는 `knowledge-system-analysis`가 짚은 **parity 갭** —
> `find_invariants`/`get_conventions`/flow 도구가 cks 경유로 안 닿아 analyzer가 일반
> `semantic_search`에 의존한다. 단 이건 cks repo 작업이라 coding-agent 단독으로는 못 닫는다.
> **위 1~6은 coding-agent 안에서 즉시 가능한 경제성 개선**이고, parity는 품질 개선의 별도 트랙.

---

## 6. 핵심 원칙 한 줄

> **"한 번 검색한 증거는 파이프라인 끝까지 재사용하고(중복 적재 제거), 검색 깊이는 작업 복잡도에
> 비례시키고(적응형), 모든 변경은 bench로 총비용 회귀를 검증한다."**
>
> 지금 시스템은 *검색은 잘하는데 그 결과를 흘려보낸다* — 가장 큰 경제적 손실은 retrieval 품질이
> 아니라 **retrieval 재사용의 부재**다.

---

## 부록. 근거 파일 인덱스

| 대상 | 경로 · 위치 |
|------|------------|
| RAG 진입점 | `plugin/agents/analyzer.md` (§3.1b get_for_task, §3.1c 완전성, §3b 재진입) |
| EvidencePack 미재사용 | `plugin/agents/implementer.md` §4.2 (target_file 전체 Read) |
| EvidencePack 소비처 | grep: planner·evaluator만 `related-code.json` 읽음(implementer 제외) |
| 과적재 | `plugin/agents/evaluator.md:133` (concurrency_impact 한 필드만 사용) |
| 측정 하네스 | `plugin/skills/bench-orchestration/SKILL.md` (§4.5 Σ-cost 비교) |
| cks parity 갭 | `docs/knowledge-system-analysis-2026-06-17.md` §4 |

---

*문서 끝 — 구현은 본 제안 합의 후 별도 진행. 1~3순위부터 bench A′ 모드로 검증 권장.*
