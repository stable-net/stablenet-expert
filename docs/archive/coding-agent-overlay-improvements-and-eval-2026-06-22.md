# coding-agent 오버레이 개선점 · 도메인팩 확장 · 평가전략 (2026-06-22)

문서 성격: **분석 + 제안 (status/proposal, 미구현)**. 구현 전 근거·합의·평가설계용.
근거: `plugin/` 전체 인벤토리(agent 6 · skill 9 · command 9 · hook 3 · MCP 3) 직접 정독 +
"Claude Code → coding-agent 화" 오버레이 관점 진단.
짝 문서: [`harness-improvement-proposals-2026-06-17.md`](./harness-improvement-proposals-2026-06-17.md)(훅·자율성 결정론화) ·
[`WORKLIST.md`](./WORKLIST.md)(SSoT).

> **요약.** coding-agent는 Claude Code를 *범용 대화형 에이전트 → 결정론적 FSM 자동개발
> 파이프라인*으로 고정하는 4-레이어 오버레이다(커맨드 진입 · 권한 잘린 서브에이전트 ·
> SOP 스킬 · 훅). 골격은 견고하다. 개선 여지는 **6건**으로 수렴한다. 그중 **P1(도메인팩
> 계약)**이 중심 — 도메인 하드코딩을 골격에서 분리한 본래 의도(*다중 프로젝트 확장*)는
> 옳았으나, 경계가 아직 **이름 기반 정적 바인딩**이라 새 프로젝트 추가 시 코어 편집을
> 강요한다. 본 문서는 (A) 6개 개선점을 *왜 → 무엇 → 어떻게 검증* 3단으로, (B) P1을
> 도메인팩 계약으로 재설계, (C) 기존 bench 하네스를 A/B 기판으로 쓰는 통합 평가
> 프레임워크를 제시한다. 모든 평가는 **사전등록 가설 + 반증조건 + 변수격리**를 갖춘다.**

---

## Part 0. 오버레이 현황 (개선점의 공통 전제)

"덮어쓰기"는 한 군데가 아니라 4-레이어로 일어난다:

| 레이어 | 무엇을 덮어쓰나 | 강제 수단 |
|---|---|---|
| 커맨드 | 자유 대화 → 고정 진입점 9개 | `commands/*.md` |
| 서브에이전트 | "무엇이든 하는 Claude" → 단일 책임 | frontmatter **tool grant 절단** |
| 스킬(SOP) | 즉흥 추론 → 강제 규율(red→green, root-cause, 불변식) | `skills/*/SKILL.md` |
| 훅 | 자유 Write/Bash → 문서가드·커밋로그·전사기록 | `hooks/*` (fail-open) |

핵심: 역할 분리가 *프롬프트 권고*가 아니라 *도구 권한*으로 박혀 있다(analyzer/planner는
코드 수정 불가, implementer만 프로덕션 편집, evaluator만 chainbench). 이 강제력이 강점인
동시에, 확장(P1)과 검증(Part C)을 어렵게 만드는 경직성의 근원이기도 하다.

---

## Part A. 개선점 6건 — 왜 / 무엇 / 어떻게 검증

각 항목은 **근거(왜) · 변경 스케치(무엇) · 평가전략(가설·지표·반증조건)**으로 구성한다.
평가전략의 공통 기판·원칙은 Part C 참조.

### P0 — 에이전트 간 계약을 산문에서 기계검증으로

**왜.** 파이프라인의 가장 약한 이음새는 `planner → implementer → evaluator`의 **계약이
마크다운 산문**이라는 점이다. 두 곳이 특히 취약하다:
- planner가 만든 **파생상태 write-site 표**(planner.md §5.2b: 모든 변이 지점 × 유지동작)를
  implementer가 *명시적으로 대조하는 단계가 없다* — "설계를 따르라"뿐. 표의 한 행 누락은
  evaluator의 테스트가 약하면 그대로 통과(false-GREEN)한다.
- implementer가 plan.md를 `## Step N` 휴리스틱으로 파싱(implementer.md §4.2). planner가
  헤딩 포맷을 어기면 *조용히* 일부 스텝을 누락한다.

