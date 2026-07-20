# Phase 4: CKS MCP - CKG (Code Knowledge Graph)

> go-stablenet 코드베이스의 구조 기반 검색 엔진.
> 심볼의 의존성, 호출 관계, 동시성 영향 범위, 변경 히스토리를 그래프로 제공한다.

## 1. CKG 전체 아키텍처

```
┌────────────────────────────────────────────────────────┐
│                     CKG Engine                          │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  AST         │  │ Git History  │  │ Concurrency  │ │
│  │  Relation    │  │ Analyzer     │  │ Analyzer     │ │
│  │  Extractor   │  │              │  │              │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                  │                  │         │
│  ┌──────▼──────────────────▼──────────────────▼──────┐ │
│  │                Graph Store                         │ │
│  │  Nodes: symbols (func, type, interface, var)       │ │
│  │  Edges: calls, implements, uses, channels, mutex   │ │
│  └───────────────────────┬────────────────────────────┘ │
│                          │                               │
│  ┌───────────────────────▼────────────────────────────┐ │
│  │              Traversal Query Engine                  │ │
│  │  BFS/DFS + depth control + relation filter          │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Graph Store

### 2.1 선택: SQLite (Adjacency List Model)

별도 그래프 DB 대신 SQLite의 adjacency list 패턴을 사용한다.

```
이유:
- CKV와 동일 SQLite 파일에 통합 가능 → 단일 DB 관리
- go-stablenet 규모 (~20000 심볼, ~100000 엣지)에 충분
- 재귀 CTE(WITH RECURSIVE)로 그래프 탐색 가능
- 외부 서비스 불필요

대안 비교:
- Neo4j embedded: Java 의존성, Go에서 사용 불편
- DGraph: 별도 서버 필요
- Cayley: Go 네이티브지만 유지보수 상태 불안정
```

### 2.2 스키마

```sql
-- 노드: 코드 심볼
CREATE TABLE graph_nodes (
  id TEXT PRIMARY KEY,              -- hash(package + symbol_name)
  file_path TEXT NOT NULL,
  package_name TEXT NOT NULL,
  symbol_name TEXT NOT NULL,
  symbol_type TEXT NOT NULL,         -- function, method, struct, interface, var, const
  qualified_name TEXT NOT NULL,      -- "consensus/wbft.(*WBFTEngine).Finalize"
  signature TEXT,
  code_snippet TEXT,                 -- 코드 상위 20줄 (미리보기)
  start_line INTEGER,
  end_line INTEGER,
  indexed_at TEXT NOT NULL
);

-- 엣지: 심볼 간 관계
CREATE TABLE graph_edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_node TEXT NOT NULL REFERENCES graph_nodes(id),
  to_node TEXT NOT NULL REFERENCES graph_nodes(id),
  relation_type TEXT NOT NULL,       -- calls, implements, uses_type, embeds,
                                     -- channels, mutex_guards, reads_field, writes_field
  metadata TEXT,                     -- JSON: 추가 정보 (호출 위치, channel 이름 등)
  UNIQUE(from_node, to_node, relation_type)
);

-- 변경 히스토리: 심볼별 git log
CREATE TABLE symbol_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id TEXT NOT NULL REFERENCES graph_nodes(id),
  commit_hash TEXT NOT NULL,
  commit_message TEXT,
  commit_date TEXT,
  author TEXT,
  diff_summary TEXT,                 -- 변경 요약 (추가/삭제 줄 수, 변경 유형)
  UNIQUE(node_id, commit_hash)
);

-- 동시성 컨텍스트
CREATE TABLE concurrency_context (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id TEXT NOT NULL REFERENCES graph_nodes(id),
  goroutine_context TEXT,            -- "launched in consensus.Start()"
  shared_resources TEXT,             -- JSON array: ["stateDB", "txPool"]
  sync_mechanisms TEXT,              -- JSON array: ["sync.RWMutex", "chan Block"]
  channel_operations TEXT            -- JSON array: [{chan, direction, type}]
);

