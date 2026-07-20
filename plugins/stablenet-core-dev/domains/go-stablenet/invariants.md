# StableNet Critical Invariants (always-on backstop — L3)

> Domain-pack data for `go-stablenet`. Loaded as the search-independent L3 backstop
> via the `domain-pack` loader skill (and, until Phase 2 rewires agents, via the
> `stablenet-invariants` pointer skill). Moved here verbatim from
> `skills/stablenet-invariants/SKILL.md` in overlay P1 Phase 1.

이 불변식들은 cks 검색이 무엇을 surface 하든 **항상** 성립한다. 인덱스가
없거나 검색이 비어도 적용된다. 아래 중 하나라도 위반하면 테스트가 통과하더라도
byzantine-fairness 또는 합의 안전성 버그다. Planner는 설계 시, Evaluator는
diff 판정 시 이 목록을 기준으로 본다.

1. **EQUAL POWER.** 모든 StableNet validator의 의결권 = 1 (PoA 등가-power,
   WEMIX식 stake-weighted 아님). stake 가중 투표·보상·정족수 계산을 절대
   도입하지 말 것. 정족수 `Quorum = ⌈N − (N−1)/3⌉` 를 등가-power validator
   위에서 계산한다.

2. **EPOCH-LENGTH ASYMMETRY.** epoch 길이 변경은 validator 간 diligence/accounting
   에 **비대칭적으로** 영향을 준다. epoch 길이 변경은 단순 상수 수정이 아니라
   byzantine-fairness 변경이므로 명시적 공정성 분석을 요구한다.

3. **ROUND-CHANGE NEUTRALITY.** round change(타임아웃 시 proposer 회전)는
   proposer-share 나 보상 accounting 을 바꾸면 **안 된다**. round change 는
   liveness 메커니즘이지 경제적 이벤트가 아니다.

4. **QUORUM FLOAT SAFETY.** 정족수/임계값 계산은 정수/⌈⌉-정확이어야 한다.
   정족수에 float 비교를 쓰지 말 것 — float 정밀도가 표결 결과를 뒤집을 수 있다.

5. **STICKY-PROPOSER CONCENTRATION.** Sticky proposer 정책은 제안권을 집중시킨다.
   proposer 선정 변경은 validator 집합 전체에 대한 장기 공정성을 보존해야 한다
   (RoundRobin 과 Sticky 는 공정성 프로파일이 다르다).

6. **INSTANT FINALITY / INERT REORG.** WBFT의 Commit-quorum 블록은 **즉시 최종**
   이다. geth의 `forker`/TotalDifficulty 코드(`core/forkchoice.go`,
   `core/blockchain.go`의 `bc.forker`)는 트리에 남아 있지만 inert(비활성) 잔재다.
   StableNet 로직으로 이 경로를 확장하거나 `TotalDifficulty`/`ReorgNeeded`에 의존
   하지 말 것. consensus-관련 fork-choice 변경은 `consensus/wbft/`에 한정한다.

7. **BASE FEE REDISTRIBUTION (NOT burned).** Ethereum EIP-1559와 달리 base fee는
   **소각하지 않고 validator에게 재분배**된다(WBFT Finalize 경로). 수수료/보상
   코드에서 EIP-1559 burn 의도를 도입하면 WKRC 공급 무결성과 validator 인센티브
   계약을 모두 깬다. Finalize의 정상 호출 경로를 우회하는 fast-path 금지.

8. **WKRC ≠ ETH.** 네이티브 자산은 **WKRC**(KRW 페그 스테이블코인)이며
   symbol/name=`WKRC`, currency=`KRW`, decimals=18이다. `Ether`/`wei` 식별자는
   geth 잔재일 뿐 실제 단위는 WKRC-wei다. 네이티브 mint/burn은 GovMinter +
   NativeCoinManager 정밀 경로의 은행-백킹 이벤트이지 프로토콜 발행이 아니다 —
   block reward로 native 발행을 절대 추가하지 말 것.

9. **CHERRY-PICK PRINCIPLE.** StableNet 고유 로직은 **새 파일**에 둔다 (예:
   `eth/handler_istanbul.go`, `core/types/tx_fee_delegation.go`). geth 원본
   파일(`eth/handler.go`, `core/blockchain.go`, `core/types/transaction_signing.go`
   등)에 StableNet 분기를 인라인하면 upstream cherry-pick이 깨진다. geth 파일에는
   최소 dispatch glue / 인터페이스 만족만 허용한다. 파일 경계의 권위는
   `.claude/docs/build-source-files.md`의 'StableNet 고유' 컬럼이다.

10. **FEEPAYER SIGHASH PAYLOAD.** 수수료 위임 트랜잭션(`0x16`)의 feepayer 서명은
    **`[[inner-tx-incl-sender-V/R/S], FeePayer]`** 위에 이루어진다 — 내부 tx만
    해시하거나 FeePayer를 trailing field에서 누락하면 feepayer 교체 공격이
    가능해진다. sigHash 페이로드 모양(내부 VRS 포함 + FeePayer 후행)은 consensus
    contract의 일부이며 byte-단위로 보존해야 한다.

11. **CONCURRENCY DISCIPLINE.** (a) `consensus/wbft/core/core.go`의 `c.current`
    는 `currentMutex`(RWMutex) 안에서만 읽고 쓴다 — `priorState`의 별도 mutex는
    대체재가 아니다. (b) txpool 맵(`pending`/`queue`/`all`)은 `pool.loop()`
    goroutine 안에서만 변경한다 — RPC/sealer/p2p에서 직접 mutate 금지, 이벤트로
    enqueue한다. 두 규율 중 하나라도 깨지면 데이터 레이스 → 비결정적 합의 또는
    tx 손실/중복.

---

합의 엔진 = **WBFT** (QBFT 계열, RPC namespace = `istanbul`). System contract 의
정식 이름은 `gov_council` / `gov_minter` / `gov_validator` 이며, WEMIX식 staking
계열 이름을 쓰지 않는다. 정확한 수치·anchor 는 cks `verified` 도메인 엔트리가
권위이며, 이 backstop 은 인덱스에 의존하지 않는 고정 기준선이다 — 둘이 어긋나면
엔트리를 따른다.
