# Phase 4: CKS MCP - CKG Graph Search — 작업 상세

> 설계 문서: [phase4-cks-mcp-ckg.md](../superpowers/specs/phase4-cks-mcp-ckg.md)

---

## P4-1. Graph Store (SQLite Adjacency) [NEW] `L`

**상태**: ✅ 완료. `tools/cks-mcp/internal/ckg/store.go` — graph_nodes, graph_edges, symbol_history, concurrency_context 4테이블 + 인덱스 + CRUD + 6개 인덱스. CKV와 동일 SQLite 파일에 공존.

**파일**: `tools/cks-mcp/internal/ckg/store.go`

**핵심 로직**:
```go
type GraphStore struct {
    db *sql.DB
}

func (s *GraphStore) Init() error {
    // 4개 테이블 생성: graph_nodes, graph_edges, symbol_history, concurrency_context
    // 인덱스 6개 생성 (Phase 4 설계 Section 2.2)
}

func (s *GraphStore) UpsertNode(node GraphNode) error
func (s *GraphStore) UpsertEdge(edge GraphEdge) error
func (s *GraphStore) AddHistory(entry SymbolHistory) error
func (s *GraphStore) AddConcurrency(ctx ConcurrencyContext) error

func (s *GraphStore) Traverse(startIDs []string, depth int, relTypes []string) (*TraversalResult, error) {
    // WITH RECURSIVE CTE 기반 BFS
    // depth 제한 + 관계 유형 필터
    // max_nodes/max_edges 제한
}
```

**완료 기준**:
- [ ] 4개 테이블 정상 생성
- [ ] Traverse가 재귀 CTE로 depth 기반 BFS 수행
- [ ] max_nodes(200), max_edges(500) 제한 동작

---

## P4-2. AST Relation Extractor [NEW] `XL`

**상태**: ✅ 완료. `internal/ckg/relations.go` — 7개 관계 추출. **RI-10 반영**: Tier 1 typed(`golang.org/x/tools/go/packages`) → 실패 시 Tier 2 AST-only 자동 폴백, confidence 등급 부여(`high`/`medium`/`low`).

**파일**: `tools/cks-mcp/internal/ckg/relations.go`

**입력**: Go 프로젝트 루트 경로

**출력**: `[]GraphNode`, `[]GraphEdge`

**핵심 로직**:
```go
func ExtractRelations(root string) ([]GraphNode, []GraphEdge, error) {
    // golang.org/x/tools/go/packages로 전체 프로젝트 타입 체크
    cfg := &packages.Config{
        Mode: packages.NeedTypes | packages.NeedSyntax | 
              packages.NeedDeps | packages.NeedImports | packages.NeedTypesInfo,
        Dir: root,
    }
    pkgs, _ := packages.Load(cfg, "./...")
    
    for _, pkg := range pkgs {
        for _, file := range pkg.Syntax {
            // 각 파일에서 7개 관계 추출
            nodes, edges := extractFromFile(file, pkg.TypesInfo, pkg.Fset)
        }
    }
}
```

**7개 관계 유형별 추출**:

```go
// calls: CallExpr 내부의 함수/메서드 참조 resolve
func extractCalls(fn *ast.FuncDecl, info *types.Info) []GraphEdge {
    ast.Inspect(fn.Body, func(n ast.Node) bool {
        if call, ok := n.(*ast.CallExpr); ok {
            callee := resolveCallee(call.Fun, info)
            // callee의 qualified name으로 edge 생성
        }
        return true
    })
}

// implements: concrete type이 interface의 메서드 셋을 충족하는지
func extractImplements(pkg *types.Package) []GraphEdge {
    // 모든 named type에 대해
    // 모든 interface에 대해
    // types.Implements(T, I) 체크
}

// uses_type: 함수 파라미터, 리턴, 로컬변수의 타입 참조
func extractUsesType(fn *ast.FuncDecl, info *types.Info) []GraphEdge

// embeds: 구조체의 익명 필드
func extractEmbeds(st *ast.StructType) []GraphEdge

// reads_field / writes_field: SelectorExpr이 좌변/우변인지
func extractFieldAccess(fn *ast.FuncDecl, info *types.Info) []GraphEdge

// channels: chan 타입의 send(<-) / receive(=<-) 연산
func extractChannels(fn *ast.FuncDecl, info *types.Info) []GraphEdge
```

**난이도가 XL인 이유**:
- `go/types`의 타입 resolve는 cross-package 의존성 전체를 로드해야 함
- 인터페이스를 통한 간접 호출(polymorphic call)은 다중 엣지 생성
- 타입 assertion, 타입 스위치 케이스도 관계에 포함
- geth fork의 대규모 코드에서 메모리/시간 관리 필요

