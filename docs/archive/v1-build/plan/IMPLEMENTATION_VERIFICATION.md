# 구현 vs 계획 검토 보고서 (Implementation Verification)

> **Status (2026-06-05)**: **Superseded by R1′ refactor** (commit `76a285d`, 2026-06-02) + 후속 통합 검증 보고서 `docs/r1-refactor/06-integration-verification.md` (commit `feeecc6`, 2026-06-04). 본문은 R1′ 진입 시점의 빌드/테스트 기반 스냅샷으로 보존 — 모델 ID 권고(F-5), ChainBench 등록 권고(F-1)는 R1′ Step 2/6/8에서 처리됨. Phase 3/4 코드 격차는 R1′ Step 6의 자체 cks shim 삭제로 자연 소멸 (외부 `code-knowledge-graph` / `code-knowledge-vector` 저장소로 이관). 후속 검증·신규 격차는 06 문서 + `HANDOFF.md §6 / §7.2 P` 참조.
>
> 작성일: 2026-05-31
> 대상: `docs/plan/`, `docs/superpowers/specs/` 의 계획·설계 문서 vs 실제 코드
> 방법: Phase별 코드레벨 대조. Go 모듈(Phase 2·3·4)은 `go build`/`go test` 실행 검증, 플러그인(Phase 1·5·6·7)은 마크다운 정의·프론트매터·문서 정합성 대조.

---

## 총괄 판정

| Phase | 산출물 형태 | 빌드/테스트 | 계획 대비 | 한 줄 평 |
|---|---|---|---|---|
| 1. 스켈레톤+상태머신 | 플러그인(md) | N/A | ✅ 완전 (초과 구현) | 모든 기준 충족, 후속 Phase까지 선구현 |
| 2. Jira Gateway MCP | Go 코드 | ✅ build OK / 43 tests pass | ✅ 충실 | MCP 6툴·필터·ADF 모두 구현. 소소한 누락 2건 |
| 3. CKS-CKV(벡터) | Go 코드 | ✅ build OK / 22 tests pass | ⚠️ 대체로 완성, 실질 누락 3건 | 실제 Ollama 임베딩 O, 배치 임베딩 누락, 하이브리드 폴백전용 |
| 4. CKS-CKG(그래프) | Go 코드 | ✅ build OK / 9 tests pass (-race OK) | ⚠️ 동작하나 "타입기반" 주장 미달 | calls 이름기반, channels 셀프루프, incremental 없음 |
| 5. 에이전트 파이프라인 | 플러그인(md) | N/A | ✅ 충실 | 모든 단계 구현. 모델 ID 런타임 리스크 |
| 6. Evaluator+ChainBench | 플러그인(md) | N/A | ⚠️ Evaluator만 | ChainBench 미구현(외부 MCP)·.mcp.json 미등록 |
| 7. PR/리뷰/머지 | 플러그인(md) | N/A | ✅ 충실 | 전체 사이클 일관. 네이밍 이탈 2건 |

**핵심 결론**: `REVIEW_ISSUES.md`가 "23개 RI 전부 RESOLVED(2026-05-29 감사)"라고 선언하고 각 task 문서가 "✅ 완료"로 표기돼 있으나, 코드레벨로는 일부 수용기준(acceptance criteria)이 여전히 미충족이다. 특히 Phase 3·4·6에 실질 격차가 있다.

> 참고: 산출물 형태가 두 종류다. Phase 1·5·6·7은 **마크다운 에이전트/커맨드/스킬 정의(프롬프트 엔지니어링)** 이고, Phase 2·3·4만 **실행 가능한 Go 코드**다. 따라서 엄밀한 "코드레벨 검증"은 Phase 2·3·4에 가장 강하게 적용된다.

---

## 중요 발견 (우선순위 높음)

### 🔴 1. Phase 6 ChainBench — 이 저장소에는 구현체가 없음
- `grep -ri chainbench`로 코드/스크립트/설정 0건. ChainBench는 "기존 외부 MCP 서버" 전제 (RI-20, `docs/SETUP.md:165` "plugin doesn't ship ChainBench").
- 더 문제: `plugin/.mcp.json`에 `jira-gateway`, `cks`만 등록돼 있고 **`chainbench` 서버 미등록**. 따라서 `evaluator.md`가 호출하는 `mcp__chainbench__*` 툴은 이 저장소 구성에서 절대 resolve되지 않음 → Stage 4는 RI-20 pre-flight에 의해 항상 BLOCKED.
- 즉 Evaluator의 4-stage 중 1~3은 사양 완비, 4단계는 런타임에 동작 불가. RI-20 상태가 "RESOLVED (사양 단계 완료)"인 이유.

