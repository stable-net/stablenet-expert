# Knowledge System 통합 분석 — coding-agent · cks · ckg · ckv (2026-06-17)

문서 성격: **분석/조사 결과 (status, Tier 3)**. 구현 전 근거 확보용. 4개 repo 교차 조사.
조사 범위: 사용자 12개 지시 항목 (analyzer 추가, doctor, cks 선택, parity, 데이터 생성, 확장성 등).
구현은 본 문서 합의 후 별도 진행.

> **요약:** 시스템은 4개 컴포넌트로 구성된다 — `coding-agent`(플러그인/오케스트레이션),
> `cks`(MCP 오케스트레이터), `ckv`(벡터 검색), `ckg`(코드 그래프). 조사 결과 **사용자
> 지시 일부의 전제가 수정**된다: (1) analyzer는 `/coding-agent:diagnose`로 이미 부분 존재,
> (2) **CKV 15개 MCP 도구 중 CKS 경유로 닿는 건 1개뿐**(parity 갭), (3) cks 인스턴스
> 런타임 선택 불가, (4) doctor(실제 MCP 연결성 검사) 부재. 데이터 생성 파이프라인은
> 건전하며, 정책/도메인은 config-driven이나 언어 추가는 하드코딩이다.

---

## 0. 시스템 구성 (확인된 사실)

| 컴포넌트 | 경로 | 역할 |
|----------|------|------|
| **coding-agent** | `Work/github/coding-agent` | Claude Code 플러그인. 명령·agent·hook으로 작업 오케스트레이션. cks/jira/chainbench MCP 사용 |
| **cks** | `Work/github/code-knowledge-system` | MCP 서버. ckv+ckg를 **in-process import**해 조합 |
| **ckv** | `Work/github/code-knowledge-vector` | 벡터/시맨틱 검색. vector.db 생성 |
| **ckg** | `Work/github/code-knowledge-graph` | 코드 그래프(노드/엣지). graph.db 생성 |

데이터 흐름: `ckv build`/`ckg build` → vector.db / graph.db → `cks-mcp`가 두 DB를
in-process로 열어 조합 → coding-agent의 agent들이 cks MCP 도구 호출.

---

## 1. coding-agent 인벤토리 (항목 6)

### 1.1 명령 9개 (`plugin/commands/`)

| 명령 | 용도 | 입력 | 결과 |
|------|------|------|------|
| `work` | Jira 티켓 기반 작업 시작 | JIRA-ID | workspace 생성, Orchestrator 디스패치 |
| `analyze` | 자유텍스트 요구 작업 시작 | 따옴표 텍스트 + `--type`/`--auto-merge` | `LOCAL-{ts}` workspace, Jira 불필요 |
| `review` | PR 리뷰 피드백 반영 | `#PR` 또는 URL | 코멘트 분류 → review-feedback.md → 수정 사이클 |
| `merge` | 승인된 PR squash 머지 | JIRA-ID | 엄격 사전조건(APPROVED+CI+mergeable) 후 머지 |
| `status` | 작업 상태 조회 | JIRA-ID 또는 없음 | 상태머신 스냅샷 / 활성작업 표 |
| `bench` | 3-way(A=cks/B=code/C=code+skills) 벤치 | manifest 또는 `--continue` | 토큰·비용·정확성 비교표 |
| `setup` | MCP 환경 셋업/검증 | `--check`/`--fix` | env var 상태표 + settings.json 기록 |
| `diagnose` | **root-cause 분석 (코드 변경 없음)** | 증상 텍스트 + `--path` | `diagnosis.md` (원인+증거+신뢰도) |
| `doc-organize` | docs 3-tier 정리 | scope | keep/merge/archive 계획 + 적용 |

### 1.2 agent 6개 (`plugin/agents/`)

| agent | 모델 | 역할 | MCP/도구 |
|-------|------|------|----------|
| Orchestrator | opus-4-7 | 상태머신 컨트롤러, sub-agent 디스패치 | jira-gateway, state-machine |
| Planner | opus-4-7 | ANALYSIS→PLANNING→DESIGN. `mode=diagnose` 지원 | **cks 13개 도구**, stablenet-*/root-cause-lifecycle 스킬 |
| Implementer | sonnet-4-6 | plan/design 기반 구현, step별 커밋 | state-machine |
| Evaluator | sonnet-4-6 | 4단계 검증(test/lint/security/chainbench) | chainbench, stablenet-invariants |
| bench-planner-codeonly | opus-4-7 | 벤치 B모드 (cks 없이 grep/read) | Grep/Glob |
| bench-planner-skills | opus-4-7 | 벤치 C모드 (grep+스킬) | + stablenet-* 스킬 |

