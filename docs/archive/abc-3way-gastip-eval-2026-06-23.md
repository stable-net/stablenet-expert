# A/B/C 3-way 비교 — GasTip 거버넌스 pending-pool 정체 버그 (2026-06-23)

> 성격: Tier 3 status / 실험 리포트. **correctness 판정은 보류**(neutral oracle 미적용 — 사용자 지시).
> A 결과는 **잠정(provisional)** — coding-agent 분석 단계 버그로 기대와 다름(§6). coding-agent 재수정 후 A 재실행 예정.
> A/B/C 정의 정본: [`bench-abc-mode-definitions.md`](./bench-abc-mode-definitions.md).

---

## 0. TL;DR

같은 버그(거버넌스 GasTip 복원 제안 tx가 pending pool에 정체)를 **3개 동일 코드 사본**에서
세 regime으로 독립 수정하고 비교했다. 모델은 셋 다 `claude-opus-4-8` 고정.

- **셋 다 자기 자체 회귀테스트로 RED→GREEN + 빌드 + race 통과**(각자 self-oracle).
- **그러나 수정 위치가 갈렸다**: A(cks)는 `eth/gasprice/anzeon.go:54`, B(맨몸)·C(프로젝트스킬)는 `miner/worker.go`+`core/blockchain.go`.
- 비용: **B 최저(~79k) < C(~99k) ≪ A(~259k)**.
- **어느 것이 canonical 정답인지는 미판정**(neutral oracle 보류). A는 분석단계 버그로 잠정.

---

## 1. 실험 설계

| 항목 | 값 |
|---|---|
| 대상 | go-stablenet (geth fork, WBFT 합의), 커밋 `0bf2f4d1b` |
| 사본 | `test/abc-test-a` / `-b` / `-c` — 셋 다 `0bf2f4d1b` clean, **동일 시작점** |
| 티켓 | `test/abc-ticket.md` (한글 원문 → X-bar 충실 영어, 증상-only) |
| 모델 | 세 모드 `claude-opus-4-8` 고정 (regime만 격리) |
| cks 정합 | 인덱스 head `0bf2f4d1b` = 사본 코드와 동일 → A의 cks 검색 유효 |

**버그(증상-only):** gasTip 27600→30000 변경 후, 27600으로 **복원**하는 거버넌스 tx가 pending pool에
계속 남아 블록 미포함. 통과기준: GasTip은 헤더 extradata(`WBFTExtra.GasTip`)에서 읽고, 변경값은
제안 블록 N이 아니라 **N+1부터** 적용(증가·복원 둘 다 N/N+1, M/M+1 일치).

### regime 정의 (정본 문서 요약)
- **A_cks** — coding-agent 전체 파이프라인(analyzer+cks → planner → implementer → evaluator). `abc-test-a`.
- **B_code_only** — 맨몸 LLM, 타깃 코드 + grep만. cks·coding-agent 스킬·프로젝트 `.claude` 전부 없음. `abc-test-b`.
- **C_project_skills** — 프로젝트 자신의 `.claude`(`/stablenet-review-code` + docs)만. coding-agent·cks 없음. `abc-test-c`.
- 격리는 **도구·스킬 부재**로 하드 보장(프롬프트 의존 아님).

---

## 2. 결과 — 모드별

### A — coding-agent + cks (abc-test-a) · 잠정
- **근본원인:** `eth/gasprice/anzeon.go:54` `AnzeonTipEnv.SetCurrentBlock` — 캐시 헤더를 **state Root가
  다를 때만** 갱신. GasTip은 다른데 Root 같은 연속 블록에서 헤더 교체 스킵 → 이전 GasTip 잔존.
  복원(30000→27600) 시 잔존한 높은 값이 정상 tx를 underpriced로 거부 → `legacypool.go:596` Pending strand.
