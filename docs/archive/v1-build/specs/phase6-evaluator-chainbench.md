# Phase 6: Evaluator + ChainBench 연동

> 구현된 코드의 품질/정확성 검증 파이프라인.
> Unit test → Lint → Security → ChainBench 통합 테스트까지 순차 수행.

## 1. Evaluator Agent 설계

### 1.1 plugin/agents/evaluator.md

```markdown
---
name: evaluator
model: sonnet-4.6
description: |
  구현된 코드의 검증 파이프라인. Unit test, lint, security scan,
  ChainBench 통합 테스트를 순차 실행하고 결과 리포트를 생성한다.
tools:
  - Bash (go test, golangci-lint, go vet, go build 등)
  - Read, Write (리포트 생성)
  - mcp: chainbench (로컬 네트워크 테스트)
skills:
  - state-machine
---
```

### 1.2 검증 파이프라인

```
evaluator(workspace_dir):

  1. 사전 준비
     state.json 로드 → IMPLEMENTATION 완료 확인
     브랜치 확인: feature/{TICKET-ID}
     빌드 확인: go build ./...

  2. 검증 단계 순차 실행
     ┌────────────────────────────────────────┐
     │ Stage 1: Unit Test                     │
     │ Stage 2: Lint & Format                 │
     │ Stage 3: Security Scan                 │
     │ Stage 4: ChainBench Integration Test   │
     └────────────────────────────────────────┘

     각 stage는 이전 stage 결과와 무관하게 모두 실행
     (모든 문제를 한 번에 발견하기 위해)

  3. 결과 종합 → test-report.md 생성
  4. 판정: ALL PASS / ANY FAIL
  5. state.json 업데이트 + Orchestrator에 결과 전달
```

---

## 2. Stage 1: Unit Test

### 2.1 실행

```bash
# 전체 테스트
go test ./... -v -count=1 -timeout=600s 2>&1 | tee {workspace_dir}/logs/unit-test.log

# 변경된 패키지만 테스트 (빠른 피드백)
# 변경 파일에서 패키지 추출
CHANGED_PKGS=$(git diff main...HEAD --name-only '*.go' | xargs -I{} dirname {} | sort -u)
go test ${CHANGED_PKGS} -v -count=1
```

### 2.2 결과 파싱

```
go test 출력을 파싱하여 구조화:

{
  "stage": "unit_test",
  "status": "PASS" | "FAIL",
  "duration_ms": 12345,
  "summary": {
    "total": 150,
    "passed": 148,
    "failed": 2,
    "skipped": 0
  },
  "failures": [
    {
      "package": "consensus/wbft",
      "test": "TestFinalize_StableCoinTransfer",
      "output": "--- FAIL: TestFinalize_StableCoinTransfer (0.02s)\n    finalize_test.go:45: ...",
      "file": "consensus/wbft/finalize_test.go",
      "line": 45
    }
  ],
  "coverage": {
    "total_percent": 67.5,
    "by_package": {
      "consensus/wbft": 72.3,
      "governance": 58.1
    }
  }
}
```

### 2.3 커버리지 분석

```bash
# 변경된 패키지의 커버리지
go test ${CHANGED_PKGS} -coverprofile=coverage.out -covermode=atomic
go tool cover -func=coverage.out
```

커버리지가 기존보다 감소한 패키지 → 경고 (FAIL은 아님).

---

## 3. Stage 2: Lint & Format

### 3.1 실행

```bash
# golangci-lint (다중 linter 통합)
golangci-lint run ./... --timeout=300s 2>&1 | tee {workspace_dir}/logs/lint.log

# gofmt 차이
gofmt -d . 2>&1 | tee {workspace_dir}/logs/fmt.log

# goimports 차이 (import 정리)
goimports -d . 2>&1 | tee {workspace_dir}/logs/imports.log
```

### 3.2 결과 파싱

```
{
  "stage": "lint",
  "status": "PASS" | "FAIL",
  "issues": [
    {
      "linter": "govet",
      "severity": "error" | "warning",
      "file": "consensus/wbft/finalize.go",
      "line": 123,
      "message": "unreachable code after return",
      "rule": "unreachable"
    }
  ],
  "format_issues": {
    "gofmt": ["file1.go", "file2.go"],
    "goimports": ["file3.go"]
  }
}
```

