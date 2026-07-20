# 그래프 추론 갭 + 수정 계획 (Graph Reasoning Gap & Fix Plan) — 2026-06-19

> **문서 성격:** Tier 3 (status / proposal, 미구현). 한 세션의 분석·합의 결과를 다른 머신/세션이
> **그대로 이어받기 위한 자급자족 핸드오프**.
> **자급자족 원칙:** 이 문서는 머신-로컬 Claude 메모리(`~/.claude/.../memory/`)가 **없는 환경에서도**
> 작업을 이어갈 수 있도록 작성됨. 빌드/환경/데이터 위치/코드 근거(file:line)/원본 프롬프트를 모두 인라인함.
> 메모리가 있는 환경이라면 `cks-mcp-serving-architecture.md`, `ckg-ckv-review-2026-06.md`,
> `ckg-4way-eval.md`, `cks-composer-retrieval-fix.md`가 보조 맥락.

---

## 0. TL;DR — 다음 세션은 여기부터 읽어라

> ⚠️ **2026-06-22 정정 (P0 전제 부분 반증 — 착수 전 필독):**
> 이 문서의 **P0(진단→agentic 도구 라우팅)** 는 "진단 실패의 원인 = 그래프 미노출"이라는 전제 위에 있었다.
> 그러나 6/22 **analyzer 단독 라이브 검증**(공정/증상-only 입력, 메커니즘 단서 없음)에서 analyzer가
> **기존 13개 도구(`get_for_task` + `find_callers`)만으로 PRIMARY 근본원인(`anzeon.go:54 SetCurrentBlock`)에
> 정확 도달**했다. 즉 자체 eval의 δ<γ 격차를 메운 것은 **새 그래프 프리미티브 노출(P0~P5)이 아니라
> analyzer의 agentic routing + 시간적-추론/확증편향 보강**이었다.
> → **P0는 사실상 흡수되어 신규 구현 불필요**. 이 문서에서 살아남는 가치는 **P1.5(depth-cap 절단 가시화, 저비용·additive)**
> 와 **P2/P3(motif·suffix-recall = 정확성 트랙)** 이다. 우선순위는 **하향**(통합뷰 `WORKLIST.md` 스트림3 참조).
> 아래 본문(§0~§6)은 6/19 시점 분석 그대로 보존한다(supersede-not-delete) — δ<γ 코드 증거 자체는 여전히 유효.

**한 줄 결론:** cks/ckg는 "그래프 DB"를 표방하지만 **그래프의 추론력(경로·도달성·사이클·모티프)을
하나도 노출하지 않는다.** 노출되는 그래프 쿼리는 전부 *고정깊이 BFS(노드/엣지 bag 반환)*이고,
cks 컴포저는 그 얕은 결과마저 **벡터 지배 + 평탄화**로 뭉갠다. 그 결과 **"현상(버그/증상) 진단"이
구조적으로 불가능**하다. 이건 추측이 아니라 **자체 eval에서 이미 측정됨**(아래 §3, δ<γ).

**이번 세션이 합의한 것:**
1. GPT-5.5가 제안한 "code knowledge system 베스트 프랙티스"는 **우리가 이미 1년 전 구현해 넘어선 표준**이다 (상대적으로 우리가 우월). 단 절대적으로는 미해결 빚이 많다 (§1).
2. 진짜 문제는 "그래프 미활용"이며 코드 레벨로 확증됨 (§2, §3).
3. 수정 우선순위는 P0~P5, 두 트랙(노출·정확성)으로 정리됨 (§4).
4. 첫 PR은 **P0(진단→agentic 도구 라우팅) + P1.5(depth 캡 가시화)**. 재인덱싱 불필요, cks 컴포저 수술 불필요 (§5).

**다음 세션의 첫 행동 (반드시 §6의 미확인 항목부터):**
- `/coding-agent:diagnose` 명령/agent가 **이미 존재**한다 → P0의 home이 `planner.md`가 아니라 이쪽일 수 있음. **먼저 확인.**
- "CKV 15개 MCP 도구 중 cks 경유 도달 1개뿐"(parity 갭) → γ-라우팅이 부를 granular 그래프 도구가 **애초에 노출돼 있는지** 확인.
- 이 둘을 확인한 뒤 §5의 첫 PR 범위를 확정하고 착수.

---

## 0.5 시스템 구성 (다른 머신이 알아야 할 전체 지형)

