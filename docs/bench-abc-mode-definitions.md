# Bench A/B/C Mode Definitions (정본)

> 작성: 2026-06-22. 목적: full-pipeline 벤치에서 비교하는 **세 가지 접근법(regime)** 의 의미를
> 머신 독립적으로 못박는다. 이 문서가 A/B/C의 **단일 정의 기준**이며, 하네스(에이전트·SKILL·매니페스트)는
> 이 정의를 따른다. 이전 하네스 정의(B/C가 coding-agent 파이프라인 *안*의 분석-단계 변이였던 것)는
> **이 문서가 supersede** 한다(§6).
>
> ⚠️ **경로 규약(중요):** 이 문서는 **절대경로를 쓰지 않는다** — 다른 머신에서 맞지 않기 때문이다.
> 머신별 실제 경로는 **매니페스트의 설정 필드에만** 둔다(문서는 기호로만 참조).

---

## 0. 용어 (기호 — 머신 독립)

| 기호 | 의미 | 머신별 실제값이 사는 곳 |
|---|---|---|
| `<coding-agent>` | coding-agent **플러그인** repo 루트 | 플러그인 설치 경로 |
| `<target>` | **벤치 대상 코드베이스(go-stablenet)의 워킹트리.** cks가 인덱싱한 트리와 **반드시 동일**해야 함 | 매니페스트 `go_stablenet_root` (= cks `source_root`) |
| `<target>/.claude/` | **대상 프로젝트 자신의** Claude Code 자산(commands + docs). `<coding-agent>` 플러그인과 **별개** | 대상 repo 안 |
| cks | code-knowledge-system MCP (ckg 그래프 + ckv 벡터 조합 검색) | MCP 등록(설정) |

> 핵심 구분: **`<coding-agent>`의 스킬**(예: `stablenet-context`, `root-cause-lifecycle`)과
> **`<target>/.claude`의 스킬**(예: `stablenet-review-code` 커맨드, `wbft-consensus.md` 등 docs)은
> **완전히 다른 스킬셋**이다. C 모드가 쓰는 것은 후자(대상 프로젝트 자신의 것)다.

---

## 1. 세 모드의 정의

### A — coding-agent + cks  *(production regime)*
- **무엇**: `<coding-agent>` 전체 파이프라인(analyzer → planner → implementer → evaluator + state machine)을
  돌리되, 분석을 **cks**(semantic + graph + domain 검색)로 구동한다.
- **정보원**: `<target>` 코드 + **cks 검색** + `<coding-agent>` 스킬/오케스트레이션.
- **한 줄**: "우리 시스템(coding-agent)을 cks와 함께 풀로 쓴다." = 실제 `/work`와 동일한 운영 형태.

### B — bare LLM + 코드 + grep  *(floor baseline)*
- **무엇**: `<coding-agent>` 플러그인 ❌, `<target>/.claude` 프로젝트 스킬 ❌. **아무 스킬·오케스트레이션 없이**
  순수 LLM이 `<target>` **프로젝트 코드 + grep/read** 만으로 티켓을 처음부터 끝까지(진단→수정→회귀테스트→통과) 해결한다.
- **정보원**: `<target>` 코드 + grep/read/edit/bash. **그 외 아무것도 없음.**
- **한 줄**: "맨몸 LLM이 코드와 grep만으로 푼다." = 비교의 바닥선.

### C — 프로젝트 네이티브 스킬만  *(project-shipped knowledge baseline)*
- **무엇**: `<coding-agent>` 플러그인 ❌, cks ❌. 대신 **대상 프로젝트 자신의 `<target>/.claude` 스킬**
  (commands + docs)만 사용하고 `<target>` 프로젝트 코드와 함께 티켓을 해결한다.
- **정보원**: `<target>` 코드 + **`<target>/.claude`**(예: `stablenet-*` 커맨드, `wbft-consensus.md`·
  `system-contract-flow.md`·`code-convention.md` 등 docs). cks·coding-agent 스킬은 **불가**.
- **한 줄**: "coding-agent 없이, 프로젝트가 자체 제공하는 지식만으로 푼다."

---

## 2. 무엇을 고정하고 무엇을 바꾸나

| 축 | A | B | C |
|---|---|---|---|
| coding-agent 파이프라인 | ✅ 사용 | ❌ 미사용 | ❌ 미사용 |
| cks 검색 | ✅ | ❌ | ❌ |
| `<coding-agent>` 스킬 | ✅ | ❌ | ❌ |
| `<target>/.claude` 프로젝트 스킬 | (간접; A는 coding-agent 경로) | ❌ | ✅ **유일 사용** |
| `<target>` 코드 + grep/read | ✅ | ✅ | ✅ |
| **고정(공통)** | 같은 티켓(증상-only) · 같은 `base_commit` · 같은 모델 · 같은 평가(정답 오라클) | | |

→ 이 정의는 *"분석단계 정보 regime의 한계효용"* 이 아니라 **"세 가지 접근법 전체의 비교"** 를 측정한다:
**우리 시스템(A)** vs **맨몸(B)** vs **프로젝트 자체 지식(C)**. B/C가 더 현실적인 baseline이다.

