# 03 — cks Refactor: Detailed Design + Implementation Plan

> **⚠ CORRECTION (integrated audit, P1-C1):** Per `00` §3, **coding-agent (`05`) is the SOLE author** of `coding-agent/contract/agent-mcp.schema.json`. This plan's Step 6 / §(c) "SSoT schema" / risk #7 instructions to **author** that file are **OVERRIDDEN**. cks instead: (1) consumes a vendored fixture `internal/mcp/testdata/agent-mcp.schema.json` synced from the `05` canonical via a CI diff-check; (2) keeps `schema_golden_test.go` asserting its registered `cks.*` set ⊆ that fixture. Do NOT author the canonical file from cks. (If cks lands before `05`, ship the fixture as a provisional copy + add the diff-check when `05` lands.)

> **Derives from:** `00-system-contract.md` (C1 incl. NEW `concurrency_impact` + `ops.index`; C2; §4; §5) + `03-cks-refactor.md` (G1–G8, composer, domain sync, M2 acceptance).
> **Repo:** `github.com/0xmhha/code-knowledge-system` at `/Users/wm-it-22-00661/Work/github/tools/code-knowledge-system` (`go 1.25.5`, toolchain `go1.25.9`, HEAD `58e276b`). `go build ./...` exits 0 today.
> **Isolation:** This repo is the LARGEST refactor and is **gated** on 02 (ckv) and 01 (ckg) publishing their `pkg/` surfaces. It is implementable in one session *only after* those two land. The C1 schema is frozen in `00`.

## Dependency note — what MUST ship first (verified against live 01/02 HEAD)

cks build is **blocked** until these land in the sibling repos:

- **From 02 (ckv), REQUIRED:**
  - `pkg/embed/ollama` — **NOT yet promoted** (verified: still `internal/embed/ollama/`; `ls pkg/embed/ollama` → absent). cks's G1+G2 both import it. **Hard blocker.**
  - `pkg/ckv.Engine.Freshness() (FreshnessReport, error)` — **NOT yet present** (verified: `pkg/ckv/ckv.go` exposes only `CheckFreshness() error` at `:174`; no `Freshness`/`FreshnessReport`). cks G6 needs the structured method. **Blocker for G6 only.**
  - Already present and importable: `pkg/ckv.Open(path, OpenOptions{Embedder})` (`ckv.go:131`), `Engine.SemanticSearch(ctx, intent, SearchOptions)` (`:149`), `Manifest()` (`:159`), `Warmup` (`:199`), `Close` (`:183`), `MockEmbedder()` (`:210`).
- **From 01 (ckg), REQUIRED:**
  - `pkg/concurrency.Analyze(r store.Reader, symbol string, opt Options) (Result, error)` — **NOT yet present** (verified: `ls pkg/concurrency` → absent). cks G7 wraps it. **Hard blocker for G7.**
  - Already present and importable (verified): `pkg/impact.Compute(store persist.StoreReader, seedQname, seedFile string, opt Options) (map[string]any, error)` (`impact.go:102`); `pkg/evidence.BuildPack(store persist.StoreReader, opt Options) (*Pack, error)` (`evidence.go:145`); `pkg/store.Reader = persist.StoreReader` alias (`store.go:46`) with `GetNodePRs`, `SubgraphByQname`, `NeighborhoodByQname`, `SearchFTS` (`SearchHit`-returning, `Score`/`RawScore`); `pkg/store.PRRef = types.PRRef` (`store.go:65`).

**Critical aliasing fact (unblocks G3):** `store.Reader` is a *type alias* for `persist.StoreReader` (`ckg/pkg/store/store.go:46`). cks's `realStoreReader` already holds a `store.Reader` field (`ckgclient/real.go:62`). Therefore cks can call `impact.Compute(r, …)` and `evidence.BuildPack(r, …)` by passing that same `store.Reader` value — it satisfies the `persist.StoreReader` parameter identically. **No wrapper needed** (this is the 01-plan risk #4 resolved in cks's favor: cks holds the real `store.Reader`, not an interface subset).

## Build note — sqlite-vec CGO inheritance (live-code confirmed)

cks today is **CGO-free** (go.mod requires only ckg, which uses `modernc.org/sqlite`, CGO-free). After G1 adds `require code-knowledge-vector`, cks's build **inherits sqlite-vec CGO** from `pkg/ckv`'s store (`ckv/internal/store/sqlitevec` imports `sqlite-vec-go-bindings/cgo`, per 02-plan D2). The **embedder** path (`pkg/embed/ollama`, pure HTTP) stays CGO-free, but the overall cks binary is **not** CGO-free post-G1. The build toolchain must support sqlite-vec (a light, standard CGO dep — not the heavy ONNX/`bgeonnx`/`libonnxruntime` stack, which cks still avoids by using Ollama). Flag in SETUP: `CGO_ENABLED=1` + a C toolchain required for cks-mcp once G1 lands.

---

## Part A — Detailed Design

### Tool surface — current vs target (the spine of G7/G8)

**STATUS: 11 tools registered; need +2.** `internal/mcp/server.go:74-84` registers exactly 11 handlers: `get_for_task, health, find_symbol, find_callers, find_callees, get_subgraph, impact_analysis, change_history, semantic_search, search_text, freshness`. This matches C1 minus the two NEW tools. **Remaining:** add `registerConcurrencyImpact` (G7) and `registerOpsIndex` (G8) to the `Register` call list and the `Deps` struct stays the shape it is (G8 needs new fields — see G8).

NB: `server.go`'s package doc (`:4-9`) still claims "registers two tools" — stale comment; update when touching the file.

---

### G1 — in-process `pkg/ckv` import + delete `ckvclient` subprocess proxy

