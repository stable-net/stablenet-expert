# Review Issues

> WORK_BREAKDOWN.md 검토에서 발견된 문제점 목록.
> 각 항목은 해당 Phase 작업 진행 시 해결한다.

## 상태

| 상태 | 의미 |
|------|------|
| `OPEN` | 미해결 |
| `RESOLVED` | 해결 완료 (해결 방법 + 커밋/문서 참조) |
| `DEFERRED` | 의도적으로 후순위 (이유 명시) |

## 최종 감사 (2026-05-29) — 보정 (2026-06-01) — R1′ 재평가 (2026-06-05)

> ⚠️ 본 문서의 RI 본문 다수가 `tools/cks-mcp/...` 코드 경로를 *증거*로 인용함. 2026-06-02 R1′ Step 6 (commit `76a285d`)이 그 디렉토리를 **통째로 삭제**(자체 cks shim 폐기, 외부 `code-knowledge-system`으로 위임)함으로써 *증거 경로*는 부재 상태가 됨. RI의 **결정·근거·해결 내용은 그대로 유효**하지만, 후속 검증은 외부 sibling repo (`code-knowledge-graph`, `code-knowledge-vector`, `code-knowledge-system`)에서 수행해야 함. 본 문서 RI별 갱신은 별도 작업으로 분리.

### 2026-05-29 → 2026-06-01 보정

| RI | 2026-05-29 선언 | 2026-06-01 실제 | 보정 작업 |
|----|---------------|---------------|---------|
| RI-09 | RESOLVED | PARTIALLY RESOLVED | F-4 배치 임베딩 |
| RI-10 | RESOLVED | PARTIALLY RESOLVED | F-2 calls 타입 기반 |
| RI-20 | RESOLVED (사양 단계 완료) | OPEN | F-1 chainbench 등록/안내 |
| 나머지 20개 | RESOLVED | RESOLVED 유지 | 해당 없음 |

### 2026-06-01 → 2026-06-05 R1′ 재평가

| RI | 2026-06-01 상태 | 2026-06-05 R1′ 후 | 경로 |
|----|--------------|----------------|------|
| RI-09 | PARTIALLY | **외부 ckv로 이관** | 자체 코드 삭제. 외부 `code-knowledge-vector` 02-plan Part D #4가 throughput 후속 추적 (`F-4 외부 이슈`) |
| RI-10 | PARTIALLY | **외부 ckg로 이관** | 자체 코드 삭제. 외부 `code-knowledge-graph` `statements.go:206`이 이미 typed (`types.Info` 사용) |
| RI-20 | OPEN | **RESOLVED (구조)** | R1′ Step 6: `.mcp.json` chainbench 등록. Step 8: evaluator §7.0 도구 이름 C1 정렬. 단 04 D1 (`chainbench_report{format:"json"}` 실 JSON) 출하 대기 |
| RI-15 (TS 잔재) | RESOLVED | **본문 갱신** | F-7 정리 — TypeScript 서술을 Go 기준으로 명시 |
| RI-22 (TS 잔재) | RESOLVED | **본문 갱신** | F-7 정리 — 동일 |
| 나머지 18개 | RESOLVED | RESOLVED 유지 | 증거 경로 stale 표시는 본 §최종 감사에 단일 안내로 처리 |

R1′ 이후 전체 23개 RI 중 18개 RESOLVED (그대로), 2개 외부 이관 (RI-09/10), 1개 RESOLVED 구조 완료 (RI-20), 2개 본문 갱신 (RI-15/22).

| 범주 | 항목 |
|------|------|
| Phase 1 (스켈레톤) | RI-01, RI-02, RI-03 |
| Phase 2 (Jira Gateway) | RI-04, RI-05, RI-06, RI-15 |
| Phase 3 (CKV) | RI-07, RI-08, RI-09, RI-23 |
| Phase 4 (CKG) | RI-10, RI-11 |
| Phase 5 (Orchestration) | RI-12, RI-13, RI-17, RI-18, RI-19 |
| Phase 6 (Evaluator) | RI-20, RI-21 |
| Phase 7 (PR/Merge) | RI-14 |
| 공통 | RI-16 (SETUP.md), RI-22 (PATTERNS_PATH) |

런타임 실증이 필요한 항목 (사용자 환경 종속):
- **RI-20**: 실제 ChainBench MCP의 tool 이름이 spec과 일치하는지는 §7.0 pre-flight가 첫 실행 시 자동 검증·BLOCKED.
- **RI-08, RI-09**: Ollama 가용성·인덱싱 시간은 호스트 자원에 의존. BM25 폴백 + code_hash 캐시로 worst-case 흡수.

---

## RI-01. MCP 서버 등록 설정 누락 [Phase 1]

**상태**: `RESOLVED` — `plugin/.mcp.json`에 `jira-gateway`(`tools/jira-gateway-mcp/bin/jira-gateway-mcp`)와 `cks`(`tools/cks-mcp/bin/cks-server`) 두 서버 등록. `${CLAUDE_PLUGIN_ROOT}` 변수 사용, env block에 Jira 자격증명/CKS 인덱스 경로/패턴 파일 경로 주입. 커밋 `c1a92cc`(plugin 구조 전환) + `d41684e`(tools/ 이동).

**문제**: plugin/mcp/ 에 Jira Gateway MCP와 CKS MCP를 Claude Code에 연결하는 설정이 없다. 플러그인의 MCP 설정(plugin/mcp/) 또는 프로젝트의 `.mcp.json`에 서버를 등록해야 한다.

