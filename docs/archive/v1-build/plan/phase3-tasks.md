# Phase 3: CKS MCP - CKV Vector Search — 작업 상세

> 설계 문서: [phase3-cks-mcp-ckv.md](../superpowers/specs/phase3-cks-mcp-ckv.md)

---

## P3-1. CKS MCP 서버 프로젝트 생성 [NEW] `M`

**상태**: ✅ 완료. `tools/cks-mcp/` Go 모듈 + `cmd/server` 진입점 + `internal/{ckv,filter,server,types}/`.

**파일**: `tools/cks-mcp/` 전체

**산출물**:
```
tools/cks-mcp/
├── go.mod                    # module github.com/user/coding-agent/cks-mcp
├── go.sum
├── cmd/cks-server/
│   └── main.go              # MCP 서버 진입점
├── internal/
│   ├── server/server.go     # tool 등록
│   ├── ckv/                 # P3-2 ~ P3-9
│   ├── ckg/                 # Phase 4
│   ├── filter/              # P3-10
│   └── types/types.go
└── shared/                   # patterns.json 접근 (아래 RI-22 참조)
```

**의존성**:
```
github.com/modelcontextprotocol/go-sdk
modernc.org/sqlite             # CGo-free SQLite
```

> ⚠️ **RI-22**: shared/patterns.json 접근 방법 결정 필요.
> 권장: 환경변수 `CKS_PATTERNS_PATH`로 경로 주입 (.mcp.json의 env에서 설정).
> 빌드 시 embed(//go:embed)는 상대 경로 제약으로 복잡해질 수 있음.

**완료 기준**:
- [ ] `go run ./cmd/cks-server`로 MCP 서버 시작
- [ ] tool 목록 조회 가능 (빈 응답이라도)
- [ ] patterns.json 경로를 환경변수로 주입 가능

---

## P3-2. Go AST Code Chunker [NEW] `XL`

**상태**: ✅ 완료. `internal/ckv/chunker.go` — FuncDecl/Method/Struct/Interface/Const/Var 청킹, 200줄 초과 함수 sub-chunk 분할, vendor·_gen.go·hidden dir 제외.

**파일**: `tools/cks-mcp/internal/ckv/chunker.go`

**입력**: Go 소스 파일 경로 (또는 프로젝트 루트)

**출력**: `[]CodeChunk`

**핵심 로직**:
```go
func ParseFile(filePath string, fset *token.FileSet) ([]CodeChunk, error) {
    f, err := parser.ParseFile(fset, filePath, nil, parser.ParseComments)
    
    for _, decl := range f.Decls {
        switch d := decl.(type) {
        case *ast.FuncDecl:
            chunk := extractFuncChunk(d, fset, filePath)
            // 200줄 초과 시 서브 청크 분할
            if chunk.EndLine - chunk.StartLine > 200 {
                subChunks := splitLargeFunc(d, fset, filePath)
                chunks = append(chunks, subChunks...)
            } else {
                chunks = append(chunks, chunk)
            }
        case *ast.GenDecl:
            if d.Tok == token.TYPE {
                chunks = append(chunks, extractTypeChunk(d, fset, filePath))
            } else if d.Tok == token.CONST || d.Tok == token.VAR {
                chunks = append(chunks, extractConstVarChunk(d, fset, filePath))
            }
        }
    }
    return chunks, nil
}

func ParseProject(root string, excludes []string) ([]CodeChunk, error) {
    // git ls-files '*.go' → 필터링 → 각 파일 ParseFile
    // exclude: vendor/, *_gen.go, *_mock.go
    // include: *_test.go (테스트 패턴 참조용)
}
```

**CodeChunk 구조체**:
```go
type CodeChunk struct {
    ID           string   // sha256(FilePath + SymbolName)[:16]
    FilePath     string
    PackageName  string
    SymbolName   string   // "(*WBFTEngine).Finalize"
    SymbolType   string   // function, method, struct, interface, const, var
    Code         string
    Signature    string   // 함수 시그니처만
    Godoc        string
    StartLine    int
    EndLine      int
    ReceiverType string   // 메서드의 리시버
    Params       []string // 파라미터 타입
    Returns      []string // 반환 타입
    Imports      []string // 이 청크가 사용하는 import
    IndexedAt    time.Time
    GitModified  string   // 마지막 수정 커밋 시각
    GitAuthor    string
}
```

**서브 청크 분할 전략**:
```go
func splitLargeFunc(fn *ast.FuncDecl, ...) []CodeChunk {
    // fn.Body.List에서 최상위 stmt를 그룹핑
    // if/for/switch 블록 단위로 분할
    // 각 서브 청크에 부모 함수 시그니처를 Godoc 앞에 첨부:
    //   "// Part of: func (e *WBFTEngine) Finalize(...) ..."
}
```

**완료 기준**:
- [ ] FuncDecl, GenDecl(type), GenDecl(const/var)를 각각 올바른 청크로 분할
- [ ] 메서드의 리시버 타입 정확 추출
- [ ] 200줄 초과 함수의 서브 청크 분할 동작
- [ ] _test.go 포함, _gen.go/_mock.go 제외
- [ ] go-stablenet 규모 (~5000 파일)에서 파싱 완료 (10분 이내)

---

## P3-3. Embedding 통합 [NEW] `L`

**상태**: ✅ 완료. `internal/ckv/embedder.go` (Ollama probe + Dimension 자동 발견) + `internal/ckv/bm25.go` (RI-08 폴백). `FormatChunkForEmbedding`에 package/file/signature/godoc 컨텍스트 포함.

**파일**: `tools/cks-mcp/internal/ckv/embedder.go`

**입력**: CodeChunk

**출력**: `[]float32` (벡터)

**핵심 로직**:
```go
type Embedder interface {
    Embed(text string) ([]float32, error)
    Dimension() int
}

// Tier 1: Ollama 로컬
type OllamaEmbedder struct {
    model   string  // "nomic-embed-text"
    baseURL string  // "http://localhost:11434"
}

func (e *OllamaEmbedder) Embed(text string) ([]float32, error) {
    // POST /api/embeddings { model, prompt: text }
    // 응답에서 embedding 배열 추출
}

// 임베딩 입력 포맷
func FormatChunkForEmbedding(c CodeChunk) string {
    return fmt.Sprintf(
        "Package: %s\nFile: %s\nType: %s\nSignature: %s\n%s\n\n%s",
        c.PackageName, c.FilePath, c.SymbolType, c.Signature, c.Godoc, c.Code,
    )
}
```

**사전 조건**: Ollama 설치 + nomic-embed-text 모델 pull
```bash
ollama pull nomic-embed-text
```

**buddy 참고**: `plugin/skills/design-embedding-search/PROCEDURE.md`
- 하이브리드 검색(BM25+벡터) 설계 참고
- 리랭킹 전략 참고

**완료 기준**:
- [ ] Ollama 미실행 시 명확한 에러 + 설치 안내
- [ ] 단일 청크 임베딩 → 768차원 벡터 반환
- [ ] 배치 임베딩 지원 (throughput 향상)
- [ ] Embedder 인터페이스로 추후 모델 교체 용이

---

## P3-4. Vector Store [NEW] `L`

**상태**: ✅ 완료. `internal/ckv/store.go` — `modernc.org/sqlite` (CGo-free) + brute-force cosine (RI-07). `code_hash` 컬럼 + `GetCodeHash` (RI-23 캐시).

**파일**: `tools/cks-mcp/internal/ckv/store.go`

**핵심 로직**:
```go
type VectorStore struct {
    db *sql.DB
}

func (s *VectorStore) Init() error {
    // chunks 테이블 + 벡터 인덱스 테이블 생성
    // sqlite-vss 로드 또는 대안 (brute-force KNN for MVP)
}

func (s *VectorStore) Upsert(chunk CodeChunk, embedding []float32) error
func (s *VectorStore) Search(query []float32, topK int, filters Filter) ([]SearchResult, error)
func (s *VectorStore) Delete(chunkID string) error
func (s *VectorStore) GetByFile(filePath string) ([]CodeChunk, error)
```

**벡터 검색 구현 전략**:
```
MVP: brute-force cosine similarity (SQLite에 벡터를 BLOB으로 저장)
  → go-stablenet 규모 (~20000 청크)에서 충분히 빠름 (<1초)
  → 프로파일링 후 sqlite-vss로 마이그레이션 여부 결정

cosine_similarity(a, b []float32) float32:
  dot = Σ(a[i] * b[i])
  normA = sqrt(Σ(a[i]²))
  normB = sqrt(Σ(b[i]²))
  return dot / (normA * normB)
```

**완료 기준**:
- [ ] 청크 + 벡터 저장/조회/삭제 동작
- [ ] cosine similarity 기반 top-K 검색
- [ ] 메타데이터 필터 (package, file_pattern, symbol_type)
- [ ] .coding-agent/index/ckv.db에 저장

---

## P3-5. 검색 파이프라인 [NEW] `L`

**상태**: ✅ 완료. `internal/ckv/search.go` — embed → vector/BM25 retrieve → over-fetch ×3 → enrich → rerank → sensitive filter.

**파일**: `tools/cks-mcp/internal/ckv/search.go`

**핵심 로직**:
```go
func (s *SearchService) Search(req CkvSearchInput) (*CkvSearchOutput, error) {
    // 1. 쿼리 임베딩
    queryVec, _ := s.embedder.Embed(req.Query)
    
    // 2. 벡터 검색 (over-fetch: topK * 3)
    candidates, _ := s.store.Search(queryVec, req.TopK*3, req.Filters)
    
    // 3. Git history enrichment
    if req.IncludeHistory {
        for i := range candidates {
            candidates[i].GitHistory = s.gitHistorySummary(candidates[i].FilePath, 5)
        }
    }
    
    // 4. Reranking (P3-6)
    if req.Rerank {
        candidates = s.reranker.Rerank(req.Query, candidates)
    }
    
    // 5. Top-K 선택
    results := candidates[:min(req.TopK, len(candidates))]
    
    // 6. Sensitive filter
    for i := range results {
        filtered := s.filter.Scan(results[i].Snippet)
        results[i].Snippet = filtered.Text
    }
    
    return &CkvSearchOutput{Results: results, Metadata: ...}, nil
}
```

**완료 기준**:
- [ ] 자연어 쿼리 → 관련 코드 반환
- [ ] 필터(package, file_pattern) 적용
- [ ] git history 요약 포함 옵션
- [ ] sensitive filter 적용

---

## P3-6. Reranker [NEW] `M`

**상태**: ✅ 완료. `internal/ckv/reranker.go` — 4개 boost (signature ×1.5, godoc ×1.3, recent ×1.1, package proximity ×1.2). 테스트 가능한 clock 주입.

**파일**: `tools/cks-mcp/internal/ckv/reranker.go`

**핵심 로직**:
```go
type Reranker struct{}

func (r *Reranker) Rerank(query string, candidates []SearchResult) []SearchResult {
    for i := range candidates {
        baseScore := candidates[i].Score
        
        // 시그니처 부스팅: 쿼리 키워드가 시그니처에 포함
        if containsKeywords(candidates[i].Signature, extractKeywords(query)) {
            baseScore *= 1.5
        }
        
        // Godoc 부스팅: godoc에 쿼리 키워드 포함
        if containsKeywords(candidates[i].Godoc, extractKeywords(query)) {
            baseScore *= 1.3
        }
        
        // 최근 수정 부스팅: 30일 이내
        if isRecentlyModified(candidates[i].GitModified, 30*24*time.Hour) {
            baseScore *= 1.1
        }
        
        // 패키지 근접성: 쿼리에서 추출된 모듈명과 동일 패키지
        if packageMatchesQuery(candidates[i].PackageName, query) {
            baseScore *= 1.2
        }
        
        candidates[i].Score = baseScore
    }
    
    sort.Slice(candidates, func(i, j int) bool {
        return candidates[i].Score > candidates[j].Score
    })
    return candidates
}
```

**완료 기준**:
- [ ] 4개 부스팅 규칙 적용
- [ ] 리랭킹 후 결과 순서가 개선됨을 검증

---

## P3-7. Indexing Pipeline [NEW] `L`

**상태**: ✅ 완료. `internal/ckv/indexer.go` — full/incremental, `code_hash` 캐시 reuse (RI-23), progress 콜백 (RI-09), `modules` 우선순위 필터, git status 변경 파일 포함.

**파일**: `tools/cks-mcp/internal/ckv/indexer.go`

**핵심 로직**:
```go
func (idx *Indexer) FullIndex(root string) (*IndexStats, error) {
    // 1. git ls-files '*.go' (vendor, _gen, _mock 제외)
    // 2. 각 파일 → ParseFile → []CodeChunk
    // 3. 각 청크 → Embed → Store
    // 4. index-meta.json 기록 (commit hash, 통계)
}

func (idx *Indexer) IncrementalIndex(root, sinceCommit string) (*IndexStats, error) {
    // 1. git diff --name-only {sinceCommit}..HEAD -- '*.go'
    // 2. Modified → re-parse → code_hash 비교:
    //      변경됨 → re-embed + update (RI-23: 캐시 활용)
    //      변경 없음 → 기존 벡터 재사용 (skip embed)
    // 3. Added → parse, embed, insert
    // 4. Deleted → delete from store
    // 5. index-meta.json 업데이트
}
```

**저장 위치**: `.coding-agent/index/ckv.db`, `.coding-agent/index/index-meta.json`

> ⚠️ **RI-23**: 임베딩 캐시 — chunks 테이블에 `code_hash` 컬럼 추가.
> incremental index 시 code_hash가 동일하면 re-embed를 건너뛰고 기존 벡터 재사용.
> 이로써 RI-09(인덱싱 시간) 문제도 완화.

> ⚠️ **RI-09**: 인덱싱 시간이 CPU 환경에서 60분+ 걸릴 수 있음.
> 대응: scope.modules 기반 우선 인덱싱 (관련 패키지 먼저), 나머지는 백그라운드.
> 진행률 표시 (N/total 청크, 예상 남은 시간).

**완료 기준**:
- [ ] Full index가 go-stablenet 규모에서 완료
- [ ] Incremental index가 변경 파일만 처리
- [ ] code_hash 기반 임베딩 캐시 동작 (변경 없는 청크는 skip)
- [ ] index-meta.json에 마지막 커밋 해시 기록
- [ ] 중복 인덱싱 방지 (이미 인덱싱된 커밋 skip)
- [ ] scope 기반 우선 인덱싱 옵션
- [ ] 진행률 출력

---

## P3-8. MCP Tool: ckv_search [NEW] `M`

**상태**: ✅ 완료. `internal/server/server.go` — query/top_k/filters/include_history/rerank 파라미터 + `SearchResponse` 구조화 출력.

**파일**: `tools/cks-mcp/internal/server/server.go` (tool 등록)

**인터페이스**: Phase 3 설계 문서 Section 7.1 참조

**완료 기준**:
- [ ] MCP tool로 호출 가능
- [ ] query, top_k, filters, include_history, rerank 파라미터 지원
- [ ] 결과 JSON 포맷 일치

---

## P3-9. MCP Tool: ckv_index [NEW] `S`

**상태**: ✅ 완료. `internal/server/server.go` — full/incremental + modules + since_commit + 진행률 stderr 로깅.

**인터페이스**: Phase 3 설계 문서 Section 7.2 참조

**완료 기준**:
- [ ] full/incremental 모드 지원
- [ ] 인덱싱 통계 반환

---

## P3-10. Sensitive Filter (Go 포팅) [ADAPT] `M`

**상태**: ✅ 완료. `internal/filter/` — jira-gateway-mcp에서 포팅. RI-22: `CKS_PATTERNS_PATH` 환경변수가 `PATTERNS_PATH`보다 우선. fail-safe 동작 검증.

**파일**: `tools/cks-mcp/internal/filter/engine.go`

**입력**: Phase 2의 TypeScript 필터 엔진과 동일 로직, Go로 재구현

**핵심 차이점**:
- Go의 regexp 패키지 사용 (PCRE가 아닌 RE2)
- 일부 regex가 RE2에서 지원되지 않을 수 있음 → 패턴 검증 필요
- shared/patterns.json을 embed 또는 런타임 로드

**완료 기준**:
- [ ] Phase 2와 동일한 패턴에 대해 동일한 결과
- [ ] RE2 호환성 확인 (lookbehind 등 미지원 패턴 대체)
