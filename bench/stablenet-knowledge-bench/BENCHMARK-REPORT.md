# CKG Benchmark — 테스트 결과 레포트 & 비교 분석 자료

> 작업 ID: `LOCAL-20260609_003552` · 브랜치: `feature/ckg-benchmark-harness` (로컬 전용, 미푸시)
> 생성일: 2026-06-09 · 대상 HEAD(go-stablenet): `9978930ba`
> 목적: CKG(cks) 그래프가 AI 코드 이해 품질을 개선하는지 **수치로 입증**하기 위한 평가
> 파이프라인의 구축 결과 보고 + 4-way 비교 방법론 스펙 + 시스템 장/단점 분석.

---

## 0. TL;DR

- **무엇을 만들었나**: 정답을 아는 30개 go-stablenet 코드 질문을 **4가지 컨텍스트 제공
  방식**으로 AI에 제출하고 **4가지 품질 지표**를 자동 측정·비교하는 재현 가능한 평가
  하니스(`.stablenet-expert/bench/ckg-bench/`, 순수 Python 3 stdlib, 4,246 LOC).
- **테스트 결과**: 단위 테스트 84/84 PASS, 4-stage 평가(빌드·테스트·린트·보안) 전부
  PASS(보안 0건), ChainBench는 정당한 SKIP(프로덕션 Go 코드 무변경). 4개 수용 기준 전부 충족.
- **현재 한계(정직한 상태)**: 지금까지 검증은 오프라인 `replay` 드라이버로 수행 → **수치는
  전부 0(placeholder)**. 즉 "방식 4가 방식 1 대비 정보량을 줄이면서 정확도를 유지한다"는
  **실효 입증은 아직 안 됨**. 실제 수치는 라이브 실행(`--driver claude_cli` + cks-mcp)이 필요.
- **이 문서의 위치**: 이후 모든 개선의 **비교 기준점(baseline) 스펙**. 라이브 실행 결과는
  이 스펙을 그대로 채워 넣으면 된다.

---

## 1. 벤치마크 스펙 (성능 비교 기준)

### 1.1 4가지 컨텍스트 제공 방식

| ID | 방식 | AI에게 제공하는 것 | 구현 | 기존 자산 매핑 |
|----|------|---------------------|------|-----------------|
| **M1_raw** | 방식 1 (기준선) | 관련 파일 **원문 전체** (정답 파일 ∪ 동일 패키지 1개) | `methods/m1_raw_files.py` | `bench-orchestration` B_code_only 와 유사하나 파일을 미리 일괄 주입 |
| **M2_graph_full** | 방식 2 | cks **그래프 덤프** (`get_subgraph depth=2, max_total=2000`, 4개 루트 패키지) | `methods/m2_graph_full.py` | 신규 (cks에 "전체 덤프" API 없음 → 모듈 한정) |
| **M3_incremental** | 방식 3 | cks **개별 조회**를 다회 턴으로(`semantic_search`/`find_symbol`/`get_subgraph`/`find_callers`, max_turns=8) | `methods/m3_incremental.py` | `bench-orchestration` A_stablenet_knowledge_mcp 의 멀티턴 패턴을 Q&A로 적응 |
| **M4_get_for_task** | 방식 4 | cks가 **자동 선별**한 EvidencePack 1회(`get_for_task(query)`) | `methods/m4_get_for_task.py` | cks `cmd/cks-eval` + `internal/eval` 의 P/R/F1 평가와 직결 |

> 4개 방식 모두 **동일한 Driver**(AI 호출 계층)를 거치므로 입력 토큰량이 상호 비교 가능.

### 1.2 4가지 측정 항목

| 지표 | 정의 | 구현 | 오라클(정답 판정 근거) |
|------|------|------|------------------------|
| **위치 정확도** | AI가 언급한 파일·코드 위치가 정답과 일치하는 비율 (Precision/Recall/F1, overlap 매칭) | `scorers/location.py` (cks `internal/eval/metrics.go` 포팅) | 골든셋 `expected_citations` |
| **정답률** | 질문에 올바르게 답한 비율 | `scorers/correctness.py` (recall ≥ 0.5 **AND** 핵심 키워드 포함) | `expected_keywords` + recall |
| **오류 건수** | 존재하지 않는 파일·함수를 만들어낸 횟수(hallucination) | `scorers/hallucination.py` | **live cks `find_symbol`** + 디스크 `exists()`/`grep` 폴백 |
| **정보량** | AI에 입력된 코드 정보의 양(입력 토큰) | `scorers/info_volume.py` | M1/M2/M4 단일샷, M3 멀티턴 합산 |

> **핵심 novelty**: 오류 건수(hallucination) 판정에 **살아있는 cks를 오라클로** 사용한다.
> cks-eval(`expected_citations` 대조만)에도, coding-agent bench(엔드투엔드 성공 여부)에도 없던 계층.

### 1.3 골든셋 30문항 구성