**영향**: 에이전트가 MCP tool을 호출할 수 없어 전체 파이프라인이 동작하지 않음.

**해결 방향**:
- `.mcp.json`을 프로젝트 루트에 생성하여 두 MCP 서버(jira-gateway, cks) 등록
- 각 서버의 실행 명령, 환경변수, 인자 정의
- ChainBench MCP는 기존 서버이므로 별도 등록 경로

**해결 시점**: Phase 2 시작 시 (P2-1과 함께)

---

## RI-02. ANALYSIS/PLANNING 중간 상태 복구 경로 불완전 [Phase 1]

**상태**: `RESOLVED` — `plugin/skills/state-machine/SKILL.md §2.6 get_resume_point()`이 ANALYSIS/PLANNING/DESIGN 각 단계의 부분 산출물(analysis.md/related-code.json/plan.md/design-v{N}.md)을 검사해서 `sub_status`(`fresh|partial|review_pending`) + `existing_artifacts` + `recommendation`을 반환한다. 커밋 `b5736d6`.

**문제**: `get_resume_point()`는 IMPLEMENTATION 단계의 step/checkpoint 복구만 상세히 정의되어 있다. ANALYSIS나 PLANNING 중간에 중단된 경우, "현재 상태 반환"만 하고 구체적으로 어디서부터 재개하는지 정의가 없다.

**영향**: ANALYSIS 중간 중단 시, CKV 검색까지 완료했지만 CKG는 미완료인 상태에서 복구하면 CKV를 불필요하게 다시 실행하게 됨.

**해결 방향**:
- ANALYSIS/PLANNING/DESIGN 각 단계 내부에도 세부 진행 상태를 state.json에 기록
  - 예: `states.ANALYSIS.sub_step = "ckv_done"` → CKG부터 재개
- 또는, 이 단계들은 시간이 짧으므로 "해당 단계 처음부터 재실행"을 허용
  - 이 경우 재실행 비용(CKV 재검색 등)이 수용 가능한지 판단 필요

**해결 시점**: Phase 5 (P5-2, P5-3에서 Planner 구현 시)

---

## RI-03. Phase 2 미완성 시 /work 테스트 불가 [Phase 1]

**상태**: `RESOLVED` — `plugin/commands/work.md`가 `--local <path>` 옵션을 지원. argument-hint·§5.1·완료 기준 체크리스트에 모두 반영. MCP 없이 로컬 JSON 파일을 ticket.json으로 직접 사용 가능 (SETUP.md §7 smoke test에서 활용). 커밋 `bfee7ca`.

**문제**: /work 커맨드가 Jira Gateway MCP를 호출하여 티켓을 읽는 것이 첫 단계인데, Phase 2가 아직 구현되지 않은 상태에서는 /work를 테스트할 수 없다.

**영향**: Phase 1을 독립적으로 검증할 수 없음.

**해결 방향**:
- /work에 `--local` 또는 `--mock` 옵션 추가: 로컬 JSON 파일을 ticket.json으로 직접 제공
  - 예: `/work STABLE-1234 --file ./test-ticket.json`
- Phase 1 테스트 시에는 이 옵션으로 MCP 의존 없이 파이프라인 전체 흐름 검증
- Phase 2 완료 후에는 기본 경로(MCP)로 동작

**해결 시점**: Phase 1 (P1-2 구현 시)

---

## RI-04. Jira API v3의 ADF(Atlassian Document Format) 처리 [Phase 2]

**상태**: `RESOLVED` — `tools/jira-gateway-mcp/internal/jira/adf.go` 자체 ADF→Markdown 변환기 구현 (HTML 의존성 제거). `adf_test.go`에 paragraph/heading/bullet list/ordered list/task list/code block 등 ≥8 노드 타입 테스트. `client.GetIssue()`에서 description 필드를 ADF로 받아 변환. 권장안 Option A(HTML 경유) 대신 Option B(ADF 직접 파싱)로 더 가벼운 의존성 그래프 확보. 커밋 `6d1b700`.

**문제**: Jira Cloud API v3는 `description` 필드를 평문 markdown이 아닌 ADF(JSON 기반 문서 포맷)로 반환한다. template-parse skill은 markdown 섹션 헤더 기반 파싱을 전제하고 있어, ADF를 직접 파싱하거나 변환하는 처리가 필요하다.

**영향**: template-parse가 description을 파싱할 수 없어 work_type 식별 실패.

**해결 방향**:
- **Option A**: API 호출 시 `?expand=renderedFields`로 HTML 렌더링 버전을 받아서 HTML → markdown 변환
- **Option B**: ADF JSON을 직접 파싱하여 텍스트 추출 → markdown으로 변환
- **Option C**: Jira 티켓 작성 시 description을 "텍스트 모드"로 작성하도록 가이드 (markdown 그대로 저장되는 경우도 있음)

**권장**: Option A. `renderedFields`는 Jira가 HTML로 변환해주므로, HTML → markdown 변환 라이브러리(예: `turndown`)를 사용하면 간단.

**해결 시점**: Phase 2 (P2-2 Jira 클라이언트 구현 시)

---

## RI-05. Jira transition 이름의 프로젝트별 차이 [Phase 2]