**완료 기준**:
- [ ] 7개 관계 유형 모두 추출
- [ ] cross-package 타입 resolve 동작
- [ ] 인터페이스 → 구현체 다중 엣지 생성
- [ ] go-stablenet에서 관계 추출 완료 (30분 이내)

---

## P4-3. Git History Analyzer [NEW] `M`

**상태**: ✅ 완료. `internal/ckg/history.go` — `git log -L startLine,endLine:file` + `--follow` 폴백. 커밋 분류(bugfix/feature/refactor/test/change). `SummarizeHistory` 텍스트 생성기.

**파일**: `tools/cks-mcp/internal/ckg/history.go`

**핵심 로직**:
```go
func AnalyzeSymbolHistory(filePath string, startLine, endLine int, limit int) ([]SymbolHistory, error) {
    // git log -L {startLine},{endLine}:{filePath} --format="%H|%s|%ai|%an" -{limit}
    // 출력 파싱 → SymbolHistory 배열
    
    // 각 커밋의 변경 유형 분류:
    classifyChange(commitMsg string) string {
        if match("(?i)(fix|bug|patch)") → "bugfix"
        if match("(?i)(add|feat|implement|new)") → "feature"
        if match("(?i)(refactor|rename|move|clean)") → "refactor"
        if match("(?i)(test)") → "test"
        default → "change"
    }
}

func AnalyzeFileHistory(filePath string, limit int) ([]SymbolHistory, error) {
    // git log --follow -{limit} {filePath}
    // 파일 이름 변경 추적
}

func SummarizeHistory(entries []SymbolHistory) string {
    // 최근 N개 커밋을 한 줄씩 요약:
    // "2026-05-20: [bugfix] nil pointer guard (author)"
}
```

**buddy 참고**: `plugin/skills/summarize-retro/PROCEDURE.md` — git log 분석 패턴

**완료 기준**:
- [ ] 심볼별(줄 범위) git 히스토리 수집
- [ ] 파일 이름 변경 추적 (--follow)
- [ ] 커밋 유형 자동 분류 (bugfix/feature/refactor/test/change)
- [ ] 히스토리 요약 문자열 생성

---

## P4-4. Concurrency Analyzer [NEW] `XL`

**상태**: ✅ 완료. `internal/ckg/concurrency.go` — goroutine 시작점, channel send/receive, mutex/atomic/select/waitgroup, 공유 receiver 필드 쓰기 탐지. **RI-11 반영**: interface-dispatch goroutine은 `confidence=unknown` + `risk=unknown` + note 명시.

**파일**: `tools/cks-mcp/internal/ckg/concurrency.go`

**핵심 로직**:
```go
func AnalyzeConcurrency(pkg *packages.Package) []ConcurrencyContext {
    for _, file := range pkg.Syntax {
        ast.Inspect(file, func(n ast.Node) bool {
            switch stmt := n.(type) {
            case *ast.GoStmt:
                // goroutine 시작점 탐지
                // launched_by: 이 go 문을 포함하는 함수
                // launches: go 문이 실행하는 함수
                
            case *ast.SendStmt:
                // channel send: ch <- val
                // channel 변수 resolve → 동일 채널의 receive 쪽 매칭
                
            case *ast.UnaryExpr:
                if stmt.Op == token.ARROW {
                    // channel receive: <-ch
                }
                
            case *ast.CallExpr:
                // mutex Lock/RLock/Unlock 탐지
                // atomic.Load*/Store* 탐지
                // sync.WaitGroup Add/Wait 탐지
            }
            return true
        })
    }
}

func DetectSharedResources(nodes []GraphNode, edges []GraphEdge, concCtx []ConcurrencyContext) []SharedResource {
    // 여러 goroutine에서 접근하는 동일 구조체 필드 → shared resource
    // mutex로 보호되는지 여부 확인
    // 보호되지 않은 공유 접근 → race condition risk
}

func AssessRisk(shared []SharedResource) RiskAssessment {
    // unprotected shared access → "high"
    // all protected → "low"
    // partial → "medium"
    // 순환 lock 패턴 감지 → deadlock potential
}
```

**난이도가 XL인 이유**:
- goroutine의 실행 범위 분석은 정적 분석의 한계가 있음 (runtime dispatch)
- channel counterpart 매칭은 타입 + 스코프 분석 필요
- mutex의 Lock/Unlock 범위 추적은 defer 패턴 고려 필요
- geth fork에서 goroutine이 매우 많아 분석 범위 관리 필요

**완료 기준**:
- [ ] goroutine 시작점(go 문) 탐지 + launched_by/launches 매핑
- [ ] channel send/receive 쌍 매칭
- [ ] mutex Lock/Unlock 범위 분석
- [ ] 공유 자원 식별 + 보호 여부 확인
- [ ] race condition 리스크 평가 (none/low/medium/high)

---

## P4-5. Traversal Query Engine [NEW] `M`

