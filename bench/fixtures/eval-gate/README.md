# eval-gate fixtures — evaluator §4.6 게이트 직접 검증 (item E)

evaluator.md §4.6(Derived-state consistency gate)가 실제로 **FAIL→bug cycle**을
발화하는지 실증하기 위한 가상 diff 쌍. go-stablenet을 변경하지 않고, 다른 스테이지
(unit/lint/security/chainbench)는 green으로 가정한 채 §4.6만 격리 검증한다.

| 파일 | 파생상태 | invariant 테스트 | 적대경로 테스트 | 기대 §4.6 |
|---|---|---|---|---|
| `negative.diff` | feePayerSpent (add/sub) | ❌ 없음 | ❌ 없음 | **FAIL** (게이트 발화) |
| `positive.diff` | feePayerSpent (add/sub) | ✅ validatePoolInternals + TestFeePayerSpentInvariant | ✅ TestTruncatePendingReleasesFeePayerObligation | **PASS** |

- 시나리오는 §4.6 rationale이 인용하는 실제 버그(truncatePending이 fee-payer 집계를 누락 →
  feePayerSpent drift)를 본뜬 것.
- 기대 판정: `expected.json`.
- 검증 방법: 실제 `coding-agent:evaluator` 에이전트를 각 diff에 대해 디스패치하되, 다른
  스테이지는 green으로 stipulate하고 §4.6만 적용해 `{gate_triggered, status, finding}`을 받게 한다.
- 결과 기록: `result-2026-06-15.md`.