산문 규칙은 모델이 흘릴 수 있으나, 구조화 + 기계검증은 못 흘린다(fail-closed).

**무엇.**
1. plan/design 산출물에 **구조화 스키마** 추가 — plan은 `steps[]`(id·desc·files·verify),
   design은 `write_site_table[]`(site·action·covered_by_test)을 마크다운이 아닌
   프런트매터/JSON 블록으로 동반 출력.
2. implementer에 **표 대조 체크리스트** 단계: 모든 `write_site_table[].site`에 대해 해당
   변이를 구현했는지 자가확인 → 미구현 행은 failure_log + Orchestrator 에스컬레이션.
3. evaluator §4.6 게이트를 **표 기반**으로 강화: 선언된 모든 site가 테스트(consistency
   invariant + adversarial path)로 커버되는지 검증(현재는 invariant/adversarial 테스트의
   *존재*만 확인, 표 대비 *완전성*은 미확인).

**어떻게 검증 (평가전략).**
- **변형(mutant) 코퍼스.** 다중-site 파생상태를 건드리는 bugfix/feature 티켓 N개를 고르고
  (txpool eviction·집계 카운터 등), planner 출력에 *고의로 한 행을 누락*한 변형을 주입.
- **가설 H0.** 개선 후 implementer/evaluator의 **누락-행 탐지율**이 개선 전보다 높다.
- **지표.** ① write-site 누락 탐지율(=FAIL로 잡힌 비율), ② false-GREEN율(eval PASS인데
  expert oracle diff 대비 site 누락), ③ plan.md 포맷 변형 코퍼스에 대한 **무성 파싱실패율**.
- **반증조건.** 개선 후 false-GREEN율이 개선 전과 통계적으로 동일하면 P0 실패(산문→구조화가
  실효 없음).
- **기판.** `bench/fixtures` + expert `reference_fix` diff(bench-orchestration이 이미 지원).

---

### P1 — 도메인 하드코딩을 "이름 바인딩"에서 "도메인팩 계약"으로 (중심 항목 → Part B 상세)

**왜 (의도 재확인).** stablenet 전용 내용(`stablenet-context`/`stablenet-invariants` 스킬,
chainbench 스테이지, `build/bin/gstable`, `go test -run`, `STABLE-*` 티켓)을 골격에서
분리한 것은 **다중 프로젝트 확장을 위한 의도된 설계**였다. 그러나 현재 경계는 **이름 기반
정적 바인딩**이다:
- 코어 에이전트 frontmatter가 `skills: [stablenet-invariants, stablenet-context]`를 직접 호명.
- evaluator가 chainbench Stage와 `build/bin/gstable` 경로를 본문에 인라인.
- state.json·CKS_CONFIG·CHAINBENCH_DIR이 *단일 프로젝트*를 가정.

⇒ **프로젝트 B를 추가하려면 코어 에이전트를 편집**해야 한다. 분리는 했지만 *치환 가능*하지
않다. "결함"이 아니라 **확장 설계의 미완성(implicit seam)**이다.

**무엇 (요지, 전체는 Part B).** `project_id`로 선택되는 **선언적 도메인팩 계약**을 도입.
코어 에이전트는 `stablenet-*`를 호명하는 대신 *"활성 도메인팩의 invariants / context-classifier
/ verification-stages / build·test 명령 / cks 인덱스 / integration harness"*를 **해석(resolve)**한다.
go-stablenet은 그 계약의 **레퍼런스 인스턴스**가 된다.

**어떻게 검증 (평가전략 — 결정적 테스트).**
- **수용 테스트 (이진).** 비-stablenet 소형 프로젝트(다른 Go 서비스 또는 다른 언어) "Project B"의
  도메인팩을 작성하고 `/coding-agent:analyze`를 완주 → PR 생성. 성공조건:
  `git diff plugin/agents/*.md plugin/skills/{generic 7종}` == **빈 diff** (오직 도메인팩 +
  설정만 추가됨).
