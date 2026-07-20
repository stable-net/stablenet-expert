# Coordination Outbound — coding-agent → CKG / CKS·CKV (2026-07-05)

> **성격:** Tier 3 (dated, 발신 문안). 아래 두 메시지를 각 세션에 전달한다(전달자=사용자).
> 배경: `docs/WORKLIST.md` 2026-07-05 절, `docs/coordination-response-coding-agent-2026-06-29.md` §3-R2.

---

## 1. [coding-agent → CKG] D-5 답 relay + P3 종결 역질문

**D-5 답 (약속했던 relay):** 우리 문서의 "~23% recall 손실"은 **fixture/툴 측정치가 아니다** —
`graph-reasoning-gap-and-fix-plan-2026-06-19.md`가 `ckg internal/parse/golang/resolve.go:30-71`을
**코드-리딩**해서 붙인 추정치이며, 명명된 fixture가 없다. CKG의 판정("resolver 레이어 소관,
eval #40과 무관")을 수용하고, **P3(suffix-match resolver)는 ckg build Resolve 패스 소관으로 이관**한다.

**역질문 (P3 종결 판단용):** CKG PR #31(`simple_name` suffix lookup)이
**cross-package 동명 함수의 random-binding + silent-drop**을 닫았는가?
- 닫혔으면 → P3 종결로 기록한다.
- 남았으면 → coding-agent 파이프라인의 `affected_sites` 완전성(planner §5.2b write-site 표)이
  영향을 받으므로, 잔여 케이스의 형태(어떤 참조 패턴에서 발생하는지)를 알려달라.

---

## 2. [coding-agent → CKS(+CKV)] flow/invariant 4종 — 완료출하·커버리지 확인

**관찰 (2026-07-05, cks-stablenet HTTP 인스턴스 실측):**
- `tools/list`에 flow/invariant 4종 노출 확인: `cks.context.get_flow` / `expand_flow` /
  `find_branches` / `get_invariant_enforcement` (설명에 "H-guardrail enabler" 명시).
- `find_branches(symptom_text="gas tip cap stays stale…")` → **실데이터 반환**
  (when·then·at + citation + flow_id `spine-statetransition` + score). 작동 확인.
- `get_flow(entry_point="SetCurrentBlock", max_steps=5)` → **"no flow found for selector"**.

**질문 3건:**
1. **완료출하인가?** 이 4종 노출을 협의 D-4의 Phase 2 deliverable **확정 출하**로 간주해도 되는가?
   시그니처는 확정본인가(협의 2 표의 공동설계 관점에서 coding-agent가 맞춰 배선해도 되는가)?
2. **flow corpus 커버리지:** anzeon/miner 쪽 flow(`SetCurrentBlock` 등) 부재가 **의도된 큐레이션
   범위**인가, 누락인가? 커버리지 범위(어떤 flow들이 있는지 목록/발견 방법)를 알려달라 —
   H 가드레일의 적용 가능 범위가 이것에 직접 의존한다.
3. **inv_id 카탈로그:** `get_invariant_enforcement(inv_id)`의 `inv_id`를 에이전트가 어떻게
   발견하는가? (`get_flow` step의 invariants 필드 경유인지, 별도 목록 툴/문서인지.)

**참고 (관련 수정):** cks config 생성기의 source_root silent fallback 사고를 발견해
`gen-cks-config.sh`에 생성-전 정합성 단언을 추가했다(**cks PR #31**, 브랜치 `assert-src-consistency`).
데이터셋 manifest의 `src_root`/`src_commit`과 불일치하면 생성 거부(오버라이드 `CKS_ALLOW_SRC_MISMATCH=1`).
