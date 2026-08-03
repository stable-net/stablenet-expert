# ADR-0011 — `stablenet-expert:doctor` 2단계: 대화형 수정 + 플러그인별 setup 위임

문서 성격: **ADR / 설계 결정 (Accepted 2026-07-31).**
짝 문서: [ADR-0010](ADR-0010-stablenet-expert-meta-plugin-design.md)(메타 플러그인 1단계) ·
참조 사례 `references/midnight-expert`의 `midnight-expert:doctor` 스킬(`Step 4: Offer Fixes`,
`references/fix-table.md`, Tooling 위임 패턴) · [ADR-0002](ADR-0002-setup-and-doctor.md)/
[ADR-0004](ADR-0004-doctor-remediation-routing.md)(`core-dev`의 기존 doctor→setup remediation
라우팅 — 이 ADR이 재사용하는 대상).

> **결정 한 줄:** `stablenet-expert:doctor`를 확장해 (1) 자기 발견 항목(플러그인 미설치/비활성화,
> MCP 이중 등록)은 `AskUserQuestion`으로 대화형 수정을 제공하고, (2) 플러그인별 환경 설정(env
> var, 빌드 산출물 등)은 **직접 구현하지 않고** 그 플러그인 자신의 `/<plugin>:setup`이 있으면
> 위임 호출한다 — `core-dev`의 기존 `/core-dev:setup`(REMEDIATION 라우팅, ADR-0002/0004)을
> 중복 재구현하지 않는다. `midnight-expert:doctor`의 "Tooling도 체크할까요?" 위임 패턴과 동형.
> **상태:** Superseded by [ADR-0012](ADR-0012-doctor-step-order-revision.md) — 위임/자체수정
> 원칙(§2.1/2.2)은 그대로 유지되지만, 스텝 구조(체크→보고→자체수정→위임→재검증 5단계)가
> 0-5 6단계(공통 환경 체크·MCP 연결성 체크 신규 추가, 결정/실행 분리, 위임을 실행 단계에 인라인,
> MCP 충돌 검증을 최종 단계로 이동)로 대체됨. 이 문서는 그 대체 이전의 설계 기록으로 보존.

---

## 1. Context (왜)

ADR-0010(1단계)은 두 체크(플러그인 상태, MCP 이중 등록)를 **읽기 전용 보고**만 하도록 의도적으로
좁혔다. 사용자가 이제 `midnight-expert`처럼 "이 플러그인들을 실제로 쓰기 위해 필요한 환경을
대화형으로 셋업해주는" 방향으로 확장하길 원한다.

### 1.1 참조 사례 재조사 — `midnight-expert:doctor`의 Step 4/5

`SKILL.md`를 다시 읽어보니 1단계 작성 때 훑지 않았던 부분이 있었다:

- **Step 1의 AskUserQuestion**: 5개 자체 체크를 백그라운드로 돌리는 동시에 "Midnight Tooling
  상태도 체크할까요? (Compact CLI, compiler, devnet, proof server)"라고 묻고, yes면
  `midnight-tooling:doctor` 스킬을 **위임 호출**한다. 즉 `midnight-expert`(메타)는 `midnight-tooling`
  (도메인 플러그인)의 진단 로직을 재구현하지 않고 그 플러그인 자신의 doctor를 부른다.
- **Step 4 (Offer Fixes)**: `references/fix-table.md`(이슈→고정 커맨드 매핑)를 참조해 FAIL/WARN
  항목마다 고칠지 물어본다. `--auto-fix`면 조용히 적용(단, 플러그인 설치/활성화·MCP 서버 추가
  scope·툴 업그레이드는 **항상** 프롬프트 — "사용자가 큐레이션하는 것"이라 auto-fix 대상이 아님).
- **Step 5**: 고친 것만 재검사해서 최종 요약.

### 1.2 `core-dev`의 기존 remediation 라우팅 재확인 (ADR-0002/0004)

`plugins/core-dev/scripts/doctor.py`에 이미 `REMEDIATION` 테이블이 있다 —
`kind → {klass, command, action}`, `klass`는 `setup`(→ `/core-dev:setup --fix` 등)/`manual`/
`restart`/`external`로 분류. `plugins/core-dev/scripts/setup.py`는 `--check`/`--fix`/`--set`/
`--interactive`/`--autonomous`를 지원하는, 이미 완성된 대화형 셋업 도구다.

**결론**: `core-dev`가 필요로 하는 env var(`JIRA_*`, `STABLENET_KNOWLEDGE_*`, `CHAINBENCH_DIR`)를
채우는 로직은 `stablenet-expert`가 다시 만들 이유가 없다 — 이미 있고, 이번 세션에서 직접 여러 번
써서 검증도 됐다(`/core-dev:setup --fix` 등). `stablenet-expert:doctor`는 **"이 플러그인은 자기
setup이 있으니 그걸 불러라"** 라고만 하면 된다.

### 1.3 `contract-dev`는 위임할 게 없다