---

## 3. 공정성 규칙 (regime 누수 금지)

1. **동일 입력**: 세 모드 모두 같은 **증상-only 티켓**(메커니즘·정확한 위치 비공개) + 같은 `base_commit` + 같은 모델.
2. **A만 cks**: B·C는 cks MCP 도구에 접근 불가.
3. **B는 최소**: `<coding-agent>` 스킬도, `<target>/.claude`도 보지 못한다. 코드 + grep/read/edit/bash만.
4. **C는 프로젝트 네이티브만**: `<coding-agent>` 스킬·cks 불가. `<target>/.claude` + 코드만.
5. **도구 부재로 보장**: "쓰지 마"라는 프롬프트 의존이 아니라, 해당 regime에서 **도구/스킬을 실제로 제공하지 않음**으로 격리.
6. **동일 평가**: 정확성은 정답 오라클(재현 테스트 GREEN + `expert-fix.diff` 유사도)로 모드 불문 동일 측정.
7. **누락 금지**: 실패한 모드도 리포트에 포함(정확성=실패로 집계).

---

## 4. 측정 축 (모드 무관 동일)

- **최종 정확성**: 재현 테스트 red→green 통과 여부 + 회귀 스위트.
- **총비용**: 옳은 수정까지의 Σ토큰(재시도/싸이클 누적) · 비용 · 지연.
- **반복 횟수**: 수정-재평가 싸이클 수.
- **사이드이펙트**: 회귀-클래스 실패 수.
- **전문가 유사도(선택)**: 에이전트 diff vs `expert-fix.diff`(결정적 overlap + 의미적 동등성).

---

## 5. 하네스 재설계 함의 (✅ 2026-06-22 구현 완료)

> 아래 1~5는 모두 반영됨: `plugin/agents/bench-solver-{codeonly,project-skills}.md` 신설,
> `bench-orchestration/SKILL.md` §0 정의 교체 + §4.4 A/(B·C) 분기, `bench/manifests/stable-0005-abc.json`
> 타깃루트 통일, 구식 `bench-analyzer-{codeonly,skills}.md` deprecation 배너. 모델 핀 `claude-opus-4-8`.

1. **B/C는 더 이상 "분석-단계 변이"가 아니다.** 기존 `bench-analyzer-codeonly`/`bench-analyzer-skills`는
   분석만 하고 **공유 planner/implementer/evaluator**(= coding-agent)로 넘겼다. 새 정의에서 B·C는
   **coding-agent를 통째로 배제**하므로, 공유 하류 파이프라인을 쓰면 안 된다 → **whole-approach 실행체**로 교체.
2. **C의 스킬 출처 변경**: 기존 C는 `<coding-agent>` 이해스킬을 썼다. 새 C는 **`<target>/.claude`** 를 써야 한다.
3. **타깃 루트 통일**: 매니페스트 `go_stablenet_root` 가 cks `source_root` 와 **달랐다**(별도 클론 vs 인덱싱된 트리).
   A의 cks 검색과 실제 수정 대상이 어긋나지 않도록 **둘을 동일 트리로 통일**(인덱싱된 트리 = 수정 트리).
4. **SKILL 프로토콜 §4.4 분기**: A는 현행 4-스테이지 디스패치, B·C는 단일 whole-approach 실행 + 동일 평가(evaluator는
   정확성 측정을 위해 공유하되 *해결 과정*에는 개입 금지 — 측정 전용)로 재작성.
5. **모델 고정 유지**: 세 모드 동일 모델(비교는 regime만 격리).

---

## 5b. 알려진 caveat — 모델 비대칭 (착수 전 인지)

세 모드 모두 `claude-opus-4-8`로 핀하지만, **A는 단계별 모델이 갈린다**: analyzer/planner는
opus-4-8, implementer/evaluator는 sonnet-4-6. 반면 **B/C는 단일 solver라 진단·수정 전부
opus-4-8 단독**이다. 즉 *구현 단계 모델*이 A(sonnet) vs B/C(opus)로 다르다.

- 이는 "접근법 전체 비교"라는 본 정의의 자연스러운 결과(맨몸/네이티브 regime은 단계분리가 인위적).
- 정밀 비교가 필요하면 (i) A의 implementer/evaluator도 opus-4-8로 맞추거나, (ii) 결과 해석 시
  이 비대칭을 명시한다. 현재는 (ii)로 진행하고 SKILL §0에 caveat를 명시.

## 6. Supersede 기록

- 이전 정의(`plugin/skills/bench-orchestration/SKILL.md` §0, `bench-analyzer-{codeonly,skills}.md`):
  B/C가 coding-agent 파이프라인 *내부*의 분석-단계 변이였고 C=coding-agent 이해스킬. → **본 문서가 대체.**
- 통합뷰 `WORKLIST.md` 스트림1의 A/B/C 표기도 본 정의에 맞춰 갱신 대상.
