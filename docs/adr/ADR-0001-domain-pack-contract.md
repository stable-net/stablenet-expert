# ADR — Domain-Pack Contract (coding-agent multi-project extension, overlay P1)

문서 성격: **ADR / 설계 결정 (ACCEPTED 2026-06-22 — 설계 합의됨, 코드 변경 0).** 2026-06-19~22
오버레이 작업의 P1. 짝 문서: [`coding-agent-overlay-improvements-and-eval-2026-06-22.md`](../archive/coding-agent-overlay-improvements-and-eval-2026-06-22.md) Part B(스케치) · [`WORKLIST.md`](../WORKLIST.md) 스트림6.

> **상태: ACCEPTED (설계만).** §8 결정 4건 모두 확정. **구현(Phase 1~3)은 교란·대형이라 별도
> 세션/승인 게이트 유지** — 이 문서 승인이 곧 구현 착수 승인은 아니다. Phase 1은 fcore-baseline
> 무회귀로 §3 메커니즘 신뢰성을 라이브 확인하며 진행.
>
> **구현 상태 갱신 (코드 검증 2026-06-28):** 구현됨. `plugins/stablenet-core-dev/domains/go-stablenet/`에
> `domain-pack.json`·`context.md`·`invariants.md` 존재 — 위 "설계만/코드 변경 0"은 작성 시점 기준.

> **결정 한 줄:** go-stablenet 전용 콘텐츠를 **선언적 도메인팩**으로 분리하고, 제너릭 에이전트가
> `state.json.project_id`로 활성 팩을 **런타임 `Read`로 해석**하게 한다. frontmatter는 정적
> 제너릭 로더 스킬 하나만 참조 — Claude Code가 frontmatter 간접참조를 막기 때문(P3에서 확인).
> go-stablenet은 계약의 첫 인스턴스(레퍼런스). 목표: **"새 프로젝트 = 팩 1개 추가, 코어 0 편집".**

---

## 1. Context (왜)

### 1.1 현재 결합 (grep 검증, 2026-06-22)

| 결합 지점 | 현재 (정적/이름) | 위치 |
|---|---|---|
| 불변식 L3 백스톱 | `stablenet-invariants` 스킬을 frontmatter + 본문에서 호명 | analyzer/planner/evaluator/bench-analyzer-skills |
| 경로→모듈 분류·복잡도 | `stablenet-context.classify_domain/estimate_complexity` | analyzer §3.3 / planner §237 |
| 통합검증 스테이지 | chainbench(35회) + `build/bin/gstable`·`go test`·`go -C` 인라인 | evaluator §2/§4/§7 |
| 지식 인덱스 | 단일 `STABLENET_KNOWLEDGE_CONFIG` | .mcp.json |
| 티켓 네임스페이스 | `STABLE-*` 가정 | template-parse / work.md |

### 1.2 의도 (재확인)

이 분리는 **결함이 아니라 다중 프로젝트 확장을 위한 *미완성 이음새***다(오버레이 문서 §P1 재프레이밍).
현재 경계가 **이름 기반 정적 바인딩**이라 새 프로젝트 추가 시 코어 에이전트를 편집해야 한다.

### 1.3 결정적 제약 (P3에서 배움)

Claude Code frontmatter는 **런타임 간접참조 불가**(`${VAR}`·중앙config 미지원). 따라서
`skills: [stablenet-invariants]`를 `${ACTIVE_PACK}`로 바꿀 수 없다. **이 제약이 해법을 규정한다.**

### 1.4 이미 유리한 사실 (grep)

- **도메인 *지식*은 이미 stablenet-knowledge에 위임됨** — stablenet-context는 "지식은 stablenet-knowledge 라이브 위임"이라 선언,
  analyzer/planner는 "권위는 stablenet-knowledge `guidance.*`/`policy/stablenet.yaml`, 하드코딩 아님"이라 명시.
  하드코딩으로 남은 건 **검색-독립 invariants 백스톱(L3)** + 경로분류 데이터뿐.
- **런타임 데이터 로딩 선례 존재** — `state-machine` 스킬은 state.json을 런타임 Read/Write,
  `stablenet-context`는 stablenet-knowledge를 라이브 호출. → "스킬이 런타임에 데이터를 로드"는 검증된 패턴.

