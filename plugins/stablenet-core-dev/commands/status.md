---
description: 작업 상태 조회. 특정 티켓 또는 전체 활성 작업의 진행 상황을 출력.
argument-hint: "[JIRA-ID] (생략 시 전체 활성 작업)"
---

# /stablenet-core-dev:status

작업 상태를 조회한다.

---

## 1. 인자 분기

```
1.1. 빈 인자 → 전체 활성 작업 모드 (3단계로 진행)
1.2. JIRA-ID 형식 (/^[A-Z]+-\d+$/) → 특정 티켓 모드 (2단계로 진행)
1.3. 형식 불일치 → 사용법 안내 후 중단:
   "사용법: /stablenet-core-dev:status [JIRA-ID]
    예: /stablenet-core-dev:status STABLE-1234
    생략: 전체 활성 작업 목록"
```

---

## 2. 특정 티켓 상세 모드

```
2.1. 프로젝트 루트 확인
   bash: git rev-parse --show-toplevel → repo_root

2.2. 작업 폴더 탐색
   bash: ls -d {repo_root}/.stablenet-expert/tickets/{jira_id}_* 2>/dev/null | sort -r
   
   결과 없음 → 출력: "{jira_id}에 대한 작업이 없습니다." + 중단
   결과 있음 → 가장 최신 폴더 선택 (workspace)

2.3. state.json 로드
   read {workspace}/state.json → state

2.4. 마지막 활동 시각 계산
   states 객체에서 가장 최근 started_at 또는 completed_at 추출
   IMPLEMENTATION 단계라면 plan_progress.steps[*].last_checkpoint.at 도 후보

2.5. 아티팩트 목록 수집
   bash: ls {workspace} | grep -v "^logs$"

2.6. IMPLEMENTATION 단계인 경우 step 진행률
   IF state.current_state == "IMPLEMENTATION":
     state.states.IMPLEMENTATION.plan_progress.steps 순회:
       status == "completed" → "✓"
       status == "in_progress" → "◐"
       status == "pending" → "○"
       status == "failed" → "✗"
       
     in_progress + last_checkpoint 존재 시:
       체크포인트 정보 표시 (work_in_progress, uncommitted_files)

2.7. 출력 포맷
   다음 형식으로 출력:
   
   ┌─ {ticket_id} ──────────────────────────────────────┐
   │ State:        {current_state}                       │
   │ Agent:        {current_agent || "—"}                │
   │ Workspace:    {workspace (basename)}                 │
   │ Created:      {created_at}                          │
   │ Last activity:{last_activity 시각}                  │
   │ Branch:       {state.states.IMPLEMENTATION.branch || "—"} │
   │                                                      │
   │ Failures:     {failure_summary.total_failures}건    │
   │   by_state:   {by_state}                            │
   │   by_type:    {by_type}                             │
   │   patterns:   {recurring_patterns 개수}             │
   │                                                      │
   │ Artifacts:                                           │
   │   - ticket.json                                      │
   │   - analysis.md                                      │
   │   - plan.md                                          │
   │   - design-v2.md                                     │
   │                                                      │
   │ Plan Progress (IMPLEMENTATION 단계인 경우):           │
   │   [1] ✓ 인터페이스 추가 (commit: a1b2c3d)            │
   │   [2] ◐ 로직 구현                                    │
   │       checkpoint: 함수 구현 70%, edge case 남음       │
   │       uncommitted: consensus/wbft/finalize.go        │
   │   [3] ○ 테스트 추가                                  │
   │   [4] ○ 통합 테스트                                  │
   │   [5] ○ 문서 업데이트                                │
   │                                                      │
   │ PR:           {COMPLETION.pr_url || "—"}            │
   └──────────────────────────────────────────────────────┘

2.8. 같은 ticket_id의 추가 폴더 안내
   동일 ticket_id로 여러 폴더가 있으면 (재작업 이력):
     "이 티켓의 이전 작업 폴더 {N}개가 더 있습니다."
```

---

## 3. 전체 활성 작업 모드

```
3.1. 프로젝트 루트 확인
   bash: git rev-parse --show-toplevel → repo_root

3.2. 활성 작업 폴더 스캔
   bash: ls -d {repo_root}/.stablenet-expert/tickets/*_* 2>/dev/null

3.3. 각 폴더의 state.json 로드 + 필터
   for each folder:
     read {folder}/state.json
     활성 조건: current_state not in ["COMPLETED"]
     활성이면 → active_workspaces 배열에 추가

3.4. 활성 작업 없음 처리
   IF active_workspaces.empty:
     "활성 작업이 없습니다." 출력 후 종료

3.5. timestamp 역순 정렬 (최신 우선)
   active_workspaces.sort by state.created_at DESC

3.6. 출력 포맷 (요약형)
   다음 형식으로 한 줄씩 출력:
   
   활성 작업 ({N}건):
   
   {ticket_id}  {current_state}  {last_activity}  {failure_summary.total_failures}건 실패
   ────────────  ──────────────  ──────────────  ──────────────
   STABLE-1234  IMPLEMENTATION  2026-05-28 01:30  1건 실패
   STABLE-1230  EVALUATION      2026-05-27 14:20  0건
   STABLE-1228  BLOCKED         2026-05-26 10:15  3건 실패  ⚠
   
   상세: /stablenet-core-dev:status <JIRA-ID>

3.7. BLOCKED 작업 강조
   BLOCKED 상태 작업이 있으면 별도 섹션으로 강조:
   
   ⚠ BLOCKED 작업 ({N}건) - 수동 개입 필요:
     STABLE-1228:
       실패 횟수: 3 (max_eval_cycles 초과)
       Recurring: {recurring_patterns 첫 항목}
       마지막 활동: 2026-05-26 10:15
```

---

## 4. 에러 처리

| 시나리오 | 처리 |
|---------|------|
| .stablenet-expert/ 미존재 | "코딩 에이전트가 아직 사용된 적이 없습니다." 출력 |
| state.json 손상 (JSON 파싱 실패) | 해당 폴더 skip, 다른 폴더는 정상 처리 + 경고 |
| ticket_id 부분 매치 | 정확한 매치만 인정 (STABLE-12는 STABLE-123에 매치되지 않음) |

---

## 5. 완료 기준 (체크리스트)

- [ ] 특정 티켓 상세 상태 출력 (state, 아티팩트, 실패 이력, plan_progress)
- [ ] IMPLEMENTATION 단계에서 step별 진행률 (✓/◐/○/✗) + checkpoint 표시
- [ ] 전체 활성 작업 목록 출력 (요약형, timestamp 역순)
- [ ] 활성 작업 없을 때 명확한 메시지
- [ ] BLOCKED 작업 별도 강조
- [ ] 동일 티켓의 여러 작업 폴더 안내
- [ ] state.json 손상 시 graceful handling
