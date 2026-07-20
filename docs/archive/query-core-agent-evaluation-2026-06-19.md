# Claude Code 코어 루프(`query.ts`) 냉정 평가 — agent 관점 (2026-06-19)

문서 성격: **평가/리뷰 (status, 미구현 제안)**. agent·AI 시스템 관점의 비판적 코드 리뷰.
대상: Claude Code 소스맵 복원본 코어 — `src/query.ts`(1730줄), `src/query/stopHooks.ts`(473줄),
`src/query/tokenBudget.ts`, `src/query/deps.ts`.
원문 위치: `Work/github/references/claude-code-reference/src/`.

---

## 한 줄 결론

> 이 루프는 **메커니즘으로서 A급, 에이전트로서 C급**이다.
> 에러 복구·캐싱·스트리밍·압축 순서 같은 *기계적 견고함*은 업계 상위지만,
> **자기 진행(progress)에 대한 내적 모델이 0**이라 — 정체 감지·목표 추적·자기검증·
> 통합 안전예산이 전부 *옵션 기능*이나 *외부 훅*으로 떠넘겨져 있다.

가장 높은 레버리지 개선 2가지: **#1 제어정책을 순수 reducer로 분리**, **#2 통합 continuation budget**.
이 둘만으로 코드에 박제된 무한루프 버그 부류가 구조적으로 사라지고, 자율 실행의 안전이
"사용자가 maxTurns를 켰는가"에 의존하지 않게 된다.

---

## 0. 먼저 — 이 코드의 성격 규정

`query.ts`는 **메커니즘(mechanism) 레이어**다: 모델 호출 · 스트리밍 · 압축 · 도구 실행 · 에러 복구.
**지능(policy)** — 목표 추적, 자기검증, 정체 판단 — 은 거의 전부 모델 · 시스템프롬프트 · 훅으로
외주화돼 있다.

그래서 냉정한 사실 하나:

> 종료 판정은 **단 하나의 신호**다 — *"이번 응답에 tool_use 블록이 있었나?"*
> 그 외 모든 고차원 행위성은 옵션 기능(`TOKEN_BUDGET`)이나 외부 Stop 훅으로만 존재한다.

이게 의도된 설계임은 인정한다. 하지만 "agent 관점 개선"이라는 질문에는 **바로 이 지점이 핵심 한계**다.

---

## 1. 평가 요약표

| # | 약점 | 심각도 | 증거 (코드) |
|---|------|--------|-------------|
| 1 | God-function + 7개 continue 사이트 수동 상태 재구성 | 🔴 높음 | `query.ts:1292` (무한루프 버그 주석) |
| 2 | 자기-반복 경로 5개, 통합 안전예산 없음 | 🔴 높음 | `maxTurns` 옵션, `feature('TOKEN_BUDGET')` 게이트 |
| 3 | 종료가 이진(tool_use 유무), 진행/정체 모델 없음 | 🔴 높음 | `tokenBudget.ts` `isDiminishing`만 존재(옵션) |
| 4 | 네이티브 자기검증(reflection) 루프 없음 | 🟠 중간 | Stop 훅으로만 가능(외부 스크립트 필요) |
| 5 | 압축이 위치 기반이지 관련성 기반 아님 | 🟠 중간 | snip=오래된 것부터, microcompact=tool_use_id |
| 6 | 무제한 fire-and-forget 백그라운드 작업 | 🟡 낮음 | `stopHooks.ts:139–156`, `query.ts:1001` |
| 7 | 복구 사다리가 고정 상수(세션 내 적응 없음) | 🟡 낮음 | `MAX_OUTPUT_TOKENS_RECOVERY_LIMIT=3` |
| 8 | 메커니즘 중복(abort 2곳, cleanup 3곳 복붙) | 🟡 낮음 | `query.ts:1015 / 1485` |

---

## 2. 구조적 약점 (높은 레버리지순)

### 🔴 #1. God-function + 7개 continue 사이트의 수동 상태 재구성

**무엇이 문제인가**
- 루프는 ~1500줄 단일 함수. 11개 필드짜리 `State`를 **7개 continue 지점에서 매번 객체 리터럴로
  통째 재작성**한다:
  `collapse_drain` · `reactive_compact` · `max_output_escalate` · `max_output_recovery` ·
  `stop_hook_blocking` · `token_budget` · `next_turn`.
- 필드 하나만 잘못 전파해도 즉시 폭주한다.

**증거 — 코드에 박제된 실제 사고** (`query.ts:1292`):