-- 인덱스
CREATE INDEX idx_edges_from ON graph_edges(from_node);
CREATE INDEX idx_edges_to ON graph_edges(to_node);
CREATE INDEX idx_edges_type ON graph_edges(relation_type);
CREATE INDEX idx_nodes_package ON graph_nodes(package_name);
CREATE INDEX idx_nodes_qualified ON graph_nodes(qualified_name);
CREATE INDEX idx_history_node ON symbol_history(node_id);
CREATE INDEX idx_concurrency_node ON concurrency_context(node_id);
```

---

## 3. AST Relation Extractor

### 3.1 추출 대상 관계 유형

| 관계 유형 | 의미 | AST 탐지 방법 |
|-----------|------|---------------|
| `calls` | A가 B를 호출 | `CallExpr`의 `Fun` 필드 resolve |
| `implements` | 타입 A가 인터페이스 B를 구현 | 메서드 셋 비교 |
| `uses_type` | 함수 A가 타입 B를 파라미터/리턴/로컬변수로 사용 | 타입 참조 resolve |
| `embeds` | 구조체 A가 구조체 B를 임베딩 | 익명 필드 탐지 |
| `reads_field` | 함수 A가 구조체 B의 필드를 읽음 | `SelectorExpr` 분석 |
| `writes_field` | 함수 A가 구조체 B의 필드에 쓰기 | `AssignStmt` + `SelectorExpr` |
| `channels` | A와 B가 동일 채널로 통신 | channel 타입 + send/receive 분석 |
| `mutex_guards` | A가 mutex를 잠그고 B를 호출 | `Lock()/RLock()` 범위 내 호출 분석 |

### 3.2 관계 추출 상세

#### calls 관계 추출

```go
// AST 순회: FuncDecl 내부의 CallExpr 탐색
// 
// 직접 호출: foo()
//   → CallExpr.Fun == Ident{Name: "foo"}
//
// 메서드 호출: obj.Method()
//   → CallExpr.Fun == SelectorExpr{X: obj, Sel: "Method"}
//
// 인터페이스 통한 호출: iface.Do()
//   → 타입 정보로 어떤 구현체가 가능한지 resolve
//   → 다중 엣지 생성 (A → impl1.Do, A → impl2.Do)

extractCalls(funcDecl *ast.FuncDecl, typeInfo *types.Info) → []Edge
```

#### implements 관계 추출

```go
// Go의 구조적 타이핑(structural typing): 
// 타입 T가 인터페이스 I의 모든 메서드를 갖고 있으면 implements
//
// 탐지: 모든 (concrete type, interface) 쌍에 대해
// types.Implements(concreteType, interfaceType) 호출

extractImplements(pkg *types.Package) → []Edge
```

#### embeds 관계 추출

```go
// 구조체의 익명 필드 = 임베딩
// type Engine struct {
//     *StateProcessor    ← embeds
//     config Config      ← uses_type (not embed)
// }

extractEmbeds(structType *ast.StructType) → []Edge
```

### 3.3 타입 정보 해석

관계 추출의 정확도는 타입 정보에 의존한다. `go/types` 패키지를 사용하여 전체 프로젝트의 타입 정보를 resolve한다.

```go
// 전체 프로젝트 타입 체크
cfg := &packages.Config{
    Mode: packages.NeedTypes | packages.NeedSyntax | packages.NeedDeps | packages.NeedImports,
    Dir:  projectRoot,
}
pkgs, err := packages.Load(cfg, "./...")

// 각 패키지의 타입 정보로 관계 추출
for _, pkg := range pkgs {
    for _, file := range pkg.Syntax {
        extractRelations(file, pkg.TypesInfo)
    }
}
```

---

## 4. Git History Analyzer

### 4.1 심볼별 변경 히스토리 수집

```
각 노드(심볼)에 대해:

