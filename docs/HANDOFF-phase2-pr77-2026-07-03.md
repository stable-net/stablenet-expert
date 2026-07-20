# HANDOFF — coding-agent Phase 2 (PR-77 통합 점검) 착수 대기 — 2026-07-03

> **STATUS UPDATE (2026-07-05):** §0의 대기 2건(CKV reindex-A + CKS config swap)은 **해소됨** —
> 새 머신 `knowledge-data/pr-77`에서 수신 확인, cks-mcp HTTP 서빙 + health/freshness 단언 통과.
> **§4.2 T-2 완료, T-3 진입가능.** flow/invariant 4종 노출도 확인(T-4 enabler, D-4).
> 정본 graph.db sha 단언은 이 머신 재빌드로 무효 — **commit(`0bf2f4d1b`)+schema(1.23) 단언으로 대체**.
> 최신 상태는 `docs/WORKLIST.md` 2026-07-05 절이 SSoT.

> **성격:** Tier 3 (status/handoff, dated). **다른 머신/세션이 이 문서 하나로 재개**할 수 있도록
> 컨텍스트·경로·커밋·의존성·실행절차를 인라인한다. SSoT는 코드 + `docs/WORKLIST.md`.
> **머신-종속 경로**는 이 머신(`/Users/wm-it-25_0220/Work/github/…`) 기준 — 다른 머신은 `docs/SETUP.md`의
> 논리 레이아웃으로 치환하고, **머신-불변 식별자(커밋 sha·graph sha·버전)** 로 정합성을 확인하라.

---

## 0. 한 줄 — 지금 무엇을 기다리나

coding-agent의 **Phase 1(파이프라인 하드닝)은 완료**(v0.1.42, main). 남은 것은 **Phase 2 = PR-77 통합
점검**인데, **cks/ckv 재인덱싱 산출물 2개가 아직 안 와서 BLOCKED**다:

- ✅ **수신됨**: CKG 정본 graph.db (`0bf2f4d1b`, schema 1.23, sha `16ee6fb70b7391b1dcf792c58cbcef78b7584dd90e092fe349eeac51222c9f78`).
- ⬜ **대기**: **CKV reindex-A(bge-m3) 벡터 인덱스** + **CKS config swap**(cks가 위 그래프+새 인덱스를 서빙하도록).

→ 이 둘이 오면 coding-agent가 **cks 배선 → PR-77 통합 bench → (Phase 2 후반) flow/invariant 인터페이스
공동설계 → H 가드레일 구현**을 실행한다. **cks 작업이 거의 끝나가므로, 그 완료 통지가 재개 트리거다.**

---

## 1. 큰 그림 (5-repo + thesis)

| repo | 역할 | 이 머신 경로 |
|---|---|---|
| **coding-agent** | 플러그인 파이프라인(analyzer→planner→implementer→evaluator) — cks의 `cks_context_*` MCP로 retrieval | `~/Work/github/coding-agent` |
| **cks** (code-knowledge-system) | ckg+ckv 합성 오케스트레이터(RRF fusion + MCP 표면). 자체 LLM/DB 없음 | `~/Work/github/code-knowledge-system` |
| **ckg** (code-knowledge-graph) | 코드 그래프(심볼·호출·git·canonical_id) | `~/Work/github/code-knowledge-graph` |
| **ckv** (code-knowledge-vector) | bge-m3/Qwen3 벡터(의미 검색) | `~/Work/github/code-knowledge-vector` |
| **go-stablenet** (테스트 대상) | geth 포크(WBFT+Anzeon 동적 가스팁). PR-77 버그의 코드베이스 | `~/Work/github/test/pr-77` (부모 `0bf2f4d1b` 체크아웃) |

**thesis (증명 대상):** *"cks 검색이 grep보다 옳은 수정까지의 **총비용**(Σ토큰 × bug-cycle + 정확성)을
줄이는가?"* — Phase 2 = 이걸 PR-77에서 A/B/C로 측정. (VISION.md)

---

## 2. 완료 상태 (이번 세션까지)