### 3.3 판정 기준

- `error` severity → FAIL
- `warning` only → PASS (경고는 리포트에 기록)
- format 차이 존재 → FAIL (자동 수정 가능하지만, 명시적 커밋 필요)

---

## 4. Stage 3: Security Scan

### 4.1 실행

```bash
# go vet (정적 분석)
go vet ./... 2>&1 | tee {workspace_dir}/logs/vet.log

# gosec (보안 특화 린터, 설치되어 있는 경우)
gosec ./... 2>&1 | tee {workspace_dir}/logs/gosec.log

# 변경된 파일만 대상으로 패턴 스캔
git diff main...HEAD -- '*.go' | grep -E "(unsafe\.|exec\.Command|sql\.Query\(|fmt\.Sprintf.*%s.*sql)" || true
```

### 4.2 추가 보안 패턴 검사

코드 레벨 민감정보/보안 패턴 (shared/patterns.json 기반이 아닌 코드 전용):

```
검사 항목:
  1. 하드코딩된 시크릿
     - 변수명이 secret/password/key/token 류 + 문자열 리터럴 대입
  
  2. Unsafe 사용
     - unsafe.Pointer 사용 (go-stablenet에서 정당한 경우도 있음 → 경고)
     - reflect 남용
  
  3. 입력 검증 부재
     - HTTP handler에서 입력 파라미터 검증 없이 사용
     - RPC 입력 직접 사용
  
  4. 에러 무시
     - err 반환값을 _ 로 무시하는 패턴
     - err != nil 체크 없이 진행
  
  5. 동시성 안전
     - 새로 추가된 공유 변수에 대한 mutex 보호 확인
     - data race 가능성 (go vet -race)
```

### 4.3 결과 구조

```
{
  "stage": "security",
  "status": "PASS" | "FAIL" | "WARN",
  "findings": [
    {
      "type": "hardcoded_secret",
      "severity": "critical",
      "file": "config/defaults.go",
      "line": 45,
      "detail": "변수 'apiKey'에 문자열 리터럴 대입 감지",
      "recommendation": "환경변수 또는 설정 파일에서 로드"
    }
  ],
  "vet_issues": [...],
  "gosec_issues": [...]
}
```

### 4.4 판정 기준

- critical severity → FAIL
- high severity → FAIL
- medium severity → WARN (리포트 기록, 통과)
- go vet 에러 → FAIL

---

## 5. Stage 4: ChainBench Integration Test

### 5.1 ChainBench MCP 인터페이스

기존 ChainBench MCP의 tool을 활용한다.

```
예상 ChainBench MCP tools:

chainbench_setup(config):
  → 로컬 네트워크 구성 (노드 수, consensus 설정)
  → 수정된 바이너리 경로 지정

chainbench_start():
  → 네트워크 시작

chainbench_status():
  → 블록 생성 상태, 노드 상태 확인

chainbench_run_tests(test_suite):
  → 트랜잭션 테스트 실행

chainbench_stop():
  → 네트워크 종료 + 리소스 정리
```

### 5.2 ChainBench 검증 흐름

