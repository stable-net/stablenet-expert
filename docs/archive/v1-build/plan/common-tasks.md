# 공통/인프라 작업 — 작업 상세

---

## COMMON-1. shared/patterns.json [NEW] `S`

**상태**: ✅ 완료

14개 민감정보 패턴 정의. Jira Gateway MCP(Go)와 (R1′ 이전 자체 시점의) CKS MCP(Go) 양쪽에서 공유. **R1′ Step 6 (2026-06-02) 후**: 자체 cks-mcp 폐기로 outbound 사용처는 jira-gateway-mcp + `pr-sanitize` skill 두 곳.

커스텀 패턴 merge 로직은 P2-7에서 구현.

---

## COMMON-2. .coding-agent/ 폴더 관리 유틸리티 [NEW] `M`

**사용처**: /work, /status, /review 커맨드 + Orchestrator

**핵심 로직**:
```
find_workspace(ticket_id: string, status_filter?: string): WorkspaceInfo[]
  1. glob: .coding-agent/tickets/{ticket_id}_*/state.json
  2. 각 state.json 읽기
  3. status_filter 지정 시 current_state 필터
  4. timestamp 역순 정렬 (최신 우선)
  5. return [{workspace_dir, current_state, created_at, ticket_type}]

find_active_workspaces(): WorkspaceInfo[]
  1. glob: .coding-agent/tickets/*/state.json
  2. current_state가 "COMPLETED"가 아닌 것만 필터
  3. timestamp 역순 정렬

create_workspace(ticket_id: string): string
  1. timestamp = UTC now, format YYYYMMDD_HHmmss
  2. path = .coding-agent/tickets/{ticket_id}_{timestamp}/
  3. mkdir -p {path}/logs/
  4. return path
```

**구현 위치**: skill로 제공하거나, 각 command에서 bash로 직접 구현.
skill이 적합 — 여러 command/agent가 공유하므로.

**완료 기준**:
- [ ] find_workspace가 ticket_id로 정확 필터
- [ ] find_active_workspaces가 완료되지 않은 작업만 반환
- [ ] create_workspace가 올바른 경로 + logs/ 생성
- [ ] .coding-agent/ 루트 디렉토리 자동 생성 (미존재 시)

---

## COMMON-3. 안전장치 (Safeguard) [ADAPT] `M`

**사용처**: state-machine skill, Implementer Agent, Orchestrator

**핵심 로직**:
```
1. 무한 루프 방지
   state.json config:
     max_eval_cycles: 3 (EVAL→ANALYSIS 재진입 상한)
     max_design_revisions: 3 (DESIGN self-review 상한)
   초과 시 → BLOCKED 상태 전이

2. 브랜치 보호
   Implementer가 커밋 전:
     current_branch = bash: git branch --show-current
     if current_branch in ["main", "master"]:
       abort: "main/master에 직접 커밋할 수 없습니다"
   브랜치명 규칙: feature/{TICKET-ID} 또는 fix/{TICKET-ID}

3. 커밋 크기 제한
   커밋 전:
     file_count = bash: git diff --cached --name-only | wc -l
     diff_lines = bash: git diff --cached --stat | tail -1  # insertions + deletions
     if file_count > 10 OR diff_lines > 500:
       warn: "변경이 큽니다. 분할 커밋을 권장합니다."
       (경고만, 강제 차단은 아님)

4. ChainBench 타임아웃
   전체: 20분
   빌드: 5분, 네트워크: 2분, 모니터링: 5분, tx 테스트: 5분
   타임아웃 시 → cleanup 강제 실행
```

**buddy 참고**:
- `plugin/skills/guard-destructive-commands/PROCEDURE.md` — 파괴적 명령 방지
- `plugin/skills/freeze-edit-scope/PROCEDURE.md` — 편집 범위 제한

**완료 기준**:
- [ ] max_eval_cycles 초과 시 BLOCKED
- [ ] max_design_revisions 초과 시 BLOCKED
- [ ] main/master 직접 커밋 차단
- [ ] 커밋 크기 경고

---

## COMMON-4. 로깅 체계 [NEW] `M`

**사용처**: 모든 에이전트

**핵심 로직**:
```
각 에이전트가 실행 시:
  log_path = {workspace_dir}/logs/{agent_name}.log

로그 포맷 (한 줄 = 한 이벤트):
  {ISO_timestamp} [{level}] {message}
  
  level: INFO, WARN, ERROR, DEBUG

기록 대상:
  INFO: 상태 전이, 단계 시작/완료, MCP 호출, 커밋
  WARN: 커밋 크기 경고, Jira 업데이트 실패, 오탐 가능 민감정보
  ERROR: 빌드 실패, 테스트 실패, 네트워크 오류
  DEBUG: CKV/CKG 검색 쿼리/결과 요약, 임베딩 시간

failure 상세 로그:
  {workspace_dir}/logs/eval-fail-{NNN}.log
  → Evaluator의 각 FAIL stage 원본 출력 전체 저장
```

**완료 기준**:
- [ ] 각 에이전트별 로그 파일 생성
- [ ] 타임스탬프 + 레벨 + 메시지 포맷
- [ ] failure 상세 로그 (원본 출력 보존)