### 🔴 2. Phase 4 CKG — "타입 기반 정확 추출" 주장과 코드 불일치
- 스펙 §3.2 핵심인 `calls` 관계가 타입정보를 무시하고 이름 기반으로 해결됨 (`relations.go:657` `_ = info`, `lookupCallNode:671-684`가 전역 `HasSuffix` 스캔). → 동명 함수 오연결, 인터페이스→다중구현 엣지 없음.
- `channels` 엣지가 producer→consumer 매칭이 아니라 같은 노드 셀프루프 (`relations.go:631`).
- `code_snippet` 컬럼 존재하나 항상 빈 값, const/var 노드 생성 안 됨.
- `ckg_index`에 incremental 모드 없음, 파라미터도 스펙(`project_root`+`mode`)과 달리 `project_dir`만 존재.
- CKV+CKG "단일 AST 패스 통합"(스펙 §9) 미달 — CKG가 독립적으로 두 번 파싱.
- (정당한 이탈: 재귀 CTE → Go BFS, 문서화됨)

### 🟠 3. Phase 3 CKV — 배치 임베딩 누락 (수용기준이었음)
- P3-3 수용기준 "배치 임베딩 지원(throughput 향상)"이 미구현. 청크 단건 임베딩(`indexer.go:158`)뿐 → CPU 환경 대규모 인덱싱 시 RI-09 우려가 실제로 남음.
- "하이브리드(vector+BM25)"라 광고하나 실제로는 embedder 실패시에만 BM25 폴백, 점수 융합형 하이브리드 아님 (`search.go:99-117`). 툴 설명("Semantic + lexical")이 과장.
- 구조체 >50필드 분할(스펙 §2.3) 미구현, 통합테스트(`tests/integration/`) 부재.
- (긍정: 실제 Ollama API 호출 O, 차원 자동탐지, sqlite-vss→brute-force는 RI-07로 문서화된 정당한 이탈)

### 🟠 4. 전 플러그인 — 비표준 모델 ID 런타임 리스크
- 모든 에이전트 프론트매터가 `opus-4.7` / `sonnet-4.6` 사용 (스펙과는 일치). 그러나 실재하지 않는 모델 ID라 런타임에 resolve 실패 가능. 스펙 충실도는 100%지만 동작 리스크.

### 🟡 5. 문서-구현 드리프트 (TypeScript 잔재)
- `common-tasks.md`(COMMON-1), `RI-15`, `RI-22`가 여전히 "Jira Gateway MCP(TS)", `npx tsx ...src/index.ts`를 전제로 서술. 실제 Phase 2는 Go로 구현됨. RI-15 본문엔 Go 전환 언급이 있으나 예시 코드/일부 서술이 옛 TS 기준.

---

## Phase별 상세

### Phase 1 — ✅ 완전 구현 (초과)
모든 §7 완료기준 7/7, P1-2~P1-10 체크박스 전부 코드로 충족. plugin.json, /work·/review·/status·/merge, state-machine(7상태/8전이/checkpoint/resume), template-parse, stablenet-context, 훅 2건 모두 구현.
- 이탈(모두 상향): 스펙은 "스텁/disabled"를 요구했으나 실제론 hooks enabled+동작 스크립트, /merge 풀구현, 에이전트 풀스펙. → Phase 1 스펙 문구가 현 구현 대비 stale.

근거: `plugin/.claude-plugin/plugin.json:1-10`, `plugin/commands/{work,review,status,merge}.md`, `plugin/skills/state-machine/SKILL.md:121-399`, `plugin/hooks/hooks.json:1-24`.

### Phase 2 — ✅ 충실 (build OK, 43 tests pass, filter 81.7% cov)
- MCP 6툴(`jira_read_ticket`/`read_comments`/`search` 필터 + `add_comment`/`update_status`/`update_assignee` 패스스루) 이름까지 스펙 일치. 14개 패턴, Shannon 엔트로피(threshold 4.5), REDACT/BLOCK/WARN, ADF→Markdown(자체 변환기), 401/404/429 백오프(1→2→4s) 모두 구현·테스트.
- 누락: ① 스펙 §3.5의 `logs/sensitive-block-*.log` 감사파일 미작성(stderr만), ② "하드코딩 최소셋 폴백" 대신 fail-safe BLOCK으로 대체(보안상 더 강함이나 스펙과 다름). server/jira HTTP 핸들러 단위테스트 부재.

근거: `tools/jira-gateway-mcp/internal/server/server.go:33-65`, `internal/jira/client.go:56-262`, `internal/jira/adf.go:28-225`, `internal/filter/{engine,entropy,patterns,redactor}.go`, `shared/patterns.json`.

