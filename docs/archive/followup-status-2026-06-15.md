# go-stablenet 자동개발 파이프라인 — 후속 작업 상태 갱신 (2026-06-15)

> **짝 문서:** [`./archive/followup-plan.md`](./archive/followup-plan.md)(작업 항목·우선순위), [`./archive/followup-expected-outcomes.md`](./archive/followup-expected-outcomes.md)(기대 결과).
> 두 짝 문서는 **2026-06-12 시점**에 멈춰 있다. 이 문서는 그 뒤 동시 세션 진행분을
> **코드·커밋·라이브 인덱스와 직접 대조**해 갱신한 것이다. (검토 작성: 2026-06-15)
> 인덱스: go-stablenet `dev c051d50b` (라이브 cks MCP `fresh:true` 확인), 경로 `data/{ckg,ckv}-stablenet`.

---

## 0. 한 줄 요약

입력 품질 쪽(**A 해결**, B 진전, ckg PR-history 86%)은 짝 문서가 비관적으로 적은 것보다 좋아졌다.
남은 진짜 작업은 두 갈래 — **(1) C로 chainbench 회귀 환경을 뚫고, (2) F의 bug-cycle "총비용" 루프를 구현해
full-pipeline thesis를 측정**하는 것. E/D-2/H는 저비용 곁가지.

---

## 1. 짝 문서 대비 갱신된 사실 (실측 대조)

| 항목 | 문서(06-12) 기록 | **실측(06-15)** | 근거 |
|---|---|---|---|
| **A. find_callers** | ❌ bare 심볼 0 hits, "여전히 열림" | ✅ **해결됨** — `find_callers("ValidateTransactionWithState")`·`("subTotalCost")` 둘 다 caller 반환(라이브 MCP) | ckg #17 `a3260e6`(static call qualify) + **#21 `1a9698c`(canonical symbol)** |
| ckg PR-history | (별개) | ✅ 57%→**86%**, func-verify 완료 | ckg #18, `eval/stablenet/func-verify/Report-A-recall-fix-results.md` |
| **B. intent** | "임베딩 분류기로 재작성, 검증 대기" | ⏩ **더 진행** — stage2 intent-aware BM25 라우팅(`f7bf2d8`), stage3 그래프 확장기(`bc0fc86`), eval 9시나리오/7intent(`8faa621`), per-intent metrics(`053ae66`), 글로서리 키워드 확장 라이브 동작 확인 | cks main 머지 |
| **F (retrieval-thesis)** | "Report v5 (4-way)" | ⏩ **v8까지 진행** — 5-way(δ 하이브리드 vs ε 그래프단독), 30Q×3run, 글로서리 answer-present 83→97% | `bench/ckg-eval/Report.md`, 커밋 `e4b2209`·`166b18a` |
| **F (full-pipeline-thesis)** | "C에 의존, 미실행" | ❌ **여전히 미실행 — 핵심 미완** | §2.1 |
| **C. chainbench** | 하네스 버그 + 미펀딩 | 🟢 **재평가: 거의 안 막힘** — `regression.yaml` 신설(senders 펀딩 완료), `WKRC`는 코인심볼(프로파일 아님, 오독). 벤치 oracle `basic/{consensus,tx-send}`는 `get_running_node_ids` 미사용 → **F 정확성 축 비차단**. 잔여: 그 helper 미정의로 4개 비-oracle 스크립트만 exit 127 + binary_path 타머신 | 06-15 read-only 검증 |
| **D-2. KO 회귀** | 0.71→0.57 | ⚠️ **미해소 추정** — 라이브 ko-quorum 쿼리가 QuorumSize 함수를 깔끔히 못 집음 | `get_for_task` 실측 |
| **txpool fix** | 로컬·미푸시 | ❌ 그대로 — `920ec4320`(3커밋) **dev 미머지·미푸시** | `git branch --merged dev` |
| **coding-agent** | 0.1.10, 가드레일 출시 | 불변 — **0.1.10**, §4.6(E) 여전히 미실증 | `plugin.json`, SKILL grep |

**가장 중요한 재구성**: cks의 06-12 핸드오프(`code-knowledge-system/docs/HANDOFF-cks-evaluation-remaining.md`)가
F를 정밀하게 다시 정의했다 — 벤치 하네스 **골격은 있으나 핵심(bug-cycle 누적 = "옳은 수정까지의 총비용" 측정)이 미구현**.
실측 확인: `bench-orchestration/SKILL.md`에 bug-cycle 루프 0건, `bench/compare.py`에 총비용/cycle/side-effect 지표 0건,
매니페스트 단일(`stablenet-abc-phase1`), end-to-end 완주 이력 0.

---

## 2. 정리된 남은 작업 리스트 (우선순위순)

### ✅ 닫힌 항목 (문서엔 열림으로 표기됐으나 해결)
- **A — ckg find_callers bare 심볼 해석**: 해결. 남은 것은 §5.2b 가드레일이 실제 planner 경로에서 grep fallback 없이 성립하는지 **1회 재검증**(저비용).
- **ckg PR-history recall**: 완료(86%, func-verify 종결).

