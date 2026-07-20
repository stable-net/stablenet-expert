# ADR — `/stablenet-core-dev:setup` 확장 + `/stablenet-core-dev:doctor` (환경 셋업·진단)

문서 성격: **ADR / 설계 결정 (ACCEPTED 2026-06-23 — 설계 합의됨, 코드 변경 0).** 짝:
[`scripts/setup.py`](../../plugin/scripts/setup.py)(기존 셋업) · [`domain-pack-contract-adr-2026-06-22.md`](./ADR-0001-domain-pack-contract.md)(repo_root_env 출처).

> **구현 상태 갱신 (코드 검증 2026-06-28):** 구현됨. `plugin/commands/{setup,doctor}.md`·
> `plugin/scripts/{setup,doctor}.py` 존재, PR #22·#23 머지 (v0.1.30). 위 "코드 변경 0"은 작성 시점 기준.

> **결정 한 줄:** "go-stablenet 루트에서 claude 실행 → 플러그인 명령으로 작업"이라는 실사용 흐름에서,
> **(1) `setup`이 의사결정을 묻지 않고** repo_root_env(=현재 repo 루트)·env·allowlist를 settings에 기록하고,
> **(2) `doctor`가** 플러그인·env·MCP·stablenet-knowledge·도메인팩 상태를 한 화면으로 진단한다. 둘 다 비교란 additive.

---

## 1. Context (왜)

실사용: `cd go-stablenet && claude` → `/stablenet-core-dev:*` 명령으로 작업. 이번 세션에서 반복된 마찰:
- `GO_STABLENET_ROOT` unset(도메인팩 `verification.repo_root_env` fallback이 빔),
- stablenet-knowledge `source_root`가 엉뚱한 체크아웃을 가리킴(인덱스는 base인데 live HEAD 이동),
- 설치 캐시 버전 vs main 버전 혼동, MCP 재연결 필요 여부 불명,
- 작업 중 권한(의사결정) 프롬프트.

기존 `setup.py`(--check/--fix, stablenet-knowledge/jira/chainbench env를 `.claude/settings.json`에 기록)와
orchestrator §2.0 MCP 프리플라이트가 일부 커버하나, **사용자-호출 진단**과 **repo_root_env·allowlist
자동화**가 없다. 이 ADR가 그 갭을 메운다.

---

## 2. Decision 1 — `/stablenet-core-dev:doctor` (read-only 진단)

한 번 실행으로 상태 리포트(쓰기 없음):

| 섹션 | 보고 내용 |
|---|---|
| 플러그인 | 활성(설치 캐시) 버전 vs 소스/최신, 설치 경로 |
| 프로젝트 | cwd, git repo 여부, repo 루트, **project_id 해석 + `domains/{id}` 팩 존재** |
| env | `{repo_root_env}`(예 `GO_STABLENET_ROOT`)·`STABLENET_KNOWLEDGE_CONFIG`·`STABLENET_KNOWLEDGE_MCP_BIN`·`CHAINBENCH_DIR`·`JIRA_*` — set/unset·값(시크릿 마스킹)·출처(process env vs settings.json) |
| MCP | stablenet-knowledge `ops.health`(serviceable?)·chainbench 연결·jira 도달 |
| stablenet-knowledge⇄repo 정합 | `source_root == repo 루트?` · `indexed_head == 현재 HEAD?`(freshness) — **이번에 데인 불일치 탐지** |
| 권한 | `permissions.defaultMode` + 플러그인 도구/명령 allowlist 여부 |
| 판정 | READY / 빠진 것[] / **재시작 필요 플래그**(settings엔 있으나 현재 env엔 없음) |

구현: 새 `commands/doctor.md` + 진단 로직(대부분 read-only bash + stablenet-knowledge/chainbench MCP health 호출).
결정론적(상태 조회)이라 테스트 용이.

---

## 3. Decision 2 — `/stablenet-core-dev:setup` 확장

