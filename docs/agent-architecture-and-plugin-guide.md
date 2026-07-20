# Claude Code 에이전트 동작 원리와 플러그인 작성 가이드

> **무엇**: 소스코드 기준으로 "claude 에이전트가 어떤 원리로 동작하는가"를 단계별로 밝히고, 그 원리에 따라 **플러그인으로 에이전트형 기능을 추가할 때 반드시 채워야 하는 요소**를 정리한 문서.
> **대상 코드**: `src/query.ts`, `src/tools/AgentTool/`, `src/plugins/`, `src/skills/`, `src/utils/hooks.ts` 외
> **분석일**: 2026-06-17

---

## 이 문서를 읽는 법

깊이를 3단계로 쌓았습니다. 필요한 만큼만 내려가세요.

| 깊이 | 읽을 곳 | 걸리는 시간 |
|---|---|---|
| **결론만** | 30초 요약 | 30초 |
| **흐름 이해** | Part 1~2 (지도 + 큰 그림) | 5분 |
| **원리 정독** | Part 3 (루프·도구·서브에이전트) | 15분 |
| **직접 제작** | Part 4 (플러그인 실전 + 예제) | 20분 |
| **사실 확인** | 부록 A (파일 맵) | 수시 |

---

## 30초 요약 (결론 먼저)

1. **엔진은 단 하나의 함수다.** 모든 대화는 `src/query.ts`의 `query()` — 비동기 제너레이터 무한 루프 — 가 처리한다. 별도의 "에이전트 객체"는 없다.

2. **에이전틱의 본질은 한 줄이다.** 모델이 **도구를 호출하면 루프를 한 번 더 돌고, 호출하지 않으면 끝난다.** 이 "다음 턴" 재귀가 자율 행동의 전부다.

3. **루프는 토큰 관리를 매 턴 먼저 한다.** 5종 압축(snip → microcompact → collapse → autocompact + reactive)이 매 iteration 맨 앞에서 돌아 긴 세션에서도 한도를 넘지 않는다.

4. **서브에이전트도 같은 루프다.** `AgentTool`이 자식을 만들지만, 자식 역시 *제한된 도구 + 전용 시스템 프롬프트*로 같은 `query()`를 재귀 실행하고 **결론만** 부모에게 돌려준다.

5. **플러그인은 루프를 대체할 수 없다.** 루프는 바이너리 안에 있다. 플러그인은 루프의 **정해진 5개 지점**(에이전트 정의·도구·컨텍스트 주입·훅·서브에이전트 위임)을 채울 뿐이다. "에이전트처럼 만들기" = **이 5개 지점을 올바르게 채우는 일.**

---

# Part 1. 분석 범위

소스맵으로 복원된 Claude Code 내부 TypeScript(~1,900 파일)에서 **에이전트 실행 경로**에 집중했다.

- 핵심 루프: `src/query.ts` (1,729줄) — 전체 정독
- 모델 호출 계층: `src/QueryEngine.ts`, `src/query/deps.ts`, `src/services/api/claude.ts`
- 서브에이전트: `src/tools/AgentTool/`, `src/tasks/`
- 도구 계약·실행: `src/Tool.ts`, `src/tools.ts`, `src/services/tools/toolExecution.ts`
- 확장 시스템: `src/plugins/`, `src/skills/`, `src/utils/hooks.ts`

---

# Part 2. 큰 그림 — 4계층 아키텍처

> **목적**: 코드를 보기 전에 "어디에 무엇이 있는지" 지도를 먼저 갖는다.

```
┌─ 진입 / UI ────────────────────────────────────────────┐
│  main.tsx → React/Ink REPL                             │
│  (entrypoints, screens, components)                    │
├─ Core 엔진 ────────────────────────────────────────────┤
│  query.ts        ← 에이전트 루프 (이 문서의 심장)        │
│  QueryEngine.ts  ← 세션·메시지 오케스트레이션            │
│  Tool.ts         ← 도구 계약 + 권한 컨텍스트             │
├─ 확장 ─────────────────────────────────────────────────┤
│  tools/ · commands/ · services/ · hooks/               │
│  AgentTool/(서브에이전트) · coordinator/(멀티에이전트)   │
├─ 플랫폼 ───────────────────────────────────────────────┤
│  plugins/ · skills/ · bridge/(IDE) · context.ts        │
└────────────────────────────────────────────────────────┘
```

