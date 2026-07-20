# 남은 작업 상세 (Remaining Work — 무엇/왜/문제/기대결과)

> 작성: 2026-06-15. 짝 문서: [`followup-status-2026-06-15.md`](./followup-status-2026-06-15.md)(실측 대조·진행),
> [`./archive/followup-plan.md`](./archive/followup-plan.md)·[`./archive/followup-expected-outcomes.md`](./archive/followup-expected-outcomes.md)(원 계획).
> 각 항목은 **무엇 / 왜 / 해결하는 문제 / 기대결과**로 정리. 우선순위순.

## 추천 실행 순서 (2026-06-18 갱신 — 아키텍처 우선)

완료: ~~A~~✅ ~~E~~✅ ~~C 상태확인~~✅ ~~F-core(a/b/c)~~✅ ~~plugin Wave1~~✅ ~~diagnose/setup 명령~~✅(#11·#12 머지)
~~MCP 재연결(재빌드·인덱스·config)~~✅(06-22) ~~항목11 단독 라이브 검증~~✅(06-22) ~~항목12 재빌드·재연결~~✅(06-22).

**다음 순서:**
1. **Tier 0 — 즉시(저위험·독립)**: plugin Wave2 **③**(COMPLETION/COMPLETED 표시). *(②는 항목 10에 흡수됨)*
2. **Tier 1 — 핵심 아키텍처 = 항목 10**: ✅ **구현 완료(2026-06-19, v0.1.17)**. `analyzer` 분리 +
   reproduce-first(red→green) 4-스테이지 + bench-analyzer 변이. Wave2 ①②·기존 reproduce-first 흡수.
   **남은 것은 (d) 라이브 검증뿐.** (코드 검증은 lint·bench테스트·핸드오프 계약 정합으로 완료.)
3. **Tier 2 — thesis 종착점 = (d)**: 새 4-스테이지 위에서 **bugfix 1셀 완주(red→green·재진입 라이브 검증)** →
   전체 A/B/C. autopilot+승인+cks(PR-77 DB) 재설정+오염정리 필요.
4. **Tier 3 — 병행(cks측, 동시 세션)**: B-verify, D-2, D.
5. **Tier 4 — 정리**: txpool 브랜치, H, Wave3, diagnose 시험실행, CI 워크플로.

이유: 당신이 결정한 4-스테이지 분리는 (i) 책임을 쪼개 **효율↑**, (ii) cks 비교점을 **analyzer로 명확히 정렬**해
벤치(d)가 *더 깨끗한 파이프라인*을 측정하게 한다. 그래서 **(d) 이전에 항목 10을 먼저** 올리고, (d)의 첫 1셀로
**라이브 검증 + thesis 측정을 동시에** 한다. 항목 10은 토폴로지+벤치+상태기계를 동시에 바꾸므로 실제 실행 검증 필수.

진행 상태 범례: ✅완료 / ◐부분 / ⏳대기 / ☐미착수

---

## ✅ 1. E — evaluator §4.6 derived-state 게이트 직접 검증  *(완료 2026-06-15)*
- **무엇**: "maintained 집계(파생상태)를 추가했는데 일관성 invariant 테스트가 없는" 가상 diff를 evaluator에
  태워, §4.6 게이트가 **FAIL→bug cycle**을 발화하는지 실증.
- **왜**: §4.6은 출시됐으나 RETEST에서 planner가 파생상태를 회피(lazy-on-read)해 **한 번도 발화된 적 없음**(미실증).
- **해결하는 문제**: `truncatePending`류 파생상태 부작용에 대한 **2차 안전망의 신뢰성**, 그리고 F 본 실행의
  correctness 신호가 믿을 만한지에 대한 사전 보증.
- **결과**: ✅ **실증 완료.** negative.diff(테스트 없음)→**FAIL**, positive.diff(invariant+적대경로 테스트)→
  **PASS**, 둘 다 기대치 100% 일치. 과탐/미탐 없음. 산출물: `bench/fixtures/eval-gate/`(diff 쌍 +
  `expected.json` + `result-2026-06-15.md`). 검증: 실제 evaluator 에이전트 2회 디스패치(go-stablenet 변경 0).
- **후속(선택)**: 캐시/인덱스/카운터 형태·design §5.2b 경로 선언 케이스로 fixture 확장 가능(현재 add/sub aggregate만 커버).

## 🔴 2. (d) F-core 본 실행 — 1셀 완주 → 전체  *(핵심 마일스톤)*
- **무엇**: bug-cycle 루프가 들어간 하네스로 실제 A/B/C 셀을 ANALYSIS→…→EVALUATION_PASS까지 완주(현재 0건),
  compare.py로 총비용·cycle·side-effect 비교표 산출.
- **왜**: 프로젝트의 **존재 이유(thesis: "cks가 grep보다 정확·저렴한가")를 숫자로 증명/반증** — 사실상 종착점.
- **해결하는 문제**: "동작하지만 미증명" 상태(과거 N=1 측정은 FakeEmbedder 등으로 confounded).
- **기대결과**: A/B/C의 **bug-cycle 수·Σ토큰·회귀실패·최종정확성** 정량 비교 → go/no-go 데이터(반증도 가치).
- **전제/주의**: autopilot 세션 + **사용자 승인** + go-stablenet 변경 + **데이터셋 오염 정리 필수**. (c)·C 의존.

## 🟡 3. (c) eval-set 확장 — 모듈 다양화 + base_commit/oracle  *(◐대부분 완료 2026-06-15)*
- **무엇**: consensus+txpool → systemcontracts·state·miner·params 등으로 확장. 실제 PR의 **부모 커밋**을
  `base_commit`(버그 실재), 실제 fix를 oracle로.
- **왜**: 단일/소수 모듈은 **케이스 편향**. thesis 일반화엔 N≥3 + 다모듈 + **grep 경쟁 대조군** 필요.
- **해결하는 문제**: 단일 케이스 결론 위험. base_commit이 틀리면 버그가 이미 고쳐진 코드라 **trivially pass**(거짓 신호).
- **결과**: ◐ **6개 모듈 태스크 추가 완료** — `STABLE-0004`(systemcontracts/#83), `0005`(miner-Anzeon/#77),
  `0007`(state-genesis/#73), `0009`(chainconfig/#58), `0006`(params-hardfork/#68), `0008`(fee-policy/#14).
  매니페스트 `stablenet-abc-phase3.json`, 각 base_commit go-stablenet에 실재 검증. 검색 스펙트럼:
  그래프-heavy(consensus)·파생상태(txpool)·**교차언어(systemcontracts)**·**교차모듈(Anzeon)**·**grep대조군(params)**.
- **티켓 설계 원칙(2026-06-15 적용)**: 모든 티켓을 **증상-수준**으로 작성 — 증상·재현·영향영역만 주고
  **수정 메커니즘(함수명·코드 변경)은 누설 금지**. 누설하면 (i) 검색 품질이 무의미해져 cks 변별력↓,
  (ii) 전문가-유사도 테스트(PR-77식) 무효. 9개 티켓 전수 스캔으로 누설 0 확인. feature(0006/0008)는
  목표-수준(설계 자유도 큼 → 유사도는 약신호). 전문가 정답은 `oracle.reference_fix`로 평가 시점에만 참조.
- **남은 것**: ⚠️ **인덱스 drift** — cks 인덱스는 dev(c051d50b)에 빌드됨. base가 dev에서 먼 태스크
  (#68/#58/**#14**)는 retrieval drift↑ → 정밀 측정 시 base_commit에 인덱스 재빌드 고려. clean 태스크
  (#83/#77/#73)를 1차 실행 권장. oracle(chainbench_test)은 (d) 실행 시 live 검증.

## 🟢 4. C — chainbench 회귀 환경 정비  *(상태 확인 완료 2026-06-15 → 거의 안 막힘)*
- **무엇**: chainbench 회귀 환경이 (d) 본 실행의 정확성 축을 막는지 확인.
- **06-12 문서 대비 정정 (실측)**:
  - ✅ **`WKRC.yaml` 부재는 오독** — WKRC는 *코인 심볼*(스테이블코인)이지 프로파일명이 아님. v2 회귀
    환경은 이제 **`profiles/regression.yaml`로 존재**(4 BP+1 EN, AnzeonBlock=0/BohoBlock=0, 103 TC).
  - ✅ **sender 펀딩 해소** — regression.yaml alloc이 TEST_ACC_A~E(sender/recipient/fee-payer/authorize/
    blacklist) 모두 펀딩. 회귀 스위트도 `a-ethereum…h-hardfork/z-layer2` 9범주로 재구성("a2-*"는 stale 명칭).
  - ✅ **벤치 oracle 비차단(핵심)** — 배선한 oracle `basic/consensus`·`basic/tx-send`는 둘 다
    `get_running_node_ids`를 **0회** 사용 → 그 버그와 무관하게 실행 가능. **F 정확성 축은 막혀 있지 않다.**
- **남은 것(우리가 안 고침, chainbench 소유)**:
  - ❌ `get_running_node_ids` 여전히 repo 전체 미정의 → `basic/txpool-propagation`·`basic/wbft-consensus`·
    `fault/{network-partition,p2p-topology}` 4개만 exit 127. **벤치 oracle 아님 → 영향 없음.**
  - ⚠️ regression.yaml `binary_path`가 타 머신 경로(`wm-it-22-00661`) → 이 머신엔 gstable 빌드 존재
    (`go-stablenet/build/bin/gstable` ✓). `node.start binary_path` 런타임 override로 우회 가능(커밋 `3150719`).
- **결론**: C는 (d) clean 태스크 실행의 **블로커가 아니다.** 위 4개 스크립트가 필요한 회귀까지 덮으려면
  그때 chainbench 소유 측에 `get_running_node_ids` 정의를 요청. 그 전까지 해당 항목만 "부분 검증" 표기.

## 🟡 5. B-verify — intent 분류 정상동작 + demoteTests 결합 확인  *(cks 측, 병행, ☐)*
- **무엇**: 재작성된 임베딩 intent 분류기가 SN/KO 쿼리에서 정상 분류(비-empty, above-threshold)하는지,
  `demoteTests := intent != TestAdd` 결합 부작용이 있는지 측정.
- **왜**: intent가 틀리면 composer의 symbol-kind/relation 필터가 광역모드로 죽고, test-add 태스크에서 테스트 오강등.
- **해결하는 문제**: 잔여 recall 갭의 유력 근본원인 + 검색 노이즈.
- **기대결과**: intent 분류율↑ → 필터 활성 → 노이즈↓·랭킹↑ (file recall 0.8→0.9+ 목표).

## 🟢 6. D-2 — KO recall 회귀(0.71→0.57)  *(cks 측, 신규 발견, ☐)*
- **무엇**: production-over-test 강등 + glossary 확장 영향을 **분리 측정**(demoteTests on/off),
  ko01-quorum·ko04-commit MISS 원인 규명.
- **왜**: SN을 +0.10 올린 변경이 **한국어를 회귀**시킴 — 의도된 트레이드오프인지 버그인지 미확인.
- **해결하는 문제**: 한국어 시나리오 검색 품질 저하.
- **기대결과**: 회귀 원인 격리 → KO recall 회복, on/off 정책 결정.

## 🟢 7. txpool fix 브랜치 처리  *(정리, ☐)*
- **무엇**: 로컬·미푸시 브랜치 `920ec4320`(3커밋) 방향 결정 — 내 수정(maintained map+Cap 훅) vs
  0.1.10 planner의 lazy-on-read 설계 수렴점.
- **왜**: 실제 발견한 고-가치 버그 수정이 **dev 미반영 방치** 중. (플랜의 G=PR 조율은 명시 제외 → 방향 결정까지만.)
- **해결하는 문제**: FD tx 오탐 거부(DoS 방어가 정상 트래픽을 막는 가용성 버그).
- **기대결과**: 머지/보류 결정 + STABLE-0003 벤치 태스크 oracle 정합.

## 🟢 8. D — SN 잔여 miss(sn06 gas price, sn07 blacklist)  *(수확체감, ☐)*
- **무엇**: 임베딩/청킹(contextual retrieval) 개선으로 file-level 진짜 miss 회복.
- **왜/문제**: intent로 흡수 안 되는 임베딩 한계 영역.
- **기대결과**: file recall 0.9+ 접근 — 단 **큰 비용 대비 작은 이득** 가능(낮은 우선순위).

## 🟢 9. H — 가드레일 일반화  *(마무리, ☐)*
- **무엇**: invariant-backstop을 합의 불변식 → **구현 불변식**으로 확장, 메모리/문서 정리.
- **왜/문제**: 현재 backstop이 합의 도메인 한정 → txpool 외 태스크엔 미적용.
- **기대결과**: 신규 derived-state 태스크에서 §5.2b/§4.6 자동 적용 → 전 태스크 유형 부작용 예방.

## 🔵 10. analyzer 분리 + reproduce-first 4-스테이지 파이프라인  *(✅ 구현 완료 2026-06-19, v0.1.17 — (d) 라이브 검증만 남음)*

> **구현 완료 (steps 1–9, main 반영)**: analyzer.md 신설(`21ff012`) → planner 슬림+orchestrator 배선(`d90fd82`)
> → reproduce-first 스킬(`055d14c`) → implementer CARRY+evaluator GREEN(`dbab246`) → state-machine 계약+cycle
> 단일화(`388b51a`) → bench-analyzer 변이(`38fa137`) → diagnose→analyzer 통일(이 커밋). lint·bench테스트(14/14)·
> 핸드오프 계약 정합 검증 완료. **남은 것: (d) 실제 bugfix 1셀로 red→green·재진입 라이브 검증(Tier 2).**

> **흡수**: 기존 reproduce-first(T1~T8) + Wave2 ①(cycle 단일화) + Wave2 ②(bench-planner drift)를 모두 포함한다.

- **무엇 (방법론)**: 현재 `planner` 한 에이전트가 *분석·재현·원인규명·설계·계획*을 다 한다 → 책임 과다. 이를
  **`analyzer`(분석·재현·원인) + `planner`(설계·수정계획)** 로 쪼개고, 전 과정을 **reproduce-first(red→green)**
  하네스로 닫는다. work_type=`bugfix`에서 재현 테스트가 "정답 오라클"이 된다.

### 4-스테이지 토폴로지
| 스테이지 | 책임 | 입력 | 산출물 |
|---|---|---|---|
| **analyzer**(신규) | ①상황분석(cks) ②**재현 테스트 작성+실행→실패(RED) 확인** ③근본원인 규명 | ticket(증상·재현방법)/[재진입]evaluator 실패문서 | `analysis.md`, **`reproduction_test`(RED 확인)** |
| **planner**(슬림) | 원인 기반 **설계+수정계획**만(§5.2b write-site 반영). 분석·재현 안 함 | analyzer 산출물 | `plan.md`,`design-v{N}.md` |
| **implementer** | 계획대로 **TDD red/green 수정**(수정용 단위테스트). **재현 테스트 불가침** | plan/design+reproduction_test | 분리 커밋(test/fix)+빌드 |
| **evaluator** | **재현 테스트 재실행→PASS(문제 재현 안 됨) 확인** + 전체 스위트/§4.6 + **chainbench ready면 e2e** | 브랜치+reproduction_test | `test-report.md`/[실패]실패문서 |

### red→green 하네스 위치
- analyzer: 재현 테스트 작성→실행→**반드시 FAIL(RED)**. PASS(재현 불가)면 `reproduction_unobtainable`로 **조기 중단**.
- implementer: 수정을 TDD로 완성(자체 단위테스트 red→green). 재현 테스트는 손대지 않음.
- evaluator: 재현 테스트 재실행→**반드시 PASS(GREEN)** (+가능하면 parent에서 FAIL 재확인=진짜 red→green) + chainbench e2e(없으면 graceful skip).

### 재진입 루프 (analyzer로)
`evaluator FAIL → 실패문서 → analyzer가 "무엇을 놓쳤나" 추가분석(재현 테스트 재생성 X·재사용, 잘못 짠 경우만 수정)
→ planner 계획 보정(plan-fix-{cycle}) → implementer 재수정 → evaluator → green까지 / max_eval_cycles 초과 BLOCKED.`
※ 기존 상태기계가 이미 `EVALUATION→ANALYSIS` 실패사이클을 가지므로 ANALYSIS의 주인만 analyzer로 바꾸면 토폴로지 정합.

### 기존 자산 재사용 (#13, 이미 main — 중복 구현 금지)
PR #13(`c45e3bc`, v0.1.13)이 **`root-cause-lifecycle` 스킬**(근본원인 *추론 절차*: 값→모든 복사본/캐시→
깨진 lifecycle edge→소스 역추적→증상 비대칭 반증)을 추가하고 planner §6·`/diagnose`에 배선했다.
→ analyzer의 **"원인규명" 두뇌는 이미 존재** = **재사용**(신규 개발 X). item 10의 신규 skill은 `reproduce-first`(red→green) **하나뿐**.
- 분리 시 **#13 배선을 함께 이전**: planner §6의 root-cause-lifecycle 적용 + §5.2b 크로스레퍼런스 → analyzer로.
  planner엔 §5.2b(설계시점 거울상)만 남겨 forward/backward 대응 보존.
- `/diagnose`의 root-cause-lifecycle 사용(#13)은 diagnose→analyzer 디스패치로 바꿀 때 자연 승계.

### 필요한 plugin 변경 (파일)
- **신규** `agents/analyzer.md`(planner에서 ANALYSIS+재현+원인 추출; 스킬 `root-cause-lifecycle`(#13, 재사용)·`reproduce-first`(신규)·cks·stablenet-* 적용), `skills/reproduce-first/SKILL.md`(red→green 단일 정의)
- **수정** `agents/planner.md`(설계/계획만; §5.2b 거울상 유지), `implementer.md`(수정 TDD·재현테스트 불가침), `evaluator.md`(재현 재실행 오라클·조건부 chainbench e2e·실패문서→analyzer), `orchestrator.md`(디스패치: ANALYSIS→analyzer·실패사이클→analyzer)
- **수정** `skills/state-machine`(마커 `reproduction_confirmed`·실패유형 `reproduction_unobtainable`·**cycle 인덱스 단일화=Wave2①**), `skills/template-parse`(bugfix "재현 방법" 필수)
- **벤치**: A/B/C 변이를 **analyzer 변이**로 — 신규 `agents/bench-analyzer-{codeonly,skills}.md`(기존 bench-planner-* 대체→Wave2② 해소), `bench-orchestration` mode_agents·매니페스트 갱신
- **명령** `commands/diagnose.md`(analyzer 디스패치로 통일 = "analyzer 단독 실행"), 필요시 `work.md`/`analyze.md` 참조 갱신
- 버전 bump (현재 main **0.1.13**부터)

### 효율·하네스 이점
단일 책임→프롬프트 작고 집중(토큰·컨텍스트↓)·핸드오프 명확 / 재현 테스트 1회 작성·재사용(재생성 churn 제거) /
재진입이 "놓친 것" 타겟 분석(전체 재분석 X) / **벤치 비교점이 analyzer로 정렬→thesis 측정 더 깨끗** / chainbench 조건부 e2e.

- **왜**: 회귀 테스트가 *증상을 실제로 잡는지* 보장(현재 AC "regression test 추가"는 red 검증이 없어 빈 테스트도 통과 가능).
  벤치(d) correctness/side-effect 신뢰도↑, 모델-독립적 수정 품질, planner 과부하 해소.
- **위험·전제**: **에이전트 토폴로지+벤치+상태기계 동시 변경**(이번 프로젝트 최대 변경). 정적 추론만으로 넣으면 어긋남 →
  **실제 bugfix 1셀 완주로 red→green·재진입 라이브 검증 필수** → (d) Tier 2와 묶어 검증.
- **정합 메모**: 재현 테스트는 **analyzer 산출물**로 확정(사용자 글의 "planner에 의해"는 책임분리상 analyzer로 정리; 변경 원하면 조정).

### 🔬 라이브 검증 기록 (2026-06-19) — `/diagnose` × PR-77, **입력 민감도 발견**
새 analyzer를 `/diagnose`로 라이브 검증(read-only). cks는 PR-77 base(`0bf2f4d1b`)에 인덱싱됨. **두 번 돌렸고 결과가 갈렸다**:
- **유도적 입력**(증상에 "동일 state root"·"빈 블록"·`--path eth/gasprice`·self-heal 타이밍 포함) → 정답 도달:
  `SetCurrentBlock` state-root 가드 = **전문가 fix와 일치**.
- **공정/lean 입력**(메커니즘 단서 제거, `--path` 제거) → **다른(틀린) 근본원인**(`pool.gasTip` goroutine race)으로 결론,
  **정답 위치(`SetCurrentBlock` 가드)를 명시적으로 배제**("거버넌스 tx는 non-empty라 안 걸림").
- **결론**: 입증된 건 **인프라 동작(analyzer·cks·root-cause-lifecycle·diagnose 라이브)** 뿐. "cks가 스스로 정확 진단"은
  **입력이 절반쯤 답을 줬을 때만** 성립 — 입력 품질이 결과를 지배한다. (그래서 STABLE-0005 티켓을 관측-증상-only로 교정함, `b0e72b2`.)
- **시사**: (i) 벤치는 A/B/C에 **동일·공정 입력** 필수 — A_cks조차 공정 입력엔 틀릴 수 있고, *그게* 진짜 측정 대상. (ii) ↓ 항목 11.

## 🟡 11. analyzer/root-cause-lifecycle 시간적-추론 보강  *(신규 2026-06-19, ☐ — 위 검증에서 발견)*
- **무엇**: 공정 입력에서 analyzer가 **"트리거 *이후* 블록/상태에서 무슨 일이 생기나"** 를 재구성 못 해 정답을 배제했다.
  root-cause-lifecycle/analyzer에 **시간적 단계**(트리거 직후 후속 블록·캐시가 어떻게 갱신/미갱신되는가)를 명시적으로 추가.
- **왜**: PR-77류 staleness 버그는 "트리거 블록"이 아니라 "그 *다음* 빈 블록 구간"이 원인 — 정적 호출그래프만으론 안 보인다.
- **구현 ◐(2026-06-19, v0.1.20)** — 일반화 버전으로 랜딩(도메인 단서 없음):
  - **① `investigative-probe` 스킬(신규)**: 후보가 갈리면 throwaway 계측 테스트로 런타임 값 관찰→판별→원복. analyzer·bench-analyzer-* 공유. diagnose 모드도 프로브 허용(원복 조건).
  - **② root-cause-lifecycle 확장**: 시간적 시퀀스 추적(트리거 *이후* 이벤트 + "증상을 해소시키는 이벤트=누락 갱신 지점").
  - **③ root-cause-lifecycle 확장**: 다중-후보 규율(정적 falsification만으로 단일 확정 금지 → 프로브 판별/competing 보고).
  - **A-보강 (v0.1.21, lean2 재진단 실패서 도출)**: ①②③를 넣고도 lean 입력에서 또 오진 → analyzer가 **cks가 준
    pack 본문**(`ValidationOptionsWithState`: "Anzeon tip cap *during validation*")을 **거슬러** "Anzeon은 admission 아님"
    단정 + 프로브 스킵. 그래서 root-cause-lifecycle/analyzer에 **(a) 효과-완전성**(같은 효과 내는 *모든* 경로/단계/use-site
    전수 열거 후에만 후보 배제), **(b) 확증편향 차단**(받은 pack 본문으로 *내 가설*을 먼저 반증; pack을 거슬러 단정 금지),
    **(c) 동일효과 다중경로 → 정적 제거 금지·프로브 강제** 추가.
- **검증(✅ 통과 2026-06-22)**: v0.1.21(①②③+A보강) analyzer를 **공정 증상-only 티켓**(PR-77, `test-data/pr-77/ticket.json`,
  메커니즘 단서·`--path` 없음)으로 단독 라이브 실행 → **PRIMARY 근본원인 `anzeon.go:54 SetCurrentBlock` 정확 도달** +
  RED 재현 독립 확인. 이전 lean2 오진(`pool.gasTip` race로 정답 배제)과 대조적 — **시간적-추론/확증편향 보강이 공정입력에서 정답 도달을 가능케 함**을 입증.
  단 oracle 2차(`RemotesBelowTip`)는 인접 메커니즘(anzeonTipCap 캐시)만 식별·미지목(ANALYSIS 단계 경계상 Planner 몫). 상세: `test-data/pr-77/analyzer-run/verdict.md`.
- **주의**: 입력은 공정하나 lean2와 **바이트 동일은 아님** + **단일 사례(PR-77)** — 일반화엔 여전히 **2~3개 다른 staleness 사례** 재확인 필요. 절차엔 도메인 단서 0. 과적합 금지.

## 🟣 12. ckg 인터페이스/동적-디스패치 호출 엣지 해소  *(◐ 구현완료 2026-06-19, 재빌드·재연결 완료 2026-06-22 / find_callers(GetAnzeonTipCap) 직접검증 잔여)*

> **구현 (ckg `5b60d00`, branch feat/canonical-id-refinements-b2b4)**: `find_callers`가 구상 메서드 seed를
> **`implements` 엣지로 인터페이스 메서드까지 확장**해 호출자 union(`pkg/mcphandlers/{helpers,handlers}.go`의
> `interfaceMethodSeeds`/`reverseCallersUnion`). 핸들러 전용 → **인덱스 재빌드 불필요**. 단위테스트
> `interface_bridge_test.go`(Thing implements Hasher; UseHasher가 인터페이스 경유 호출)로 **갭→복구 입증**, mcphandlers 전체 회귀 통과.
> **재빌드·재연결 (2026-06-22, 완료)**: cks-mcp/ckg/ckv 최신 소스로 재빌드(바이너리에 `interfaceMethodSeeds` 임베딩 확인),
> `settings.json` CKS_CONFIG→`test-data/pr-77/cks-pr-77.yaml`(schema 1.21·head 0bf2f4d1b) 배선, `/mcp` 재연결,
> 라이브 `cks.ops.health=ok`. analyzer 단독 라이브에서 `find_callers("SetCurrentBlock")`이 호출자 3곳을 정상 반환.
> **남은 것**: 항목 12의 *특정* 케이스 `find_callers("GetAnzeonTipCap")`(iface 경유 호출)이 `ValidateTransactionWithState`(+Pending)를 반환하는지 **직접 확인**(이번 analyzer는 SetCurrentBlock 구상 호출자 경로로 도달해 이 엣지를 직접 타진하지 않음).
- **무엇**: ckg 호출그래프가 **인터페이스 메서드 호출을 구상 구현에 연결하지 못한다.** 검증: lean2 진단에서
  `find_callers("GetAnzeonTipCap")` → **self-edge만**(실호출자 0). 원인: `GetAnzeonTipCap`이 `validation.go:338`에서
  **인터페이스 타입**(`opts.AnzeonTipEnv types.AnzeonGasTipEnv`)으로 호출됨 → ckg가 iface→impl 미해소.
  (구상 함수 호출은 정상: `find_callers("ValidateTransactionWithState")` → `validateTx`(673-701) 나옴.)
- **왜**: "이 값을 *누가 계산/소비하나*"를 graph로 추적할 때, 의존이 인터페이스로 주입되면 끊겨 **value/consumer 전수
  열거가 실패** → 부분진단. (이번 오진의 *부차* 원인. 주원인은 항목 11의 A — 받은 정보를 규율 있게 안 씀.)
- **작업**: code-knowledge-graph repo — Go 인터페이스 메서드 call-site를 구상 구현(들)에 연결(또는 find_callers가
  iface 메서드의 구상 구현 호출자도 포함). 일반 기능(PR 무관).
- **검증**: `find_callers("GetAnzeonTipCap")`가 `ValidateTransactionWithState`(+ Pending 경로)를 반환.

---

**한 줄 요약**: 계기를 먼저 믿을 수 있게 만들고(**E**), 그 위에서 좋은 입력(**c·C**)을 갖춰 **본 실행(d)으로
thesis를 증명**한다. cks측 검색품질(B/D-2)은 동시 세션과 병행 가능한 곁가지.
**(2026-06-19) Tier 1 아키텍처 구현 완료 + 라이브 검증으로 입력 민감도 발견 → 공정 입력 원칙·항목 11 추가.**
**(2026-06-22) MCP 재연결 트랙 완료(재빌드·DB검증·config배선·재연결) + 항목 11·12 단독 라이브 검증 통과(공정입력→PRIMARY 정답 도달). 다음=항목 2 (d) full pipeline 라이브. 통합뷰: [`WORKLIST.md`](./WORKLIST.md).**