1. 파일 경로 + 줄 범위로 git log 조회
   git log -L {start_line},{end_line}:{file_path} --format="%H|%s|%ai|%an" -10

2. 파일 이름 변경 추적
   git log --follow -10 {file_path}

3. 각 커밋에 대해 diff 요약 생성
   - 추가/삭제 줄 수
   - 변경 유형 분류:
     "signature_change": 함수 시그니처 변경
     "logic_change": 함수 내부 로직 변경
     "refactor": 이름 변경, 코드 이동
     "bugfix": 커밋 메시지에 fix/bug 키워드
     "feature": 커밋 메시지에 add/feat/implement 키워드
```

### 4.2 히스토리 요약 생성

```
summarize_history(commits):
  최근 10개 커밋을 시간순으로 요약:
  
  "2026-05-20: [bugfix] nil pointer 방지 guard 추가 (author)
   2026-05-15: [feature] staking reward 계산 로직 추가 (author)
   2026-05-01: [refactor] Finalize → FinalizeBlock 이름 변경 (author)"
```

---

## 5. Concurrency Analyzer

### 5.1 분석 대상 패턴

go-stablenet(geth fork)의 동시성 패턴:

| 패턴 | 탐지 방법 | 의미 |
|------|----------|------|
| goroutine 시작 | `go func(){}()`, `go obj.Method()` | 비동기 실행 컨텍스트 |
| channel send/receive | `ch <- val`, `val = <-ch` | goroutine 간 통신 |
| sync.Mutex/RWMutex | `mu.Lock()`, `mu.RLock()` | 공유 자원 보호 |
| sync.WaitGroup | `wg.Add()`, `wg.Wait()` | goroutine 동기화 |
| context.Context | 함수 파라미터에 `ctx context.Context` | 취소/타임아웃 전파 |
| select 문 | `select { case ... }` | 다중 채널 대기 |
| atomic 연산 | `atomic.Load*`, `atomic.Store*` | 락 없는 공유 변수 |

### 5.2 동시성 영향 그래프 구축

```
concurrency_graph 구축 단계:

1. goroutine 시작점 탐지
   → 각 go 문에서 실행되는 함수를 goroutine_context로 기록
   → 예: "go engine.processBlocks()" → processBlocks의 goroutine_context = "launched by engine.Start()"

2. 공유 자원 식별
   → 같은 구조체의 필드가 여러 goroutine에서 접근되면 shared_resource
   → mutex로 보호되는지 여부 확인
   → 보호되지 않은 공유 접근 → 잠재적 race condition 경고

3. 채널 의존성
   → 동일 채널 타입의 send/receive 쌍을 매칭
   → 채널 방향성 추적: 생산자 → 채널 → 소비자

4. 동시성 영향 범위
   → 함수 A를 수정하면 영향 받는 goroutine 목록
   → 함수 A가 접근하는 공유 자원 → 같은 자원을 접근하는 다른 함수 목록
```

### 5.3 concurrency_impact 응답 구조

```typescript
interface ConcurrencyImpact {
  symbol: string;                    // 분석 대상 심볼
  
  goroutine_context: {
    launched_by: string[];           // 이 함수를 goroutine으로 실행하는 함수
    launches: string[];              // 이 함수가 goroutine으로 실행하는 함수
  };
  
  shared_resources: Array<{
    resource: string;                // "engine.stateDB", "txPool.pending"
    access_type: "read" | "write" | "read_write";
    protected_by: string | null;     // "engine.mu" 또는 null (보호 안 됨)
    other_accessors: string[];       // 같은 자원을 접근하는 다른 함수
  }>;
  
  channel_participation: Array<{
    channel: string;                 // "blockCh"
    channel_type: string;           // "chan *types.Block"
    direction: "send" | "receive" | "both";
    counterparts: string[];         // 반대편 함수
  }>;
  
  sync_mechanisms: Array<{
    type: "mutex" | "rwmutex" | "waitgroup" | "context" | "atomic" | "select";
    variable: string;
    scope: string;                   // "entire_function" | "partial"
  }>;
  
