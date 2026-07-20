# ADR — Reproduction vs Fix-Validity 분리 + 2-티어 재현 (bugfix 검증 강화)

문서 성격: **ADR / 설계 결정 (ACCEPTED 2026-06-23 — 구현·머지 완료).** 구현: PR #18
(squash → main `a39221d`, plugin v0.1.25). 짝 문서: [`WORKLIST.md`](../WORKLIST.md) ·
스킬 [`plugin/skills/reproduce-first/SKILL.md`](../../plugin/skills/reproduce-first/SKILL.md).

> **상태: ACCEPTED (구현 반영됨).** 명세(.md/.json) 변경으로 파이프라인 동작을 바꾼다. **라이브
> 무회귀(실제 버그픽스 1건으로 e2e 티어 재현 + "GREEN인데 형제경로 미커버" 케이스의 §4.8 FAIL)는
> 미실행** — 잔여 검증 항목으로 §6에 추적.

> **결정 한 줄:** 버그픽스를 **두 개의 독립 판정**으로 평가한다 — ① *재현 판정*(결함이 실제로
> 재현/해소되는가, **필요조건**)과 ② *수정 타당성 판정*(GREEN 위에서 수정이 *타당*한가, **충분조건**)을
> 섞지 않는다. 그리고 재현은 **2-티어**(simulation 인-프로세스 / e2e chainbench 멀티노드)로 수행하며,
> 재현 오라클은 한 티어로 고정한다.

---

## 1. Context (왜)

### 1.1 관찰된 결함 (다른 세션)
재현 테스트가 GREEN인데 **수정이 부당**했던 사례가 관찰됐다. 재현 테스트의 GREEN은 "그 시나리오에서
증상이 멈췄다"만 증명한다 — 다음은 잡지 못한다:
- **증상 마스킹**: 근본 원인(producer edge)이 아니라 하류 캐시를 덮어 테스트만 통과
- **오버핏**: 재현 테스트의 특정 입력만 특수처리
- **형제 경로 누락**: 같은 증상을 내는 다른 경로는 깨진 채 방치
- **회귀**: 그 시나리오만 고치고 다른 곳을 부숨

실제로 evaluator §4.6(파생상태 게이트)은 이미 *"A green unit suite is necessary but NOT
sufficient"* 라고 같은 명제를 쓰고 있었으나, 이 개념이 **흩어져 있고** §4.7이 재현 GREEN을
"correctness spine"이라 부르며 **두 판정을 뭉개고** 있었다.

### 1.2 chainbench 실측 (2-티어의 근거)
chainbench는 **전부 e2e**다 — 모든 테스트가 `tests/<category>/<name>.sh` bash 스크립트이고 멀티노드
체인이 떠 있어야 돈다. 바이너리는 `chainbench_init/start({ binary_path, project_root })`로 주입된다.
"simulation"은 chainbench 안에 없다 → **대상 프로젝트(go-stablenet) 트리의 인-프로세스 Go 테스트**가
그 역할을 한다. 즉 재현 위치가 본질적으로 두 곳이다.

---

## 2. Decision 1 (메인) — 재현 판정 vs 수정 타당성 판정 분리

버그픽스 평가를 **두 개의 독립 verdict**로 나눈다. 절대 하나의 PASS/FAIL로 합치지 않는다.

### 2.1 재현 판정 (necessary) — evaluator §4.7
- `red_confirmed && green_at_head && oracle_unmodified` 모두 참이어야 함. 기계적·이진.
- 재현 테스트의 존재 자체가 필수. 실패 = **"bug not fixed"** → **Analyzer 재진입**(원인 재진단).
- PASS = "증상이 더는 재현 안 됨" — **수정이 타당함을 뜻하지 않는다.**

### 2.2 수정 타당성 판정 (sufficient) — evaluator §4.8
**재현 판정이 PASS일 때만** 평가한다. 입력: analysis.md 근본원인 + `related-code.json.affected_sites`
(analyzer §4.1) + 설계 write-site-contract(planner §5.2b) + diff.

- **기계적 체크 (hard FAIL → 버그 사이클):**
  1. **근본원인-엣지 터치** (anti 증상-마스킹): diff가 `must_fix` 사이트를 실제로 건드렸는가
  2. **형제경로 커버리지** (anti 부분수정): `produces_symptom:true` 사이트가 전부 수정/테스트로 덮였는가 (§4.6을 파생상태 너머로 일반화)
  3. **파생상태 일관성** (§4.6)
  4. **무회귀** (전체 스위트 + `-race`)