- **수정:** `currentBlock`/`signer` 갱신을 Root 가드 밖으로 이동(매번 갱신), 비싼 `stateAt`만 Root-게이트.
- **단계별:** analyzer(cks, 근본원인+프로덕션 연결 RED) → planner → implementer(RED→GREEN) → evaluator
  (재현 유효성 VALID/GREEN + 수정타당성 PASS).
- **테스트:** `eth/gasprice/anzeon_repro_test.go` RED→GREEN, `-race` 통과, 빌드 OK.
- **비용:** ~259k 토큰 (analyzer 109k + planner 63k + implementer 35k + evaluator 52k). 4-에이전트 파이프라인.
- ⚠️ **잠정 사유:** §6 — 분석 단계 재현/검증 기능에 잔여 버그가 있어 기대와 다름. coding-agent 재수정 후 재실행 대상.

### B — 맨몸 LLM + 코드 + grep (abc-test-b)
- **근본원인:** `miner/worker.go:1200` `updateGasTipFromContract`→`TxPool.SetGasTip`이 블록 N의
  **post-state**(GovValidator slot)에서 소싱 → pool min-tip이 N 시점에 조기 상승 → 증가 제안 시
  `legacypool.go:487 RemotesBelowTip`이 복원 tx를 evict. consensus 헤더 생산측(`engine.go:622` parent-state)은 정상.
- **수정:** `core/blockchain.go` `gasTipUpdater(*state.StateDB)`→`(*types.Header)`, import 훅이 `block.Header()` 전달;
  `miner/worker.go` `updateGasTipFromHeader(header.GasTip())` 신설, post-state 경로 제거.
- **테스트:** `miner/gastip_governance_test.go` 자체 작성, RED→GREEN, `-race`/빌드 OK.
- **비용:** ~79k 토큰 (단일 whole-approach 솔버). **최저 비용.**

### C — 프로젝트 `.claude` 스킬 (abc-test-c)
- **근본원인:** B와 동일 — `miner/worker.go`+`core/blockchain.go` post-state 소싱 → N 시점 적용 → 복원 tx strand.
- **수정:** B와 동형 — pool/miner tip을 `header.GasTip()` extradata에 바인딩, dead 경로 제거.
- **사용한 프로젝트 자산:** `.claude/commands/stablenet-review-code.md`(절차+doc 인덱스),
  `.claude/docs/{review-guide, wbft-consensus(§14 WBFTExtra.GasTip), code-convention}.md`.
- **테스트:** `miner/worker_gastip_test.go` 자체 작성(N/N+1·M/M+1 extradata), RED→GREEN, `-race`/빌드 OK.
- **비용:** ~99k 토큰 (단일 whole-approach 솔버).

---

## 3. 비교표

| 축 | A (cks) | B (맨몸) | C (프로젝트스킬) |
|---|---|---|---|
| 수정 위치 | `anzeon.go:54` | `worker.go`+`blockchain.go` | `worker.go`+`blockchain.go` |
| 메커니즘 | 캐시 헤더 staleness | pool tip 조기 상승(evict) | pool tip 조기 상승(동상) |
| 자체 테스트 | RED→GREEN ✓ | RED→GREEN ✓ | RED→GREEN ✓ |
| build/race | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ |
| 토큰 비용 | **~259k** | **~79k** | **~99k** |
| 실행 구조 | 4-에이전트 파이프라인 | 단일 솔버 | 단일 솔버 |
| 독립 referee | evaluator(파이프라인 내) | 자체-oracle만 | 자체-oracle만 |
| 상태 | **잠정**(§6) | 완료 | 완료 |

---

## 4. 핵심 관찰 (correctness 판정 아님)

1. **근본원인 분기.** A(cks)만 `anzeon.go:54`(per-tx 캐시 staleness)를, B·C는 `miner/worker.go`
   (pool-tip 조기 상승)을 짚었다. **두 개의 서로 다른 수정 위치**다. 같은 증상이 두 메커니즘으로
   도달 가능한지, 한쪽만 canonical인지는 **neutral oracle 없이 단정 불가**.
