---
description: 플러그인·프로젝트 환경 진단(read-only). 버전·env·MCP·stablenet-knowledge·도메인팩 상태를 한 화면으로 보고하고, 빠진 것·재시작 필요·불일치를 알려준다. 아무것도 수정하지 않는다.
argument-hint: "[--project <id>] [--json]"
allowed-tools: Bash(python3:*), ToolSearch, mcp__plugin_stablenet-core-dev_stablenet-knowledge__cks_ops_health, mcp__plugin_stablenet-core-dev_stablenet-knowledge__cks_ops_freshness, mcp__plugin_stablenet-core-dev_chainbench__chainbench_status, mcp__plugin_stablenet-core-dev_jira-gateway__jira_read_ticket, mcp__plugin_stablenet-core-dev_jira-gateway__jira_search
---

# /stablenet-core-dev:doctor

읽기 전용 환경 진단. **아무것도 쓰지 않는다**(수정은 `/stablenet-core-dev:setup`). 결정론 진단(스크립트)
+ 라이브 MCP 프로브를 합쳐 **READY / ATTENTION** 과 다음 행동을 보고한다.

---

## 1. 결정론 진단 (스크립트)

```
bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py --plugin-root "${CLAUDE_PLUGIN_ROOT}" {--project <id> 인자 있으면}
```

보고: 활성 플러그인 버전, 프로젝트/repo(`git rev-parse`), project_id+사용가능 팩, `repo_root_env`,
env(process + `.claude/settings*.json`, 시크릿 마스킹, **restart_needed**=settings엔 있으나 현재 env엔
없음), STABLENET_KNOWLEDGE_CONFIG 존재, permissions/allowlist. 이 출력을 사용자 보고에 그대로 포함한다.

## 2. 라이브 MCP 프로브 (이 명령이 직접 — §1 스크립트로는 못 보는 실연결)

stablenet-knowledge 도구를 로드(미인식이면 ToolSearch 1회)한 뒤:

- `cks_ops_health` → status/serviceable, ckg·ckv reachable(+model), **source_root**, indexed_head, data_path.
- `cks_ops_freshness` → indexed_head vs current_head, changed_files.
- **정합 교차(핵심)**:
  - `source_root == §1 repo_root` 인가? 다르면 **⚠ 다른 체크아웃을 인덱싱** — 검색이 엉뚱한 트리 반영.
  - `indexed_head == 현재 HEAD` 인가? 아니면 stale(단, *의도된 base 인덱스*일 수 있음 — 판단만, 재인덱싱 금지).
  - `data_path`가 로컬 접근 가능하면 데이터셋 manifest(`{data_path 상위}/graph-db/manifest.json` 등)의
    `src_root`·`src_commit`을 health의 `source_root`·`indexed_head`와 대조. 다르면 **⚠ config가 인덱스와
    다른 체크아웃/커밋을 가리킴**(config 생성 시 `GO_STABLENET_ROOT` 폴백 사고 유형) → `source_root_mismatch`로 라우팅.
- chainbench: `chainbench_status`(또는 config 조회)로 연결/프로파일 확인. 미연결이면 보고(SKIPPED, 차단 아님).
- jira(`requirement_source != "local"` 일 때만): 가벼운 호출로 도달 확인. 미연결이면 보고.

각 MCP가 미등록/미연결이어도 **차단하지 않고 사실만 보고**한다.

## 3. 판정 + 다음 행동 (remediation)

수정 매핑의 **단일 소스는 `doctor.py`의 `REMEDIATION` 테이블**이다(ADR
[doctor-remediation-adr-2026-06-26](../../docs/adr/ADR-0004-doctor-remediation-routing.md)). 각 항목은
`klass`(`setup`=우리 setup.py가 해결 / `restart`=세션 재시작 / `manual`=재설정 / `external`=빌드·설치→docs/SETUP.md)로 분류된다.

1. **§1 스크립트가 이미 계산한 `remediations` 목록을 그대로 표시**한다(산문으로 재작성하지 말 것).
   스크립트는 이를 결정론적으로 출력하므로 doctor 보고의 "다음 행동" 절은 그 목록이다. 예: fresh repo →
   `setup --fix`(repo_root_env+env), `setup --fix --set`(시크릿), `setup --autonomous`(allowlist).
2. **§2 라이브 MCP 결과는 스크립트가 못 보므로, 같은 `REMEDIATION` 키로 라우팅**해 동일 형식으로 덧붙인다:
   - stablenet-knowledge not serviceable → `stablenet_knowledge_not_serviceable` (manual: ckv/Ollama 기동 또는 `STABLENET_KNOWLEDGE_CONFIG` 재배선 + 재시작)
   - `source_root ≠ repo_root` → `source_root_mismatch` (manual: 현재 repo를 인덱싱하도록 재설정 + 재시작)
   - index stale → `index_stale` (manual: 재인덱싱 — ⚠ *의도된 base 인덱스면 하지 말 것*, 사용자 확인)
   - MCP 미연결 → `mcp_unreachable` / `stablenet_knowledge_mcp_not_built` / `chainbench_not_installed`
3. 맨 끝에 스크립트의 **한 줄 요약**(`READY` / `ATTENTION — N action(s): <명령>`)을 그대로 노출한다.

**읽기 전용 계약**: doctor는 어떤 파일·설정·인덱스도 수정하지 않는다 — remediation은 *출력만* 하고, 실제 적용은
사용자가 해당 `setup` 명령을 호출한다.