- **판단성 체크 (WARN + needs-careful-review, PASS 차단 안 함):**
  5. **오버핏 의심**: diff가 오라클의 리터럴/식별자에 특수분기하거나, 수정 표면이 `must_fix`보다 부자연스럽게 좁음

### 2.3 정책: 하이브리드 (채택)
기계적 항목은 객관적 → **hard FAIL**. 오버핏은 기계적으로 판정 불가 → **WARN + needs-careful-review**로
사람에게 위임.

**기각한 대안:**
- *전부 hard FAIL* — 판단성 항목 오탐으로 버그 사이클 무한루프 위험.
- *전부 flag만* — 자동 차단이 약해 "GREEN이면 통과"의 허점을 다시 남김.

### 2.4 실패 라우팅 분리 (실익)
- 재현 FAIL → Analyzer (원인 자체가 틀림)
- 타당성 FAIL: 증상-마스킹(체크1) → Analyzer / 형제경로·파생상태(체크2·3) → Planner
- analyzer §3b 재진입이 두 verdict를 읽고 분기 → "무엇을 놓쳤나"를 정확히 겨냥.

---

## 3. Decision 2 — 2-티어 재현 (simulation + chainbench e2e)

재현을 **증상을 가장 싸게 잡는 티어**에서 수행한다. 한 버그의 오라클은 **티어 하나**.

| 티어 | 무엇 | 어디 | 언제 |
|---|---|---|---|
| `simulation` | 인-프로세스 Go 테스트 | go-stablenet 트리 | 기본. 빠르고 결정적 |
| `e2e` | chainbench `.sh` (프로젝트-빌드 바이너리, 멀티노드 합의) | chainbench `tests/repro/` | 합의/동기화/P2P/txpool 전파/하드포크 등 멀티노드 증상, 또는 simulation 재현 실패 시 |

- 바이너리는 **분석 대상 프로젝트를 빌드**한 것을 chainbench가 사용 (요구사항).
- e2e repro 테스트는 `tests/repro/<ticket>-<slug>.sh`로 **회귀 누적**(검증되면 `regression/`로 승격 가능).
- `reproduction.json`은 **tier-keyed** 계약. RED/CARRY/GREEN 세 게이트가 두 티어 모두에서 동작
  (evaluator §7.5c가 e2e 오라클용으로 HEAD/parent 바이너리를 재빌드).
- analyzer는 분석 전 과정의 중요 발견을 `findings.log`(append-only)로 남긴다.

---

## 4. Consequences — 구현 위치 (SSoT는 코드)

| 컴포넌트 | 변경 |
|---|---|
| `skills/reproduce-first` | 필요/충분 프레이밍, tier-keyed `reproduction.json`, 세 게이트 티어 분기 |
| `agents/analyzer` | chainbench MCP 툴 배선, §5 2-티어 재현, §4.1 `affected_sites`, `findings.log`, §3b verdict 분기 |
| `agents/evaluator` | §4.7 재현 판정 / §4.8 타당성 판정 / §7.5c e2e 오라클 GREEN, §8 두 verdict 분리 리포트 |
| `agents/implementer` | CARRY 티어 분기, §6.0 사전체크 티어 분기 |
| `agents/planner` | §5.2b 완전성을 `affected_sites`에서 seed |
| `agents/orchestrator` | 디스패치에 `go_stablenet_root`/`analyzer` 명시, PR `needs-careful-review` 연동 |

---

## 5. 의존성 / 한계
- §4.8 체크 ①②는 analyzer가 `affected_sites`를 **성실히 열거**해야 작동 — 빈약하면 게이트가 헐거워진다.
- 오버핏(⑤)은 본질적으로 판단성 → 자동 hard-block 불가. 사람 검토에 위임(needs-careful-review)이 한계선.
- e2e 티어는 `$CHAINBENCH_DIR` + 빌드 가능한 대상 바이너리에 의존. 미충족 시 simulation 티어로 폴백.

## 6. 잔여 검증 (Open)
- 🔴 **라이브 무회귀**: 실제 버그픽스 1건으로 (a) e2e 티어가 프로젝트-빌드 바이너리로 RED→GREEN을 돌리는지,
  (b) "재현 GREEN인데 형제경로 미커버" 케이스에서 §4.8이 hard FAIL을 내고 Planner로 라우팅되는지 관찰.
- ⚪ `affected_sites` 품질을 운영하며 관찰(게이트 실효의 전제).
