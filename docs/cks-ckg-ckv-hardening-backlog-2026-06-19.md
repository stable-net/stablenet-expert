# cks · ckg · ckv 하드닝 백로그 (Remaining Work, 2026-06-19)

> 범위: `cks`(code-knowledge-system) · `ckg`(code-knowledge-graph) · `ckv`(code-knowledge-vector)의
> **신뢰성/정합성 하드닝** 라인 — serviceability 정책, 네트워크 transport, Ollama/모델 신뢰성,
> 그리고 4-agent 코드리뷰(2026-06-16)에서 도출한 개선 백로그.
> 짝 문서: [`knowledge-system-analysis-2026-06-17.md`](./archive/knowledge-system-analysis-2026-06-17.md)(4-repo 교차 조사),
> [`remaining-work-detail.md`](./archive/remaining-work-detail.md)(coding-agent 파이프라인/bench thesis — **다른 스코프**).
> 진행 범례: ✅완료·머지 / ⏳즉시(운영) / ☐미착수 / 🔵선택 / ⏸차단.

---

## 맥락 출처 (이 문서로 부족할 때 어디를 보나)

이 문서는 **자급자족을 목표로** 빌드/검증/컨벤션/근거를 아래 §0.5·§0.6에 담았다. 추가 맥락:

- **저장소 동반 문서(누구나)**: [`SETUP.md`](./SETUP.md)(빌드·Ollama·cks 설정·플러그인 설치), [`knowledge-system-analysis-2026-06-17.md`](./archive/knowledge-system-analysis-2026-06-17.md)(4-repo 교차 조사), [`remaining-work-detail.md`](./archive/remaining-work-detail.md)(coding-agent 파이프라인/bench — 별개 스코프).
- **머신 로컬 메모리(이 머신의 Claude 세션에서만 자동 로드 — 다른 머신/사람에겐 안 따라감)**: `~/.claude/projects/-Users-wm-it-25-0220-Work-github/memory/`의 `cks-mcp-serving-architecture.md`(serviceability 구현 상세+정책결정), `ckg-ckv-review-2026-06.md`(이 백로그의 원본 리뷰), `ollama-apple-silicon-cask.md`, `cks-composer-retrieval-fix.md`. → 이 메모리가 없는 환경에서는 **본 문서 + SETUP.md가 전부**이므로, 본 문서를 1차 권위로 본다.

---

## 0. 한눈에 (현재 상태 — 2026-06-25 갱신)

신뢰성 라인 + **정합성 🔴 2건(A1·A2) 모두 main에 머지됨.** 남은 것은 (a) 운영 반영(재시작/재설치),
(b) 코드리뷰 잔여 성능·확장성 백로그(§3.3·§3.4·§3.5, 미착수), (c) 더 큰 인접 줄기(설계 구현·검색실험·그래프 추론 갭).

**2026-06-25 진행:** A1(ckv 임베딩 정체성 강제) = ckv #12 머지, A2(ckg silent-incompleteness loud) = ckg #27 머지,
cks 전파(ckv 핀 bump) = cks #27 머지. 재검증 결과 §3.4.9(MCP envelope)·§3.5.5(coreml CLI)는 별도 작업으로 **이미 해결**됨.

---

## 0.5 전제조건 · 빌드 · 테스트 · 검증 (착수 전 필독)

전체 설치 절차는 [`SETUP.md`](./SETUP.md). 이 라인 작업에 필요한 핵심만:

**전제조건**
- **Ollama는 macOS *앱 캐스크*로 띄운다**(`open -a Ollama`) — **brew formula 버전은 embeddings에서 500을 반환**하므로 금지. 모델 `bge-m3` 필요(`ollama list`로 확인, 없으면 `ollama pull bge-m3`). 엔드포인트 `http://localhost:11434`.
- ckv/ckg는 **CGO 필요**(sqlite-vec). cks 빌드: `CGO_ENABLED=1 make build-bins` → `bin/cks-mcp`(+CLI들).
- cks config 예: `~/Work/github/code-knowledge-system/cks-stablenet.yaml` — `backends.ckg.path`(graph.db), `backends.ckg.source_root`(=go-stablenet 워킹트리, 인덱싱 커밋과 일치해야 함), `backends.ckv.path`, `embed_model: bge-m3`, `ollama_url`. 인덱싱 커밋·데이터는 `code-knowledge-system/data/ckg-stablenet`·`data/ckv-stablenet`(go-stablenet@`c051d50b` 기준 빌드본).