**Phase 1 — 파이프라인 하드닝 (전부 머지, v0.1.37→0.1.42):**
| PR | 작업 |
|---|---|
| #37 | fix-synthesis 갭 — source-correct over downstream-compensate(planner §5.2c) + unit-oracle fidelity(evaluator §4.8 check 6) |
| #38 | RAG 효율 — implementer EvidencePack 재사용(§4.2 scoped Read) + adaptive 그래프 깊이(analyzer §3.4/§3.5) |
| #39 | simulation-harness 스킬 — L1/L2/L3 재현 레벨 라우팅 + L3→L2 down-push(충실성 불변) |
| #40 | 검색 충분성 게이트 — analyzer §6.0 (ANALYSIS→PLANNING 전 unknown 해소) |
| #41 | harness 안전 hooks — git-guard/on-stop/session-context + 결정론 테스트(overlay-gates) |
| (e2e03dc/1abd504/b5afca0) | bench가 cks를 HTTP(`CKS_MCP_URL`)로 연결 + cks-eval/cks-bench 리네임 + v0.1.42 |

**협의 라운드 — cks/ckg/ckv 정합 (#42~#46, 문서 only):** 아래 §3.

**의도적 홀드 (§5):** 검색 캐시 · lessons.md 학습루프 · H 가드레일(단 협의 D-4로 **해금**됨).

---

## 3. 협의 결과 (D-1~D-5, 5세션 수렴) + 재인덱싱 계획

전체: `docs/coordination-response-coding-agent-2026-06-29.md`(우리 회신 §3-R/§3-R2) +
CKV 문서 `code-knowledge-vector/docs/coordination-prompts-2026-06-29.md`(§1-R/§2-R/§3-R-CKV/§5/§6).

| # | 결정 (합의) |
|---|---|
| **D-1** | 재인덱싱 커밋 **`0bf2f4d1b` 통일**. CKG가 `make eval-build-dbs LANG=auto`로 canonical graph.db 빌드·sha 공표 → CKV/CKS/coding-agent가 **그걸 가리킴(독자 재빌드 금지)**. **모델축 2회**: reindex-A(bge-m3)/reindex-B(Qwen3) |
| **D-2** | 그래프 cache SchemaVersion **≥1.19**(현 **1.23**). 배선 전 manifest `schema_version` + graph.db sha 단언 |
| **D-3** | parity 분리: recall/rerank툴=cks proxy **불요** / **flow·invariant·conventions = cks 표면 노출 필요**(노출=CKS 소관, 미구현) |
| **D-4** | `get_invariant_enforcement`(코드-도출 구현 불변식·H 가드레일 enabler)의 cks 표면 노출 = **Phase 2 deliverable 확정**(defer 안 함) → **H 가드레일 해금** |
| **D-5** | ckg #40은 graph-gap P3 supersede **아님**. 우리 "~23% recall"은 fixture 아닌 `resolve.go:30-71` 코드-리딩 추정치 → **P3 ckg 이관**. CKG에 **PR #31이 cross-package random-binding+silent-drop 닫았는지 역질문**(미회신) |

**R1(차원):** 1024 고정 금지 — reindex-B에서 1024-truncate vs full-dim 정밀도 실측 후 결정(사용자 목표=정밀도).
**R2(parity):** flow/invariant cks 노출은 옵션 아니라 비전 경로 → post-Phase-2 defer 금지.

**정본 그래프 (CKG 공표, 수신됨):**
- graph.db = `/tmp/ckg-eval/stablenet-0bf2f4d1bfeb/graph.db` (⚠️ **tmp=휘발** → 영속 위치 확보 + sha로 동일성 확인)
- commit `0bf2f4d1b` · schema `1.23` · sha256 `16ee6fb70b7391b1dcf792c58cbcef78b7584dd90e092fe349eeac51222c9f78`

---

## 4. ⭐ Phase 2 — coding-agent 잔여 작업 (상세)

### 4.1 선행 의존 (다른 세션이 줘야 착수)
| 산출물 | 상태 | 주체 |
|---|---|---|
| CKG 정본 graph.db (위 sha) | ✅ 수신 | CKG |
| **CKV reindex-A(bge-m3) 벡터 인덱스** (`0bf2f4d1b` 동일 커밋, ≥1.19 그래프에 정렬) | ⬜ 대기 | CKV |
| **CKS config swap** (cks가 위 graph.db + CKV 인덱스를 HTTP로 서빙) | ⬜ 대기 | CKS |
| (Phase 2 후반) CKV flow-aware 4종 + `get_invariant_enforcement` **+ CKS 표면 노출** | ⬜ 대기 | CKV+CKS |

### 4.2 실행 순서 (의존 해소 후)

**T-1 · D-5 답 relay → CKG (지금 가능, 선행 의존 없음).**
"~23% recall"은 **fixture/툴 측정 아님** = `ckg internal/parse/golang/resolve.go:30-71` 코드-리딩 추정치.
CKG의 "resolver 레이어·#40 무관" 판정 수용. **역질문**: PR #31(`simple_name` suffix lookup)이 그
cross-package 동명함수 random 바인딩 + silent drop을 닫았나? (닫혔으면 P3 종결 / 남았으면 affected_sites
완전성 위협.) → 이미 §3-R2에 답 있음, CKG에 전달만.

**T-2 · cks 배선 (CKV reindex-A + CKS swap 도착 후).**
- cks config(`bench/manifests/stablenet-pr77.json._requires.cks_config` = 이 머신
  `~/Work/github/knowledge-data/pr-77/cks-pr77.yaml`)가 **정본 graph.db(sha 검증) + CKV reindex-A 인덱스**를
  가리키도록 CKS가 swap → cks-mcp HTTP 재시작.
- coding-agent 배선 확인: `cks_ops_health` = `serviceable:true`, `cks_ops_freshness.indexed_head` =
  `0bf2f4d1b`, manifest `schema_version` **≥1.19(1.23)** 단언. (불일치면 fail-loud로 BLOCKED — 정상.)
- coding-agent 플러그인 **재설치 + 세션 재시작**(v0.1.42 설치본 활성화; `/reload-plugins`는 MCP 프로세스
  안 죽임 → 세션 재시작 필수).

**T-3 · PR-77 통합 bench (핵심 측정).**
- 매니페스트 **`bench/manifests/stable-0005-abc.json`** (2026-07-05 정정: 종전 지목이던
  `stablenet-pr77.json`은 deprecated `bench-analyzer-*`를 참조하는 구식 A/B/C 정의 — `_superseded_by`
  표기됨, 실행 금지): task **STABLE-0005**, base_commit `0bf2f4d1b`, go_stablenet_root(체크아웃-상대 경로),
  oracle.reference_fix = `bench/fixtures/pr77/expert-fix.diff`(전문가 fix 대조 기준),
  modes A_cks/B_code_only/C_project_skills (whole-approach solver).
- 실행: `/coding-agent:bench`(bench-orchestration 스킬) — **autopilot 세션 + 사용자 승인 필요**.
  cks는 HTTP(`CKS_MCP_URL`); A_cks만 cks 필요, B/C는 grep/skills.
- **모델축 2회**: reindex-A(bge-m3)=현행-프로덕션 baseline / reindex-B(Qwen3)=A→B 임베딩 델타. 각 인덱스에
  cks 재배선 후 동일 매니페스트 재실행.
- **종료 후 오염 정리 필수**: throwaway 브랜치/커밋 제거, go-stablenet 부모 무오염 복원, 인덱스 manifest 무변동.

**T-4 · flow/invariant 인터페이스 공동설계 → H 가드레일 (Phase 2 후반, D-4).**
- CKV flow-aware 4종(`get_flow`/`expand_flow`/`find_branches`/`get_invariant_enforcement`) + **CKS 표면
  노출**이 나오면, 3자 인터페이스 확정(시그니처 출발점 = `coordination-response-coding-agent-2026-06-29.md`
  협의 2 표). 핵심 = `get_invariant_enforcement(value)` → {불변식, 유지해야 하는 site, 유지 누락 site}.
- 그 위에 **H 가드레일(코드-도출 구현 불변식)** 구현: 하드코딩 리스트 아니라 cks가 코드에서 마이닝한
  불변식을 planner §5.2b/evaluator §4.6 always-on backstop으로. (WORKLIST 스트림1 #9 / D-4.)

### 4.3 측정 지표 (thesis)
- **총비용** = Σ(analysis+impl+eval 토큰) × bug-cycle 수 + **correctness**(expert `98f05c2a0` 대비
  side-effect 적발 / false-GREEN율). **recall@k 아님.**
- A_cks vs B/C = cks 값 검증. reindex-A vs reindex-B = 임베딩 교체 회귀/이득.
- 참고 선행 결과: run-2(#32, `docs/archive/test/pr-77/pr77-gastip-pipeline-fidelity-analysis-2026-06-24.md`) —
  하드닝 후 **false-green 없이 BLOCKED**(원래 실패모드 CLOSED), 잔여 약점=fix-synthesis(→ #37로 처리).

---

## 5. 홀드 항목 + 해금 조건

| 항목 | 상태 | 해금 조건 |
|---|---|---|
| **H 가드레일**(코드-도출 구현 불변식) | 🟢 **해금(D-4)** | cks `get_invariant_enforcement` 표면 노출(Phase 2 deliverable) 도착 → T-4 |
| 검색 캐시(rag §2.1) | ⏸ 홀드 | 베이스 검증(Phase 2 PR-77) 후 — 새 메커니즘·stale 위험 |
| lessons.md 학습루프(harness #4) | ⏸ 홀드 | 베이스 검증 후 — 노이즈/성능저하 위험 |
| cross-repo perf: ckg B3/B4/B5, graph-gap P1.5/P2/P3 | 🔵 다른 세션 | P3는 D-5로 ckg 이관 |

---

## 6. 다른 머신 재개 절차

1. **repo 확보** — coding-agent/cks/ckg/ckv/go-stablenet 5개 클론(레이아웃·remote는 `docs/SETUP.md`).
   coding-agent main = **v0.1.42**(이 문서 시점 tip `b5afca0`).
2. **env** (`docs/SETUP.md` §설치): `CKS_CONFIG`(pr-77이면 `knowledge-data/pr-77/cks-pr77.yaml`),
   `CKS_MCP_URL`(bench의 cks HTTP 연결), `CHAINBENCH_DIR`, `CKS_MCP_BIN`(=`bin/cks-mcp`), Ollama(**앱 캐스크**,
   `bge-m3`; Qwen3 교체 시 해당 모델 pull).
3. **빌드** — cks/ckg/ckv `make build-bins`(CGO), go-stablenet `make gstable`. cks-mcp는 **정본 graph.db(sha
   `16ee6fb7…`) + CKV reindex-A 인덱스**를 서빙하도록 config(CKS swap 산출물).
4. **plugin 설치** — coding-agent 플러그인 설치 + **세션 재시작**(MCP 로드). `/coding-agent:doctor`로
   env·MCP·cks health 점검.
5. **정합성 단언** — `cks_ops_health.serviceable=true`, `freshness.indexed_head=0bf2f4d1b`, schema≥1.19.
6. **실행** — §4.2 T-2→T-3(→T-4). autopilot 승인 + 종료 후 정리.

> ⚠️ **정본 그래프가 `/tmp`에 있음(휘발).** 다른 머신에는 없으므로, CKG가 재빌드하거나 sha
> `16ee6fb70b7391b1dcf792c58cbcef78b7584dd90e092fe349eeac51222c9f78`로 동일성 확인 가능한 영속 사본을 받아야 한다.

---

## 7. 핵심 파일·커밋 레퍼런스 (coding-agent repo)

- **작업 SSoT**: `docs/WORKLIST.md`(Phase 1 완료·Phase 2 트리거·D-1~D-5·홀드).
- **협의**: `docs/coordination-response-coding-agent-2026-06-29.md`.
- **Phase 2 bench**: `bench/manifests/stablenet-pr77.json`(+ `stablenet-abc-phase{1,2,3}.json`, `stable-0005-abc.json`),
  `bench/fixtures/tickets/STABLE-0005.json`, `bench/fixtures/pr77/expert-fix.diff`, 스킬 `plugin/skills/bench-orchestration/`.
- **파이프라인 계약(이번 세션 변경)**: analyzer §3.4/§3.5(adaptive)·§6.0(sufficiency)·planner §5.2c(fix-pattern)·
  evaluator §4.8(unit fidelity)·`plugin/skills/simulation-harness/`·`plugin/hooks/{git-guard,on-stop,session-context}.py`.
- **재현 검증 런북**: `docs/reproduction-verification-runbook-2026-06-23.md`(ADR-0003 라이브 프로토콜).
- **선행 결과**: `docs/archive/test/pr-77/pr77-gastip-pipeline-fidelity-analysis-2026-06-24.md`(run-1/run-2),
  `docs/archive/abc-3way-gastip-eval-2026-06-23.md`(A/B/C 방법론).
- **main tip(이 문서 시점)**: `b5afca0` · **version 0.1.42**.

---

**재개 트리거 한 줄:** *CKV reindex-A(bge-m3) + CKS config swap 완료* 통지 → §4.2 T-2(cks 배선·정합성 단언)
→ T-3(PR-77 통합 bench, reindex-A/B) → (flow 도구 도착 시) T-4(H 가드레일). 그 전엔 T-1(D-5 relay)만 가능.