**이 그림에서 기억할 3가지**

- 실행 엔진은 **함수 하나**(`query()`)다. 거대한 객체 그래프가 아니라 제너레이터 루프 한 개라는 점이 이 시스템 전체를 이해하는 열쇠다.
- 모델 호출은 **의존성 주입(DI)** 으로 분리돼 있다. `query()`는 `deps.callModel`을 부를 뿐이고, 프로덕션에서는 그게 `queryModelWithStreaming`으로 바인딩된다(`src/query/deps.ts`). 덕분에 테스트에서 모델을 가짜로 갈아끼울 수 있다.
- 도구는 **선언적 계약**이다. `buildTool()`이 빠진 필드를 안전한 디폴트로 채운다(읽기전용 아님·병렬 불가·권한 필요로 가정 = fail-closed, `src/Tool.ts:757`).

---

# Part 3. 에이전트는 어떻게 동작하는가

## 3.1 핵심 한 문장

> 에이전트 = **「모델에게 묻고 → 도구를 실행하고 → 결과를 다시 모델에게 먹이는」 루프**를, 모델이 더 이상 도구를 부르지 않을 때까지 반복하는 것.

나머지 Part 3는 이 한 문장을 코드 수준으로 풀어낸다.

## 3.2 루프가 들고 다니는 상태 (State)

`query()`는 `while(true)` 한 개로 돌면서, iteration 사이에 `State` 객체 하나를 갱신한다(`query.ts:204`). 어떤 값을 들고 다니는지 알면 루프의 모든 분기가 이해된다.

| State 필드 | 의미 |
|---|---|
| `messages` | 지금까지의 전체 대화(다음 모델 호출의 입력) |
| `toolUseContext` | 도구·권한·앱 상태에 접근하는 컨텍스트 객체 |
| `autoCompactTracking` | 압축이 일어났는지/연속 실패 횟수 |
| `maxOutputTokensRecoveryCount` | 출력 토큰 초과 복구 시도 횟수 |
| `hasAttemptedReactiveCompact` | 413 복구용 reactive compact를 이미 썼는지(무한루프 방지) |
| `turnCount` | 현재 턴 수(`maxTurns` 비교용) |
| `transition` | **직전 iteration이 왜 계속됐는지**(복구/다음턴/예산 등). 디버깅·테스트의 단서 |

> 💡 포인트: 종료·복구·재시도가 전부 "다음 `State`를 만들어 `continue`"로 표현된다. 그래서 코드에 `state = next; continue`가 반복적으로 나온다.

## 3.3 한 턴의 흐름 (단계별)

`while(true)` 한 바퀴 = **모델 1회 호출 + 그 도구 실행**. 각 단계가 *무엇을·왜* 하는지:

```
0. 턴 준비
   • 메모리/스킬 prefetch 시작 (비차단)         query.ts:301, :331
   • queryTracking(chainId/depth) 증가          :347
     → 부모-자식 쿼리 체인을 분석에서 추적하기 위함

1. 컨텍스트 압축 파이프라인 (순서가 의도된 설계)
   applyToolResultBudget → snip → microcompact → collapse → autocompact
                                    :379 / :403 / :414 / :441 / :454
   → 앞 단계가 토큰을 줄이면 뒤 단계가 no-op이 되어
     "요약 한 덩어리" 대신 "세밀한 컨텍스트"를 최대한 보존한다

2. 시스템 프롬프트 확정
   appendSystemContext(systemPrompt, systemContext)  :449

3. 하드 토큰 한계 검사
   초과 + 자동압축 꺼짐 → PROMPT_TOO_LONG 반환        :637

4. 모델 호출 (스트리밍)
   deps.callModel({ messages, systemPrompt, tools,
                    thinkingConfig, model, agents,
                    taskBudget, signal ... })          :659
   • tool_use 블록이 오면 needsFollowUp = true         :832
   • StreamingToolExecutor: 스트리밍 도중 도구를 즉시 착수(병렬)  :841
   • 모델 폴백(FallbackTriggeredError) → 모델 교체 후 전체 재시도  :894

5. post-sampling 훅 실행 (비차단)                       :1001

6. 분기
   ├─ abort 됐나? → 미완 도구를 합성 결과로 메우고 종료   :1015
   ├─ 도구 없음(needsFollowUp=false) → [종료 경로] 3.4   :1062
   └─ 도구 있음 → [계속 경로] 3.5                         :1366
```

