---
description: 3-way 비교 벤치 실행. 동일 태스크를 A(stablenet-knowledge)/B(code-only)/C(code+skills) 모드로 자율 실행하고 토큰·비용·정확성·안전성을 비교. token limit 고려 배치+재개.
argument-hint: "<manifest.json> | <experiment-id> --continue"
---

# /core-dev:bench

harness-engineering automation 진입점. 같은 go-stablenet 태스크를 세 정보 regime
(A=stablenet-knowledge 검색 / B=code-only / C=code+이해 skill)으로 자율 실행하고, 결정적 측정 tool로
{최종코드 정확성, 토큰, 비용, 지연, 안전성}을 비교한다.

오케스트레이션 절차·state·checkpoint 계약은 `bench-orchestration` skill에 정의되어
있다. 이 command는 진입점일 뿐 — skill을 호출한다.

---

## 0. 인자 형식

- **신규 실험:** `/core-dev:bench bench/manifests/example.json`
  - manifest를 읽어 `.stablenet-expert/bench/{experiment}/`를 만들고 셀(태스크×모드)을
    초기화한 뒤 첫 배치를 실행한다.
- **이어서 실행:** `/core-dev:bench gsn-retrieval-abc-2026-06 --continue`
  - 기존 experiment의 pending 셀을 batch_size만큼 더 실행한다(token 한계 때문에
    한 번에 전체를 돌리지 않는다).

## 1. 동작

```
1. bench-orchestration skill 을 호출한다(§4 프로토콜):
   - 신규: manifest 복사 + state.json 초기화.
   - --continue: experiment 디렉터리 로드.
2. MCP pre-flight: 매트릭스에 A_stablenet_knowledge_mcp가 있으면 stablenet-knowledge/jira/chainbench 등록+env 확인
   (orchestrator §2.0 재사용). B/C 전용이면 stablenet-knowledge 없이 진행.
3. pending 셀에서 batch_size개 선택해 각 셀 실행:
   mode 별 ANALYSIS 에이전트(analyzer | bench-analyzer-codeonly | bench-analyzer-skills)
   → 공유 planner → 공유 implementer → 공유 evaluator. transcript hook가 sub-agent I/O를
   셀 워크스페이스에 기록.
4. 배치 후 측정 tool 호출:
   bash: python3 bench/compare.py --experiment-dir .stablenet-expert/bench/{experiment}
   → report/{comparison.md,json,csv}. md 요약 표를 출력.
5. 진행 보고: 남은 셀이 있으면 `--continue` 안내, 없으면 최종 리포트 경로 안내.
```

## 2. 주의

- **token 한계**: plugin-native 실행이라 현재 세션 한도 안에서 돈다. 한 번에
  `manifest.batch_size`개 셀만 실행하고 멈춘다. 큰 매트릭스는 `--continue`로 여러
  번에 나눠 돌린다.
- **실제 런 전제조건**: A_stablenet_knowledge_mcp 모드는 stablenet-knowledge-mcp(+Ollama/bge-m3, 빌드된 ckv/ckg 인덱스)와
  chainbench가 필요하다(`docs/SETUP.md`). 미충족이면 stablenet-knowledge는 degraded로 떨어지고
  결과에 그대로 기록된다.
- **벤치 격리**: 셀 워크스페이스는 `.stablenet-expert/bench/`(일반 `/work`의
  `.stablenet-expert/tickets/`와 분리)에 만든다.

## 3. 출력 예시(측정 tool)

```
| mode          | tasks | correct | avg_tokens | avg_cost($) | avg_latency(s) | safety_flags |
|---------------|-------|---------|------------|-------------|----------------|--------------|
| A_stablenet_knowledge_mcp         |   1   |   1/1   |   ...      |   ...       |   ...          |   0          |
| B_code_only   |   1   |   0/1   |   ...      |   ...       |   ...          |   1          |
| C_code_skills |   1   |   1/1   |   ...      |   ...       |   ...          |   0          |
```
모드 간 정확성·토큰·비용 델타가 "stablenet-knowledge가 grep/skill 대비 정확도·토큰에서 우위인가"
(§9 thesis)를 데이터로 답한다.