**상태**: `RESOLVED` — `tools/jira-gateway-mcp/internal/jira/client.go:140 TransitionIssue()`이 case-insensitive lookup으로 1) transition name 2) target status name 3) statusCategory key 순으로 해결. `jira_update_status` MCP tool description에 "Transition name, status name, or statusCategory key" 명시. 별도 설정 파일 없이 프로젝트별 명명 차이를 흡수. 커밋 `6d1b700`.

**문제**: `jira_update_status("In Review")`에서 "In Review"는 Jira workflow의 transition name인데, 이는 프로젝트마다 다르다. 하드코딩하면 다른 Jira 프로젝트 설정에서 실패한다.

**영향**: Jira 상태 변경 호출 실패.

**해결 방향**:
- transition 이름을 설정 파일로 분리:
  ```jsonc
  // .coding-agent/config.json
  {
    "jira": {
      "transitions": {
        "in_progress": "In Progress",
        "in_review": "In Review",
        "complete": "Done"
      }
    }
  }
  ```
- 또는, 먼저 `GET /rest/api/3/issue/{id}/transitions`로 가용 transition 목록을 조회한 후, 이름이 아닌 의미(category)로 매칭
  - Jira transition에는 `to.statusCategory`가 있음: "To Do", "In Progress", "Done"

**해결 시점**: Phase 2 (P2-2 Jira 클라이언트 구현 시)

---

## RI-06. Sensitive Filter fail-safe 시 MCP 응답 형태 미정의 [Phase 2]

**상태**: `RESOLVED` — `tools/jira-gateway-mcp/internal/filter/engine.go`가 내부 오류 시 BLOCKED 결과(empty text + fail-safe block 로그)를 반환. `server.go blockedResult()`은 `SENSITIVE_CONTENT_BLOCKED` 에러 코드 + `detected_patterns` + `recommendation` + `recoverable=false`로 구조화된 응답. `engine_test.go`의 `TestScanAndFilter_FailSafe`가 BLOCKED + empty text 보장. 커밋 `6d1b700`.

**문제**: P2-3에서 "필터 엔진 자체 예외 시 차단"이라 했는데, 이때 MCP tool 응답으로 무엇을 반환하는지 정의되지 않았다. Agent 입장에서는 tool 호출 실패로 인식되며, 재시도 로직이 없으면 파이프라인이 멈춘다.

**영향**: 필터 버그 시 파이프라인 교착.

**해결 방향**:
- fail-safe 발동 시 명확한 에러 응답 반환:
  ```json
  {
    "error": "FILTER_ENGINE_ERROR",
    "message": "민감정보 필터 실행 중 오류가 발생했습니다. 안전을 위해 데이터를 차단합니다.",
    "recoverable": false
  }
  ```
- Orchestrator가 이 에러를 감지하면 → BLOCKED 상태로 전이 + 유저에게 보고
- 유저가 필터 문제를 해결한 후 /work로 재시작

**해결 시점**: Phase 2 (P2-3 필터 엔진 구현 시)

---

## RI-07. sqlite-vss의 Go 바인딩 호환성 [Phase 3]

**상태**: `RESOLVED` — `tools/cks-mcp/go.mod`가 `modernc.org/sqlite v1.51.0` (CGo-free) 채택. `internal/ckv/store.go:17` 주석에 결정 근거 명시("sqlite-vss is not CGo-free, and the project size justifies brute-force MVP"). 벡터는 BLOB(float32)로 저장, `VectorSearch()` + `cosineSimilarity()`로 brute-force 계산. 향후 외부 vector DB 마이그레이션 경로 명시. 커밋 `292e7dc`.

**문제**: sqlite-vss는 C 확장이며, Go의 CGo-free SQLite 드라이버(`modernc.org/sqlite`)와 호환되지 않는다. CGo 기반 드라이버(`mattn/go-sqlite3`)를 쓰면 빌드가 복잡해진다.

**영향**: 벡터 검색 구현 방식 결정에 영향.

**해결 방향**:
- **MVP**: brute-force cosine similarity (이미 P3-4에 대안으로 명시됨)
  - 20000 청크 × 768차원: 단일 쿼리 ~10-50ms (충분히 빠름)
  - 벡터를 BLOB으로 저장, 쿼리 시 전체 로드 후 계산
- **향후**: 규모가 커지면 Qdrant/Milvus 같은 외부 벡터 DB로 마이그레이션
- `modernc.org/sqlite` 유지 (CGo-free, 크로스 플랫폼 빌드 용이)

**해결 시점**: Phase 3 (P3-4 Vector Store 구현 시)

---

## RI-08. Ollama 미설치 환경에서 CKV 동작 불가 [Phase 3]

**상태**: `RESOLVED` — `tools/cks-mcp/internal/ckv/bm25.go` BM25 lexical 폴백 구현 (k1=1.2, b=0.75, signature+godoc+code 토큰화). `search.go retrieve()`는 embedder=nil 또는 임베딩 호출 실패 시 자동으로 `bm25_fallback`으로 전환. `ckv_search` 응답의 `engine` 필드로 fallback 사용 여부를 클라이언트가 식별 가능. SETUP.md §9.4에 Ollama 미연결 시 동작 안내. 커밋 `292e7dc`.

**문제**: P3-3에서 Ollama + nomic-embed-text를 임베딩 Tier 1으로 설정했는데, go-stablenet 개발 환경에 Ollama가 설치되어 있지 않을 수 있다. 임베딩 모델이 없으면 CKV 전체가 동작하지 않는다.

**영향**: CKV가 없으면 ANALYSIS 단계가 동작 불가 → 전체 파이프라인 중단.

