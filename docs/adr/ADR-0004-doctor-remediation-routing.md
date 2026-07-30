# ADR — doctor→setup remediation routing + single-source fix table (P-A + P-B)

문서 성격: **ADR / 설계 결정 (ACCEPTED 2026-06-26 — fix-table는 doctor.py 내 데이터로 합의).** 짝:
[`scripts/doctor.py`](../../plugins/core-dev/scripts/doctor.py) · [`commands/doctor.md`](../../plugins/core-dev/commands/doctor.md) ·
[`scripts/setup.py`](../../plugins/core-dev/scripts/setup.py) · 선행 [`setup-doctor-adr-2026-06-23.md`](./ADR-0002-setup-and-doctor.md).
참조 사례: midnight-expert 마켓플레이스(`references/midnight-expert`)의 2단 doctor + `fix-table.md`.

> **결정 한 줄:** doctor가 감지하는 **모든** 결함을 빠짐없이 정확한 다음 행동(주로 `/core-dev:setup`)으로
> 라우팅한다. 그 매핑을 doctor.py 안의 **단일 데이터 테이블(REMEDIATION)** 로 두고, issue를 구조화하여
> render에 **Remediation 섹션 + 한 줄 요약**을 추가한다. 진단은 결정론(Python) 유지, 수정은 **데이터로 분리**.
> 범위는 P-A(라우팅)+P-B(fix-table)까지. **setup이 바이너리를 설치하는 P-C는 이 ADR 범위 밖**(별도 합의).

---

## 1. Context (왜)

선행 ADR(setup-doctor)로 doctor=read-only 진단, setup=write가 분리됐다. 그러나 실사용에서 갭:

- doctor의 수정 안내가 **부분적·산문적**이다. `commands/doctor.md §3`이 일부 케이스(`repo_root_env` unset,
  permissions 미등록)만 `/core-dev:setup`으로 라우팅하고, `doctor.py`가 낼 수 있는 다른 결함
  (`STABLENET_KNOWLEDGE_CONFIG` 파일 없음, MCP not-serviceable, source_root 불일치, index stale, chainbench/jira 미연결)에는
  "다음에 뭘 하라"가 **체계적으로 붙지 않는다**.
- 결함→수정 매핑이 **한 곳에 없다**(doctor.md 산문 + docs/SETUP.md 산재). 새 체크를 추가하면 안내가 누락되기 쉽다.
- `doctor.py`의 `issues`는 **맨 문자열**이라 "다음 행동"이 데이터로 존재하지 않는다 → 기계 검증 불가.

참조 사례(midnight-expert)의 강점은 정확히 이 부분이다: **detection(결정론 bash) ↔ fix(데이터 표 `fix-table.md`)
분리**, 그리고 진단→수정→재검증의 닫힌 루프. 단 그쪽은 bash 출력 텍스트를 **LLM이 파싱**해 비결정론이다.
우리는 그 *분리 패턴*만 취하고, 진단의 결정론(단일 Python·시크릿 마스킹·`restart_needed`)은 유지한다.

---

## 2. Decision (무엇을)

### 2.1 P-A — doctor가 모든 결함을 다음 행동으로 라우팅

`doctor.py`:
- `issues`를 맨 문자열 → **구조화** `{kind, detail, fix}`로 바꾼다. `fix`는 §2.2 테이블에서 해석.
- `render()`에 **Remediation 섹션**과 맨 끝 **한 줄 요약** 추가:
  `READY` 또는 `ATTENTION — N action(s): <대표 명령 나열>`.
- `restart_needed`는 항상 "세션 재시작" 행동으로 매핑.

`commands/doctor.md §3`:
- §1 스크립트가 이미 계산한 remediation 목록을 **그대로 표시**한다(LLM이 산문으로 재작성하지 않음).
- 스크립트가 못 보는 **라이브 MCP 프로브** 결과(source_root 불일치, not-serviceable, stale, chainbench/jira
  미연결)도 **같은 fix-table 키**를 거쳐 동일한 형식으로 라우팅한다.

### 2.2 P-B — 단일 소스 fix-table (doctor.py 내 데이터)

