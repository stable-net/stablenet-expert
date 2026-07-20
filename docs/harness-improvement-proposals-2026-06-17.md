# 하네스 개선 제안 — Claude 에이전틱 패턴 기반 (2026-06-17)

> **STATUS (2026-06-29): 제안 1~3 구현·머지됨 (v0.1.41).** Part D 롤아웃 순서대로
> **제안 2 git-guard** (`plugin/hooks/git-guard.py`, PreToolUse:Bash — main 직접 commit/push·
> force-push deny / reset --hard·clean -f·branch -D·tag push ask), **제안 1 Stop 훅**
> (`plugin/hooks/on-stop.py`, Stop — auto 모드·비종료·cycle 한도·`stop_hook_active`·staleness
> 가드 동봉), **제안 3 SessionStart** (`plugin/hooks/session-context.py` — 비종료 워크스페이스
> 주입) 신설 + `hooks/hooks.json` 배선 + 결정론 테스트(`bench/hooks/test_hooks.py`, overlay-gates 편입).
> **잔여 = 제안 4(교차-티켓 학습 lessons.md)·5(evaluator 병렬화)·6(state.json 스키마 검증)·7(context:fork).**
> SubagentStop 정밀 게이트(제안 1의 서브)는 의도적 보류(오버블록 위험 — Stop 본체로 충분).

문서 성격: **분석 + 제안 (status/proposal, 미구현)**. 구현 전 근거·합의용.
근거: Claude Code 코어(소스맵 복원본 ~1,900 TS 파일) 동작 원리 분석 문서 3종 +
`coding-agent` 플러그인 전체 인벤토리(agent 4 · hook 3 · skill 7 · command 9 · MCP 3) 교차 점검.
참조 원문: `Work/github/references/claude-code-reference/docs/`
(`agent-architecture-and-plugin-guide.md`, `claude-code-unreleased-features.md`,
`claude-code-vs-sourcemap-analysis.md`).

> **요약:** `coding-agent`는 **상태머신 오케스트레이션**(Orchestrator→Planner→Implementer→
> Evaluator)으로 이미 견고하게 설계돼 있다. 단 하나의 약점에 개선 여지가 집중된다 —
> **자율성·안전성·정보주입을 거의 전부 "에이전트 프롬프트 속 산문(prose)"으로만 구현하고,
> Claude 코어 루프가 제공하는 결정론적 확장 지점(Stop 훅 / PreToolUse 게이트 / SessionStart
> 주입)을 쓰지 않는다.** 산문 규칙은 모델이 흘릴 수 있으나 훅은 못 한다(fail-closed). 본 문서는
> (A) Claude 에이전틱 시스템의 우수 패턴을 다른 세션도 알 수 있게 정리하고, (B) 그 기준으로
> 플러그인을 진단하며, (C) 우선순위별 개선 제안 7건을 구현 스케치와 함께 제시한다.

---

# Part A. Claude 에이전틱 시스템의 핵심 패턴 (context 보존용)

> 이 파트는 **다른 세션에서 본 문서만 읽어도** Claude Code 코어가 "왜 그렇게 동작하는가"를
> 파악할 수 있도록 정리한 것이다. 모든 제안(Part C)은 이 원리에서 도출된다.

## A.1 엔진은 함수 하나 — `query()` 무한 루프

모든 대화는 `src/query.ts`의 `query()`(비동기 제너레이터 `while(true)`)가 처리한다.
별도의 "에이전트 객체"는 없다. iteration 사이에 `State` 하나(`messages`,
`toolUseContext`, `turnCount`, 압축/복구 추적 필드 등)를 갱신하며 돈다.

**에이전틱의 본질은 한 줄이다:**

> 모델이 **도구를 호출하면 루프를 한 번 더 돌고, 호출하지 않으면 끝난다.**

이 "다음 턴" 재귀가 자율 행동의 전부다. 종료·복구·재시도가 모두 "다음 `State`를 만들어
`continue`"로 표현된다.

## A.2 한 턴의 흐름 (단계별)