**해결 방향**:
- **폴백 계층**:
  1. Ollama 사용 가능 → 벡터 검색 (기본)
  2. Ollama 없음 → 키워드 기반 검색으로 폴백
     - BM25 또는 단순 TF-IDF
     - 코드 청크의 심볼명/godoc/시그니처를 텍스트 인덱스로 구축
     - 정확도는 낮지만 파이프라인은 동작
- /work 시작 시 Ollama 연결 체크 → 미연결 시 경고 + 폴백 모드 안내
- 초기 셋업 가이드(RI-16)에 Ollama 설치 포함

**해결 시점**: Phase 3 (P3-3 Embedding 구현 시)

---

## RI-09. 인덱싱 시간 추정이 낙관적 [Phase 3]

**상태**: `PARTIALLY RESOLVED` (2026-06-01 재평가) — 3가지 완화 중 (1) code_hash 캐시 + (2) 진행률 + (3) modules 우선순위는 그대로 유효. 그러나 `IMPLEMENTATION_VERIFICATION.md`가 발견: **배치 임베딩 미구현** (`indexer.go:158` 단건 호출만). P3-3 수용 기준 "배치 임베딩 지원(throughput 향상)" 미충족 → CPU 환경 첫 인덱싱 시 worst-case 시간(~67분 추정)이 그대로 남음.

**보정 작업**: HANDOFF.md §7.1 F-4 — Ollama `/api/embed`의 배치 인자 활용해 N개 청크 묶음 호출. 완료 시 본 RI를 `RESOLVED`로 복원.

**문제**: P3-7에서 "~5000 파일 → 10-30분"으로 추정했으나, Ollama 로컬 임베딩은 CPU 환경에서 청크당 수백ms가 걸린다. 20000 청크 × 200ms = 약 67분. GPU 없는 환경에서는 예상보다 훨씬 오래 걸릴 수 있다.

**영향**: 첫 /work 실행 시 full index 대기 시간이 과도하게 길어질 수 있음.

**해결 방향**:
- **배치 임베딩**: Ollama에 여러 청크를 한 번에 전송 (가능한 경우)
- **점진적 인덱싱**: 전체 인덱싱을 백그라운드로 실행하고, 현재 티켓에 관련된 패키지만 우선 인덱싱
  - scope.modules가 "consensus"이면 consensus/ 하위만 먼저 인덱싱
  - 나머지는 백그라운드에서 계속
- **캐싱**: 임베딩 결과를 캐시하여 재인덱싱 시 변경된 청크만 재계산
- 인덱싱 중 진행률 표시 (N/total 청크, 예상 남은 시간)

**해결 시점**: Phase 3 (P3-7 Indexing Pipeline 구현 시)

---

## RI-10. AST Relation Extractor의 전체 빌드 의존 [Phase 4]

**상태**: `PARTIALLY RESOLVED` (2026-06-01 재평가) — Tier 1/Tier 2 폴백 구조 자체는 구현됨 (`relations.go` extractTyped/extractASTOnly). 그러나 `IMPLEMENTATION_VERIFICATION.md` (2026-05-31)이 발견: **Tier 1 진입 후에도 `calls` 추출에서 `_ = info`로 타입 정보를 명시적으로 무시 (`relations.go:657`)하고 이름 기반 `lookupCallNode`(`relations.go:671-684`)로 fallback**. 결과적으로 동명 함수 오연결·interface→구현 엣지 부재. "타입 기반 정확 추출" 본래 의도 미달.

**보정 작업**: HANDOFF.md §7.1 F-2 — `types.Info`를 사용해 `*types.Func` resolve, `types.Implements`로 interface dispatch 처리. 완료 시 본 RI를 `RESOLVED`로 복원.

**원래 해결책 (Tier 2 폴백)**: 그대로 유효 — packages.Load 실패 시 AST-only 폴백 동작.

**문제**: P4-2에서 `packages.Load`로 cross-package 타입 resolve를 하려면 go-stablenet의 전체 의존성(geth 포함)을 빌드할 수 있어야 한다. 빌드 환경이 갖춰지지 않으면 `packages.Load`가 실패하며, 타입 정보 없이 AST만으로 관계를 추출해야 한다.

**영향**: `calls`에서 인터페이스 통한 간접 호출 resolve 불가, `implements` 관계 추출 불가 → CKG 정확도 저하.

**해결 방향**:
- **2-tier 접근**:
  1. `packages.Load` 성공 시 → 풀 타입 정보로 정확한 관계 추출
  2. `packages.Load` 실패 시 → AST only 모드로 폴백
     - `calls`: 함수명/메서드명 기반 텍스트 매칭 (정확도 낮음)
     - `implements`: 구조체의 메서드 목록과 인터페이스 메서드 목록 텍스트 비교
     - 결과에 `confidence: "low"` 태그 추가
- 사전 조건 확인: `go build ./...`가 성공하는지 먼저 체크
- 실패 시 유저에게 빌드 환경 셋업 안내

**해결 시점**: Phase 4 (P4-2 구현 시)

---

## RI-11. Concurrency Analyzer 정적 분석 한계 [Phase 4]

**상태**: `RESOLVED` — `tools/cks-mcp/internal/ckg/concurrency.go`가 interface dispatch/reflect-based goroutine 감지 시 `confidenceDowngraded=true` 플래그 후 `risk_assessment.race_condition_risk = "unknown"`으로 기록. 정적 분석 한계를 명시적으로 표면화하여 Evaluator(RI-21)가 동적 검증으로 보완할 수 있게 함. 커밋 `15b75b2`.

