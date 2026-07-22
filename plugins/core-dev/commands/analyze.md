---
description: 자유 텍스트 요구사항 기반 작업 시작. 요구사항 intake → ticket.json 합성 → Orchestrator 디스패치. Jira 불필요.
argument-hint: "\"<요구사항 텍스트>\"  [--type feature|bugfix|code_review|release] [--auto-merge]"
allowed-tools: Read, Write, Edit, Bash, Agent, TodoWrite, mcp__plugin_core-dev_stablenet-knowledge, mcp__plugin_core-dev_chainbench, mcp__plugin_core-dev_jira-gateway
---

# /core-dev:analyze

Jira 티켓 없이 **자유 텍스트 요구사항**으로 자동화 파이프라인을 시작한다.
`/core-dev:work` 와 동일한 파이프라인(planner→implementer→evaluator)을 타되,
진입만 자유 텍스트다. 내부적으로 요구사항을 `ticket.json` 으로 합성하여 기존
`template-parse` + Orchestrator 를 그대로 재사용한다(`requirement_source: "local"`).

> 자율 진입: 이 커맨드는 Jira·중복·민감정보로 인한 **사용자 프롬프트가 없다**.
> 매 실행이 새 `LOCAL-{timestamp}` 작업이며, 로컬 민감정보는 auto-redact 후 진행한다.

---

## 0. 인자 형식

- 기본: `/core-dev:analyze "consensus Finalize 의 nil pointer 패닉을 고쳐줘"`
- 유형 힌트(선택): `... --type bugfix` (생략 시 본문에서 추론)
- 자동 머지(선택): `... --auto-merge` — PR 생성에서 멈추지 않고 merge/tag/push까지 자율.
  **기본은 OFF**(merge/push/tag 게이트 유지). 켜도 merge.md §3 안전조건(APPROVED/CI/MERGEABLE)은 유지된다.

---

## 1. 인자 검증

```
1.1. 인자 파싱
   - 따옴표로 감싼 요구사항 본문 → requirement_text
   - 옵션 --type <feature|bugfix|code_review|release> → type_hint (선택)
   - 옵션 --auto-merge (플래그) → auto_merge_flag = true (기본 false)
   - 빈 요구사항 → 사용법 출력 후 중단:
     "사용법: /core-dev:analyze \"<요구사항 텍스트>\" [--type <유형>] [--auto-merge]"
```

---

## 2. .stablenet-expert/ 디렉토리 확인

```
2.1. 프로젝트 루트 확인
   bash: git rev-parse --show-toplevel
   실패 → "git 레포가 아닙니다. go-stablenet 레포 안에서 실행하세요." → 중단
   성공 → repo_root 저장
2.2. bash: mkdir -p {repo_root}/.stablenet-expert/tickets
```

---

## 3. 작업 폴더 생성 (항상 새 작업)

```
3.1. bash: date -u +"%Y%m%d_%H%M%S"  → timestamp
3.2. local_id = "LOCAL-{timestamp}"
3.3. workspace = "{repo_root}/.stablenet-expert/tickets/{local_id}"
3.4. bash: mkdir -p {workspace}/logs
```
중복/복구 판별은 생략한다 — local_id 가 매번 고유하므로 항상 신규 작업이다(사용자 프롬프트 없음).

---

## 4. 요구사항 intake → ticket.json 합성

자유 텍스트를 `template-parse` 가 파싱할 수 있는 구조로 LLM이 직접 합성한다.