루트: `~/Work/github/` (※ 이 디렉토리 자체는 git repo 아님 — **각 하위 프로젝트가 독립 .git**).

| 컴포넌트 | 경로 | Go 모듈 | 역할 |
|---|---|---|---|
| **coding-agent** | `Work/github/coding-agent` | (플러그인) | Claude Code 플러그인. 명령·agent·hook으로 작업 오케스트레이션. cks/jira/chainbench MCP 소비. **planner→implementer→evaluator** 파이프라인 + state machine |
| **cks** | `Work/github/code-knowledge-system` | `github.com/0xmhha/code-knowledge-system` | MCP 오케스트레이터. ckv+ckg를 **in-process import**해 조합. 컴포저(get_for_task)와 granular MCP 도구 노출 |
| **ckg** | `Work/github/code-knowledge-graph` | `github.com/0xmhha/code-knowledge-graph` | 코드 그래프(37 노드/43 엣지). SQLite(`graph.db`). Go/TS/Solidity 파서 |
| **ckv** | `Work/github/code-knowledge-vector` | `github.com/0xmhha/code-knowledge-vector` | 벡터/시맨틱 검색. sqlite-vec(`vector.db`). 임베딩 bge-m3(Ollama) |
| **chainbench** | `Work/github/chainbench` | (bash + MCP) | go-stablenet(geth fork, WBFT 합의) 통합 테스트 하네스. evaluator Stage 4가 사용 |

**대상 코드베이스:** go-stablenet (geth fork, WBFT/PoA 합의, KRW-pegged stablecoin). 위 지식시스템이 인덱싱하는 실제 코드.

데이터 흐름: `ckv build`/`ckg build` → `vector.db`/`graph.db` → `cks-mcp`가 두 DB를 in-process로 열어 조합 → coding-agent의 agent들이 cks MCP 도구 호출.

---

## 0.6 빌드 · 테스트 · 환경 (착수 전 필독, 자급자족용)

**전제조건**
- **Ollama는 macOS 앱 캐스크로 띄운다** (`open -a Ollama`). **brew formula 버전은 embeddings에서 HTTP 500** → 금지. 모델 `bge-m3` 필요 (`ollama list` 확인, 없으면 `ollama pull bge-m3`). 엔드포인트 `http://localhost:11434`.
- ckv/ckg는 **CGO 필요**(sqlite-vec). 빌드: `CGO_ENABLED=1 make build-bins` → `bin/cks-mcp`(+CLI).
- cks config 예: `code-knowledge-system/cks-stablenet.yaml` — `backends.ckg.path`(graph.db), `backends.ckg.source_root`(=go-stablenet 워킹트리, **인덱싱 커밋과 일치해야 함**), `backends.ckv.path`, `embed_model: bge-m3`, `ollama_url`.
- 인덱싱 데이터: `code-knowledge-system/data/ckg-stablenet`, `data/ckv-stablenet` (go-stablenet@`c051d50b` 기준 빌드본 — 세션 시점 값, 갱신됐을 수 있으니 manifest 확인).

**각 repo 루트에서**
```
make build-bins                  # CGO_ENABLED=1, 바이너리 산출
go test ./...                    # cks≈23pkg, ckv≈36pkg 통과 기대
go vet ./...
go test -race ./<changed-pkg>/   # 동시성 변경 시 (특히 ckg)
make lint                        # ckg: go vet + fmt-check (+viewer eslint)
make fmt                         # ckg: gofmt 드리프트는 하드 게이트
```
- ckg는 **Go 1.25.x**. `make build`(뷰어 포함) vs `make build-no-viewer`(빠름).
- ⚠️ ckv `internal/embed/coreml`는 네이티브 `tokenizers` 미설치 시 **테스트 링크 실패**(`ld: library 'tokenizers' not found`) — 환경 이슈, 정상. 다른 패키지 통과면 OK.

**ckg 작업 시 규율 (ckg/CLAUDE.md):**
- `pkg/`는 **공개 contract 경계** — CKV/CKS가 소비. 변경은 back-compat 검토 필요. `internal/`은 외부 repo가 import 금지.
- `SchemaVersion` 범프는 **breaking 변경만**. additive optional 필드(`omitempty`)는 범프 안 함.
- **그래프 빌드는 LLM-free·결정론적** 유지. LLM은 `eval` 표면에서만.
- 동시성 주장은 `make test-race` 통과 후에만.
- 문서는 3-tier(VISION=Tier1 / ADR=Tier2 / status=Tier3). 결정 변경은 새 ADR로 supersede(삭제 금지). 본 문서는 Tier 3.

