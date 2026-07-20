# PR-77 결합 실행 — 에이전트 vs 전문가 유사도 + (d-1) 완주 검증

사용자의 PR-77 테스트와 bench (d-1)을 하나로 묶은 실행. PR-77(Anzeon 동적 가스팁
staleness, go-stablenet #77)을 **부모 커밋에서** 에이전트가 풀게 하고, **전문가(실제 PR)
수정과 얼마나 유사한지** 검토한다. 동시에 bench 하네스가 1셀 완주하는지 검증한다.

## 셋업 (이미 준비됨)
| 요소 | 경로/값 |
|---|---|
| 대상 트리(부모에 체크아웃) | `/Users/.../test/pr-77` @ `0bf2f4d1b` (#75 = PR-77 부모, 버그 실재) |
| PR-77 전용 cks DB | `/Users/.../knowledge-data/pr-77` (ckg+ckv, `cks-pr77.yaml`, source_root=/test/pr-77) |
| 매니페스트 | `bench/manifests/stablenet-pr77.json` |
| 증상-수준 티켓 | `bench/fixtures/tickets/STABLE-0005.json` (해법 미누설) |
| 전문가 정답(비교 기준) | `bench/fixtures/pr77/expert-fix.diff` (= `git diff 0bf2f4d1b 98f05c2a0`, 2파일 23줄) |

## 두 측정 축
1. **기능 정확성** — evaluator(unit/race/lint/security/chainbench `basic/tx-send`) → EVALUATION_PASS 여부.
2. **전문가 유사도** (신규) — 에이전트 diff(`git diff 0bf2f4d1b <agent-HEAD>`) vs `expert-fix.diff` 비교:
   - 결정적: 수정 파일 집합 overlap(전문가 = legacypool.go + anzeon.go), 핵심 심볼 touch 여부(SetCurrentBlock / RemotesBelowTip).
   - 의미적: 동일 근본원인(head 변화 시 GasTip 갱신)·동등 해법인지 LLM 판정.

## 실행 순서
1. (다른 세션) cks MCP를 `cks-pr77.yaml`로 재설정 → 세션 재시작(MCP 리로드). A_cks 전제.
2. autopilot 세션을 `/test/pr-77`에서 기동(implementer 무프롬프트 편집).
3. `/coding-agent:bench bench/manifests/stablenet-pr77.json` → `--continue`로 셀별 진행.
   - B_code_only / C_code_skills는 cks 불필요 → cks 재설정 전에도 실행 가능.
   - A_cks는 pr-77 DB 서빙 확인 후.
4. compare.py 리포트 + 유사도 검토 → A/B/C × {기능정확성, 유사도, 총비용, bug-cycle}.
5. 🔴 종료 후 `/test/pr-77`의 throwaway 브랜치/커밋 정리(데이터셋 오염 방지).

## 주의
- **base = 부모(0bf2f4d1b)**: 트리에 PR-77 fix가 적용돼 있으면 안 됨(현재 HEAD=부모 ✓).
- **PR-77 편향 금지**: 이 한 케이스로 thesis 판정 금지. STABLE-0004/0007 등과 함께 결론낼 것.
- **유사도 자동 스코어러는 미구현**: 현재는 수동/판정 단계. 결정적 overlap 헬퍼는 다음 하네스 증분.