### 1.3 스킬 7개

state-machine / template-parse / stablenet-context / stablenet-invariants /
pr-sanitize / bench-orchestration / **root-cause-lifecycle** (값 produce→store→consume 추적).

### 1.4 hook 4개 (`plugin/hooks/hooks.json`) — 모두 non-blocking

| 이벤트 | 핸들러 | 동작 |
|--------|--------|------|
| PreToolUse Write/Edit | doc-guard.py pre | VISION.md 편집 시 소프트 확인 |
| PostToolUse Agent | on-agent-complete.sh | agent transcript JSONL 기록(토큰 회계 기반) |
| PostToolUse Bash | on-commit.sh | `git commit` 시 ticket workspace에 로그 |
| PostToolUse Write | doc-guard.py post | 신규 docs/*.md 미등록 시 리마인더 |

---

## 2. 로컬 셋업 & MCP 설정 (항목 7)

### 2.1 `/coding-agent:setup` + `scripts/setup.py`

설정 위치: `.claude/settings.json`(경로값) + `.claude/settings.local.json`(시크릿, .gitignore).
읽는 키: `CKS_MCP_BIN`, `CKS_CONFIG`, `JIRA_GATEWAY_BIN`, `JIRA_BASE_URL`,
`JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, `CHAINBENCH_DIR`.
자동탐지: 형제 repo(`code-knowledge-system/bin/cks-mcp`, `../chainbench`)에서 추론.
**세션 재시작 필요** (MCP env 재로드).

### 2.2 MCP 등록 (`plugin/.mcp.json`)

서버 3개: `jira-gateway`, `cks`(`${CKS_MCP_BIN} -config ${CKS_CONFIG}`), `chainbench`.

### 2.3 셋업 갭 (항목 7 답)

- 설정 키는 있으나 **자동 원격복구 없음** (chainbench-mcp PATH 미발견 시 수동 안내만).
- **민감정보 패턴 오버라이드 설정 경로 없음** (patterns.json 하드코딩, 조직별 패턴 추가 불가).
- **Jira custom 필드 매핑 설정 없음** (template-parse가 섹션 헤더 하드코딩).
- **멀티 repo 일괄 init 없음** (repo마다 setup 개별 실행).

---

## 3. cks ↔ ckv/ckg 연동 (항목 3·8)

### 3.1 in-process import (항목 8)

cks는 ckv/ckg를 **서브프로세스가 아니라 Go 패키지로 import**한다:
- ckv: `pkg/ckv` import (`cmd/cks-mcp/main.go:42`, `internal/ckvclient/real.go`). `ckv.Open()`으로 vector.db open.
- ckg: `code-knowledge-graph/pkg/store` import (`internal/ckgclient/real.go:14`). `store.OpenReadOnly()`로 graph.db open.

DB 경로: config YAML(`config.Backends.CKV.Path`, `config.Backends.CKG.Path`).
기동 흐름: `cks-mcp main → loadConfig → buildBackends → buildCKGClient/buildCKVClient`.

**누락 처리 (중요):**
- **CKG 누락/stale → fatal** (기동 실패, `main.go:237-239`).
- **CKV 누락/임베더 불통 → degraded** (`NewDegradedDummy`, health=degraded, CKG만으로 응답 지속).
→ 즉 CKV가 조용히 빠져도 서버는 뜬다 → **doctor(항목 4)가 이걸 드러내야 함.**

### 3.2 응답 규격 (항목 3 답)

- **통일된 response envelope 없음.** `internal/envelope/`는 요청 컨텍스트(trace_id/run_id)만 관리, 응답 envelope 아님. tool마다 다른 구조체(`searchResponse`, `findSymbolResponse`...).
- ckv/ckg **분리 반환**: `semantic_search`(ckv only, `HitSourceCKV`), `search_text`(ckg only, `HitSourceCKG`).
- ckv/ckg **통합 반환**: `get_for_task`가 EvidencePack에 둘을 source 표시해 함께 반환.
→ 사용자 요구 "규격화된 일관 포맷"은 **현재 미충족**. **정규화 envelope 신설이 작업 항목.**

---

## 4. parity 갭 — 핵심 발견 (항목 9)

ckv/ckg는 각자 자체 MCP 서버를 띄울 수 있고, 그때만 노출되는 도구가 있다. cks 경유로
닿는지 비교한 결과:

### 4.1 CKV: 15개 중 CKS 경유 가능 = 1개

cks의 `ckvclient.Client` 인터페이스는 **4개 메서드(SemanticSearch/Health/Freshness/Close)**만
가지며, cks MCP가 노출하는 ckv 기능은 사실상 `semantic_search` 하나다.

**CKS 경유 불가 (CKV 자체 MCP 서버에서만):**
`get_freshness`(tool로 미노출), `warmup`, `related_changes`, `embed`, `vector_search`,
`rerank`, `index`, `keyword_search`, `narrow_candidates`, `explain_match`,
**`find_invariants`**, **`get_conventions`**, `expand_in_file`, alias/vocab 확장.

### 4.2 CKG: 10개 중 9개 도달

`find_symbol`/`find_callers`/`find_callees`/`get_subgraph`/`search_text`/`impact_of_change`/
`concurrency_impact`/`change_history`/`evidence_for_intent` → 모두 도달.
**미도달**: CKG 자체 `get_context_for_task` (단 cks가 자체 `get_for_task`로 대체).

### 4.3 함의 (지난 턴 flow-corpus 계획 수정)

- analyzer가 풍부한 CKV 도구(invariants/conventions/explain)를 **CKS 통해 못 씀** → `get_for_task` 하나에 의존.
- **지난 턴 계획한 flow 도구 4종(`get_flow`/`expand_flow`/`find_branches`/`get_invariant_enforcement`)을 CKV에만 만들면 analyzer가 호출 불가.** flow-corpus 계획에 **CKS-side(ckvclient 인터페이스 확장 + cks MCP 도구 노출) 단계 필수 추가.**
- 이 갭 해소가 항목 1·2(analyzer)·10(효율)의 선결조건.

---

## 5. 오케스트레이션 효율 (항목 10)

Planner의 cks 호출 순서 (fresh):
1. `cks_ops_health()` — serviceable 게이트 (아니면 BLOCKED, degraded로 진행 금지)
2. `cks_context_get_for_task()` — 1차 검색 (토큰 예산, <1.5k 목표). 반환 코드 직접 인용(재Read 금지)
3. `impact_analysis()` / `concurrency_impact()` — 공유/파생 상태·동시성 모듈 보강
4. 필요 시 `semantic_search`/`find_callers`/`get_subgraph`/`change_history` 보강

**비효율 후보:**
- parity 갭(§4) 때문에 invariants/conventions/flow 같은 **고신호 도구를 못 써서** 일반 검색에 의존.
- 토큰 효율 원칙은 명문화돼 있음("이번 턴 토큰 아끼려다 rework 10k 쓰지 말 것").
→ **항목 9 해결이 곧 항목 10 개선.** flow 도구가 닿으면 "현상→불변식→강제지점" 한 번에 회수 가능.

---

## 6. 데이터 생성 검증 (항목 11)

### 6.1 CKV 파이프라인 (`internal/build/builder.go`)
projectcfg(ckv.yaml) 로드 → discover(ignore/files-from/build_roots) → parse → chunk →
(invariant 추출, Go) → policy 분류 → (ckg 정렬) → (PR/docs corpus) → embed → store + manifest.
저장: 9 chunk kind + 메타(Category/Guidance/CKGNodeID/Invariants/ConventionStats).

### 6.2 CKG 파이프라인 (`internal/buildpipe/pipeline.go`)
detect → Pass1 parse(노드+pending refs) → Pass2 resolve(cross-file 엣지) →
Pass3 graph build(+xlang link, temporal/git, lock 전파) → Pass4 cluster+PageRank → persist.
저장: 33+ 노드 종류 + ~25 엣지 종류 + FTS + pkg_tree/topic_tree/node_prs.

### 6.3 검증 결론
파이프라인 **건전**. 단 §7 언어 불균등 주의.

---

## 7. 확장성 — 언어/도메인/정책 (항목 12)

### 7.1 언어 지원 품질 (불균등)

| 언어 | CKV | CKG | 비고 |
|------|-----|-----|------|
| Go | ⭐⭐⭐ | ⭐⭐⭐ | types-aware, 동시성/RPC/lock, 필드정밀 |
| Solidity | ⭐⭐⭐ | ⭐⭐⭐ | EVM slot, assembly, ABI 링크 |
| TypeScript/JS | ⭐⭐ | ⭐⭐ | 타입해석 없음, call edge 휴리스틱 |
| Markdown | ⭐⭐ | N/A | heading section |

→ "동일 언어 동일 품질" 요구는 **현재 Go≈Sol ≫ TS** 로 미충족. TS 품질 보강이 별도 과제.

### 7.2 정책/도메인 = config-driven (✅)
- CKV: `ckv.yaml`(파싱 설정) + `--policy stablenet.yaml`(Category/Guidance, 경로 glob).
- CKG: `--policy-file policy.yaml`(governed_by 엣지) + `--security-pattern-file`(security 패턴).
- **스키마는 범용, 내용만 도메인 특화.** 다른 프로젝트는 자기 정책 YAML만 쓰면 됨. 하드코딩된 go-stablenet 경로 가정은 **코드에 없음**(정책 파일에만).

### 7.3 언어 추가 = 하드코딩 (❌)
- 파서 인터페이스는 있음(CKV 단일패스 ~200LOC, CKG 2패스 ~2-5kLOC).
- 그러나 **컴파일타임 등록** (`newParsers()`/language_runners 수정 + 재빌드). **런타임 플러그인 없음.**
- xlang 링크(Sol→TS)는 하드코딩 페어.

### 7.4 항목 12 답
"다른 프로젝트를 knowledge data로": **Go/TS/Sol 조합은 정책 YAML만 쓰면 즉시 가능.**
새 **언어** 추가는 코드+재빌드. 도메인/정책 확장은 쉬움, 언어 확장은 어려움.

---

## 8. analyzer 현황 (항목 1·2)

**이미 부분 존재:**
- `/coding-agent:diagnose` (코드 변경 없는 root-cause 출력) + Planner `mode=diagnose` + `root-cause-lifecycle` 스킬.

**갭 (실제 작업):**
- "상황별 specific 정책" 적용 메커니즘 부재 → 정책 기반 분석 추가 필요.
- flow-corpus 인식 부재 (지난 턴 계획한 flow 도구가 아직 없고 CKS 경유도 안 됨, §4).
→ 항목 1·2 = **신규 생성이 아니라 diagnose 확장 (정책 기반 + flow 인식)**, Phase 2(parity) 의존.

---

## 9. 갭 요약 + 제안 작업 순서

### 9.1 확정된 갭

| 항목 | 갭 | 영향 |
|------|----|----|
| 4 | doctor: MCP 실제 연결성 검사 없음 (setup은 env만) | CKV degraded가 조용히 숨음 |
| 5 | cks 인스턴스 런타임 선택/전환 없음 | 세션 재시작 필요 |
| 9 | CKV 14개 도구 CKS 경유 불가 | analyzer가 고신호 도구 못 씀 |
| 3 | 통일 응답 envelope 없음 | 규격 일관성 미흡 |
| 7 | 패턴/Jira필드/멀티repo 설정 경로 없음 | 환경별 커스터마이즈 제약 |
| 12 | 언어 추가 하드코딩, TS 품질 낮음 | 언어 확장·품질 균등 제약 |

### 9.2 제안 순서 (의존성 기반)

```
Phase 1  진단 인프라 (독립, 즉시 유용)
  · 항목 4: doctor (MCP 실제 연결성 + ckv/ckg degraded 노출)
  · 항목 5: cks 인스턴스 선택/전환
Phase 2  parity 해소 (analyzer 토대)  ← 지난 턴 flow-corpus 계획과 병합
  · 항목 9: CKV 핵심 도구(flow 4종 + find_invariants 등)를 ckvclient+cks MCP로 노출
  · 항목 3: 정규화 응답 envelope
Phase 3  analyzer 강화 (Phase 2 의존)
  · 항목 1·2: diagnose를 정책 기반 + flow 인식으로 확장
Phase 4  확장성·품질 (병행 가능)
  · 항목 7: 설정 경로 보완
  · 항목 12: 언어 추가 가이드 / TS 품질 보강
```

---

## 10. 핵심 파일 인덱스

**coding-agent:** `plugin/commands/*.md`, `plugin/agents/*.md`, `plugin/hooks/hooks.json`,
`plugin/.mcp.json`, `plugin/scripts/setup.py`, `plugin/skills/root-cause-lifecycle/`.
**cks:** `cmd/cks-mcp/main.go`(기동·DB open), `internal/ckvclient/interface.go`(4메서드),
`internal/ckgclient/interface.go`(10메서드), `internal/mcp/`(tool 등록), `internal/composer/`.
**ckv:** `pkg/mcp/server.go`(15 tool), `internal/build/builder.go`, `internal/parse/*`,
`internal/policy/loader.go`, `policy/stablenet.yaml`.
**ckg:** `pkg/mcphandlers/`(10 tool), `internal/buildpipe/pipeline.go`, `internal/parse/*`,
`pkg/policy/policy.go`, `policies/stablenet/policy.yaml`, `internal/persist/schema.sql`.

---

## 11. 참조

- 지난 턴 flow-corpus 계획 (ckv): `code-knowledge-vector/docs/plan-2026-06-16-flow-ingest.md`
  → **§4 parity 갭에 따라 "CKS-side 노출" 단계 추가 필요.**
- coding-agent 기존 문서: `docs/OVERVIEW.md`, `docs/SETUP.md`, `docs/followup-*.md`.
