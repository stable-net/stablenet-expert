# 핸드오프: cks A/B/C 벤치 harness 완성 — "총비용 측정" 구현

> 이 문서는 `coding-agent` repo에서 띄운 세션에 그대로 붙여넣어 작업을 시작하기 위한 자립형 핸드오프다.
> 작성 맥락: cks(code-knowledge-system) repo 세션에서 남은 작업을 정리해 이관함.
> 원본 진단: `code-knowledge-system/docs/HANDOFF-cks-evaluation-remaining.md` §5.1.

---

## 0. 작업 한 줄 요약
cks A/B/C 벤치 harness를 보강해 **"옳은 수정까지의 총비용"**(Σ토큰 × bug-cycle)을 측정 가능하게 만든다. 수정 대상은 전부 `coding-agent` repo 안이며, cks repo와 chainbench repo는 건드리지 않는다.

## 1. 배경 (큰 그림)
- **검증 명제**: "cks(코드 그래프 ckg + 벡터 ckv를 합성한 검색) 도입 = 토큰↓ + 정확도↑"가 실제로 성립하는가.
- **시스템 경계**:
  - **cks** = planner의 정보원(검색/지식). 별도 repo. 이 작업에서 수정 안 함.
  - **coding-agent** = LLM 파이프라인 + 벤치 harness. ← **이 작업의 수정 대상.**
  - **chainbench** = evaluator가 쓰는 e2e 검증 도구. 외부/동시 세션 소유. **절대 수정 안 함.**
  - **go-stablenet** = 대상 코드. 벤치 실행 시에만 변경됨(throwaway).
- **A/B/C 모드**: 같은 태스크를 모델 고정(opus-4.7)으로 planner 정보원만 바꿔 비교.
  - **A_cks** = cks MCP / **B_code_only** = grep·read만(`bench-planner-codeonly`) / **C_code_skills** = grep+이해스킬(`bench-planner-skills`)
  - implementer·evaluator는 모드 불문 **공유** → planner의 정보 regime만 격리 비교.

## 2. ⭐ 방법론 (가장 중요 — 절대 누락 금지)
- 단일 싸이클(분석 단계) 토큰만 보면 cks는 더 비싸 보인다(다각도 검색이라 입력 큼). **이걸로 결론내면 틀린다.**
- 올바른 지표 = **"옳은 수정에 도달할 때까지의 총비용"**:
  - cks = 완전한 정보 → 첫 수정을 옳게 → 재작업(bug-cycle) 감소 → **총 토큰↓ + 정확도↑**.
  - B/C = 분석은 싸지만 → 불완전 정보 → 사이드이펙트/오수정 → EVALUATION_FAIL → bug-cycle 반복 → **총비용↑**.
- 따라서 측정 = **Σ(분석+구현+평가) × bug-cycle 수** + **사이드이펙트 적발/수정 정확성**.

## 3. 현재 상태 (검증 완료 — 아래가 빠져 있음)
1. **bug-cycle 재진입 루프 0건** → 셀이 evaluate **1회**만 돌고 종료(단발).
   - 확인: `plugin/skills/bench-orchestration/SKILL.md` §4.4 는 `a→g` 단발, step e(EVALUATION) 뒤 재진입 없음.
2. **compare.py가 단발 토큰만 집계** → `bug_cycles` / `Σ토큰` / `사이드이펙트` / `최종정확성` 없음.
   - 확인: `bench/compare.py` 는 per-cell correctness/safety/tokens/cost/latency만.
3. **EVALUATION_PASS 완주 셀 0건** (미검증).
4. **매니페스트가 `STABLE-0001` 단일 태스크뿐** → 편향.

## 4. 할 일

### (a) bench-orchestration에 bug-cycle 루프 추가
파일: `plugin/skills/bench-orchestration/SKILL.md` (§4.4 step e 뒤)
- `EVALUATION_FAIL` 이면 `config.max_eval_cycles`(기본 3)까지 **재-plan(또는 재-implement) → 재-evaluate** 반복.
- 싸이클마다 토큰·결과·failure를 셀 `state.json` / `run-meta.json` 에 누적 기록.
- ⚠️ 재-plan 시에도 해당 셀의 **모드 planner**(A=`planner` / B=`bench-planner-codeonly` / C=`bench-planner-skills`)를 써야 공정하다. shared `implementer`/`evaluator`는 그대로.
- **재사용**: 프로덕션 `plugin/agents/orchestrator.md` §5 에 이미 완성된 bug-cycle 상태기계가 있다
  (`EVALUATION_FAIL → cycle counter → max_eval_cycles → planner 재디스패치 OR BLOCKED`). 이 로직을 포팅하되 "모드별 planner" 차이만 반영.

