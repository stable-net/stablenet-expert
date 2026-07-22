# WORKLIST — 잔여 작업 (Tier 3)

> **Tier 3 (상태/잔여작업).** dated·disposable, 코드+git에서 재생성 가능. 완료된 항목은
> 삭제한다(이력 보존이 목적이 아니다 — 그건 git log가 한다). 새 항목은 발견 즉시 추가한다.

---

## 커맨드 레벨 메타데이터

- [ ] **`commands/merge.md`의 `description`이 영어, 나머지 8개 커맨드는 한글** — 언어 일관성이
  깨져 있다. `analyze`/`bench`/`diagnose`/`doc-organize`/`doctor`/`review`/`setup`/`status`/`work`
  전부 한글 설명인데 `merge`만 "Squash-merge an approved PR, transition Jira to Complete, and
  clean up the local branch."로 영어. 한글로 통일할지, 전체를 영어로 통일할지 결정 필요.

## 에이전트 레벨 메타데이터

- [ ] **모델 핀 `exec` 티어가 구식** — `bench/model-pins/models.json`의 `tiers.exec` =
  `claude-sonnet-4-6`(→ `implementer`/`evaluator`에 적용됨)가 최신 세대가 아님. `deep` 티어는
  `claude-opus-4-8`로 최신. 업그레이드 절차: `models.json`의 `exec` 값을 갱신 →
  `python3 bench/model-pins/check.py --apply`로 9개 agent frontmatter에 전파 →
  `bench/prices.json`에 새 모델의 가격 행 추가 → `python3 bench/model-pins/check.py`로 재검증.
  (참고: `name`/파일명/`models.json`의 `agents` 매핑 3자 정합성은 이번에 대조 확인해 문제 없음 —
  실제 액션이 필요한 항목은 `exec` 모델 값 자체뿐.)

## 라이선스 정합성

- [ ] **`plugins/core-dev/.claude-plugin/plugin.json`(`GPL-3.0-or-later`) vs 저장소 루트 `LICENSE`
  파일(실제 확인 결과 `AGPL-3.0`, 최초 이관 커밋부터 그랬음) — 두 라이선스가 서로 다르다.**
  README는 실제 `LICENSE` 파일 내용(AGPL-3.0)에 맞춰 이미 정정함. 남은 결정: 플러그인도
  AGPL-3.0으로 통일할지, 아니면 플러그인=GPL-3.0-or-later / 저장소=AGPL-3.0 이원화를 의도적으로
  유지할지(둘 다 go-stablenet dual-license의 강한 쪽보다도 더 강한 조합이라 법적으로 문제는 없으나,
  왜 다른지 근거가 문서화돼 있지 않음).

## `agent-mcp.schema.json` — 제거된 `Citation`/`PRRef` 타입 정의 (미래 참고용)

`scripts/contract/agent-mcp.schema.json`의 `definitions.Citation`/`definitions.PRRef`를 삭제했다
(2026-07-21 스키마 감사) — 스키마 어디에서도 `$ref`로 참조되지 않는 죽은 정의였다. 삭제 전 확인한
사실을 남긴다:

- **`Citation`**(`{file, start_line, end_line}`)은 `stablenet-knowledge` 계열 도구(`cks_context_get_for_task`
  등)가 반환하는 evidence pack의 citation 항목을 타입으로 표현하려던 것으로 보인다. 실제로 이
  shape는 `bench/stablenet-knowledge-bench/bench_io/envelope.py`의 `Citation` dataclass로 **독립적으로
  이미 구현되어 있다** — 단, 필드가 `file, start_line, end_line, symbol` 4개로 스키마의 3개보다 하나
  많다(`symbol` 누락). 두 정의가 서로 모른 채 따로 진화한 상태.
- **`PRRef`**(`{number, title, merged_at}`)는 `cks_context_change_history`의 "PR refs (provenance)" 반환
  형태를 표현하려던 것으로 보이나, 저장소 어디에도 대응 구현체가 없다(Python/Go 어느 쪽에도 없음) —
  아마 계획만 되고 구현되지 않았다.
- 현재 스키마의 모든 `stablenet-knowledge` 도구는 `input`만 정의돼 있고 `output` 스키마가 없다
  (`chainbench_report`만 예외적으로 `output`을 정의함). **만약 나중에 도구 출력 타입을 스키마에
  추가하는 작업을 한다면**, `bench/stablenet-knowledge-bench/bench_io/envelope.py`의 `Citation`을
  기준으로 `symbol` 필드를 포함해 다시 정의하는 게 맞다(위 4-필드 버전이 실제 운영 코드가 검증한
  형태이므로).
