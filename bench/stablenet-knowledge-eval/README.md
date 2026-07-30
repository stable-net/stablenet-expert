# CKG 4-Way Evaluation Harness

ckg(Code Knowledge Graph)의 쿼리 검색 효과를 4방식(α/β/γ/δ)으로 정량 검증하는 평가 하니스.
(원래 go-stablenet/.stablenet-expert 에서 개발됐으나, 플러그인 자산이므로 이 레포로 이관함.)

## 구성
- `ckg-query-testset.md` — 12개 도메인 30문항 테스트셋 설계(키워드+자연어 문장, 입력↔정답 분리)
- `queries.json` — 30문항 구조화 입력(키워드/질의/정답파일·심볼). 정답은 채점 전용(oracle 누수 방지).
- `run_retrieval.py` — α(grep)/β(graph전체+본문)/γ(개별조회+본문)/δ(get_for_task) 검색 + 결정적 채점(위치적중·precision·토큰·오류). `--runs N` 평균.
- `run_judge.py` — LLM 판정(관련성·설계충분성·정답존재), `--votes N` 다수결, JSON강제+강건파싱.
- `cks_client.py` — stablenet-knowledge-mcp stdio 클라이언트(올바른 인자키: get_for_task=prompt, find_symbol=name, semantic_search=query).
- `scope/` — make-gstable 빌드 파일리스트(참고).
- `Report.md` — 4방식 비교 결과 예시.

## 사용
```
# 1) 검색 + 결정적 채점 (stablenet-knowledge 실행 필요: STABLENET_KNOWLEDGE_MCP_BIN/STABLENET_KNOWLEDGE_CONFIG)
python3 run_retrieval.py --runs 3
# 2) LLM 판정
python3 run_judge.py --model claude-sonnet-5 --votes 3
```

## 관련 인프라(별도 레포)
- 파일리스트 생성기: `code-knowledge-system/scripts/gen-stablenet-filelist.sh`
- ckv `--files-from` allowlist: `code-knowledge-vector` (feat/files-from-allowlist)