---

## 1. GPT-5.5 제안서 검토 평결

세션 발단: 사용자가 GPT-5.5가 작성한 "코드 구현용 Knowledge Data System 베스트 프랙티스" 제안서
(Graph+Vector+Keyword+Relational 하이브리드, AST 파서, context package, retrieve→impact→test→implement 워크플로 등 — 전문은 부록 A)를 **냉정하게 검토하고 우리 코드와 비교** 요청.

**평결: 제안서는 "이미 구현해 넘어선 표준의 회고적 재서술"이다.**

| 제안서 권장 | 우리 현실 | 판정 |
|---|---|---|
| Graph+Vector+Keyword+Relational 하이브리드 | ckg+ckv+ckg FTS5+cks | ✅ 초과 구현 |
| Graph node/edge (Function/Test/Policy/PR/Commit, CALLS/IMPLEMENTS/MODIFIES…) | ckg 37 노드/43 엣지 | ✅ |
| AST 파서(Go: go/ast·go/types) | go/packages(types-aware)+tree-sitter(TS/Sol) | ✅ 다언어 |
| 검색: keyword→graph→vector→rerank | cks 5단계 컴포저 + RRF 융합 | ✅ 더 정교(단, §2에서 이게 오히려 문제) |
| Context Package(raw 파일 금지) | `get_for_task`→EvidencePack(8k 토큰 예산) | ✅ |
| retrieve→impact→test→implement→verify | planner→implementer→evaluator 4-stage | ✅ |
| Incremental indexing / 품질평가 | ckg 캐시키·ckv reindex / eval ckg-4way·bench A/B/C | ✅ 초과 |

제안서 8장 베스트프랙티스 13행 중 11행이 이미 production. 9장 "MVP Phase 1~4 로드맵"은 우리가 Phase 3후반~4 진입인데 Phase 1부터 그림 → **현 위치 모르는 일반론**.

**제안서가 우리보다 순진/틀린 지점:**
- (a) Neo4j+Qdrant+OpenSearch+PostgreSQL+S3 5종 스택 권장 → 우리는 **의도적으로 임베디드 SQLite 단일파일**로 통일(MCP 서브프로세스·CGO-free·라이프사이클 패리티). 제안서대로면 운영복잡도 폭증.
- (b) "keyword→graph→vector 엄격 순차" → 우리는 RRF 동시융합으로 대체했고, **eval에서 벡터+bodies(δ)가 tool-only(γ)보다 나쁨을 실측**(§3). 제안서의 암묵 가정을 우리 데이터가 반박.
- (c) 인용 출처 자기모순: 두 번째 출처 제목이 *"Why Cursor/Claude Code/Devin Use grep, NOT Vectors"*인데 본문은 Vector DB를 1급으로 깖.

**제안서가 놓친 우리의 진짜 문제(제안서엔 개념조차 없음):** CJK/한글 임베딩 붕괴(bge-large-en은 영어전용),
인용 환각(δ), 앵커 staleness(지식이 코드보다 빨리 썩음), silent degraded mode, impact recall ~23% 누락.

**제안서에서 실제 건질 갭(우리 약점과 교집합) 딱 3개:** ① Test→Function 엣지(ckg 미추적) ② Relational 축(ownership/quality metrics) ③ BM25 rerank default화(현재 opt-in).

> **상대 평가(제안서 기준): 우리가 한참 앞섰다. 절대 평가(production 신뢰성): 아직 빚 많다.**
> 다음 작업은 제안서 따라가기가 아니라 **우리만의 미해결 4난제(환각·한글임베딩·staleness·recall)와
> 본 문서의 그래프 갭을 깨는 것**.

---

## 2. 핵심 발견 — 그래프 미활용 (코드로 확증)

사용자 후속 지시: *"cks 제공 내용으로는 어떤 현상에 대한 문제를 제대로 파악하지 못한다. graph db를
쓰는데도 graph의 장점이 활용되지 않는다. 냉정하고 상세하게 검토하라."* → 두 정밀 감사(Explore agent)
결과 **두 개의 독립적 실패가 곱해져** 진단 무능을 만든다.