```
0. 턴 준비       메모리/스킬 prefetch(비차단), 쿼리 체인 추적
1. 컨텍스트 압축  applyToolResultBudget → snip → microcompact → collapse → autocompact
                 (싼 것부터 비싼 것 순서 — 앞이 줄이면 뒤는 no-op → 세밀함 최대 보존)
2. 시스템 프롬프트 확정
3. 하드 토큰 한계 검사 (초과 + 자동압축 꺼짐 → PROMPT_TOO_LONG)
4. 모델 호출(스트리밍)  tool_use 오면 needsFollowUp=true, 스트리밍 중 도구 즉시 착수
5. post-sampling 훅(비차단)
6. 분기:
   ├─ abort? → 미완 도구 합성결과로 메우고 종료
   ├─ 도구 없음 → [종료 경로] (A.3)
   └─ 도구 있음 → 도구 실행 후 다음 턴 (누적 컨텍스트가 다시 0단계로)
```

## A.3 루프는 언제 끝나는가 — **가장 중요한 포인트**

```
모델 응답에 tool_use 블록이 있는가?
   ├─ 있음 → 도구 실행 → 다음 턴 (무조건 한 턴 더)
   └─ 없음 → (413/출력초과 복구 시도)
            → Stop 훅 검사 ──block──▶ 사유를 컨텍스트에 주입하고 루프 계속
            → 통과 → Token budget 판단 → return { reason:'completed' }
```

자율성을 결정하는 3겹 메커니즘:

1. **자연 종료 = "도구를 안 부른 응답"**. 반대로 도구를 부르면 무조건 한 턴 더 돈다.
2. **복구 경로**: 토큰 한계로 깨지면 코어가 먼저 회복(collapse 드레인 / 한도 상향 재시도).
   `hasAttemptedReactiveCompact` 같은 가드로 death spiral(에러→압축→에러)을 차단.
3. **Stop 훅 + Token budget (최후 재정의)**: 도구가 없어 끝나려는 순간 Stop 훅이 `block`을
   반환하면 코어가 그 `reason`을 컨텍스트에 주입하고 **루프를 다시 돌린다**.
   → **자가 검증·자가 반복의 구현 지점.** 무한루프는 `maxTurns`·Token budget·
   `stopHookActive` 플래그가 함께 막는다.

## A.4 도구 한 건의 생애 — 7단계 파이프라인 (권한·훅 개입 지점)

```
1. 입력 Zod 검증
2. 도구별 추가 검증
3. PreToolUse 훅    ← 입력 변형(updatedInput) / allow·deny·ask 결정
4. 권한 판정        ← 모드 + allow/deny/ask 규칙 + (auto면) bash 분류기
5. tool.call() 실행
6. PostToolUse 훅   ← 출력 검증·변형
7. 결과 → 메시지    (50KB 초과 시 디스크 저장 + 프리뷰만 API로)
```

핵심 안전 원칙 **fail-closed**: `buildTool()`이 빠진 필드를 *안전한 디폴트*로 채운다
(읽기전용 아님·병렬 불가·권한 필요로 가정). 즉 **모르면 막는다.**

## A.5 서브에이전트 = 또 하나의 `query()` 루프

`AgentTool`이 자식을 만들지만, 자식도 *제한된 도구풀 + 전용 시스템 프롬프트 + 독립
AbortController*로 같은 루프를 재귀 실행하고 **결론만**(텍스트 + 토큰/툴카운트) 부모에 돌려준다.
부모는 파일 덤프가 아니라 요약을 받는다. 코어가 서브에이전트에 자동 적용하는 안전장치:
재귀 `AgentTool` 금지, `AskUserQuestion`/`ExitPlanMode`/`Workflow` 제거, 비동기 에이전트는
화이트리스트 도구만.

## A.6 플러그인이 채울 수 있는 5개 지점 — 그리고 그 한계

> **플러그인은 `query()` 루프를 대체할 수 없다.** 루프는 바이너리 안에 있다. 플러그인은
> 루프의 *이미 뚫린 확장 지점*만 채운다. "에이전트답게 만들기" = 아래 6요소를 올바로 채우는 일.

