# CKG 쿼리 검색 검증 테스트셋

> 목적: **ckg(Code Knowledge Graph)의 쿼리 검색 기능을 검증**하기 위한 테스트 입력 데이터.
> go-stablenet의 다양한 도메인(패키지)에서 추출한 **키워드 + 자연어 질의 문장**을 정리한다.
> 추출 기준일 HEAD: `9978930ba` · 모든 항목은 raw 코드에서 직접 추출(ckg 비의존 = 독립 ground truth).

---

## 0. 사용 규약 (중요)

1. **실험 구조**: 각 테스트 행의 **키워드(또는 문장)를 동일하게 4개 케이스에 입력**하고 결과를 비교한다.
   (4개 케이스 = 파일원문 / 그래프전체 / 개별조회 / 자동선별 등 컨텍스트 제공 방식)
2. **입력 ↔ 기대값 분리 (오라클 누수 금지)**:
   - **입력으로 쓰는 것**: `키워드`, `질의 문장`(자연어) — 이것만 AI/검색에 제공.
   - **절대 입력하지 않는 것**: `검증 기대값(정답 파일·심볼·라인)` — 채점·검증 용도로만 사용.
   - 이전 설계의 결함(정답 파일을 baseline 입력으로 줘버린 label leakage)을 구조적으로 차단한다.
3. **키워드 스타일 2종**을 모두 포함 — 검색 강건성 비교용:
   - `심볼형`: 코드 식별자 그대로 (예: `QuorumSize`, `FeeDelegateDynamicFeeTx`)
   - `개념형`: 자연어 개념구 (예: "정족수 계산", "수수료 위임 서명")
4. **검증 방법(권장)**: 검색 결과(파일·심볼·라인)가 기대값과 overlap(같은 파일 + 라인 범위 겹침)하는지로 recall/precision 산출. 심볼명은 `receiver.Method` 점표기를 마지막 식별자로 정규화해 비교.

---

## 1. 도메인 커버리지 (12개 패키지/영역)

| # | 도메인 | 패키지/파일 | StableNet 고유 |
|---|--------|-------------|:---:|
| D1 | WBFT 밸리데이터셋·정족수 | `consensus/wbft/validator/` | ✓ |
| D2 | WBFT 라운드체인지 | `consensus/wbft/core/{core,roundchange}.go` | ✓ |
| D3 | WBFT Prepare/Commit 합의 | `consensus/wbft/core/{prepare,commit}.go` | ✓ |
| D4 | WBFT justification(위조/리플레이 방지) | `consensus/wbft/core/justification.go` | ✓ |
| D5 | WBFT Aggregated Seal·BLS | `core/types/istanbul.go`, `consensus/wbft/backend` | ✓ |
| D6 | WBFT Finalize·블록확정 | `consensus/wbft/engine`, `backend` | ✓ |
| D7 | 거버넌스 밸리데이터 컨트랙트 | `systemcontracts/gov_validator.go` | ✓ |
| D8 | 거버넌스 council·블랙리스트 | `systemcontracts/gov_council.go` | ✓ |
| D9 | 거버넌스 minter·코인발행 | `systemcontracts/gov_minter.go`, `coin_adapter.go` | ✓ |
| D10 | 네이티브 컨트랙트 매니저 | `core/vm/native_manager.go` | ✓ |
| D11 | 수수료 위임 트랜잭션·txpool | `core/types/tx_fee_delegation.go`, `core/txpool/` | ✓ |
| D12 | Anzeon 가스가격 / 제네시스·체인설정 | `eth/gasprice/anzeon.go`, `core/genesis.go`, `params/config_wbft.go` | ✓ |

---

## 2. 테스트 케이스 (30문항)

표기: `Q##` | 키워드(심볼형/개념형) | 질의 문장(=입력) | 검증 기대값(=채점전용, 입력금지)

### D1 — WBFT 밸리데이터셋·정족수
| ID | 키워드 | 질의 문장 | 검증 기대값(파일 · 심볼) |
|----|--------|-----------|--------------------------|
| Q01 | `QuorumSize` / 정족수 계산 | WBFT에서 블록을 커밋하기 위한 최소 정족수(supermajority)는 어떻게 계산되는가? | `consensus/wbft/validator/default.go` · `defaultSet.QuorumSize` (≈226–229) |
| Q02 | `proposer` / 제안자 선출 | WBFT 밸리데이터셋에서 라운드마다 제안자(proposer)를 어떻게 선출하는가? (round-robin / sticky) | `consensus/wbft/validator/` · `roundRobinProposer` / `stickyProposer` |
| Q03 | `NewSetByValidators` / 밸리데이터셋 생성 | 밸리데이터 주소 목록으로 밸리데이터셋을 생성·정렬하는 로직은 어디에 있는가? | `consensus/wbft/validator/` · `NewSetByValidators` |