### 실패 1 — ckg가 그래프를 "근접 인덱스"로만 노출 (추론 엔진 아님)

노출되는 그래프 쿼리가 전부 고정깊이 BFS 하나의 래퍼. 노드/엣지 bag만 반환, 경로/구조 없음.

| 그래프의 진짜 무기 | 구현 상태 | 근거 file:line |
|---|---|---|
| 고정깊이 BFS (모든 도구의 토대) | 있음 (얕음) | `ckg internal/persist/sqlite_reader.go:354-403` (NeighborhoodByQname), `:409-430` (SubgraphByQname) |
| find_callers/callees | BFS 래퍼 | `ckg pkg/mcphandlers/handlers.go:47-100` |
| impact_analysis | 6개 독립 reverse-BFS 합집합 | `ckg pkg/impact/impact.go:102-275` |
| concurrency_impact | 양방향 BFS 2회 | `ckg pkg/concurrency/concurrency.go:62-182` |
| **두 노드 간 경로(A→B)** | ❌ **존재하나 CLI 전용, MCP 미노출** | `ckg cmd/ckg/path.go` (`bfsShortestPath`) |
| 전이폐쇄/무제한 도달성 | ❌ depth 하드캡 5에서 잘림 | `ckg pkg/impact/impact.go:27`, `pkg/concurrency/concurrency.go:22` (기본 2) |
| 사이클 탐지(의존성/락순서/데드락) | ❌ 내부 DFS 사이클 *회피*만, 빌드타임 전용 | `ckg internal/buildpipe/lock_propagation.go:104` |
| 데이터플로우(값 전파) | ❌ 엣지 자체 없음 (statement-granular 제어흐름 + field read/write뿐) | (enums.go 엣지 목록) |
| 경로 설명(증상→원인 엣지 시퀀스) | ❌ CLI만 | `ckg cmd/ckg/path.go:213-220` |
| 모티프 매칭(락 획득후 미해제, 수신자 없는 채널 송신) | ❌ **엣지는 저장되는데 읽는 알고리즘 0개** | (acquires_lock/releases_lock/sends_to/recvs_from 엣지 존재, 분석코드 없음) |

가장 아픈 점: **동시성 엣지가 다 있는데 분석 알고리즘이 한 줄도 없다.** `concurrency_impact`조차
"동시성 엣지로 연결된 모듈 목록"을 BFS로 뱉을 뿐 "이 락이 경로 Z에서 미해제" 같은 *판정*은 안 함.
데드락/레이스는 정확히 그래프 모티프 문제인데 모티프 매칭이 없음.

**정확성 버그:** `ckg internal/parse/golang/resolve.go:30-71` — suffix-match 해소가 cross-package
동명 함수(`main.Run`/`worker.Run`)를 **map 순회 순서대로 random 바인딩**하고, 미해소 시 **silent drop**
→ impact_analysis recall ~23% 누락.

### 실패 2 — cks 컴포저가 남은 구조마저 평탄화

| 문제 | 근거 file:line |
|---|---|
| Stage 3가 이웃을 target 키로 dedup, **최고점 엣지만 남기고 대체 경로 폐기** (A→B→C 체인 소멸) | `cks internal/composer/stage3/scoring.go:346-354`, 호출부 `stage3/expander.go:189-217` |
| EvidencePack에 **경로 필드 없음** (Citations[]·Bodies[]·평탄 GraphNeighbors[]뿐) | `cks pkg/contract/pack.go:170-184` |
| **벡터 지배** RRF 가중치 Ckv **5.0** ≫ Symbol 1.5 > BM25 1.0; Stage1 키워드 추출도 ckv 구동 | `cks internal/composer/stage2/searcher.go:40-57` |
| 컴포저 전체 (Stage1~5 순차) | `cks internal/composer/composer.go:148-244` |
| get_for_task = retrieve-by-relevance, **인과 순회 없음** | `cks internal/mcp/get_for_task.go:21-55` |

### 왜 이게 "현상 진단 불가"로 직결되나

> **현상(버그/증상)은 chunk가 아니라 path·interaction이다. 그런데 cks는 "이 단어와 의미적으로
> 비슷한 코드"를 검색한다 — 완전히 다른 질문에 답하고 있다.**

