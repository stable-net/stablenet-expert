# Phase 6: Evaluator + ChainBench — 작업 상세

> 설계 문서: [phase6-evaluator-chainbench.md](../superpowers/specs/phase6-evaluator-chainbench.md)

---

## P6-1. Evaluator Agent 구현 [ADAPT] `L`

**상태**: ✅ 완료. `plugin/agents/evaluator.md` — bootstrap(state + go build) → 4-stage 순차 실행 → 통합 리포트 + failure_log → 상태 전이. 모든 stage 결과 한 번에 보고.

**파일**: `plugin/agents/evaluator.md` 완성

**입력**: workspace_dir (구현 완료된 브랜치)

**출력**: test-report.md + state.json 업데이트 (PASS/FAIL)

**핵심 로직**:
```
evaluator(workspace_dir):
  verify: branch = feature/{TICKET-ID}, all steps completed
  
  results = {}
  for stage in [unit_test, lint, security, chainbench]:
    results[stage] = run_stage(stage)
    // 중간에 중단하지 않음 — 모든 stage 실행
  
  write test-report.md (all results)
  
  if all PASS:
    state → EVALUATION_PASS
  else:
    state → EVALUATION_FAIL
    log_failure(combined failure entry)
```

**buddy 참고**:
- `plugin/skills/verify-quality/PROCEDURE.md` — QA 오케스트레이터 패턴
- `plugin/skills/measure-code-health/PROCEDURE.md` — 복합 헬스 스코어

**완료 기준**:
- [ ] 4-stage 순차 실행, 모든 stage 결과 수집
- [ ] test-report.md 생성
- [ ] 다중 FAIL을 하나의 failure_log entry에 기록

---

## P6-2. Stage 1: Unit Test [NEW] `M`

**상태**: ✅ 완료. `evaluator.md §4` — 전체 + 변경 패키지 커버리지 + **RI-21 `-race`** (related-code.json의 concurrency_impact + consensus/txpool/miner 우선) + 결과 파싱(passed/failed/skipped + race 탐지).

**핵심 로직**:
```bash
# 전체 테스트
go test ./... -v -count=1 -timeout=600s 2>&1 | tee logs/unit-test.log

# 변경 패키지만 (빠른 피드백)
CHANGED_PKGS=$(git diff main...HEAD --name-only '*.go' | xargs -I{} dirname {} | sort -u)
go test ${CHANGED_PKGS} -v -count=1

# 커버리지
go test ${CHANGED_PKGS} -coverprofile=coverage.out -covermode=atomic
go tool cover -func=coverage.out

# RI-21: 동시성 관련 패키지에 race detector 실행
# CKG의 concurrency_impact 결과에서 영향받는 패키지를 대상으로 사용
RACE_PKGS=$(동시성 영향 패키지 목록, 예: consensus/... core/txpool/...)
go test -race ${RACE_PKGS} -count=1 -timeout=300s 2>&1 | tee logs/race-test.log
```

> ⚠️ **RI-21**: `go test -race`를 전체 패키지에 적용하면 시간이 크게 증가하므로,
> CKG concurrency_impact에서 식별된 동시성 관련 패키지만 대상으로 제한한다.
> related-code.json의 concurrency_impact 데이터를 참조하여 대상 패키지를 결정.
> -race 결과는 test-report.md의 별도 섹션으로 리포트.

**결과 파싱**:
```
go test 출력에서:
  "--- PASS:" → passed count++
  "--- FAIL:" → failed count++, 실패 상세 캡처
  "ok" / "FAIL" 라인에서 패키지별 결과
  커버리지 %를 패키지별로 추출

go test -race 출력에서:
  "WARNING: DATA RACE" → race condition 탐지
  goroutine 스택 트레이스 캡처
```

**완료 기준**:
- [ ] 전체 + 변경 패키지 테스트 실행
- [ ] passed/failed/skipped 카운트 정확
- [ ] 커버리지 % 추출 (전체 + 패키지별)
- [ ] 실패 테스트의 파일/라인/에러메시지 캡처
- [ ] 동시성 관련 패키지에 -race 실행 + 결과 파싱
- [ ] race condition 탐지 시 FAIL 판정

---

## P6-3. Stage 2: Lint & Format [NEW] `S`

**상태**: ✅ 완료. `evaluator.md §5` — golangci-lint JSON + gofmt -l + goimports -l. error → FAIL, format 위반도 FAIL (style drift 방지).

**핵심 로직**:
```bash
golangci-lint run ./... --timeout=300s 2>&1 | tee logs/lint.log
gofmt -d . 2>&1 | tee logs/fmt.log
goimports -d . 2>&1 | tee logs/imports.log
```

**판정**: error → FAIL, warning only → PASS, format diff → FAIL

**buddy 참고**: `plugin/skills/measure-code-health/PROCEDURE.md`

**완료 기준**:
- [ ] golangci-lint 결과 파싱 (linter/severity/file/line/message)
- [ ] gofmt/goimports 차이 파일 목록

---

## P6-4. Stage 3: Security Scan [NEW] `M`

**상태**: ✅ 완료. `evaluator.md §6` — go vet + gosec(optional) + diff-targeted 4가지 패턴(하드코딩 시크릿, unsafe, 에러 무시, 신규 공유필드 미보호). critical/high → FAIL.

**핵심 로직**:
```bash
go vet ./... 2>&1 | tee logs/vet.log
# gosec (설치되어 있으면)
gosec ./... 2>&1 | tee logs/gosec.log
```

**추가 패턴 검사** (변경 파일 대상):
```
1. 하드코딩 시크릿: 변수명(secret/password/key/token) + 문자열 리터럴
2. unsafe.Pointer 사용 (경고)
3. 에러 반환값 _ 무시 패턴
4. 새로 추가된 공유 변수의 mutex 보호 여부
```

