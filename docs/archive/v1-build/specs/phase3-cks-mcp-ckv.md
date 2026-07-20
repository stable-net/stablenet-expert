# Phase 3: CKS MCP - CKV (Code Knowledge Vector)

> go-stablenet 코드베이스의 의미 기반 검색 엔진.
> 자연어 쿼리(Jira 티켓 내용)로 관련 코드를 찾는다.

## 1. CKV 전체 아키텍처

```
┌─────────────────────────────────────────────────┐
│                  CKS MCP Server                  │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │                CKV Engine                    │ │
│  │                                              │ │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐ │ │
│  │  │  Code    │  │ Embedding │  │  Vector  │ │ │
│  │  │  Chunker │→│  Model    │→│  Store   │ │ │
│  │  │ (Go AST) │  │           │  │          │ │ │
│  │  └──────────┘  └───────────┘  └──────────┘ │ │
│  │                                              │ │
│  │  ┌──────────┐  ┌───────────┐               │ │
│  │  │ Reranker │  │ Sensitive │               │ │
│  │  │          │  │ Filter    │               │ │
│  │  └──────────┘  └───────────┘               │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │           Indexing Pipeline                  │ │
│  │  git ls-files → parse → chunk → embed       │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

---

## 2. Code Chunker (Go AST 기반)

### 2.1 청킹 단위

Go 코드를 의미 단위로 분할한다. AST 노드 타입별 청킹 전략:

| AST Node | 청킹 단위 | 포함 메타데이터 |
|----------|----------|----------------|
| `FuncDecl` | 함수/메서드 전체 | 패키지, 리시버, 시그니처, godoc |
| `GenDecl` (type) | 구조체/인터페이스 정의 | 패키지, 필드 목록, 메서드 목록 |
| `GenDecl` (const/var) | 상수/변수 블록 | 패키지, 타입 |
| File-level | import + package 선언 | 의존성 목록 |

### 2.2 청크 구조

```typescript
interface CodeChunk {
  id: string;                  // hash(file_path + symbol_name + version)
  file_path: string;           // "consensus/wbft/finalize.go"
  package_name: string;        // "wbft"
  symbol_name: string;         // "(*WBFTEngine).Finalize"
  symbol_type: "function" | "method" | "struct" | "interface" | "const" | "var";
  
  code: string;                // 원본 코드
  signature: string;           // 함수 시그니처 (검색 가중치 높음)
  godoc: string;               // godoc 주석 (있으면)
  
  start_line: number;
  end_line: number;
  
  // 컨텍스트 메타데이터
  receiver_type?: string;      // 메서드의 리시버 타입
  params?: string[];           // 파라미터 타입 목록
  returns?: string[];          // 반환 타입 목록
  imports: string[];           // 이 청크가 사용하는 import
  
  // 인덱싱 메타데이터
  indexed_at: string;
  git_last_modified: string;   // 마지막 수정 커밋 시각
  git_last_author: string;
}
```

### 2.3 청킹 규칙

```
1. 함수/메서드가 200줄 초과 시:
   → 논리적 블록(if/for/switch 최상위 기준)으로 서브 청크 분할
   → 각 서브 청크에 부모 함수 시그니처를 컨텍스트로 첨부

2. 구조체 정의가 50 필드 초과 시:
   → 필드 그룹별로 분할 (연속 주석 블록 기준)

3. 파일 레벨 init() 함수:
   → 별도 청크로 분리 (초기화 로직은 검색 빈도 높음)

4. 생성된 코드 (_gen.go, _mock.go, _test.go):
   → _test.go는 인덱싱 포함 (테스트 패턴 참조용)
   → _gen.go, _mock.go는 기본 제외 (설정으로 변경 가능)
```

### 2.4 Go AST Parser 설계

```
구현 언어: Go

이유:
- go/ast, go/parser, go/token 표준 라이브러리 직접 활용
- go-stablenet과 동일 생태계
- CKG(Phase 4)와 파서 코드 공유