- **무회귀 테스트 (필수).** 리팩터 *후* 기존 go-stablenet 3-way bench를 재실행 → 정확성·토큰이
  리팩터 전 대비 노이즈 밴드 이내. *일반화가 stablenet 인스턴스를 퇴화시키지 않음*을 증명.
- **도메인 격리 테스트.** Project B 실행 산출물(analysis.md·design)에 stablenet 용어·불변식이
  **누출되지 않음**을 grep으로 확인(잘못된 팩 해석/오염 차단).
- **가설 H0.** 코어 무편집으로 신규 프로젝트 파이프라인이 완주되며(수용), stablenet 정확성은
  무회귀.
- **반증조건.** 코어 diff가 비지 않거나(=계약 누수), stablenet 정확성이 회귀하면 P1 실패.

---

### P2 — cks 하드 의존 완화 (재시도·백오프 + degraded/blocked 임계 명문화)

**왜.** analyzer·planner는 §3.0에서 cks가 serviceable(ckg+ckv 둘 다)하지 않으면 BLOCKED.
"틀린 분석보다 멈춤이 낫다"는 옳은 원칙이지만, ckv가 *간헐적으로* 실패할 때(과거 ckv 한글버그·
Ollama 타임아웃 이력) **명시적 재시도/백오프가 없어** best-effort로 진행→ *조용히 불완전한*
분석을 낼 여지가 있다. 또 "degraded지만 진행" vs "BLOCKED"의 임계가 산문으로만 존재.

**무엇.**
1. cks MCP 호출에 **재시도+지수백오프**(예: 3회, 점진 타임아웃) 래퍼.
2. **serviceability 판정 임계 명문화**: 핵심 프리미티브(get_for_task/find_callers) 성공률 임계
   미달 → BLOCKED, 보조 프리미티브만 실패 → 명시적 `degraded` 플래그를 analysis.md에 기록하고
   진행. "조용한 best-effort" 금지.
3. degraded 시 evaluator·orchestrator가 그 플래그를 보고 검증 강도를 올리도록 전파.

**어떻게 검증.**
- **결함 주입(fault injection).** cks MCP 앞에 X% 호출을 드롭/지연시키는 **flaky 프록시**를
  끼우고, **PR-77 공정-입력 티켓**(오라클 존재: 근본원인 `anzeon.go:54 SetCurrentBlock`)을
  fault rate 0/10/30/50%에서 analyzer 단독 실행.
- **가설 H0.** 개선 후 *root-cause 정확도-vs-fault* 곡선이 개선 전보다 완만(고장에 강건)하고,
  진행 불가 시 **조용한 오답 대신 명시적 BLOCKED**가 난다.
- **지표.** ① fault rate별 PR-77 오라클 적중률, ② "조용한 오답"(틀린 근본원인을 confident하게
  제시) 발생 수 → 0이어야 함, ③ degraded 플래그 정확성(실제 보조툴만 실패했을 때만 degraded).
- **반증조건.** 개선 후에도 fault 상황에서 조용한 오답이 1건이라도 나오면 P2 부분실패.

---

### P3 — 모델 핀 중앙화 + 세대 갱신

**왜.** frontmatter가 `claude-opus-4-7`(orchestrator/analyzer/planner)·`claude-sonnet-4-6`
(implementer/evaluator)로 고정 — 현재 최신 Opus 4.8보다 한 세대 뒤. 핀이 6개 파일에 흩어져
세대 업그레이드가 다중 편집을 요구. (※ 의도적 핀이면 그 이유를 문서화해야 함.)

**무엇.** 모델 선택을 **단일 설정원**(예: 도메인팩/플러그인 설정의 `models.{deep,impl}`)으로
모으고, 에이전트는 역할 티어만 참조. 그 위에서 4-7→4-8 갱신을 1줄로.

**어떻게 검증.**
- **A/B on fixed fixtures.** 동일 bench 픽스처에서 (4-7/4-6) vs (4-8) 양 구성으로 3-way bench
  실행, agent-transcript.jsonl 기반 토큰/비용/지연 + 정확성 비교.
