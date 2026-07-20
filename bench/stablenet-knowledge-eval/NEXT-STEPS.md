# Hybrid Benchmark — 남은 후속 작업 (post-v8)

> 기준 상태: Report v8 (5-way) 완료 — δ 하이브리드(방식5) 97%/86%(정답존재/설계충분성),
> ε 그래프단독(방식4) 30%/6%. ckv 벡터 기여분 +67pp/+80pp 확정.
> 하네스: `run_retrieval.py`(검색·결정적 채점) + `run_judge.py`(LLM 판정) +
> `aggregate_v5.py`(집계). 인덱스: go-stablenet `dev`(`c051d50b`), `make gstable` 스코프.
> cks 바이너리: `code-knowledge-system/bin/cks-mcp` (exclude_tests·expand·OR 수정 반영).

세 작업은 독립적이며 우선순위 순서대로 정리한다.

---

## 1. RRF 가중치 스윕 → 운영 최적 설정값 결정

### 배경 / 목표
방식5(δ, composer)의 검색 품질은 Stage2의 RRF(Reciprocal Rank Fusion) 결합과
recall 파라미터에 좌우된다. 현재는 기본값으로만 측정했다. 설정값을 변경하며
측정해 **운영 권장 기본값 1세트**를 근거를 갖고 확정한다.

### 스윕 대상 노브 (code-knowledge-system)
- **Stage2 RRF 벡터:그래프 가중치** (주) — ckv hit 순위 vs ckg seed 순위의 결합 비중
  - 위치: `internal/composer/stage2/merge.go` (RRF 결합), `stage2/searcher.go`
- **ckv recall K** — Stage1 `InitialK` (`internal/composer/stage1/extractor.go`)
- **RerankPerKW** — 키워드당 ckg BM25 K (`DefaultRerankPerKW=5`)
- **그래프 확장 depth / max_total** — Stage2 seed 확장 폭
- (보조) test-demotion factor `0.25`, RRF 상수 k

### 방법
1. composer 설정을 외부에서 주입 가능하게 노출(설정 파일 또는 env). 현재 하드코딩
   상수면 우선 `cks-stablenet.yaml`/플래그로 빼는 작업이 선행.
2. 그리드/단계 스윕: 가중치 비율 ∈ {벡터우위, 균형, 그래프우위} × recall K ∈ {기본, 확대}.
3. 각 조합마다 `run_retrieval.py --runs 3` + `run_judge.py` → `aggregate_v5.py`.
4. **목적함수: 설계충분성 / 1k토큰(효율) 최대화**, 제약: 정답존재 ≥ 95%(현 δ 97% 기준 회귀 방지).

### 산출물
- `configs/` 조합별 결과 + 비교표, 권장 기본값 1세트와 근거를 Report에 "최적 설정값" 절로 추가.

### 의존성 / 규모
- composer 파라미터 외부화가 선행(없으면 코드 변경 필요). 측정 자체는 조합 수 × (검색~7분 + 판정~25분).

---

## 2. Go ↔ Solidity 크로스언어 문항 추가

### 배경 / 목표
지시사항의 "여러 언어가 섞인 코드 질문"은 이 코드베이스에선 **Go ↔ Solidity**다
(빌드에 TypeScript 0개, Go 966 + Solidity 11). 현재 30문항은 대부분 단일 Go라
하이브리드의 크로스언어 강점을 드러낼 헤드룸이 없다(δ 이미 97% 천장). 언어 경계를
넘는 문항을 신설해 방식 간 변별력을 높인다.

### 후보 문항 (정답이 Go+Solidity 양쪽)
- 제네시스 Go 시더 `initializeValidator` ↔ `GovValidator.sol` 스토리지 레이아웃
- `EncodeBytesToSlots`/`CalculateMappingSlot`(Go stateutil) ↔ `AddressSetLib.sol`
- `gov_minter.go`의 MintProof ↔ `GovMinter.sol` 발행 흐름
- coin adapter(Go) ↔ FiatToken(Solidity) allowance 연동
- → 6~10문항, `expected_files`에 Go·Solidity 파일 동시 포함

### 방법
1. `queries.json`에 신규 문항 추가(`domain: "cross-lang-*"`, `keyword`는 영문 식별자,
   `query`는 자연어, `expected_files`에 양 언어 파일).
2. `ckg-query-testset.md`에 설계 근거 기록.
3. 5방식 재측정(v9) → 크로스언어 도메인 행을 보고서에 분리 표기.

### 성공 기준
- 크로스언어 문항에서 δ(하이브리드)가 α/β/γ/ε 대비 정답존재·충분성 우위를 보이는지 확인
  (단일언어에서 가려졌던 변별력 노출).

### 의존성 / 규모
- 인덱스에 Solidity 청크/노드가 이미 포함됨(빌드 스코프). 문항 작성 + 1회 측정 사이클.

---

## 3. 회귀 자동 감지 CI 하네스

### 배경 / 목표
"코드 변경 시 통합 검색 품질 저하 자동 감지" — 일회성 측정이 아니라 **회귀 게이트**.
인덱스/코드/composer가 바뀔 때 방식5 품질이 임계 이상 떨어지면 CI가 실패하도록 한다.

### 설계
1. **기준 스냅샷**: 현재 v8 수치(방식5: 정답존재 97%, 설계충분성 86%, 테스트오염 0)를
   `baseline.json`으로 저장.
2. **러너**: 인덱스 재생성 → `run_retrieval.py --runs N` → `aggregate_v5.py` →
   baseline 대비 비교.
3. **게이트 기준(예)**: 방식5 정답존재 −3pp 또는 설계충분성 −5pp 또는 테스트오염 > 0 →
   비-제로 exit + 요약 출력.
4. 비용 절감: CI에선 결정적 지표(정답존재·테스트오염·토큰)만으로 1차 게이트(LLM 판정은
   비싸므로 야간/수동 또는 축소 표본).

### 산출물
- `ci/regression_check.py` + `baseline.json` + 사용법(README). 선택: GitHub Actions 잡.

### 의존성 / 규모
- cks 바이너리·인덱스 빌드가 CI에서 재현 가능해야 함(ckv는 ollama/bge-m3 필요 →
  결정적 1차 게이트는 ckv 없이도 가능한 항목 위주로 우선 구성).

---

## 권장 순서
1 (설정 외부화가 선행되면) → 2 (변별력 확보) → 3 (확정 기준으로 게이트화).
2번은 1·3과 독립이라 먼저 진행해도 무방하다.