인터페이스:
  ParseFile(filePath string) → []CodeChunk
  ParsePackage(pkgPath string) → []CodeChunk
  ParseProject(rootPath string, excludePatterns []string) → []CodeChunk
```

---

## 3. Embedding Model

### 3.1 선택지 비교

| 모델 | 차원 | 장점 | 단점 |
|------|------|------|------|
| **CodeBERT** | 768 | 코드 특화, 로컬 실행 | 모델 크기 ~1.5GB |
| **StarCoder Embeddings** | 1024 | 최신 코드 이해도 높음 | GPU 권장 |
| **text-embedding-3-small** (OpenAI) | 1536 | 고품질, API 호출 | 외부 의존, 비용 |
| **Voyage Code 3** | 1024 | 코드 특화 최고 성능 | API 호출, 비용 |
| **nomic-embed-text** | 768 | 경량, 로컬 실행 | 코드 특화 아님 |

### 3.2 권장: 2-tier 전략

```
Tier 1 (기본, 로컬): nomic-embed-text 또는 CodeBERT
  - 로컬 실행으로 민감정보 외부 전송 없음
  - Ollama를 통한 간편 배포
  - 인덱싱 + 기본 검색에 사용

Tier 2 (정밀, API): Voyage Code 3 또는 text-embedding-3-small
  - Reranking 단계에서 상위 후보를 정밀 재평가
  - API 호출이므로 비용 발생
  - 선택적 사용 (정확도가 중요한 경우)
```

보안 고려: 코드 임베딩을 외부 API로 전송하는 것은 코드 내용의 간접적 노출. Tier 1 로컬 모델을 기본으로 하되, 유저가 명시적으로 외부 API 사용을 허용한 경우에만 Tier 2 활성화.

### 3.3 임베딩 입력 포맷

```
코드 청크를 임베딩할 때, 순수 코드만이 아닌 컨텍스트를 포함한 텍스트로 변환:

[template]
Package: {package_name}
File: {file_path}
Type: {symbol_type}
Signature: {signature}
{godoc}

{code}
```

이유: 패키지명, 시그니처, godoc을 포함하면 의미적 검색 정확도가 향상됨. "staking reward 계산"이라는 쿼리가 `governance/staking.go`의 `CalcReward()` 함수를 더 잘 매칭.

---

## 4. Vector Store

### 4.1 선택: SQLite + sqlite-vss

```
이유:
- 로컬 실행, 외부 서비스 불필요
- 파일 기반으로 백업/이동 용이
- sqlite-vss: SQLite 확장으로 벡터 검색 지원
- go-stablenet 규모 (수만 청크)에 충분한 성능

대안:
- ChromaDB: Python 생태계에 적합하지만 Go/TS에서 사용하려면 서버 모드 필요
- Qdrant: 고성능이지만 별도 서버 운영 필요
- lancedb: 경량이지만 생태계가 아직 초기
```

### 4.2 스키마

```sql
CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  file_path TEXT NOT NULL,
  package_name TEXT NOT NULL,
  symbol_name TEXT NOT NULL,
  symbol_type TEXT NOT NULL,
  code TEXT NOT NULL,
  signature TEXT,
  godoc TEXT,
  start_line INTEGER,
  end_line INTEGER,
  receiver_type TEXT,
  params TEXT,          -- JSON array
  returns TEXT,         -- JSON array
  imports TEXT,         -- JSON array
  indexed_at TEXT NOT NULL,
  git_last_modified TEXT,
  git_last_author TEXT
);

-- sqlite-vss 벡터 인덱스
CREATE VIRTUAL TABLE chunk_embeddings USING vss0(
  embedding(768)       -- 차원은 모델에 따라 변경
);

-- 메타데이터 검색용 인덱스
CREATE INDEX idx_chunks_package ON chunks(package_name);
CREATE INDEX idx_chunks_file ON chunks(file_path);
CREATE INDEX idx_chunks_symbol_type ON chunks(symbol_type);
```

### 4.3 검색 파이프라인

```
ckv_search(query, top_k, filters?) 동작:

1. query를 embedding model로 벡터화

