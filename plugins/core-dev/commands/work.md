---
description: Jira 티켓 기반 작업 시작. 티켓 읽기 → 민감정보 필터 → 작업 폴더 생성 → Orchestrator 디스패치.
argument-hint: "<JIRA-ID, 예: STABLE-1234> [--local <path>]"
allowed-tools: Read, Write, Edit, Bash, Agent, TodoWrite, mcp__plugin_core-dev_stablenet-knowledge, mcp__plugin_core-dev_chainbench, mcp__plugin_core-dev_jira-gateway
---

# /core-dev:work

Jira 티켓 기반 자동화 작업을 시작한다.

---

## 0. 인자 형식

- 기본: `/core-dev:work STABLE-1234`
- 로컬 테스트: `/core-dev:work STABLE-1234 --local ./test-ticket.json`
  - `--local <path>`: MCP 호출 대신 지정 파일을 ticket.json으로 직접 사용
  - Phase 2 (Jira Gateway MCP) 완료 전 Phase 1 테스트 용도

---

## 1. 인자 검증

```
1.1. 인자 파싱
   - 위치 인자 1: jira_id
   - 옵션 --local <path>: 로컬 ticket 파일 경로
   - 빈 인자 → 사용법 출력 후 중단:
     "사용법: /core-dev:work <JIRA-ID>
      예: /core-dev:work STABLE-1234
      로컬 테스트: /core-dev:work STABLE-1234 --local ./test-ticket.json"

1.2. JIRA-ID 형식 검증
   regex: /^[A-Z]+-\d+$/
   불일치 → "JIRA-ID 형식이 올바르지 않습니다. 예: STABLE-1234"
```

---

## 2. .stablenet-expert/ 디렉토리 확인

```
2.1. 프로젝트 루트 확인
   bash: git rev-parse --show-toplevel
   실패 → "git 레포가 아닙니다. /core-dev:work는 git 레포 내에서 실행해야 합니다."
   성공 → repo_root 저장

2.2. .stablenet-expert/tickets/ 디렉토리 생성 (없으면)
   bash: mkdir -p {repo_root}/.stablenet-expert/tickets
```

---

## 3. 중복/복구 판별

```
3.1. 동일 ticket_id의 기존 작업 폴더 탐색
   bash: ls -d {repo_root}/.stablenet-expert/tickets/{jira_id}_* 2>/dev/null | sort -r
   
   결과 없음 → 4단계로 진행 (새 작업)
   결과 있음 → 가장 최신 폴더부터 state.json 읽기

3.2. 기존 작업 상태별 처리
   for each existing_workspace (최신순):
     read existing_workspace/state.json
     
     case state.current_state:
       "COMPLETED":
         continue → 다음 폴더 확인 (또는 새 작업 생성)
       
       "BLOCKED":
         자율 모드 분기 (existing state.config.autonomy.mode):
           == "auto":
             묻지 않고 새 작업으로 진행 (4단계). 이전 BLOCKED 워크스페이스는 보존.
             로그: "이전 BLOCKED 작업 발견 — 자율 모드라 새 작업으로 진행합니다."
           그 외 ("interactive"):
             사용자에게 질문:
               "이전 작업이 BLOCKED 상태입니다 (workspace: {existing_workspace}).
                원인: {state.failure_summary 요약}
                재개하시겠습니까? (y/n) 또는 새 작업을 시작하시겠습니까? (new)"
             답변에 따라:
               y → 복구 모드로 진행 (5단계로 점프, workspace = existing_workspace)
               new → 새 작업 (4단계로 진행)
               n 또는 기타 → 중단
       
       그 외 (in_progress 상태들):
         사용자에게 알림: "진행 중인 작업이 있습니다 ({existing_workspace}). 복구합니다."
         복구 모드로 진행:
           workspace = existing_workspace
           state-machine.get_resume_point(workspace) 호출
           반환된 resume_point를 Orchestrator에 전달
         → 7단계로 점프 (Orchestrator 디스패치)
```

---

## 4. 새 작업 폴더 생성

```
4.1. timestamp 생성
   bash: date -u +"%Y%m%d_%H%M%S"
   → timestamp 변수에 저장

4.2. workspace 경로 결정
   workspace = "{repo_root}/.stablenet-expert/tickets/{jira_id}_{timestamp}"

4.3. 폴더 생성
   bash: mkdir -p {workspace}/logs
```

---

## 5. Jira 티켓 읽기 + 민감정보 필터