  risk_assessment: {
    race_condition_risk: "none" | "low" | "medium" | "high";
    unprotected_shared_access: string[];  // 보호되지 않은 공유 접근
    deadlock_potential: string[];         // 순환 lock 가능성
  };
}
```

---

## 6. Traversal Query Engine

### 6.1 그래프 탐색 알고리즘

```
ckg_query 처리:

1. 시작 노드 resolve
   symbols 목록 → graph_nodes에서 qualified_name 매칭
   매칭 실패 시 → LIKE 검색으로 후보 제안

2. BFS 탐색 (depth 제어)
   depth=1: 직접 호출/참조만
   depth=2: 2-hop 관계까지
   depth=3+: 광범위 (결과 크기 제한 적용)

3. 관계 유형 필터
   include_types: ["calls", "implements"]  → 이 유형만 탐색
   exclude_types: ["reads_field"]          → 이 유형 제외

4. 결과 구성
   nodes: 탐색된 모든 노드
   edges: 탐색된 모든 엣지
   (+ history, concurrency_impact 옵션)
```

### 6.2 재귀 CTE 쿼리 예시

```sql
-- depth=2까지의 calls 관계 탐색
WITH RECURSIVE call_graph AS (
  -- 시작 노드
  SELECT n.id, n.qualified_name, n.symbol_type, 0 as depth
  FROM graph_nodes n
  WHERE n.qualified_name IN (?)
  
  UNION ALL
  
  -- 재귀: calls 관계를 따라 확장
  SELECT n2.id, n2.qualified_name, n2.symbol_type, cg.depth + 1
  FROM call_graph cg
  JOIN graph_edges e ON e.from_node = cg.id
  JOIN graph_nodes n2 ON e.to_node = n2.id
  WHERE e.relation_type = 'calls'
    AND cg.depth < ?  -- depth 제한
)
SELECT DISTINCT * FROM call_graph;
```

### 6.3 결과 크기 제한

```
대규모 코드베이스에서 depth=3 이상은 결과가 폭발적으로 증가할 수 있다.

제한:
- max_nodes: 200 (기본)
- max_edges: 500 (기본)
- depth가 높을수록 score가 낮은 엣지부터 제거
- 우선순위: calls > implements > uses_type > embeds > reads_field > channels
```

---

## 7. MCP Tool 인터페이스

### 7.1 ckg_query

```typescript
// Input
interface CkgQueryInput {
  symbols: string[];           // 검색 시작 심볼 (qualified name 또는 short name)
  depth?: number;              // 탐색 깊이 (기본: 2)
  relation_types?: string[];   // 포함할 관계 유형 (기본: 전체)
  include_history?: boolean;   // git 히스토리 포함 (기본: false)
  include_concurrency?: boolean; // 동시성 분석 포함 (기본: false)
  max_nodes?: number;          // 최대 노드 수 (기본: 200)
}

// Output
interface CkgQueryOutput {
  nodes: Array<{
    id: string;
    symbol: string;            // qualified name
    file: string;
    symbol_type: string;
    signature: string;
    code_snippet: string;      // 상위 20줄
    depth: number;             // 시작점으로부터의 거리
  }>;
  
  edges: Array<{
    from: string;              // node id
    to: string;
    relation_type: string;
    metadata?: Record<string, unknown>;
  }>;
  
  history?: Array<{
    symbol: string;
    commits: Array<{
      hash: string;
      message: string;
      date: string;
      author: string;
      diff_summary: string;
    }>;
  }>;
  
  concurrency_impact?: ConcurrencyImpact[];
  
  metadata: {
    total_nodes: number;
    total_edges: number;
    truncated: boolean;        // max 제한으로 잘렸는지
    query_time_ms: number;
  };
}
```

### 7.2 ckg_impact

특정 심볼을 수정했을 때의 영향 범위를 분석하는 편의 tool.

```typescript
// Input
interface CkgImpactInput {
  symbol: string;              // 수정 대상 심볼
  change_type: "signature" | "logic" | "delete";  // 변경 유형
}