| 버킷 | 수 | 출처/의도 |
|------|----|-----------|
| `seeded_cks_eval` | 10 | cks-eval `scenarios-stablenet` SN01–SN10 그대로 시드 |
| `invariants` | 11 | byzantine-fairness 불변식 RI-1..RI-11 각 1문항 (정답 = 정전 코드 경로) |
| `hotspot` | 6 | 최근 버그픽스 핫스팟 (`c37994e9b` 라운드체인지 레이스, `9978930ba` justification 위조, `3eada119e` gov_council zero-balance, `98f05c2a0` AnzeonTip refresh, txpool fee-delegation) |
| `cherry_pick_boundary` | 3 | geth 원본 vs StableNet 글루 구분 (RI-9; `handler.go` vs `handler_istanbul.go`/`tx_fee_delegation.go`) |

불변식 커버리지(실측): RI-1×3, RI-2×2, RI-3×3, RI-4×2, RI-5×2, RI-6×2, RI-7×2, RI-8×3,
RI-9×3, RI-10×2, RI-11×3 → **RI-1..RI-11 전부 ≥2회 커버**.

스키마: cks-eval v1(`file`+`start_line`+`end_line`) 상위호환 v2 — `sha_pin`, `difficulty`,
`invariant_refs`, `language`, `bucket`, `expected_keywords` 추가. 코드 드리프트 방어를 위해
**모든 실행 전에 `validate_golden.py` 가 30문항 앵커를 재해석**하고 불일치 시 즉시 abort.

---

## 2. 테스트 결과 레포트

### 2.1 4-Stage 평가 결과 (Evaluator)

| Stage | 결과 | 비고 |
|-------|------|------|
| Stage 0 — Go Build (`go build ./...`) | **PASS** | exit 0; 경고는 transitive dep(x/tools) 테스트 헬퍼뿐 |
| Stage 1 — 단위 테스트 (Python) | **PASS** | 84/84; Go `-race` 는 N/A(Go 프로덕션 무변경) |
| Stage 2 — Lint & Format | **PASS** | 30/30 `py_compile` OK; gofmt N/A |
| Stage 3 — Security Scan | **PASS** | 0 findings (shell injection·하드코딩 시크릿·path traversal 없음) |
| Stage 4 — ChainBench | **SKIP** | 합의/거버넌스/state/txpool 프로덕션 무변경 → 신호 없음 (정당) |
| **Overall** | **PASS** | 적용 가능한 모든 스테이지 통과 |

### 2.2 단위 테스트 상세 (84/84)

| 모듈 | 테스트 수 | 검증 대상 |
|------|-----------|-----------|
| `test_scorers` | 30 | location P/R/F1, correctness, hallucination(파일/심볼/라인), info_volume |
| `test_drivers` | 16 | AskResult, ClaudeCLIDriver(mock), ReplayDriver 결정성 |
| `test_runner` | 13 | 배치/resume, state CRUD |
| `test_extract` | 12 | strict/lenient/failed 추출 모드, Citation 왕복 |
| `test_report` | 10 | rollup, delta, per-question, 누락 method graceful |
| `test_e2e_replay` | 3 | 2문항×4방식 풀런, 부분 resume, report.json 구조 |

### 2.3 수용 기준 (AC) 충족

- **AC#1 (단일 명령 재현)**: `run.py --driver replay` 2회 연속 실행 → `report.json` 바이트 동일. **PASS**
- **AC#2 (4지표 표 출력)**: rollup 표에 4방식 행 × (loc_p/r/f1, correct_rate, hallucs, avg_input_tokens) 모두 존재. **PASS**
- **AC#3 (M4-vs-M1 델타)**: delta 표에 `Δ_correct_rate`, `token_reduction_%` 존재. **PASS**
- **AC#4 (변경 후 재실행)**: 매 실행 전 `validate_golden.py` 드리프트 재해석 + 재현성. **PASS**

> 전체 평가 로그: `.stablenet-expert/tickets/LOCAL-20260609_003552/logs/` · 원본 리포트: 동 디렉토리 `test-report.md`

---

## 3. 비교 분석 자료

### 3.1 현재 측정값 (replay 드라이버, **구조 검증 전용**)

| method | n | loc_f1 | correct_rate | hallucs | avg_input_tokens |
|--------|---|--------|--------------|---------|------------------|
| M1_raw | 30 | 0.0000 | 0.0000 | 0 | 100.0 |
| M2_graph_full | 30 | 0.0000 | 0.0000 | 0 | 100.0 |
| M3_incremental | 30 | 0.0000 | 0.0000 | 0 | 100.0 |
| M4_get_for_task | 30 | 0.0000 | 0.0000 | 0 | 100.0 |

> ⚠️ **이 수치는 실제 성능이 아니다.** `replay` 드라이버는 캔드(canned) placeholder 응답을
> 돌려주므로 인용·정답·정보량이 전부 0/상수다. 이 표가 증명하는 것은 **"파이프라인이
> 결정적으로 끝까지 돌고 4지표 표·델타 표를 정확히 산출한다"** 라는 **구조적 정합성**뿐이다.

### 3.2 가설 (라이브 실행이 채울 칸)

기대 효과는 다음 형태로 나타날 것으로 설계됨 (실측 아님, **가설**):