---

## 2. Decision 1 — 도메인팩 계약 (`domain-pack.json`)

프로젝트별 `plugins/stablenet-core-dev/domains/<project_id>/` 디렉터리 + 선언적 매니페스트. 코어가 요구하는 **확장점**을
계약으로 고정:

```jsonc
// plugins/stablenet-core-dev/domains/go-stablenet/domain-pack.json
{
  "project_id": "go-stablenet",
  "ticket_namespace": "STABLE",                  // template-parse / work.md
  "repo_root_env": "GO_STABLENET_ROOT",          // 또는 bench manifest의 go_stablenet_root
  "knowledge": { "stablenet_knowledge_config_env": "STABLENET_KNOWLEDGE_CONFIG" },// 프로젝트별 stablenet-knowledge 인덱스(지식은 여기 + 백스톱)
  "context_classifier": "context.md",            // 경로→모듈 데이터 (전 stablenet-context의 데이터부)
  "invariants": "invariants.md",                 // 검색-독립 L3 백스톱 (전 stablenet-invariants)
  "build":     { "cmd": "go build ./...", "artifact": "build/bin/gstable" },
  "unit_test": { "runner": "go", "run_tmpl": "go test -run '{name}' ./{pkg}/...",
                 "race_tmpl": "go test -race {pkgs}" },
  "verification_stages": [                        // evaluator가 순회 (chainbench = 그중 mcp 항목)
    { "id": "unit",  "kind": "builtin:unit_race" },
    { "id": "lint",  "kind": "builtin:lint" },
    { "id": "sec",   "kind": "builtin:gosec" },
    { "id": "integ", "kind": "mcp:chainbench", "profile": "default",
      "oracle_enum": ["basic/tx-send", "basic/consensus"] }
  ]
}
```

새 프로젝트가 제공해야 할 것: 자기 stablenet-knowledge 인덱스 + `invariants.md`(백스톱) + `context.md`(경로분류) +
build/test/verification 명령. **지식 대부분은 그 프로젝트의 stablenet-knowledge 인덱스가 들고**, 팩은 *검색-독립
백스톱 + 분류 데이터 + 실행 명령*만 담는다.

---

## 3. Decision 2 — 활성 팩 해석 메커니즘 (frontmatter 한계 우회)

P3 제약(frontmatter 정적) 때문에 **정적 frontmatter + 동적 Read**로 푼다:

1. 에이전트 frontmatter는 **제너릭 로더 스킬 `domain-pack` 하나만** 정적으로 참조
   (`stablenet-context`·`stablenet-invariants` 호명을 대체). 이름 고정이라 frontmatter 한계 무관.
2. `domain-pack` 로더 스킬(제너릭)이 런타임에 *지시*한다:
   ```
   project_id = state.json.project_id
   pack = Read(plugins/stablenet-core-dev/domains/{project_id}/domain-pack.json)
   invariants = Read(plugins/stablenet-core-dev/domains/{project_id}/{pack.invariants})      # L3 백스톱
   classifier = Read(plugins/stablenet-core-dev/domains/{project_id}/{pack.context_classifier})
   → 에이전트는 classify_domain / estimate_complexity / invariants-backstop 를
     "활성 팩" 소스로 수행 (기존 stablenet-context.* 호출의 일반화)
   ```
3. **검증된 feasibility**: `Read`는 동적이라(frontmatter `model:`과 달리) 막히지 않는다.
   선례 — state-machine은 state.json을 런타임 Read, stablenet-context는 stablenet-knowledge 라이브 호출(§1.4).

> 핵심 분리: **절차(path로 분류하는 *방법*, 불변식을 백스톱으로 *적용하는 법*)는 제너릭 로더에,
> 데이터(모듈 목록, 11개 불변식 본문)는 per-pack 파일에.** 절차 generic / 데이터 per-pack.

대안 검토(기각): 별칭식 단순화는 model 핀(P3)에선 됐지만, 도메인 지식은 "값 하나"가 아니라
*문서·표·규칙 집합*이라 별칭으로 표현 불가 → 로더+Read가 유일하게 성립하는 길.