**컨텍스트 압축 5종을 한 줄씩** (왜 5개나 되는가: 비용·세밀함이 다르기 때문):

| 단계 | 하는 일 | 특징 |
|---|---|---|
| `applyToolResultBudget` | 누적 도구 결과 크기에 예산 적용 | 가장 싸다, 내용만 치환 |
| **snip** | 오래된 대화 토막 잘라내기 | `HISTORY_SNIP` 게이트 |
| **microcompact** | 도구 결과를 `tool_use_id` 기준으로 제거 | 캐시 친화적 |
| **collapse** | 세밀 컨텍스트를 접어 투영 | `CONTEXT_COLLAPSE` |
| **autocompact** | 대화 전체를 요약으로 대체 | 가장 비싸고 거칠다, 최후수단 |

## 3.4 루프는 언제 끝나는가 (가장 중요한 포인트)

```
   모델 응답에 tool_use 블록이 있는가?
          │
    ┌─────┴─────┐
   있음         없음
    │            │
 도구 실행    (복구 검사: 413 / max_output_tokens 회복 가능?)
    │            │
 다음 턴       Stop 훅 검사 ──block──▶ 사유를 컨텍스트에 주입하고 루프 계속
              │
            통과 → Token budget 판단 → return { reason:'completed' }
```

**이 한 장이 에이전트의 자율성을 결정한다.** 세 가지 메커니즘이 겹쳐 있다.

1. **자연 종료 = "도구를 부르지 않은 응답"** (`needsFollowUp == false`, `query.ts:1062`). 반대로 도구를 부르면 **무조건 한 턴 더** 돈다. 이것이 "스스로 일을 이어가는" 행동의 정체다.

2. **복구 경로**(종료 직전): 모델 호출이 토큰 한계로 깨졌다면 코어가 먼저 회복을 시도한다.
   - *프롬프트 초과(413)*: collapse 드레인 → reactive compact 순으로 단발 시도 후 재시도(`query.ts:1085~`).
   - *출력 토큰 초과*: 8k→64k로 한도를 올려 같은 요청 재시도, 그래도 안 되면 "이어서 작성" 메타 메시지를 넣고 최대 3회 재시도(`query.ts:1188~`).
   - `hasAttemptedReactiveCompact` 같은 가드로 **death spiral(에러→압축→에러…)을 차단**한다.

3. **Stop 훅 + Token budget**(마지막 재정의): 도구가 없어 끝나려는 순간, Stop 훅이 `block`을 반환하면 코어가 그 사유를 컨텍스트에 주입하고 **루프를 다시 돌린다**(`query.ts:1267~1306`). `+500k` 같은 Token budget이 켜져 있으면 예산이 남는 한 nudge 메시지로 계속시킨다(`query.ts:1308`). → **자가 검증·자가 반복**의 구현 지점.

무한루프는 `maxTurns`, Token budget, `stopHookActive` 플래그가 함께 막는다.

## 3.5 도구를 실행하는 한 턴 (계속 경로)

도구가 있으면 코어는 도구를 실행하고 결과를 붙여 다음 턴을 만든다(`query.ts:1366~1727`).