```
5.1. --local 옵션 사용 시 (로컬 테스트)
   ticket_path = 옵션 값
   bash: test -f {ticket_path} || echo "FILE_NOT_FOUND"
   not found → 중단
   bash: cp {ticket_path} {workspace}/ticket.json
   sensitive_check 결과는 "LOCAL_BYPASS"로 마킹 (실제 필터 미적용 경고)
   → 6단계로 진행

5.2. 기본: Jira Gateway MCP 호출
   mcp tool: jira_read_ticket(ticket_id={jira_id})

   호출 자체가 실패한 경우(MCP 미등록/미연결, 인증 실패, 네트워크 오류 —
   즉 _filter_metadata 가 포함된 정상 응답이 아닌 경우):
     유저에게 알림:
       "jira-gateway MCP 호출에 실패했습니다: {error 요약}.
        확인: (1) .mcp.json 에 jira-gateway 가 등록되어 있고
        JIRA_BASE_URL/JIRA_API_TOKEN/JIRA_USER_EMAIL 가 환경에 설정되었는가,
        (2) docs/SETUP.md §4.1 의 curl 검증이 통과하는가.
        로컬 테스트는 `--local <ticket.json>` 로 Jira 없이 진행할 수 있습니다."
     작업 폴더 정리: bash: rm -rf {workspace}
     중단 (이 분기는 콘텐츠 스캔 결과 처리(5.3)와 별개 — 전송/인증 실패다)

   응답에는 _filter_metadata가 포함:
   {
     "ticket_id": "...",
     "type": "...",
     "summary": "...",
     "description": "...",
     "assignee": "...",
     "status": "...",
     "_filter_metadata": {
       "scan_result": "CLEAN" | "REDACTED" | "BLOCKED",
       "redacted_count": N,
       "redacted_patterns": ["..."],
       ...
     }
   }

5.3. 필터 결과 처리
   case _filter_metadata.scan_result:
     "CLEAN":
       정상 진행
     
     "REDACTED":
       유저에게 경고: 
         "Jira 티켓에서 {redacted_count}개의 민감정보가 감지되어 마스킹되었습니다.
          탐지 패턴: {redacted_patterns}
          계속 진행합니다."
     
     "BLOCKED":
       유저에게 알림:
         "Jira 티켓에 critical 민감정보가 감지되어 작업을 중단합니다.
          탐지 패턴: {detected_patterns}
          Jira 티켓에서 해당 정보를 제거한 후 다시 시도하세요."
       작업 폴더 정리: bash: rm -rf {workspace}
       중단

5.4. ticket.json 저장
   응답 데이터(_filter_metadata 포함)를 {workspace}/ticket.json 으로 저장
```

---

## 6. ticket_type 식별 + state.json 초기화

```
6.1. template-parse skill 호출
   input: ticket.description (markdown)
   output: { work_type, pipeline_variant, fields, missing_fields, warnings }
   
   결과를 {workspace}/ticket-parsed.json 으로 저장.

6.2. missing_fields 처리
   missing_fields 가 비어있지 않으면:
     유저에게 경고: "다음 필수 필드가 누락되었습니다: {missing_fields}
                   작업은 진행되지만, Planner가 추론으로 보강할 수 있습니다."

6.3. state.json 초기화
   base_ref = bash: git rev-parse HEAD    # 지금 체크아웃된 커밋이 이 티켓의 베이스 — 이후 어떤
                                          # 단계도 다른 브랜치로 checkout/pull 해 베이스를 옮기지 않는다
   state-machine.init_state(
     ticket_id={jira_id},
     ticket_type={work_type},
     workspace_dir={workspace},
     pipeline_variant={pipeline_variant},
     base_ref={base_ref}
   )

6.4. TICKET_INTAKE.sensitive_check 기록
   state.json 의 states.TICKET_INTAKE.sensitive_check 필드에:
     {
       "result": "{_filter_metadata.scan_result}",
       "redacted_count": N,
       "scanned_at": "{current ISO timestamp}"
     }
```

---

## 7. Orchestrator Agent 디스패치

```
7.1. 디스패치 컨텍스트 구성
   prompt_context = {
     "workspace_dir": "{workspace}",
     "mode": "fresh" | "resume",
     "resume_point": {...} (복구 모드인 경우에만)
   }

7.2. Agent 도구로 Orchestrator 호출
   Agent(
     subagent_type="orchestrator",
     description="Run core-dev pipeline for {jira_id}",
     prompt="workspace_dir={workspace}\nmode={mode}\n{resume_point 정보}"
   )

7.3. Orchestrator 완료 후
   결과 메시지를 유저에게 출력:
     - 새 작업이었으면: "작업이 시작되었습니다. workspace: {workspace}"
     - 복구였으면: "작업이 재개되었습니다. 진행 중인 단계: {current_state}"
```

---

## 8. 완료 기준 (체크리스트)

- [ ] 유효하지 않은 JIRA-ID에 에러 메시지 출력
- [ ] git 레포가 아닐 때 명확한 에러 메시지
- [ ] 기존 in_progress 작업 발견 시 복구 모드 진입
- [ ] BLOCKED 작업 발견 시 유저 확인 후 재개/새 작업/중단 선택
- [ ] `--local` 옵션으로 MCP 없이 테스트 가능
- [ ] sensitive_check 결과(CLEAN/REDACTED/BLOCKED)별 동작 분기
- [ ] `.stablenet-expert/tickets/` 하위에 올바른 폴더 생성 (timestamp 포함)
- [ ] state.json이 TICKET_INTAKE 상태로 초기화 + sensitive_check 정보 포함
- [ ] template-parse 결과로 pipeline_variant 결정
- [ ] Orchestrator Agent가 workspace_dir와 함께 디스패치