**상태**: ✅ 완료. `internal/ckg/traversal.go` — BFS + depth/relation/direction 필터 + max_nodes/max_edges 캡 + truncation 보고.

**파일**: `tools/cks-mcp/internal/ckg/traversal.go`

**핵심 로직**:
```go
func (s *GraphStore) Traverse(startIDs []string, depth int, relTypes []string, maxNodes int) (*TraversalResult, error) {
    // SQL WITH RECURSIVE CTE (Phase 4 설계 Section 6.2)
    // relTypes가 비어있으면 전체, 있으면 필터
    // depth 제한 + maxNodes 제한
    // 결과에 시작점으로부터의 거리(depth) 포함
}
```

**완료 기준**:
- [ ] depth=1, 2, 3 각각 올바른 결과
- [ ] 관계 유형 필터 동작
- [ ] maxNodes 초과 시 truncated=true

---

## P4-6. MCP Tool: ckg_query [NEW] `M`

**상태**: ✅ 완료. `internal/server/server.go`의 `makeCKGQueryHandler` — symbols/depth/relation_types/include_history/include_concurrency/max_nodes/max_edges.

**인터페이스**: Phase 4 설계 Section 7.1 참조

**완료 기준**:
- [ ] symbols로 시작 노드 resolve (qualified name + short name 매칭)
- [ ] depth, relation_types, include_history, include_concurrency 파라미터
- [ ] nodes + edges + history + concurrency_impact 반환

---

## P4-7. MCP Tool: ckg_impact [NEW] `L`

**상태**: ✅ 완료. `internal/ckg/query.go`의 `Impact` — direct/indirect callers, interface contracts, test files, concurrency risk, risk classification (delete/signature/logic 별 트리).

**파일**: `tools/cks-mcp/internal/ckg/impact.go`

**핵심 로직**:
```go
func AnalyzeImpact(symbol string, changeType string) (*ImpactResult, error) {
    // 1. symbol → node resolve
    // 2. reverse traverse: 이 심볼을 호출하는 함수 (callers)
    //    depth=1 → direct_callers
    //    depth=2+ → indirect_callers
    // 3. implements: 이 심볼이 구현하는 인터페이스
    // 4. test coverage: *_test.go에서 이 심볼을 참조하는 파일
    // 5. concurrency risk: 이 심볼의 ConcurrencyContext 조회
    // 6. changeType에 따른 영향 평가:
    //    "signature" → interface 계약 변경 가능 → high risk
    //    "logic" → 호출자에 영향 적음 → medium risk (동시성 제외)
    //    "delete" → 모든 호출자 영향 → critical
    // 7. recommended_test_scope: 영향 받는 테스트 파일 목록
}
```

**완료 기준**:
- [ ] direct/indirect callers 정확 반환
- [ ] interface contracts 식별
- [ ] 관련 test files 목록
- [ ] risk_level 판정 (low/medium/high/critical)
- [ ] recommended_test_scope 반환

---

## P4-8. MCP Tool: ckg_index [NEW] `M`

**상태**: ✅ 완료. `internal/ckg/indexer.go` + 서버 핸들러. 전체 관계 추출 → 노드/엣지 upsert → 노드별 history → concurrency context. mode 필드로 Tier 1/2 보고.

**핵심 로직**: CKV indexer와 통합. AST 1회 파싱 후 CKV 청킹 + CKG 관계 추출 동시 수행.

**완료 기준**:
- [ ] full/incremental 모드
- [ ] CKV + CKG 통합 인덱싱
- [ ] 노드/엣지/히스토리/동시성 통계 반환

---

## P4-9. CKV + CKG 통합 검색 흐름 [NEW] `M`

**상태**: ✅ 완료. `cmd/server/main.go`에서 CKV와 CKG가 동일 SQLite 파일을 공유. ckv_search → 심볼 추출 → ckg_query 시퀀스가 단일 인덱스 위에서 동작.

**파일**: `tools/cks-mcp/internal/server/server.go`에서 tool 조합 패턴 문서화

실제 구현은 Agent 레벨(Phase 5)에서 수행. 여기서는 CKS MCP가 두 tool을 제공하고, Planner Agent가 순차 호출하는 패턴을 검증.

**검증 시나리오**:
```
1. ckv_search("staking reward overflow", top_k=10)
   → 결과에서 "governance.CalcReward", "wbft.Finalize" 식별

2. ckg_query(symbols=["governance.CalcReward"], depth=2, include_history=true)
   → 호출 관계 + 히스토리 반환

3. ckg_impact(symbol="governance.CalcReward", change_type="logic")
   → 영향 범위 + 리스크 반환
```

**완료 기준**:
- [ ] CKV → CKG 순차 호출 패턴이 의미 있는 결과 반환
- [ ] go-stablenet 실제 코드에서 검증