2. **비용 역전.** 단일 whole-approach 솔버(B 79k / C 99k)가 4-에이전트 파이프라인(A 259k)보다
   3배 저렴. A의 비용은 단계분리(analyzer/planner/implementer/evaluator)와 cks 왕복의 합.
3. **self-oracle 한계.** 세 모드 모두 **자기가 작성한 회귀테스트로만** GREEN을 봤다 — 서로의 수정을
   교차 검증하지 않았다. "통과"는 "자기 framing에서 통과"이지 "canonical 정답"이 아니다.
4. **B≈C 수렴.** 프로젝트 `.claude` 스킬(C)이 맨몸(B) 대비 *다른 근본원인을 못 더 짚었고* 동일
   위치로 수렴 — 단, C는 doc 기반으로 WBFTExtra.GasTip 의미를 빠르게 확보(과정 차이는 §5 후속에서 정량화 여지).

---

## 5. 보류 중인 판정 (테스트 후 단계 — 사용자 주관)

다음은 **의도적으로 미수행**(사용자가 "모든 검토는 테스트 완료 후" 지시):
- **neutral oracle 대조** — 전문가 정답 diff(`bench/fixtures/pr77/expert-fix.diff`) 또는 chainbench
  라이브 N/N+1·M/M+1 시나리오로 **어느 수정이 canonical인지** 판정.
- **교차 재현테스트** — A의 oracle을 B/C 사본에, B/C의 oracle을 A 사본에 적용해 *각 수정이 다른 framing의
  증상도 닫는지* 확인(두 메커니즘이 독립인지 종속인지 규명).
- 이 판정은 **A 재실행(§6) 이후** 함께 수행하는 것이 정확하다(A를 신뢰 가능한 상태로 만든 뒤 비교).

---

## 6. A의 잠정성 + 후속 작업 (coding-agent 재수정 → A 재실행)

- **관찰(사용자):** 수정된 coding-agent의 **분석 단계 기능 — 재현 테스트 코드 구현 + 원인 검증** 이
  아직 제대로 동작하지 않아, **A 결과가 기대와 많이 다르다.**
  - 1차 A 실행: 재현 테스트가 **결함 오라클**(package types 하드코딩 모델 → GREEN 불가)이었음 → v0.1.25에서 일부 개선.
  - 2차(재실행, v0.1.25): evaluator는 VALID/PASS로 보고했으나, **분석 단계 신뢰성은 여전히 의심** → A는 **잠정**.
- **후속(확정):**
  1. **coding-agent 분석 단계 버그 재수정** (analyzer의 재현테스트 구현 + 원인 검증 경로).
  2. 재수정 후 **A 재실행** (동일 티켓·동일 abc-test-a clean 리셋).
  3. 그 다음 **§5 neutral-oracle 판정**을 A/B/C에 일괄 적용해 canonical 정답 확정.
- **재실행 절차:** `test/abc-test-a`를 `git checkout -- . && git clean -fd`로 `0bf2f4d1b` clean 복원 →
  워크스페이스 ticket 재배치 → plugin reload(버전 bump 필요) → A 파이프라인 재구동.

---

## 7. 방법론 caveat (해석 시 인지)

- **모델 비대칭:** A는 구현이 sonnet-4-6, B/C는 단일 솔버라 opus-4-8 단독(정의문서 §5b). 비용·품질 비교 시 인지.
- **in-process 한정:** 셋 다 라이브 멀티노드 chainbench 미실행(N/N+1·M/M+1 헤더 extradata 라이브 미검증) — 인-프로세스 프록시 테스트만.
- **self-oracle:** §4-3 참조. 교차/전문가 대조 전까지 "정확성" 단정 금지.
- **단일 사례:** 1개 버그(GasTip 거버넌스). 일반화엔 다모듈 N≥3 필요.
- 사본별 수정은 미커밋 상태로 각 `abc-test-*`에 잔존.