| # | 요소 | 아티팩트 | 루프에서의 역할 |
|---|------|---------|----------------|
| ① | 정체성 | `agents/*.md` (프론트매터 + 본문=시스템프롬프트) | **완료기준**을 본문에 명시해야 자연 종료(A.3) |
| ② | 능력 | `mcpServers` / 에이전트 `tools` 스코프 | 행동 능력 + 최소권한 경계 |
| ③ | 정보 | **SessionStart / UserPromptSubmit 훅** → `additionalContext` | 플러그인 고유 지식 주입 |
| ④ | 제어 | **PreToolUse(게이트) / PostToolUse(검증) / Stop(자율반복)** 훅 | 가드레일 + 자가 반복 |
| ⑤ | 위임 | `skills/<n>/SKILL.md` (`context: fork`) | 무거운 작업을 격리 서브에이전트로 |
| ⑥ | 안전 | 완료기준(①) + Stop 훅 수렴조건(④) + maxTurns/예산 인지 | 멈출 조건 |

**Stop 훅 동작 규약:** `{"decision":"block","reason":"..."}` 반환 → 코어가 reason 주입 후
루프 계속. 여러 훅은 병렬 실행, 결과는 **deny > ask > allow** 우선순위로 합쳐진다.

## A.7 진화 방향 (미출시 기능이 가리키는 곳 — 설계 영감)

소스맵에서 확인된 미출시 기능들은 이 플러그인의 로드맵 영감이 된다:

- **Coordinator Mode**(🟢): 리더 에이전트가 워커를 병렬 생성→연구/종합/구현/검증 4단계.
- **Auto Dream**(🟢): 오프라인에 여러 세션 학습을 메모리로 통합(시간/세션/잠금 3게이트).
- **Session Memory**(🟢): 대화 중 핵심 정보 자동 추출→마크다운 노트.
- **Skill Improvement / Magic Docs**(🔴/🟡): 사용 후 자동 개선 / 자동 갱신 문서.
- **Proactive + Remote Triggers**(🔴/🟢): 자발적 작업 개시 / 크론 기반 스케줄 실행.

→ 공통 테마: **세션 간 학습 + 병렬 협업 + 자율 반복**. Part C의 제안은 이 방향과 정합한다.

---

# Part B. coding-agent 플러그인 현재 상태 진단

## B.1 구조 한눈에

```
coding-agent/plugin/
├── .claude-plugin/plugin.json     # manifest (mcpServers→.mcp.json, hooks→hooks.json)
├── .mcp.json                      # MCP 3종: jira-gateway, cks, chainbench
├── agents/                        # orchestrator, planner, implementer, evaluator (+ bench 2종)
├── hooks/  hooks.json             # PreToolUse(Write|Edit) · PostToolUse(Agent,Bash,Write)
│   ├── doc-guard.py               #   문서 거버넌스 가드
│   ├── on-agent-complete.sh       #   서브에이전트 transcript JSONL 로깅
│   └── on-commit.sh               #   git commit 해시 로깅
├── skills/                        # state-machine, template-parse, stablenet-context,
│                                  # stablenet-invariants, root-cause-lifecycle, pr-sanitize,
│                                  # bench-orchestration
└── commands/                      # work, analyze, diagnose, bench, setup, status, review,
                                   # merge, doc-organize
```

## B.2 파이프라인 (상태머신)

```
TICKET_INTAKE → ANALYSIS → PLANNING → DESIGN → IMPLEMENTATION → EVALUATION
                                                        │              │
                                              EVALUATION_PASS    EVALUATION_FAIL
                                                        │              │
                                                   COMPLETION    (bug cycle ≤ max_eval_cycles)
                                                                       │
                                                                    BLOCKED
```

- **Orchestrator**: state.json을 읽어 다음 서브에이전트를 디스패치하는 *자기 프롬프트 루프*.
  "Do NOT spawn parallel sub-agents — 상태 전이는 직렬화돼야 한다"가 명시됨(정당).