```
도구 실행 (StreamingToolExecutor 또는 runTools)        :1380
  → 각 도구 결과를 tool_result 메시지로 수집
tool-use 요약 생성 (Haiku, 비차단 — 모바일 UI용)        :1469
첨부 주입:
  • 큐에 쌓인 명령 (task-notification 등)               :1570
  • 메모리 prefetch 결과 (이미 settled면)               :1599
  • 스킬 discovery prefetch 결과                         :1620
  • 파일 변경 알림                                       :1646
도구 새로고침 (신규 MCP 서버 반영)                       :1660
maxTurns 검사                                            :1705
다음 State = [이전 + assistant 응답 + toolResults], turn++ → continue  :1715
```

핵심: **다음 턴의 입력은 "이전 전체 + 이번 모델 응답 + 이번 도구 결과"**다. 이렇게 누적된 컨텍스트가 다시 3.3의 0단계(압축)로 들어간다.

## 3.6 도구 한 건의 생애

도구 실행(3.5의 첫 줄) 내부는 항상 같은 7단계 파이프라인을 탄다(`services/tools/toolExecution.ts`). 권한과 훅이 어디서 개입하는지가 핵심이다.

```
1. 입력 Zod 검증         tool.inputSchema.safeParse
2. 도구별 추가 검증       tool.validateInput
3. PreToolUse 훅          입력 변형(updatedInput) / allow·deny·ask 결정 가능
4. 권한 판정             canUseTool: 모드 + allow/deny/ask 규칙 + (auto면)bash 분류기
5. tool.call() 실행       실제 동작 + 진행상황 콜백
6. PostToolUse 훅         출력 검증·변형(updatedMCPToolOutput)
7. 결과 → 메시지          mapToolResultToToolResultBlockParam
                         50KB 초과 시 디스크 저장 + 프리뷰만 API로
```

**권한 모드 7종** (`src/types/permissions.ts`):

| 모드 | 동작 |
|---|---|
| `default` | 사용자에게 물어봄 |
| `acceptEdits` | 파일 편집 자동 승인 |
| `bypassPermissions` | 전부 자동 승인 |
| `plan` | 읽기전용 도구만 허용 |
| `dontAsk` | 전부 자동 거부 |
| `auto` | bash 분류기로 판단(게이트) |
| `bubble` | 내부 전용 |

> 결과가 50KB를 넘으면 디스크에 저장하고 API엔 프리뷰(앞 2000바이트)+경로만 보낸다. 모델이 더 보려면 Read 도구로 꺼낸다 → 컨텍스트 폭증 방지.

## 3.7 서브에이전트 — 일을 위임할 때

`AgentTool.call()` (`src/tools/AgentTool/AgentTool.tsx:239`)이 자식 에이전트를 만든다. 입력: `prompt, subagent_type, description, model?, run_in_background?, isolation?('worktree'|'remote'), cwd?`.

**스폰 분기**

| 조건 | 동작 |
|---|---|
| `teamName + name` | 팀 협업(InProcessTeammate) |
| `isolation: 'remote'` | CCR 원격 세션(ant 전용) |
| `subagent_type` 없음 + FORK 켜짐 | 부모 시스템프롬프트/도구 상속(프롬프트 캐시 히트) |
| 그 외 | 일반 스폰 |

**일반 스폰 시퀀스**

1. `subagent_type`으로 에이전트 정의 조회 → 전용 시스템 프롬프트 확보 (`loadAgentsDir.ts`). MCP 요구사항·deny 규칙으로 후보를 거른다.
2. 워커 도구풀 구성 — **위험 도구 자동 제거**:
   - 모든 서브에이전트 금지: 재귀 `AgentTool`, `AskUserQuestion`, `ExitPlanMode`, `TaskStop`, `Workflow` 등 (`src/constants/tools.ts`).
   - 비동기 에이전트는 **화이트리스트만**: Read/Edit/Write/Grep/Glob/Bash/WebSearch/WebFetch/Skill/Todo/MCP…