- **가설 H0.** 갱신 후 정확성 무회귀(이상적으로 향상), 비용/지연 허용범위.
- **지표.** 정확성(오라클 적중)·avg_tokens·avg_cost·avg_latency. **반증조건.** 정확성 회귀 또는
  비용이 효용 대비 과다 증가하면 핀 유지/롤백.
- **부수효과.** 중앙화 자체가 dispatch를 깨지 않았는지(=전 에이전트 정상 기동) 스모크 확인.

---

### P4 — 문서 드리프트 정리 (HANDOFF-simulation-verification supersede)

**왜.** `plugin/docs/HANDOFF-simulation-verification.md`는 "simulation-harness 스킬 부재 +
red→green 보증 공백"을 제안하나, 현재 `reproduce-first`·`investigative-probe` 스킬이 그
상당부분을 이미 구현. 활성 문서가 *이미 닫힌 공백*을 미해결로 서술 → 후속 세션을 오도.
(doc-organize 규율: supersede-not-delete.)

**무엇.** 핸드오프 문서를 현 구현 기준으로 재작성하거나 `docs/archive/`로 supersede + 상단에
"무엇이 reproduce-first/evaluator §4.7로 충족됐고 무엇이 남았나"를 명시.

**어떻게 검증 (감사 체크리스트, 런타임 무관).**
- **doc-truth 대조.** 핸드오프의 각 주장(claim)을 현 스킬/에이전트 파일과 1:1 대조표로:
  ① simulation-harness 스킬 존재? ② evaluator red→green 격리 worktree 게이트(§4.7) 존재?
  ③ implementer red-before-green(§3.4·§6.0) 존재? 등.
- **성공조건.** 활성 문서 중 현 코드와 *모순되는* 주장 0건. (메모리의 "CKG 4-way 함정"·
  "graph-gap P0 반증" 같은 *분석↔코드 불일치*를 재발 방지하는 규율과 동일.)

---

### P5 — evaluator 파괴적 정리 범위 한정

**왜.** evaluator §7.6이 `gstable`/`wbft-node` *이름*으로 프로세스를 kill → 개발자가 별도로
띄운 무관한 로컬 인스턴스를 죽일 수 있다(파괴적·외향 부작용).

**무엇.** 정리 대상을 **evaluator가 직접 spawn한 PID**로 한정(워크스페이스 로그에 PID 기록 →
그 PID만 종료). 광역 `pkill`/이름매칭 회피.

**어떻게 검증 (이진 안전 테스트).**
- 무관한 더미 프로세스를 타깃과 같은 이름으로 띄움 → evaluator 정리 실행 → **더미 생존** &
  워크스페이스-추적 PID만 종료 확인.
- **반증조건.** 더미가 죽으면 P5 실패.

---

## Part B. P1 상세 — 도메인팩 계약 (다중 프로젝트 확장)

> 목표: **"새 프로젝트 = 도메인팩 1개 추가, 코어 0 편집".** go-stablenet은 첫 인스턴스이자
> 계약의 레퍼런스 구현이 된다.

### B.1 현재의 암묵적 이음새 (무엇이 정적으로 묶였나)

| 도메인 결합 지점 | 현재(정적/이름) | 위치 |
|---|---|---|
| 불변식(L3 backstop) | `stablenet-invariants` 스킬 직접 호명 | analyzer/planner/evaluator frontmatter |
| 경로→모듈 분류 | `stablenet-context` 스킬 직접 호명 | analyzer/planner frontmatter |
| 통합검증 스테이지 | chainbench Stage 인라인 | evaluator.md §7 |
| 빌드 산출물 | `build/bin/gstable` 하드코딩 | implementer §6.1 / evaluator §7.1 |
| 단위테스트 명령 | `go test -run …` 하드코딩 | reproduce-first / evaluator §4 |
| 지식 인덱스 | 단일 `CKS_CONFIG` | .mcp.json |
| 티켓 네임스페이스 | `STABLE-*` 가정 | template-parse / work.md |

### B.2 도메인팩 계약 (선언적 인터페이스)

