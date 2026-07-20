# WORKLIST — 통합 작업 리스트 (SSoT)

> 작성: 2026-06-22. 목적: `docs/` 하위 문서에 흩어진 작업 항목을 **6개 스트림**으로 통합한 단일 기준점.
> 상세는 각 원본 문서를 링크. 진행 마커: ✅완료 / ◐부분 / 🟡진입가능·대기 / 🔴미착수 / ☐예정.
>
> 짝 문서: [`remaining-work-detail.md`](./archive/remaining-work-detail.md)(스트림1 상세) ·
> [`cks-ckg-ckv-hardening-backlog-2026-06-19.md`](./cks-ckg-ckv-hardening-backlog-2026-06-19.md)(스트림2) ·
> [`graph-reasoning-gap-and-fix-plan-2026-06-19.md`](./graph-reasoning-gap-and-fix-plan-2026-06-19.md)(스트림3) ·
> [`rag-context-efficiency-proposals-2026-06-19.md`](./rag-context-efficiency-proposals-2026-06-19.md)(스트림4) ·
> [`harness-improvement-proposals-2026-06-17.md`](./harness-improvement-proposals-2026-06-17.md)(스트림5) ·
> [`coding-agent-overlay-improvements-and-eval-2026-06-22.md`](./archive/coding-agent-overlay-improvements-and-eval-2026-06-22.md)(스트림6: 오버레이 개선·도메인팩 확장·평가전략).
>
> ⚠️ `./archive/followup-plan.md`·`./archive/followup-expected-outcomes.md`는 `followup-status-2026-06-15.md`가 정정·대체했으므로
> 아카이브 후보(중복·상충 주의).

---

## 진척 갱신 (2026-07-12) — cks/ckg/ckv 종결 후 재검토: Phase 2 라이브 언블록

코드 대조 재검토(coding-agent `eced1c0`/v0.1.53, 라이브 `cks_ops_health`, sibling repo `remaining` 문서 3종).
**07-05 절 이후 상황이 크게 바뀜** — 이 절이 최신 기준.

### 라이브 검증 (ground truth)
- **cks 서빙 정합·최신**: `cks-stablenet`(builder `0.1.0-90dc885d`) status=ok, serviceable=true,
  **`alignment.ok=true`·`source_root_ok=true`·freshness `fresh=true`**(실측).
- 서빙 데이터셋 = **신규 컷오버 `pr-77-gstable`**: ckg schema 1.23·graph_digest `6231441…`·head `0bf2f4d1b`,
  ckv **bge-m3(=reindex-A)·dim 1024**·head `0bf2f4d1b`, source_root = `go-stablenet/pr/pr-77-problem`(HEAD `0bf2f4d1b`).
- ∴ **07-05 절의 T-2(cks 배선)는 진짜 완료·라이브 검증됨**(당시 sha 다운그레이드 단언 → 지금은 digest·alignment 실측 통과).

