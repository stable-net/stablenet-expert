# go-stablenet 자동개발 파이프라인 — 기대 결과 (Expected Outcomes)

> **짝 문서:** [`followup-plan.md`](./followup-plan.md) (작업 항목·우선순위·실행 순서).
> 이 문서는 그 플랜을 적용했을 때 **무엇이 얼마나 개선되는가**를 baseline 수치에 앵커링해 정리한다.
> 모든 기대치는 **검증 지표를 동반한 가설**이다(과대선언 아님 — 해당 지표로 확인).
> 작성: 2026-06-10. G 항목은 플랜에서 제외(여기에도 미포함).

> ### 🔄 재검토 갱신 (2026-06-12) — read-only
> 동시 세션 작업으로 baseline이 이동함. 핵심: 인덱스 `@9978930`→`dev c051d50b`, 설정 `data/ckv-stablenet`. 검색 수치 SN **0.60→0.70**, KO **0.71→0.57(회귀)**. A(find_callers)는 커밋 있었으나 bare 심볼 여전히 empty(미해결). B(intent)는 동시 세션이 임베딩 분류기로 재작성(검증 대기). D/테스트노이즈는 처리됐으나 KO 회귀 유발. F는 검색-레벨 측정 대폭 진행(Report v5). 아래 §1 표와 §2 항목에 **「2026-06-12」**로 반영. 모든 수치는 시점 측정치.

---

## 0. 한 줄 요약

검색 품질↑(B/D) + 부작용 안전망의 **모델-독립적 신뢰**(A/E) + e2e **실측 가능**(C)을 갖춘 뒤, 그 위에서 프로젝트의 핵심 thesis를 **드디어 측정(F)**한다. → 프로젝트를 *"동작하지만 미검증"* 에서 *"검증 가능하고 안전하며 가치가 측정된"* 상태로 이동.

---

## 1. 현재 baseline (개선의 기준점, 측정치)

| 영역 | 지표 | 작성 시(06-10) | **재검토(06-12)** |
|---|---|---|---|
| 검색 (영어) | `get_for_task` line-overlap recall | 0.60 (6/10) | **0.70** (개선) |
| 검색 (한국어) | line-overlap recall (KO) | 0.71 (5/7) | **0.57 ⚠️회귀** (ko01·ko04 새 MISS) |
| 검색 | intent 분류 | 비활성(`intent=""`) | **임베딩 분류기로 재작성**(`1dc4325`, threshold 0.6) — 정상분류 검증 대기 |
| 검색 | 테스트파일 노이즈 | 미처리 | **처리됨** (cks `265d71a`/`55b2072`) |
| 안전 가드레일 | planner §5.2b write-site 열거 | grep fallback 의존 | **여전히 grep fallback** — bare 심볼 find_callers 0 hits |
| 안전 가드레일 | evaluator §4.6 게이트 | 미실증 | 변화 없음(미실증) |
| e2e | chainbench | 서브셋 PASS, 회귀 차단 | 변화 없음 |
| thesis (retrieval) | α/β/γ/δ 측정 | 미실행 | **대폭 진행** (CKG eval Report v5: 30Q, glossary answer-present 83→97%) |
| thesis (full pipeline) | implement+chainbench A/B/C | 미실행 | **여전히 미실행** (C에 의존) |
| 인덱스 | 기준 commit | `@9978930` | **`dev c051d50b`**, 경로 `data/ckv-stablenet` |

---

## 2. 항목별 기대 결과

각 항목: **현재 → 적용 후(기대) → 확인 지표 → 리스크**.