```
4.1. work_type 결정
   type_hint 가 있으면 그 값. 없으면 requirement_text 내용으로 추론:
     - "버그/패닉/에러/fix/깨짐/실패" 중심 → bugfix
     - "리뷰/검토/review" 중심 → code_review
     - "릴리즈/태그/버전/release" 중심 → release
     - 그 외(새 동작/기능/개선) → feature

4.2. description(markdown) 합성
   template-parse 가 인식하는 헤더로 본문을 구성한다(섹션이 비면 LLM 추론으로 보강하되
   확신 없는 값은 비워 missing_fields 로 남긴다):

   - 공통 첫 줄:  "## 작업 유형: {work_type}"
   - feature:   ## 요약 / ## 배경 / ## 요구사항(체크리스트) / ## 영향 범위(모듈) / ## 수용 기준
   - bugfix:    ## 요약 / ## 재현 방법 / ## 기대 동작 / ## 실제 동작 / ## 영향 범위(모듈, 심각도) / ## 수용 기준
   - code_review: ## 요약 / ## 리뷰 대상 / ## 리뷰 기준
   - release:   ## 요약 / ## 버전 / ## 포함 변경사항 / ## 릴리즈 체크리스트

   본문은 requirement_text 를 충실히 반영하되, go-stablenet 도메인 용어를 보존한다.
   (영향 범위 모듈을 단정하기 어려우면 비워 둔다 — planner 가 stablenet-knowledge 로 정밀 분석한다.)

4.3. 로컬 민감정보 스캔 (auto-redact, 하드스톱 없음)
   requirement_text 에서 명백한 비밀(예: API 키/토큰/패스워드/`sk-`·`ghp_`·`-----BEGIN` 등)을
   탐지하면 description 내 해당 값을 "[REDACTED]" 로 치환하고 카운트한다.
     scan_result = (치환 발생) ? "REDACTED" : "CLEAN"   # 절대 BLOCKED 로 중단하지 않음

4.4. ticket.json 저장 ({workspace}/ticket.json)
   {
     "ticket_id": "{local_id}",
     "type": "{work_type}",
     "summary": "<한 줄 요약>",
     "description": "<4.2 에서 합성한 markdown>",
     "requirement_source": "local",
     "_filter_metadata": { "scan_result": "{scan_result}", "redacted_count": N }
   }
```

---

## 5. ticket_type 식별 + state.json 초기화

```
5.1. template-parse skill 호출
   input: ticket.description (4.2 의 markdown), summary: ticket.summary
   output: { work_type, summary, pipeline_variant, fields, missing_fields, warnings }
   결과를 {workspace}/ticket-parsed.json 으로 저장.
   (work_type 이 intake 추론과 다르면 template-parse 결과를 우선한다.)

5.2. missing_fields 는 중단 사유가 아니다
   비어있지 않아도 진행한다 — planner 가 ANALYSIS 에서 stablenet-knowledge 로 보강한다(프롬프트 없음).

5.3. state.json 초기화
   base_ref = bash: git rev-parse HEAD    # 지금 체크아웃된 커밋이 이 티켓의 베이스 — 이후 어떤
                                          # 단계도 다른 브랜치로 checkout/pull 해 베이스를 옮기지 않는다
   state-machine.init_state(
     ticket_id={local_id},
     ticket_type={work_type},
     workspace_dir={workspace},
     pipeline_variant={pipeline_variant},
     requirement_source="local",
     base_ref={base_ref}
   )
   # autonomy 는 requirement_source="local" 에서 {mode:auto, on_blocked:escalate,
   # auto_merge:false} 로 유도된다. --auto-merge 가 주어졌으면 init_state 후
   # state.config.autonomy.auto_merge = true 로 덮어쓴다(merge/tag/push 게이트 해제;
   # 단 merge.md §3 안전조건은 유지). 미지정 시 false(PR 까지만 자율).

5.4. TICKET_INTAKE.sensitive_check 기록
   states.TICKET_INTAKE.sensitive_check = {
     "result": "{scan_result}",        # CLEAN | REDACTED (로컬 스캔)
     "redacted_count": N,
     "scanned_at": "{ISO now}"
   }
```

---

## 6. Orchestrator Agent 디스패치

```
6.1. Agent(
       subagent_type="orchestrator",
       description="Run core-dev pipeline for {local_id} (local requirement)",
       prompt="workspace_dir={workspace}\nmode=fresh"
     )
6.2. 완료 후 출력:
   "자유 텍스트 요구사항 작업을 시작했습니다. workspace: {workspace}
    (requirement_source=local — Jira 동기화 없이 PR 생성까지 진행, merge 는 /core-dev:merge 로 별도)"
```

---

## 7. 완료 기준 (체크리스트)

- [ ] 빈 요구사항에 사용법 출력
- [ ] git 레포 아닐 때 명확한 에러
- [ ] 매 실행 고유 LOCAL-{timestamp} 작업 폴더 생성 (중복/복구 프롬프트 없음)
- [ ] 자유 텍스트 → template-parse 헤더 형식 ticket.json 합성
- [ ] 로컬 민감정보 auto-redact (BLOCKED 하드스톱 없음)
- [ ] state.json 이 requirement_source="local" 로 초기화
- [ ] Orchestrator 가 Jira 호출 없이 파이프라인 수행 (PR 생성까지 자율, merge 게이트 유지)