### 3.1 Feasibility — in-plugin 증거 (단정 아님)

"이게 정말 되나?"의 정직한 답: **새 하베스 기능에 의존하지 않는다.** 메커니즘은 둘만 쓴다 —
(1) frontmatter가 *정적* 스킬 이름 하나를 로드(모든 스킬이 이렇게 로드됨, bedrock), (2) 에이전트가
스킬 지시에 따라 *데이터-의존 경로를 런타임 `Read`*. 둘 다 기존 기능.

**플러그인 안 증거** (`skills/stablenet-context/SKILL.md` 정독): 스킬은 마크다운 지시문이고
`classify_domain(...)`은 "절차:"로 적힌 프로즈(함수 디스패치 없음). 이 스킬은 이미 — "심볼 경로를
모르면 stablenet-knowledge `find_symbol`로 *런타임 조회*해 규칙 적용"(§3.1), "도메인 지식은 stablenet-knowledge 라이브 +
`…/go-stablenet/entries/*.yaml`(*계산된 경로*)에서"(§1)라고 지시한다. 즉 **스킬이 런타임에
데이터-의존 조회·파일 참조를 지시하는 패턴이 이미 작동 중**. `domain-pack` 로더는 동일 패턴.

**P3와의 결정적 차이**: P3의 `frontmatter ${VAR}`는 하베스 미지원 → *진짜 불가능*이었다. 여기엔
그런 미지원 기능이 없다 — "에이전트가 지시대로 파일 Read"는 가장 기본 능력.

**정직한 한계**: 라이브 에이전트로 *끝까지 돌려본 건 아니다* → "검증 완료"라곤 안 한다. 남은 리스크는
*능력*(됨)이 아니라 *프롬프트 신뢰성*(매 런 지시 준수)이며, 완전 증명은 Phase 1 라이브(§7-3)에서.
즉 리스크가 **"불가능" → "Phase 1에서 확인할 신뢰성"** 으로 내려갔다.

---

## 4. Decision 3 — generic vs pack 재분류

| 분류 | 구성요소 | 이동? |
|---|---|---|
| **Generic 골격(불변)** | state-machine, reproduce-first, root-cause-lifecycle, investigative-probe, pr-sanitize, template-parse(파서), orchestrator FSM | 그대로 |
| **Generic 로더(신규)** | `domain-pack` 스킬 — 활성 팩 해석 + classify/complexity/invariants 절차 | 신규 |
| **Pack 데이터(치환)** | `invariants.md`(11 WBFT 규칙), `context.md`(모듈 목록), build/test/verification 명령, stablenet_knowledge_config_env, ticket_namespace | `domains/go-stablenet/`로 |

---

## 5. Decision 4 — verification_stages 일반화 (최대 난이도)

evaluator는 chainbench·Go 툴체인·repo 레이아웃이 §2/§4/§7에 35곳 인라인(grep). 일반화:

- evaluator를 **`verification_stages[]` 데이터 주도 루프**로: 각 stage를 `kind`로 분기
  (`builtin:unit_race`/`builtin:lint`/`builtin:gosec`/`mcp:chainbench`). chainbench는 `mcp:` 한 인스턴스.
- `go build`/`go test`/`build/bin/gstable`/`go_stablenet_root`를 팩의 `build`/`unit_test`/`repo_root`로 치환.
- §4.6 파생상태 게이트·§4.7 reproduce-first 게이트는 **generic 유지**(언어 무관 — diff·테스트 기반).
- ⚠️ 이게 P1에서 가장 무겁고 위험한 부분 → Phase 2 후반, 무회귀 락 하에.

---

## 6. 마이그레이션 계획 (이 ADR가 규정하는 순서)

| Phase | 내용 | 교란? | 게이트 |
|---|---|---|---|
| **0 (이 ADR)** | 계약·메커니즘·재분류 합의 | ✗ | — |
| **1 무리팩터 이동** | `stablenet-*` 콘텐츠 → `domains/go-stablenet/{invariants,context}.md` + `domain-pack.json`. `domain-pack` 로더 스킬 신설. 에이전트는 *아직* 활성 팩=go-stablenet 고정. **동작 불변.** | ✗ | overlay-gates + (타세션) bench 무회귀 |
| **2 일반화** | 에이전트 frontmatter `stablenet-*` 호명 → `domain-pack`. 본문 `stablenet-context.*` → 로더 해석. evaluator stage 데이터화(§5). state.json에 `project_id`. | ✓ | **fcore-baseline 대비 stablenet bench 무회귀** |
| **3 Project A 검증** | go-stablenet 무회귀 + 코어 grep-clean 검증 (Project B는 안 만듦, §7) | ✗ | 수용 테스트(§7) |