### 외부 cks/ckg/ckv — 실질 종결
- **cks**: flow 4종 + `find_invariants`/`get_conventions` 표면 노출(#34), ckg_node_id 은퇴(#33), `pr-77-gstable` 컷오버(M6-data)·M5 배선(#38/#39).
- **ckg**: binary-reachable 스코핑(#55), `graph_digest` pin + atomic cold rebuild + canonical_id 통합(#53). 열린 항목 소수·전부 P1 이하(Korean/CJK 테스트·Stage B harness).
- **ckv**: flow 도구 4종 CKV 구현+MCP 노출(Phase D), `FindInvariants`/`GetConventions` 노출(#35), **Qwen3 차원 락 ADR-008=1024-truncate**, reindex P2~P5 CKV-side 완료. 잔여 4건 전부 대형 corpus/CKS 오케스트레이션 의존(우리 소관 아님).

### 우리쪽 완료·미기록 (0.1.46→0.1.53 — 07-05 이후, WORKLIST에 없던 done)
| 버전 | 작업 |
|---|---|
| 0.1.47/48 (#56/#57) | bench transcript hook·측정 인프라 하드닝 / shipped prompt PR-77 정답 누출 제거 |
| 0.1.49 (#58) | per-cycle 검증 가속 + cks contamination gate |
| 0.1.50 (#59) | 런타임 프로젝트 감지 + per-project tools routing |
| 0.1.51/52 | knowledge-first + hard reproduction gate / attempt ledger + knowledge loop-back |
| **0.1.53 (#60)** | analyzer에 `find_invariants`/`get_conventions` cks 도구 배선 + C1 스키마 미러(라이브 pr-77-gstable 검증) |

### 크리티컬 패스 (우리 소관 잔여 — 실행 순서)
| 순위 | 작업 | 상태 |
|---|---|---|
| **0** | **bench 매니페스트 `go_stablenet_root` 정정** → 라이브 source_root | ✅ **완료 (07-12)** — `stable-0005-abc.json`: `../go-stablenet-pr-77`(부재) → `../go-stablenet/pr/pr-77-problem`. (deprecated `stablenet-pr77.json`은 `_superseded_by`로 실행 금지, 미정정) |
| **1** | **T-3 PR-77 통합 bench** (reindex-A/bge-m3) | 🟢 **언블록**(cks 라이브) — 승인+autopilot 대기 |
| **2** | **T-4 H 가드레일** (코드-도출 불변식, planner §5.2b/evaluator §4.6 always-on) | 🟢 **enabler 전량 도착**(flow/invariant/conventions 3-repo 배선 완료) — flow 인터페이스 확정 후 착수 |
| **3** | reindex-B(Qwen3) A→B 임베딩 델타 측정 | ⬜ 대기 — CKV Qwen3 인덱스 빌드(cks M4) 선행 |

### 홀드 (유지) / 협의 회신 (이제 답 가능)
- **홀드**: 검색 캐시(rag §2.1)·lessons.md 학습루프(harness #4) = T-3 베이스 측정 후.
- **회신 가능**: flow/invariant 4종 완료출하 ✅확정(라이브 노출+0.1.53 소비 검증) / P3 종결(ckg #53 Q1·Q2·Q6) → relay·커버리지 최종확인만 잔여([`coordination-outbound-2026-07-05.md`](./coordination-outbound-2026-07-05.md)).

> **한 줄:** 외부 3-repo 종결 + cks 라이브 정합 → **남은 것은 T-3 thesis 측정**(선결=매니페스트 경로정정 ✅완료) → T-4 H 가드레일 → (Qwen3 인덱스 도착 시) reindex-B 델타. 홀드 2건은 T-3 이후.

---

## 진척 갱신 (2026-07-05) — Phase 2 선행 의존 해소 + T-2 완료

**T-2(cks 배선) 완료.** Phase 2를 막던 대기 2건이 이 머신(`~/work/github/0xmhha/auto-coding`)에서 충족 확인·배선·단언 통과:

- `knowledge-data/pr-77`에 **graph-db**(schema 1.23, src_commit `0bf2f4d1b`, 이 머신 재빌드) +
  **vector-db = CKV reindex-A**(bge-m3, dim 1024, `0bf2f4d1b`, 15,413 chunks) 실재.
- **CKS config swap 완료**: cks-mcp가 `code-knowledge-system/cks-stablenet.yaml`(HTTP)로 위 DB 서빙.
  `cks.ops.health` = ok/serviceable, source_root = go-stablenet-pr-77, `cks.ops.freshness` fresh=true **실측 단언 통과**.
- ⚠ **sha 단언 대체**: 정본 graph.db sha `16ee6fb7…`는 구 머신 빌드의 지문 — 이 머신 것은 재빌드본이라
  sha 불일치가 정상(빌드 비결정성; handoff §6이 허용한 재빌드 경로). 동일성 단언은
  **src_commit `0bf2f4d1b` + schema ≥1.19(1.23) + parse_errors 0**으로 다운그레이드.
- **사고 발견+수정**: config 생성기의 silent fallback(`GO_STABLENET_ROOT` 미지정→`../go-stablenet`)으로
  source_root가 인덱스와 다른 체크아웃을 가리켰음 → (a) `gen-cks-config.sh` 생성-전 정합성 단언(cks PR #31),
  (b) bench manifest 머신-절대경로 제거 + 체크아웃-루트-상대 해석 규칙(coding-agent PR #53),
  (c) doctor에 데이터셋 manifest↔health 교차검증 추가(PR #53).
- **★ flow/invariant 4종 노출 확인(T-4 enabler 도착, D-4)**: cks tools/list에
  `get_flow`/`expand_flow`/`find_branches`/`get_invariant_enforcement` 실재, `find_branches` 실동작
  확인(PR-77 증상→when·then·at 후보). 단 **flow corpus 커버리지 부분적**(`get_flow(SetCurrentBlock)`=no flow)
  → CKS/CKV에 완료출하·커버리지 확인 필요([`coordination-outbound-2026-07-05.md`](./coordination-outbound-2026-07-05.md)).

**Phase 2 action items 상태:** 1 D-5 relay = 문안 확정(위 outbound 문서, 세션 전달 대기) ·
2 cks 배선 = ✅ 완료 · 3 PR-77 통합 bench = 🟡 **진입가능**(reindex-A 축; autopilot 승인만 대기.
reindex-B(Qwen3)는 CKV 인덱스 대기) · T-4 H 가드레일 = enabler 도착, **T-3 측정 후 착수**(교란 원칙).

---

## 진척 갱신 (2026-06-29) — 06-22 스냅샷 이후 닫힌 것 + 신규 잔여

06-22 이후 #16~#35 머지로 여러 스트림이 닫혔다. 이 절이 최신 기준, 아래 06-22 절은 이력.

**닫힘(머지):**
- **스트림6 P1 도메인팩**(최대 작업): Phase 2a/2b/3 전부 머지(#16·#21)+경로fix(#17). 본체 완료.
- **스트림2 A1·A2**: §3.1 ckv identity(ckv #12)·§3.2 ckg silent-incompleteness(ckg #27)+cks 전파(cks #27). "조용히 틀림" 임베딩·그래프 경로 닫힘.
- **재현 하드닝**: ADR-0003 2-티어 재현 + 재현/수정타당성 분리(#18·#19·#20·#25), evaluator per-cycle unit gate D-7(#26).
- **doctor**: read-only 진단 + fix table + allowed-tools/CI(#22·#31·#33, ADR-0002/0004). setup auto repo_root+autonomous(#23·#24).
- **consequence-of-change side-findings**(#27·#28)+버전 bump(#29). cks **HTTP transport**(#34). docs **3-tier 재편**(#35).

**★ PR-77 blind 재측정 = #32 run-2 (06-25) — thesis 핵심, 완료.** 하드닝 하네스(0.1.32 symptom-bound RED+anti-pivot+idle-window, 0.1.33 focused unit)로 clean blind 재실행:
- ✅ **원래 실패모드 CLOSED** — run-1은 *틀린 수정을 false-GREEN으로 PR*까지 냈으나, run-2는 3 사이클 모두 증상 오라클에 RED → **false-green 없이 정직하게 BLOCKED**.
- ✅ **전문가 근본원인(`SetCurrentBlock` currentBlock lag)에 §5c 런타임으로 독립 수렴.**
- ❌ **남은 약한 고리 = FIX SYNTHESIS**(reproduce/diagnose/verify 아님): planner/implementer가 계속 *add-time-drop* 변형을 골랐고, unit test가 `raw==header tip` 실제 오라클 조건을 안 건드려 masking. → **신규 잔여 2건**(아래 스트림1).

### Phase 1 후속 머지 (2026-06-29) — coding-agent 파이프라인 하드닝 5건

위 run-2가 가리킨 FIX SYNTHESIS 약점부터 시작해 Phase 1 *기능·수정* 트랙을 진행(코드 동결 후 Phase 2 측정 원칙 유지):

| PR | 작업 | ver |
|---|---|---|
| #37 | **fix-synthesis 갭** — source-correct over downstream-compensate(planner §5.2c) + unit-oracle fidelity(evaluator §4.8 check 6) + implementer §4.2 | 0.1.37 |
| #38 | **RAG 효율** — implementer EvidencePack 재사용(§4.2 scoped Read) + adaptive 그래프 깊이(analyzer §3.4/§3.5 complexity 게이트) | 0.1.38 |
| #39 | **simulation-harness 스킬** — L1/L2/L3 재현 레벨 라우팅 + L3→L2 비용 down-push(충실성 불변); L2 레시피는 도메인팩 | 0.1.39 |
| #40 | **검색 충분성 게이트** — analyzer §6.0 ANALYSIS→PLANNING 전 unknown 해소(reproduce-first RED 게이트의 검색판) | 0.1.40 |
| #41 | **harness 안전 hooks** — git-guard(PreToolUse:Bash) + on-stop(Stop) + session-context(SessionStart) + 결정론 테스트(overlay-gates) | 0.1.41 |

**홀드(의도적, 베이스 검증 후):** 검색 캐시(2.1)·lessons.md 학습루프(harness #4) = 새 메커니즘·stale/노이즈 위험. **H 가드레일**(코드-도출 구현 불변식)은 협의 D-4로 **해금**(cks `get_invariant_enforcement` 표면 노출이 Phase 2 deliverable 확정 → enabler 도착 시 구현). **cross-repo(ckg·ckv)** = 협의 D-1~D-5 수렴 → Phase 2 재인덱싱(`0bf2f4d1b`·≥1.19·모델축 A/B)과 배치.

---

## 이번 세션 진척 (2026-06-22)

MCP 재연결 트랙 + analyzer 단독 검증을 완주:

1. **소스 동기화 점검** — cks/ckg/ckv/go-stablenet 4 repo 모두 origin 최신(0/0) 확인 (재동기화 불필요).
2. **바이너리 재빌드 검증** — cks-mcp/ckg/ckv 재빌드, schema 1.21·B작업(interfaceMethodSeeds)·canonical_id 임베딩 + `go mod verify` 통과.
3. **DB 검증** — 다른 세션이 생성한 `test-data/{go-stablenet,pr-77}/` 인덱스 양쪽 모두 schema 1.21, ckg↔ckv 동일커밋 쌍, health=ok.
4. **MCP 재연결** — `settings.json` CKS_CONFIG→pr-77 배선, `/mcp` 재연결, 라이브 `cks.ops.health=ok`·`freshness=fresh`(head 0bf2f4d1b).
5. **analyzer 단독 검증 (PR-77, 공정 증상-only 티켓)** — cks 검색만으로 **PRIMARY 근본원인 정확 식별**
   (`anzeon.go:54 SetCurrentBlock`) + **RED 재현 독립 확인**. oracle(`98f05c2a0`) 대조: #1 완전일치, #2(RemotesBelowTip) 부분.
   `get_for_task`+`find_callers` 결정적. 산출물 `test-data/pr-77/{oracle,analyzer-run,ticket.json}`.
6. **오염 정리 완료** — 격리 브랜치/RED 테스트 제거, baseline 무오염 복원, 인덱스 manifest 무변동(C7).

→ **스트림1 항목 11·12의 '검증 대기'가 이번 라이브로 해소**(상세는 remaining-work-detail.md 갱신분).

### 6/19 문서 재검토 결과 (priority 재조정)

`docs/` 6월 19일 클러스터(중단된 작업) 6개를 재검토. 결론:
- **6/19 문서 6개는 대부분 "분석·제안 완료 / 구현 0" 상태**이며, 그중 2개는 작업항목이 아님 —
  `query-core-agent-evaluation`(상위 Claude Code 코어 = **본 repo 범위 밖**), `agent-architecture-and-plugin-guide`(**레퍼런스**).
- **핵심 모순 판정**: 스트림4(rag-efficiency)는 "cks 검색 *품질*은 좋다"고, 스트림3(graph-gap)은 "그래프 미노출로
  진단 *구조적 불가*"라고 정반대 주장. → **6/22 analyzer 공정입력 검증으로 판정**: analyzer가 **13툴
  (get_for_task+find_callers)만으로 PRIMARY 근본원인 도달** → δ<γ를 푼 것은 **새 그래프 프리미티브 노출(P0~P5)이
  아니라 analyzer agentic routing + 시간적-추론/확증편향 보강**. ∴ **graph-gap P0 전제 부분 반증**(스트림3 표 갱신).
- **진짜 "중단된 실행"은 단 하나로 수렴**: F-core (d) full pipeline 라이브 1셀(스트림1). 나머지 6/19 항목은 모두 미착수 제안.

---

## 스트림 1 — coding-agent 파이프라인 / thesis 검증  ★핵심
원본: [`remaining-work-detail.md`](./archive/remaining-work-detail.md) 항목 1–12

| ID | 작업 | 상태 |
|---|---|---|
| MCP 재연결 (재빌드·인덱스·config) | cks/ckg/ckv 운영 반영 | ✅ **완료 (06-22)** |
| 10 analyzer 분리 + reproduce-first 4스테이지 | 구현 | ✅ 구현완료(v0.1.17) — (d) 라이브만 |
| 11 analyzer 시간적-추론 보강 | investigative-probe·확증편향 차단 | ✅ **단독 라이브 검증 통과 (06-22, 공정입력→정답 도달)** |
| 12 ckg iface/동적디스패치 호출 엣지 | find_callers 브릿지 | ✅ 재빌드·재연결 완료(06-22) / ◐ find_callers(GetAnzeonTipCap) 직접검증 잔여 |
| 1 E §4.6 게이트 직접검증 | derived-state | ✅ 완료(06-15) |
| 3 (c) eval-set 확장 | 6모듈/9티켓 | ◐ 대부분완료 (인덱스 drift 잔여) |
| 4 C chainbench 회귀환경 | 상태확인 | 🟢 (d) 비차단 확인 |
| 2 (d) **F-core full pipeline 라이브 1셀** | red→green 완주 | 🟡 **진입가능** (전제충족·analyzer검증됨·승인+autopilot 대기) |
| A/B/C 정의 재설계 (whole-approach) | B/C=coding-agent 배제 단독 solver, C=프로젝트 .claude | ✅ **완료 (06-22)** — 정의문서 + `bench-solver-{codeonly,project-skills}` + SKILL §4.4 분기 + `stable-0005-abc.json` |
| F-core 전체 A/B/C bench | thesis 종착점 | 🟡 **진입가능** (STABLE-0005 매니페스트 준비됨·승인+autopilot 대기) |
| **fix-synthesis 갭** (run-2 §F a·b) | source-correct over downstream-compensate(planner §5.2c) + unit-oracle fidelity(evaluator §4.8 check 6) | ✅ **머지 (PR #37, v0.1.37)** |
| 9 H 가드레일 일반화 | 구현 불변식 확장 → **코드-도출 방식으로 재정의**(cks 컨벤션-마이닝 의존) | ⏸ 홀드 |

## 스트림 2 — cks/ckg/ckv 하드닝
원본: [`cks-ckg-ckv-hardening-backlog-2026-06-19.md`](./cks-ckg-ckv-hardening-backlog-2026-06-19.md) · [`knowledge-system-analysis-2026-06-17.md`](./archive/knowledge-system-analysis-2026-06-17.md)

| ID | 작업 | 상태 |
|---|---|---|
| §2 세션 재시작/운영 반영 | 머지 PR 6개 반영 | ✅ **완료 (06-22, 재연결로 흡수)** |
| §3.1 ckv identity checksum | 임베딩 공간 교체 감지 | ✅ **머지 (A1, ckv #12 + cks 전파 #27)** |
| §3.2 ckg silent-incompleteness | 파싱실패 게이트 | ✅ **머지 (A2, ckg #27)** |
| §3.3 ckg 성능 6종 | N+1·LIKE·SQLite pragma | 🟠 미착수 |
| §3.4/§3.5 ckg 확장성·ckv 기타 | | 🟠 미착수 |
| ~~Item 9 "CKV 15툴 parity gap"~~ → **분리(협의 D-3)** | (a) recall/rerank류 cks 배선 = **불요**(cks가 fusion 소유, 단일 SemanticSearch만 proxy) / (b) **flow·invariant·conventions = cks 표면 노출 필요(미구현)** | (a) 닫힘 / (b) 🔴 cks Phase 2 deliverable 대기(=H 가드레일 enabler, 협의 D-4) |

## 스트림 3 — graph reasoning gap
원본: [`graph-reasoning-gap-and-fix-plan-2026-06-19.md`](./graph-reasoning-gap-and-fix-plan-2026-06-19.md)

| ID | 작업 | 상태 |
|---|---|---|
| P0 진단 intent→agentic routing | δpack→γdirect | 🟢 **사실상 흡수 — 신규구현 불필요** (06-22 공정입력 검증: analyzer가 13툴만으로 PRIMARY 도달 → "진단실패=그래프 미노출" 전제 부분 반증) |
| P1.5 ckg depth-cap 절단 경고 | metadata.warnings (additive) | 🟡 **진입가능** (저비용·재인덱싱 불필요·additive) |
| P1 ckg path/reachability 툴 MCP 노출 | CLI-only→MCP | 🔴 미착수 (중비용) |
| P2 motif 쿼리 3종 | lock 미해제 등 | 🔴 미착수 |
| P3 suffix-match resolver 수정 | ~23% recall | 🔴 미착수 (위험·격리) |
| P4/P5 pack synthesis·data-flow | | ⏸ defer (고비용) |

> **6/22 재평가**: graph-gap의 가치는 P0(진단 라우팅)이 아니라 **P1.5(저비용 가시성)·P2/P3(정확성)** 로 이동.
> P0는 analyzer가 이미 흡수했으므로 우선순위 **하향**.

## 스트림 4 — RAG 비용 효율
원본: [`rag-context-efficiency-proposals-2026-06-19.md`](./rag-context-efficiency-proposals-2026-06-19.md) — 1~6 coding-agent 단독·차단 없음

| ID | 작업 | 상태 |
|---|---|---|
| 1 implementer EvidencePack 재사용 | 중복 full-Read 제거 | ✅ **머지 (PR #38, v0.1.38)** — design 인용 범위 scoped Read |
| 2 evidence 캐시 (index-head 키) | | ⏸ **홀드** (새 메커니즘·stale 위험 — 베이스 검증 후) |
| 3 adaptive search depth 라우터 | | ✅ **머지 (PR #38)** — analyzer §3.4/§3.5 complexity tier 게이트 |
| 4 search sufficiency 게이트 | ANALYSIS→PLANNING 전 unknown 해소 | ✅ **머지 (PR #40, v0.1.40)** — analyzer §6.0 |
| 5/6 evidence digest·prompt-cache prefix | | 🔴 미착수 |

## 스트림 5 — harness 자율성/안전 (hooks)
원본: [`harness-improvement-proposals-2026-06-17.md`](./harness-improvement-proposals-2026-06-17.md) · [`query-core-agent-evaluation-2026-06-19.md`](./archive/query-core-agent-evaluation-2026-06-19.md)

| ID | 작업 | 상태 |
|---|---|---|
| 1 PreToolUse git-guard | force-push/main 차단 | ✅ **머지 (PR #41, v0.1.41)** — `hooks/git-guard.py` |
| 2 Stop/SubagentStop 훅 | state 게이트 | ✅ **머지 (PR #41)** — `hooks/on-stop.py` (Stop only; SubagentStop은 over-block 위험으로 보류) |
| 3 SessionStart 컨텍스트 주입 | | ✅ **머지 (PR #41)** — `hooks/session-context.py` |
| 4~7 lessons.md·evaluator 병렬화·schema 검증·context:fork | | 🔴 미착수 (4 lessons.md = **홀드**: 베이스 검증 후) |
| query.ts 권고 (#1 reducer·#2 budget) | | ⏸ 본 repo 범위 밖 (상위 Claude Code 코어) |

## 스트림 6 — coding-agent 오버레이 개선 / 도메인팩 확장
원본: [`coding-agent-overlay-improvements-and-eval-2026-06-22.md`](./archive/coding-agent-overlay-improvements-and-eval-2026-06-22.md)

| ID | 작업 | 평가 오라클 | 상태 |
|---|---|---|---|
| P0 계약 기계검증 | plan/design 구조화 스키마 + implementer write-site 표 대조 + evaluator §4.6 완전성 | mutant 코퍼스 누락-행 탐지율 / false-GREEN율 (expert reference_fix) | ✅ **스펙 패치 + 결정론 평가 완료 (06-22)** — planner §4.5/§5.2b·implementer §2.1/§4.2b·evaluator §4.6c. 하네스 `bench/p0-mutants/` (score.py·rules.py·mutate.py·contracts.py·render.py·tests 10/10). **측정: hard mutant 탐지 before 33%→after 100% (+66.7pp), clean 오탐 0**. 잔여: `contract_underdeclare`(planner §5.2b 작성규율, P0 범위밖·정직표기) / 에이전트-인-더-루프 충실도 레이어(render→실에이전트 디스패치) 미실행 |
| P2 cks 결함강건 | 재시도·백오프 + degraded/blocked 임계 명문화 ("조용한 best-effort" 금지) | PR-77 fault-injection (0/10/30/50%) → 조용한 오답 **0** | ✅ **스펙 패치 + 결정론 평가 완료 (06-22)** — analyzer §3.0b(retry+PRIMARY/COMPLETENESS/ENHANCEMENT tier+degraded 전파)·planner §3.0 미러·evaluator §4.0. 하네스 `bench/p2-cks-fault/` (policy·scenarios·score·tests 7/7). **측정: silent-incomplete before 6→after 0, 과잉차단 0, retry 회복 3**. 잔여: 라이브 fault-injection(flaky 프록시+PR-77 오라클) 충실도 레이어 미실행 |
| P5 정리 범위 한정 | evaluator §7.6 pkill→spawn한 PID만 | 동명 더미 프로세스 생존 이진 테스트 | ✅ **완료 (06-22)** — evaluator §7.3 pre-start PID 스냅샷 + §7.6 scoped cleanup(스냅샷 차집합 ∖ $$/$PPID, self-match 버그도 제거). 하네스 `bench/p5-cleanup-scope/` (cleanup_scoped.sh + verify.sh). **실프로세스 이진 테스트 PASS: foreign 생존·ours 종료, naive pkill는 foreign 죽임(버그 실증)** |
| P3 모델 핀 중앙화/갱신 | 6파일 산재 핀 → 단일 설정원, 4-7→4-8 | 동일 픽스처 3-way bench A/B (정확성 무회귀·비용) | ✅ **완료 (06-22)** — 4-8 갱신(`304afba`) + 중앙화: `bench/model-pins/models.json` 단일 소스(tier→id, agent→tier), capture.py가 런타임에 그걸 읽음(이중소스 제거), `check.py`가 frontmatter·capture·prices 정합성 검증(+`--apply` 1-커맨드 갱신). **발견(claude-code-guide 확인): frontmatter `model:`은 런타임 간접참조 불가, `CLAUDE_CODE_SUBAGENT_MODEL`은 tier 평탄화 → 진짜 런타임 중앙화는 불가, 툴링레벨 단일소스+드리프트 게이트가 최선.** 테스트 7/7 + bench 14/14 무회귀 |
| P1 도메인팩 계약 | `domain-pack.json`+`project_id`, `stablenet-*` 정적 호명 → 활성 팩 해석, chainbench→`mcp:` 스테이지 일반화 | ① 코어 grep-clean(도메인 용어 0) ② go-stablenet 무회귀(fcore-baseline) ③ Phase1 라이브 신뢰성 | ◐ **Phase 1 완료 (구조 이동, 06-22)** — 설계 ACCEPTED(`adr/ADR-0001-domain-pack-contract.md`). `plugin/domains/go-stablenet/{domain-pack.json,invariants.md,context.md}` 신설(콘텐츠 단일소스 이동, 불변식 11·경로맵 보존), `stablenet-*` 스킬→thin pointer, 제너릭 `domain-pack` 로더 스킬 신설(미배선). 게이트 `bench/domain-pack/check.py`(5/5)+overlay-gates 편입. **에이전트 frontmatter 무변경=동작 보존**(라이브 무회귀는 미실행). **Phase 2a 브랜치 작업 (`p1-phase2-domain-pack-wire`, 미머지)**: analyzer/planner/evaluator/bench-analyzer-skills frontmatter+본문을 `domain-pack` 로더로 배선, dead 포인터 스킬 삭제, dangling 참조(root-cause-lifecycle·domain-pack) 수정, check.py를 wiring 검증으로 갱신. frontmatter stablenet-* 의존 0·overlay-gates ALL PASS. **검증 3/4 통과**(`phase2a-verification.md`): ①콘텐츠 byte-identical ②로더 해석 결정론 ③**실제 에이전트가 로더만으로 resolve·분류·불변식 적용 PASS(§3.1 실측)**. ④풀파이프라인 무회귀: **세션이 설치 캐시(baseline)를 디스패치 → 브랜치 테스트엔 설치+재시작 필요** → **결정: main 머지 후 v0.1.22 재설치하고 테스트(머지-후-테스트), 실패 시 revert.** PR `p1-phase2-domain-pack-wire`→main, 버전 0.1.21→0.1.22 bump. runbook은 verification.md Layer 4. **④ 라이브 무회귀 실행 (06-23, clean 체크아웃 `test/dev-test/pr-77`@0bf2f4d1b + pr-77 cks)**: Phase 2a analyzer가 PR-77 오라클 **PRIMARY 근본원인(`anzeon.go:54 SetCurrentBlock`) 정확 도달** + RED 재현 + domain-pack 로더 정상 해석·분류 → **분석 무회귀 PASS**(06-22 baseline #1 일치). **단 실런이 실버그 발견**: 로더 경로 `plugin/domains/...`가 설치 플러그인에서 안 풀림(cwd=타깃repo, 캐시엔 plugin/ 접두 없음) → **fix `${CLAUDE_PLUGIN_ROOT}/domains/...`(인라인 치환), v0.1.23, PR `fix-domain-pack-plugin-root`**(머지됨, 현 main 0.1.25). **③ 치환 라이브 검증 닫힘 (06-23, 0.1.25 설치+reload)**: 에이전트 로드 시 `${CLAUDE_PLUGIN_ROOT}`→절대경로 인라인 치환 실측 확인 → 로더가 워크어라운드 없이 정확한 팩 경로 Read. ∴ **Phase 2a(배선)+경로fix 검증완료·클린.** **Phase 2b + 3 머지됨 (PR #21, v0.1.28, 06-23)**: 2b-α(evaluator repo_root+build/test 팩 `verification` 소싱)·2b-β(§3 stage-loop 데이터주도, kind 디스패치)·Phase 3(`go_stablenet_root`→`repo_root` orchestrator+analyzer 계약통일 + grep-clean 게이트 in check.py). **코어 `go_stablenet_root` 0**, overlay-gates ALL PASS. 계획·체크리스트 `docs/archive/p1-phase2b-3-plan-2026-06-23.md`. **잔여 = 라이브 무회귀(게이트)만**: 0.1.28 설치+reload 후 evaluator+chainbench로 go-stablenet 무회귀(2b-5/3-4). 정직한 한계: MCP grant frontmatter 정적·bench-orchestration manifest 키 allowlist. |
| P4 문서 드리프트 | HANDOFF-simulation-verification supersede (reproduce-first/§4.7로 충족분 반영) | doc-truth 대조표: 활성문서 ↔ 코드 모순 0건 | ✅ **완료 (06-22)** — `plugin/docs/HANDOFF-simulation-verification.md` 상단에 STATUS+doc-truth 대조표(7행) prepend, §8 NEXT supersede. 제안 (1)~(5)는 reproduce-first 트랙으로 충족 확인, **활성 잔여 1건만 분리**: 신규 `simulation-harness` 스킬(L1/L2/L3 라우팅 + L2 in-process 시뮬 + ChainBench L2 down-push) → 아래 잔여항목 추적 |

> **시퀀싱 핵심**: P0·P1·P3은 파이프라인 동작을 *바꾼다* → 스트림1 thesis bench(F-core)의 측정을
> 교란한다. **F-core 베이스라인을 먼저 캡처**한 뒤 착수하거나, 각 항목을 *자체 before/after A/B*로
> 측정해야 한다(Part C 변수격리). P2·P4·P5는 비교란이라 아무 때나 가능.
>
> **📌 베이스라인 핀 (06-22)**: git tag **`fcore-baseline` = `b33931f`** (overlay P0/P2/P4/P5 적용,
> pre-P1/P3). A/B/C 라이브 런(다른 세션)은 이 커밋에서 돌리고, P1/P3 교란 작업은 이것을 *before*로
> 비교한다. 순수 pre-overlay 기준점이 필요하면 `def2af0~1`. (캡처=참조 커밋 핀일 뿐, 벤치 *실행*은
> 별개 — 스트림1 F-core 행 참조.)

**P4 분리 잔여 (신규 추적 항목):** `simulation-harness` 스킬 — 재현 테스트의 시뮬레이션 레벨
라우팅(L1 단위 / L2 in-process 체인·합의 / L3 ChainBench) + ChainBench(L3, 20분)를 L2로 down-push.
red→green 골격은 reproduce-first로 이미 존재하므로 *레벨 카탈로그/라우팅*만 추가하면 됨. 🔴 미착수
(원 제안: `plugin/docs/HANDOFF-simulation-verification.md` §6 신규 스킬·§9 결정성 가이드).

**✅ 오버레이 회귀 게이트 통합 (06-22):** `bash bench/overlay-gates.sh` — P0/P2/P3/P5 하네스 +
bench 단위테스트 9개를 한 커맨드로 묶어 스펙 회귀를 즉시 잡는다(음성 테스트로 드리프트 주입→FAIL 확인).
pre-commit/CI 후보. P0~P5의 "진짜 개선" 보증을 영구 고정하는 capstone.

---

## 권장 다음 순서 (2026-06-29 — 2단계: 기능 구현·수정 → 성능 테스트)

> **계획 원칙(사용자 지시 2026-06-29):** **기능 구현 및 수정을 먼저** 끝내고, **성능 테스트는 그 뒤에** 한다.
> 근거는 *교란 의존성* — Phase 1의 파이프라인 동작 변경은 thesis/bench 측정을 교란한다. 따라서
> 기능·수정을 **동결**한 뒤 베이스라인을 재캡처하고 Phase 2 측정을 돌린다(이전 06-22 절의 "베이스라인 락" 원칙과 동일).

### Phase 1 — 기능 구현 및 수정 (먼저)

| 순위 | 작업 | 스트림 | 상태 |
|---|---|---|---|
| **1** | **fix-synthesis 갭 닫기** — source-correct over downstream-compensate + unit-oracle fidelity | 1 | ✅ **머지 (PR #37, v0.1.37)** |
| **2** | **RAG 효율** — implementer EvidencePack 재사용(#1) + 적응형 그래프 깊이(#3) | 4 | ✅ **머지 (PR #38, v0.1.38)** · 검색 캐시(#2)는 홀드(아래) |
| **3** | **simulation-harness 스킬**(P4 분리) — L1/L2/L3 재현 레벨 라우팅 | 6 | ✅ **머지 (PR #39, v0.1.39)** |
| **3.5** | **검색 충분성 게이트** (rag-efficiency §4.1) — ANALYSIS→PLANNING 전 unknown 해소 | 4 | ✅ **머지 (PR #40, v0.1.40)** |
| **4** | **harness hooks** git-guard·Stop·SessionStart | 5 | ✅ **머지 (PR #41, v0.1.41)** — 제안 1~3. 4~7·SubagentStop 잔여 |
| **홀드** | **검색 캐시**(2.1) / **lessons.md 학습루프**(harness #4) | 4·5 | ⏸ **홀드** — 베이스 검증(Phase 2) 후. stale·노이즈 위험(새 메커니즘) |
| **Phase 2 enabled** | **H 가드레일 일반화** (코드-도출 구현 불변식) | 1 | 🟢 **해금됨(협의 D-4)** — `get_invariant_enforcement`의 cks 표면 노출이 Phase 2 deliverable 확정 → enabler 도착 시 구현(3자 인터페이스 공동설계). 하드코딩 아닌 cks 마이닝 |
| **cross-repo** | **graph-gap P1.5 / cks B3–B5** | 2·3 | 🔵 ckg·ckv 다른 세션 정리 중 → Phase 2 직전 빌드+재인덱싱과 배치 |

### Phase 2 — 성능 테스트 / thesis 측정 (Phase 1 동결 후)

| 순위 | 작업 | 근거 |
|---|---|---|
| **1** | **F-core 전체 A/B/C 라이브 bench** | full-pipeline-thesis 종착점. Phase 1 동결 후 베이스라인 재캡처하고 측정 |
| **2** | **A/B/C neutral-oracle 판정 + 교차재현** (abc-3way §5 보류분) | run-2로 A가 신뢰가능해짐 → canonical 정답 대조 가능 |
| **3** | **도메인팩 라이브 무회귀 게이트** + (필요시) Phase 1 교란항목 자체 before/after A/B | 동작보존 최종 확인 |

#### ✅ Phase 2 착수 전 cross-session 결정 (협의 D-1~D-5) — **5세션 수렴 완료 (2026-06-29)**

CKV/CKG/CKS 협의(`coordination-response-coding-agent-2026-06-29.md` §3-R/§3-R2, CKV 문서)에서 전부 합의:

| # | 결정 | 결과 |
|---|---|---|
| **D-1** ★ | 재인덱싱 커밋 **`0bf2f4d1b` 통일** | ✅ **합의.** CKG가 `LANG=auto`로 canonical graph.db 빌드·sha 공표 → 3자가 가리킴(독자 빌드 금지). **모델축 2회**: reindex-A(bge-m3)/reindex-B(Qwen3) |
| **D-2** | SchemaVersion **≥1.19(현 1.22)** | ✅ **합의.** CKG manifest 공표 → coding-agent 배선 전 단언 |
| **D-3** | parity 분리 | ✅ **합의.** recall=불요 / flow·invariant=cks 표면 노출(CKS 소관) |
| **D-4** | `get_invariant_enforcement` 일정 | ✅ **Phase 2 deliverable 확정** → **H 가드레일 해금**(홀드→Phase 2 enabled). 조건=3자 인터페이스 공동설계 |
| **D-5** | R06가 P3 supersede? | ✅ **CKG: NO.** P3=ckg build Resolve 소관 이관. 우리 "~23%"=코드-리딩 추정치 → CKG에 PR #31 종결 역질문 |

> **재인덱싱 일괄(D-1/D-2 합의분):** CKG가 `0bf2f4d1b`·≥1.19·`LANG=auto`로 canonical graph.db 빌드·sha 공표 →
> CKV 인덱스 동일 커밋, **reindex-A(bge-m3)/reindex-B(Qwen3) 2회**. CKS는 그 그래프 config swap+재시작.
> coding-agent는 두 인덱스 각각에 cks 배선 → **PR-77 통합 bench**(A=현행 baseline, A→B 델타=임베딩 효과).

#### 📥 Phase 2 트리거 — CKG 정본 그래프 수신 (2026-06-29, [CKG → coding-agent])

CKG가 정본 그래프를 공표했다(3자 공통, **독자 재빌드 금지**). D-1/D-2 충족 확인:

| 항목 | 값 |
|---|---|
| graph.db | `/tmp/ckg-eval/stablenet-0bf2f4d1bfeb/graph.db` (⚠️ tmp = 휘발 → sha로 동일성 확인, 영속 위치 확보 필요) |
| commit | `0bf2f4d1b` (D-1 ✅) |
| schema | **1.23** (D-2 ✅ ≥1.19; 협의 시점 1.22→1.23 상향, 게이트 충족) |
| sha256 | `16ee6fb70b7391b1dcf792c58cbcef78b7584dd90e092fe349eeac51222c9f78` |

**coding-agent action items (Phase 2):**
1. ☐ **D-5 답 relay (→ CKG):** "~23% recall"은 **fixture/툴 측정 아님** — `graph-reasoning-gap` 문서가
   `ckg internal/parse/golang/resolve.go:30-71`을 **코드-리딩**해 붙인 추정치(명명 fixture 없음). 이미
   §3-R2로 답함 → CKG에 그대로 전달. **역질문**: PR #31(`simple_name` suffix lookup)이 cross-package
   random-binding+silent-drop을 닫았나? 닫혔으면 P3 종결, 남았으면 affected_sites 완전성 위협.
2. ☐ **cks 배선 (재인덱싱 그래프):** cks config가 위 graph.db(sha 검증 + manifest `schema_version`≥1.19
   단언) + **CKV reindex-A(bge-m3) 인덱스**를 가리키게 함. ⚠️ **선행 의존**: 이 ckg 그래프만으론 부족 —
   **CKV reindex-A 벡터 인덱스 + CKS config swap**이 와야 cks가 서빙. (현재 ckg 그래프만 수신.)
3. ☐ **PR-77 통합 bench:** reindex-A(bge-m3)=현행 baseline, reindex-B(Qwen3)=A→B 임베딩 델타. 두 인덱스 각각 측정.

> **재인덱싱 일괄(D-1/D-2 충족 시):** 임베딩 교체(bge-m3→Qwen3, dim 1024 유지) + B3(스키마 마이그레이션) +
> 기타 retrieval-바꾸는 변경을 **`0bf2f4d1b`·≥1.19 그래프 1회 재인덱싱**으로 묶고, 그 위에서 **PR-77 통합 bench =
> 임베딩 before/after A/B**(thesis 수치 + 회귀 동시 산출).

> **한 줄:** Phase 1 = 파이프라인을 *더 정확하게/싸게* 만드는 기능·수정(최우선=fix-synthesis 갭) →
> 동결 → Phase 2 = 그 위에서 thesis/성능을 측정(F-core A/B/C). 측정은 반드시 기능·수정 동결 이후
> **그리고 D-1~D-2(재인덱싱 커밋·스키마) 합의 이후.**