3. `isolation: 'worktree'`면 별도 git worktree(`agent-<id8>`) 생성 — 파일 충돌 방지.
4. 동기/비동기 결정: `run_in_background || definition.background || coordinator || proactive` → 비동기면 즉시 반환 + 진행상황 SDK 이벤트(`task_progress`, `task_terminated`), 동기면 부모 턴이 블로킹 소비.
5. 결과는 `AgentToolResult`(텍스트 content + `totalTokens` + `totalToolUseCount` + `usage`)로 **결론만** 회수.

> **핵심**: 서브에이전트 = *제한된 도구풀 + 전용 시스템 프롬프트 + 독립 AbortController*로 도는 **또 하나의 `query()` 루프**. 부모는 파일 덤프가 아니라 자식의 요약 결론을 받는다.

**에이전트 정의 레지스트리** (`loadAgentsDir.ts`):

| 출처 | 위치 |
|---|---|
| 내장 | `general-purpose`(=`claude`), `Explore`, `Plan`, `Fork`, `Verification`… |
| user/project | `.claude/agents/*.md` |
| 플러그인 | 플러그인의 `agents/` |

각 정의 = **마크다운 프론트매터(name, description, tools, disallowedTools, model, permissionMode, requiredMcpServers, skills) + 본문(=시스템 프롬프트)**.

---

# Part 4. 플러그인으로 에이전트 만들기 (실전)

> **목적**: Part 3의 원리를 그대로 플러그인 작성 규칙으로 번역한다.

## 4.1 먼저 알아야 할 제약 — 무엇을 할 수 없는가

플러그인은 **`query()` 루프를 대체할 수 없다.** 루프는 바이너리 안에 있다. 즉 "나만의 에이전트 루프를 코드로 짜 넣는" 것은 불가능하다. 대신 플러그인은 루프의 **이미 뚫려 있는 확장 지점**을 채운다. 다행히 그 지점들이 Part 3에서 본 에이전틱 요소와 정확히 1:1로 대응한다.

## 4.2 플러그인이 기여할 수 있는 아티팩트

`plugin.json` manifest로 등록한다(`src/plugins/`, `src/utils/plugins/schemas.ts`).

| 아티팩트 | 위치 | 루프에서의 역할 | 대응 원리 |
|---|---|---|---|
| **agents** | `agents/*.md` | 시스템 프롬프트 + 도구 스코프 + 모델 | 정체성(3.7) |
| **skills** | `skills/<name>/SKILL.md` | 호출형 능력. `context:fork`면 서브에이전트 실행 | 위임(3.7) |
| **hooks** | `hooks/hooks.json` | 컨텍스트 주입·도구 게이트·계속/종료 | 제어(3.4, 3.6) |
| **mcpServers** | manifest | 외부 도구 추가 | 능력(3.6) |
| **commands** | `commands/*.md` | 슬래시 커맨드 진입점 | 진입 |
| (그 외) | output-styles, lsp | 출력 스타일·언어서버 | 부가 |

## 4.3 반드시 채워야 하는 에이전틱 시퀀스 (6단계)

### ① 정체성 — 에이전트 정의 (필수)

`agents/my-agent.md`:

```yaml
---
name: my-agent
description: 언제 이 에이전트를 부르는지 (모델/사용자 라우팅의 판단 근거)
tools: [Read, Grep, Glob, Bash]   # 최소권한 원칙. '*'(전체)는 신중히
disallowedTools: [Write]          # 명시적 차단
model: sonnet                     # 또는 inherit
permissionMode: plan              # 예: 읽기전용 강제
requiredMcpServers: [my-server]   # 이 서버 없으면 이 에이전트 비활성
---
본문 = 시스템 프롬프트.
- 목표와 산출물 형식
- **완료 기준** (언제 끝났다고 판단하는가)
- 행동 규칙 / 금지사항
```

> ⚠️ **완료 기준을 본문에 반드시 명시.** 루프는 "도구를 안 부른 응답"으로만 끝난다(3.4). 모델이 임무 완수를 스스로 인지해야 자연 종료된다. 이게 빠지면 에이전트가 멈추지 못하거나 너무 빨리 멈춘다.

