# ADR-0014 — 플러그인 setup 스크립트 계약 (설치 직후 재시작 없이 셋업)

문서 성격: **ADR / 설계 결정 (Accepted 2026-08-05).**
짝 문서: [ADR-0011](ADR-0011-stablenet-expert-doctor-interactive-setup.md) §2.2(위임 원칙 —
도메인 지식은 소유 플러그인에) · [ADR-0012](ADR-0012-doctor-step-order-revision.md)(doctor 6단계
구조) · [ADR-0008](ADR-0008-new-plugin-scaffolding-contract.md)(신규 플러그인 체크리스트 —
이 ADR이 항목 하나를 추가한다).

> **결정 한 줄:** 이 마켓플레이스의 모든 플러그인은 `scripts/setup.py`를
> `--check` / `--fix` / `--json` 인터페이스로 제공하고, `stablenet-expert:doctor`는 설정 위임을
> **스킬 이름이 아니라 설치 경로의 스크립트 실행**으로 수행한다. 그래야 같은 세션에서 설치한
> 플러그인도 재시작 없이 셋업까지 끝난다.

## 1. Context (왜)

ADR-0011 §2.2는 "플러그인의 환경 설정은 그 플러그인이 안다"는 위임 원칙을 세웠고, doctor는 이를
`Skill(skill: "<plugin>:setup")` 호출로 구현했다.

그런데 Claude Code는 플러그인의 `commands/`·`skills/`를 **세션 시작 시점에** 읽는다. 세션 도중
설치한 플러그인은 그 목록에 없으므로 스킬 호출이 `Unknown skill: <plugin>:setup` 으로 실패한다
(2026-08-04 실측). #21은 이 실패를 우아하게 처리하려고 **"설치했으면 위임을 시도하지 말고 재시작을
안내한다"**로 규정했다.

> **정정 (2026-08-05).** 위 원인 기술은 불완전했다. `core-dev`의 `setup`은 애초에 스킬이 아니라
> **커맨드**다(`plugins/core-dev/commands/setup.md`가 있고 `skills/setup/`은 없다). 따라서
> `Skill(skill: "core-dev:setup")`은 재시작 여부와 무관하게 성공할 수 없었다 — 세션 등록 시점은
> 두 번째 장애물이었을 뿐 첫 번째가 아니다. 채택한 해법(설치 경로의 스크립트를 직접 실행)은 두
> 원인을 모두 우회하므로 결정 자체는 바뀌지 않는다.

그 결과 doctor의 실사용 흐름이 이렇게 끊긴다:

```
플러그인 선택 → 설치 → "재시작 후 /<plugin>:setup 을 직접 실행하세요" → 종료
```

사용자가 기대한 것은 **선택 → 설치 → 필요한 것 점검 → 셋업**이 한 번에 끝나는 것이다. 설치만
하고 끝나는 doctor는 "설치 도구"이지 "환경을 갖춰주는 도구"가 아니다.

핵심은 **제약을 잘못 일반화**했다는 점이다. 세션 시작 등록이 필요한 것은 *스킬 호출*이지 *설정
작업 자체*가 아니다. `core-dev:setup`은 이미 얇은 래퍼이고 실제 점검·기록은
`scripts/setup.py`(stdlib only)가 한다. 스크립트는 **경로만 있으면 `Bash`로 실행된다** — 등록과
무관하다. 그리고 `installPath`는 설치가 끝나는 즉시
`~/.claude/plugins/installed_plugins.json`에 기록된다(2026-08-05 실측: 방금 설치한 core-dev의
`setup.py --check`가 재시작 없이 정상 동작).

즉 필요한 재료는 이미 전부 있었고, 위임 *수단*만 잘못 골라 두었던 것이다.

## 2. Decision (무엇)

### 2.1 플러그인이 지켜야 할 것

이 마켓플레이스의 모든 플러그인은 `scripts/setup.py`를 제공한다. 요구사항:

| 항목 | 계약 |
|---|---|
| 위치 | `plugins/<name>/scripts/setup.py` |
| 의존성 | **stdlib only** — doctor가 임의 환경에서 실행하므로 설치 절차가 있으면 안 된다 |
| `--check` | 읽기 전용. 무엇이 갖춰졌고 무엇이 비었는지 보고. 미해결이 있으면 exit 1 |
| `--fix` | **이미 해결 가능한 값만** 기록. 사용자에게 물어야 하는 값은 건드리지 않는다 |
| `--json` | `--check`의 기계 판독 형태. 아래 스키마 |
| `--set KEY=VALUE` | 사용자가 직접 값을 줄 때의 경로 |