프로젝트별 **도메인팩 디렉터리** + `domain-pack.json` 매니페스트로 정의. 코어가 요구하는
**확장점(extension point)** 목록을 계약으로 고정:

```jsonc
// domains/<project_id>/domain-pack.json (예시 스키마)
{
  "project_id": "go-stablenet",
  "ticket_namespace": "STABLE",            // template-parse·work.md 가 참조
  "knowledge": {
    "cks_config": "${CKS_CONFIG_GO_STABLENET}"   // 프로젝트별 cks 인덱스
  },
  "context_classifier": "domains/go-stablenet/context.md",  // 경로→모듈 (전 stablenet-context)
  "invariants": "domains/go-stablenet/invariants.md",       // L3 backstop (전 stablenet-invariants)
  "build": { "cmd": "go build ./...", "artifact": "build/bin/gstable" },
  "unit_test": { "runner": "go", "run_tmpl": "go test -run '{name}' ./{pkg}/..." },
  "verification_stages": [                  // evaluator 가 순회 (chainbench 는 그중 하나)
    {"id": "unit",  "kind": "builtin:unit_race"},
    {"id": "lint",  "kind": "builtin:lint"},
    {"id": "sec",   "kind": "builtin:gosec"},
    {"id": "integ", "kind": "mcp:chainbench", "profile": "default",
     "oracle_enum": ["basic/consensus", ...]}
  ]
}
```

핵심 전환:
- **frontmatter 정적 호명 제거** → 에이전트는 *"활성 도메인팩의 invariants/classifier를 로드"*
  하는 단계로 대체(스킬은 *제너릭 로더*가 되고, 도메인 콘텐츠는 데이터).
- **evaluator 스테이지 = 데이터 주도 루프**: `verification_stages[]`를 순회하며 `kind`로
  분기(builtin/mcp). chainbench는 `mcp:` 스테이지의 한 인스턴스일 뿐.
- **빌드/테스트/티켓 네임스페이스 = 매니페스트 값** 치환(하드코딩 제거).
- **프로젝트 선택**: state.json에 `project_id` 추가 → 모든 에이전트가 해당 팩을 해석.
  CKS_CONFIG·integration dir도 팩에서 해석(다중 인덱스 공존).

### B.3 generic vs domain 재분류 (목표 상태)

| 분류 | 구성요소 | 비고 |
|---|---|---|
| **Generic 골격(불변)** | state-machine, reproduce-first, root-cause-lifecycle, investigative-probe, pr-sanitize, template-parse(파서만), orchestrator FSM | 프로젝트 무관 |
| **Domain pack(치환)** | invariants, context-classifier, build/test 명령, verification_stages, cks 인덱스, ticket namespace | 프로젝트당 1벌 |
| **Generic 로더(신규)** | "활성 팩 해석" 스킬 | frontmatter 정적 바인딩 대체 |

### B.4 마이그레이션 (무회귀 우선)

1. `domains/go-stablenet/` 추출 — 기존 `stablenet-*` 콘텐츠를 그대로 이동(*무리팩터*).
2. 코어 에이전트의 정적 호명을 "활성 팩 해석"으로 치환. **이 시점에서 go-stablenet bench
   무회귀 확인(P1 무회귀 테스트).**
3. 토이 "Project B" 팩 작성 → 수용 테스트(코어 빈 diff)로 계약 누수 검출.
4. evaluator 스테이지 데이터화(chainbench를 `mcp:` 스테이지로 일반화).

> 순서가 중요: **먼저 무리팩터 이동 → 무회귀 고정 → 그 다음 일반화**. 일반화가 stablenet
> 인스턴스를 퇴화시키지 않음을 각 단계에서 bench로 잠근다.

---

## Part C. 통합 평가 프레임워크

개별 평가(Part A)를 관통하는 공통 원칙·기판. 메모리의 두 함정 — *"CKG 4-way: .claude/docs는
실재 indexed 문서(환각 아님)"*, *"graph-gap P0: 진짜 개선은 새 프리미티브가 아니라 analyzer
agentic routing이었다(δ<γ 반증)"* — 을 재발 방지하는 규율을 내장한다.