> *"Resetting to false here caused an infinite loop: compact → still too long → error →
> stop hook blocking → compact → … burning thousands of API calls."*

`hasAttemptedReactiveCompact`를 한 사이트에서 잘못 리셋했다가 **수천 번의 API 호출을 태운
무한루프**가 실제로 발생했다. 수동 상태 재구성 패턴이 fragile하다는 증거.

**개선 방향**
- 루프의 *제어 정책*("다시 돌까, 왜?")을 I/O 제너레이터에서 분리한
  **순수 reducer `(state, event) => nextState`** 로 모델링.
- 효과: 복구 경로 간 상호작용을 단위 테스트로 격리 가능 → 위 무한루프류 버그가
  *구조적으로 불가능*해진다.
- `deps.ts`의 DI가 이미 그 방향이나, 스스로 *"패턴 증명용 4개로 좁혔다"* 며 멈춰 있다.

---

### 🔴 #2. 자기-반복 경로가 5개인데 통합 "continuation budget"이 없다

**무엇이 문제인가**
- 루프가 스스로 한 턴 더 도는 경로 5가지:
  ① Stop 훅 block ② token-budget nudge ③ 413 복구 ④ max_output 복구 ⑤ 모델 fallback.
- 각각 **제각각의 임시 가드**로 막혀 있다: `hasAttemptedReactiveCompact`, `stopHookActive`,
  `MAX_OUTPUT_TOKENS_RECOVERY_LIMIT=3` …
- death spiral 방지 주석이 코드 곳곳에 흩어져 있음 = **나선을 프로덕션에서 하나씩 얻어맞고
  개별 패치**했다는 신호.

**가장 큰 위험**
> 무한루프의 최종 방어선이 `maxTurns`인데 **이건 옵션**이다 (`if (maxTurns && ...)`).
> 설정 안 하면 token-budget(이것도 opt-in)만이 자율 실행을 멈출 수 있다.
> 즉 **자율 에이전트의 안전이 "사용자가 maxTurns를 켰는가"에 달려 있다.**

**개선 방향**
- 모든 자기-continuation을 한 곳에서 카운트하는 **턴당 통합 continuation budget**(사유별 분류 포함).
- boolean 가드 5개보다 견고하고, `transition` 필드에 노출하면 관측성도 공짜.

---

### 🔴 #3. 종료가 이진(tool_use 유무)일 뿐, 진행/정체 모델이 없다

**무엇이 문제인가**
- 규칙은 "도구를 또 부르면 무조건 한 턴 더". **오실레이션 감지가 없다** —
  A→B→A→B 무한 반복도 maxTurns/token-budget(둘 다 옵션)이 없으면 안 멈춘다.
- 정체에 가장 근접한 로직은 `tokenBudget.ts`의 `isDiminishing`인데:
  - TOKEN_BUDGET 기능 뒤에 갇혀 있고(옵션),
  - 판정이 거칠다 — 델타 < 500토큰 × 2회 연속 → "수렴"으로 판정.
  - **신중하게 적은 토큰으로 추론하는 모델**을 "정체"로 오판할 수 있다.

**개선 방향**
- 기본 경로에 경량 정체 신호: 동일 tool_use(이름+입력 해시) 반복, 새 정보 없는 도구결과 반복을
  감지 → break 하거나 reflection nudge 주입.
- "에이전트가 헛도는" 문제는 현재 base case에서 *전혀 다뤄지지 않는다*.

---

### 🟠 #4. 네이티브 자기검증(reflection) 루프가 없다

**무엇이 문제인가**
- 완료 선언 전에 *"정말 목표를 달성했나"*를 모델에게 묻는 단계가 코어에 없다.
- Stop 훅이 메우지만 **사용자가 셸 스크립트를 직접 짜야** 한다.

**결정적 증거**
> 우리가 분석한 `coding-agent` 플러그인은 이 "검증 후 종료"를
> Evaluator 에이전트 + state-machine으로 **통째로 재구현**했다.
> → 코어가 제공했어야 할 일반 기능을 *모두가 각자 다시 만든다*.

**개선 방향**
- 플래그로 켜는 네이티브 "verify-then-finish" 패스(미충족 기준을 모델이 스스로 열거).
- 모든 사용자가 Stop 훅을 작성하는 것보다 싸고 일반적.

---

### 🟠 #5. 압축이 "위치 기반"이지 "관련성 기반"이 아니다

