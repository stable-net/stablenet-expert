# Runbook — coding-agent 재현·검증 동작 확인 (v0.1.26)

문서 성격: **검증 runbook (재사용).** 대상 변경: PR #18(2-티어 재현 + 재현/타당성 verdict 분리),
#19(재현 하드 게이트, v0.1.26), #20(ADR). 짝 문서:
[`adr/ADR-0003-reproduction-and-fix-validity.md`](./adr/ADR-0003-reproduction-and-fix-validity.md).

> **목적:** 별도 세션에서 실제 bugfix 파이프라인을 돌려, 재현이 *강제*되는지 / 게이트가 재현 없이는
> *막는지* / 두 verdict가 *분리*되는지를 **아티팩트 증거로** 판정한다. 명세(.md)만 바뀌었으므로
> 라이브 무회귀로만 실효를 확인할 수 있다.

## 사용법
아래 §"검증 프롬프트"를 그대로 복사해, **실제 파이프라인을 돌리는 다른 세션**에 붙여넣는다.
그 세션이 정해진 시나리오로 돌린 뒤 아티팩트를 증거로 판정·보고한다. (이 세션/문서에서는 실행하지 않는다.)

## 가장 중요한 단일 질문
> 이번 bugfix가 **재현 테스트를 실제로 작성·실행·RED 확인 없이** 진행될 수 있었는가?
> (있었다면 #19 게이트 실패.) — §검증 프롬프트 2-C 반례 테스트가 이 질문의 직접 검증이다.

---

## 검증 프롬프트 (복사해서 다른 세션에 붙여넣기)

````markdown
# coding-agent v0.1.26 재현·검증 동작 모니터링

너는 이 세션에서 coding-agent 파이프라인을 **실제 bugfix 티켓 1건**으로 돌리면서, 최근
main에 머지된 세 가지 변경이 실제로 동작하는지 관찰·분석·보고하는 역할이다. 코드를 고치지
말고, 정해진 시나리오로 돌린 뒤 **아티팩트를 증거로** 판정만 한다.

## 0. 검증 대상 (무엇이 바뀌었나)
- **#19 재현 하드 게이트 (v0.1.26)**: `ticket_type=="bugfix"`이면 `ANALYSIS→PLANNING` 전이가
  `reproduction.json` + `reproduction_confirmed==true` + `red_confirmed==true` 없이는
  TRANSITION_BLOCKED. (이전엔 prose "MUST"뿐이라 재현을 통째로 스킵해도 통과됐음 — 이게 핵심 버그.)
- **#18 2-티어 재현**: simulation(인-프로세스 Go) / e2e(프로젝트-빌드 바이너리로 chainbench
  멀티노드). 오라클은 한 티어. e2e repro는 `$CHAINBENCH_DIR/tests/repro/*.sh`로 누적.
- **#18 두 verdict**: evaluator가 재현 판정(§4.7, 필요)과 수정 타당성 판정(§4.8, 충분)을 분리.

## 1. 사전 확인
1. 설치된 플러그인 버전이 **0.1.26**인지 확인(`.claude-plugin/plugin.json`). 아니면 재설치·재시작.
2. 검증용 티켓 선정: **재현 가능한 실제 버그** 1건(가능하면 멀티노드/합의/txpool 같은 e2e성 1건 +
   단일프로세스 1건, 두 케이스면 더 좋음). 티켓 ID와 증상을 기록.
3. 워크스페이스 경로(`workspace_dir`)를 확보 — 모든 증거는 여기 아티팩트에서 읽는다.

## 2. 스테이지별 관찰 체크리스트 (각 항목 = state.json/아티팩트 실측)

### A. 분류 (가장 먼저, 게이트 적용 여부를 가른다)
- [ ] `state.json` 최상위 `ticket_type` == `"bugfix"` 인가?
      → `feature`로 오분류면 재현은 정당히 스킵된다. 이 경우 **버그 분류 오류**로 별도 보고(게이트와 무관).

### B. ANALYSIS — 재현이 실제로 일어났는가 (이번 수정의 핵심)
- [ ] `analysis.md` 에 `## Root cause` + `## Affected sites` 존재.
- [ ] `related-code.json.affected_sites` 가 구조화되어 채워짐(`produces_symptom`/`must_fix` 포함).
- [ ] `findings.log` 가 존재하고 분석 과정의 발견이 시간순으로 append 됨(빈 파일/누락이면 결함).
- [ ] `reproduction.json` 존재. `tier` 값 확인(`simulation` | `e2e`).
- [ ] `reproduction.json.red_confirmed == true` + `red_output`에 실제 실패 로그.
- [ ] `state.json.states.ANALYSIS.reproduction_confirmed == true`.
- [ ] **실제 테스트 파일이 생성됐는가**:
      - simulation: go-stablenet 트리에 `TestReproduce_*` (uncommitted) 존재.
      - e2e: `$CHAINBENCH_DIR/tests/repro/<ticket>-<slug>.sh` 존재 + `reproduction.json.chainbench_test*` 기록.