**문제**: goroutine이 인터페이스를 통해 실행되거나, reflect/unsafe로 동작하는 경우 정적 분석으로 추적이 불가능하다. geth에는 이런 패턴이 존재한다.

**영향**: 동시성 영향 분석이 불완전할 수 있음 → 수정 후 예상치 못한 race condition 발생 가능.

**해결 방향**:
- "best-effort" 범위를 명확히 정의:
  - 분석 가능: 직접 `go func()`, 직접 `go obj.Method()`, 명시적 channel/mutex
  - 분석 불가: interface dispatch를 통한 goroutine, reflect 기반, dynamic dispatch
- 분석 불가능한 경우 출력에 명시:
  ```json
  {
    "risk_assessment": {
      "race_condition_risk": "unknown",
      "note": "인터페이스 기반 goroutine dispatch가 감지되어 정적 분석 한계. go test -race 실행을 권장합니다."
    }
  }
  ```
- Evaluator(Phase 6)에서 `go test -race`를 보조 수단으로 실행하여 동적 검증 보완

**해결 시점**: Phase 4 (P4-4 구현 시)

---

## RI-12. Orchestrator 테스트를 위한 MCP mock [Phase 5]

**상태**: `RESOLVED` — RI-03의 `/work --local <path>` 옵션과 통합. orchestrator는 ticket.json이 작업 폴더에 이미 존재하면 Jira 호출 스킵, ANALYSIS도 manually placed analysis.md/related-code.json fixture를 그대로 사용. SETUP.md §7 smoke test가 Jira/CKS MCP 없이 Phase 1 파이프라인 검증 절차를 안내. 커밋 `bfee7ca` + `eb7b85a`.

**문제**: Orchestrator가 동작하려면 Jira Gateway MCP + CKS MCP가 모두 필요한데, Phase 2-4가 완료되기 전에는 Orchestrator를 테스트할 수 없다.

**영향**: Phase 5를 Phase 2-4 완료 전에 개발/테스트할 수 없음.

**해결 방향**:
- **mock 아티팩트 세트**: 미리 생성된 ticket.json, analysis.md, related-code.json, plan.md, design-v1.md를 테스트 fixtures로 준비
- Orchestrator 테스트 시 이 fixtures를 작업 폴더에 배치하고, 각 상태에서의 전이를 검증
- MCP 호출이 필요한 부분은 에이전트 프롬프트에서 "mock 모드: MCP 호출 대신 {path}의 파일을 사용" 지시
- RI-03의 `--local` 옵션과 연계

**해결 시점**: Phase 5 (P5-1 구현 시)

---

## RI-13. Agent 간 에러 전파 및 아티팩트 완전성 검증 [Phase 5]

**상태**: `RESOLVED` — `plugin/skills/state-machine/SKILL.md §3 transition()` 가드가 단순 파일 존재 외에 필수 섹션 존재(analysis.md: 도메인/관련 코드/리스크, related-code.json: 비어 있지 않은 results 배열)를 검사. 누락 시 transition 거부 + state.json의 `failure_log`에 부족 항목 기록. orchestrator §3.x가 에이전트 호출 실패 → BLOCKED 전이로 이어지는 경로를 명시. 커밋 `b5736d6` + `eb7b85a`.

**문제**: Planner 내부에서 CKS MCP 호출이 실패하면 analysis.md가 불완전한 상태로 생성될 수 있다. 현재 전이 조건은 "파일 존재"만 체크하므로, 불완전한 파일로도 다음 단계로 전이될 수 있다.

**영향**: 불완전한 분석 결과를 기반으로 plan이 수립되어 잘못된 코드 수정으로 이어질 수 있음.

**해결 방향**:
- 아티팩트 완전성 검증을 전이 조건에 추가:
  ```
  ANALYSIS → PLANNING 전이 조건:
    ✅ analysis.md 존재
    ✅ analysis.md에 필수 섹션 존재 (도메인 분류, 관련 코드, 리스크 평가)
    ✅ related-code.json 존재
    ✅ related-code.json에 results 배열이 비어있지 않음
  ```
- 에이전트 내부에서 MCP 호출 실패 시:
  - 재시도 (최대 2회)
  - 재시도 실패 → 에이전트가 불완전 상태를 명시적으로 보고
  - state.json에 `error` 필드 기록 → Orchestrator가 감지하여 유저에게 보고

**해결 시점**: Phase 5 (P5-1, P5-2 구현 시)

---

## RI-14. Squash merge commit body 길이 [Phase 7]

**상태**: `RESOLVED` — `plugin/commands/merge.md §4.2` size-aware strategy 구현. `plan_progress.total_steps <= 10`이면 개별 step 전체 나열, 11+면 [Interface, Implementation, Tests, Docs, Misc] 5개 카테고리 버킷으로 그룹화 후 `* {bucket} ({N} commits)` 요약. pr-sanitize 적용 후 `gh pr merge --squash` 전달. 커밋 `459a7ad`.

**문제**: step이 많은 작업(10+ step)에서 모든 개별 커밋 메시지를 나열하면 squash commit body가 과도하게 길어진다.

**영향**: git log 가독성 저하. GitHub PR merge 시 body 길이 제한 가능성.