기존 setup.py에 추가:
1. **repo_root_env 자동 set** — `git rev-parse --show-toplevel`로 repo 루트를 구하고, **활성 도메인팩의
   `verification.repo_root_env` 이름**(go-stablenet=`GO_STABLENET_ROOT`)으로 그 값을 `.claude/settings.json`
   `env`에 기록. 도메인팩 연계로 *generic*(프로젝트마다 자기 env 이름).
2. **allowlist 등록 (opt-in `--autonomous`)** — 플러그인 MCP 도구·명령·안전 bash 패턴을
   `permissions.allow`에 추가(또는 `permissions.defaultMode`). 작업 중 의사결정 프롬프트 제거.
3. **출력** — 변경분 + "env/permissions는 **세션 재시작 후 적용**".

---

## 4. 메커니즘 + 제약 (정직하게)

- **settings.json env·permissions는 세션 시작 시 로드** → setup은 *기록*만, 적용엔 **재시작 필요**.
  doctor가 "set됐으나 현재 env엔 없음 → 재시작" 플래그로 감지. (메모리: `/reload-plugins ≠ MCP/env 재시작`.)
- **repo_root는 사실 `git rev-parse`로도 흐른다**(work.md) → repo_root_env set은 *fallback 보강·명시화*이지
  필수는 아니다(generalized evaluator는 dispatch repo_root가 primary). 그래도 혼동 제거 위해 set 권장.
- **allowlist 자동등록은 opt-in** — 광범위 권한은 안전 결정. 기본은 안 함(setup.py도 bypassPermissions 미자동).
- **시크릿**(JIRA_API_TOKEN)은 `settings.local.json`(gitignored), doctor에선 마스킹.

---

## 5. Decisions (모두 확정, 2026-06-23)

1. **project_id 탐지** — ✅ **auto-detect + `--project` 폴백.** repo를 `domains/{id}`에 매핑:
   repo remote/dir 또는 마커로 auto-detect → 실패 시 단일 팩이면 그걸, 아니면 `--project <id>` 요구.
2. **allowlist** — ✅ **granular `permissions.allow`.** 플러그인 MCP 도구(stablenet-knowledge/chainbench/jira)·
   `/stablenet-core-dev:*` 명령·안전 read-only bash 패턴만 등록(범위 최소). `--autonomous`로 opt-in.
3. **repo_root_env** — ✅ **setup `--fix`가 자동 기록.** `git rev-parse --show-toplevel` → 활성 팩
   `verification.repo_root_env` 이름으로 `.claude/settings.json` `env`에 write.
4. **doctor MCP 확인** — ✅ **라이브 health 프로브.** stablenet-knowledge `ops.health`/`ops_freshness`·chainbench·jira를
   실제 호출해 serviceable·source_root·indexed_head 정합까지 확인.

---

## 6. Build 계획 (비교란 additive) — ✅ 구현 완료 (06-23)
1. ✅ **doctor** (read-only) — `scripts/doctor.py` + `commands/doctor.md` + tests 6/6. **PR #22 머지**.
2. ✅ **setup 확장** (repo_root_env auto-set + `--autonomous` allowlist) — `scripts/setup.py` +
   `commands/setup.md` + `tests/test_setup.py` 6/6. **PR #23 머지** (main v0.1.30).
각 단계 overlay-gates 무회귀 PASS. 실사용 흐름: `cd <project-root> && claude` →
`/stablenet-core-dev:setup --fix --autonomous` → 세션 재시작 → `/stablenet-core-dev:doctor`(READY) → 작업.
**잔여(설계상 한계, 코드 아님)**: settings env/permissions는 세션 재시작 후 적용(doctor가 플래그);
write 액션 무프롬프트는 `permissions.defaultMode` 사용자 추가(자동 안 함, 보안).

## 7. Consequences / Residuals
- **+**: 세션당 환경 마찰 제거, env/MCP 가독성, 의사결정 프롬프트 감소.
- **−/제약**: env/permissions 적용에 재시작 불가피(doctor가 안내). allowlist는 opt-in(안전).
- 도메인팩 연계로 다중 프로젝트에도 generic하게 확장 가능(P1과 정합).