```
chainbench_evaluation(workspace_dir):

  1. 바이너리 빌드
     cd {go-stablenet-root}
     go build -o ./build/gstable ./cmd/gstable
     
     빌드 실패 → FAIL (이 시점에서 이미 실패 확정)

  2. 네트워크 구성
     chainbench_setup({
       binary_path: "./build/gstable",
       node_count: 4,          // 4노드 테스트 네트워크
       consensus: "wbft",
       genesis_config: "default"  // ChainBench 기본 genesis
     })

  3. 네트워크 시작 + 안정화 대기
     chainbench_start()
     
     안정화 체크 (polling):
       - 30초 내 첫 블록 생성 확인
       - 60초간 블록이 꾸준히 생성되는지 확인
       - 모든 노드가 같은 블록 높이에 도달하는지 확인
     
     안정화 실패 → FAIL + 로그 수집

  4. 블록 생성 안정성 테스트
     5분간 블록 생성 모니터링:
       - 블록 간격이 정상 범위 내인지
       - 빈 블록 비율
       - 노드 간 합의 일관성

  5. 트랜잭션 테스트
     chainbench_run_tests("standard")
     
     표준 테스트 세트:
       - 기본 전송 트랜잭션
       - 스마트 컨트랙트 배포
       - 스마트 컨트랙트 호출
       - stablecoin 전송 (native coin)
       - system contract 호출 (GovStaking 등)
       - 대량 트랜잭션 부하 (stress test)

  6. 결과 수집
     chainbench_status() → 최종 상태
     
  7. 네트워크 정리
     chainbench_stop()
     
     반드시 정리 (테스트 성공/실패 무관):
     → 프로세스 종료
     → 임시 데이터 디렉토리 삭제
     → 포트 해제

  8. 결과 구조화
```

### 5.3 ChainBench 결과 구조

```
{
  "stage": "chainbench",
  "status": "PASS" | "FAIL",
  "duration_ms": 360000,
  
  "build": {
    "status": "PASS",
    "binary": "./build/gstable",
    "build_time_ms": 45000
  },
  
  "network": {
    "node_count": 4,
    "startup_time_ms": 15000,
    "stabilization": "PASS",
    "first_block_at_ms": 8000
  },
  
  "block_production": {
    "status": "PASS",
    "duration_seconds": 300,
    "total_blocks": 150,
    "avg_block_interval_ms": 2000,
    "max_block_interval_ms": 3500,
    "empty_block_ratio": 0.05,
    "consensus_consistency": true
  },
  
  "transactions": {
    "status": "PASS",
    "tests": [
      {
        "name": "basic_transfer",
        "status": "PASS",
        "duration_ms": 2000,
        "tx_hash": "0x..."
      },
      {
        "name": "contract_deploy",
        "status": "PASS",
        "duration_ms": 3500
      },
      {
        "name": "stablecoin_transfer",
        "status": "PASS",
        "duration_ms": 1800
      },
      {
        "name": "system_contract_call",
        "status": "FAIL",
        "duration_ms": 5000,
        "error": "execution reverted: insufficient staking amount",
        "detail": "GovStaking.stake() 호출 시 최소 스테이킹 금액 미달"
      }
    ]
  },
  
  "cleanup": {
    "status": "PASS",
    "processes_terminated": 4,
    "data_cleaned": true
  }
}
```

### 5.4 타임아웃 & 안전장치

```
타임아웃:
  - 바이너리 빌드: 5분
  - 네트워크 시작 + 안정화: 2분
  - 블록 생성 모니터링: 5분
  - 트랜잭션 테스트: 5분
  - 전체 ChainBench 단계: 20분 (총 상한)

안전장치:
  - 타임아웃 시 chainbench_stop() 강제 실행
  - 프로세스가 남아있는지 ps로 확인 후 kill
  - 포트 사용 확인 (lsof) 후 충돌 방지
  - 이전 실행의 잔여 데이터 정리 후 시작
```

---

## 6. test-report.md 생성

### 6.1 리포트 포맷

```markdown
# Test Report: {TICKET-ID}
Generated: {timestamp}
Branch: feature/{TICKET-ID}
Commit: {HEAD commit hash}

## Summary
| Stage | Status | Duration |
|-------|--------|----------|
| Unit Test | ✅ PASS | 45s |
| Lint & Format | ✅ PASS | 12s |
| Security Scan | ⚠️ WARN | 8s |
| ChainBench | ❌ FAIL | 320s |
| **Overall** | **❌ FAIL** | **385s** |

## Unit Test
- Total: 150, Passed: 150, Failed: 0
- Coverage: 67.5% (변경 패키지 평균)
- Coverage delta: +2.3% (개선)

## Lint & Format
- Issues: 0 errors, 2 warnings
- Format: all clean

## Security Scan
- Findings: 1 medium (에러 반환값 무시: core/state.go:234)
- go vet: clean

## ChainBench Integration Test
- Build: PASS (45s)
- Network startup: PASS (15s)
- Block production: PASS (150 blocks in 300s)
- Transaction tests: FAIL
  - ❌ system_contract_call: execution reverted
    Error: insufficient staking amount
    Detail: GovStaking.stake() 최소 스테이킹 금액 미달
  - ✅ basic_transfer, contract_deploy, stablecoin_transfer: PASS

## Failure Analysis
- 원인: GovStaking 컨트랙트의 최소 스테이킹 금액이 
  genesis 설정과 불일치
- 관련 코드: governance/staking.go:L89
- 권장 조치: genesis config의 minStakeAmount 확인
```