### D2 — WBFT 라운드체인지
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q04 | `newRoundChangeTimer` / 라운드체인지 타이머 | 라운드체인지 타이머는 언제 어떻게 스케줄되며, 동시성(레이스) 보호는 어떻게 하는가? | `consensus/wbft/core/core.go` · `Core.newRoundChangeTimer` (≈353) |
| Q05 | `broadcastRoundChange` / 라운드 변경 전파 | 노드가 다음 라운드로의 변경을 다른 밸리데이터에게 어떻게 브로드캐스트하는가? | `consensus/wbft/core/roundchange.go` · `broadcastRoundChange` |

### D3 — WBFT Prepare/Commit 합의
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q06 | `handlePrepareMsg` / PREPARE 처리 | PREPARE 메시지를 수신하면 어떤 검증을 수행하고 어떤 정족수 조건을 확인하는가? | `consensus/wbft/core/prepare.go` · `handlePrepareMsg` |
| Q07 | `commitWBFT` / 커밋 확정 | 커밋 정족수가 모이면 블록을 확정하는 흐름(commit)은 어떻게 진행되는가? | `consensus/wbft/core/commit.go` · `commitWBFT` |
| Q08 | `handleCommitMsg` / COMMIT 처리 | COMMIT 메시지의 서명과 정족수를 어떻게 수집·검증하는가? | `consensus/wbft/core/commit.go` · `handleCommitMsg` |

### D4 — WBFT justification (위조/리플레이 방지)
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q09 | `justification` / 라운드체인지 정당성 증명 | 라운드체인지 justification 메시지의 위조나 중복 투표를 어떻게 방지하는가? | `consensus/wbft/core/justification.go` |
| Q10 | 위조 방지 / 중복 투표 차단 | WBFT는 justification 증명에서 동일 밸리데이터의 중복 서명을 어떻게 걸러내는가? | `consensus/wbft/core/justification.go` |

### D5 — WBFT Aggregated Seal · BLS
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q11 | `WBFTAggregatedSeal` / 집계 서명 | 커밋 서명들을 하나의 집계 seal로 묶는 자료구조와 인코딩은 무엇인가? | `core/types/istanbul.go` · `WBFTAggregatedSeal` |
| Q12 | `aggregateSeal` / BLS 집계 | 백엔드에서 여러 밸리데이터의 서명을 집계(aggregate)하는 함수는 어디 있는가? | `consensus/wbft/backend/` · `aggregateSeal` |
| Q13 | `CommitSigners` / 커밋 서명자 추출 | 확정된 블록에서 실제로 커밋에 서명한 밸리데이터 집합을 어떻게 복원하는가? | `consensus/wbft/backend/` · `GetCommitSignersFromBlock` |

### D6 — WBFT Finalize · 블록확정
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q14 | `Finalize` / 블록 마감 | WBFT 엔진의 Finalize 단계에서 보상·시스템컨트랙트 처리 등 무엇을 수행하는가? | `consensus/wbft/engine/` · `Finalize` |
| Q15 | `FinalizeAndAssemble` / 블록 조립 | 블록을 최종화하고 조립(assemble)하는 엔진 메서드는 무엇인가? | `consensus/wbft/engine/` · `FinalizeAndAssemble` |
| Q16 | `WBFTExtra` / 헤더 extra 인코딩 | WBFT 블록 헤더의 extra 필드(밸리데이터·seal)는 어떻게 RLP 인코딩/추출되는가? | `core/types/istanbul.go` · `WBFTExtra` / `ExtractWBFTExtra` |

### D7 — 거버넌스 밸리데이터 컨트랙트
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q17 | `initializeValidator` / 밸리데이터 컨트랙트 초기화 | 제네시스에서 거버넌스 밸리데이터 컨트랙트 상태를 어떻게 초기화하는가? | `systemcontracts/gov_validator.go` · `initializeValidator` (≈52–184) |
| Q18 | 스토리지 슬롯 / validator slot | 밸리데이터 컨트랙트의 스토리지 슬롯 레이아웃은 어떻게 구성·기록되는가? | `systemcontracts/gov_validator.go` (+ `stateutil.go`) |

### D8 — 거버넌스 council · 블랙리스트
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q19 | `IsBlacklisted` / 블랙리스트 확인 | 특정 주소가 블랙리스트에 올라있는지 검사하는 로직은 무엇인가? | `systemcontracts/gov_council.go` · `IsBlacklisted` |
| Q20 | `initializeGovCouncil` / 거버넌스 카운슬 초기화 | gov_council 컨트랙트를 제네시스에서 초기화할 때 params-only alloc 처리는 어떻게 하는가? | `systemcontracts/gov_council.go` · `initializeGovCouncil` |
| Q21 | `GetAllBlacklisted` / 블랙리스트 조회 | 전체 블랙리스트 주소 목록과 카운트를 어떻게 조회하는가? | `systemcontracts/gov_council.go` · `GetAllBlacklisted` / `GetBlacklistCount` |