// Output
interface CkgImpactOutput {
  direct_callers: string[];    // 이 심볼을 직접 호출하는 함수
  indirect_callers: string[];  // 간접 호출 (depth 2+)
  interface_contracts: string[];// 이 심볼이 구현하는 인터페이스
  test_files: string[];        // 이 심볼을 테스트하는 파일
  
  concurrency_risk: {
    affected_goroutines: string[];
    shared_resource_conflicts: string[];
  };
  
  recommended_test_scope: string[];  // 검증이 필요한 테스트 파일/패키지
  
  risk_level: "low" | "medium" | "high" | "critical";
  risk_explanation: string;
}
```

### 7.3 ckg_index

```typescript
// 그래프 인덱싱 트리거
interface CkgIndexInput {
  mode: "full" | "incremental";
  project_root: string;
}

interface CkgIndexOutput {
  nodes_created: number;
  edges_created: number;
  history_entries: number;
  concurrency_contexts: number;
  duration_ms: number;
}
```

---

## 8. CKV + CKG 통합 검색 흐름

Agent가 실제로 사용하는 전형적인 검색 시퀀스:

```
[Planner Agent의 ANALYSIS 단계]

Step 1: CKV로 의미 검색
  ckv_search(query="staking reward 계산 overflow 방지", top_k=10)
  → 관련 코드 후보 10건 반환

Step 2: CKV 결과에서 핵심 심볼 추출
  → "governance.CalcReward", "wbft.Finalize", "types.StakingInfo"

Step 3: CKG로 구조 탐색
  ckg_query(
    symbols=["governance.CalcReward", "wbft.Finalize"],
    depth=2,
    include_history=true,
    include_concurrency=true
  )
  → 호출 관계, 의존성, 히스토리, 동시성 영향 반환

Step 4: CKG Impact 분석
  ckg_impact(symbol="governance.CalcReward", change_type="logic")
  → 영향 범위, 리스크 레벨, 필요 테스트 범위 반환

Step 5: 종합
  CKV 결과 (관련 코드) + CKG 결과 (구조/히스토리/동시성)
  → analysis.md, related-code.json 생성
```

---

## 9. Indexing 통합

CKV와 CKG의 인덱싱은 동시에 수행하여 효율화한다.

```
통합 인덱싱 파이프라인:

1. git ls-files '*.go' → 파일 목록
2. 각 파일에 대해:
   a. Go AST Parse (1회만)
   b. CKV: 청크 생성 + 임베딩
   c. CKG: 관계 추출 + 노드/엣지 생성
3. CKG: 전체 타입 정보 resolve (cross-package)
4. CKG: Git History 수집
5. CKG: Concurrency 분석
6. 결과 저장:
   .coding-agent/index/ckv.db (벡터 + 청크)
   .coding-agent/index/ckg.db (그래프, 또는 동일 DB)
```

단일 DB 파일로 통합할지 분리할지는 구현 시 결정. 성능 벤치마크 후 판단.

---

## 10. Phase 4 완료 기준

- [ ] AST Relation Extractor가 7개 관계 유형(calls, implements, uses_type, embeds, reads_field, writes_field, channels) 추출
- [ ] Graph Store (SQLite adjacency)에 노드/엣지 저장
- [ ] Git History Analyzer가 심볼별 변경 히스토리 수집
- [ ] Concurrency Analyzer가 goroutine/channel/mutex 패턴 분석
- [ ] ckg_query MCP tool이 depth 기반 그래프 탐색 결과 반환
- [ ] ckg_impact MCP tool이 변경 영향 범위 분석
- [ ] CKV + CKG 통합 인덱싱 파이프라인
- [ ] 결과 크기 제한(max_nodes, max_edges) 동작
- [ ] 타입 정보 resolve (cross-package)