**빌드/테스트 (각 repo 루트)**
```
make build-bins        # ckv/ckg/cks: 바이너리 산출 (CGO_ENABLED=1)
go test ./...          # cks=23pkg, ckv=36pkg 통과 기대
go vet ./...
go test -race ./<changed-pkg>/   # 동시성 변경 시
```
- ⚠️ ckv `internal/embed/coreml`는 네이티브 `tokenizers` 라이브러리 미설치 환경에서 **테스트 링크 실패**(`ld: library 'tokenizers' not found`) — *환경 이슈, 정상*. 다른 패키지 통과면 OK.

**검증 — cks 실동작 smoke** (코드 변경이 cks 거동에 닿을 때)
- health: `bash scripts/cks-health.sh ./cks-stablenet.yaml` → `status`/`serviceable`/`backends`(provider·model·indexed_head) 출력. Ollama up이면 `serviceable:true`, 끄면 `degraded`+`serviceable:false`.
- get_for_task / fail-loud / HTTP: cks-mcp는 **stdio MCP**(또는 `transport: http`). stdio는 JSON-RPC 3줄(`initialize` → `notifications/initialized` → `tools/call`)을 바이너리에 파이프. HTTP는 `Mcp-Session-Id` 헤더 + `Accept: application/json, text/event-stream`. (4-시나리오: Ollama down→health degraded/serviceable=false, down→get_for_task isError, up→health ok, up→get_for_task 인용 pack.)

## 0.6 작업 컨벤션 (어기면 사용자 규칙 위반)

- **커밋: 영어 conventional**(`feat:`/`fix:`/`chore:`/`refactor:`/`style:`). 개발단계 용어 금지("Step 1", "WIP", "phase"). **`Co-Authored-By`/AI 트레일러 절대 금지**(하니스 기본값 override). 이유: 오픈소스라 히스토리가 공개 — 전문적·단일저자로 읽혀야 함.
- **PR 본문에도 AI 생성 표기 금지**(같은 이유).
- **default 브랜치에 직접 커밋 금지** → 항상 브랜치 분리. **push/PR/merge는 사용자가 명시 지시할 때만.**
- gh 인증 = `0xmhha`. remote: cks=`github.com/0xmhha/code-knowledge-system`, ckv=`…/code-knowledge-vector`, coding-agent=`…/coding-agent`.

---

## 1. ✅ 완료·머지 (신뢰성 라인)

