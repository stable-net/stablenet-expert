---
name: bench-orchestration
description: "동일 go-stablenet 태스크를 A(cks)/B(code-only)/C(code+skills) 3모드로 자율 실행하고 토큰·비용·정확성·안전성을 비교하는 harness-engineering 오케스트레이션. token limit 고려 배치+checkpoint/resume. /stablenet-core-dev:bench 가 호출."
type: skill
---

# Bench Orchestration (3-way comparison automation)

이 skill은 harness-engineering automation의 코어다. 하나의 실험 manifest(태스크 ×
모드)를 받아, **같은 태스크를 세 접근법(regime)으로 자율 실행**하고 결과를 비교한다.

> **정의 정본: [`docs/bench-abc-mode-definitions.md`](../../../docs/bench-abc-mode-definitions.md).**
> A/B/C는 *분석-단계 변이*가 아니라 **접근법 전체 비교**다(이전 "분석만 하고 공유
> 파이프라인으로 넘기는" 정의는 supersede됨).

- **A_stablenet_knowledge_mcp** — stablenet-core-dev 전체 파이프라인: 실제 `analyzer`(cks) → planner → implementer → evaluator.
- **B_code_only** — stablenet-core-dev ❌ · 프로젝트 .claude ❌. `bench-solver-codeonly`가 **타깃 코드 + grep만으로
  단독 완주**(진단→수정→회귀테스트). evaluator는 **측정 전용 referee**로만 공유(해결 개입 X).
- **C_project_skills** — stablenet-core-dev ❌ · cks ❌. `bench-solver-project-skills`가 **타깃 프로젝트 자신의
  `.claude`**(`/stablenet-review-code` 등)로 **단독 완주**. evaluator는 측정 전용 referee로만 공유.

세 모드 모두 모델은 `claude-opus-4-8`로 고정 — 비교는 *접근법 regime*을 격리한다.
**B/C 격리는 도구·스킬 부재로 하드 보장**(프롬프트 의존 아님): solver 에이전트에 cks·stablenet-core-dev
스킬을 부여하지 않는다. 측정은 결정적 tool(`bench/compare.py`), 구동은 이 skill + Agent tool +
transcript hook. (모델 비대칭 주의: A는 implement가 sonnet, B/C는 단일 solver라 opus 단독 —
정의 문서 §5b의 알려진 caveat.)

> **Token-limit 인지.** plugin-native 실행은 사용자의 현재 세션 한도 안에서 돈다.
> 그래서 이 skill은 **한 번에 batch_size 셀만** 실행하고 checkpoint 후 멈춘다.
> 이어서 `/stablenet-core-dev:bench <experiment> --continue` 로 재개한다. 절대 한 번에
> 전체 매트릭스를 돌리지 않는다.

---

## 1. 실험 레이아웃 (state + checkpoint 계약)

```
.stablenet-expert/bench/{experiment}/
├── manifest.json          # 실험 정의(아래 §2)를 복사
├── state.json             # 셀 상태(아래 §3) — resume의 단일 진실
├── cells/
│   └── {task}__{mode}/    # 셀별 실행 워크스페이스 = 일반 ticket 워크스페이스 + run-meta.json
│       ├── run-meta.json  # { experiment, task, mode, mode_agent, started_at, ended_at, bug_cycles }
│       ├── state.json     # 파이프라인 state (state-machine) — failure_log = bug-cycle 회계 원천
│       ├── logs/agent-transcript.jsonl   # transcript hook가 기록(P4) → 토큰 회계 원천(전 싸이클 누적)
│       ├── analysis.md / plan.md / plan-fix-{cycle}.md / design-v*.md / test-report.md
│       └── ...
└── report/                # bench/compare.py 산출물(md/json/csv)
```

## 2. Manifest (입력)

`bench/manifests/*.json` (스키마: `bench/manifest.schema.json`):

```jsonc
{
  "experiment": "gsn-retrieval-abc-2026-06",
  "modes": ["A_stablenet_knowledge_mcp", "B_code_only", "C_project_skills"],
  "mode_agents": {                       // 모드 → SOLVE agent (A=ANALYSIS / B·C=whole-approach solver)
    "A_stablenet_knowledge_mcp":           "analyzer",
    "B_code_only":     "bench-solver-codeonly",
    "C_project_skills": "bench-solver-project-skills"
  },
  "shared_agents": { "plan": "planner", "implement": "implementer", "evaluate": "evaluator" },
  "tasks": [
    { "id": "STABLE-0001",
      "ticket": "bench/fixtures/tickets/STABLE-0001.json",
      "oracle": { "chainbench_test": "basic/consensus" } }
  ],
  "go_stablenet_root": "../go-stablenet",  // 경로 해석 규칙은 아래 참조
  "batch_size": 1,                       // 한 invocation당 실행할 셀 수(token 한계)
  "config": { "max_eval_cycles": 3 }     // 셀당 bug-cycle 상한(§4.4 step e). 미지정 시 3.
}
```

**경로 해석 규칙(머신 이식성)**: manifest 안의 경로 필드(`go_stablenet_root`, `_requires.*` 등)에서
**상대경로는 stablenet-core-dev 체크아웃 루트 기준으로 해석**한다 — sibling 레이아웃(docs/SETUP.md §2)에서
sibling 레포는 `../<repo>`(예: `../go-stablenet`). git에 커밋되는 manifest에는 머신 절대경로를 넣지
않는다 — 절대경로는 머신-로컬 오버라이드(비커밋 manifest 사본)에서만 허용. 해석 후 경로가 존재하지
않으면 실행 전에 fail-loud로 중단한다.

셀 집합 = `tasks × modes` (예: 1 task × 3 modes = 3 cells).

## 3. state.json (재개의 단일 진실)

```jsonc
{
  "experiment": "...",
  "created_at": "...", "updated_at": "...",
  "cells": [
    { "task": "STABLE-0001", "mode": "A_stablenet_knowledge_mcp", "workspace": "cells/STABLE-0001__A_cks",
      "status": "pending|running|done|failed",
      "pipeline_state": "EVALUATION_PASS|EVALUATION_FAIL|BLOCKED|...",
      "bug_cycles": 0,        // EVALUATION_FAIL→재진입 횟수(0 = 첫 평가에 PASS). compare.py가 failure_log로 교차검증.
      "failure": null }
  ]
}
```

> `bug_cycles`는 셀 state.json의 `failure_log`에서 `state=="EVALUATION"`인 항목 수와 같아야
> 한다(단일 진실은 failure_log; compare.py가 거기서 도출). 여기 미러는 resume 가독성용.

## 4. 프로토콜 (이 skill이 실행하는 절차)

```
4.1 진입(/stablenet-core-dev:bench)
    - 신규: manifest 경로 → .stablenet-expert/bench/{experiment}/ 생성, manifest 복사,
      state.json 초기화(모든 셀 status=pending).
    - --continue: 기존 experiment 디렉터리 로드.

4.2 MCP pre-flight (orchestrator §2.0 재사용)
    - A_stablenet_knowledge_mcp 모드가 매트릭스에 있으면 cks/jira/chainbench 등록+env를 config-레벨로 확인.
    - B/C 모드만 있으면 cks 없이 진행 가능.

4.3 배치 선택(token-limit 인지)
    - pending 셀에서 앞에서부터 batch_size개 선택.

4.4 각 셀 실행(셀 = 한 (task, mode))
    a. cells/{task}__{mode}/ 생성, run-meta.json 기록(mode, mode_agent, 시작시각).
       state.json 셀 status=running.
    b. ticket을 셀 워크스페이스에 복사(manifest.tasks[].ticket → ticket.json),
       state-machine.init_state 로 파이프라인 state 초기화.
       ★ base 고정: task.base_commit 이 있으면 go_stablenet_root 를 그 커밋으로 reset
         (`git -C {root} checkout {base_commit}` 또는 worktree)하여 **각 셀이 같은 출발점**에서
         시작하게 한다. 미지정 시 현재 HEAD. (기-수정 버그 태스크는 반드시 버그가 실재하는
         부모 커밋이어야 trivially-pass 거짓신호를 피한다.) 셀 종료 후 생성 브랜치는 §5 정리 대상.
    ── SOLVE 단계는 모드에 따라 분기한다 (정의: docs/bench-abc-mode-definitions.md) ──

    [모드 A_stablenet_knowledge_mcp — stablenet-core-dev 4-스테이지 파이프라인]
    c. ANALYSIS: Agent tool 로 mode_agents["A_stablenet_knowledge_mcp"]=analyzer 디스패치 → analysis.md,
       related-code.json, reproduction.json(bugfix).
    c2. PLANNING/DESIGN: shared_agents.plan(planner) 디스패치 → plan.md, design-v*.md.
    d. IMPLEMENTATION: shared_agents.implement(implementer) 디스패치 → build/bin/gstable +
       state.json.binary_path.

    [모드 B_code_only / C_project_skills — whole-approach 단독 solver]
    c*. SOLVE(단일): Agent tool 로 mode_agents[mode] 디스패치 (B=bench-solver-codeonly /
        C=bench-solver-project-skills). 전달: target_root(=base reset된 트리), workspace_dir, ticket.
        solver가 진단→수정→회귀테스트→빌드까지 **스스로 완주**하고 solve-report.md 를 쓴다.
        ★ regime 격리는 solver 에이전트의 도구·스킬 부재로 보장(cks·stablenet-core-dev 스킬 미부여).
        ★ stablenet-core-dev의 planner/implementer 는 B/C에서 **쓰지 않는다**. evaluator는 referee(step e)로만.

    e. EVALUATION + bug-cycle 루프 (★ 총비용 측정의 핵심 — 모드 공통, evaluator는 referee):
       max_cycles = manifest.config.max_eval_cycles (기본 3). 다음을 반복한다:

       e1. EVALUATION: Agent tool 로 shared_agents.evaluate(evaluator) 디스패치
           → test-report.md + chainbench summary. PASS면 EVALUATION_PASS,
             FAIL이면 state-machine.log_failure 로 failure_log 엔트리(state="EVALUATION")를 쓴다.
           (evaluator는 정확성 채점만 — B/C의 해결 과정엔 개입하지 않는다.)
       e2. PASS → pipeline_state=EVALUATION_PASS. 루프 종료(→ step g).
       e3. FAIL → eval_failures = failure_log에서 state=="EVALUATION"인 항목 수.
           - eval_failures >= max_cycles → pipeline_state=BLOCKED. 루프 종료(최종 정확성=실패).
             (autonomy.on_blocked=="escalate"면 orchestrator §5의 1회 escalation 패스도 동일 적용 가능.)
           - else → bug 사이클 진입(states.EVALUATION.cycle += 1), **모드에 따라 재진입**:
               [A_stablenet_knowledge_mcp] i. transition(EVALUATION→ANALYSIS). ii. analyzer 재디스패치(mode="bugfix",
                       last_failure_id + test_report_path + failure_doc → analysis-revisited-{cycle}.md,
                       재현 테스트 재사용). iii. planner 재디스패치(plan-fix-{cycle}.md). iv. implementer
                       재디스패치(재빌드). v. e1로 복귀.
               [B/C]   i. 같은 mode solver 를 **failure_report**(test-report.md + 실패문서) 와 함께
                       재디스패치 → solver가 자체 수정. ii. e1로 복귀. (planner/implementer 미사용 유지.)
       ⚠️ A는 implementer/evaluator 공유 + planner만 모드내. B/C는 solver 단독 + evaluator referee.
    f. transcript hook(P4)가 **모든 싸이클의** 각 sub-agent 디스패치 prompt/response를 셀 워크스페이스
       logs/agent-transcript.jsonl 에 누적 기록 → compare.py의 total_tokens(Σ across cycles) 원천.
       run-meta.json.bug_cycles = 최종 eval_failures 로 갱신.
    g. state.json 셀 status=done(EVALUATION_PASS) 또는 failed(BLOCKED + 사유), ended_at 기록.

    각 셀은 독립 — 한 셀 실패가 다음 셀을 막지 않는다(기록 후 계속).

4.5 측정 + 리포트(배치 후, 또는 모든 셀 done 시)
    Bash: python3 bench/compare.py \
            --experiment-dir .stablenet-expert/bench/{experiment} \
            [--prices bench/prices.json]
    → report/{comparison.md, comparison.json, comparison.csv} 생성.
    md 요약 표(모드 × {최종정확성, bug-cycle, 사이드이펙트, 총토큰, 비용, 지연, 안전성})를 출력.
    ★ 단발 토큰이 아니라 "옳은 수정까지의 총비용"(Σ across bug-cycles)·bug-cycle 수·
      회귀-클래스 사이드이펙트 실패 수가 핵심 비교축이다(§2 방법론).

4.5b 전문가 유사도(선택; task.oracle.reference_fix 가 있을 때):
    셀의 에이전트 diff(`git -C {root} diff {base_commit} {agent-HEAD}`)를 reference_fix(전문가 정답
    diff)와 비교해 별도 축으로 보고한다 — (i) 결정적: 수정 파일/핵심 심볼 overlap, (ii) 의미적:
    동일 근본원인·동등 해법인지 LLM 판정. 기능 정확성(EVALUATION_PASS)과 **분리**해서 표기한다
    (둘은 다른 질문 — "통과하는가" vs "전문가처럼 고쳤는가"). 자동 스코어러 미구현 시 수동/판정 단계.

4.6 진행 보고 + 재개 안내
    - pending 셀이 남았으면: "남은 N 셀. 이어서: /stablenet-core-dev:bench {experiment} --continue"
    - 모두 done: 최종 리포트 경로 안내.
```

## 5. 안전/경계 정책
- 이 skill은 벤치 전용. 셀 워크스페이스는 `.stablenet-expert/bench/`(일반 `/work`의
  `.stablenet-expert/tickets/`와 분리)에 격리.
- 측정 tool은 결정적(LLM 없음)·read-only — 셀 산출물을 읽기만 한다.
- B/C 모드 agent는 cks tool grant가 없어(별도 agent) regime이 하드하게 분리된다 —
  "cks 쓰지 마"라는 프롬프트 의존이 아니라 도구 부재로 보장.
- 실패한 셀도 리포트에 포함(정확성=실패로 집계) — 누락 truncation 금지.
- 🔴 **데이터셋 오염 방지**: 벤치는 go_stablenet_root 에 셀별 throwaway 브랜치/커밋을 만든다.
  실험 종료 후 **반드시 정리**한다 — 캐노니컬 브랜치 checkout → `git branch -D {셀 브랜치들}` →
  `git reflog expire --expire-unreachable=now --all && git gc --prune=now`. 안 그러면 다음 cks/ckg
  재빌드 때 가짜 코드·커밋이 인덱스로 유입된다(과거 실제 발생). base_commit 으로 reset 한 트리도 원복.