- [ ] e2e면: 분석 대상 프로젝트를 **빌드한 바이너리**로 chainbench가 돌았는지
      (`binary_build_cmd`, 노드 기동 로그, `chainbench_*` 호출 흔적) 확인.

### C. 게이트 강제 검증 (음성 시나리오 — 가장 중요)
- [ ] 정상 흐름에서 ANALYSIS→PLANNING 전이가 **reproduction.json이 있을 때만** 성공했는가.
- [ ] (가능하면) **반례 테스트**: reproduction 없이 전이를 시도하면 `TRANSITION_BLOCKED`(missing에
      "bugfix requires a reproduction test confirmed RED")가 나오는가. 예: 의도적으로 reproduction.json을
      비우거나 `reproduction_confirmed=false`로 두고 transition 호출 → 반드시 BLOCK 되어야 함.
      (이게 통과해버리면 게이트가 무력 — 즉시 결함 보고.)

### D. EVALUATION — 두 verdict가 분리되는가
- [ ] `test-report.md` 에 **"Bugfix verdicts"** 섹션이 있고 두 줄로 분리 표기:
      - Reproduction (§4.7, necessary) = PASS/FAIL
      - Fix validity (§4.8, sufficient) = PASS/WARN/FAIL
- [ ] `state.json.states.EVALUATION.results` 에 `reproduction_verdict`, `fix_validity_verdict`,
      `needs_careful_review` 가 채워짐.
- [ ] `reproduction.json` 에 `green_confirmed`/`green_at_head`/`red_at_parent` 채워짐(수정 후).
- [ ] (실익 검증) 만약 수정이 형제경로를 안 덮으면 §4.8이 hard FAIL을 내고 **Planner로** 라우팅,
      오버핏 의심이면 WARN + needs-careful-review 로만 표기(PASS 차단 안 함)인가.
- [ ] e2e 오라클이면 §7.5c가 HEAD 바이너리로 GREEN, parent 바이너리로 RED 재확인했는가.

## 3. 합격/불합격 신호
- **합격**: B의 재현 아티팩트가 모두 실측되고, C의 게이트가 reproduction 없이는 막으며, D의 두
  verdict가 분리 표기된다. → 원래 버그("테스트 없이 재현 확인 스킵")가 닫혔다.
- **불합격 신호(즉시 보고)**:
  - reproduction.json/테스트 파일 없이 PLANNING 이후 단계로 진행됨 → **게이트 미작동**.
  - `ticket_type`이 bugfix인데 reproduction_confirmed=false인 채 전이 성공.
  - findings.log/affected_sites 누락.
  - test-report에 두 verdict가 한 줄로 뭉개져 있음.

## 4. 보고 형식 (이 형식으로 회신)
```
## 검증 결과 — {ticket_id} (plugin {version})
- 분류: ticket_type={...}  (gate 적용 대상? yes/no)
- 재현: tier={simulation|e2e}, red_confirmed={...}, 테스트 파일={경로}, e2e 바이너리 빌드={yes/no}
- 게이트: 정상 전이={조건 충족시에만 통과? yes/no}, 반례 BLOCK 확인={yes/no/untested}
- verdict: reproduction={...}, fix_validity={...}, needs_careful_review={...}, 라우팅={...}
- findings.log/affected_sites: {ok/누락}
- 판정: 합격 / 불합격(사유)
- 첨부 증거: {state.json 발췌, reproduction.json, test-report.md "Bugfix verdicts" 섹션, findings.log tail}
```

핵심: **추론하지 말고 아티팩트로 증명**한다. 각 체크 항목은 파일 실측(경로+발췌)으로 뒷받침할 것.
가장 중요한 단일 질문 — "이번 bugfix가 재현 테스트를 실제로 작성·실행·RED 확인 없이 진행될 수
있었는가? (있었다면 게이트 실패)"
````

---

## 참고 — 검증이 보는 아티팩트/마커 (SSoT는 코드)
| 위치 | 항목 |
|---|---|
| `state.json` | `ticket_type`, `states.ANALYSIS.reproduction_confirmed`, `states.IMPLEMENTATION.reproduction_commit`, `states.EVALUATION.results.{reproduction_verdict,fix_validity_verdict,needs_careful_review}` |
| `reproduction.json` | `tier`, `red_confirmed`, `green_confirmed`, `green_at_head`, `red_at_parent`, `fix_validity_verdict`, `validity_findings`, (e2e) `chainbench_test*`,`binary_build_cmd`,`profile`,`preconditions` |
| `related-code.json` | `affected_sites[]` (`produces_symptom`,`must_fix`,`role`) |
| `findings.log` | 분석 과정 append-only 저널 |
| `test-report.md` | "Bugfix verdicts" 섹션 (재현/타당성 2행) |
| 전이 게이트 | state-machine §2.3 `ANALYSIS → PLANNING` (bugfix 재현 HARD gate) |
| evaluator | §4.7 재현 판정 / §4.8 타당성 판정 / §7.5c e2e 오라클 GREEN |
