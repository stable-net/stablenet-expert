> ## ⚠️ STATUS (2026-06-29): 전부 SUPERSEDED — `reproduce-first` + `simulation-harness`로 구현 완료
>
> 이 문서(2026-06-19) 제안은 **전부 구현·머지됐다.** 코어(red→green 기계검증)는 `reproduce-first`
> 트랙으로(2026-06-22), **마지막 잔여였던 `simulation-harness` 스킬(L1/L2/L3 레벨 라우팅 + L3→L2
> down-push)은 PR #39(v0.1.39)로** 닫혔다. §1~§9는 *역사적 제안 원문*으로 보존한다
> (supersede-not-delete). 코드와의 1:1 대조:
>
> | 제안 항목(§5/§6) | 현재 코드 (2026-06-22) | 판정 |
> |---|---|---|
> | (1) `/diagnose` 실행 falsification | `commands/diagnose.md` §3 → `investigative-probe` 스킬(throwaway 관찰) + reproduce-first 오라클 | ✅ 충족 (이름은 `--repro`가 아니라 investigative-probe) |
> | (2) planner red→green 버그캡처 *요구* | `reproduce-first` 스킬: analyzer **§5 REPRODUCE**가 RED 테스트 작성 + `reproduction.json`; L1/L2/L3 레벨 선택은 `simulation-harness`(#39) | ✅ 충족 |
> | (3) implementer red-before-green | implementer **§3.4**(재현 테스트 FIRST 커밋=RED) + **§6.0**(GREEN 선확인) | ✅ 충족 |
> | (4) evaluator red→green 회귀게이트 (핵심 enabler) | evaluator **§4.7** Reproduction GREEN gate (HEAD green + repro_commit red 재확인 + 테스트파일 무수정) | ✅ 충족 — §7이 제안한 격리 red→green 기계검증 그대로 |
> | (5) 리포트/상태 연결 | `reproduction.json.{green_confirmed,green_at_head,red_at_parent}` evaluator 기록 | ✅ 충족 |
> | (신규) `simulation-harness` 스킬 (L1/L2/L3 라우팅 + L2 in-process 체인·합의 시뮬 레시피) | `skills/simulation-harness`(#39) — 도메인 중립 레벨 라우팅; L2 레시피는 도메인팩 `domains/go-stablenet/simulation.md` | ✅ **구현 (PR #39, v0.1.39)** |
> | ChainBench L2 down-push (무거운 L3 → 경량 L2 우선) | `simulation-harness` 비용 down-push(L3 전 팩의 충실한 L2 확인) — 단 **충실성 불변**(analyzer §5.0 약화 안 함, under-push) | ✅ **구현 (#39)** |
>
> **활성 잔여 0.** red→green 골격(reproduce-first)+레벨 라우팅(simulation-harness, #39) 모두 닫힘.
> 이 문서의 §0·§8 "범위 결정 대기" 서술은 더 이상 유효하지 않다. 추적: WORKLIST 스트림6 P4(완료).

# HANDOFF — 시뮬레이션 기반 "수정 검증/재현" 도입 (coding-agent plugin)

> 목적: 다른 머신/세션에서 이 문서만 읽고도 직전 작업 상태로 복귀해 곧바로 이어서
> 진행할 수 있게 한다. 아래 §0~§9를 순서대로 읽으면 된다.
> 작성 시점 기준 날짜: 2026-06-19. 작성자 세션 모델: Claude Opus 4.8 (1M).

---

## 0. 한 줄 요약 (지금 무엇을 하는 중인가)

`coding-agent` 플러그인 파이프라인(`planner → implementer → evaluator` + `/diagnose`)에
**"증상을 재현하는 경량 in-process 시뮬레이션 테스트"** 를 1급 시민으로 도입하려는 중이다.
이 테스트로 (a) 진단 단계에서 근본원인 가설을 *실행으로 falsify*하고, (b) 수정이 이슈를
실제로 고쳤는지 **red→green**으로 기계 검증한다. 설계 제안까지 합의됐고, **구현 착수
직전에 사용자가 "범위 선택" 질문을 중단(reject)** 시킨 상태다. → 다음 행동은 §8.

---

## 1. 이 작업의 출발 맥락 (어쩌다 여기까지 왔나)

세션은 3개의 사용자 요청으로 진행됐다:

1. **(완료) PR77 커밋 분석 + 유닛테스트 가이드 prompt 작성.**
   대상 커밋 `98f05c2a0c161ac67a1d50f254ca4847c8fac2a5`
   (제목: *"fix: refresh AnzeonTipEnv current block when GasTip changes (#77)"*).
   - 작업 레포: `/Users/wm-it-25_0220/Work/github/test/pr-77-origin` (go-stablenet, branch `dev`).
   - 산출: "수정 완료 시 통과해야 할 유닛테스트 핵심 명세" prompt (대화 본문에만 존재, 파일 저장 안 함).

2. **(완료) 위 가이드를 "작업 지시 prompt에 넣을 핵심만"으로 압축.** 대화 본문 참조.

3. **(진행 중 — 이 문서의 본체) 시뮬레이션 기반 검증/재현을 플러그인에 도입하는 설계.**
   계기: 사용자가 `consensus/wbft/backend/multiengine_test.go`를 보고
   "유닛테스트 레벨에서도 in-process로 체인/합의 시뮬레이션이 가능하다",
   "증상이 주어지면 그 현상을 재현하는 것도 시뮬 코드로 가능하지 않냐"고 제안.

---

## 2. 두 레포 / 위치 정보 (반드시 먼저 확인)

| 용도 | 경로 | git |
|------|------|-----|
| **플러그인(수정 대상)** | `/Users/wm-it-25_0220/Work/github/coding-agent/plugin` | 별도 repo |
| **go-stablenet(검증 예시/참조)** | `/Users/wm-it-25_0220/Work/github/test/pr-77-origin` | branch `dev`, HEAD `98f05c2a0` |

플러그인 구조(핵심만):
```
plugin/
  agents/      planner.md  implementer.md  evaluator.md  orchestrator.md  bench-*.md
  commands/    analyze.md  diagnose.md  work.md  review.md  merge.md  ...
  skills/      root-cause-lifecycle/  stablenet-context/  stablenet-invariants/
               state-machine/  template-parse/  pr-sanitize/  bench-orchestration/
  docs/        ← 이 문서가 여기 있음
```

---

## 3. PR77 — 재현 시뮬의 "워크드 예시"로 계속 쓰는 버그

플러그인 설계의 구체 예시로 PR77을 일관되게 사용한다(스킬 `root-cause-lifecycle/SKILL.md:44-51`도
이미 PR77을 예로 씀). 요약:

- **문제**: 거버넌스 투표로 GasTip이 변경된 직후의 **빈 블록(empty block)** 구간에서,
  비검증자(unauthorized) tx가 **stale GasTip**으로 검증되어 `EffectiveGasTip`이 minTip 미만이 됨.
- **원인**: `eth/gasprice/anzeon.go`의 `SetCurrentBlock`이 **state root 동일성만**으로 갱신 판단.
  빈 블록은 변경 블록과 root가 같지만 헤더 GasTip은 갱신값 → `currentBlock`이 stale 헤더에 고정.
- **수정**:
  - `eth/gasprice/anzeon.go`: 갱신 조건에 `gasTipChanged(currentBlock.GasTip(), header.GasTip())`
    OR 추가 + 헬퍼 `gasTipChanged` 신설(nil 처리 포함).
  - `core/txpool/legacypool/legacypool.go` `RemotesBelowTip`: 임계값 비교 시
    캐시된 `tx.GetAnzeonTipCap()` 우선, nil이면 `tx.GasTipCap()` 폴백.
- **재현 시뮬(L2) 시나리오**: genesis(validators) → 체인 전진 → gasTip 거버넌스 변경 블록 →
  빈 블록 여러 개 → 비검증자 tx의 `EffectiveGasTip`/`AnzeonTipEnv` 결과가 **새 gasTip 기준**인지 assert.
  **수정 전엔 fail(red), 수정 후 pass(green).** 증상 비대칭("인상 정상/인하 stuck")을 assert로 인코딩.

> PR77 유닛테스트 핵심 명세(요청 1·2의 산출)도 참고로 남김:
> - `SetCurrentBlock`: root 동일 + GasTip 변경 시 currentBlock 갱신되어야(핵심 회귀 케이스).
> - `gasTipChanged`: 양쪽 nil→false, 한쪽 nil→true, 같은 값(다른 포인터)→false, 다르면→true.
> - `RemotesBelowTip`: AnzeonTipCap < threshold면 GasTipCap이 임계값 이상이라도 드롭 대상.
> - 두 핵심 케이스는 *수정 전 코드에서 반드시 실패*해야 함(회귀 검출력).

---

## 4. 시뮬레이션 인프라 — 이미 존재하는 재사용 자산 (조사 완료)

`multiengine_test.go`가 증명하는 in-process 시뮬 빌딩블록 (모두 확인함):

- **`consensus/wbft/testutils/genesis.go`**: `Genesis`, `GenesisWithSeals`,
  `GenesisAndKeys(n)`, `GenesisAndFixedKeys(n)` → validator set + genesis 구성.
- **인메모리 체인**: `rawdb.NewMemoryDatabase()` + `genesis.MustCommit(...)` +
  `core.NewBlockChain(memDB, nil, genesis, nil, engine, vm.Config{}, nil, nil)`.
- **합의 엔진 시뮬**: `consensus/wbft/backend` `New(config, nodeKey, memDB)` +
  `multiengine_test.go`의 `testEnv` 패턴 — 다중 엔진, 라운드 진행(`GoNewRound`),
  `MustSucceed`, scenario 훅(`makeScenarioEngineDown` / `DisableCommitMsg` 등으로 down/지연 주입).
- **블록 시퀀스 생성**: `core.GenerateChain`(다른 코어 테스트에서 광범위 사용).
- **결정성 트릭**: `testEnv`는 goroutine/채널/타이머 기반 → flaky 위험.
  `config.AllowedFutureBlockTime` 크게, 채널 동기화(`newRoundReady`/`roundStartChan`), `BlockPeriod=1` 등.

→ 결론: **ChainBench(프로세스 레벨, L3) 없이도** 대부분의 도메인 버그를 L2 in-process로 재현 가능.
이게 이번 제안의 기술적 근거다.

---

## 5. 현재 파이프라인이 멈추는 지점 (gap 분석 — 파일·라인 근거)

각 단계가 "재현"을 직전까지 갔다가 안 한다:

| 단계 | 근거 위치 | 빠진 것 |
|------|----------|--------|
| `/diagnose` + `root-cause-lifecycle` | `commands/diagnose.md` §3 / `skills/root-cause-lifecycle/SKILL.md:42` ("어떤 *재현*이 확신을 올리나") | 가설을 **실행으로 falsify**하는 단계 없음 → 글로만 남음 |
| planner DESIGN | `agents/planner.md` §5.2 Tests(L486-489), §4.4 Verification Plan(L407-417), bugfix §6.4(L648-651) | "red→green 버그캡처 테스트" **요구사항** 및 시뮬 레벨 선택 없음 |
| implementer | `agents/implementer.md` §4.2 implement, §4.4 commit(테스트는 bucket 3) | "고치기 전 빨갛게 실패" 선확인 절차 없음 |
| evaluator | `agents/evaluator.md` §4.6 derived-state gate(L165-203) | 회귀 테스트가 **진짜 그 버그를 잡는지** 검증 안 함. `go test ./...` green = 통과 |
| evaluator ChainBench | `agents/evaluator.md` §7(L305-473) | 무겁고(20분 예산) generic(`basic/tx-send`). 특정 증상 시나리오 표현 못 함 |

핵심: **"증상을 재현하는 결정적·경량 시뮬"** 단 하나가 빠져 diagnose 확신도 / design 테스트 /
eval 회귀게이트를 동시에 막고 있다.

참고로 evaluator §4.6의 "파생상태 게이트"(파생상태엔 consistency-invariant + adversarial-path
테스트 강제)는 **이미 존재하는 좋은 형제 패턴**이다. 이번 제안은 그 철학을 회귀 테스트로 확장하는 것.

---

## 6. 합의된 제안 — 6개 지점 + 신규 스킬 1개

사용자에게 제시했고 방향 동의를 받은 설계. **아직 코드/파일 수정은 하나도 안 함.**

### (신규 스킬) `skills/simulation-harness/SKILL.md`
재현 시뮬을 매번 재발명하지 않도록 "빌딩블록 카탈로그 + 레벨 라우팅"을 1개 스킬로.
- **레벨 정의**: L1 순수단위(table test) / L2 in-process 체인·합의 시뮬(`testutils`+인메모리
  BlockChain+`testEnv`+`GenerateChain`) / L3 ChainBench(evaluator §7).
- **라우팅 규칙**: *증상을 표현할 수 있는 가장 낮은 레벨* 선택(PR77=L2, 헬퍼=L1).
- **도메인 레시피**: "거버넌스 값 변경→빈 블록", "validator N + 1 down", "tx 넣고 effective tip 읽기" 등.
- **결정성 가이드**: `multiengine_test`의 채널 동기화/`AllowedFutureBlockTime` 패턴, `-count=1`.
- planner/implementer/evaluator의 `skills:` frontmatter에 추가해 참조.

### (1) `/diagnose` — 실행 가능한 falsification (옵트인)
`commands/diagnose.md §3` 프롬프트에 `--repro` 플래그 추가. 켜지면 가설 후 **throwaway 재현
테스트**(`*_repro_test.go`, 워크스페이스/격리 worktree)를 작성·실행해 *현재(미수정) 코드에서 실패*
확인, 출력을 `diagnosis.md` Confidence 절에 첨부. **읽기전용 계약 유지**(커밋·브랜치 없음, 실험
테스트는 정리). `medium/"재현 있으면↑"` → `high/"X_test.go가 Y로 실패"`.

### (2) planner DESIGN/bug-cycle — 버그캡처 테스트를 *요구사항*으로
`agents/planner.md` §5.2(또는 bugfix는 §6.4)에 추가:
- 디자인은 **red→green 버그캡처 테스트** ≥1개 명시(수정 전 실패, 수정 후 통과).
- 사용할 **시뮬 레벨(L1/L2/L3)** + harness 빌딩블록 기재.
- `root-cause-lifecycle` step5의 **증상 비대칭(판별변수)** 을 assert로 인코딩.
- §4.4 Verification Plan 템플릿에 "Simulation level + repro test name" 행 추가.
- 톤은 기존 §5.2b(파생상태 게이트)의 형제로.

### (3) implementer — bugfix는 red-before-green 프로토콜
`agents/implementer.md` §4.2에 bugfix 분기: 재현 테스트 먼저 작성·실행 → "디자인이 예측한
방식으로 fail(red)" 확인·기록 → 프로덕션 수정 → 재실행 green 확인. red/green 출력 `impl.log`에 남김.

### (4) evaluator — 회귀캡처 게이트 (핵심 enabler, §7 참조)
`agents/evaluator.md` §4.6 옆에 bugfix 전용 게이트 추가. green 여부가 아니라 **테스트가 그 버그를
실제로 잡는지** 기계 검증.

### (5) 리포트/상태 연결
evaluator `test-report.md`에 "Regression capture: red(pre-fix)→green(post-fix) 확인됨/실패" 행
추가 → orchestrator PASS/FAIL·bug-cycle 재진입 근거에 반영.

### 우선순위
**코어 3종 = 신규 harness 스킬 + (2) planner 요구사항 + (4) evaluator red→green 게이트.**
(1)/(3)/(5)는 보강.

---

## 7. 핵심 enabler 상세 — evaluator의 red→green 기계 검증

"수정으로 이슈가 진짜 고쳐졌나"를 증명하는 가장 강한 수단이며 현재 완전히 비어 있음.
evaluator가 **격리 worktree**에서:

```
1. 회귀 테스트 이름을 design/plan-fix에서 읽음
2. HEAD(수정본)에서 그 테스트 실행 → PASS(green)여야
3. worktree에서 프로덕션 변경분만 되돌림
   (테스트 파일은 유지: git checkout main -- <비테스트 변경파일>)
4. 그 테스트만 재실행 → FAIL(red)이어야
5. 복원
→ 2,4 둘 다 PASS면 "테스트가 버그 못 잡음" → 게이트 FAIL, planner로 회송
```

`Agent`의 `isolation:"worktree"` 또는 evaluator Bash로 구현. 단일 테스트만 돌려 저비용.
evaluator §4.6 철학("green suite는 필요조건일 뿐")을 회귀 테스트로 확장.

---

## 8. 다음 행동 (NEXT — 여기서 재개)

> **⚠️ 이 NEXT는 SUPERSEDED (2026-06-22).** 당시의 "범위 결정 대기"는 더 이상 유효하지 않다.
> 코어(제안 (2)·(4) + (3)·(5))는 `reproduce-first` 트랙으로 **이미 구현됐다**(상단 STATUS 표 참조).
> 남은 살아있는 작업은 **단 하나 — 제안의 신규 스킬 (`simulation-harness`)** 뿐이다:
> 재현 테스트의 **시뮬레이션 레벨 라우팅(L1 단위 / L2 in-process 체인·합의 / L3 ChainBench)** 을
> 카탈로그화하고 ChainBench(L3, 20분)를 L2로 down-push. red→green *골격*은 손대지 말 것(이미 있음).
> 아래 "구현 착수 후 권장 순서"는 이제 그 잔여(harness 스킬)에만 적용된다.

<details><summary>역사적 원문 (당시 막힌 지점 — 보존용)</summary>

**막힌 지점**: 사용자에게 "구현 범위"를 묻는 `AskUserQuestion`을 던졌으나 사용자가 reject하고,
대신 이 핸드오프 문서 작성을 요청함. 즉 **범위 결정이 아직 안 남.**

재개 시 첫 행동: 사용자에게 아래 4개 범위 중 무엇으로 구현할지 확인.
1. **코어 3종 먼저** — 신규 harness 스킬 + planner 버그캡처 요구사항 + evaluator red→green 게이트.
2. **전체 6지점** — 코어 3종 + diagnose `--repro` + implementer red-before-green + 리포트 연결.
3. **harness 스킬만** — 레벨 정의 + 레시피 + PR77 예시부터.
4. **설계문서만** — 코드 수정 없이 이 제안을 plugin 안 설계 제안 .md로 정리(사실상 이 문서가 초안).

</details>

구현 착수 후 권장 순서(코어 3종 기준):
1. `skills/simulation-harness/SKILL.md` 신설(다른 스킬들 톤·길이 참고: 50~90줄, frontmatter `name`/`description`/`type: skill`).
2. `agents/evaluator.md`에 §4.6 형제로 "회귀캡처 게이트" 섹션 추가(+ §7 red→green 절차, §8 리포트 행).
3. `agents/planner.md` §5.2/§4.4/§6.4에 버그캡처 테스트 요구사항 + 시뮬 레벨 추가.
4. 각 agent frontmatter `skills:`에 `simulation-harness` 등록.
5. (선택) `commands/diagnose.md` `--repro`, `agents/implementer.md` red-before-green.

---

## 9. 작업 시 주의/제약 (놓치면 안 되는 것)

- **레벨 다운-푸시**: 가능하면 L2로 끌어내려 ChainBench(L3, 20분)는 합의/거버넌스/state 티켓에만. evaluator §7은 유지하되 L2가 1차.
- **결정성**: `testEnv`는 타이밍 의존 → flaky 위험. harness 스킬에 동기화·타임아웃 가이드 명시, 회귀 테스트 `-count=1`.
- **읽기전용 계약**: `/diagnose --repro`는 throwaway/worktree 격리, 커밋 금지 명시.
- **기존 패턴 재사용**: evaluator §4.6(파생상태 게이트)와 planner §5.2b(write-site completeness)가
  이미 "green만으론 부족" 철학의 선례다. 새 게이트는 그 형제로 톤을 맞출 것.
- **플러그인 문서 규약**: agent .md는 "워크스페이스 아티팩트는 Write 허용"이 명시적 예외(planner §0/evaluator §0). 스킬은 짧고 명령형.
- **CKS MCP 도구**는 이 세션 후반에 연결 해제됨(`mcp__plugin_coding-agent_cks__*` 사용 불가). 플러그인 .md 파일 수정 자체엔 불필요하니 무관. 필요 시 재연결 후 사용.
- **커밋/푸시**: 사용자가 명시 요청하기 전엔 하지 말 것. 플러그인 repo는 별도이며 현재 브랜치 확인 후 작업.

---

## 부록 A. 이 세션에서 실제로 읽은/조사한 것 (재조사 불필요)

- 전체 정독: `agents/planner.md`(800줄), `agents/evaluator.md`(623줄), `agents/implementer.md`(364줄),
  `commands/diagnose.md`, `skills/root-cause-lifecycle/SKILL.md`, `consensus/wbft/backend/multiengine_test.go`.
- 부분 확인: `commands/analyze.md`, `consensus/wbft/testutils/genesis.go`(함수 시그니처),
  go-stablenet `eth/gasprice/anzeon.go`(전체), `core/txpool/legacypool/legacypool.go`(관련 부분),
  `core/types/transaction.go`(EffectiveGasTip/AnzeonTipCap), `core/types/block.go`(Header.GasTip).
- 플러그인 내 "reproduce/재현/simulation" grep: 거의 없음(template-parse에 재현*방법* 필드,
  root-cause-lifecycle:42에 재현 언급뿐) → 이 기능이 신규임을 확인.

## 부록 B. 핵심 파일 라인 레퍼런스 (빠른 점프용)

- `agents/planner.md`: §4.4 Verification Plan(L407), §5.2 Tests(L486-489), §5.2b 파생상태(L491-526), §6 Bug cycle(L574-668), §6.4 Verification(L648-651).
- `agents/evaluator.md`: §4 Unit Test(L94), §4.6 파생상태 게이트(L165-203), §7 ChainBench(L305-473), §8 리포트(L477-534).
- `agents/implementer.md`: §4.2 Implement(L152), §4.4 Commit split(L207-230).
- `commands/diagnose.md`: §3 planner 디스패치 프롬프트(L43-73).
- `skills/root-cause-lifecycle/SKILL.md`: 절차 step5·6(L27-35), PR77 워크드 예(L44-51), 산출(L37-42).