`--json` 스키마(doctor가 의존하는 필드):

```json
{
  "plugin": "core-dev",
  "project": "/abs/path",
  "rows": [{
    "key": "STABLENET_KNOWLEDGE_CONFIG",
    "description": "무엇에 쓰는 값인지 — 사용자에게 그대로 보여진다",
    "how_to_find": "어디서 얻는지",
    "status": "missing | global | project | env | ...",
    "auto_fixable": false,
    "secret": false
  }],
  "missing": ["..."],
  "auto_fixable": ["..."]
}
```

**`description`이 계약에 들어 있는 이유**: doctor는 수정 여부를 `AskUserQuestion`으로 묻는다.
`STABLENET_KNOWLEDGE_CONFIG` 같은 변수명만 보여주면 사용자가 무엇을 승인하는지 알 수 없다.
용도 설명은 그 값을 정의한 플러그인만 쓸 수 있으므로 계약에 포함한다.

**`secret: true` 행은 값을 절대 싣지 않는다.** doctor의 출력은 대화 컨텍스트에 들어가므로,
시크릿은 `--json`에도 `--fix`의 로그에도 나타나면 안 된다. `--fix`가 시크릿을 쓰는 경우는
이미 해결된 값(설정 파일에 있던 것)을 옮길 때뿐이고, 새 값을 받는 경로는 `set-mcp-env.sh`다.

### 2.2 doctor가 지켜야 할 것

Step 4의 위임은 다음 순서로 한다:

1. `installed_plugins.json`에서 `installPath` 조회
2. `python3 "$P/scripts/setup.py" --check --json` 실행
3. 결과를 세 부류로 나눠 처리
   - `auto_fixable` → `AskUserQuestion` 다중 선택으로 **한 번에 묻고**, 각 항목에 `description`을
     붙인다. 승인 시 `--fix`
   - `missing` & 비시크릿 → `description` + `how_to_find`를 그대로 보여주고
     `--fix --set KEY=VALUE` 명령을 사용자에게 넘긴다
   - `missing` & 시크릿 → `set-mcp-env.sh`로 안내. doctor가 대신 실행하지 않는다
4. 스크립트가 없는 플러그인만 기존 스킬 경로 / 재시작 안내로 폴백

**doctor는 다른 플러그인의 요구사항을 알지 못한다**(ADR-0011 §2.2). `--json`의 내용을 요약하거나
재해석하지 않고, 그 플러그인의 권위 있는 진단으로 그대로 전달한다.

### 2.3 ADR-0008 체크리스트에 추가

신규 플러그인은 `scripts/setup.py`를 위 계약대로 제공한다. 설정할 환경값이 없는 플러그인은
스크립트를 두지 않아도 되지만, 그 경우 doctor는 **셋업이 필요 없는 것으로 간주**한다.

## 3. Consequences (결과)

**얻는 것**

- 설치 → 점검 → 셋업이 **한 세션에서 끊기지 않는다.** doctor의 원래 목적이 성립한다.
- 위임 원칙(ADR-0011 §2.2)이 그대로 유지된다. 바뀐 것은 위임의 *수단*뿐이고, 도메인 지식은
  여전히 소유 플러그인에 있다.
- 승인 대상이 변수명이 아니라 **용도 설명과 함께** 제시된다.
- doctor 쪽에 플러그인별 분기가 늘지 않는다 — 모든 플러그인이 같은 인터페이스를 갖는다.

**치르는 것**

- 신규 플러그인의 진입 비용이 스크립트 하나만큼 늘어난다. stdlib only 제약도 따라온다.
- `--json` 스키마가 doctor와 모든 플러그인 사이의 공개 계약이 된다. 필드를 바꾸려면 양쪽을
  같이 고쳐야 하고, 그래서 `core-dev`의 테스트가 이 스키마를 고정한다
  (`test_setup.py::TestJSONOutput`).

**해결되지 않는 것 — 오해하지 말 것**

스크립트 위임은 **설정**을 재시작 없이 끝내줄 뿐이다. 방금 설치한 플러그인의 **MCP 서버·에이전트·
슬래시 커맨드는 여전히 세션 재시작이 필요하다.** doctor는 셋업을 마친 뒤에도 그 사실을 계속
말해야 한다. 이 ADR은 "재시작이 필요 없다"가 아니라 "재시작 전에 할 수 있는 일을 미루지 않는다"는
결정이다.
