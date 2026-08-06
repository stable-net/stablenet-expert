---
description: core-dev 동작에 필요한 settings.json 설정을 점검하고, 빠졌으면 자동탐지·대화형으로 등록한다.
argument-hint: "[--check | --fix] [--autonomous] [--project <id>]   (생략 시 점검 후 등록 제안)"
---

# /core-dev:setup

설치 직후 `core-dev` 가 바로 동작하도록, 플러그인 MCP 서버(.mcp.json)가 요구하는
환경값이 프로젝트 설정에 등록돼 있는지 **점검**하고, 빠진 값은 **자동탐지 → 못 찾으면
대화형 입력**으로 채워 넣는다.

- 경로·공개값 → `{repo_root}/.claude/settings.json` 의 `env`
- 시크릿 → `{repo_root}/.claude/settings.local.json` (자동 .gitignore). 현재 시크릿 항목은 없다 —
  Jira 는 OAuth 로 인증하고 자격증명은 Claude Code 가 보관한다(ADR-0013).
- **활성 도메인팩의 `repo_root_env`(예 `GO_STABLENET_ROOT`) → 현재 repo 루트로 `settings.json` 에 자동 기록**
  (현재 폴더에서 실행 시; project_id 모호하면 `--project <id>`).
- **`--autonomous`**: granular `permissions.allow`(플러그인 MCP + read-only bash + 파이프라인 write path:
  Write/Edit·go/make 빌드·feature-branch git·gh pr create)와 `permissions.deny`(`.env*`·`.secrets`·
  `settings.local.json` Read 차단)를 `settings.local.json` 에 등록(무프롬프트 opt-in).
  merge/tag/release 는 allowlist 에 없다 — `/core-dev:merge` 게이트와 git-guard hook 이 유지된다.

스크립트 `${CLAUDE_PLUGIN_ROOT}/scripts/setup.py` 가 실제 점검·기록을 수행한다(stdlib only).

> 점검 항목: `STABLENET_KNOWLEDGE_MCP_BIN`, `STABLENET_KNOWLEDGE_CONFIG`, `CHAINBENCH_DIR`,
> Atlassian MCP 플러그인(설치·인증 상태), 그리고
> `chainbench-mcp` PATH·`permissions` 권고.

---

## 0. 인자 (사용자가 준 플래그를 그대로 setup.py 에 전달)
- 기본(인자 없음): 점검(--check 동등) → 미완이면 §2 로 등록 제안·수행.
- `--check`: 점검만(기록 안 함).
- `--fix`: env 를 settings.json 에 기록(활성 팩 `repo_root_env` 포함 — 단 cwd 가 plugin repo 면 MISMATCH 로 건너뜀).
- `--autonomous`: granular allow/deny 등록(**`--fix` 없이도 동작**).
- `--project <id>`: 활성 도메인팩 명시(auto-detect 모호 시).

## 1. 실행 (플래그 전달)
```
1.1. bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py {사용자 플래그; 없으면 --check}
     # 예: /core-dev:setup --autonomous        → setup.py --autonomous (allowlist 등록)
     #     /core-dev:setup --fix --autonomous   → env + repo_root_env + allowlist 기록
1.2. 출력 표·기록 결과를 사용자에게 그대로 보여준다(KEY/STATUS/SOURCE).
1.3. repo_root_env 가 **MISMATCH** 면 안내: "현재 plugin repo 라 repo_root_env 미기록 —
     실제 작업은 타깃 프로젝트(예: go-stablenet) 루트에서 setup 을 실행하라."
1.4. exit 0 이고 (--fix/--autonomous 없이) 전부 해소 → 종료: "설정이 모두 갖춰져 있습니다."
     MISSING 이 있으면 §2.
```

## 2. 미완 항목 처리 (자동탐지 → 대화형)
```
2.1. MISSING 항목이 있으면, 먼저 자동탐지·기존 env 로 채울 수 있는 값만 기록:
     bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py --fix
     (탐지/env 로 찾은 경로값을 .claude/settings.json 에 병합. 이미 있는 값은 보존.)

2.2. 그래도 남은 MISSING(주로 Jira URL/이메일/토큰, 또는 탐지 실패한 경로):
     사용자에게 각 값을 물어본다(시크릿은 화면에 노출하지 않도록 주의 안내).
     받은 값으로 재실행:
     bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py --fix \
             --set KEY1=VALUE1 --set KEY2=VALUE2 ...
     # 시크릿이 생기면 --set 로 전달 → 스크립트가 settings.local.json 에 기록하고
     #   .claude/settings.local.json 을 .gitignore 에 추가한다.
     # 사용자가 터미널에서 직접 채우고 싶어 하면 안내: `! python3 .../setup.py --fix --interactive`

2.3. 재점검:
     bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py --check
     여전히 MISSING 이면 무엇이 왜 빠졌는지 보고하고, 해당 항목의 설치/빌드 방법을
     docs/SETUP.md 기준으로 안내(예: stablenet-knowledge-mcp 빌드, chainbench 설치).
```

## 3. 마무리 안내
```
3.1. 기록 완료 시:
     - "settings.json/settings.local.json 에 등록 완료. MCP 서버가 새 env 를 읽도록
        세션을 재시작하세요(exit → claude --continue). /reload-plugins 는 MCP 를 재시작하지 않습니다."
     - chainbench-mcp 가 PATH 에 없으면 그 설치 안내.
     - `--fix` 는 **활성 팩 repo_root_env(예 `GO_STABLENET_ROOT`)를 현재 repo 루트로 자동 기록** —
       `git rev-parse` 로도 흐르지만 명시화로 혼동 제거. project_id 모호 시 `--project <id>`.
     - 무프롬프트가 필요하면 `--autonomous` 로 granular allow(플러그인 MCP + read-only bash +
       Write/Edit·빌드·feature-branch git) + deny(시크릿 Read 차단) 등록. merge/tag 는 여전히 프롬프트
       (또는 `/core-dev:merge`). 그 밖의 도구까지 전면 무프롬프트는 `permissions.defaultMode` 사용자 설정
       (자동 설정 안 함 — 보안).
```

## 4. 완료 기준 (체크리스트)
- [ ] setup.py --check 결과 표를 사용자에게 출력
- [ ] 자동탐지·기존 env 로 채울 수 있는 값은 --fix 로 .claude/settings.json 에 병합(기존값 보존)
- [ ] 못 찾은 값은 대화형으로 받아 --set 로 기록(시크릿은 settings.local.json + .gitignore)
- [ ] 재점검으로 해소 확인, 남으면 설치/빌드 방법 안내
- [ ] 세션 재시작 안내(MCP env 반영)