### Phase 3 — ⚠️ 대체로 완성 (build OK, 22 tests pass) — 위 🟠3 참조
- 구현됨: AST 청킹, 실 Ollama 임베딩+폴백(RI-08), SQLite store+코사인, BM25, 리랭커 4부스트, full/incremental 인덱싱+code_hash 캐시(RI-23), 민감필터 결과 적용, `ckv_search`/`ckv_index`.
- 미달: 배치 임베딩, 융합 하이브리드, 구조체 대형분할, git history(현재 placeholder, Phase 4 위임), 통합테스트.

근거: `tools/cks-mcp/internal/ckv/{chunker,embedder,store,bm25,search,reranker,indexer}.go`, `internal/server/server.go:31-141`.

### Phase 4 — ⚠️ 동작하나 정확도 미달 (build OK, 9 tests pass, -race clean) — 위 🔴2 참조
- 구현됨: 4테이블 store, 7관계 엣지 생성, git history+분류, 동시성 분석(goroutine/channel/mutex), BFS+depth+캡(max_nodes 200/edges 500), `ckg_query`/`ckg_impact`/`ckg_index`, 2-tier 타입/AST 폴백(RI-10), interface dispatch→unknown(RI-11).
- 미달: calls 타입해결, channels 카운터파트, const/var·code_snippet, incremental, shared-resource/deadlock(스텁), 단일 AST 패스 통합.

근거: `tools/cks-mcp/internal/ckg/{store,relations,concurrency,traversal,query,history,indexer}.go`, `internal/types/types.go`.

### Phase 5 — ✅ 충실
orchestrator/planner/implementer + evaluator 4에이전트 프론트매터 정상, 파이프라인 단계·상태전이·핸드오프·checkpoint·버그사이클 재진입·파이프라인 variant(code_review/release) 모두 구현. §8 완료기준 11/11.
- 이탈: 훅 `.sh`(스펙 `.js`, P5-9에 문서화), Jira는 `jira-gateway` 단일화(스펙 `atlassian`+`jira-gateway`), 모델 ID(🟠4), `READY_FOR_IMPL`이 orchestrator엔 있으나 state-machine 열거 상태엔 없음(흐름엔 무해).

근거: `plugin/agents/{orchestrator,planner,implementer,evaluator}.md`, `plugin/commands/{work,status}.md`, `plugin/skills/*/SKILL.md`.

### Phase 6 — ⚠️ Evaluator 사양만 완비 — 위 🔴1 참조
Evaluator 루브릭은 스펙 충실+초과(빌드 short-circuit, `-race` RI-21, JSON 출력). 단, 전부 자연어 프롬프트이며 파싱/스코어링 코드는 없음. ChainBench는 미구현·미등록.

근거: `plugin/agents/evaluator.md:1-512`, `plugin/.mcp.json`(chainbench 항목 없음).

### Phase 7 — ✅ 충실 (§9 수용기준 12/12)
PR생성(orchestrator §4)→리뷰수집/분류 7타입·4심각도(review.md)→버그수정 재계획(planner §6)→기존 PR 재발행(orchestrator §4.1)→게이트+squash merge(merge.md, 5게이트, RI-14 size-aware body) 전 사이클 일관. pr-sanitize가 모든 외부출력 경로에 연결.
- 이탈(경미): 재리뷰 `gh pr ready` → `--add-reviewer`로 구현, 산출물명 `plan-review-{N}` → `plan-fix-{N}`, pr-sanitize 로그경로 plumbing 미정의.

근거: `plugin/commands/{review,merge}.md`, `plugin/agents/orchestrator.md:122-218`, `plugin/skills/pr-sanitize/SKILL.md`.

---

## 권고 (우선순위순)

1. **Phase 6/4의 "✅ 완료" 표기 보정** — task 문서 헤더와 실제 코드 격차를 명시(특히 ChainBench 미구현, CKG calls 이름기반).
2. **모델 ID 검증** — `opus-4.7`/`sonnet-4.6`를 실재 ID(`claude-opus-4-*`/`claude-sonnet-4-*`)로 교체 검토. 미수정 시 런타임 실패 가능.
3. **Phase 3 배치 임베딩 구현** 또는 수용기준에서 공식 제외 — 현재는 "완료" 표기와 불일치.
4. **Phase 4 calls 타입해결** 도입(이미 로드한 `types.Info` 활용) — CKG 정확도의 핵심.
5. **문서 TS 잔재 정리** — common-tasks/RI-15/RI-22의 TypeScript 서술을 Go 기준으로 갱신.
6. **`.mcp.json`에 chainbench 등록 경로 또는 "외부설정 필요" 명시** — Phase 6 Stage 4가 항상 BLOCK되는 현 구성 안내.

---

## 종합

- Phase 1·2·5·7: 계획대로(또는 그 이상) 견고하게 구현.
- Phase 3·4: 동작하지만 핵심 정확도/성능 기능 일부 미달.
- Phase 6: Evaluator 사양만 완비, ChainBench는 외부 의존으로 미구현.