ADR-0009 결정대로 `contract-dev`는 MCP 서버도 env var도 없다 — 위임할 `setup` 자체가 없다. doctor는
이걸 "설정 불필요"로 보고하고 넘어가면 된다.

---

## 2. Decision (무엇)

### 2.1 대화형 수정 — `stablenet-expert` 자체 발견 항목만

`check-plugins.sh`/`check-mcp-conflicts.sh`가 낸 `critical`/`info` 각각에 대해, 보고 직후
`AskUserQuestion`으로 하나씩(또는 같은 종류끼리 묶어서) 물어본다:

- **플러그인 미설치** → "`<plugin>@stablenet-expert`를 설치할까요?" → yes면
  `claude plugin install <plugin>@stablenet-expert` 실행.
- **플러그인 설치됐지만 비활성화** → "활성화할까요?" → yes면 `claude plugin enable <plugin>` 또는
  `settings.json`의 `enabledPlugins`에 `true`로 기록(ADR-0010이 이미 쓰는 방식과 동일 경로).
- **MCP 이중 등록 충돌** → "`<A>`와 `<B>` 중 어느 쪽을 켜두고 싶으세요?" → 선택된 쪽만 남기고
  나머지를 비활성화. **여기는 `--auto-fix` 같은 무프롬프트 옵션을 주지 않는다** —
  `midnight-expert`도 플러그인 활성화 판단은 항상 프롬프트로 남겨두는 것과 같은 이유(사용자가
  큐레이션해야 하는 결정).

수정 후 해당 체크만 재실행해서 확인(`midnight-expert` Step 5와 동일 원칙 — 통과한 체크까지
재실행하지 않는다).

### 2.2 플러그인별 setup 위임 — 새로 만들지 않고 부른다

체크 리포트 다음에, **설치·활성화된 플러그인 각각에 대해** 그 플러그인이 자기 `setup` 커맨드를
갖고 있으면(`commands/setup.md` 존재 여부로 판별) 실행 여부를 묻는다:

> "`core-dev`가 설치돼 있습니다. 필요한 환경(Jira, stablenet-knowledge, chainbench)이 갖춰졌는지
> 확인할까요?" → yes면 `/core-dev:setup --check`를 호출(Skill 도구로)하고 그 출력을 그대로 포함.
> 문제가 있으면 사용자에게 `/core-dev:setup --fix`(또는 필요한 정확한 플래그)를 안내 — 여기서
> `stablenet-expert`가 직접 env를 쓰지 않는다, `core-dev:setup`이 이미 하는 일이다.

`contract-dev`처럼 `commands/setup.md`가 없는 플러그인은 "설정 불필요"로 한 줄만 보고.

**미래 플러그인 규칙(문서화만, 강제 안 함)**: 새 플러그인이 env var/빌드 산출물이 필요하면
`/​<plugin>:setup`을 직접 만들어야 이 위임이 작동한다 — `stablenet-expert`는 각 플러그인의
setup 존재 여부만 확인하지, 없는 걸 대신 만들어주지 않는다.

### 2.3 `--auto-fix` 플래그는 1단계에서 도입하지 않는다

`midnight-expert`의 `--auto-fix`는 "설치류는 조용히, 활성화/업그레이드/scope 선택은 항상 프롬프트"
로 세분화돼 있다. 지금 `stablenet-expert`의 자체 수정 항목(플러그인 설치, MCP 충돌 해소)은 전부
"항상 프롬프트" 카테고리에 해당하므로, `--auto-fix`를 만들어도 사실상 아무것도 조용히 처리할 게
없다 — 후속(§3)으로 남기고 지금은 구현하지 않는다.

---

## 3. Consequences (결과)

- **+**: `core-dev`의 검증된 setup 로직을 재사용해서 새 버그 표면을 만들지 않는다.
- **+**: `midnight-expert`가 실제로 검증한 UX 패턴(대화형 1건씩 확인, 위임 델리게이션)을 그대로
  따라가서 설계 리스크가 낮다.
- **−/제약**: 위임은 "그 플러그인이 `commands/setup.md`를 갖고 있어야" 작동한다 — 앞으로 생길
  `stablenet-tooling` 등이 env var가 필요한데 자기 setup을 안 만들면 이 메타 플러그인이 대신
  채워주지 않는다(의도된 제약, §2.2).
- **후속**:
  1. 이 ADR 승인 후 `commands/doctor.md` 확장 — 별도 작업.
  2. `--auto-fix`/`references/fix-table.md` 같은 구조화된 고정-테이블은 수정 항목이 실제로
     늘어나서 필요해지면(예: 외부 CLI 툴 체크가 추가되면) 재검토.
  3. `stablenet-tooling`이 실제로 만들어질 때, 자기 `setup` 커맨드를 갖춰야 이 위임 대상이 된다는
     걸 새 플러그인 체크리스트(ADR-0008 §2.1)에 반영할지 검토.