### D9 — 거버넌스 minter · 코인 발행
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q22 | `IsMinter` / 민터 권한 | 어떤 주소가 코인 민터(minter) 권한을 갖는지 어떻게 판정하는가? | `systemcontracts/gov_minter.go` · `IsMinter` |
| Q23 | `MintProof` / 발행 증명 | 코인 발행 제안(mint proposal)의 증명과 한도(allowance)는 어떻게 관리되는가? | `systemcontracts/gov_master_minter.go` · `MintProof` / `GetMaxMinterAllowance` |
| Q24 | `coin_adapter` / 코인 어댑터 | 거버넌스 코인 어댑터의 초기화 파라미터는 무엇이며 어디서 설정되는가? | `systemcontracts/coin_adapter.go` · `initializeCoinAdapter` |

### D10 — 네이티브 컨트랙트 매니저
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q25 | `ActiveNativeManagers` / 네이티브 매니저 | 네이티브 컨트랙트 매니저들이 어떻게 등록·활성화되고 실행 가능 여부를 판정하는가? | `core/vm/native_manager.go` · `ActiveNativeManagers` / `CanRun` |
| Q26 | `coinManagerBurn` / 코인 소각 | 네이티브 코인 매니저의 소각(burn) 경로는 어떻게 동작하는가? | `core/vm/native_manager.go` · `coinManagerBurn` |

### D11 — 수수료 위임 트랜잭션 · txpool
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q27 | `FeeDelegateDynamicFeeTx` / 수수료 위임 트랜잭션 | 수수료 위임(fee delegation) 트랜잭션 타입의 구조와 필드는 무엇인가? | `core/types/tx_fee_delegation.go` · `FeeDelegateDynamicFeeTx` |
| Q28 | `feePayer` 서명 / sigHash | 수수료 대납자(feePayer)의 서명 해시(sigHash)는 어떻게 계산되는가? | `core/types/tx_fee_delegation.go` · `sigHash` / `rawFeePayerSignatureValues` |
| Q29 | `NewFeeDelegateSigner` / txpool 검증 | txpool에서 수수료 위임 트랜잭션의 서명자·잔고를 어떻게 검증하는가? | `core/txpool/validation.go` (+ `legacypool/`) · `NewFeeDelegateSigner` |

### D12 — Anzeon 가스가격 / 제네시스 · 체인설정
| ID | 키워드 | 질의 문장 | 검증 기대값 |
|----|--------|-----------|-------------|
| Q30 | `AnzeonTipEnv` / anzeon 가스팁 | Anzeon 가스팁 환경(AnzeonTipEnv)은 GasTip 변경 시 현재 블록을 어떻게 갱신하는가? | `eth/gasprice/anzeon.go` · `AnzeonTipEnv` / `SetCurrentBlock` |

---

## 3. 보조 후보 풀 (확장·교체용)

추가로 필요하면 아래 키워드/심볼로 문항을 확장할 수 있다(동일 추출 기준):

- 제네시스/체인설정: `DefaultStableNetMainnetGenesisBlock`, `initializeAnzeonGenesis`, `AnzeonConfig`, `IsAnzeon` (`core/genesis.go`, `params/config_wbft.go`)
- eth 통합: `handleConsensusMsg`(`eth/handler_istanbul.go`), `makeQuorumConsensusProtocol`(`eth/quorum_protocol.go`)
- 시스템컨트랙트 슬롯: `CalculateMappingSlot`, `CalculateDynamicSlot`, `EncodeBytesToSlots`(`systemcontracts/stateutil.go`)
- WBFT 헤더: `GetValidators`, `GetSealers`, `EpochInfo`(`core/types/istanbul.go`)
- 백로그/메시지: `addToBacklog`, `checkMessage`, `deduplicatePrepares`(`consensus/wbft/core/`)

---

## 4. 난이도/유형 분포 (설계 의도)

| 유형 | 문항 | 의도 |
|------|------|------|
| 단일 심볼 핀포인트 | Q01, Q04, Q11, Q17, Q19, Q27, Q30 | 정확한 정의 위치를 짚는 검색력 |
| 흐름/관계 추적 | Q05, Q07, Q08, Q13, Q14, Q25 | 호출 관계·다중 파일에 걸친 이해 |
| 개념→코드 매핑 | Q02, Q09, Q10, Q18, Q22, Q29 | 자연어 개념을 실제 심볼로 연결 |
| 도메인 경계/고유성 | Q16, Q20, Q23, Q24, Q26, Q28 | StableNet 고유 로직(geth와 구분) |

> 비고: 키워드는 `심볼형/개념형` 2가지를 병기했다. 동일 문항을 **심볼형 키워드만**, **개념형 문장만**으로 각각 질의해
> 검색 강건성(식별자 의존 vs 의미 이해)을 비교하는 실험도 가능하다.
