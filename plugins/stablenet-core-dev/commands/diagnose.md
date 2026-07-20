---
description: 분석 전용. 증상을 입력하면 근본 원인만 진단하고 멈춘다(코드 변경·설계·PR 없음). analyzer를 진단 모드로 재사용.
argument-hint: "\"<증상/문제 설명>\"  [--path <파일/디렉토리>]"
---

# /stablenet-core-dev:diagnose

증상을 입력하면 **근본 원인이 무엇인지**만 파악해서 보고한다. `/stablenet-core-dev:analyze`
와 달리 설계·구현·테스트·PR로 진행하지 **않는다** — **읽기 전용 진단**이다.

내부적으로 `analyzer`(상황분석 + 근본원인 단계 + stablenet-knowledge 검색·root-cause-lifecycle)를
**진단 모드**로 재사용하되, 근본원인 규명 직후 **멈추고** `diagnosis.md` 를 산출한다.
재현 테스트를 만들지 않고, 코드를 수정하거나 브랜치를 만들지 않으며, PLANNING으로 넘어가지 않는다.

> 언제 쓰나: "왜 이런 일이 생기지?"를 빠르게 규명하고 싶을 때. 고치는 것까지 자율로
> 진행하려면 대신 `/stablenet-core-dev:analyze` 를 쓴다.

---

## 0. 인자 형식
- 기본: `/stablenet-core-dev:diagnose "에포크 전환 직후 일부 tx가 부당 거부된다"`
- 범위 힌트(선택): `... --path core/txpool` — planner가 우선 살필 경로(생략 시 stablenet-knowledge가 전역 검색).

---

## 1. 인자 검증
```
1.1. 따옴표 본문 → problem_text. 옵션 --path <경로> → focus_path (선택).
1.2. 빈 본문 → 사용법 출력 후 중단:
     "사용법: /stablenet-core-dev:diagnose \"<증상/문제 설명>\" [--path <경로>]"
```

## 2. 작업 폴더 (진단은 tickets 와 분리)
```
2.1. bash: git rev-parse --show-toplevel → repo_root (실패 시 "git 레포 안에서 실행" 중단)
2.2. bash: date -u +"%Y%m%d_%H%M%S" → timestamp
2.3. workspace = "{repo_root}/.stablenet-expert/diagnoses/DIAG-{timestamp}"
2.4. bash: mkdir -p {workspace}
2.5. 로컬 민감정보 auto-redact: problem_text 의 명백한 비밀(sk-/ghp_/-----BEGIN/토큰·패스워드)을
     "[REDACTED]" 로 치환(하드스톱 없음).
```

## 3. analyzer 디스패치 (진단 전용 — situation + root cause만)
```
3.1. Agent(
       subagent_type="analyzer",
       description="Diagnose root cause for DIAG-{timestamp}",
       prompt=
         "DIAGNOSE MODE — read-only root-cause analysis. Do the ANALYSIS phase ONLY.\n"
         "workspace_dir={workspace}\n"
         "problem: {problem_text}\n"
         "focus_path: {focus_path or '(none — search broadly via stablenet-knowledge)'}\n"
         "\n"
         "Use stablenet-knowledge (semantic_search / get_for_task / find_callers / get_subgraph /\n"
         "impact_analysis / change_history) to locate candidate code. Then REASON to\n"
         "the cause with the `root-cause-lifecycle` skill: pick the single value the\n"
         "symptom is about, enumerate EVERY copy/cache of it, find which lifecycle edge\n"
         "(produce/store/consume) is broken, TRACE a stale value to its source (the\n"
         "first cache is usually the symptom, not the cause), and FALSIFY competing\n"
         "hypotheses with the symptom's distinguishing feature. Then write\n"
         "{workspace}/diagnosis.md with EXACTLY these sections:\n"
         "  1. Root cause — the single most likely cause, stated plainly, naming the\n"
         "     broken lifecycle edge and the competing hypothesis you ruled out (why).\n"
         "  2. Evidence — file:line citations + relevant call/relation edges from stablenet-knowledge.\n"
         "  3. Affected sites — every place that would need to change to fix it\n"
         "     (write-site enumeration via find_callers/impact_analysis), or 'n/a'.\n"
         "  4. Confidence — high/medium/low + what would raise it.\n"
         "  5. Suggested direction — a one-paragraph fix approach (NOT a full plan).\n"
         "\n"
         "STRICT (diagnose mode): do ONLY situation analysis + root cause. You MAY write a\n"
         "THROWAWAY investigative probe (investigative-probe skill) to disambiguate competing\n"
         "candidates at runtime, then REVERT it (do not keep it). Do NOT author the\n"
         "reproduction test (the fix oracle), do NOT modify production code, do NOT write\n"
         "plan.md or any design, do NOT create a branch, do NOT transition the pipeline (stay\n"
         "in ANALYSIS), do NOT dispatch other agents. End after writing diagnosis.md."
     )
```

## 4. 결과 보고
```
4.1. {workspace}/diagnosis.md 를 읽어 사용자에게 요약 출력:
     - 근본 원인 한 줄
     - 핵심 근거(파일:라인) 2~3개
     - 확신도
     - "전체 진단: {workspace}/diagnosis.md"
4.2. 안내: "고치는 작업까지 진행하려면: /stablenet-core-dev:analyze \"{problem_text}\""
```

## 5. 완료 기준 (체크리스트)
- [ ] 빈 본문에 사용법 출력
- [ ] git 레포 아닐 때 명확한 에러
- [ ] DIAG-{timestamp} 진단 폴더 생성(tickets 와 분리)
- [ ] planner가 ANALYSIS만 수행하고 diagnosis.md 산출(코드·브랜치·PR 변경 없음)
- [ ] 근본 원인·근거·확신도 요약 출력