- **Planner**: cks(시맨틱+그래프+impact/concurrency) 기반 ANALYSIS→PLANNING→DESIGN.
  derived-state write-site 완전성 검사(§5.2b)가 정교함.
- **Implementer**: 브랜치 격리, step별 split commit, checkpoint 복구, 바이너리 핸드오프.
- **Evaluator**: 4스테이지(unit+race / lint / security / chainbench) **순차** 실행,
  derived-state consistency 게이트(§4.6).
- **state-machine 스킬**: transition 게이트(artifact-existence 검증), failure_log,
  recurring_patterns, get_resume_point(중단 복구).

## B.3 Part A 6요소 대비 충족도

| 요소 | 현재 | 갭 |
|------|------|----|
| ① 정체성 | ✅ 4 에이전트 + 명시적 완료기준 | 양호 |
| ② 능력 | ✅ 최소권한 tool 스코프, MCP 3종 | 양호 |
| ③ 정보(주입 훅) | ❌ **SessionStart/UserPromptSubmit 훅 없음** (doc-guard만 부분 additionalContext) | **큼** |
| ④ 제어(게이트/Stop) | 🔸 PreToolUse는 doc-guard 1개, **Stop/SubagentStop 훅 0개** | **가장 큼** |
| ⑤ 위임 | ✅ Agent 디스패치, 단 **직렬·비병렬**, 스킬은 전부 inline | 부분 |
| ⑥ 안전 | 🔸 max_eval_cycles 등 *논리적* 수렴만, **루프-레벨 가드 없음** | 중간 |

## B.4 핵심 발견 (진단 결론)

1. **자율 진행이 Orchestrator 모델의 자발성에만 의존.** 모델이 중간에 도구 호출을 멈추면
   (current_state가 비종료인데) 파이프라인이 조용히 멈춘다 — Stop 훅이 없어 코어가 되돌릴
   장치가 없다(A.3 위반).
2. **안전정책이 전부 산문.** "never force-push / push to main / reset --hard / tag without
   confirm / edit go.mod"가 agent.md 텍스트에만 존재 → 모델이 흘리면 무방비. 코어의 fail-closed
   원칙(A.4)을 PreToolUse 훅으로 실체화하지 않음.
3. **세션 간 학습 부재.** `recurring_patterns`/`failure_log`가 **티켓 1개 state.json 안에만**
   쌓이고 BLOCKED 보고용으로만 소비됨 → 같은 실수를 다음 티켓에서 반복. (A.7 Auto Dream/
   Session Memory가 가리키는 학습 루프 없음.)
4. **단계 내 병렬화 미사용.** Evaluator의 unit/lint/security는 읽기전용·독립인데 순차 →
   wall-clock 낭비(A.5/A.7 Coordinator 패턴 미적용).

---

# Part C. 개선 제안 (우선순위순)

> 원칙: 기존 상태머신 아키텍처를 건드리지 않고 **증분 적용**한다. 제안 1~3은 각각
> `hooks/hooks.json` 항목 1개 + 훅 스크립트 1개 추가로 끝난다.

---

## 🥇 제안 1 — Stop/SubagentStop 훅으로 자율 파이프라인 경화

**근거**: A.3 · A.6-④. 자율 반복의 *코어 메커니즘*인 Stop 훅이 전혀 없다.

**문제**: 파이프라인 진행이 Orchestrator의 자기 프롬프트 루프에만 의존. 모델이 "다 한 듯"
하고 도구 호출을 멈추면 `current_state`가 `EVALUATION`이어도 파이프라인이 멈춘다.

**해결**: `hooks/on-stop.py` 추가 → `Stop` + `SubagentStop`에 등록.
- 활성 워크스페이스 `state.current_state`가 **종료/대기 상태가 아니면**
  `{"decision":"block","reason":"파이프라인 미완: current_state={S}. state.json 기준 다음 단계 계속."}`
  반환 → 코어가 사유 주입 후 루프 한 턴 더.
- SubagentStop: Planner 종료인데 필수 artifact(analysis.md/plan.md/design-v*.md) 부재 시
  block → "완료기준=artifact 존재"를 *프롬프트 신뢰*가 아닌 *루프에서 강제*.