**해결 방향**:
- 기본: step 10개 이하 → 전체 커밋 목록 나열
- 10개 초과 → 카테고리별 요약:
  ```
  STABLE-1234: staking reward overflow 방지
  
  * 인터페이스 변경 (3 commits)
  * 로직 구현 (5 commits)
  * 테스트 추가 (4 commits)
  
  Jira: {url}
  PR: #{number}
  ```

**해결 시점**: Phase 7 (P7-5 구현 시)

---

## RI-15. MCP 서버 설정 파일 [공통]

**상태**: `RESOLVED` — `plugin/.mcp.json`이 빌드 산출물을 직접 가리키도록 구성됨. **언어 선택은 처음부터 Go**(이 RI 작성 시점에는 TypeScript 안도 고려했으나 채택하지 않음 — 단일 실행 파일·CGo-free·빠른 시작·geth 생태계 동일 언어). ChainBench MCP는 별도 사용자 설정으로 분리. 커밋 `c1a92cc` + `d41684e`. **R1′ Step 6 (2026-06-02, `76a285d`) 후**: cks 항목은 자체 `tools/cks-mcp/bin/...`에서 외부 `${CKS_MCP_BIN}` 바이너리로 전환됨. chainbench 항목도 R1′ Step 6에서 등록(`chainbench-mcp` 명령). 자세한 현 구성은 `HANDOFF.md §4 저장소 레이아웃` + `docs/SETUP.md §4.2/§5` 참조.

**문제**: 프로젝트에 `.mcp.json`이 없다. Jira Gateway MCP, CKS MCP, ChainBench MCP를 Claude Code에서 사용하려면 MCP 서버 등록이 필요하다.

**영향**: RI-01과 동일 — MCP tool 호출 불가.

**해결 방향**:
- `.mcp.json` 생성:
  ```jsonc
  {
    "mcpServers": {
      "jira-gateway": {
        "command": "${CLAUDE_PLUGIN_ROOT}/../tools/jira-gateway-mcp/bin/jira-gateway-mcp",
        "env": {
          "JIRA_BASE_URL": "",
          "JIRA_API_TOKEN": "",
          "JIRA_USER_EMAIL": ""
        }
      },
      "cks": {
        "command": "${CKS_MCP_BIN}",
        "args": ["-config", "${CKS_CONFIG}"]
      },
      "chainbench": {
        "command": "chainbench-mcp",
        "env": { "CHAINBENCH_DIR": "${CHAINBENCH_DIR}" }
      }
    }
  }
  ```
- RI-01과 통합 처리

**해결 시점**: Phase 2 시작 시 (RI-01과 함께)

---

## RI-16. 초기 셋업 가이드 부재 [공통]

**상태**: `RESOLVED` — `docs/SETUP.md` 작성 완료. 10개 섹션(prerequisites → 빌드 → env → 플러그인 설치 → 인덱싱 → smoke test → 실제 워크플로우 → 트러블슈팅). Troubleshooting §9에 RI-08/RI-13/RI-20/RI-22 발생 시 해결 방법 명시.

**문제**: 플러그인을 처음 사용하는 개발자를 위한 셋업 가이드가 없다. Jira API token, Ollama 설치, ChainBench MCP 연결, go-stablenet 경로 등 사전 설정이 필요하다.

**영향**: 온보딩 마찰. 설정 누락으로 인한 런타임 에러.

**해결 방향**:
- `docs/SETUP.md` 작성:
  1. 플러그인 설치
  2. Jira 설정 (API token 발급, 환경변수 설정)
  3. Ollama 설치 + nomic-embed-text 모델 pull
  4. ChainBench MCP 연결 확인
  5. go-stablenet 프로젝트 경로 설정
  6. 첫 인덱싱 실행 (`/work --index-only`)
  7. 동작 확인 (`/status`)
- `/work` 첫 실행 시 누락 설정을 자동 감지하고 안내하는 로직

**해결 시점**: Phase 2 완료 후 (MCP 서버들이 동작하는 시점에)

---

## RI-17. /merge 커맨드의 Phase 배치 불일치 [Phase 1 / Phase 7]

**상태**: `RESOLVED` — Phase 1 P1-5에서는 `/merge` 커맨드 등록(auto-discovery용 frontmatter)만 수행하고 실제 로직은 Phase 7 P7-5에서 구현. 현재 `plugin/commands/merge.md`는 Phase 7 §6 사양만 보유 (Phase 1 stub 충돌 없음). 커밋 `459a7ad`.

**문제**: P1-5에서 /merge 커맨드를 Phase 1에 배치했지만, /merge가 동작하려면 PR URL(Phase 6 EVALUATION_PASS 이후 생성)이 필요하다. Phase 1에서는 PR이 존재하지 않으므로 /merge를 테스트할 수 없다.

**영향**: Phase 1의 /merge 구현이 실제로는 Phase 7까지 검증 불가.

**해결 방향**:
- Phase 1에서는 /merge를 **커맨드 등록(auto-discovery) + 스텁**만 포함
- /merge의 로직 구현은 Phase 7(P7-5)에서 수행
- P1-5의 상세 로직을 P7-5로 이동하고, P1-5는 스텁으로 축소

**해결 시점**: Phase 1 (P1-5 스텁화) + Phase 7 (P7-5 구현)

---

## RI-18. Code Review 파이프라인의 review-report.md 미정의 [Phase 5]

