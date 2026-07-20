# go-stablenet 자동개발 파이프라인 — 후속 작업 계획 (검토/더블체크용)

> **상태:** 계획만 수립됨. 사용자가 항목별로 "시작" 요청 시에만 착수.
> **진행 순서:** 권장 실행 순서 준수.
> **제외:** **G(go-stablenet fix 브랜치 PR/리뷰 조율)는 수행하지 않음.**
> 작성 시점: 2026-06-10. 다른 세션의 추가 작업을 반영해 방향 더블체크가 목적.

> ### 🔄 재검토 갱신 (2026-06-12) — read-only, 코드 변경 없음
> 동시 세션이 빠르게 진행 중이라 이 계획의 여러 가정이 바뀌었음. 핵심 델타:
> - **인덱스 이동**: `@9978930` → go-stablenet `dev c051d50b` (ckg-eval 리포트 기준). 설정 경로도 `data/ckv-stablenet`로 변경. 아래 모든 수치는 **시점 측정치**(이미 또 달라졌을 수 있음).
> - **검색 수치 변동**: SN line-recall **0.60 → 0.70**(개선), KO **0.71 → 0.57**(⚠️ **회귀** — D 참조).
> - **A(find_callers)**: 관련 커밋 착수됐으나(cks #12 `4a5fabd`, ckg #17 `a3260e6`) **bare 심볼은 여전히 0 hits** → **미해결**.
> - **B(intent)**: 동시 세션이 임베딩 기반 분류기로 **재작성**(`1dc4325`, `fcd0365` threshold 0.6) → 소유 이전, 정상분류 검증 필요.
> - **D/테스트노이즈**: 처리됨(cks `265d71a` production>test, `55b2072` exclude_tests) — **그러나 KO 회귀를 유발**(신규 항목 D-2).
> - **F(thesis)**: 검색-레벨 측정이 대폭 진행됨 (cks `RetrievalTrace`/`ComposeTraced` + coding-agent CKG eval 하네스 #9 + **Report v5**: α=grep/β/γ/δ=get_for_task, 30Q). 단 이는 *retrieval* 비교이지 *전체 파이프라인(implement+chainbench)* 비교가 아님.
> - 각 항목 본문의 **「현재(2026-06-12)」** 주석으로 상세 반영.

---

## 0. 컨텍스트 (다른 세션 검토 기준점)

시스템: **coding-agent**(LLM 파이프라인) + **cks/ckv/ckg**(결정론적 retrieval) + **chainbench**(로컬 e2e), 대상 = **go-stablenet**.
인덱스: ~~go-stablenet `@9978930`~~ → **`dev c051d50b`로 재빌드됨**(2026-06-12, ckg-eval 리포트 기준), 설정 경로 `data/ckv-stablenet`.

### 이번 세션에서 이미 완료된 것 (검토 시 반영 여부 확인)

- **cks retrieval 수정**: `get_for_task` **0/10 → line-overlap 0.60 / file-level 0.80** (한국어 0.71).
  - 방법: ckv 시맨틱을 stage2 RRF 융합 + 복합 키워드 생성 + glossary 배선 + `CkvWeight=5.0`.
  - cks 커밋: `180b5f5`(fuse ckv+compound), `8e741e3`(CkvWeight 5.0), `ad6f12c`(glossary/setup), `674d06e`(KO scenarios).
  - eval 하네스(신규): `eval/scenarios-stablenet/SN01-10`, `eval/scenarios-stablenet-ko/KO*`.
- **txpool 버그 발견·수정**: `legacypool.truncatePending`의 두 `list.Cap` 루프가 `subFeePayerObligation` 누락 → `feePayerSpent` drift(over-count) → 풀 포화 시 FD tx 오탐 거부(DoS 방어가 작동해야 할 바로 그 순간).
  - 수정 + **B-1 invariant backstop**(`validatePoolInternals` 재계산-비교).
  - 브랜치 `fix/txpool-cumulative-balance-fee-delegation @ 920ec4320` (로컬, **미푸시**). 베이스 `545c902e3`,`e67a48afc`.
- **파이프라인 가드레일(coding-agent)**: planner **§5.2b**(파생상태 write-site 전수열거 + co-location/invariant), evaluator **§4.6**(파생상태 일관성 게이트). 버전 0.1.9/0.1.10(HEAD `94fcbe2`). jira fix `bf9c0e1`.
- **재검증**: 0.1.10 planner가 같은 txpool 태스크에서 §5.2b를 스스로 적용 → **Cap 포함 write-site 전수열거 + lazy-on-read 설계로 버그 클래스 구조 제거**. 증거: `.coding-agent/tickets/RETEST-20260609_043021/design-v1.md`.

---

## 1. 진행 규칙

- 시작은 사용자가 **항목별로 명시 요청**할 때만.
- 권장 실행 순서: **A·B → C → E → F → D/H**.
- **G는 수행하지 않음.**
- A/C는 동시 세션이 활발히 수정 중인 영역 → 단독 진행 전 역할분담 확인.

---

## 2. 작업 항목

### Tier 0 — 하드닝 (방금 만든 것을 단단히)

#### B. intent 분류 항상 빈값/below-threshold 수정 — *소유: cks/나, 충돌위험 낮음*
- **증거**: `composer.intent_classified`에서 `intent=""`, `confidence≈0.39`, `below_threshold=true` 관측(세션 초반). 착수 시 재확인 필요.
- **영향**: composer stage2 symbol-kind 필터 + stage3 relation 필터가 전부 비활성("unknown intent" 광역모드). 잔여 recall 갭의 유력 근본원인.
- **범위**: `internal/composer/intent/`(classifier.go, anchors.go, embedder.go) 임계값·앵커 점검.
- **검증**: SN/KO eval에서 intent 분류율↑ + recall 변화 측정.
- **🔄 현재(2026-06-12)**: 동시 세션이 **임베딩 기반 vibe-prompt 분류기로 재작성**(`1dc4325` B.2) + `DefaultUnknownThreshold` 0.6 상향(`fcd0365` B.2.1). → **소유가 동시 세션으로 이전됨**. 실제 정상분류 여부는 아직 미검증(footprint 비어 확인 불가). 또한 **B는 D와 결합됨**: `demoteTests := intent != IntentTestAdd` 이므로 intent가 TestAdd를 못 맞히면 test-add 태스크에서 테스트가 잘못 강등됨.

#### A. ckg find_callers go-심볼(qualified-name) 해석 실패 — *소유: ckg, 동시 세션 조율 필수*
- **증거**: RETEST `analysis.md` — `find_callers(ValidateTransactionWithState / ExistingExpenditure)` "graph returned empty (qualified-name miss in ckg's go layer)" → planner가 grep으로 fallback.
- **영향**: §5.2b 가드레일의 전제(graph로 write-site 전수열거)가 깨짐. 부지런한 모델만 grep fallback으로 구제됨.
- **범위**: ckg go layer의 qname 인덱싱/해석(suffix-resolve는 `feb4788`에서 일부 개선 — 그 이후 상태 확인).
- **검증**: `find_callers("ValidateTransactionWithState" / "subTotalCost")` 비-empty 반환.
- **🔄 현재(2026-06-12)**: 관련 커밋 착수됨 — cks `4a5fabd`(#12 over-qualified FQN 해결), ckg `a3260e6`(#17 go static call 한정). **그러나 실측상 bare 심볼 find_callers는 여전히 0 hits**(QuorumSize / ValidateTransactionWithState / subTotalCost). → **미해결**. qualified-name 형태(`pkg.Type.Method`)를 요구할 가능성 — planner가 bare 이름으로 호출하면 여전히 grep fallback. **여전히 열림**.

### Tier 1 — 검증 뚫기

#### C. chainbench 회귀 환경 정비 — *소유: chainbench(외부/동시)*
- **증거**: bash 4+ 필요(`mapfile`; brew bash 5 설치 완료) + python eth-* 설치 완료. 잔여:
  1. `get_running_node_ids` 미정의 → `basic/txpool-propagation`, `basic/wbft-consensus` 실패(exit 127).
  2. `default` 프로파일이 a2-* 회귀 sender EOA 미펀딩 → "insufficient funds balance 0"로 대부분 실패(표준 per-tx 검사, 우리 코드 무관). `a2-06-insufficient-funds`·`basic/tx-send`은 PASS.
  3. `profile list`엔 WKRC("v2 회귀 환경")가 보이나 `profiles/WKRC.yaml` 부재.
- **영향**: 진짜 런타임 e2e/회귀 스위트 미실행 → 검증 신뢰도 + **F의 정확성 축 측정 전제**.
- **검증**: a2-* 회귀 스위트가 펀딩된 프로파일에서 실제 통과/실패 신호를 냄.

#### E. evaluator §4.6 게이트 직접 검증 — *소유: 나, 저비용*
- **증거**: RETEST에선 planner가 maintained 파생상태를 회피(lazy-on-read)해 §4.6 미발화.
- **범위**: "maintained 집계 추가 + invariant 테스트 없음" 가상 diff에 evaluator를 태워 FAIL→bug cycle 나는지 확인.

### Tier 2 — 본 thesis

#### F. 3-way A/B/C 벤치 (cks vs code-only vs code+skills) — *소유: bench 하네스*
- **의의**: "cks가 grep보다 정확·저렴한가" — 프로젝트 미증명 핵심 질문(`/coding-agent:bench`).
- **의존**: C(정확성 측정), 입력 품질은 A·B로 개선.
- **검증**: 동일 태스크 N건에서 correctness/tokens/cost/latency/safety 비교표.
- **🔄 현재(2026-06-12)**: **검색-레벨 측정은 대폭 진행됨**. cks `RetrievalTrace`(`fd136cf`)/`ComposeTraced`(`78c4905`)로 composer-retrieval vs LLM-agent-retrieval를 동형 비교 가능. coding-agent **CKG eval 하네스**(#9 `5f9b183`) + **Report v5**: α=grep/β=full-dump/γ=incremental/δ=get_for_task(glossary 확장), 30Q×3run, 메트릭(answer-present / answer-focus / relevance-precision / design-sufficiency / tokens·efficiency / test-pollution), glossary가 δ answer-present **83→97%**. → **단, 이는 retrieval 비교**. F의 본래 정의(implement+chainbench까지 포함한 전체 파이프라인 A/B/C)는 **여전히 미실행**(C에 의존). 문서는 둘을 구분해야 함: ✅retrieval-thesis(거의 측정됨) vs ⏳full-pipeline-thesis(대기).

### Tier 3 — 잔여

#### D. retrieval 잔여 recall — *소유: ckv/cks*
- **증거**: SN line-miss = sn06(gas price 완전), sn07(blacklist 완전), sn04(commit.go 맞으나 handleCommitMsg vs commitWBFT), sn10(genesis 맞으나 함수 어긋남). file-level 진짜 miss는 sn06/sn07.
- 일부는 B(intent)로 흡수 가능, 나머지는 임베딩/청킹(contextual retrieval) 한계.
- **🔄 현재(2026-06-12)**: **테스트노이즈는 처리됨** — cks `265d71a`(production>test 랭킹, `results(cap, demoteTests)`) + `55b2072`(exclude_tests filter + shared test-path classifier). SN recall 0.60→**0.70** 개선.

#### D-2. (신규) production-over-test 랭킹의 KO 회귀 — *소유: cks, 신규 발견*
- **증거**: D의 test-demotion이 SN(+0.10)엔 도움됐으나 **KO recall 0.71→0.57 회귀** — `ko01-quorum`, `ko04-commit`가 새로 MISS(2026-06-12 실측).
- **가설**: production-over-test 강등 또는 glossary 확장 상호작용이 한국어 시나리오에서 정답을 밀어냄. 원래 플랜에 없던 항목.
- **검증**: KO 시나리오에서 demoteTests on/off 비교 + glossary 확장 영향 분리 측정.

#### H. 가드레일 일반화·정리 — *소유: 나*
- implementation-invariants backstop 개념 확장(합의 불변식 → 구현 불변식), 메모리/문서 정리.

---

## 3. 실행 순서 (확정)

**A·B(하드닝) → C(e2e 뚫기) → E(가드레일 마감) → F(thesis 측정) → D/H.** (G 제외)

논리: *거의 실패할 뻔한 것(A)·계속 새던 것(B)을 먼저 막고 → 측정 막던 chainbench(C)를 뚫어 → 그 위에서 본 질문(F)을 측정.*

---

## 4. 다른 세션과 더블체크할 포인트

- cks composer 4커밋(`180b5f5`/`8e741e3`/`ad6f12c`/`674d06e`)이 그쪽 작업과 충돌/중복인지, 그 이후 ckgclient 변경(`feb4788`/`ef01c86`/`808d6fa`/`0b97630`)과 정합한지.
- ~~**A(ckg find_callers)**가 이미 그쪽에서 진행/해결됐는지~~ → **부분 진행됨(#12/#17)이나 bare 심볼 여전히 empty** — 해결 책임/방향 확인.
- **D-2(KO 회귀)**: production-over-test 랭킹이 한국어 시나리오를 깨뜨린 것을 그쪽이 인지하는지 — 의도된 트레이드오프인지 버그인지.
- **B(intent 분류기 재작성)**: 임베딩 기반 분류기(`1dc4325`)가 실제로 정상분류하는지, demoteTests 결합 부작용을 인지하는지.
- **C(chainbench WKRC 프로파일/펀딩)** 소유 주체.
- **txpool fix 브랜치(`920ec4320`) 방향 vs 0.1.10 planner가 제안한 "lazy-on-read" 설계** — 둘 중 수렴점(내 수정 = maintained map + Cap 훅 추가, planner 권장 = 유지 안 함).
- coding-agent 0.1.10의 planner completeness 재구성(`94fcbe2`)이 §5.2b를 온전히 포함하는지(retest상 포함 확인됨).

---

## 5. 적용 시 기대 효과 (프로젝트 개선 매핑)

프로젝트 목표(`00-system-contract`): **G1** go-stablenet 구현을 더 정확·효율적으로, **G2** 시간·토큰·인력 절감.
핵심 thesis("cks 검색이 grep보다 정확·저렴")는 현재 **미증명**(이전 N=1 측정은 FakeEmbedder 등으로 confounded).
이 플랜은 그 thesis를 **측정 가능 상태로 끌어올리고**, 측정 입력(검색 품질·부작용 안전성)을 개선한다.

각 효과는 **검증 지표를 동반한 가설**이다(과대선언 아님 — 해당 지표로 확인).

### 5.1 검색 정확도 (retrieval) — "어디를 고칠지 정확히 찾는가" — *기여: B, D, 일부 A*
- 현재(2026-06-12 갱신): `get_for_task` SN line **0.70** / KO line **0.57**(회귀), 테스트노이즈는 처리됨, intent는 동시 세션이 임베딩 분류기로 재작성(검증 대기). ~~이전: line 0.60 / file 0.80~~.
- 적용 후: intent-aware symbol-kind/relation 필터 활성 → 노이즈↓·랭킹↑, 잔여 miss(sn04/06/07/10) 일부 회복.
- 기대 지표: **file recall 0.80 → 0.9+ 목표, line recall 0.60 → 0.7~0.8, precision↑.**
- 프로젝트 효과: planner가 무관 코드를 근거로 설계할 확률↓ → **G1(정확성) 직접 개선**.

### 5.2 부작용 없는 코드 생성 (side-effect 안전) — "고치면서 딴 데를 깨뜨리지 않는가" — *기여: A, E*
- 현재: §5.2b/§4.6 가드레일은 출시됐으나 (i) graph 전수열거가 `find_callers` 실패로 **grep fallback에 의존**(부지런한 모델만 구제), (ii) §4.6 게이트 **미실증**.
- 적용 후: `find_callers` 신뢰 동작 → §5.2b가 **어떤 모델에서도** write-site를 빠짐없이 열거; §4.6 FAIL 동작 실증 → 2차 안전망 보증.
- 기대 지표: **`find_callers` 비-empty 반환**, **§4.6가 maintained-집계-무테스트 diff에 FAIL→bug cycle**.
- 프로젝트 효과: 이번에 발견한 `truncatePending` 류 부작용이 **설계·검증 양 단계에서 모델-독립적으로 차단** → G1·신뢰도 핵심.

### 5.3 검증 신뢰도 (e2e) — "통과했다는 말을 믿을 수 있는가" — *기여: C*
- 현재: chainbench 서브셋만 실행(consensus/tx-send/a2-06 PASS), **전체 tx 회귀 스위트 차단**.
- 적용 후: 펀딩된 회귀 프로파일 + 하네스 버그(`get_running_node_ids`) 수정 → evaluator의 chainbench 단계가 **런타임 회귀를 실제로 검증**.
- 기대 지표: **a2-* 회귀 스위트 실측 통과율**(현재 환경상 미측정 항목들).
- 프로젝트 효과: "EVALUATION PASS"의 신뢰도↑, 그리고 **F(thesis)의 정확성 축 측정 전제 해제**.

### 5.4 thesis 측정 가능성 (전략) — "이 시스템이 값어치를 하는가" — *기여: F (C 이후)*
- 현재: thesis 미증명, A/B/C 비교 미실행.
- 적용 후: 동일 태스크 N건에서 **cks vs grep vs skills의 정확성·토큰·비용·지연·안전성 비교표** → go/no-go 의사결정 데이터.
- 프로젝트 효과: 프로젝트 **존재 이유의 실증** — G1/G2를 숫자로 증명/반증. **사실상 종착점.**

### 5.5 견고성·일반화 — *기여: H*
- 적용 후: invariant-backstop을 **합의 불변식 → 구현 불변식**으로 확장 → txpool뿐 아니라 **모든 태스크 유형**에서 파생상태 부작용 예방.

### 종합 — 프로젝트 상태 전이
- **Before**: 데이터·검색·파이프라인은 동작하나 — thesis 미증명 + 부작용 1건 발견 + e2e 부분 실행 + 가드레일이 grep-fallback에 의존.
- **After**: 검색 품질↑(B/D) + 부작용 안전망이 **모델-독립적으로 신뢰**(A/E) + e2e **실측 가능**(C) → 그 위에서 **thesis를 드디어 측정(F)**.
- **한 줄**: 이 플랜은 프로젝트를 *"동작하지만 미검증"*에서 *"검증 가능하고 안전한, 그리고 가치가 측정된"* 상태로 옮긴다.