`doctor.py`에 `REMEDIATION: dict[kind -> {action, command, klass}]` 추가. `klass`(분류)는 midnight-expert의
auto-fix 분류를 차용:

| klass | 의미 | 예 |
|---|---|---|
| `setup` | 우리 `setup.py`가 해결(write) | env MISSING→`setup --fix`; allowlist 없음→`setup --autonomous` |
| `restart` | settings엔 있으나 현재 env에 없음 → 세션 재시작 | `repo_root_env` restart_needed |
| `manual` | 사용자 결정·재설정(쓰기 위험·취향) | source_root≠repo_root → stablenet-knowledge config 재배선 후 재시작; index stale(의도된 base일 수 있음 → 확인) |
| `external` | 외부·빌드·설치(이 범위 밖, 문서로 안내) | stablenet-knowledge-mcp 미빌드, chainbench 미설치, `STABLENET_KNOWLEDGE_CONFIG` 파일 없음 → docs/SETUP.md |

테이블은 **데이터**이므로 새 체크 추가 시 한 곳만 고치면 되고, 아래 게이트로 누락을 막는다.

### 2.3 기계 검증 (게이트)

`bench/`(또는 `plugins/core-dev/scripts/tests/test_doctor.py`)에 **커버리지 게이트**:
- doctor.py가 emit할 수 있는 모든 `kind`가 `REMEDIATION`에 항목을 가진다(orphan issue 0).
- `--json` 출력의 각 issue에 비어있지 않은 `fix.command`(또는 external 안내)가 붙는다.
- `klass`는 허용된 4값 중 하나.
overlay-gates에 편입(무회귀).

---

## 3. 메커니즘 + 제약 (정직하게)

- **진단은 여전히 read-only.** doctor는 remediation을 *출력*만 한다. 실제 쓰기는 사용자가 `setup`을 호출(계약 유지).
- **fix-table를 doctor.py 데이터로 두는 이유**: 참조 사례는 `fix-table.md`(마크다운)지만, 우리는 진단이 단일
  Python이라 **같은 파일 내 데이터**가 결정론·테스트·단일소스에 더 맞는다. 마크다운 표는 LLM 파싱이 필요하고
  코드 진단과 동기화가 끊기기 쉽다. (산문 설명은 doctor.md에 남기되, 권위 출처는 doctor.py 테이블.)
- **P-C 제외**: setup이 stablenet-knowledge-mcp 빌드/chainbench 설치를 직접 수행하는 것은 비용·외부 안전성 검토가 필요 →
  별도 ADR. 지금은 `external` klass로 **문서 라우팅**까지만.
- **LIVE MCP 결과의 fix 키**: 스크립트가 못 보는 항목이라 doctor.md가 키를 부여하지만, 키 문자열은 doctor.py
  `REMEDIATION`에 미리 정의해 단일 소스를 유지한다(doctor.md는 키만 참조).

---

## 4. 비범위 / 변경 없음

- `setup.py` 동작 불변(이번엔 install 기능 추가 없음).
- doctor read-only 계약 불변.
- 도메인팩·파이프라인 에이전트 불변(additive).

---

## 5. Build 계획 (additive)

1. `doctor.py`: `REMEDIATION` 테이블 + `issues` 구조화 + `render()` Remediation 섹션/요약 + `--json` 스키마 확장.
2. `commands/doctor.md`: §3을 "스크립트 remediation 그대로 표시 + 라이브 MCP 결과를 같은 키로 라우팅"으로 개정.
3. `tests/test_doctor.py`: 커버리지 게이트 + render/JSON 단언. overlay-gates 편입.
4. 무회귀 PASS → 버전 bump → PR(English, 핵심만, no co-author, no emoji).

## 6. Consequences

- **+**: 진단이 항상 "다음 한 줄"로 끝남(닫힌 루프 시작점), 매핑 단일 소스·기계 검증, 새 체크 누락 방지.
- **−/제약**: 실제 적용은 여전히 사용자의 setup 호출 필요(read-only 유지). 외부 빌드는 문서 안내까지만(P-C 대기).
- 후속: P-C(setup install) · 적용 후 영향 체크만 재검증하는 verify 루프(P-D).