2. Vector Search (sqlite-vss)
   → top_k * 3 개 후보 검색 (over-fetch for reranking)
   → filters 적용 (package, file_pattern)

3. Metadata Enrichment
   → 각 후보에 git history 요약 추가
   → git log --follow -5 {file_path} -- {함수 범위}

4. Reranking
   → query와 각 후보의 (signature + godoc + code) 쌍을
     cross-encoder 또는 LLM으로 재평가
   → 상위 top_k개 반환

5. Sensitive Filter
   → 반환 전 코드 스니펫에 민감정보 스캔
   → (shared/patterns.json 사용)

6. 결과 반환
   → [{file, function, snippet, score, git_history_summary}]
```

---

## 5. Reranker

### 5.1 동작

초기 벡터 검색은 recall 위주(많이 가져옴). Reranker는 precision을 높인다.

```
Reranker 입력:
  - query: "staking reward 계산 로직에서 overflow 방지"
  - candidates: 벡터 검색 결과 top_k*3개

Reranker 동작:
  각 candidate에 대해 relevance score 계산:
  score = relevance(query, candidate.signature + candidate.godoc + candidate.code[:500])

Reranker 방법 (2가지 중 선택):
  A. Cross-Encoder 모델 (로컬):
     - ms-marco-MiniLM-L-6-v2 등 경량 모델
     - 로컬 실행, 빠름
  
  B. LLM 기반 (Sonnet):
     - 프롬프트: "다음 코드가 쿼리와 관련 있는지 0-10으로 평가"
     - 더 정확하지만 비용/지연 발생
     - 후보 수가 적을 때(10개 이하) 적합

기본: A (Cross-Encoder) 사용. 정확도 부족 시 B로 전환 가능.
```

### 5.2 Reranking 최적화

```
1. 시그니처 부스팅:
   함수 시그니처가 쿼리 키워드를 포함하면 score * 1.5 가중

2. godoc 부스팅:
   godoc 주석이 쿼리와 의미적으로 일치하면 score * 1.3

3. 최근 수정 부스팅:
   최근 30일 내 수정된 코드 → score * 1.1
   (활발히 개발 중인 코드가 더 관련성 높을 확률)

4. 패키지 근접성:
   쿼리에서 추출된 모듈명과 동일 패키지 → score * 1.2
```

---

## 6. Indexing Pipeline

### 6.1 Full Index (초기)

```
full_index(project_root):

  1. git ls-files '*.go' → 전체 Go 파일 목록
  2. 제외 필터: vendor/, *_gen.go, *_mock.go (설정 가능)
  3. 각 파일에 대해:
     a. Go AST Parse → CodeChunk 목록
     b. 각 chunk를 embedding model로 벡터화
     c. SQLite에 chunk 메타데이터 + 벡터 저장
  4. 인덱싱 통계 출력:
     - 총 파일 수, 총 청크 수, 인덱싱 시간
     - 패키지별 청크 분포

예상 시간 (go-stablenet 규모 추정):
  ~5000 Go 파일 → ~20000 청크 → 로컬 임베딩 기준 10-30분
```

### 6.2 Incremental Index (변경분)

```
incremental_index(project_root, since_commit):

  1. git diff --name-only {since_commit}..HEAD -- '*.go' → 변경 파일
  2. 변경 파일 분류:
     - Modified: re-parse → 기존 청크 업데이트
     - Added: parse → 새 청크 추가
     - Deleted: 해당 파일의 청크 삭제
     - Renamed: 경로 업데이트
  3. 변경된 청크만 re-embed
  4. 마지막 인덱스 커밋 해시 기록

트리거:
  - /work 실행 시 자동 (마지막 인덱스 이후 변경분)
  - 수동: /index 커맨드 (향후 추가 가능)
```

### 6.3 인덱스 저장 위치

```
.coding-agent/
├── index/
│   ├── ckv.db              # SQLite + 벡터 인덱스
│   ├── index-meta.json     # 마지막 인덱스 커밋, 통계
│   └── embeddings-cache/   # 임베딩 캐시 (재계산 방지)
└── tickets/
    └── ...