| method | loc_f1 ▲ | correct_rate ▲ | hallucs ▼ | avg_input_tokens |
|--------|----------|----------------|-----------|------------------|
| M1_raw (기준) | 낮음 | 낮음 | 높음 | **매우 높음** (파일 원문 일괄) |
| M2_graph_full | 중간 | 중간 | 중간 | 높음 |
| M3_incremental | 높음 | 높음 | 낮음 | 중간 |
| M4_get_for_task | 높음 | 높음 | **가장 낮음** | **가장 낮음** |

→ **검증 목표**: `M4 vs M1` 에서 `token_reduction_% ` 가 크게 음수(정보량 절감)이면서
`Δ_correct_rate ≥ 0`(정확도 유지/향상)이면 CKG 효과가 수치로 입증된다.

### 3.3 시스템 장/단점 (벤치마크 설계 관점)

**장점 (이 하니스가 잘 잡아내도록 설계된 것)**
- cks 자동 선별(M4)이 토큰 대비 정확도에서 우월하면 **정량적 ROI**가 드러난다.
- hallucination을 **live cks로 교차검증** → "그럴듯한 거짓 인용"을 기계적으로 적발.
- 골든셋이 **불변식 RI-1..11 + 최근 버그 핫스팟**에 정렬 → 합의 안전성에 직결된 질문 위주.
- `validate_golden.py` 드리프트 가드 → 코드 변경 시 재실행만으로 품질 저하 즉시 감지(회귀 탐지기).

**단점 / 리스크 (해석 시 유의)**
- **오라클 의존성**: hallucination 판정이 cks 정확도에 의존 → cks가 실존 심볼을 놓치면 정답
  인용이 오탐될 수 있음(완화: 디스크 `exists()`+`grep` 폴백, `cks_partial` 플래그 기록).
- **정답률의 근사성**: correctness = recall+키워드 휴리스틱 → 의미적 정답을 100% 보장하진 않음.
- **비용**: 풀런 = 30×4 = **120 LLM 호출**. 라이브는 opt-in, CI는 replay로 결정적.
- **M2 스케일**: 그래프 덤프가 커질 수 있어 `max_total=2000`/seed + 100k 토큰 상한 강제.
- **골든셋 대표성**: 30문항은 핵심 경로 위주 → 커버리지 확장이 향후 과제.

---

## 4. 라이브 실행 방법 (실제 수치 생성)

전제: ① cks-mcp 가동 + `cks.ops.health` = ok, ② Claude CLI 사용 가능, ③ go-stablenet HEAD == cks `indexed_head`.

```bash
# 1) 드리프트/헬스 확인 (자동: run.py 가 매 실행 전 validate_golden 호출)
# 2) 라이브 풀런 (배치+resume 지원, 중단 시 --continue 로 재개)
python3 .stablenet-expert/bench/ckg-bench/run.py \
  --manifest .stablenet-expert/bench/ckg-bench/manifests/default.json \
  --driver claude_cli --batch-size 8

# 결과:
#   runs/ckg-bench-default/report/report.md   ← §3.1 표가 실제 수치로 채워짐
#   runs/ckg-bench-default/report/{report.csv,report.json}
#   runs/ckg-bench-default/cells/G**__M*/result.json  (셀별 원자료)
```

> `runs/` 는 `.gitignore` 처리됨(생성물). 실측 레포트가 나오면 그 `report.md` 를 본 문서
> §3.1·§3.2 자리에 그대로 이식하면 baseline 스펙이 완성된다.

---

## 5. 산출물 위치

| 항목 | 경로 |
|------|------|
| 하니스 본체 | `.stablenet-expert/bench/ckg-bench/` (run/runner/state/report/validate_golden + drivers·methods·bench_io·scorers) |
| 골든셋 30문항 | `.stablenet-expert/bench/ckg-bench/golden-set/G01–G30.yaml` + `index.yaml` |
| 매니페스트 | `.stablenet-expert/bench/ckg-bench/manifests/default.json` |
| 테스트 | `.stablenet-expert/bench/ckg-bench/tests/` (6 모듈, 84 테스트) |
| 사용법 | `.stablenet-expert/bench/ckg-bench/README.md` |
| 파이프라인 산출물 | `.stablenet-expert/tickets/LOCAL-20260609_003552/` (analysis/plan/design/test-report) |

---

## 6. 결론 & 다음 단계

- **완료**: 4-way × 4-지표 × 30문항 평가 프레임워크가 구축·테스트·평가 검증됨. 재현 가능하고
  코드 변경 시 회귀 탐지가 가능한 baseline **스펙**이 확보됨.
- **미완(의도적)**: 실제 비교 수치 = 라이브 실행 필요(사용자 결정에 따라 본 단계 보류).
- **다음 단계 후보**:
  1. cks-mcp + Claude CLI 환경에서 §4 라이브 풀런 → §3.1/§3.2 수치 확정.
  2. 결과를 정기 회귀(코드 변경 PR마다)로 묶기.
  3. 골든셋 30→확장, 난이도/언어(ko) 밸런싱.
  4. (선택) `/coding-agent:ckg-bench` 슬래시 래퍼.