### ② 능력 — 도구 + 권한 경계 (필수)

행동하려면 도구가 있어야 한다. 두 가지 경로:
- **새 능력 추가**: `mcpServers`로 MCP 서버를 붙이면 그 도구들이 풀에 들어온다.
- **기존 도구 스코프**: 에이전트 정의의 `tools`/`disallowedTools`/`permissionMode`로 범위를 좁힌다.

**능력과 경계는 항상 함께 정의한다.** 코어가 서브에이전트에 자동 적용하는 안전장치(재귀 AgentTool 금지 등, 3.7)를 전제로, 최소권한을 설계하라.

### ③ 정보 — 컨텍스트 주입 (필수)

플러그인 고유의 도메인 지식은 훅으로 루프에 넣는다. `SessionStart` 또는 `UserPromptSubmit` 훅이 JSON으로:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "이 프로젝트의 배포 규칙: ...",
    "initialUserMessage": "(선택) 첫 사용자 메시지 씨앗"
  }
}
```

CLAUDE.md·메모리는 코어가 매 쿼리에 자동으로 넣지만, 플러그인만 아는 지식은 이렇게 직접 주입해야 한다.

### ④ 제어 — 훅으로 가드레일과 자율 반복 (에이전트답게 하려면 사실상 필수)

| 훅 | 반환 필드 | 효과 |
|---|---|---|
| **PreToolUse** | `permissionDecision: allow/deny/ask`, `updatedInput` | 도구 실행 전 게이트·입력 교정 |
| **PostToolUse** | `updatedMCPToolOutput` | 결과 검증·후처리 |
| **Stop / SubagentStop** | `decision: 'block'`, `reason` | **자율 반복의 핵심** |

Stop 훅이 `block`을 반환하면 코어가 `reason`을 컨텍스트에 주입하고 **루프를 한 턴 더** 돌린다(3.4). 예: "테스트가 아직 통과 안 했으니 계속" → 에이전트가 스스로 다시 일한다. 여러 훅은 병렬 실행되고 결과는 **deny > ask > allow** 우선순위로 합쳐진다.

### ⑤ 위임 — 서브에이전트 분기 (스케일이 필요할 때)

긴/병렬 작업은 skill로 위임한다. `skills/<name>/SKILL.md`:

```yaml
---
name: deep-check
description: 무거운 검증을 격리된 서브에이전트로 수행
context: fork          # inline(기본)이면 대화에 펼침 / fork면 서브에이전트
agent: my-agent        # fork 시 어떤 에이전트로 돌릴지
allowed-tools: "Read,Grep,Bash"
model: sonnet
---
서브에이전트에게 줄 지시 프롬프트. $ARGUMENTS 로 인자 수신.
```

`context: fork`면 코어가 **격리된 서브에이전트 루프**를 돌리고 **결론만** 회수한다(3.7). 파일을 동시에 고치는 병렬 작업이면 worktree 격리 패턴을 따른다.

### ⑥ 안전 — 종료/예산 (필수)

자율 반복(④)을 켰다면 **멈출 조건**을 반드시 함께 둔다.
- 시스템 프롬프트에 명확한 완료 기준(①).
- Stop 훅의 `block`에 **수렴 조건**(예: "최대 N회까지만 재시도").
- 코어가 제공하는 `maxTurns`·Token budget 인지.

코어 자신도 `hasAttemptedReactiveCompact`·`stopHookActive` 가드로 무한루프를 막는다(3.4) — 같은 원리를 플러그인에도 적용하라.

## 4.4 한 장 요약 — 플러그인 에이전트의 사이클

```
[진입]  command 또는 (description 기반) 모델 자동 호출
   │