**STATUS: remaining (proxy fully present).** Verified:
- `internal/ckvclient/real.go` is the **543-LOC subprocess MCP proxy** (`grep -c` → 543 lines; `spawnAndInitialize` at `:150` spawns `ckv mcp --out=<path>`; `DefaultCallTimeout = 10*time.Second` at `:81`; `callToolWithRestart`/`restart` at `:297`/`:351` are the hang-recovery machinery the spec's 2/9 timeouts came from).
- `cmd/cks-mcp/main.go:176-194` `buildCKVClient` constructs it via `ckvclient.NewReal(ctx, RealOpts{...})`.
- `internal/config/config.go:78-83` `CKVConfig` carries `BinaryPath`/`Path`/`EmbedModel`/`TimeoutMS` — all subprocess-flavored.
- go.mod (verified) requires ckg but **NOT** ckv.

**Target design — replace the proxy with an in-process adapter:**

1. **go.mod:** `go get github.com/0xmhha/code-knowledge-vector@<02-HEAD>` → adds the require. (This is the CGO-inheriting line; do it first so the build surface is known.)

2. **New `internal/ckvclient/real.go`** (rewrite, ~120 LOC vs 543) implementing the **unchanged `Client` interface** (`interface.go:30` — `SemanticSearch`, `Health`, `Freshness`, `Close`). The interface is the seam the composer programs against (`stage1.New(ckv, ckg, …)`), so it stays byte-identical; only the impl swaps. Construction:
   ```go
   import (
       "github.com/0xmhha/code-knowledge-vector/pkg/ckv"
       "github.com/0xmhha/code-knowledge-vector/pkg/embed/ollama"
   )
   type Real struct{ eng *ckv.Engine }
   func NewReal(ctx context.Context, opts RealOpts) (*Real, error) {
       adapter, err := ollama.Open(ollama.Options{
           Endpoint:  opts.OllamaURL,           // default http://localhost:11434
           ModelName: opts.EmbedModel,          // "bge-m3"
       })
       if err != nil { return nil, fmt.Errorf("ckvclient: ollama: %w", err) } // fail fast (S5)
       eng, err := ckv.Open(opts.DataPath, ckv.OpenOptions{Embedder: adapter})
       if err != nil { return nil, fmt.Errorf("ckvclient: ckv.Open: %w", err) }
       return &Real{eng: eng}, nil
   }
   func (r *Real) SemanticSearch(ctx context.Context, query string, opts SearchOpts) ([]contract.Hit, error) {
       resp, err := r.eng.SemanticSearch(ctx, query, ckv.SearchOptions{K: opts.K, /* map Filter */})
       // translate ckv.Hit → contract.Hit (Citation, Rank, Score=Normalized, Source=HitSourceCKV)
   }
   func (r *Real) Freshness(ctx context.Context) (FreshnessReport, error) {
       rep, err := r.eng.Freshness() // 02's NEW structured method (G6)
       return FreshnessReport{Fresh: rep.Fresh, IndexedHead: rep.IndexedHead, CurrentHead: rep.CurrentHead, ChangedFiles: rep.ChangedFiles}, err
   }
   func (r *Real) Health(ctx context.Context) (Health, error) { /* from eng.Manifest() */ }
   func (r *Real) Close() error { return r.eng.Close() }
   ```
   The wire-payload structs (`queryHitWire`, `healthWire`, etc., real.go:410-448) and the mcp-go transport imports are **deleted** — there is no subprocess. The `ckv.Hit`/`ckv.Manifest` types are now native Go values (`ckv.go:84`,`:103`).

3. **`RealOpts`** loses `BinaryPath`/`ModelDir`/`Env`/`CallTimeout`/`spawn`; gains `OllamaURL`. **`CKVConfig`** (config.go:78) likewise: drop `BinaryPath`, keep `Path` (now the ckv-data dir for `ckv.Open`), keep `EmbedModel`, add `OllamaURL string` (default `http://localhost:11434`). Update `cks.yaml.example` (`policies/cks.yaml.example:14-18`: replace `embed_model: "bge-base-onnx"` → `embed_model: "bge-m3"`, add `ollama_url`).

4. **`cmd/cks-mcp/main.go:176-194` `buildCKVClient`** rewires to the new opts. Keep the **Smart Dummy fallback** (`ckvclient.NewDummy()`, dummy.go) for `cfg.Path == ""` AND **add a degraded path**: when `cfg.Path != ""` but `ollama.Open` fails, **do not crash** — log a warning, fall back to `NewDummy()`, and mark a flag so `cks.ops.health` reports `degraded: embedder unavailable` (see G-health below). This satisfies `00` §6/S5.

5. **Error/degraded handling (S5):** `ollama.Open` fails fast with a clear error string (02-plan: `"ollama: connectivity check failed"`). cks catches it at `buildCKVClient`, surfaces it through health (not a panic). The Smart Dummy records would-be calls as `DummyInstruction`s (dummy.go:81-92) so the agent can proceed via session retrieval.

**Health degraded wiring:** `internal/mcp/health.go:84` `aggregateHealthStatus(ckgUp, ckvUp)` already returns `"degraded"` when ckg is up but ckv is down — but the Dummy reports `Reachable:true` (dummy.go:122-127), so a degraded ckv would falsely read "ok". **Fix:** give the Dummy-in-degraded-mode a Health that reports `Reachable:false` with `Error:"embedder unavailable: <reason>"`, OR thread a `Degraded bool` into `Deps` and special-case the status. Recommended: a tiny `DegradedDummy` (Dummy with `Health` returning `Reachable:false, Error:…`) so the existing aggregator yields `degraded` unchanged.

**Test:** `go test ./internal/ckvclient/` after rewriting `real_test.go` to drive the in-process engine against `ckv.MockEmbedder()` (no Ollama, no subprocess). The old subprocess restart tests (`real_test.go` mock-client machinery) are deleted with the proxy.

---

### G2 — real intent embedder (FakeEmbedder dim 32 → bge-m3 dim 1024)

**STATUS: remaining (FakeEmbedder still wired).** Verified:
- `cmd/cks-mcp/main.go:109` `embedder := &intent.FakeEmbedder{Dim: 32}`.
- `intent.FakeEmbedder` (embedder.go:44) is a SHA-256 hash→PRNG noise vector (`hashVector`, embedder.go:86) — meaning-free, so cosine similarities are random → intent routing is noise.

**How the classifier builds/compares prototypes (cited):** `intent.New` (classifier.go:79) **eagerly embeds every anchor at construction** (`classifier.go:97-105`: loops `defaultAnchors`, calls `embedder.Embed(ctx, text)`, caches `anchor{Text, Vec}` in `c.embedded`). `Classify` (classifier.go:141) embeds the prompt once (`:146`) and takes the max cosine over all cached anchor vecs (`:155-164`), thresholded at `DefaultUnknownThreshold = 0.6` (`:22`). **Prototypes are NOT precomputed/persisted — they are embedded at runtime from `defaultAnchors` (anchors.go:20) on every process start.** This is the key mechanic: there is **no stale prototype file to regenerate** — swapping the embedder automatically re-embeds all 50 anchors (9 intents × 5-7 Korean/English texts) with bge-m3 at startup. The "regenerate prototypes" worry in `03 G2` is **moot** because embedding is lazy-at-construction, not cached on disk.

**Exact change:**
1. `cmd/cks-mcp/main.go:109` — replace `&intent.FakeEmbedder{Dim: 32}` with a real bge-m3 embedder. Reuse the **same** `ollama.Open(ollama.Options{ModelName: "bge-m3"})` adapter constructed for ckv (G1) so anchor + query + chunk vectors share one model/space. The adapter must satisfy `intent.Embedder` (embedder.go:27: `Embed(ctx, text) ([]float32, error)`). The ckv ollama adapter's method is likely `Embed(ctx, text) ([]float32, error)` or `EmbedBatch` — **verify the signature at edit time**; if it's batch-only, wrap it in a 3-line `intentEmbedderAdapter` that calls the batch path with a single text. Construct it **once** and pass the same instance to both `buildCKVClient`'s adapter and `buildComposer`'s `embedder` arg.
2. **Dim assertion (startup check, S3):** after constructing the embedder, before `intent.New`, assert `embedder.Dimension() == 1024` (bge-m3) — fail fast if Ollama served a different model. Since prototypes are embedded from the same `embedder`, query-dim == prototype-dim is structurally guaranteed; the only failure mode is "Ollama returned a non-1024 vector," which the assertion catches. Add a helper `assertEmbedderDim(embedder, 1024)` in main.go. (The `FakeEmbedder.Dim: 32` had no such guard — that's why intent stayed silently broken.)
3. **Degraded mode:** if Ollama is down, the intent classifier cannot embed anchors → `intent.New` errors at startup (`classifier.go:101`). Handle the same as G1's degraded path: fall back to `FakeEmbedder{Dim:1024}` ONLY in degraded mode (so the pipeline still runs, intent is noise but `IntentUnknown` fan-out is acceptable), and let health report degraded. **Decision:** in degraded mode use `FakeEmbedder{Dim:1024}` (not 32) so any future dim assertion downstream stays consistent.

**Test:** a startup test asserting `assertEmbedderDim` rejects a 64-dim stub; a classifier test (real bge-m3, skip-gated on Ollama) asserting two paraphrases of the same intent ("X 가 깨졌어요" / "X is broken") both classify `IntentBugFix` with cosine ≥ 0.6 — the M2.c "stable non-random intents" gate.

---

### G3 — wire the 4 ckg methods

**STATUS: 1 of 4 already wired; 3 remaining as stubs.** Verified in `internal/ckgclient/real.go`:
- `GetSubgraph` (real.go:358) — **already wired** to `r.s.SubgraphByQname(qname, depth)` and translates nodes/edges. ✅ (The `get_subgraph` tool, graph.go:201, already works against it.)
- `ImpactOfChange` (real.go:332) — **STUB**: returns `ImpactResult{Seed: seedQname}` with no groups.
- `EvidenceForIntent` (real.go:341) — **STUB**: returns `ChangeHistoryResult{Seed: opts.SeedQname}` empty.
- `GetNodePRs` (real.go:350) — **STUB**: returns `nil`.

The 01-plan's risk #3 noted these are cks-side gaps, not ckg gaps. The handlers already call them (`analysis.go:68` impact, `:124` evidence, `:138` prs) — they just receive empty results today.

**The seam problem (must fix first):** cks's `storeReader` interface (real.go:48-56) exposes only `SearchFTS([]types.Node)`, `FindSymbol`, `NodesByFilePath`, `NeighborhoodByQname`, `SubgraphByQname`. It does **NOT** expose the underlying `store.Reader` that `impact.Compute`/`evidence.BuildPack`/`GetNodePRs` need. The `realStoreReader` struct (real.go:61) *holds* the real `store.Reader` (`r store.Reader`), but the cks-internal `storeReader` interface hides it. **Design: widen the seam** — add three methods to the `storeReader` interface so the Real adapter can reach them, and implement them on `realStoreReader` as passthroughs:
```go
// add to storeReader interface (real.go:48)
ImpactCompute(seedQname, seedFile string, includeBlobs bool) (map[string]any, error)
EvidenceBuildPack(intent, seedQname string, k int) (*evidence.Pack, error)
GetNodePRs(qname string, cutoff time.Time) ([]store.PRRef, error)
// implement on realStoreReader: call impact.Compute(a.r, …), evidence.BuildPack(a.r, …), a.r.GetNodePRs(…)
```
(Putting the `impact`/`evidence` calls behind the seam keeps mocks injectable — the existing test pattern, real.go:134 `newRealWithStore`. Tests inject a `storeReader` returning canned `map[string]any`/`*evidence.Pack`.)

**Per-method wiring:**

| cks method | ckg pkg call (01-plan/live-verified) | cks-side work |
|---|---|---|
| `ImpactOfChange(seedQname, opts)` | `impact.Compute(store.Reader, seedQname, seedFile, impact.Options{IncludeBlobs:false})` → `map[string]any` keyed `callers/interface_impact/type_users/distributed/concurrent/other` (`impact.go:58-64,234-241`) | **(a)** resolve `seedFile`: `impact.Compute` needs `seedFile` too (`impact.go:102`); cks has only the qname. Resolve via `r.s.FindSymbol(seedQname, "", false)` → take `Node.FilePath`. **(b)** translate `map[string]any` groups → `contract.ImpactResult{Groups: []ImpactGroup}` (impact.go in contract: `ImpactCallers/ImpactInterface/ImpactTypeUsers/ImpactDistributed/ImpactConcurrent/ImpactOther`, contract/impact.go:6-12). Map ckg key `interface_impact`→`ImpactInterface`. Each group's node list → `[]Citation`. |
| `EvidenceForIntent(intent, opts)` | `evidence.BuildPack(store.Reader, evidence.Options{Intent:intent, SeedQname:opts.SeedQname, K:opts.K})` → `*evidence.Pack` (`evidence.go:145`, Options `:54`) | translate `Pack.Hits[].Hunks[]` (HunkRow: `FilePath`,`StartLine`,`PatchText`, evidence.go:115-118) → `contract.HunkEvidence{File,StartLine,EndLine,Patch,Score}` (contract/history.go:18). Commit SHAs → optional `PRRef`s if available; else leave PRs to GetNodePRs. |
| `GetNodePRs(qname, opts)` | `store.Reader.GetNodePRs(nodeID, cutoff)` → `[]store.PRRef` (= `types.PRRef`, store.go:63-65) | resolve qname → nodeID via `FindSymbol`; call `GetNodePRs`; translate `types.PRRef` → `contract.PRRef{Number,Title,Summary,BaseSHA,HeadSHA,MergedAt,Repo}` (contract/history.go:6). `opts.MaxCount` truncates. |
| `GetSubgraph` | already wired (real.go:358) | none. |

**Test:** extend `internal/ckgclient/real_test.go` with a mock `storeReader` returning a canned impact map / evidence pack / PR slice; assert the translation. Then an MCP-level test (`analysis_test.go`) that `impact_analysis` returns non-empty `Groups` and `change_history` returns hunks+PRs.

---

### G5 — stop synthesizing BM25 score; consume ckg's real Score/RawScore

**STATUS: remaining (synthesis live).** Verified: `ckgclient/real.go:196` `Score: 1.0 - float64(i)/float64(n+1)` — the fake gradient. Root cause (01-plan G1): cks's seam calls `SearchFTS(q, limit) ([]types.Node, error)` (real.go:50,78) — the **`[]types.Node` path that drops scores** — instead of ckg's real `SearchFTS(q, limit, opts) ([]store.SearchHit, error)` which carries `Score ∈[0,1]` + `RawScore` (01-plan confirms ckg already provides them, `search_hit.go:80-84`).

**Exact change:**
1. **Widen the seam:** change `storeReader.SearchFTS` (real.go:50) from `(q string, limit int) ([]types.Node, error)` to `(q string, limit int) ([]store.SearchHit, error)`, and `realStoreReader.SearchFTS` (real.go:78) to call `a.r.SearchFTS(q, limit, store.SearchFTSOptions{})` (the `SearchHit`-returning path). `store.SearchHit` embeds `Node` + `Score`/`RawScore` (01-plan).
2. **`BM25Search` (real.go:160-205):** replace the loop. Iterate `[]store.SearchHit`; use `hit.Node` for the citation/filter, and set `Score: hit.Score` (real already-normalized, descending). **Delete** the `1.0 - i/(n+1)` synthesis at `:196` and the `n := len(nodes)` line at `:187`. Keep `Rank: i+1`.
3. **Edge case (01-plan note):** degenerate single-row / all-equal results set every `Score=1.0` (ckg's min-max maps uniform strength to 1.0, not 0). Document in the cks code comment that `1.0` means "uniform strength," not "perfect" — downstream stage2 weighting (stage2/searcher.go) must not over-trust it.

**Test:** mock `storeReader.SearchFTS` returns `[]store.SearchHit` with known descending Scores; assert `BM25Search` passes them through verbatim (not re-synthesized). Update `real_test.go` SearchFTS mocks (currently return `[]types.Node`).

NB this seam widening touches the same `storeReader` interface as G3 — do G3 and G5 in one seam-rewrite commit to avoid double-churning real_test.go mocks.

---

### G6 — wire structured Freshness

**STATUS: remaining; blocked on 02.** Verified: `ckvclient/real.go:262` `Freshness` returns `FreshnessReport{}` stub; the MCP handler (`freshness.go:43`) already calls `d.CKV.Freshness(ctx)` and shapes the response correctly. The dummy (dummy.go:98) returns `{Fresh:true}` and records an instruction.

**Exact call (after 02 adds `Engine.Freshness()`):** in the **new in-process** `ckvclient.Real.Freshness` (G1 step 2):
```go
func (r *Real) Freshness(ctx context.Context) (FreshnessReport, error) {
    rep, err := r.eng.Freshness()              // 02 G6: pkg/ckv.Engine.Freshness() (ckv.FreshnessReport, error)
    if err != nil { return FreshnessReport{}, fmt.Errorf("ckvclient: freshness: %w", err) }
    return FreshnessReport{
        Fresh:        rep.Fresh,
        IndexedHead:  rep.IndexedHead,
        CurrentHead:  rep.CurrentHead,
        ChangedFiles: rep.ChangedFiles,
    }, nil
}
```
`ckv.FreshnessReport` mirrors `internal/freshness.Report{IndexedHead, CurrentHead, ChangedFiles, Stale, Fresh}` (02-plan). cks's `FreshnessReport` (interface.go:57) already has the matching fields. No handler change. **Folded into the G1 rewrite** — the in-process `Real` implements it directly.

---

### G7 — NEW `cks.context.concurrency_impact` tool

**STATUS: remaining (no concurrency handler exists, grep-confirmed; no `ConcurrencyImpact` on `ckgclient.Client`).**

**(a) ckgclient method.** Add to `Client` interface (interface.go:28) and `Real`:
```go
ConcurrencyImpact(ctx context.Context, symbol string, opts ConcurrencyOpts) (contract.ConcurrencyResult, error)
// opts: Depth int (default 3 — channel reach is one hop deeper than calls, per 01-plan note 7), MaxTotal int
```
`Real.ConcurrencyImpact` widens the seam with `ConcurrencyAnalyze(symbol string, depth, maxTotal int) (concurrency.Result, error)` on `storeReader`, implemented on `realStoreReader` as `concurrency.Analyze(a.r, symbol, concurrency.Options{Depth:depth, MaxTotal:maxTotal})` (01-plan signature: `Analyze(r store.Reader, symbol string, opt Options) (Result, error)`). Translate `concurrency.Result.Modules` (id/type/name/qname/file_path/start_line/citation/direction) → a new `contract.ConcurrencyResult`:
```go
// pkg/contract/concurrency.go (NEW)
type ConcurrencyModule struct {
    Citation  Citation `json:"citation"`
    Qname     string   `json:"qname"`
    Name      string   `json:"name"`
    Kind      string   `json:"kind"`
    Direction string   `json:"direction"` // affects | affected_by | both
}
type ConcurrencyResult struct {
    Seed     string              `json:"seed"`
    Depth    int                 `json:"depth"`
    Modules  []ConcurrencyModule `json:"modules"`
    NotFound bool                `json:"not_found,omitempty"`
}
```

**(b) Handler + registration** (`internal/mcp/analysis.go` or new `concurrency.go`):
```go
const ToolNameConcurrencyImpact = "cks.context.concurrency_impact"
// schema:
//   symbol   (string, required) — fully-qualified symbol
//   depth    (number, optional, default 3)
//   max_total(number, optional, default 0=unbounded)
```
- **Input JSON:** `{ "symbol": "consensus.wbft.Finalize", "depth": 3, "max_total": 50 }`.
- **Output JSON:** `{ "seed": "...", "depth": 3, "modules": [ {"citation":{"file":...,"start_line":...}, "qname":..., "name":..., "kind":..., "direction":"affected_by"} ], "instructions": [] }`.
- Handler mirrors `handleImpactAnalysis` (analysis.go:55): require `symbol`, build `ConcurrencyOpts{Depth: intArg(req,"depth",3), MaxTotal: intArg(req,"max_total",0)}`, attach instruction collector, call `d.CKG.ConcurrencyImpact`, return `NewToolResultStructured`.
- Register in `server.go` `Register` after `registerImpactAnalysis` (`server.go:80`).
- **Dummy:** add `ConcurrencyImpact` to `ckgclient.Dummy` recording a `DummyInstruction{Backend:"ckg", Operation:"ConcurrencyImpact"}` so degraded mode still flows.

**(c) SSoT schema.** Add the tool to `coding-agent/contract/agent-mcp.schema.json` — **this file does NOT exist yet** (verified: no `coding-agent/contract/` dir). **It must be created** as part of this work (it is the C1 SSoT, owned by coding-agent per `00` S4, but no repo has authored it). Author the full C1 tool set (all 13 tools incl. the 2 NEW) so the golden test below has something to assert against. See "SSoT schema" subsection.

---

### G8 — NEW `cks.ops.index` tool

**STATUS: remaining (no index/reindex handler, grep-confirmed).**

**Schema:**
```
const ToolNameOpsIndex = "cks.ops.index"
//   mode         (string, optional, "full"|"incremental", default "incremental")
//   since_commit (string, optional) — base commit for incremental diff
```
- **Input JSON:** `{ "mode": "incremental", "since_commit": "abc123" }`.
- **Output JSON:** `{ "mode": "incremental", "ckv": {"reindexed": 42, "ok": true}, "ckg": {"rebuilt": true, "ok": true}, "indexed_head": "def456" }`.

**Handler design — two sub-actions:**
1. **ckv reindex:** the in-process `pkg/ckv.Engine` does **not** expose a reindex method in its public surface (verified: `ckv.go` has `Open/SemanticSearch/Manifest/CheckFreshness/Freshness/Warmup/Close` — no `Reindex`). Two options:
   - **(A) shell to `ckv reindex`** (`ckv build`/`reindex` CLI per 02-plan) against `cfg.Backends.CKV.Path` + `--src <SourceRoot>`. Deterministic, but reintroduces a subprocess (only for the *index* op, not the query path — acceptable, the hang risk was in per-query calls).
   - **(B)** request 02 expose `Engine.Reindex(ctx, mode)` on `pkg/ckv`. Cleaner but adds a cross-repo dependency not in 02's plan.
   - **Decision: (A) shell out for the index op.** It's an explicit agent-triggered maintenance call (not in the hot retrieval loop), and 02-plan's index story is CLI-based (`ckv build`/`reindex`). Keep the binary path in `CKVConfig` for *this* purpose only (don't fully delete it in G1 — repurpose `BinaryPath` as `IndexBinaryPath`).
2. **ckg incremental:** likewise shell to `ckg build`/`ckg watch` (01-plan §4 confirms `ckg build --src` is the path; no in-process incremental API). `ckg`'s `runIncremental` partial-cache is disabled (`00` §10 risk) → cold rebuild is the fallback (~40s).

Both sub-actions run, collect exit status + new `indexed_head` (re-read manifest after), return the structured result. On either failure, return an `IsError` result with the failing backend named. This needs `Deps` to gain `IndexerCKV`/`IndexerCKG` config (binary paths, src root) — add an `Indexer` field to `Deps` or pass `cfg` through. **Decision:** add `IndexConfig` to `Deps` (`CKVBinary, CKGBinary, CKVDataPath, CKGDataPath, SourceRoot string`) wired from `cfg` in main.go.

**Register** in `server.go` after `registerFreshness`. **Dummy:** `cks.ops.index` in dummy/degraded mode records an instruction telling the agent to run the index CLIs manually.

---

### Composer tuning + per-stage instrumentation

**STATUS: remaining.** Verified: `composer.go:139` captures `start := time.Now()`, and `emitFootprint` (`composer.go:289-315`) emits a single `composer.compose_complete` event with only **`zap.Duration("elapsed", …)`** — total wall-clock, no per-stage breakdown. Citation count flows uncapped from stage2→budget (no default cap surfaced at the composer level).

**Over-retrieval tuning (dogfood precision 2-24%, returns 35-53 citations):**
- The budget allocator (`internal/composer/budget/allocator.go`) is the gate. Lower the **default budget tokens** and/or add a **default max-citation cap** so the agent isn't flooded. The agent's depth/budget knobs (control) override; the composer's *default* tightens.
- Add a `MaxCitations int` knob to the budget allocator's options (default e.g. 12) so `Compose` truncates after greedy fit. Surface it as a `get_for_task` optional input (`max_citations`) per C1's "budget/depth knobs."

**Per-stage latency instrumentation:** wrap each stage call in `Compose` (composer.go:150-193) with `t0 := time.Now()` … `stageMs := time.Since(t0)`, accumulate into a `map[string]time.Duration`, and emit per-stage durations in `emitFootprint` (`zap.Duration("intent_ms",…)`, `"stage1_ms"`, … `"stage5_ms"`). This lets `00` §9's validation spike attribute cost. Keep the existing `elapsed` total. **Decision:** add a `stageTimings` struct threaded through `Compose` → `emitFootprint`; ~15 lines, no behavior change.

---

### Domain SSoT sync codegen

**STATUS: partial — glossary codegen DONE; ckv `watch_out` + ckg `policy.yaml` derivation MISSING.** Verified:
- `cmd/cks-glossary-gen` (main.go) **already** derives `glossary.yaml` from `entries/*.yaml` (gated on `status: verified`, default). ✅ This is one of the three derived views.
- **No codegen** for ckv `policy/stablenet.yaml` `watch_out`/`also_review`/`required_tests` nor ckg `policy.yaml` `governed_by` — grep `watch_out|governed_by|stablenet.yaml` across cks `*.go` → **0 hits**. The master entries exist (`docs/domain-knowledge/projects/go-stablenet/entries/*.yaml`, 30+ files) and the ckv consumer view exists (`code-knowledge-vector/policy/stablenet.yaml`, hand-maintained), but the **derivation** is not automated.

**Target design — new `cmd/cks-domain-sync` (or extend cks-glossary-gen):**
- Scan `entries/*.yaml` with `status: verified`.
- Derive **(a) ckv view:** for each entry's `category`/`risk_level`/`invariants`/`pitfalls`, emit `policy/stablenet.yaml` `category → {watch_out, also_review, required_tests}` strings (match the existing hand-authored shape, ckv `policy/stablenet.yaml`).
- Derive **(b) ckg view:** entries with `code_anchors` → ckg `policy.yaml` `Policy` nodes + `governed_by` edge mappings (qname → policy id).
- Write both to the sibling repos' expected paths (or to a staging dir the operator copies). One cks edit → both consumers refresh on next reindex (`00` §4.1).
- **Reuse** the inventory loader (`internal/inventory/load.go`, `types.go`) which already parses the entry schema (used by cks-glossary-gen).

**Runtime note (not a code gap):** `grep "status: verified"` across `entries/` returns **0** today — every entry is below `verified`. So all three derived views (glossary included) currently emit **empty** until the curation session (`00` §4.2, ~6 byzantine-fairness entries) promotes entries to `verified`. The codegen is correct; its *output* is gated on curation. Flag this in Part D.

---

### SSoT schema file (C1 conformance) — must be created

**STATUS: missing entirely.** Verified: no `coding-agent/contract/agent-mcp.schema.json`; no schema golden test in cks (`grep schema.json` → only an unrelated `pkg/contract/intent.go` match).

**Target:** author `coding-agent/contract/agent-mcp.schema.json` as the C1 SSoT — a JSON Schema enumerating all **13** cks agent-facing tools (the 11 live + `concurrency_impact` + `ops.index`) with their input/output shapes, plus the jira(6) and chainbench tool names (those are owned by their own conformance tests; cks asserts only the `cks.*` subset). Add a cks **golden test** (`internal/mcp/schema_golden_test.go`) that:
1. Boots the server, enumerates registered tool names,
2. Asserts the `cks.*` set == the schema's `cks.*` set (no drift, no extras),
3. Optionally validates each tool's input schema against the SSoT.

This is M2.a. The schema file lives in the coding-agent repo but is **created by this session** (cks is the first provider to need it).

---

## Part B — Implementation Plan (ordered, test-gated)

> Order keeps cks compiling at each step. The two NEW tools are discrete steps. The **proxy deletion (G1) lands only after the in-process path is green** — but since the proxy and the new impl share the `Client` interface, the swap is atomic per file. The go.mod require + in-process import comes early (it's the build-surface change everything else assumes).

**PRE — confirm 01+02 landed.** Verify `pkg/embed/ollama`, `pkg/ckv.Engine.Freshness`, and `pkg/concurrency.Analyze` exist in the sibling repos' tags cks will `go get`. If absent, STOP — cks cannot build. (Hard gate.)

**Step 0 — Baseline green.** Files: none. Action: `go build ./... && go test ./...`. Test: exit 0 (confirmed today). Commit: none.

**Step 1 — go.mod require ckv + in-process ckvclient.Real (G1 + G6).** Files: `go.mod`, `go.sum`, `internal/ckvclient/real.go` (rewrite), `internal/ckvclient/real_test.go` (rewrite to MockEmbedder, drop subprocess tests), `internal/ckvclient/interface.go` (add `OllamaURL` to `RealOpts` if RealOpts lives here — it's in real.go), `internal/config/config.go` (`CKVConfig`: drop `BinaryPath` query-use, add `OllamaURL`; keep `Path`), `policies/cks.yaml.example`. Action: `go get code-knowledge-vector`; rewrite `Real` to `ollama.Open`→`ckv.Open`→`SemanticSearch`/`Freshness`/`Health`/`Close`; delete wire structs + transport imports. Test: `go test ./internal/ckvclient/` (MockEmbedder, no Ollama). Commit: "feat(ckv): in-process pkg/ckv + Ollama bge-m3; structured Freshness (G1,G6)".

**Step 2 — main.go wiring + degraded mode (G1 cont., G2).** Files: `cmd/cks-mcp/main.go`. Action: construct one `ollama.Open(bge-m3)` adapter; pass to `buildCKVClient` AND as `intent.Embedder` (replace `FakeEmbedder{Dim:32}` at `:109`); add `assertEmbedderDim(embedder,1024)`; on `ollama.Open` failure fall back to Smart Dummy + degraded flag; wire `DegradedDummy` so health reports degraded. Test: `go build ./cmd/... && go test ./cmd/cks-mcp/...` (skip-gate Ollama tests). Commit: "feat(intent): real bge-m3 embedder + dim assert + degraded fallback (G2,S5)".

**Step 3 — widen storeReader seam + real BM25 score (G5) + 3 ckg methods (G3).** Files: `internal/ckgclient/real.go` (widen `storeReader` interface + `realStoreReader`; rewrite `BM25Search`, `ImpactOfChange`, `EvidenceForIntent`, `GetNodePRs`), `internal/ckgclient/real_test.go` (update mocks: `SearchFTS`→`[]store.SearchHit`; add impact/evidence/PR canned returns), `pkg/contract` (no change — types exist). Action: per Part A G3+G5 (one seam rewrite). Test: `go test ./internal/ckgclient/ ./internal/mcp/ -run 'Impact|Change|Search'`. Commit: "feat(ckg): real BM25 score + wire impact/evidence/node-PRs (G3,G5)".

**Step 4 — NEW tool: concurrency_impact (G7).** Files: `pkg/contract/concurrency.go` (new types), `internal/ckgclient/{interface.go,real.go,dummy.go}` (add `ConcurrencyImpact` + seam method `ConcurrencyAnalyze`), `internal/mcp/concurrency.go` (new handler+register), `internal/mcp/server.go` (add to `Register`). Action: per Part A G7. Test: `go test ./internal/ckgclient/ ./internal/mcp/ -run Concurrency`. Commit: "feat(mcp): add cks.context.concurrency_impact tool (G7,S1)".

**Step 5 — NEW tool: ops.index (G8).** Files: `internal/mcp/ops_index.go` (new handler+register), `internal/mcp/server.go` (add to `Register` + `Deps.IndexConfig`), `cmd/cks-mcp/main.go` (wire IndexConfig from cfg), `internal/config/config.go` (index binary/src paths). Action: per Part A G8 (shell `ckv reindex` + `ckg build`). Test: `go test ./internal/mcp/ -run OpsIndex` (mock exec or skip-gate binaries). Commit: "feat(mcp): add cks.ops.index tool (G8,S2)".

**Step 6 — SSoT schema + golden test.** Files: `coding-agent/contract/agent-mcp.schema.json` (NEW), `internal/mcp/schema_golden_test.go` (NEW). Action: author the 13-tool C1 schema; golden test asserts registered `cks.*` set == schema. Test: `go test ./internal/mcp/ -run SchemaGolden`. Commit: "test(mcp): C1 SSoT schema + golden conformance (M2.a)".

**Step 7 — composer tuning + per-stage instrumentation.** Files: `internal/composer/composer.go` (per-stage timings, `max_citations`), `internal/composer/budget/allocator.go` (default cap), `internal/mcp/server.go`+`get_for_task.go` (`max_citations` input). Action: per Part A composer section. Test: `go test ./internal/composer/...`. Commit: "feat(composer): cap default citations + per-stage latency (00 §3)".

**Step 8 — domain sync codegen (ckv watch_out + ckg policy.yaml).** Files: `cmd/cks-domain-sync/main.go` (new), reuse `internal/inventory`. Action: derive ckv `stablenet.yaml` + ckg `policy.yaml` from `verified` entries. Test: `go test ./cmd/cks-domain-sync/...` (fixture entries → expected yaml). Commit: "feat(domain): codegen ckv watch_out + ckg policy from cks entries (00 §4.1)".

**Step 9 — go-stablenet config + full build/test gate.** Files: `policies/cks.yaml.example` (point ckv/ckg at real go-stablenet index paths, glossary path, ollama_url). Action: `go build ./... && go test ./...`. Test: full gate (Part C). Commit: "chore(config): point cks at go-stablenet index + bge-m3 + ollama (C3)".

> **Proxy deletion timing:** the subprocess `real.go` is *replaced* in Step 1 (not a separate deletion step) — once the in-process `Real` compiles and its tests pass, the old subprocess code is already gone from the file. The mcp-go client transport imports drop in Step 1's `go mod tidy`.

---

## Part C — Verification & Acceptance

**Full-repo gate (after every destructive step, mandatory before "done"):**
```
go build ./...
go test ./...
go vet ./...
grep -rn 'ckv mcp\|spawnAndInitialize\|callToolWithRestart\|mcpgotransport' internal/ckvclient/ | wc -l   # expect 0 (proxy gone)
grep -c 'code-knowledge-vector' go.mod                                                                      # expect ≥1 (ckv required)
grep -rn 'FakeEmbedder{Dim: 32}' cmd/                                                                       # expect 0 (G2)
grep -rn '1.0 - float64(i)/float64(n+1)' internal/ckgclient/                                                # expect 0 (G5)
```

**M2 acceptance (`03` §7) → command map:**

| M2 clause | Proof |
|---|---|
| (a) registers exactly the C1 SSoT tool set (incl. concurrency_impact + ops.index); passes schema golden test | Step-6 `go test ./internal/mcp/ -run SchemaGolden`; assert 13 `cks.*` tools |
| (b) no subprocess `ckvclient`; ckv via `pkg/ckv` + Ollama bge-m3 in-process | grep gate above (0 transport refs); `go test ./internal/ckvclient/` green on MockEmbedder |
| (c) intent classifier returns stable non-random intents; dim assertion passes | Step-2 classifier test (paraphrase→same intent, cosine≥0.6, skip-gate Ollama); `assertEmbedderDim` rejects non-1024 |
| (d) `cks-eval` deterministic scenarios pass against go-stablenet index | `cks-eval -scenarios ./eval/scenarios/ -config ./policies/cks.yaml` (spawns cks-mcp; zero-LLM, confirmed) |
| (e) `cks.ops.health` reports degraded (not crash) when Ollama down | degraded-mode test: construct with unreachable OllamaURL → `buildCKVClient` falls back to DegradedDummy → `handleHealth` returns `status:"degraded"` |

**Ollama + bge-m3 runtime prereq:** M2.c/d/e against the **real** index require `ollama serve` + `ollama pull bge-m3`. All **unit** gates (ckvclient MockEmbedder, ckgclient mock storeReader, schema golden, composer, dim-assert-rejection) run with **no Ollama** — CI stays green without a model server. The bge-m3 go-stablenet index itself is built by 02's operator-gated rebuild (~10h, 02-plan D4). Document the prereq in coding-agent `SETUP.md` (cross-ref `05`).

**Degraded-mode test (explicit, M2.e):** point `CKVConfig.OllamaURL` at a closed port; assert (1) cks-mcp starts (no crash), (2) `cks.ops.health` → `status:"degraded"` with `ckv.error` set, (3) `get_for_task` still returns a pack (via Smart Dummy instructions). No Ollama needed.

---

## Part D — Risks / Unknowns (live-code findings the spec didn't anticipate)

1. **cks is FAR ahead of the `03` spec on G4; the spec's gap is stale (HIGH, grep+read).** `03` G4 claims `vocab.Resolver` is **nil/unimplemented** and lists it as remaining work with `main.go:118`. **Live reality:** `internal/vocab/resolver.go` is a **complete implementation** (`New`/`Load`/`Resolve`/`EntryCount`, 144 LOC), wired into Stage 1 (`extractor.go:36,150,191`), constructed in `main.go:118-121,162-167`, and the glossary codegen (`cmd/cks-glossary-gen`) already exists. **G4 is DONE.** Drop it from scope — only verify the glossary path is populated (gated on `verified` entries, see #5).

2. **The 4-method "unwired" gap is 75% accurate but `GetSubgraph` is already wired (HIGH).** `03` G3 lists all 4 as unwired. Live: `GetSubgraph` (real.go:358) is **fully wired** via `SubgraphByQname`; only `ImpactOfChange`/`EvidenceForIntent`/`GetNodePRs` are stubs (real.go:332/341/350). Re-scope G3 to 3 methods. The handlers already call all 4 (`analysis.go`, `graph.go`) — they just get empty results from the 3 stubs.

3. **`impact.Compute` needs `seedFile`, which cks doesn't have at the seam (MID).** `impact.Compute(store, seedQname, seedFile, opt)` (impact.go:102) takes **two** seed args. cks's `ImpactOfChange(seedQname, opts)` has only the qname. Must resolve `seedFile` via `FindSymbol(seedQname)→Node.FilePath` first (extra round-trip). If `FindSymbol` returns multiple definitions, pick the first or pass empty (verify `impact.Compute`'s behavior with empty `seedFile` — it may fall back to qname-only resolution). **Flag for a read of impact.go:102-140 at edit time.**

4. **`store.Reader` alias makes G3 trivial — BUT the cks seam hides it (MID, resolved).** `store.Reader = persist.StoreReader` (store.go:46), and cks's `realStoreReader.r` IS a `store.Reader` (real.go:62). So `impact.Compute(a.r,…)`/`evidence.BuildPack(a.r,…)` compile directly — the 01-plan risk #4 (external caller can't name `persist.StoreReader`) does NOT bite cks because cks holds the alias. The only work is **widening the cks-internal `storeReader` interface** to expose these (Part A G3). Confirm the alias identity holds across the module boundary at compile time (Step 3 build is the check).

5. **All domain entries are below `status: verified` → derived views emit empty (HIGH, fact).** `grep "status: verified" entries/` → **0**. The glossary codegen (done) and the new ckv/ckg sync codegen (Step 8) both gate on `verified`, so they produce **empty output** until the `00` §4.2 curation session promotes the ~6 byzantine-fairness entries. The codegen is correct; its value is gated on a **separate human-curation activity** (out of scope for this binary session, `00` §4.2). Without it, intent/vocab/policy enrichment stays empty and M2.c's "domain wired" is only structurally true. **Surface to the operator.**

6. **`cks.ops.index` has no in-process ckv reindex API (MID).** `pkg/ckv` exposes no `Reindex` (verified). G8 must shell to `ckv reindex` / `ckg build` for the index op — reintroducing a subprocess for *maintenance* (not the query hot path). Acceptable per `00` C3 (index is agent-triggered, infrequent), but means `BinaryPath` in `CKVConfig` can't be fully deleted in G1 — repurpose it as `IndexBinaryPath`. Alternative: request 02 add `Engine.Reindex` (not in 02's plan; cross-repo). **Decision: shell out.** Flag if a reviewer wants the in-process path.

7. **SSoT schema file does not exist in ANY repo (HIGH, fact).** `00` S4 says the schema lives at `coding-agent/contract/agent-mcp.schema.json` owned by coding-agent — but no such file/dir exists. cks is the first provider needing it for its golden test (M2.a). **This session must author it** (13 tools). Ownership ambiguity: it physically lands in the coding-agent repo (outside cks), so the commit spans two repos OR the schema is authored here and `05` (coding-agent) adopts it. **Decision: author it now in `coding-agent/contract/`; note the cross-repo touch.**

8. **Embedder `Embed` vs `EmbedBatch` signature unknown until 02 lands (MID).** `intent.Embedder` needs `Embed(ctx,text)([]float32,error)` (embedder.go:27). The 02 `pkg/embed/ollama` adapter's public method name/shape isn't pinned in 02-plan (it's `internal` today). If it's batch-only, wrap it. **Verify at Step 2.** Same adapter must also satisfy `ckv.OpenOptions{Embedder}` (a `types.Embedder` from ckv) — confirm the one adapter satisfies both `intent.Embedder` and ckv's `types.Embedder`, or build a thin bridge.

9. **Degraded-health false-positive (MID, designed-around).** The Smart Dummy reports `Reachable:true` (dummy.go:122), so naive fallback would read "ok" not "degraded". Part A G1 step 5 introduces `DegradedDummy` (Health→`Reachable:false`) so the existing `aggregateHealthStatus` (health.go:84) yields `degraded` unchanged. Without this, M2.e fails silently.

10. **`server.go` package doc + `TestRegister_RegistersBothTools` are stale (LOW).** Doc says "two tools" (server.go:4); the test is named `RegistersBothTools` (server_test.go:106) though 11 are registered. Update both when adding the 2 NEW tools (13 total) to avoid a misleading test name.

---

### Fact-based summary
**Fact (None-label, code-verified):** cks `go build ./...` exits 0; go.mod requires ckg, NOT ckv. 11 tools registered (`server.go:74-84`); `concurrency_impact` + `ops.index` absent. `ckvclient/real.go` is the 543-LOC subprocess proxy (`spawnAndInitialize:150`, `DefaultCallTimeout=10s:81`). `main.go:109` still `FakeEmbedder{Dim:32}`. `ckgclient/real.go:196` synthesizes BM25 `Score=1.0-i/(n+1)` via the `[]types.Node` seam. `GetSubgraph` (real.go:358) is wired; `ImpactOfChange/EvidenceForIntent/GetNodePRs` (real.go:332/341/350) are stubs. `ckvclient.Real.Freshness` (real.go:262) is a stub. `vocab.Resolver` is **fully implemented + wired** (G4 already-landed). `store.Reader = persist.StoreReader` alias; cks's `realStoreReader.r` holds it. ckg `pkg/impact.Compute(store,seedQname,seedFile,opt)` + `pkg/evidence.BuildPack(store,opt)` exist; `pkg/concurrency` does NOT. ckv `pkg/embed/ollama` NOT promoted; `pkg/ckv.Engine.Freshness()` NOT present (both 02 blockers). No `coding-agent/contract/agent-mcp.schema.json`. 0 entries `status: verified`. `cks-eval` is zero-LLM (spawns cks-mcp).

**Opinion — High:** real remaining scope is G1 (proxy→in-process, the biggest), G2 (one-line embedder swap + dim guard — easy once 02 lands), G3 (3 methods via seam-widen), G5 (seam-widen to `SearchHit`), G6 (folded into G1), G7+G8 (two net-new tools), the SSoT schema (net-new file), composer tuning, and the ckv/ckg domain-sync codegen. G4 is done. **Mid:** `seedFile` resolution for impact; the embedder method-name unknown until 02; G8's shell-out vs in-process; degraded-health DegradedDummy. **Low:** stale `server.go` doc/test names. **Blocking unknowns:** (1) 02's `pkg/embed/ollama` + `Freshness()` and 01's `pkg/concurrency.Analyze` must ship first — cks cannot build without them; (2) the bge-m3 go-stablenet index (~10h build, 02-operator) and `verified`-entry curation (human session) are external prerequisites for M2.c/d against real data.