> 원칙: **무리팩터 이동 → 무회귀 락 → 일반화 → 신규 프로젝트로 계약 누수 검출.**
> Phase 1·2·3은 별도 세션/승인하에(대공사·교란). **이 ADR는 Phase 0만.**

---

## 7. 수용/평가 (Project A 검증으로 재정의 — Q4 결정)

Project B를 새로 만들지 않는다(없는 것을 위해 부담 X). 대신 **있는 프로젝트(go-stablenet=A)에서
리팩터가 (i) 동작을 보존하고 (ii) 코어에 도메인 결합을 남기지 않음**을 증명한다 — 이 둘이면
"새 프로젝트 = 팩 추가뿐"이 *구조적으로* 따라온다(코어에 프로젝트명이 없으므로).

1. **무회귀 (행위 보존)**: 리팩터 후 go-stablenet 파이프라인이 `fcore-baseline` 대비 동등 —
   overlay-gates 통과 + (타세션) bench 정확성·토큰 노이즈밴드 이내.
2. **구조적 확장성 증명 (grep, 라이브 불필요)**: 추출 후 코어(`plugin/agents/*.md` + generic 스킬
   7종)에 "stablenet"·도메인 용어 **0건**. 도메인 콘텐츠는 전부 `plugins/stablenet-core-dev/domains/go-stablenet/`.
   → "코어 편집 없이 새 팩만 추가 가능"이 *부재로* 증명됨(B 없이).
3. **메커니즘 신뢰성 (§3.1)**: Phase 1 라이브 런에서 로더가 활성 팩을 실제로 해석·적용하는지
   확인(= 무회귀가 곧 신뢰성 증명).
4. **하네스화**: 위 1·2를 결정론적으로 검증하는 게이트(grep-clean 체크 + 무회귀 비교)를
   overlay-gates에 추가.

> Project B(합성/실재)를 통한 라이브 확장 검증은 *나중 별도 단계*로 미룬다 — P1 게이트엔 불필요.

---

## 8. Decisions (모두 확정, 2026-06-22)

1. **§3 로더 메커니즘** — ✅ **승인.** 미지원 하베스 기능 의존 없음(§3.1 in-plugin 증거:
   stablenet-context가 이미 런타임 데이터-의존 Read/stablenet-knowledge 호출을 지시) → 능력 확실. 신뢰성은
   Phase 1 라이브 무회귀가 검증(안전망). "불가능"이 아니라 "Phase 1에서 확인할 신뢰성".
2. **첫 추출 범위** — ✅ **invariants + context만** (chainbench 일반화는 Phase 2로 분리).
3. **`domains/` 위치** — ✅ **`plugins/stablenet-core-dev/domains/`** (CC 마켓플레이스 설치는 플러그인 디렉터리만 복사 →
   repo-level은 설치 시 안 따라옴).
4. **Project B** — ✅ **만들지 않음.** Project A(go-stablenet) 무회귀 + 코어 grep-clean으로 검증(§7).

---

## 9. Consequences / Risks

- **+**: 새 프로젝트가 코어 편집 없이 추가됨. 도메인 지식이 한곳(pack + 그 프로젝트 stablenet-knowledge)으로 모임.
- **+**: chainbench가 `mcp:` 스테이지로 일반화되어 다른 통합 하네스도 끼울 수 있음.
- **−/위험**: Phase 2 evaluator 일반화가 광범위 — 무회귀 락(fcore-baseline) 필수. 단계 분리로 완화.
- **−**: 로더 스킬이 매 런 pack 파일을 Read(소량 토큰). 무시 가능 수준.
- **전제**: go-stablenet은 첫 인스턴스로 *그대로 동작* 유지가 모든 Phase의 통과 조건.