[정체성]  agent.md 시스템프롬프트 + 스코프된 도구풀 로드   ①
   │
   ▼  ── 코어 query() 루프 (플러그인이 채우는 지점) ──
   │   SessionStart 훅 → additionalContext 주입          ③
   │   모델 스트리밍 → tool_use
   │   PreToolUse 훅 → 도구 실행 (mcpServers의 도구 포함)   ②④
   │   PostToolUse 훅 → 결과 검증                          ④
   │   도구 없으면 → Stop 훅:                              ④⑥
   │        완료? → 종료
   │        미흡? → block + 사유 → 루프 계속(자가 반복)
   │   (대형 작업) context:fork skill → 서브에이전트 재귀   ⑤
   ▼
[종료]  도구 미호출 + Stop 훅 통과 / maxTurns / 예산 소진   ⑥
```

## 4.5 최소 예제 — 디렉토리 구조

```
my-agent-plugin/
├── plugin.json              # manifest: name, version, 기여물 선언
├── agents/
│   └── my-agent.md          # ① 정체성 (+ 완료 기준)
├── skills/
│   └── deep-check/
│       └── SKILL.md         # ⑤ context:fork 위임
├── hooks/
│   └── hooks.json           # ③ 컨텍스트 주입 + ④ 가드레일/자율반복
└── (mcpServers는 plugin.json 안에 선언) # ② 능력
```

## 4.6 놓치면 "에이전트가 아닌" 3가지

1. **종료 신호를 설계하라.** 루프는 "도구 없는 응답"으로만 끝난다. → 시스템 프롬프트에 완료 기준(①), Stop 훅에 검증/계속 로직(④).
2. **도구와 권한 경계를 함께 정의하라.** 능력 없이는 행동이 없고, 경계 없이는 안전이 없다(②).
3. **컨텍스트 주입과 위임을 갖춰라.** additionalContext(훅, ③)로 정보, context:fork(skill, ⑤)로 서브에이전트 위임.

---

# 부록 A. 핵심 파일 맵

| 역할 | 파일 (· 핵심 라인) |
|---|---|
| 에이전트 루프(심장) | `src/query.ts` |
| 루프 상태(State) 정의 | `src/query.ts:204` |
| 한 턴 흐름 | `src/query.ts:307`(루프) · `:659`(모델호출) · `:1366`(도구실행) |
| 종료/계속·복구·예산 | `src/query.ts:1062~1357` · `src/query/stopHooks.ts` |
| 모델 호출(DI) | `src/query/deps.ts` · `src/services/api/claude.ts` |
| 세션 오케스트레이션 | `src/QueryEngine.ts` (`submitMessage`, `ask`) |
| 도구 계약 + 디폴트 | `src/Tool.ts` (`buildTool`:757) |
| 도구 레지스트리/필터 | `src/tools.ts` |
| 도구 실행 7단계 | `src/services/tools/toolExecution.ts` |
| 서브에이전트 스폰 | `src/tools/AgentTool/AgentTool.tsx:239` |
| 에이전트 정의 로딩 | `src/tools/AgentTool/loadAgentsDir.ts` |
| 서브에이전트 도구 제한 | `src/constants/tools.ts` |
| 훅 시스템 | `src/utils/hooks.ts` · `src/types/hooks.ts` |
| 플러그인 manifest 스키마 | `src/utils/plugins/schemas.ts` |
| 스킬 로딩/프론트매터 | `src/skills/loadSkillsDir.ts` |
| 컨텍스트 조립 | `src/context.ts` · `src/utils/queryContext.ts` |

---

# 부록 B. 이 문서가 따른 포맷 원칙

읽기 쉽게 하려고 적용한 규칙 (다음 문서에도 재사용 가능):

- **결론 먼저** (Minto Pyramid / BLUF): 맨 위 「30초 요약」.
- **점진적 공개** (Progressive Disclosure): 30초 → 큰 그림 → 원리 → 실전. 각 깊이에서 멈출 수 있게 「읽는 법」 표로 안내.
- **유형 분리** (Diátaxis): "원리 설명"(Part 3)과 "실전 방법"(Part 4)을 섞지 않음.
- **스캔 가능성** (Google/Microsoft 개발자 문서 스타일): 짧은 문장, 한 섹션 한 주제, 제목·표만 훑어도 흐름 파악, 다이어그램은 분기·비교가 있을 때만.