**buddy 참고**:
- `plugin/skills/audit-security/PROCEDURE.md` — CSO 보안 감사
- `plugin/skills/classify-review-risks/PROCEDURE.md` — 리스크 분류

**완료 기준**:
- [ ] go vet + gosec 결과 파싱
- [ ] 4개 추가 패턴 검사 동작
- [ ] critical/high → FAIL, medium → WARN

---

## P6-5. Stage 4: ChainBench Integration Test [NEW] `XL`

**상태**: ✅ 완료. `evaluator.md §7` — **RI-20 사전 도구 검증** (예상 도구 5개와 실제 비교) → 빌드 → setup → start+stabilize → 5min monitoring → 표준 tx 테스트 → **finally cleanup 보장**. 20분 총 타임아웃.

> ⚠️ **RI-20**: 아래 tool 인터페이스(chainbench_setup, chainbench_start 등)는
> Phase 6 설계에서 **예상한** 이름이다. 실제 ChainBench MCP의 tool 이름/파라미터와
> 다를 수 있으므로, **구현 전에 반드시 ChainBench MCP의 실제 tool list를 확인**한다.
>
> 확인 방법:
> 1. ChainBench MCP 서버 실행 → MCP Inspector로 tool list 조회
> 2. 또는 ChainBench 프로젝트의 MCP tool 정의 소스 코드 확인
> 3. 인터페이스 불일치 시 이 문서의 핵심 로직을 업데이트

**핵심 로직**:
```
0. [사전] ChainBench MCP tool list 확인 (RI-20)
   실제 tool 이름과 파라미터를 확인하여 아래 호출을 맞춤

1. 바이너리 빌드
   bash: cd {go-stablenet-root} && go build -o ./build/gstable ./cmd/gstable
   timeout: 5분
   fail → FAIL (빌드 불가)

2. 네트워크 구성
   mcp:chainbench → chainbench_setup({
     binary_path: "./build/gstable",
     node_count: 4,
     consensus: "wbft"
   })

3. 시작 + 안정화
   mcp:chainbench → chainbench_start()
   polling (30초 내 첫 블록, 60초간 지속 생성 확인)
   fail → FAIL + cleanup

4. 블록 생성 모니터링 (5분)
   블록 간격, 빈 블록 비율, 노드 합의 일관성

5. 트랜잭션 테스트
   mcp:chainbench → chainbench_run_tests("standard")
   기본 전송, 컨트랙트 배포/호출, stablecoin 전송, system contract

6. 정리 (항상 실행)
   mcp:chainbench → chainbench_stop()
   프로세스 확인 + kill, 임시 데이터 삭제, 포트 해제
```

**타임아웃**: 전체 20분. 각 단계별 개별 타임아웃.

**안전장치**: try/finally 패턴으로 cleanup 보장. 이전 실행 잔여 데이터 정리 후 시작.

**완료 기준**:
- [ ] 수정된 코드로 바이너리 빌드
- [ ] 4노드 로컬 네트워크 구성 + 안정화
- [ ] 블록 생성 모니터링 + 합의 검증
- [ ] 표준 tx 테스트 실행 + 결과 수집
- [ ] cleanup 항상 실행 (성공/실패 무관)
- [ ] 타임아웃 시 강제 정리

---

## P6-6. test-report.md 생성기 [NEW] `M`

**상태**: ✅ 완료. `evaluator.md §8` — Summary 표 + 4 stage 상세 + Failure Analysis (FAIL 시) + 사이클별 보존(test-report-{N}.md).

**핵심 로직**:
```
4-stage 결과를 마크다운 리포트로 조합:

# Test Report: {TICKET-ID}
Generated: {timestamp}
Branch: feature/{TICKET-ID}
Commit: {HEAD hash}

## Summary (테이블)
## Unit Test (상세)
## Lint & Format (상세)
## Security Scan (상세)
## ChainBench (상세)
## Failure Analysis (FAIL 시)
```

**저장**: `{workspace}/test-report.md` (최신), `test-report-{cycle}.md` (사이클별 보존)

**완료 기준**:
- [ ] 4-stage 결과 종합 리포트 생성
- [ ] FAIL 시 Failure Analysis 섹션 포함
- [ ] 사이클별 리포트 보존

---

## P6-7. failure_log 자동 기록 [ADAPT] `M`

**상태**: ✅ 완료. `evaluator.md §9` — 다중 stage FAIL을 단일 consolidated entry로 병합 (전체 상황 한눈에). agent_analysis 포함, resolution.transitioned_to는 Orchestrator가 결정.

**핵심 로직**:
```
FAIL 발생 시:
  1. 모든 FAIL stage를 하나의 failure_entry에 종합
  2. state-machine.log_failure() 호출
  3. failure_summary 자동 업데이트:
     - by_state["EVALUATION"] += 1
     - by_type["{stage}_failure"] += 1
     - recurring_patterns 갱신
  4. agent_analysis 포함:
     - root_cause_hypothesis (Evaluator의 분석)
     - confidence (high/mid/low)
     - suggested_fix

다중 FAIL 시:
  FAIL 간 관계 분석 ("unit test FAIL과 chainbench FAIL이 동일 원인인가?")
```

**buddy 참고**: `plugin/skills/persist-learning-jsonl/PROCEDURE.md` — 구조화된 학습 기록

**완료 기준**:
- [ ] 다중 FAIL을 하나의 entry에 종합
- [ ] failure_summary 자동 업데이트
- [ ] recurring_patterns 갱신
- [ ] agent_analysis 포함