**무엇이 문제인가**
- 5단계 파이프라인(budget→snip→microcompact→collapse→autocompact)을 싼 것부터 도는 *순서*
  설계는 **훌륭하다**(앞이 줄이면 뒤는 no-op → 세밀함 보존).
- 그러나 *무엇을 버릴지*의 선택은 위치 기반:
  - snip = 오래된 것부터, microcompact = tool_use_id 기준.
- **가장 오래된 도구 결과 = 가장 덜 중요한 결과가 아니다.** 현재 목표에 load-bearing인 결과를
  버리고 최근 노이즈를 남길 수 있다. "이 결과는 핀(pin)해라" 보호 장치가 없다.

**개선 방향**
- 관련성/attention 가중 eviction, 또는 도구가 결과를 pinnable로 마킹.
- 최소한 현재 plan/goal을 보호 영역에 고정.
- (CONTEXT_COLLAPSE·SessionMemory가 부분 대응하나 임계값 기반 *요약*이지 관련성 *고정*이 아님.)

---

## 3. 부차적이지만 실재하는 문제

- **🟡 #6 무제한 fire-and-forget 백그라운드 작업.**
  auto-dream / extract-memories / prompt-suggestion / tool-use-summary / task-summary /
  post-sampling 훅이 전부 `void`로 발사(`stopHooks.ts:139–156`, `query.ts:1001`).
  긴 자율/headless 실행에서 rate limit·토큰을 두고 **메인 루프와 경쟁**. 전역 동시성·토큰
  거버너가 루프에 없음 — 특히 TOKEN_BUDGET 하에서 모순.

- **🟡 #7 복구 사다리가 고정 상수.**
  single-shot collapse→reactive, 8k→64k 1회 에스컬레이션, 3회 재시도. 세션 내 적응 없음
  (64k가 계속 깨져도 매번 재유도).

- **🟡 #8 메커니즘 중복.**
  abort 처리 블록이 거의 동일하게 두 곳(스트리밍 후 `:1015` · 도구 후 `:1485`),
  chicago cleanup 3번 복붙. 유지보수 리스크.

---

## 4. 공정하게 — 진짜 잘한 것

평균 이상인 부분(칭찬할 건 칭찬):

- **복구 가능 에러를 복구 가능성 확정 전까지 withhold** — SDK 소비자에게 중간 에러 누출 방지.
  대부분의 에이전트 프레임워크가 못 하는 디테일.
- **스트리밍 중 도구 즉시 착수**(`StreamingToolExecutor`) — 레이턴시 설계 일류.
- **`transition` 필드**로 "왜 계속됐는가"를 관측 가능하게 함(다만 #2처럼 정책 자체엔 미사용).
- 50KB 초과 도구결과 디스크 오프로드, prompt cache byte-mismatch 회피(원본 불변 유지)
  — 토큰/캐시 인지도가 높다.

---

## 5. 권장 우선순위

| 순위 | 항목 | 이유 |
|------|------|------|
| 1 | **#1 제어정책 → 순수 reducer 분리** | 무한루프 버그류를 구조적으로 제거. 최고 레버리지. |
| 2 | **#2 통합 continuation budget** | 자율 안전이 maxTurns 설정에 의존하지 않게 함. |
| 3 | **#3 정체 감지(기본 경로)** | "헛도는 에이전트" 문제 직접 해결. |
| 4 | #4 네이티브 reflection → #5 관련성 압축 → #6 백그라운드 거버너 | 점진 개선. |

> #1과 #2는 함께 가야 한다: 제어정책을 reducer로 분리하면서 continuation budget을
> 그 reducer의 1급 입력으로 넣으면, 두 개선이 하나의 리팩터링으로 수렴한다.

---

## 부록. 코어 파일 빠른 참조

| 대상 | 경로 · 핵심 위치 |
|------|------------------|
| 메인 루프 | `src/query.ts` (`while(true)` :307) |
| State 정의 | `src/query.ts:204` |
| 7개 continue 사이트 | `:1114 :1164 :1219 :1250 :1304 :1340 :1727` |
| 무한루프 버그 주석 | `:1292` |
| Stop 훅 처리 | `src/query/stopHooks.ts` (`handleStopHooks`) |
| 토큰 예산 정책 | `src/query/tokenBudget.ts` (`checkTokenBudget`, `isDiminishing`) |
| DI 경계(4개) | `src/query/deps.ts` |

---

*문서 끝 — 구현/리팩터링은 본 평가 합의 후 별도 진행.*