**⑥ 안전 (필수 동봉)** — 무한루프 방지:
- `autonomy.mode=="auto"`일 때만 block. interactive/halt·BLOCKED·`COMPLETED`·
  max_eval_cycles 초과 시엔 **통과**(사용자 대기/수렴 종료를 방해 금지).
- 코어 `stopHookActive` 가드와 함께 동작. block 사유에 "현재 cycle/limit"을 포함해 모델이
  수렴 인지하도록.

```python
# 의사코드
state = read_active_workspace_state()
TERMINAL = {"COMPLETED", "BLOCKED"}
if state and state.current_state not in TERMINAL \
   and state.config.autonomy.mode == "auto" \
   and eval_cycles(state) < state.config.max_eval_cycles:
    emit({"decision": "block",
          "reason": f"파이프라인 미완(state={state.current_state}). "
                    f"state.json 기준 다음 단계를 계속하라."})
# 그 외 → exit 0 (통과)
```

---

## 🥈 제안 2 — PreToolUse Bash 가드레일 훅 (산문 안전정책 → 결정론적 게이트)

**근거**: A.4(도구 7단계, PreToolUse=③단계) · fail-closed(A.6) · A.1(2번 발견).

**문제**: 위험 git 작업 금지가 agent.md 산문에만 존재 → 모델이 흘리면 무방비.

**해결**: `hooks/git-guard.py` 추가 → `PreToolUse: Bash`에 등록.
- 명령 정규식 검사 →
  - `deny`: `push --force`/`-f`, `reset --hard`, **main/master 직접 push·commit**,
    비-feature 브랜치 `branch -D`, `git clean -fd`.
  - `ask`: `git tag` push, `go mod tidy`/`go.mod` 편집.
- state.json `autonomy.auto_merge` 플래그로 화이트리스트 분기(예: release tag는
  auto_merge=true면 통과). on-commit.sh가 이미 Bash payload(`.tool_input.command`)를
  파싱하므로 패턴 재사용 가능.

> 이건 자동화일 뿐 아니라 **자율 모드(`auto`)를 안심하고 켤 수 있게 하는 안전 기반**이다.
> 제안 1과 짝을 이룬다(자율 반복을 켜기 전에 가드를 먼저 깐다).

---

## 🥉 제안 3 — SessionStart 컨텍스트 주입 훅 (파이프라인 인지형 어시스턴트)

**근거**: A.6-③. 플러그인 고유 지식은 SessionStart `additionalContext`로 주입해야 매 쿼리에 실린다.

**문제**: 활성 티켓 상태를 알려면 매번 `/coding-agent:status`를 쳐야 함.

**해결**: `hooks/session-context.py` 추가 → `SessionStart`에 등록.
- `.stablenet-expert/tickets/*/state.json` 스캔 → 비종료 워크스페이스 요약 주입:
  *"진행 중: STABLE-1234 (EVALUATION, cycle 2/3). BLOCKED: STABLE-1300 — nil pointer 재발."*
- 세션 열자마자 Claude가 "재개할 일"을 인지 → 사용자가 "이어서 해줘"만 해도 동작.
- 비용 가드: 워크스페이스 N개 초과 시 최신 5개만, 요약은 워크스페이스당 1줄.

---

## 제안 4 — 교차-티켓 실패 학습 루프 (지능 향상의 핵심)

**근거**: A.7(Auto Dream / Session Memory / Skill Improvement) · B.4(3번 발견).

**문제**: `recurring_patterns`/`failure_log`가 티켓 1개 안에만 쌓이고 보고용으로만 소비됨 →
세션·티켓 간 학습 0.

**해결 (경량, 단계적)**:
1. `.stablenet-expert/lessons.md`(프로젝트 레벨 누적 파일) 도입.
2. Evaluator/Orchestrator가 EVALUATION_FAIL·BLOCKED 시 **일반화된 교훈 1줄** append
   (예: *"derived state 추가 시 eviction 경로 누락 반복 — planner §5.2b write-site 표 필수"*).