### C.1 기판 — 이미 가진 자산을 재사용 (신규 인프라 최소화)

- **3-way bench 하네스**(`/coding-agent:bench`, bench-orchestration): A/B의 실행 기판.
  개선 전(baseline) vs 개선 후를 *동일 픽스처*로.
- **agent-transcript.jsonl**(on-agent-complete 훅): 토큰/비용/지연 사후 정산의 substrate.
- **reproduction 오라클**(reproduce-first, red→green): 정확성의 결정적 oracle.
- **PR-77 공정-입력 티켓 + expert oracle**(`test-data/pr-77/`): 정확도 측정의 ground truth
  (P2 결함주입의 표적).
- **expert `reference_fix` diff**(bench fixtures): false-GREEN/완전성 측정(P0).

### C.2 세 가지 지표군

1. **정확성(correctness).** 오라클 적중률, false-GREEN율, write-site 완전성, 도메인 격리.
2. **비용(cost).** avg_tokens · avg_cost · avg_latency (transcript 기반).
3. **안전성(safety).** BLOCKED 적절성(조용한 오답 0), 파괴적 부작용 없음(P5), 도메인 누출 0(P1).

### C.3 방법론 규율 (함정 회피)

- **사전등록.** 각 개선은 구현 전에 H0 + 지표 + **반증조건**을 본 문서에 고정(사후 합리화 금지).
- **변수 격리.** A/B는 *한 번에 한 가지*만 변경(픽스처·오라클·모델 고정). graph-gap 사례처럼
  "여러 변수를 동시에 바꿔 엉뚱한 원인에 공을 돌리는" 오류 차단.
- **무회귀 우선.** 모든 일반화/갱신(P1·P3)은 *먼저 무회귀*를 통과해야 효용 평가로 진입.
- **조용한 실패 = 실패.** "best-effort로 진행"이 만든 *무성 품질저하*를 지표로 끌어올림
  (P2의 "조용한 오답 0" 조항).
- **오라클 신뢰성 점검.** red→green·PR-77 오라클이 *우연히* 통과하지 않는지(약한 오라클)
  evaluator §4.7 red 재확인으로 교차검증.

### C.4 우선순위 · 순서 · 리스크

| 우선 | 항목 | 선행/리스크 |
|---|---|---|
| **P0** | 계약 기계검증 | 저위험·고효용. 즉시 착수 가능 |
| **P2** | cks 결함강건 | PR-77 오라클로 단독 평가 용이. P0와 병행 가능 |
| **P5** | 정리 범위 한정 | 소규모·안전. 단독 |
| **P3** | 모델 핀 중앙화/갱신 | 중앙화(저위험) → 갱신(bench A/B로 게이트) |
| **P1** | 도메인팩 계약 | **최대 효용·최대 위험.** 반드시 무리팩터→무회귀→일반화 순. bench 잠금 필수 |
| **P4** | 문서 정리 | 비런타임. 아무 때나, 단 다른 항목 구현 후 사실 반영 |

> P1은 단독 대형 작업이므로, P0/P2/P5로 **계약·강건·안전 기반을 먼저 다진 뒤** 착수하는 것이
> 안전하다(도메인팩 데이터화가 곧 P0의 구조화 산출물·P2의 degraded 전파와 맞물린다).

---

## 부록: 근거 파일 인덱스

- 파이프라인: `plugin/agents/{orchestrator,analyzer,planner,implementer,evaluator}.md`
- 계약 지점: planner §5.2b(write-site) · implementer §3.4/§4.2/§6.1 · evaluator §4.6/§4.7/§7
- cks 게이트: analyzer/planner §3.0
- 도메인 결합: `plugin/skills/{stablenet-context,stablenet-invariants}` · `.mcp.json`
- 평가 기판: `plugin/skills/bench-orchestration` · `hooks/on-agent-complete.sh` · `test-data/pr-77/`
- 모델 핀: 각 `plugin/agents/*.md` frontmatter `model:`