```

---

## 7. MCP Tool 인터페이스

### 7.1 ckv_search

```typescript
// Input
interface CkvSearchInput {
  query: string;              // 자연어 검색 쿼리
  top_k?: number;             // 반환 개수 (기본: 10)
  filters?: {
    package?: string;         // 패키지명 필터 (예: "consensus")
    file_pattern?: string;    // 파일 경로 glob (예: "consensus/wbft/**")
    symbol_type?: string;     // "function" | "method" | "struct" | ...
    modified_since?: string;  // 이 날짜 이후 수정된 것만
  };
  include_history?: boolean;  // git 히스토리 포함 여부 (기본: true)
  rerank?: boolean;           // reranking 수행 여부 (기본: true)
}

// Output
interface CkvSearchOutput {
  results: Array<{
    file: string;
    package: string;
    symbol: string;
    symbol_type: string;
    signature: string;
    snippet: string;           // 코드 스니펫 (상위 500자)
    godoc: string;
    score: number;             // 0.0 ~ 1.0
    start_line: number;
    end_line: number;
    git_history_summary?: string;  // 최근 5개 커밋 요약
  }>;
  
  metadata: {
    total_candidates: number;  // 초기 벡터 검색 후보 수
    reranked: boolean;
    index_commit: string;      // 인덱스 기준 커밋 해시
    query_time_ms: number;
  };
}
```

### 7.2 ckv_index

```typescript
// 인덱싱 트리거 (관리용)
interface CkvIndexInput {
  mode: "full" | "incremental";
  project_root: string;
  exclude_patterns?: string[];
}

interface CkvIndexOutput {
  files_processed: number;
  chunks_created: number;
  chunks_updated: number;
  chunks_deleted: number;
  duration_ms: number;
  index_commit: string;
}
```

---

## 8. CKS MCP Server 프로젝트 구조

CKV(Phase 3)와 CKG(Phase 4)를 하나의 MCP 서버에 포함한다.

```
tools/cks-mcp/
├── go.mod
├── go.sum
├── cmd/
│   └── cks-server/
│       └── main.go           # MCP 서버 진입점
├── internal/
│   ├── server/
│   │   └── server.go         # MCP 서버 설정 + tool 등록
│   ├── ckv/
│   │   ├── chunker.go        # Go AST 기반 코드 청킹
│   │   ├── chunker_test.go
│   │   ├── embedder.go       # 임베딩 모델 인터페이스
│   │   ├── store.go          # SQLite + vss 벡터 스토어
│   │   ├── search.go         # 검색 + reranking 파이프라인
│   │   ├── indexer.go        # Full/Incremental 인덱싱
│   │   └── indexer_test.go
│   ├── ckg/                  # Phase 4에서 구현
│   │   └── ...
│   ├── filter/
│   │   ├── engine.go         # Sensitive Filter (shared logic)
│   │   └── engine_test.go
│   └── types/
│       └── types.go          # 공유 타입
├── shared/
│   └── patterns.json         # Jira GW와 공유
└── tests/
    └── integration/
        └── ckv_search_test.go
```

**구현 언어: Go**

이유:
- Go AST 파서를 네이티브로 사용 (go/ast, go/parser)
- go-stablenet과 동일 생태계
- 성능 (인덱싱 파이프라인은 CPU 집약적)

---

## 9. Phase 3 완료 기준

- [ ] Go AST Parser가 함수/메서드/구조체/인터페이스를 청크로 분할
- [ ] 로컬 임베딩 모델(nomic 또는 CodeBERT)로 코드 청크 벡터화
- [ ] SQLite + sqlite-vss 벡터 스토어에 저장/검색
- [ ] ckv_search MCP tool이 자연어 쿼리로 관련 코드 반환
- [ ] Reranker가 초기 결과를 재순위화
- [ ] Full/Incremental 인덱싱 파이프라인 동작
- [ ] Sensitive Filter가 검색 결과에 적용
- [ ] 인덱스가 .coding-agent/index/에 저장