### 🔴 Tier 1 — 진짜 병목 (핵심 경로)

**F-core. full-pipeline A/B/C 벤치 "총비용" 측정** — *소유: 나/bench 하네스* (cks 핸드오프 §5.1) — **진행: §2.5 참조**
- (a) ✅ bug-cycle 루프 — `bench-orchestration/SKILL.md` §4.4 step e(orchestrator §5 포팅, 모드별 planner 유지).
- (b) ✅ `bench/lib/{collect,report}.py`에 `bug_cycles`/`side_effect_failures`(+ `total_tokens`/`final_correctness` 노출) 컬럼 + 테스트(14/14).
- (c) ◐ `stablenet-abc-phase3.json`로 6개 모듈 태스크 추가(systemcontracts/Anzeon/state/chainconfig/params-hardfork/fee-policy). 남은 것: 인덱스 drift 태스크는 재빌드 고려, oracle live 검증.
- (d) ⏳ **1셀 end-to-end 완주(현재 0건)** → 전체 실행 → compare.py. autopilot+승인 필요(미실행).
- **확인 지표**: N≥3 태스크 A/B/C 정량 비교(총비용·bug-cycle·side-effect·정확성) → thesis 증명/반증.

**C. chainbench 회귀 환경 정비** — 🟢 **상태확인 완료(06-15): (d)의 블로커 아님** (§1 표 C행 참조)
- ✅ `regression.yaml` 신설(senders TEST_ACC_A~E 펀딩), `WKRC`는 코인심볼(프로파일 아님, 06-12 오독).
- ✅ 벤치 oracle `basic/{consensus,tx-send}`는 `get_running_node_ids` 미사용 → 정확성 축 비차단.
- ❌ 잔여(chainbench 소유): `get_running_node_ids` 미정의로 4개 비-oracle 스크립트 exit 127; regression.yaml binary_path 타머신(런타임 override로 우회).

### 🟡 Tier 2 — 하드닝·검증

**E. evaluator §4.6 게이트 직접 검증** — ✅ **완료(2026-06-15)**
- negative.diff(테스트 없음)→FAIL, positive.diff(invariant+적대경로)→PASS, 기대치 100% 일치 → §4.6 실증.
- 산출물: `bench/fixtures/eval-gate/`. 검증: 실제 evaluator 에이전트 2회(go-stablenet 변경 0).

**B-검증. intent 정상분류 + demoteTests 결합 부작용** — *소유: cks*
- 분류기 코드는 진행됐으나 SN/KO eval에서 **분류율↑·recall 변화 측정 미완**.
- `demoteTests := intent != IntentTestAdd` 결합 → intent가 TestAdd를 못 맞히면 test-add 태스크에서 테스트 오강등. 부작용 확인 필요.

**txpool fix 브랜치 처리** — *플랜의 G(PR 조율)는 명시 제외 대상이므로 방향 결정만*
- `920ec4320`(`545c902e3`→`e67a48afc`→`920ec4320`, 3커밋) **dev 미머지·미푸시** 상태.
- 0.1.10 planner의 "lazy-on-read" 설계 vs 내 수정(maintained map + Cap 훅) 수렴점 정리.

### 🟢 Tier 3 — 잔여

**D-2. KO recall 회귀(0.71→0.57)** — *소유: cks, 신규 발견*
- demoteTests on/off + 글로서리 확장 영향 **분리 측정**. ko01-quorum·ko04-commit MISS 원인 규명(production-over-test 강등 vs 글로서리 상호작용).

**D. SN 잔여 miss** — *소유: ckv/cks*
- sn06(gas price), sn07(blacklist) file-level 진짜 miss. 임베딩/청킹(contextual retrieval) 한계 영역 — 수확체감.

**H. 가드레일 일반화·정리** — *소유: 나*
- invariant-backstop을 합의 불변식 → **구현 불변식**으로 확장 → 전 태스크 유형 부작용 예방. 메모리/문서 정리.

---

## 2.5 F-core 착수 진행 (2026-06-15, 이 세션) — 코드 랜딩

다른 세션 프롬프트("cks A/B/C 벤치 하네스 완성")를 **검열 후** 반영. 검열 핵심: 프롬프트가 (b)에서
신규 4컬럼을 요구하나 실측상 `final_correctness`(=`RunResult.correct`)·`total_tokens`(transcript Σ로
자연 누적)는 **이미 존재** → 진짜 신규는 `bug_cycles` 1개, `side_effect`는 **정의 재정립** 필요(공유
evaluator라 "적발"은 모드무관 → "회귀-클래스 실패 수, 낮을수록 좋음"으로 조작화).