### (b) compare.py 확장
파일: `bench/compare.py`
- per-cell에 추가: `bug_cycles`(횟수), `total_tokens`(Σ across cycles), `side_effect_catches`, `final_correctness`(EVALUATION_PASS 여부).
- 3-way 표(comparison.md)에 **"총 토큰 / bug-cycle / 사이드이펙트 / 정확성"** 컬럼 추가. (현재는 단발 correctness/safety/tokens/cost/latency만.)
- 토큰 출처: 셀 `logs/agent-transcript.jsonl` + `--sessions` 옵션(실토큰). **싸이클별 합산 로직** 추가.
- 실패 셀도 리포트 포함(정확성=실패). 누락 truncation 금지.

### (c) 태스크 다양화
파일: `bench/manifests/` , `bench/fixtures/tickets/`
- `STABLE-0001` 단일 → 여러 모듈 태스크로 확장: consensus/wbft, core/txpool, systemcontracts(거버넌스), state, miner 등. PR#77(Anzeon)은 **여러 케이스 중 하나로만**.
- 태스크는 `ticket.json` 형태(자유텍스트 요구사항 가능, `/coding-agent:analyze` 참고). 정답/AC를 명확히.

### (d) end-to-end 1셀 완주 검증
- 한 셀이라도 ANALYSIS→…→EVALUATION_PASS 완주 확인 후 전체 매니페스트 실행.
- ⚠️ 실제 벤치 실행은 별도 조건(아래 §5의 1·2). 코드 수정/dry 검증까지는 이 세션에서 가능, **본 실행은 사용자 승인 후.**

## 5. 주의사항 (반드시 숙지)
1. **chainbench는 손대지 않는다.** 회귀 환경 정비(`get_running_node_ids`, 프로파일 펀딩 등)는 외부/동시 세션 소유다. chainbench가 불완전하면 해당 정확성 칸을 **"부분 검증"으로 표기만** 한다. harness의 토큰·cycle 회계는 chainbench 상태와 무관하게 구현·검증 가능하다.
2. **실제 A/B/C 본 실행은 go-stablenet을 변경하고 무겁다**(모드3 × 태스크N × 파이프라인 × bug-cycle). bypassPermissions 세션 필요 → autopilot 런처 `code-knowledge-system/scripts/coding-agent.sh` 로 go-stablenet에서 기동.
3. **🔴 데이터셋 오염 방지**: 벤치가 만든 throwaway 브랜치/커밋을 반드시 정리해야 한다(안 그러면 다음 CKG 재빌드 때 가짜 코드 유입 — 과거 실제 발생). 정리: 캐노니컬 브랜치 checkout → `git branch -D <테스트브랜치>` → `git reflog expire --expire-unreachable=now --all && git gc --prune=now`.
4. **코드 수정은 어느 세션에서 해도 무방**하나, **본 실행만 autopilot 세션 요구.**

## 6. 레퍼런스
- 원본 핸드오프: `code-knowledge-system/docs/HANDOFF-cks-evaluation-remaining.md` (§5.1 = 이 작업)
- 후속 계획(thesis 분기): `coding-agent/docs./archive/followup-plan.md`
  (✅ retrieval-thesis는 CKG eval Report v5~v8로 거의 측정됨 / ⏳ 이 작업 = full-pipeline-thesis, chainbench(item C)에 의존)
- 벤치 harness: `plugin/skills/bench-orchestration/SKILL.md`, `plugin/commands/bench.md`,
  `plugin/agents/bench-planner-{codeonly,skills}.md`, `plugin/agents/orchestrator.md`,
  `bench/compare.py`, `bench/manifest.schema.json`, `bench/prices.json`
- 셀 산출물 경로: `go-stablenet/.coding-agent/bench/<experiment>/cells/<task>__<mode>/`
  (state.json, analysis/plan/design, test-report.md, run-meta.json, logs/agent-transcript.jsonl)

## 7. 진행 방식
- (a)(b)(c) 코드 보강 먼저(외부 의존 없음) → (d) 1셀 dry 완주 검증.
- 본 매니페스트 실행은 사용자에게 확인받고 autopilot 세션에서.
- 먼저 위 파일들을 읽고 현재 구조를 파악한 뒤, **(a)부터 착수할 계획을 제시**해라.