### 6.2 리포트 저장

```
{workspace_dir}/test-report.md           ← 최신 (덮어쓰기)
{workspace_dir}/test-report-{cycle}.md   ← 사이클별 보존 (재시도 시)
{workspace_dir}/logs/                    ← 각 stage의 원본 로그
```

---

## 7. failure_log 기록

### 7.1 Evaluator의 실패 기록

```
FAIL 발생 시 failure_log에 자동 기록:

failure_entry = {
  id: "fail-{auto_increment}",
  occurred_at: now(),
  state: "EVALUATION",
  agent: "evaluator",
  step: "{실패한 stage}",  // "unit_test", "lint", "security", "chainbench"
  
  attempted_action: {
    description: "{stage 설명}",
    command: "{실행한 명령}",
    related_plan_step: "{관련 plan step, 있으면}",
    modified_files: [git diff --name-only main...HEAD]
  },
  
  expected_outcome: "{stage} PASS",
  actual_outcome: {
    type: "{stage}_failure",
    summary: "{실패 요약}",
    details: "{상세 에러 메시지}",
    log_file: "logs/{stage}.log"
  },
  
  agent_analysis: {
    root_cause_hypothesis: "{Evaluator의 원인 분석}",
    confidence: "high" | "mid" | "low",
    suggested_fix: "{수정 제안}"
  },
  
  resolution: {
    action: "retry_cycle",
    transitioned_to: "ANALYSIS",
    retry_count: N
  }
}
```

### 7.2 다중 FAIL 처리

여러 stage에서 동시에 FAIL이 발생한 경우:

```
1. 모든 stage를 실행 (중간에 중단하지 않음)
2. 모든 FAIL을 하나의 failure_entry에 기록
3. root_cause_hypothesis에서 FAIL 간 관계 분석:
   → unit test FAIL + chainbench FAIL이 동일 원인인지
   → lint FAIL은 독립적 이슈인지
4. 재진입 시 Planner에게 모든 FAIL 정보를 전달
```

---

## 8. State 업데이트

### 8.1 EVALUATION 상태 필드

```jsonc
{
  "EVALUATION": {
    "status": "completed",
    "started_at": "...",
    "completed_at": "...",
    "results": {
      "unit_test": "PASS",
      "lint": "PASS",
      "security": "WARN",
      "chainbench": "FAIL"
    },
    "overall": "FAIL",
    "report_path": "test-report.md",
    "log_paths": {
      "unit_test": "logs/unit-test.log",
      "lint": "logs/lint.log",
      "security": "logs/vet.log",
      "chainbench": "logs/chainbench.log"
    }
  }
}
```

---

## 9. Phase 6 완료 기준

- [ ] Evaluator Agent가 4개 stage를 순차 실행
- [ ] Unit test 결과 파싱 (passed/failed/coverage)
- [ ] Lint & Format 검사 동작 (golangci-lint, gofmt, goimports)
- [ ] Security scan 동작 (go vet + 코드 패턴 검사)
- [ ] ChainBench MCP 연동: 빌드 → 네트워크 구성 → 블록 생성 확인 → tx 테스트
- [ ] ChainBench 타임아웃 및 정리(cleanup) 보장
- [ ] test-report.md 생성 (구조화된 리포트)
- [ ] 다중 FAIL 시 모든 실패를 하나의 failure_entry에 기록
- [ ] state.json의 EVALUATION 결과 필드 업데이트
- [ ] PASS → Orchestrator에 COMPLETION 전이 요청
- [ ] FAIL → failure_log 기록 + Orchestrator에 재진입 요청