| 작업 | 상태 | 산출물 |
|---|---|---|
| **(a)** bug-cycle 재진입 루프 | ✅ 랜딩 | `bench-orchestration/SKILL.md` §4.4 step e 재구성(orchestrator §5 포팅, 모드별 planner 유지), §2 manifest `config.max_eval_cycles`, §3 state `bug_cycles` |
| **(b)** compare.py 총비용 회계 | ✅ 랜딩+테스트 | `bench/lib/collect.py`(`bug_cycles`/`side_effect_failures` from failure_log), `report.py`(rollup·per-task·CSV 컬럼), `test_report.py` 신규 테스트 — **14/14 통과** |
| **(c)** 태스크 다양화 | ◐ 대부분완료 | `manifest.schema.json`(`module`/`base_commit`/`config`), `STABLE-0003`(txpool) + **`STABLE-0004~0009`(systemcontracts·Anzeon·state·chainconfig·params-hardfork·fee-policy, 실제 PR base_commit)**, `stablenet-abc-phase{2,3}.json`. base_commit 6개 go-stablenet 실재 검증. 남은 것: 인덱스 drift 태스크 재빌드·oracle live 검증 |
| **(d)** end-to-end 완주 | ⏳ dry만 | 매니페스트 스키마검증·tickets CLEAN·collect→report 경로 통과. **본 실행은 autopilot+승인 필요(미실행)** |

**E(별도). evaluator §4.6 게이트** ✅ **실증 완료** — `bench/fixtures/eval-gate/`(negative→FAIL, positive→PASS, 기대 100% 일치).

**남은 F-core 작업**:
- (c) 인덱스 drift: base가 dev에서 먼 태스크(#68/#58/#14)는 해당 base_commit에 cks 재빌드 고려; clean(#83/#77/#73) 1차 실행 권장.
- (d) autopilot 세션에서 clean 태스크 1셀 완주 → 전체 실행 → compare.py 판정. **데이터셋 오염 방지 정리 필수(§4.1).**

---

## 3. 권장 실행 순서 (갱신)

원 플랜은 **A·B → C → E → F → D/H**였으나 A 해결 + E·C·F-core(a/b/c) 완료로 갱신:

**~~A~~✅ ~~E~~✅ ~~C 확인~~✅ ~~F-core(a/b/c)~~✅ → (d) clean 태스크 1셀 완주 → 전체 실행 → D-2/H.**
> 다음 단계 = (d) 본 실행(autopilot+승인). 상세 체크리스트는 [`remaining-work-detail.md`](./remaining-work-detail.md).

논리: A는 닫혔고 B는 동시 세션 소유로 진전 중 → 내가 단독으로 값을 낼 수 있는 건 **E(즉시)**와
**F-core 하네스 구현**. C는 외부 소유라 주체 확인하며 병렬로 밀고, C가 뚫리는 시점에 F의 정확성 축이 완성된다.

---

## 4. 운영 주의 (cks 핸드오프 §6 — 반드시 숙지)

1. **데이터셋 오염 방지(最重要)**: 벤치는 go-stablenet에 throwaway 브랜치/커밋 생성 → **반드시 정리**. 안 하면 다음 ckg 재빌드 때 가짜 코드·커밋 유입(2026-06-09 실제 발생). 정리: 캐노니컬 브랜치 checkout → `git branch -D <테스트브랜치>` → `git reflog expire --expire-unreachable=now --all && git gc --prune=now`.
2. **재빌드 반영 = 세션 재시작**: 라이브 cks MCP가 새 graph를 서빙하려면 `/reload-plugins` 아닌 **세션 재시작**(`exit`→`claude --continue`). `ops.freshness`는 인메모리 staleness 못 잡음.
3. **무프롬프트 실행**: implementer의 go-stablenet 편집을 무프롬프트로 돌리려면 autopilot 런처 `code-knowledge-system/scripts/coding-agent.sh`로 go-stablenet에서 세션 기동(다른 디렉터리 세션은 편집 권한 프롬프트로 멈춤).
4. **무게**: A/B/C 벤치 = 모드 3 × 태스크 N × 전체 파이프라인 × bug-cycle → 비용 큼. batch + checkpoint/resume(`/coding-agent:bench ... --continue`).

---

## 5. 핵심 경로 레퍼런스

- 벤치 하네스: `plugin/skills/bench-orchestration/SKILL.md`, `plugin/commands/bench.md`, `plugin/agents/bench-planner-{codeonly,skills}.md`, `bench/compare.py`, `bench/manifests/`
- retrieval thesis 산출물: `bench/ckg-eval/Report.md`(v8), `bench/ckg-eval/queries.json`
- cks 핸드오프(F 재정의): `code-knowledge-system/docs/HANDOFF-cks-evaluation-remaining.md`
- ckg find_callers 검증: `code-knowledge-graph/eval/stablenet/func-verify/`
- txpool fix: go-stablenet `fix/txpool-cumulative-balance-fee-delegation @ 920ec4320`(로컬)
- 데이터셋: `code-knowledge-system/data/{ckg,ckv}-stablenet/`, config `code-knowledge-system/cks-stablenet.yaml`