진단이 요구하는 질문("값 X가 어떤 경로로 Y에 도달", "이 락이 경로 Z에서 안 풀림", "필드 F를 A는 락걸고
B는 안걸고 씀")은 전부 그래프 워크/모티프 질문. cks는 증상의 *이웃*만 회수하고 *메커니즘*을 구성 안 함.
게다가 벡터 지배(Ckv 5.0)는 진단에서 역효과 — 버그는 증상으로 표현되는데 원인 코드는 증상과
*구조적*으로 연결될 뿐 *텍스트 유사*하지 않음. 벡터는 텍스트 유사한 걸 끌어와 엉뚱한 곳을 상위로 올림.
(feature 구현 task에선 벡터 지배가 괜찮음 → 이 시스템이 retrieval엔 쓸 만하고 diagnosis엔 무력한 이유.)

---

## 3. 결정적 증거 — 자체 eval이 이미 δ<γ를 측정함

출처: `cks eval/ckg-4way/Report.md` (30문항 × 4모드 = 120런).

| 모드 | 정의 | location 정확도 | correctness | 환각 | tokens |
|---|---|---|---|---|---|
| α | raw 파일 | 0.267 | 0.90 | — | 2.0k |
| β | 전체 그래프 구조만 | 0.567 | 0.00 | — | 3.5k |
| **γ** | **on-demand tool을 LLM이 직접 호출 (bodies 없음)** | **0.80** | 0.667 | **0** | 4.0k |
| **δ** | **get_for_task 합성 팩 (bodies 포함)** | **0.367** | 0.833 | **10** | 3.5k |

**해석:** 합성 파이프라인(δ)이 날것 도구(γ)보다 location 절반 이하 + 환각 10건. γ의 환각 0은 도구
출력을 그대로 복사하기 때문. δ는 bodies를 주니 모델이 line range를 재구성하며 환각. **컴포저의
사전-평탄화가 agent가 직접 걸을 수 있던 구조를 오히려 파괴한다.** = "cks로는 현상 파악 안 됨"의 정체.

---

## 4. 수정 우선순위 (P0~P5, 두 트랙)

### 전략 분기 (먼저 결정): 진단을 "합성 팩 개선"으로 풀까 "agentic 도구 라우팅"으로 풀까?
→ **권고: agentic 라우팅.** eval이 γ>δ를 증명. 합성 팩(Paths[] 필드 추가 등)에 큰 투자 말 것.
이 결정이 P4 우선순위를 낮춤. (만약 "팩은 토큰예산/캐시/sanitize 때문에 포기 못함"이면 P4가 P2로 승격.)

### 트랙 A — 노출·추론 (그래프 활용의 본체)

| 순위 | 작업 | 위치 | 효과 | 비용 | 재인덱싱 |
|---|---|---|---|---|---|
| **P0** | 진단 인텐트 → agentic 도구 라우팅 (δ 팩 대신 find_callers/callees/subgraph/concurrency_impact를 LLM이 직접 호출, 출력 그대로 인용) | coding-agent (planner.md or diagnose agent — §6 확인) | ★★★★★ | 낮음 | ❌ |
| **P1** | `ckg path` MCP 노출 ("A가 B에 어떻게 연결되나") | ckg `pkg/mcphandlers` + cks proxy tool | ★★★★☆ | 낮음 | ❌ |
| **P2** | 모티프 쿼리 3종 (락 획득후 미해제 / sends_to만 있고 recvs_from 없음 / 필드가 한경로는 accessed_under_lock 다른경로는 아님) | ckg 신규 analysis 패키지(빌드타임 lock_propagation DFS 재활용) + MCP + cks proxy | ★★★★★ | 중간 | ❌ |
| P4 | (전략분기서 "팩 유지" 택한 경우만) Stage 3 경로 보존 + EvidencePack.Paths[] | cks stage3/scoring.go, pkg/contract/pack.go | ★★★☆☆ | 중간 | ❌ |
| P5 | 데이터플로우 엣지(값 전파) | ckg 파서(SSA급) | ★★★★☆ | **높음** | ✅ |

### 트랙 B — 정확성 (모든 그래프 op의 기반)

| 순위 | 작업 | 위치 | 효과 | 비용 |
|---|---|---|---|---|
| **P1.5** | depth 캡 설정화 + **절단 경고**(BFS가 max depth에서 frontier 안 비면 `metadata.warnings`에 truncated_at_depth) | ckg pkg/impact/impact.go:27, pkg/concurrency/concurrency.go:22 | ★★★☆☆ | 매우 낮음 |
| P3 | suffix-match 해소 버그 (cross-package random 바인딩 + silent drop → recall 23% 누락) | ckg internal/parse/golang/resolve.go:30-71 | ★★★★☆ | 중간(리스크) |

### 권장 실행 순서
```
1주차  P0(라우팅) + P1.5(depth 가시화)   ← 거의 공짜, 즉시 체감. eval 재측정해 baseline 갱신.
2주차  P1(ckg path 노출)                ← 기본 진단 질문 잠금 해제
3~4주  P2(모티프 쿼리 3종)               ← "그래프의 장점" 본체
병렬   P3(suffix-match 정확성)           ← resolve.go라 리스크 격리 후
보류   P4(전략분기 따라) / P5(데이터플로우, 파서 대공사)
```

> **핵심:** 큰 투자(P5 데이터플로우, P4 팩개선)부터 가지 말 것. 진단 무능의 80%는 *이미 저장된
> 엣지를 읽는 도구가 없어서* 생김. P0+P1+P2(셋 다 재인덱싱 불필요)가 진짜 레버, 합쳐 한 달 안짝.

---

## 5. 첫 PR 설계 (권장 "a" = P0 + P1.5)

**왜 cks를 안 건드리나:** P0의 본질은 "어떤 도구를 호출하느냐". eval의 γ/δ는 둘 다 cks MCP 통과 —
차이는 호출 도구뿐. granular 도구(find_callers/callees/get_subgraph/concurrency_impact)는 이미 cks에
존재하고 ckg를 프록시. 즉 라우팅은 cks 컴포저 수술이 아니라 **소비자(coding-agent)의 도구선택 정책 변경**.
**진단용 인텐트도 이미 존재** → 새 인텐트 불필요:
- `IntentBugFix` `cks pkg/contract/intent.go:50`, `IntentConcurrencySafety:106`, `IntentSecurity:119`, `IntentArchExplain:83`
- 인텐트 분류기: `cks internal/composer/intent/classifier.go`, 앵커: `internal/composer/intent/anchors.go`

**어디서 고치나:**

| 변경 | 프로젝트 | 파일 | 성격 |
|---|---|---|---|
| P0 진단→agentic 라우팅 | coding-agent | `plugin/agents/planner.md` §3 검색 워크플로 **또는** diagnose agent (§6 확인 후 확정) | 프롬프트 |
| P1.5 depth 설정화+절단경고 | ckg | `pkg/impact/impact.go:27`, `pkg/concurrency/concurrency.go:22` | pkg/ = **contract 변경(additive)** |
| (선택) 진단 시 깊은 depth 요청 | coding-agent | planner.md depth 인자 | 프롬프트 |

**cks: 변경 없음. 재인덱싱: 없음.**

### P0 상세 (planner.md 현 상태 = δ 편향)
현재 §3.1b가 `get_for_task`를 **primary**("Cite directly; don't re-Read"), granular는 follow-up.
진단 분기 추가:
- bugfix 모드 또는 인텐트 BugFix/ConcurrencySafety/Security일 때:
  1. `get_for_task`는 **증거가 아니라 "시작 심볼 후보 찾기"용**으로만 1회 호출(seed 추출).
  2. 이후 **agentic 그래프 순회를 primary 증거로**: 증상 심볼→find_callers/callees(depth 3)→get_subgraph→(동시성이면)concurrency_impact(depth 3)→impact_analysis. **도구 출력 그대로 인용**(γ 환각0 이유).
  3. get_for_task의 bodies로 line range 재구성 **명시 금지**(δ 환각10 이유).
- feature/refactor 인텐트는 기존 δ 경로 유지(거기선 잘 작동).

### P1.5 상세 (맹목적 상향 금지 — 절단 가시화)
ckg 주석은 DepthCap=5를 옹호("deeper dilutes signal") — 일리 있음. 그래서 숫자 상향 대신:
1. **절단 경고**(핵심, memory의 "ckg silent-incompleteness"와 직결): BFS가 max depth에서 frontier가
   아직 안 비면(=더 있는데 잘림) `metadata.warnings`에 `truncated_at_depth:N`. impact.go는 이미
   `metadata.warnings` 구조 있음(:101) → 거기 얹음. 지금은 조용히 잘려 agent가 "전부"로 오판.
2. **DepthCap 설정화**: 하드 const 5 → Options 필드 또는 env. 기본값 5 유지(회귀 없음, additive).
   eval이 depth sweep 가능하게. 캡 8 상향은 eval 데이터 본 뒤 결정.

### 측정 (이 PR 정당화)
`cks eval/ckg-4way`를 **진단형 질문 세트**로 재실행 → planner "δ-led(기존)" vs "agentic-led(P0)"의
location·환각 비교. γ>δ 재현되면 P0 확정 + P2 투자 근거 확보.

### 착수 순서
① ckg P1.5(additive, 격리됨) → make build-bins + go test + go test -race → ② planner.md P0 → ③ eval 재측정.

---

## 6. 미확인 항목 — 다음 세션이 첫 PR 전에 반드시 검증 ⚠️

세션 막판 인접 문서 조사에서 우리 계획을 흔드는 사실 2개 발견(아직 코드로 미검증):

1. **diagnose 명령/agent가 이미 존재.** `knowledge-system-analysis-2026-06-17.md §1.1`에 따르면
   `/coding-agent:diagnose` = "root-cause 분석(코드 변경 없음) → `diagnosis.md`(원인+증거+신뢰도)".
   → **P0의 home이 planner.md bugfix 분기가 아니라 이 diagnose agent일 수 있음.** 진단→agentic
   라우팅이 거기 부분 구현돼 있을 수도. **확인 후 P0 위치 확정.**
   확인 경로: `coding-agent/plugin/commands/diagnose.*`, `coding-agent/plugin/agents/` 중 diagnose 관련.

2. **CKV parity 갭.** 같은 문서: "CKV 15개 MCP 도구 중 cks 경유 도달 1개뿐". → γ-라우팅이 부를
   granular 그래프/벡터 도구가 **애초에 cks에 노출돼 있는지** 확인 필요. 노출 안 됐으면 P0 전에
   도구 노출(작은 선행 PR)이 필요할 수 있음.
   확인 경로: `cks internal/mcp/server.go`의 Register 목록 vs ckv/ckg 실제 도구.

---

## 7. 인접 문서와의 관계 (중복/경계/긴장)

| 문서 (coding-agent/docs/) | 스코프 | 본 문서와의 관계 |
|---|---|---|
| `knowledge-system-analysis-2026-06-17.md` | 4-repo 교차 조사 | **상위 맥락.** diagnose 명령·CKV parity 갭 출처(§6). 먼저 읽을 것 |
| `rag-context-efficiency-proposals-2026-06-19.md` | RAG 비용/재사용 | **긴장**: "검색 품질 좋다, 문제는 재사용/중복적재"라 결론. 본 문서는 "진단용으론 그래프 미활용". **상보적 — 둘 다 참**(품질 OK ≠ 진단 OK). 합칠 때 충돌 주의 |
| `cks-ckg-ckv-hardening-backlog-2026-06-19.md` | 신뢰성/정합성 하드닝(transport·Ollama·serviceability) | P3(suffix-match recall)와 겹칠 가능성 → 중복 회피 위해 cross-check. 본체는 별개 |
| `remaining-work-detail.md` | coding-agent 파이프라인/bench thesis | 별개 스코프 |

**머신-로컬 메모리(있는 환경에서만):** `ckg-4way-eval.md`(§3 eval 원본), `ckg-ckv-review-2026-06.md`,
`cks-composer-retrieval-fix.md`, `cks-mcp-serving-architecture.md`. 없으면 본 문서가 1차 권위.

---

## 부록 A — 이번 세션 원본 프롬프트 (재현용)

**A.1 발단 (요약):** 사용자가 `coding-agent`/`code-knowledge-system`/`code-knowledge-graph`/
`code-knowledge-vector`/`chainbench` 5개 프로젝트에 대해, GPT-5.5가 작성한 "코드 구현용 Knowledge
Data System 베스트 프랙티스" 제안서를 **냉정하게 검토하고 우리 코드와 비교** 요청.

제안서 골자(전문은 길어 핵심만 — 비교 재현엔 충분):
- 결론: "Vector DB만으론 부족, 코드는 정확한 구조관계가 중요" → Graph+Vector+Keyword+Relational 하이브리드 권장.
- 저장 대상: (A) 코드구조(Symbol/AST/Dependency/TypeRelation/RuntimeFlow/TestRelation/ErrorFlow → Graph),
  (B) 도메인정책(BusinessRule/Invariant/Security/Performance/ADR/Naming → Vector+Graph),
  (C) 변경이력(PR/commit/issue/review → Graph: Change-MODIFIES/FIXES/DECIDED_BY).
- Retrieval: "Vector 단독 금지", 순서 keyword→graph traversal→vector→rerank.
- 데이터모델: 노드(Repository/Package/File/Symbol/Function/.../DomainPolicy/ADR/PR/Commit/Issue/Error/SecurityRule),
  엣지(CONTAINS/CALLS/IMPLEMENTS/IMPORTS/TESTS/MODIFIES/FIXES/DEPENDS_ON/OWNED_BY/VIOLATES/PROTECTS/CONFIGURES).
- 스토리지: Neo4j/Memgraph(그래프)+Qdrant/Weaviate/Milvus/pgvector(벡터)+OpenSearch/Meilisearch(exact)+PostgreSQL(메타)+S3(raw).
- LLM 입력: raw 아닌 "Coding Context Package"(Task/RelevantSymbols/CallGraph/DomainRules/ExistingTests/ChangeHistory/Risk/ImplementationPlan).
- 워크플로: 요구분석→symbol검색→graph영향도→vector정책검색→테스트확인→계획→수정→테스트→lint→diff리뷰→self-verify.
- MVP Phase 1~4 로드맵. 인용: arXiv 2505.14394(KG 기반 repo-level codegen) + MindStudio 블로그("grep not vectors").

**A.2 후속 1:** "결론은 우리 코드가 현재 더 우수한 상태라는거지??"
→ (답: 제안서 대비 우월 ✅, 절대 신뢰성으론 빚 많음 ⚠️ — §1)

**A.3 후속 2 (핵심 전환):** "2의 (b) 항목에 대해 더 고민해보자. 현재 cks 제공 내용으론 어떤 현상에
대한 문제를 제대로 파악 못한다. graph db를 쓰는데도 graph 장점이 활용 안 된다. 냉정하고 상세히 검토."
→ (§2, §3 — 두 정밀 감사로 확증)

**A.4 후속 3:** "그래프가 제대로 노출 안 되는 게 맞네. 수정 우선순위를 정리해줘." → (§4)

**A.5 후속 4:** "권장 a를 진행하자. 수정은 어떤 프로젝트에서?" → (§5)

**A.6 후속 5:** "이 세션 작업이 문서로 정리된 게 있나?" → (없음 확인 → 본 문서 생성)

### 다음 세션에서 그대로 쓸 수 있는 재개 프롬프트 (복붙용)
```
~/Work/github/coding-agent/docs/graph-reasoning-gap-and-fix-plan-2026-06-19.md 를 읽고 이어서 진행해줘.
먼저 §6 미확인 항목 2개(diagnose agent 존재 여부 + CKV parity 갭)를 코드로 검증해서 P0의 home과
선행 PR 필요 여부를 확정한 뒤, §5의 첫 PR(P0 진단→agentic 라우팅 + P1.5 ckg depth 절단경고)을 착수해줘.
ckg pkg/는 contract 경계이니 additive로만, make build-bins + go test + go test -race로 검증.
```

---

## 부록 B — 이번 세션 산출물 인덱스 (한눈에)
- 평결(§1): GPT-5.5 제안 = 이미 넘어선 표준. 건질 갭 3개(Test→Func 엣지·Relational축·BM25 rerank default).
- 확증(§2): 실패1(ckg 얕은 BFS만 노출) + 실패2(cks 평탄화·벡터지배). file:line 전부 포함.
- 증거(§3): eval ckg-4way δ(0.367/환각10) < γ(0.80/환각0).
- 우선순위(§4): P0 라우팅 / P1 ckg path 노출 / P2 모티프 / P1.5 depth가시화 / P3 recall / P4 팩개선 / P5 데이터플로우.
- 첫 PR(§5): P0(coding-agent)+P1.5(ckg). cks·재인덱싱 무관.
- 차단/확인(§6): diagnose agent 존재, CKV parity 갭.

*문서 작성: Claude Opus 4.8 (1M) 세션, 2026-06-19. Tier 3 — 코드+git이 ground truth, 불일치 시 코드 우선.*