| 영역 | 내용 | 머지 |
|---|---|---|
| cks Phase 1 | degraded·down = **서비스 불가**로 분류, `get_for_task` fail-loud, health에 `serviceable` + 모델/indexed_head/provider 메타데이터, index-identity와 model-liveness 분리(런타임 거짓 ok 해소) | cks `b2a337e` (#18) |
| cks Phase 4 | Streamable HTTP transport(`listen.transport: stdio\|http`) + `allow_remote` opt-in + **LAN source-IP 필터**(`allowed_cidrs`) | cks #18 |
| cks Phase 2+3 | 임베더 **provider 추상화**(`internal/embedder`, config `backends.ckv.provider`), backend `buildBackends` 부트스트랩, dummy 하드코딩 경로(타 머신) 제거→cwd 기반 | cks #18 |
| coding-agent Phase 5 | planner/orchestrator가 `serviceable=false`(degraded/down)면 best-effort 대신 **BLOCKED** | coding-agent `f636d43` (#10) |
| ckv 신뢰성 | Ollama 요청 **타임아웃**(probe bounded + 응답 길이 검증) | ckv `ac34a22` (#7) |
| ckv 신뢰성 | 모델 다운로드 **transport 타임아웃**(connect/TLS/header + 백스톱, 대용량 전송 미캡) | ckv `460a718` (#8) |
| cks↔ckv | go.mod ckv→`ac34a22`(Ollama 타임아웃 cks 반영) + main.go gofmt | cks `a8f411e` (#19) |
| **A1** ckv 정합성 🔴 | **임베딩 공간 정체성 강제** — `Identity()`를 `Embedder` 인터페이스 정식 멤버로(provider/model/dim/pooling/normalize+Checksum), registry서 파생(하드코딩 제거), `query.Open`+reindex가 checksum 불일치 시 거부(구 인덱스는 name+dim 폴백). 모델 교체 안전. | ckv #12 |
| **A2** ckg 정합성 🔴 | **불완전 빌드를 loud하게** — CLI에 parse-fail 수 노출+`--fail-on-parse-errors`, Solidity 쿼리 컴파일 self-check(go/ast 스캔, 드리프트0), `GetManifest` `rows.Err()` 검사. | ckg #27 |
| cks↔ckv | go.mod ckv→`485b644`(A1 cks 반영) | cks #27 |

핵심 효과: 멈춘 Ollama가 이제 *행(hang)* 대신 **bounded 에러**로 surface → cks가 not-serviceable로
정직 보고 → planner가 차단. **A1·A2로 "조용히 틀림"의 임베딩-공간 경로와 그래프-불완전 경로까지 닫힘.**

> **정책 근거(왜 degraded=서비스불가):** 사용자 결정(2026-06-15)으로, cks의 기존 "never a crash"
> graceful-degradation을 *override*. degraded(ckv 없이 ckg/BM25만)로는 설계-급 컨텍스트가 안 나와
> "confidently-wrong" 산출 → **ckv를 optional이 아니라 required로** 격상. health는 진단용 status
> (ok/degraded/down)는 유지하되 `serviceable`(=ok만) 게이트를 추가.

> **cks↔ckv 전파 절차(향후 ckv 수정 시 반복):** cks는 ckv를 **버전 핀**으로 의존(`go.mod`, `replace` 없음).
> 따라서 ckv 변경이 cks에 닿으려면: ① ckv main에 merge → ② cks에서 `go get github.com/0xmhha/code-knowledge-vector@main`
> + `go mod tidy` → ③ `make build-bins` 재빌드 → ④ 세션 재시작. (예: §3.1 ckv identity를 고치면 이 4단계로 cks에 반영.)

---

## 2. ⏳ 즉시 (운영 반영 — 코드 아님)

- ☐ **세션 재시작** — 새 `cks-mcp` 바이너리 로드(MCP는 기동 시 1회만 env/바이너리 로드). 바이너리는 `make build-bins`로 이미 빌드됨.
- ☐ **coding-agent 플러그인 재설치** — Phase 5 planner/orchestrator 변경을 실행 캐시(설치본)에 반영. (`/reload-plugins`는 MCP 서브프로세스를 안 죽임 → 세션 재시작 필요.)

---

## 3. ckg / ckv 리뷰 백로그 (4-agent 리뷰 2026-06-16 · 재검증 2026-06-25)

> **🔁 재검증 2026-06-25 (4-agent, ckg `e74ce15`·ckv `e5b1380`·cks `08e8dbf` 기준):** ckg canonical_id
> Phase 1–3(#24–26)·ckv #9–11 머지로 코드가 크게 이동 → 아래 file:line은 재검증 기준으로 갱신함.
> **🔴 A1(§3.1)·A2(§3.2)는 구현·머지 완료** (아래 ✅). 남은 미착수는 §3.3·§3.4·§3.5.
> **착수 전 심볼/grep으로 한 번 더 확인** 권장(코드 계속 이동 중).
> **공통 검증:** 각 수정은 (1) 해당 repo `go test ./...` + `go vet` + 동시성이면 `-race`, (2) cks 거동에
> 닿으면 §0.5 health smoke로 회귀 확인. 각 항목의 "검증:"은 그 위에 더할 항목-특화 확인.

### 3.1 ✅ ckv 인덱스 identity — **구현·머지 (ckv #12, A1)**
- **구현**: `EmbeddingIdentity{provider,model,dim,pooling,normalize}` + `Checksum()`를 `Embedder` 인터페이스 정식 멤버 `Identity()`로 승격. 전 백엔드(ollama/bgeonnx/mock/coreml/cache)가 registry서 파생(하드코딩 `"l2"` 제거). builder가 normalize·checksum 기록, `query.Open`+`reindex`가 checksum 불일치 시 `ErrIndexUnavailable`로 거부(구 인덱스=빈 checksum은 name+dim 폴백→회귀 없음). 새 모델은 registry 엔트리 하나 + 컴파일러가 `Identity()` 강제.
- (원본 문제) name+dim만 검증 → Ollama bge-m3 ↔ ONNX bge-m3 무성 교체. (해결됨)
- 테스트: `TestEmbeddingIdentityChecksum`/`TestOpenRejectsIdentityMismatch`/`TestOpenAcceptsMatchingIdentity`/`TestReindex_IdentityMismatchFails`. cks 전파(cks #27) 완료.

### 3.2 ✅ ckg silent-incompleteness — **구현·머지 (ckg #27, A2)**
- **구현**: (1) CLI 성공 라인에 parse-fail 수 노출 + `--fail-on-parse-errors` 게이트(`cmd/ckg/build.go`). (2) Solidity 쿼리 컴파일 self-check 테스트 — `go/ast`로 패키지 내 모든 쿼리(26개) 스캔·grammar 컴파일, 드리프트 0·프로덕션 코드 변경 0, guard-on-guard 포함(`queries_selfcheck_test.go`). (3) `GetManifest` `rows.Err()` 검사(`internal/persist/manifest.go`).
- (원본 문제) parse 실패 파일 조용히 드롭, Solidity 쿼리 실패 시 edge 클래스 소실, `rows.Err()` 무시. (해결됨)
- 전부 additive — 정상 빌드 노드/엣지 수 회귀 없음.

### 3.3 🟠 ckg 성능 (180K 노드 빌드) — 부분 착수 (B1·B2 PR, B3~B5 미착수)
- ✅ **B1** `loadAllNodes/Edges` **N+1 쿼리** → `AllNodes()`/`AllEdges()` 단일 스캔(언어 외 노드=proto 누락도 해소). **구현(ckg `perf/ckg-query-hotpaths`).**
- ✅ **B2** SQLite DSN `busy_timeout(5000)`+`synchronous(NORMAL)` 추가(`internal/persist/sqlite.go`). **구현(같은 PR).**
- ☐ **B3** 역의존 쿼리 **leading-wildcard LIKE**로 인덱스 무효(`internal/persist/sqlite_reader.go:739` `ReverseDepsForFiles`; `FindSymbol`:354도 동일) → `simple_name` 컬럼+equi-join. **별도 PR**(스키마 마이그레이션 + cache.go SchemaVersion bump=전체 재인덱싱 강제).
- ☐ **B4** impact 분석 **6× 재순회**(공유 visited 없음, `pkg/impact/impact.go:154`; `pkg/impact` 테스트 여전히 0) → 1회 순회 후 버킷 분할 + 테스트.
- ☐ **B5** 파이프라인/SQLite 리더 **`context.Context` 부재**(취소 불가; `Run`은 `pipeline.go:217`) → ctx 배선; `parseConcurrent` 파일당 goroutine 선생성(`language_runners.go:73-100`) → sem을 부모 루프서 acquire. (침습적, 별도 PR)

### 3.4 🟠 ckg 확장성 / API — ☐ 미착수 (재검증 2026-06-25)
- 언어 추가 시 cold(`pipeline.go:308-361`)+incremental(`incremental.go:311-345`) 분기 **다중 중복** → `LanguageRunner` 인터페이스+map. post-Resolve pass ~80% 중복도 함께.
- `types.Node`가 Solidity 불린 ~20개 단 **god-struct**(`pkg/types/node.go:46-155`) → `SolFacts` 서브구조 분리. **⚠️ canonical_id가 `CanonicalID`(node.go:15)를 또 추가해 악화.**
- ~~MCP 응답 envelope 불일치~~ → **✅ 해결(재검증): `pkg/mcphandlers/helpers.go:89` `textResult()`로 전 핸들러 단일 envelope.**
- Policy/SecurityPattern 노드 **인덱싱되나 MCP 미노출**(`pkg/types/enums.go:157-158` vs `registerall.go:24-38` 10개 도구) → 도구 추가 or 빌드작업 제거.
- `NewLLMSafeReader` 안전경계 **opt-in(미강제)**(`pkg/mcphandlers/safety.go:26`).

### 3.5 🟠 ckv 기타 — ☐ 미착수 (재검증 2026-06-25)
- ~~coreml 백엔드 반쪽 배선~~ → **✅ 해결(재검증): `cmd/ckv/embedder.go:21-44`가 mock/bgeonnx/ollama만 처리·광고, coreml 제거.** 잔존: `internal/embed/coreml` dead-package(`model convert --format coreml` 출력용).
- Ollama `MaxInputTokens` **8192 하드코딩**(registry 무시, `pkg/embed/ollama/adapter.go:104`) → 모델별 registry 조회.
- build 첫 embed 실패 시 **부분 인덱스 + stale manifest**(`internal/build/builder.go:332-342`) → retry or 실패 시 인덱스 무효화.
- `CKVVersion:"dev"` 하드코딩(`builder.go:452`; ldflags 훅 `cmd/ckv/root.go:8`는 있으나 미배선) → 배선. `~/.cache/ckv/models` 경로 3곳 중복(`model/fetch.go:78`·`registry.go:125`·`bgeonnx.go:115`).

---

## 4. 🔵 cks serviceability 잔여 (검토 결과 "불필요/저가치"로 판정)

- 🔵 **Phase 1b ckv 경량 `Ping()`** — 현재 full-embed probe가 *더 정확*(데몬+모델 임베딩 가능까지 검증), TTL로 비용 무시 → **스킵 권장**.
- 🔵 **ckg start-and-report** — 정적 misconfig는 fail-fast가 옳음 → 스킵. (서브: dummy ckg `reachable=true` 구멍은 이론적, ckg path 항상 설정됨.)
- 🔵 **Dummy 전면 제거** — ~10개 granular 도구 + analysis 의존(cross-tool 변경), 휴면 tech-debt → 별도 신중 작업으로 보류.

---

## 5. 🟣 더 큰 인접 줄기 (이 라인과 별개, 본격 미착수)

- ☐ **ai-knowledge-data 지식시스템 설계 구현** — `study/docs/research/ai-knowledge-data`의 gate rollout(D-017)
  ★greenfield: `_ssot`+컴파일러, constraint-assembler, perspective-reviewer, canonical-selector/best-of-N,
  module criticality, decision-loop 모드, evidence/재검증 캐시, retrieval-policy 엔진, normalized_query,
  invariant→test catalog, externalizer. (Gate 0/1은 이번 serviceability 작업으로 일부 실증.)
- ⏸ **corpus 검색실험** — `ai-knowledge-data/corpus/REMAINING-WORK.md`: Track A(RetrievalTrace A vs B),
  Track B(corpus→cks 적재). **ckv 한글용어 오추출 버그 수정에 종속(차단).**
- (참고) coding-agent 파이프라인/bench thesis 백로그는 [`remaining-work-detail.md`](./archive/remaining-work-detail.md) 참조.

---

## 6. 추천 실행 순서 (2026-06-25 갱신)

1. ✅ **정합성 🔴 — 완료**: §3.1 ckv identity(A1, ckv #12) · §3.2 ckg silent-incompleteness(A2, ckg #27) · cks 전파(cks #27).
2. **즉시**: §2 운영 반영(세션 재시작) — 머지된 cks-mcp 바이너리 활성화.
3. **성능**: §3.3 — ✅ B1(N+1)·B2(pragma) PR 완료 → 다음 B3(LIKE, 스키마 마이그레이션·재인덱싱) → B4(impact)·B5(context, 침습적).
4. **확장성/정리**: §3.4·§3.5 (envelope·coreml은 이미 해결, 잔여만).
5. **별개 줄기**: §5는 규모/차단 고려해 별도 계획.

---

## 부록. 저장소 · 머지 커밋 맵

| repo | 경로 | main tip(2026-06-19) | A1/A2 머지 후(2026-06-25) |
|---|---|---|---|
| cks | `~/Work/github/code-knowledge-system` | `a8f411e` | ckv 핀 `485b644` (cks #27); 활성화엔 세션 재시작 |
| ckv | `~/Work/github/code-knowledge-vector` | `460a718` | A1 머지 (ckv #12) |
| ckg | `~/Work/github/code-knowledge-graph` | (`56306ed`) | A2 머지 (ckg #27); canonical_id Phase 1–3(#24–26) |
| coding-agent | `~/Work/github/coding-agent` | (Phase 5 `f636d43` 포함) | 이 문서 갱신 |
| 설계 코퍼스 | `~/Work/github/study/docs/research/ai-knowledge-data` | (비-git 스냅샷) | — |

> 빌드/검증: ckv·ckg `go vet` clean·focus `-race` 통과; cks `make build-bins`+23pkg 그린.
> coreml만 네이티브 lib 미설치로 테스트 링크 실패(환경, 무관).
> A1·A2·cks 전파 전부 `go test ./...` green (ckv 38pkg·ckg 31pkg·cks 23pkg).
</content>