3. 제안 3 SessionStart 훅 + Planner가 ANALYSIS 시작 시 lessons.md를 읽어 컨텍스트 반영
   → **Planner가 과거 실수를 사전 회피**.

기존 `stablenet-invariants`(always-on 정적 backstop)와 같은 "상시 지식" 패턴을
**동적 학습**으로 확장하는 것. 향후 cks 인덱싱과 결합하면 Auto Dream에 근접.

---

## 제안 5 — Evaluator 단계 내 병렬화 (Coordinator 패턴, 처리량)

**근거**: A.5 · A.7(Coordinator Mode).

**문제**: Evaluator 4스테이지 순차 실행. 앞 3개(unit/lint/security)는 읽기전용·독립인데 직렬.

**해결**: **상태 전이는 직렬 유지**(Orchestrator 원칙 정당)하되, *한 단계 내부*에서:
- unit / lint / security를 병렬 서브에이전트(또는 Workflow `parallel`)로 fan-out.
- chainbench(바이너리 의존·무거움·자원 점유)만 직렬.
- ANALYSIS의 다중 seed `impact_analysis`도 동일하게 병렬 가능.

주의: 각 병렬 워커는 결론(stage 결과 JSON)만 반환하고, 통합·failure_log 머지는 Evaluator
본체가 barrier 후 수행(A.5 "결론만 회수").

---

## 제안 6 — PostToolUse state.json 스키마 검증 (보조)

**근거**: A.4(6단계 PostToolUse 출력검증).

**문제**: 현재 PostToolUse Write는 doc-guard만. state.json 손상은 다음 에이전트가 읽을 때야 발견.

**해결**: PostToolUse Write 훅에 state.json 분기 추가 → 쓰기 직후 JSON 유효성 + 필수 키
(`current_state`, `states`, `config`) 검증, 깨졌으면 `additionalContext`로 즉시 경고.

---

## 제안 7 — 무거운 작업을 `context: fork` 스킬로 (보조)

**근거**: A.6-⑤.

**문제**: 모든 스킬이 inline(`type: skill`) → 대화 컨텍스트에 펼쳐짐.

**해결**: bench-orchestration 등 대형·일회성 작업을 `context: fork`로 전환 → 격리
서브에이전트로 돌리고 결론만 회수, 메인 컨텍스트 오염 방지.

---

# Part D. 권장 롤아웃 순서

| 순서 | 제안 | 이유 |
|------|------|------|
| 1 | **제안 2 (git-guard)** | 가장 안전·독립적, 즉시 가치. 자율 모드의 전제. |
| 2 | **제안 1 (Stop 훅)** | 자율성의 본체. ⑥ 수렴 가드 반드시 동봉. |
| 3 | **제안 3 (SessionStart)** | 작고 효과 큼. |
| 4 | 제안 4 (학습 루프) → 5 (병렬화) → 6, 7 | 점진 적용. |

제안 1~3은 `hooks/hooks.json` 항목 추가 + 파이썬 훅 1개씩이라 기존 아키텍처 무수정 증분 적용.

---

# 부록. 핵심 파일 맵 (빠른 참조)

| 대상 | 경로 |
|------|------|
| 코어 루프 원리(원문) | `references/claude-code-reference/docs/agent-architecture-and-plugin-guide.md` |
| 미출시 기능(원문) | `references/claude-code-reference/docs/claude-code-unreleased-features.md` |
| 플러그인 훅 등록 | `coding-agent/plugin/hooks/hooks.json` |
| 기존 훅 패턴(재사용) | `hooks/on-commit.sh`(Bash payload 파싱), `hooks/doc-guard.py`(JSON additionalContext) |
| 상태머신/전이 게이트 | `coding-agent/plugin/skills/state-machine/SKILL.md` |
| 오케스트레이션 루프 | `coding-agent/plugin/agents/orchestrator.md` |
| autonomy 설정 위치 | state.json `config.autonomy.{mode, on_blocked, auto_merge}` |

---

*문서 끝 — 구현은 본 문서 합의 후 별도 진행.*