### B. intent 분류 수정 *(Tier 0)*
- 현재: 항상 `unknown` 광역모드 → symbol-kind/relation 필터 미적용, 테스트파일 노이즈.
- 기대: intent-aware 필터 활성 → 노이즈↓, 랭킹↑, 잔여 miss(sn04/06/07/10) 일부 회복.
- 확인 지표: **file recall 0.80 → 0.9+ 목표, line recall 0.60 → 0.7~0.8, precision↑**, intent 분류 성공률↑.
- 리스크: 일부 miss는 intent가 아니라 임베딩 한계(D) → 부분 회복에 그칠 수 있음.
- **🔄 현재(06-12)**: 동시 세션이 **임베딩 기반 분류기로 재작성**(`1dc4325`, threshold 0.6 `fcd0365`) → 소유 이전, 정상분류 미검증. `demoteTests := intent != TestAdd` 결합 → intent가 틀리면 test-add 태스크에서 테스트 잘못 강등.

### A. ckg find_callers go-심볼 해석 *(Tier 0)*
- 현재: 가드레일이 grep fallback에 의존(부지런한 모델만 구제).
- 기대: graph 전수열거가 **어떤 모델에서도** 신뢰 동작 → §5.2b가 write-site를 빠짐없이 열거.
- 확인 지표: **`find_callers("ValidateTransactionWithState"/"subTotalCost")` 비-empty**.
- 리스크: 동시 세션의 ckg 작업과 중복/충돌 — 착수 전 역할분담 필요.
- **🔄 현재(06-12)**: 관련 커밋 착수(cks #12 `4a5fabd`, ckg #17 `a3260e6`) — **그러나 bare 심볼 실측 여전히 0 hits → 미해결**(qualified-name 형태 필요 가능성).

### C. chainbench 회귀 환경 정비 *(Tier 1)*
- 현재: 서브셋만 실행, 전체 tx 회귀 차단(하네스 버그 + 미펀딩 프로파일).
- 기대: 펀딩 프로파일 + `get_running_node_ids` 수정 → evaluator chainbench 단계가 런타임 회귀를 실제 검증.
- 확인 지표: **a2-* 회귀 스위트가 펀딩 프로파일에서 실측 통과/실패 신호**.
- 리스크: chainbench 소유(외부/동시) — WKRC 프로파일/펀딩 주체 확인 필요.

### E. evaluator §4.6 게이트 직접 검증 *(Tier 1)*
- 현재: 미실증(planner가 maintained 파생상태를 회피해 미발화).
- 기대: maintained-집계-무테스트 diff에 **FAIL→bug cycle** 실증 → 2차 안전망 보증.
- 확인 지표: **§4.6가 해당 가상 diff에 FAIL**.
- 리스크: 게이트의 탐지 휴리스틱이 과탐/미탐 → 임계 조정 필요할 수 있음.

### F. 3-way A/B/C 벤치 *(Tier 2, C 이후)*
- 현재: thesis 미증명.
- 기대: 동일 태스크 N건에서 cks vs grep vs skills의 **정확성·토큰·비용·지연·안전성 비교표** → go/no-go 데이터.
- 확인 지표: **N≥3 태스크의 A/B/C 정량 비교 + 통계적으로 의미 있는 차이(또는 무차이)**.
- 리스크: 결과가 thesis를 **반증**할 수도 있음(=그 자체로 가치 있는 결론). C 미완 시 정확성 축 측정 불가.
- **🔄 현재(06-12)**: **retrieval-레벨은 거의 측정됨** — cks `RetrievalTrace`/`ComposeTraced` + coding-agent CKG eval 하네스(#9) + **Report v5**(α=grep/β/γ/δ=get_for_task, 30Q, answer-present/relevance-precision/test-pollution, glossary 83→97%). **전체 파이프라인(implement+chainbench) A/B/C는 여전히 미실행**(C 의존). 둘을 구분할 것.

### D. retrieval 잔여 recall *(Tier 3)*
- 기대: 임베딩/청킹(contextual retrieval) 개선으로 sn06/sn07 회복, line 정밀도↑.
- 확인 지표: **file recall → 0.9+ 상향, line recall → 0.8 접근**.
- 리스크: 임베딩 품질은 수확 체감 — 큰 비용 대비 작은 이득 가능.
- **🔄 현재(06-12)**: 테스트노이즈는 처리됨(cks `265d71a`/`55b2072`) → SN +0.10. **신규 부작용 D-2: KO 회귀 0.71→0.57**(ko01-quorum·ko04-commit 새 MISS) — production-over-test 랭킹/glossary 상호작용 의심. demoteTests on/off + glossary 분리 측정 필요.

### H. 가드레일 일반화·정리 *(Tier 3)*
- 기대: invariant-backstop을 합의 불변식 → 구현 불변식으로 확장 → 전 태스크 유형 부작용 예방.
- 확인 지표: 신규 derived-state 태스크에서 §5.2b/§4.6 자동 적용.

---

## 3. 차원별 Before → After

| 프로젝트 차원 | Before | After | 기여 |
|---|---|---|---|
| ① 검색 정확도 | line 0.60 / file 0.80, intent 비활성 | file 0.9+, line 0.7~0.8, 노이즈↓ | B, D, 일부 A |
| ② 부작용 안전 | 가드레일 출시했으나 grep fallback 의존, §4.6 미실증 | write-site 열거 모델-독립 신뢰 + 2차 게이트 실증 | A, E |
| ③ 검증 신뢰도(e2e) | chainbench 서브셋만 | 전체 tx 회귀 런타임 실측 | C |
| ④ thesis 측정 | 미증명, 비교 없음 | A/B/C 정량 비교 → go/no-go | F (C 이후) |
| ⑤ 견고성·일반화 | 합의 불변식만 backstop | 구현 불변식까지 → 전 태스크 예방 | H |

---

## 4. 전체 플랜 완료 시 성공 기준 (Definition of Done)

- [ ] `get_for_task` file recall ≥ 0.9, line recall ≥ 0.7 (SN), 한국어도 동등 수준.
- [ ] intent 분류가 대표 쿼리에서 정상 분류(비-empty, above-threshold) 동작.
- [ ] `find_callers`가 go 심볼에 대해 비-empty 반환 → §5.2b가 grep fallback 없이 성립.
- [ ] evaluator §4.6가 maintained-파생상태-무테스트 diff에 FAIL.
- [ ] chainbench 전체 tx 회귀 스위트가 펀딩 프로파일에서 실측(통과/실패가 환경이 아닌 코드 신호).
- [ ] 3-way A/B/C 벤치 N≥3 태스크 비교표 산출 → thesis에 대한 **증명 또는 반증** 결론.

---

## 5. 가정·리스크 (기대 결과를 무효화할 수 있는 요인)

- **동시 세션 충돌**: A(ckg)·C(chainbench)는 다른 세션이 활발히 수정 중 → 방향이 이미 바뀌었을 수 있음(이 문서 검토 목적).
- **인덱스 정합**: ckv/ckg가 go-stablenet `@9978930` 기준 — 코드가 이동하면 일부 수치/groundtruth 재측정 필요(일부 파일 `fd22f7f` 부분 reindex 관측).
- **intent ≠ 만능**: 잔여 miss 일부는 intent가 아니라 임베딩 한계 → B만으로 0.9 미달 가능.
- **thesis 반증 가능성**: F가 "cks가 grep 대비 이득 없음"을 보일 수 있음 — 이는 실패가 아니라 의사결정 데이터.
- **chainbench 외부성**: 환경 정비(C)가 chainbench 소유 범위 밖이면 우리 통제 밖.

---

## 6. 상태 전이 종합

- **Before**: 데이터·검색·파이프라인은 동작하나 — thesis 미증명 + 부작용 1건 발견 + e2e 부분 실행 + 가드레일 grep-fallback 의존.
- **After**: 검색 품질↑(B/D) + 부작용 안전망 모델-독립 신뢰(A/E) + e2e 실측 가능(C) → 그 위에서 **thesis를 측정(F)**.
- **한 줄**: 이 플랜은 프로젝트를 *"동작하지만 미검증"* 에서 *"검증 가능하고 안전한, 그리고 가치가 측정된"* 상태로 옮긴다.
