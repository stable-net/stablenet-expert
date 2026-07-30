---
name: domain-pack
description: "프로젝트-불문 도메인팩 로더. state.json의 project_id로 활성 프로젝트의 domain-pack(${CLAUDE_PLUGIN_ROOT}/domains/{project_id}/)을 런타임에 해석해, 경로→모듈 분류·복잡도 추정·항상-켜진 invariants backstop을 제공한다. 도메인 *지식*은 그 프로젝트의 stablenet-knowledge 인덱스가 권위. (ADR docs/adr/ADR-0001-domain-pack-contract.md)"
type: skill
---

# Domain-Pack Loader (generic — resolves the active project's domain pack)

이 스킬은 **프로젝트 고유 내용을 담지 않는다.** 절차(어떻게 분류·평가·backstop 적용하나)만
제너릭하게 정의하고, 데이터는 활성 프로젝트의 팩에서 런타임 `Read`로 끌어온다. 그래서 코어
에이전트는 `stablenet-*` 같은 프로젝트명을 호명하지 않고 이 스킬 하나만 참조한다.

> **배선 상태:** analyzer/planner/evaluator가 이 로더를 참조하며, 활성 팩은 **`scripts/resolve-project.py`
> 가 런타임에 발견**한다(git remote/go.mod ↔ 각 팩의 `detect`). 프로젝트 특화 데이터·명령·불변식·툴은
> 전부 `domains/{project_id}/` 에 있고, 스킬은 프로젝트-불문이다.

## 1. 활성 팩 해석 (런타임 — 발견은 도구로, 폴백 없음)

스킬 본문은 *지금 어느 프로젝트인지* 정적으로 모른다. 반드시 **런타임 도구 실행으로 발견**한다:

```
# 1) 굳어 있으면 그걸 쓴다 (엔트리 커맨드/SessionStart hook이 이미 발견해 둠):
pack_root  = read {workspace_dir}/state.json → .pack_root       # 있으면 이 경로가 활성 팩 디렉터리
project_id = read {workspace_dir}/state.json → .project_id

# 2) 없거나 workspace가 없으면 결정론적 resolver로 발견:
res = Bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/resolve-project.py
      # git remote origin + go.mod module 을 domains/*/domain-pack.json 의 detect 와 대조 → JSON
project_id = res.project_id ; pack_root = res.pack_root

pack = Read({pack_root}/domain-pack.json)     # pack_root = ${CLAUDE_PLUGIN_ROOT}/domains/{project_id}
```

⚠️ **폴백 금지 (fail-loud).** `res.unknown == true`(매칭 팩 없음) 또는 `res.ambiguous`이면 **BLOCKED**로
보고한다 — *조용한 기본 프로젝트 적용은 오염이므로 하지 않는다*. 안내: "이 repo에 맞는 domain-pack
없음(감지 신호: origin={res.origin}, module={res.go_module}). `domains/<id>/`에 detect 규칙을 추가하거나
`setup --project <id>`로 지정하라." (구 `go-stablenet` 무조건 폴백은 제거됨.)

> **발견이 실제로 트리거되는가(핵심):** resolver는 (a) **SessionStart hook**(하네스가 세션마다 강제
> 실행 → `additionalContext`로 활성 팩 주입)과 (b) **엔트리 커맨드 스텝1**(발견 후 `state.json.pack_root`
> 로 영속)로 **결정론적으로 호출**된다. 스킬은 그 굳은 결과를 Read할 뿐 재발견하지 않는다.
> **경로 주의**: `${CLAUDE_PLUGIN_ROOT}`는 *설치된 플러그인 루트*(`~/.claude/plugins/cache/.../<version>/`)로
> **로드 시점 인라인 치환**된다. 에이전트 cwd는 타깃 repo라 상대경로는 안 풀리므로 번들 팩 파일·스크립트는
> **반드시 `${CLAUDE_PLUGIN_ROOT}` 절대경로**로 Read/Bash한다.

## 2. 제공 절차  (경로는 모두 §1의 `{pack_root}` 기준)

### 2.1 classify_domain(file_paths, symbols)
`Read({pack_root}/{pack.context_classifier})` 의 경로→모듈 규칙(§"경로 기반 모듈 분류")으로 각
file_path를 분류 → 중복 제거 → 빈도순 정렬. 심볼이 모호하면 stablenet-knowledge `find_symbol`로 경로를 얻어 같은
규칙 적용. 출력: `{primary_domain, domains[], confidence}`.

### 2.2 estimate_complexity(domains, change_summary)
같은 classifier 파일의 복잡도 휴리스틱(simple/moderate/complex + 동시성 키워드 승급)을 적용.
출력: `{complexity, reasoning}`.

### 2.3 invariants backstop (항상-켜짐)
`Read({pack_root}/{pack.invariants})` 의 불변식 목록을 **검색 결과와 무관하게** 적용한다(L3
backstop): Planner는 설계가 이를 위반하지 않게, Evaluator는 diff가 이를 깨지 않았는지 판정.
도메인별 정확한 수치·anchor의 권위는 그 프로젝트의 stablenet-knowledge 엔트리다.

### 2.4 project tools (프로젝트 특화 런타임 스크립트)
`pack.tools.entries[]` 는 그 프로젝트 전용 실행 스크립트다(`{pack_root}/tools/` 하위). 스킬/커맨드는
프로젝트를 모른 채 **id로만** 호출한다 — 실체는 팩이 라우팅한다:

```
tool = pack.tools.entries[] 에서 id 로 조회
Bash: {tool.runner} {pack_root}/tools/{tool.path} [args]     # 예: bash .../tools/preflight.sh {repo_root}
```
인터프리터를 직접 부르므로(`bash`/`python3`) 실행비트 불필요. `when`은 어느 단계가 부를지 라우팅
힌트(예: `before-build`). 스크립트 로직은 그 프로젝트 팩에 산다 — 코어 스킬엔 프로젝트 명령이 없다.

## 3. 경계

- 도메인 *지식*(불변식 수치·contract 이름·합의 규칙)은 이 스킬이나 팩 파일에 하드코딩하지 않는다 —
  활성 프로젝트의 stablenet-knowledge 인덱스(`guidance.*` / 도메인 엔트리)가 권위. 팩은 *검색-독립 backstop +
  경로 분류 데이터*만 담는다.
- `pack.verification`(repo_root_env·build·unit_test·stages)은 evaluator/implementer가 데이터-주도로
  소비한다(빌드·테스트 명령의 단일 소스 — 스킬/에이전트에 하드코딩 금지). `pack.tools`는 §2.4로 실행.
- 새 프로젝트 지원 = `domains/<id>/`(domain-pack.json+detect [+ context/invariants/simulation/tools]) 추가.
  코어 스킬·에이전트·resolver 코드는 무변경 — 확장성이 데이터(팩)에 있다.