**상태**: `RESOLVED` — `orchestrator.md §6` "code_review" variant 정의: `TICKET_INTAKE → ANALYSIS → PLANNING(review-report) → COMPLETION`. `planner.md §7` review-report.md 포맷(리뷰 대상/Findings[severity]/Suggestions/Risk) + Jira 코멘트 게시 흐름 정의. Planner는 `mode=code_review`로 디스패치되어 §3 light ANALYSIS 후 §7로 점프. design/implementation/evaluation 단계 건너뜀. 커밋 `eb7b85a`.

**문제**: P5-8에서 Code Review 유형은 "ANALYSIS → PLANNING(리뷰 리포트) → COMPLETION"으로 분기한다고 정의했지만, 리뷰 리포트(review-report.md)의 구체적 포맷과 Planner가 어떻게 "리뷰 모드"로 전환하는지 정의되지 않았다.

**영향**: Code Review 티켓 처리 시 Planner가 무엇을 생성해야 하는지 불명확.

**해결 방향**:
- review-report.md 포맷 정의:
  ```markdown
  # Code Review Report: {TICKET-ID}
  ## 리뷰 대상
  ## 발견 사항 (Findings)
  ### [severity] {finding title}
  - 위치: {file}:{line}
  - 설명: ...
  - 권장 조치: ...
  ## 개선 제안 (Suggestions)
  ## 리스크 평가
  ```
- Planner 내부에서 `ticket_type == "code_review"` 시:
  - ANALYSIS까지는 동일 (CKV/CKG 검색)
  - PLANNING에서 plan.md 대신 review-report.md 생성
  - design/implementation/evaluation 단계 건너뜀

**해결 시점**: Phase 5 (P5-8 구현 시)

---

## RI-19. Release 파이프라인 상세 미정의 [Phase 5]

**상태**: `RESOLVED` — `orchestrator.md §6` "release" variant 정의: `TICKET_INTAKE → ANALYSIS → EVALUATION → COMPLETION(tag + CHANGELOG)`. `planner.md §8` release-summary.md 포맷(버전/포함 STABLE-xxx 목록/Release checklist) 정의. COMPLETION에서 `git tag v{version}` + `CHANGELOG.md` 업데이트 + Jira Complete. 안전장치: orchestrator §유저 확인 가드("Never tag or push tags without user confirmation"). 커밋 `eb7b85a`.

**문제**: P5-8에서 Release 유형은 "ANALYSIS → EVALUATION → COMPLETION(태그)"으로 분기한다고 정의했지만, 구체적으로 ANALYSIS에서 "포함 변경사항 취합"이 어떻게 동작하는지, COMPLETION에서 태깅/CHANGELOG 생성의 상세가 없다.

**영향**: Release 티켓 처리 시 구체적 동작이 불명확.

**해결 방향**:
- ANALYSIS (Release 모드):
  - 티켓의 "포함 변경사항" 필드에서 STABLE-xxx 목록 추출
  - 각 티켓의 작업 폴더에서 변경 요약 수집
  - 전체 변경 요약 문서 생성
- EVALUATION (Release 모드):
  - unit test + lint + security + ChainBench 전체 실행 (변경 코드가 아닌 전체 기준)
- COMPLETION (Release 모드):
  ```
  git tag v{version}
  git push origin v{version}
  CHANGELOG.md 업데이트 (포함 변경사항 목록)
  Jira 티켓 → Complete
  ```

**해결 시점**: Phase 5 (P5-8 구현 시)

---

## RI-20. ChainBench MCP 인터페이스 검증 [Phase 6]

**상태**: `OPEN` (2026-06-01 재평가) — `IMPLEMENTATION_VERIFICATION.md`가 발견: **ChainBench 구현체가 이 저장소에 0건이고 `plugin/.mcp.json`에 `chainbench` 서버가 등록되어 있지 않음** (`jira-gateway`, `cks` 두 개만). 따라서 evaluator의 `mcp__chainbench__*` 도구 호출은 §7.0 pre-flight를 통과할 수 없고 영구 BLOCKED. 사양 단계만 완료되었고 런타임에서는 동작 불가.

**보정 작업**: HANDOFF.md §7.1 F-1 — 둘 중 하나 선택:
- (a) `plugin/.mcp.json`에 chainbench 서버 항목 추가 (ChainBench MCP 별도 빌드 필요)
- (b) SETUP.md §5에 "사용자가 ChainBench MCP를 별도 설치하고 `.mcp.json`에 추가해야 함"을 명시 + §9.6 트러블슈팅 보강

**원래 사양 (§7.0 pre-flight)**: 도구 이름 불일치 시 BLOCKED 처리 로직은 그대로 유효 — 일단 서버가 등록된 후에 동작.

**문제**: Phase 6 설계에서 ChainBench MCP의 tool 인터페이스(chainbench_setup, chainbench_start, chainbench_status, chainbench_run_tests, chainbench_stop)를 "예상"으로 정의했다. 실제 ChainBench MCP의 tool 이름과 파라미터가 다를 수 있다.

**영향**: Phase 6 구현 시 실제 ChainBench MCP API와 불일치하면 연동 코드 재작성 필요.

**해결 방향**:
- Phase 6 시작 전에 실제 ChainBench MCP의 tool 목록 확인:
  - ChainBench MCP 서버를 실행하고 tool list 조회
  - 또는 ChainBench 프로젝트의 MCP tool 정의 코드 확인
- 설계 문서의 tool 인터페이스를 실제와 일치하도록 업데이트
- 인터페이스가 크게 다르면 P6-5의 핵심 로직 수정 필요

**해결 시점**: Phase 6 시작 전 (사전 조사)

---

## RI-21. Evaluator에 go test -race 미포함 [Phase 6]

**상태**: `RESOLVED` — `evaluator.md §4.4 -race scope` 정의: CKG의 `concurrency_impact[].risk_assessment.race_condition_risk != "none"`인 심볼의 parent package만 `race_pkgs`로 추출 후 `go test -race ${race_pkgs[@]} -count=1 -timeout=300s` 실행. `eval-race.log`의 "WARNING: DATA RACE" 매칭으로 `result.race_detected` 설정. 전체 테스트 -race 적용으로 인한 시간 폭발 회피하면서 RI-11의 정적 분석 한계 보완. 커밋 `0058b4e`.

**문제**: RI-11에서 Concurrency Analyzer의 정적 분석 한계를 보완하기 위해 `go test -race`를 권장했지만, Evaluator의 4-stage 파이프라인에 race detector가 포함되어 있지 않다.

**영향**: 동시성 관련 수정 후 race condition이 테스트에서 검출되지 않을 수 있음.

**해결 방향**:
- Stage 1(Unit Test)에 `-race` 플래그 옵션 추가:
  ```bash
  # 동시성 관련 패키지에 대해 race detector 실행
  go test -race ./consensus/... ./core/txpool/... -count=1
  ```
- 전체 테스트에 -race를 적용하면 시간이 크게 증가하므로, 동시성 관련 패키지만 대상으로 제한
- CKG의 concurrency_impact 결과에서 영향받는 패키지를 -race 대상으로 사용

**해결 시점**: Phase 6 (P6-2 구현 시)

---

## RI-22. patterns.json 공유 전략 미확정 [공통]

**상태**: `RESOLVED` — 환경변수 기반 경로 주입으로 통일. `plugin/.mcp.json`의 env: `PATTERNS_PATH=${CLAUDE_PLUGIN_ROOT}/../shared/patterns.json` (jira-gateway, Go), `CKS_PATTERNS_PATH=${CLAUDE_PLUGIN_ROOT}/../shared/patterns.json` (자체 cks-mcp, Go). 양쪽 모두 `resolvePatternsPath()` 헬퍼에서 env → project-root probe → cwd/shared 순으로 폴백. `plugin/skills/pr-sanitize/SKILL.md §3.1`도 동일 패턴(env → repo_root → plugin_root). 빌드 의존성 없음. 커밋 `6d1b700` + `292e7dc` + `459a7ad`. **R1′ Step 6 (2026-06-02, `76a285d`) 후**: 자체 cks-mcp 폐기로 `CKS_PATTERNS_PATH`는 더 이상 사용 안 함. outbound 패턴(pr-sanitize)만 `PATTERNS_PATH` 환경변수로 운영. 외부 cks는 자체 도메인 시스템(`policy/stablenet.yaml`)을 가짐.

**문제**: shared/patterns.json을 Jira Gateway MCP와 (자체 시점의) CKS MCP 양쪽 Go 서버에서 사용해야 한다. 현재 파일은 프로젝트 루트의 shared/에 있지만, 각 MCP 서버 프로젝트에서 이 파일에 접근하는 방법(symlink, 빌드 시 복사, embed)이 정의되지 않았다.

**영향**: MCP 서버 빌드/실행 시 patterns.json 경로 불일치 가능.

**해결 방향**:
- **Jira Gateway MCP (Go)**: 런타임 환경변수 `PATTERNS_PATH`로 절대 경로 주입. 부재 시 project-root → cwd/shared 폴백
- **자체 시점의 CKS MCP (Go, R1′ 후 폐기)**: 동일 패턴, 환경변수 `CKS_PATTERNS_PATH`가 `PATTERNS_PATH`보다 우선
- **권장**: 환경변수 기반 경로 주입 (`.mcp.json`의 env에서 설정). 빌드 의존성 없음.

**해결 시점**: Phase 2 (P2-1) + Phase 3 (P3-1) 각각 구현 시

---

## RI-23. 임베딩 캐시 전략 부재 [Phase 3]

**상태**: `RESOLVED` — `tools/cks-mcp/internal/ckv/store.go`의 chunks 테이블에 `code_hash TEXT NOT NULL` 컬럼 + `idx_chunks_hash` 인덱스 추가. `Store.GetCodeHash(chunkID)` API + `indexer.go:149` incremental 루프가 `oldHash == chunk.CodeHash && oldHash != ""`일 때 임베딩 호출 스킵. 변경된 청크만 re-embed → RI-09 시간 추정 완화. 커밋 `292e7dc`.

**문제**: P3-7(Indexing Pipeline)에서 incremental index는 변경 파일만 재처리한다고 정의했지만, 임베딩 결과의 캐싱 메커니즘이 없다. 동일 청크를 다시 임베딩하는 불필요한 재계산이 발생할 수 있다.

**영향**: incremental index에서도 불필요한 임베딩 호출 → 시간 낭비 (RI-09 악화).

**해결 방향**:
- 청크 ID(hash of file_path + symbol_name)를 키로, 임베딩 벡터를 캐시
- incremental index 시:
  1. 변경 파일의 청크 재파싱
  2. 청크 내용(code)의 hash 비교 → 변경 없으면 기존 임베딩 재사용
  3. 변경된 청크만 re-embed
- 캐시 저장: SQLite chunks 테이블의 code_hash 컬럼 + 기존 벡터 보존

**해결 시점**: Phase 3 (P3-7 구현 시)
