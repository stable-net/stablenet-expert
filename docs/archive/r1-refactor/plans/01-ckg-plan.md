# 01 — ckg Refactor: Detailed Design + Implementation Plan

> **Derives from:** `00-system-contract.md` (C2, C3, §4, §5) + `01-ckg-refactor.md` (G1–G7, §3 excision, M2 acceptance).
> **Repo:** `github.com/0xmhha/code-knowledge-graph` at `/Users/wm-it-22-00661/Work/github/tools/code-knowledge-graph` (`go 1.25.5`).
> **Isolation:** This repo is implementable in a single isolated session. The only external contract is the `pkg/` surface cks imports.
> **Dependency note (what must ship before consumers):** cks (`03`) imports `pkg/store`, `pkg/bm25`, `pkg/impact`, `pkg/evidence`, and the new `pkg/concurrency` (G7) added here. ckv (`02`) imports `pkg/bm25`. Nothing in this repo depends on cks/ckv/chainbench, so it ships first (build order row 1). The C1 NEW tool `cks.context.concurrency_impact` is a **cks** wiring of the `ConcurrencyImpact` function this plan adds; `cks.ops.index` shells out to `ckg build`/`ckg watch` and needs no new ckg code beyond the clean `ckg build --src` run (§4).

> **⚠️ Major finding up front (read before estimating):** the live code is *far* ahead of the `01-ckg-refactor.md` evidence table. G1, G2, G3, G5, G6 are **already landed** on HEAD — their cited file:line evidence (`relations.go:657 _ = info`, `relations.go:631`, "`code_snippet` column always empty", "fake BM25 score in ckg") is **stale** and refers to a `relations.go` that no longer exists and a `code_snippet` column that never existed in the current schema. The real, non-trivial work is **G7 (ConcurrencyImpact, net-new)** and the **LLM excision (§3)**. The other gaps reduce to *verification + a guard test*. Part D enumerates every stale-evidence conflict with the live proof.

---

## Part A — Detailed Design

### G1 — Real `Score`/`Rank` on search hits

**Current state (ALREADY DONE):**
`internal/persist/search_hit.go:80-84` already defines the score-carrying hit:
```go
type SearchHit struct {
	Node     types.Node
	Score    float64 // normalized to [0, 1], result-set local
	RawScore float64 // backend-native, higher = stronger match
}
```
`internal/persist/store_interface.go:94` exposes `SearchFTS(q string, limit int, opts SearchFTSOptions) ([]SearchHit, error)`. SQLite `RawScore = -bm25(nodes_fts)` (sign-flipped, higher=better), then `normalizeSearchHits` (search_hit.go:94-117) min-max normalizes `Score` into `[0,1]`. `pkg/store/store.go:51` re-exports it: `type SearchHit = persist.SearchHit`. The LLM-safe wrapper preserves scores (`pkg/mcphandlers/safety.go:80-96` re-pairs each survivor with its original `SearchHit`).

**The spec's "fake score" lives in cks, not ckg.** `code-knowledge-system/internal/ckgclient/real.go:153-204` synthesizes `Score: 1.0 - float64(i)/float64(n+1)` because cks's *internal seam* `storeReader.SearchFTS(q, limit) ([]types.Node, error)` (real.go:50, real.go:78) calls a **`[]types.Node`-returning** path — it never calls the real `SearchFTS(...)([]SearchHit,...)`. ckg already provides the real score; **cks must switch its seam to consume `[]store.SearchHit`** — that is a `03-cks-refactor` task, not a ckg task.

**Target design (ckg side):** No code change. Add a **guard test** in `pkg/store` (external package `store_test`) asserting `SearchFTS` returns populated `Score`/`RawScore` with `Score ∈ [0,1]` and descending order, so the contract cks depends on cannot silently regress.

**Notes/edge cases:** degenerate single-row / all-equal results set every `Score = 1.0` (search_hit.go:108-113), not `0.0`/`NaN` — cks rerankers must treat `1.0` as "uniform strength," not "perfect." Document this in the guard test.

---

### G2 — `pkg/bm25` stable for external import

**Current state (ALREADY DONE):** `pkg/bm25` is a fully public package. `pkg/bm25/example_external_test.go` is an `package bm25_test` guard that imports `github.com/0xmhha/code-knowledge-graph/pkg/bm25` and exercises the exact surface ckv/cks use:
- `bm25/scorer.go:19` `type Document struct`, `:27` `type ScoredDoc struct`, `:35` `type Scorer interface`
- `bm25/okapi.go:37` `func NewOkapi() *Okapi`, `:43` `Index`, `:93` `Score`, `:120` `TopK`
- `bm25/tokenize.go:21` `func Tokenize(s string) []string`

**Target design:** No code change. The existing `example_external_test.go` already *is* the "if this stops compiling the external contract broke" guard (its own doc comment says so). Verify it runs green; that satisfies G2.

**Notes:** ckv will import `bm25.Tokenize` + `bm25.NewOkapi`; both are exported and covered. No CGO. Nothing to do beyond a CI assertion.

---

### G3 — `code_snippet` population

**Current state (ALREADY DONE / premise stale):** there is **no `code_snippet` column** anywhere in `internal/persist/schema.sql` or any Go file (grep-confirmed empty). Source bodies live in a separate `blobs` table:
```sql
-- internal/persist/schema.sql:88
CREATE TABLE IF NOT EXISTS blobs ( node_id ..., source BLOB NOT NULL );
```
Cold build populates it: `internal/buildpipe/pipeline.go:532` `store.InsertBlobs(blobs)` where `blobs := extractBlobs(srcRoot, g.Nodes)` (pipeline.go:531) materializes per-node source slices; hunk patches merge into the same map (pipeline.go:530). Fetched via `Reader.GetBlob(id)` (`internal/persist/sqlite_reader.go:296`), surfaced to LLMs through `attachBlobs` in handlers (`pkg/mcphandlers/handlers.go:113`) and `impact.Compute(..., IncludeBlobs:true)` (`pkg/impact/impact.go:344-347`).

**Target design:** No schema change. Add a **build-integration assertion** to the §4 go-stablenet smoke: after `ckg build`, `SELECT count(*) FROM blobs` > 0 and a spot `GetBlob` on a known Function node returns non-empty source. This closes G3 as "verified populated."

**Notes:** the spec's "HANDOFF F-8 always empty" refers to a pre-blob-table era. Do **not** add a `code_snippet` column — it would duplicate `blobs` and break the single-source-of-truth for source text.

---

### G5 — `calls` resolution uses `types.Info`

**Current state (ALREADY DONE / `relations.go` gone):** call/dispatch resolution lives in `internal/parse/golang/statements.go`, not `relations.go`. It already runs the typed path:
- `statements.go:206` `classifyCallDispatch` uses `v.typesInfo` to classify `interface_method` / `func_value` / `method_value` / `closure`, falling back to AST-only `closure` detection when `typesInfo == nil` (statements.go:295-318).
- `parsePendingFromCall` (statements.go:219) stamps `DispatchKind` and lifts interface dispatch to `EdgeInvokes`; static calls stay `EdgeCalls`.
- `resolve.go:104` loads packages with `packages.NeedTypesInfo | packages.NeedTypes | packages.NeedDeps`, so production builds run the EXTRACTED typed path.
- Interface→impl edges exist as first-class `EdgeImplements` (`internal/parse/golang/implements.go`), and `uses_type.go` / `instantiates.go` both consume `pkg.TypesInfo` (uses_type.go:146, instantiates.go:65). The dead `_ = info` is gone.

**Target design:** No code change. Add a **parser unit test** (or assert an existing one) that a fixture with `var i Iface = &Impl{}; i.M()` produces an `invokes` edge tagged `dispatch_kind="interface_method"` with `Confidence=EXTRACTED` and an `implements` edge `*Impl → Iface`. `internal/parse/golang/implements_test.go` + `statements_test.go` + `resolve_test.go` already exist — confirm coverage, add only if a gap.

**Notes:** confirm against HEAD before touching (spec §6 warns of W-B/W-C doc-date conflicts). HEAD git log on `statements.go` is `2026-05-29 feat(go-parser): emit calls edge for go x.method() (P2 #8 W-A)` — the typed path is *newer* than the spec's evidence date. **Treat G5 as landed.**

---

### G6 — `channels` emits producer→consumer pairs, not self-loops

**Current state (ALREADY DONE / premise stale):** channel edges are emitted in `internal/parse/golang/concurrency.go:511-585` `emitGoroutineChannelEdges`. They are **`Goroutine → Channel`** edges, NOT self-loops:
- `concurrency.go:553-558`: `*ast.SendStmt` → `types.Edge{Src: goroutineID, Dst: chanID, Type: types.EdgeSendsTo}`
- `concurrency.go:563-569`: `*ast.UnaryExpr` with `token.ARROW` (`<-ch`) → `types.Edge{Src: goroutineID, Dst: chanID, Type: types.EdgeRecvsFrom}`

Producer (`sends_to`) and consumer (`recvs_from`) are distinguished by edge type and both point goroutine→channel; a downstream traversal joining on the shared `Channel` node recovers the producer↔consumer pairing. `emitChannelFromMake` (concurrency.go:471) mints the `Channel` node from `make(chan T, n)`. No `Src==Dst` self-loop on channels.

**Target design:** No code change. Add a **parser unit test** (extend `concurrency_test.go`): a fixture with one goroutine sending and one receiving on the same channel yields one `sends_to` and one `recvs_from` edge to the **same** `chanID`, with `Src != Dst`. This both verifies G6 and is the upstream correctness guarantee that `ConcurrencyImpact` (G7) relies on.

**Notes:** confidence is `ConfInferred` for these edges (concurrency.go:557, 567) — AST-positional, not type-resolved. `ConcurrencyImpact` must surface INFERRED concurrency edges (do not filter to EXTRACTED only, or channel impact disappears). Named-function goroutines (`go worker(ch)`) are skipped (concurrency.go:530) — a known recall gap, **out of scope** (cross-file resolution, spec §6 / D1).

---

### G7 — `ConcurrencyImpact(symbol, depth)` — **NET-NEW, the real work**

**Current state:** No public traversal exposes concurrency edges. The five edge constants exist (`pkg/types/enums.go:245-247, :266, :268`):
```go
EdgeSpawns      = "spawns"
EdgeSendsTo     = "sends_to"
EdgeRecvsFrom   = "recvs_from"
EdgeAcquiresLock      = "acquires_lock"
EdgeAccessedUnderLock = "accessed_under_lock"
```
(`EdgeReleasesLock="releases_lock"` also exists but is **not** one of the contract's 5 — exclude it; release is the unlock half of a lock pair and adds noise to "what is affected.")

The closest existing code is `pkg/impact/impact.go` — but it (a) only covers `edgesConcurrent = {"spawns","sends_to","recvs_from"}` (impact.go:45) and **deliberately excludes** the lock edges (impact.go:35-38 comment: "runtime locking state … out of category"), and (b) takes `persist.StoreReader` (impact.go:102) — an **internal** type cks cannot name. So `impact.Compute` is unusable for the contract. G7 needs a dedicated `pkg/` entry point over all 5 edges.

The traversal primitive exists and is the right substrate: `internal/persist/sqlite_reader.go:353` / `pkg/store` `Reader.NeighborhoodByQname(qname string, depth int, reverse bool, edgeTypes ...string) ([]Node, []Edge, error)` — accepts an edge-type filter and a direction, BFS to `depth`, returns the union node set + every traversed edge.

**Target design — new package `pkg/concurrency`:**

```go
// pkg/concurrency/concurrency.go
package concurrency

import (
	"sort"
	"github.com/0xmhha/code-knowledge-graph/pkg/store"
	"github.com/0xmhha/code-knowledge-graph/pkg/types"
)

// ConcurrencyEdgeTypes is the contract's 5 concurrency edge types (00 C1 S1).
// releases_lock is intentionally excluded — the unlock half adds no
// affected-by signal over acquires_lock.
var ConcurrencyEdgeTypes = []string{
	string(types.EdgeSpawns),
	string(types.EdgeSendsTo),
	string(types.EdgeRecvsFrom),
	string(types.EdgeAcquiresLock),
	string(types.EdgeAccessedUnderLock),
}

const DepthCap = 5 // mirrors pkg/impact.DepthCap

// Options bundles tunable knobs. Zero value resolves to documented defaults.
type Options struct {
	Depth    int // default 2; clamped to [1, DepthCap]
	MaxTotal int // default 0 = unbounded; caps returned Modules (00 C1 max_total)
}

// Module is one symbol reachable from the seed via a concurrency edge.
type Module struct {
	ID        string    `json:"id"`
	Type      types.NodeType `json:"type"`
	Name      string    `json:"name"`
	Qname     string    `json:"qname"`
	FilePath  string    `json:"file_path"`
	StartLine int       `json:"start_line"`
	Citation  string    `json:"citation,omitempty"` // "file:line" when both present
	// Direction the module was reached from the seed.
	//   "affects"     — reverse edge: module → ... → seed (changing module
	//                   impacts the seed's concurrency behaviour)
	//   "affected_by" — forward edge: seed → ... → module
	//   "both"        — reached in both traversals
	Direction string    `json:"direction"`
}

// Result is what cks's concurrency_impact tool consumes.
type Result struct {
	Seed      string         `json:"seed"`       // echoed qname
	NotFound  bool           `json:"not_found"`  // seed did not resolve
	Depth     int            `json:"depth"`      // post-clamp
	Modules   []Module       `json:"modules"`    // dedup'd, sorted by qname (tiebreak id)
	Edges     [][]any        `json:"edges"`      // [src,dst,type,line] triples, sorted
	Totals    map[string]any `json:"totals"`     // {modules, edges}
}

// Analyze returns the concurrency blast radius of symbol: every module that
// affects or is affected by it via spawns/sends_to/recvs_from/acquires_lock/
// accessed_under_lock edges, BFS to depth in BOTH directions.
//
// Backed by store.Reader.NeighborhoodByQname filtered to ConcurrencyEdgeTypes.
// Deterministic: modules sorted by qname (tiebreak id), edges by
// (type,src,dst,line) — so cks's prompt-cache stays stable.
func Analyze(r store.Reader, symbol string, opt Options) (Result, error)
```

**Implementation body of `Analyze`:**
1. Clamp depth: `d := opt.Depth; if d<1 {d=1}; if d>DepthCap {d=DepthCap}`.
2. `fwdN, fwdE, err := r.NeighborhoodByQname(symbol, d, false, ConcurrencyEdgeTypes...)` (forward = affected_by).
3. `revN, revE, err := r.NeighborhoodByQname(symbol, d, true, ConcurrencyEdgeTypes...)` (reverse = affects).
4. If both traversals returned only the seed root (or nothing resolved), set `NotFound` appropriately (FindSymbol miss → `NotFound:true`).
5. Dedup nodes by ID across both sets, drop the seed root itself, stamp `Direction` (`affects`/`affected_by`/`both`), build `Citation` via `file:line` when present.
6. Dedup edges by `(type,src,dst,line)`, sort, project to `[src,dst,type,line]` triples.
7. Apply `MaxTotal` cap on `Modules` *after* sorting (deterministic truncation).

**Which store method it builds on:** `store.Reader.NeighborhoodByQname` (the only public, edge-type-filterable, directional traversal). **Do NOT** route through `pkg/impact.Compute` — it excludes lock edges and takes the internal `persist.StoreReader`.

**Return type cks consumes:** `concurrency.Result` (JSON-marshalable; `Modules []Module` is the `cks.context.concurrency_impact` payload — "modules that affect/are-affected via concurrency"). cks's `ckgclient.Client` gets a method `ConcurrencyImpact(ctx, symbol, depth, maxTotal) (concurrency.Result, error)` thin-wrapping `concurrency.Analyze`.

**Optional MCP exposure (dev-only):** add `RegisterConcurrencyImpact(s, safe)` in `pkg/mcphandlers` and append to `RegisterAll` (`registerall.go:24`) so the dev-only ckg MCP server (build-tagged, `00` §7) can be probed directly. The envelope mirrors `RegisterImpactOfChange` (impact.go:23). This is convenience, not contract — cks calls `concurrency.Analyze` in-process.

**Notes/edge cases:**
- Lock edges (`acquires_lock`, `accessed_under_lock`) are anchored on the *enclosing function* (concurrency.go:341, the `maybeEmitLockEdge` path), so a reverse traversal from a `Mutex`/`Field` node finds every function in the critical section — exactly the byzantine-fairness "what else touches this under the same lock" query (`00` §4.3 L2).
- Channel edges go goroutine→channel, so a seed *function* needs depth ≥ 2 to reach across the channel to the peer goroutine (seed func → spawns → goroutine → sends_to → channel ← recvs_from ← goroutine ← spawns ← peer func). Default `Depth:2` is the floor; document that concurrency reach is one hop deeper than call reach. Consider defaulting `Depth:3` for this tool specifically — **decision: keep default 2, let cks pass depth=3**, matching `00` C1 which lists `depth` as a knob.
- `Confidence` of channel/lock edges is often `INFERRED` — surface them; filtering to EXTRACTED would empty the result on real Go code.

---

### LLM excision (§3) — remove `anthropic-sdk-go` + `cli-wrapper`

**Current state:** `go.mod:8-9` requires `github.com/0xmhha/cli-wrapper v0.4.6` and `github.com/anthropics/anthropic-sdk-go v1.38.0`. The LLM surface is confined to:
- `cmd/ckg/eval.go` — `newEvalCmd` (the `ckg eval` four-baseline command), `selectLLMBackend` (eval.go:76), `--llm-backend`/`--llm-claude-binary` flags. **Only this file** imports `internal/eval` from outside the package (grep-confirmed).
- `internal/eval/llm.go` — `APIClient` (anthropic-sdk-go + `ANTHROPIC_API_KEY`).
- `internal/eval/llm_cli.go` — `CLIClient` (spawns `claude -p` via `cliwrap.Manager`).
- `internal/eval/gamma_loop.go` — multi-turn LLM loop.
- `internal/eval/runner.go` — `Run(ctx, tasks, baselines, graphDir, llm LLMClient, ...)` (runner.go:80) α/β/γ/δ baseline execution; `runOne(ctx, llm LLMClient, ...)` (runner.go:133).
- `internal/eval/doc.go` — references the LLM clients in prose only.

Grep proof of LLM-type users (non-test): `internal/eval/{llm.go, llm_cli.go, gamma_loop.go, runner.go, doc.go}` are the **only** files referencing `LLMClient`/`APIClient`/`CLIClient`/`gammaLoop`.

The deterministic-LLM-*output* scorers (`score.go`, `citation.go`, `hallucination_check.go`, `report.go`, `task.go`, `baseline.go`, `baseline_context.go`, `filter.go`) score an LLM `output string` — per `00` §5 they belong in the agent eval layer, but **none of them import anthropic/cli-wrapper**; they only become dead once `runner.go` (their sole caller) is gone.

**KEEP (deterministic, no network):**
- `internal/eval/retrieval/` (`fixture.go`, `runner.go`, `scorer.go`) — store-probe P/R/F1. **Self-contained**: grep-confirmed it does NOT import parent `internal/eval`. Already exposed as `ckg eval-retrieval` via `cmd/ckg/eval_retrieval.go` (registered in `root.go:34` `newEvalRetrievalCmd()`).
- `internal/validate/llm.go` — `LLMValidator` is a **DryRun stub** (validate/llm.go:30, "V0 … dry-run only … no external dependency or network access"). No anthropic/cli-wrapper import. **Leave as-is** (enforces the no-call invariant).
- all `exec.Command("git", …)` in `internal/temporal/`, `internal/buildpipe/`, `internal/server/` — deterministic.

**Target design (deletions, ordered so the repo always compiles):**
1. `cmd/ckg/root.go:34` — remove `newEvalCmd()` from the `AddCommand(...)` list (keep `newEvalRetrievalCmd()`).
2. Delete `cmd/ckg/eval.go` (the `eval` command + `selectLLMBackend` + `maxInt` helper — check `maxInt` isn't used elsewhere; if it is, relocate).
3. Delete `internal/eval/llm.go`, `internal/eval/llm_cli.go`, `internal/eval/gamma_loop.go`, `internal/eval/runner.go` + their `_test.go` siblings (`llm_test.go`, `llm_cli_test.go`, `gamma_loop_test.go`, `runner_test.go`, `runner_cycle6_test.go`, `runner_cycle7_test.go`, `runner_internal_test.go`).
4. Decide the fate of the now-orphaned output-scorers (`score.go`, `citation.go`, `hallucination_check.go`, `report.go`, `task.go`, `baseline.go`, `baseline_context.go`, `filter.go`, `export.go` if present, + their tests). **Recommended:** delete them from ckg (they move to the agent/session eval layer per `00` §5; `internal/eval/doc.go` already anticipates a `code-knowledge-graph-eval` sister). This empties `internal/eval/` down to only the `retrieval/` subpackage. Update/trim `internal/eval/doc.go` to describe only the kept retrieval self-test, or delete it if the package body is gone.
5. `go mod tidy` → drops `anthropic-sdk-go`, `cli-wrapper`, and the transitive deps they pulled: `creack/pty` (go.mod:25), `vmihailenco/msgpack/v5` (:46), `vmihailenco/tagparser/v2` (:47), `tidwall/{gjson,match,pretty,sjson}` (:39-42), `mailru/easyjson` (:33), `buger/jsonparser` (:23) — confirm each is no longer referenced after the cut.

**Notes/edge cases:**
- `cmd/ckg/eval_test.go`, `cli_test.go`, `cli_extra_test.go` may assert the `eval` command exists — update them to drop `eval` assertions while keeping `eval-retrieval`.
- `internal/eval/retrieval/` must keep compiling after the parent package is gutted — it doesn't import the parent (verified), so this is safe, but run `go build ./internal/eval/...` after step 4.
- Some kept transitive deps (`tidwall/*`, `easyjson`) may also be pulled by `mcp-go` or `pgx` — `go mod tidy` resolves the truth; do not hand-edit `go.mod` require blocks.

---

### §4 — Indexing & policy load (config, not code change)

**Current state (ALREADY WIRED):** `cmd/ckg/build.go:63-64,95-98` already accepts `--policy-file` (→ `PolicyFile`) and `--security-pattern-file` (→ `SecurityPatternFile`). Loaders exist: `pkg/policy/policy.go:85` `LoadFromFile`, `:141` `Resolve`; `pkg/security/security.go:107` `LoadFromFile`, `:164` `Resolve`. Node/edge types exist: `NodePolicy`/`NodeSecurityPattern` (enums.go:108,120), `EdgeGovernedBy`/`EdgeHasSecurityPattern` (enums.go:427,435).

**Target design:** No code change. A **runnable build invocation** + a count assertion:
```
ckg build --src <go-stablenet> --out <graph.db> \
  --policy-file <go-stablenet>/policy.yaml \
  --security-pattern-file <go-stablenet>/security.yaml
```
then assert `count(Policy) > 0` and `count(SecurityPattern) > 0` (M2.d). The `policy.yaml`/`security.yaml` are derived from cks entries (`00` §4.1) — their *production* by the cks codegen script is a `03-cks-refactor` task; ckg only needs to *consume* them, which it already does.

**Notes:** the live `.ckg-data/` self-indexes ckg itself (`00` C3) — the go-stablenet build must point `--src` at the real go-stablenet tree. This is an operator/CI step, not a code change.

---

## Part B — Implementation Plan (ordered, test-gated)

> Ordering keeps the repo compiling at every commit. Verification-only steps come first (they're zero-risk and prove the "already landed" claims), then the net-new G7, then the destructive LLM excision last (largest blast radius).

**Step 1 — Baseline green.**
- Files: none. · Do: `go build ./... && go test ./pkg/... ./internal/persist/... ./internal/parse/...` to capture the pre-change green baseline. · Test: build exit 0 (already confirmed). · Commit: none (baseline only).

**Step 2 — G1 guard test (Score/Rank contract).**
- Files: `pkg/store/score_contract_test.go` (new, `package store_test`). · Do: build a tiny in-memory/temp graph, call `Reader.SearchFTS("Deposit", 5, store.SearchFTSOptions{})`, assert every hit has `Score ∈ [0,1]`, descending, and `RawScore` populated; assert the single-row case sets `Score==1.0`. · Test: `go test ./pkg/store/ -run TestSearchFTSScoreContract`. · Commit: "test(store): pin SearchFTS Score/RawScore contract (G1)".

**Step 3 — G2 bm25 external-import assertion.**
- Files: none (or extend `pkg/bm25/example_external_test.go`). · Do: confirm `go test ./pkg/bm25/ -run TestExternalConsumer_IndexAndQuery` is green; add a one-line assertion that `bm25.Tokenize` + `bm25.NewOkapi().TopK` are reachable from `package bm25_test`. · Test: `go test ./pkg/bm25/`. · Commit: "test(bm25): assert external-consumer surface (G2)" (skip if no edit).

**Step 4 — G5 typed-calls + interface→impl test.**
- Files: `internal/parse/golang/resolve_test.go` (extend) or new `g5_typed_calls_test.go`. · Do: fixture `var i Iface = &Impl{}; i.M()` → assert an `invokes` edge `dispatch_kind="interface_method"` `Confidence=EXTRACTED` + an `implements` edge `*Impl→Iface`. Reuse existing `implements_test.go`/`statements_test.go` harness. · Test: `go test ./internal/parse/golang/ -run 'TestTypedCalls|TestImplements'`. · Commit: "test(go-parser): pin types.Info calls resolution (G5)".

**Step 5 — G6 producer/consumer channel-pair test.**
- Files: `internal/parse/golang/concurrency_test.go` (extend). · Do: fixture with one goroutine `ch <- x` and one `<-ch` on the same channel → assert exactly one `sends_to` and one `recvs_from` edge, both `Dst == chanID`, both `Src != Dst`. · Test: `go test ./internal/parse/golang/ -run TestChannelProducerConsumerPair`. · Commit: "test(go-parser): pin sends_to/recvs_from pairing (G6)".

**Step 6 — G7 new package `pkg/concurrency` (the real feature).**
- Files: `pkg/concurrency/concurrency.go` (new), `pkg/concurrency/doc.go` (new), `pkg/concurrency/concurrency_test.go` (new). · Do: implement `Analyze(r store.Reader, symbol string, opt Options) (Result, error)` per Part A G7 (forward+reverse `NeighborhoodByQname` filtered to `ConcurrencyEdgeTypes`, dedup, direction-stamp, deterministic sort, `MaxTotal` cap, `NotFound` handling). · Test: `go test ./pkg/concurrency/` — fixture graph with a `spawns`+`sends_to`+`recvs_from`+`acquires_lock`+`accessed_under_lock` chain; assert `Analyze("Worker", {Depth:3})` returns the peer goroutine's function and the lock-sharing function with correct `Direction`, and that `releases_lock` edges are NOT surfaced. · Commit: "feat(concurrency): add pkg/concurrency.Analyze for G7/S1".

**Step 7 — G7 dev-only MCP handler (optional but recommended).**
- Files: `pkg/mcphandlers/concurrency.go` (new) `RegisterConcurrencyImpact(s, reader)`; `pkg/mcphandlers/registerall.go` (append call in `RegisterAll`). · Do: envelope mirrors `RegisterImpactOfChange` (impact.go:23) — params `seed_qname` (required), `depth` (default 2), `max_total` (default 0); call `concurrency.Analyze`; `textResult(...)`. · Test: `go test ./pkg/mcphandlers/ -run TestConcurrencyImpact` (smoke: tool registers, returns the fixture's modules). · Commit: "feat(mcphandlers): expose concurrency_impact tool (dev-only)".

**Step 8 — LLM excision part 1: unregister + delete the command.**
- Files: `cmd/ckg/root.go` (drop `newEvalCmd()`), delete `cmd/ckg/eval.go`, fix `cmd/ckg/eval_test.go`/`cli_test.go`/`cli_extra_test.go` to stop asserting `eval`. · Do: relocate `maxInt` if still used. · Test: `go build ./cmd/... && go test ./cmd/ckg/ -run 'TestRoot|TestEvalRetrieval'`. · Commit: "refactor(cmd): drop `ckg eval` LLM command (00 §5)".

**Step 9 — LLM excision part 2: delete LLM clients + runner.**
- Files: delete `internal/eval/{llm.go,llm_cli.go,gamma_loop.go,runner.go}` + their `*_test.go`. · Do: nothing else references `LLMClient`/`APIClient`/`CLIClient` (grep-verified). · Test: `go build ./internal/eval/...` (will fail to compile the orphaned scorers if they referenced runner types — that's Step 10's signal). · Commit: "refactor(eval): remove LLM baseline execution (00 §5)".

**Step 10 — LLM excision part 3: remove orphaned output-scorers, keep retrieval.**
- Files: delete `internal/eval/{score.go,citation.go,hallucination_check.go,report.go,task.go,baseline.go,baseline_context.go,filter.go}` + tests; trim or delete `internal/eval/doc.go`. Keep `internal/eval/retrieval/` untouched. · Do: confirm `internal/eval/retrieval/` still builds (it doesn't import the parent). · Test: `go build ./... && go test ./internal/eval/retrieval/`. · Commit: "refactor(eval): move LLM-output scorers to agent layer; keep retrieval self-test".

**Step 11 — go.mod tidy (drop anthropic + cli-wrapper).**
- Files: `go.mod`, `go.sum`. · Do: `go mod tidy`. Verify `anthropic-sdk-go`, `cli-wrapper`, `creack/pty`, `vmihailenco/*` are gone from `go.mod` (others may stay if pulled by mcp-go/pgx). · Test: `go build ./... && go test ./... && grep -c 'anthropic-sdk-go\|cli-wrapper' go.mod` (expect 0). · Commit: "chore(deps): drop anthropic-sdk-go + cli-wrapper after eval excision".

**Step 12 — go-stablenet index + policy load smoke (§4, G3 verify).**
- Files: `cmd/ckg/build_test.go` (extend) or a `make` target / CI script. · Do: run `ckg build --src <go-stablenet> --out /tmp/gsn.db --policy-file ... --security-pattern-file ...`; assert `count(blobs)>0` (G3), `count(Policy)>0` + `count(SecurityPattern)>0` (M2.d); call `concurrency.Analyze` on a known go-stablenet concurrency symbol and assert non-empty `Modules` (M2.a). · Test: `go test ./cmd/ckg/ -run TestBuildGoStablenetSmoke` (gated/skipped when go-stablenet tree absent). · Commit: "test(build): go-stablenet policy + concurrency smoke (M2)".

---

## Part C — Verification & Acceptance

**Full-repo gate (run after every destructive step, mandatory before "done"):**
```
go build ./...
go test ./...
golangci-lint run ./...        # if configured (.golangci.yml present? check repo)
go test ./internal/eval/retrieval/ -run .   # the KEEP self-test (00 §5)
go vet ./...
grep -c 'anthropic-sdk-go\|cli-wrapper' go.mod   # expect 0
```

**M2 acceptance (`01-ckg-refactor.md` §5) → command map:**

| M2 clause | Proof command |
|---|---|
| (a) all frozen `pkg/` methods incl. `ConcurrencyImpact` compile **and** return non-empty on a go-stablenet symbol with known concurrency | `go build ./pkg/...` + Step-12 `TestBuildGoStablenetSmoke` asserting `concurrency.Analyze(...).Modules` non-empty |
| (b) `internal/eval/retrieval` deterministic self-test passes in CI | `go test ./internal/eval/retrieval/` (and `ckg eval-retrieval --graph <db> --fixtures eval/retrieval/*.yaml`) |
| (c) `go.mod` no longer requires `anthropic-sdk-go` or `cli-wrapper` | `grep -c 'anthropic-sdk-go\|cli-wrapper' go.mod` == 0 |
| (d) `ckg build` populates `Policy`/`SecurityPattern` nodes (count > 0) | Step-12 count assertions |

**Frozen `pkg/` surface (C2 §1) — confirm each is reachable from an external `package x_test`:** `store.{Reader, OpenReadOnly, GetManifest, SearchHit, PRRef}`; `Reader.{SearchFTS→BM25, FindSymbol, NeighborhoodByQname, SubgraphByQname (==GetSubgraph), GetNodePRs, Close}`; `pkg/impact.Compute` (==ImpactOfChange, **but takes internal `persist.StoreReader`** — see Part D risk); `pkg/evidence.BuildPack` (==EvidenceForIntent); **`pkg/concurrency.Analyze` (==ConcurrencyImpact, NEW)**; `pkg/bm25.*`. Add a single `pkg/store/external_surface_test.go` (`package store_test`) that names each, so the C2 freeze can't silently drift.

---

## Part D — Risks / Unknowns (live-code findings the spec didn't anticipate)

1. **The spec's evidence table is mostly stale (HIGH confidence, grep+read proven).** G1, G2, G3, G5, G6 are already implemented on HEAD. Concretely:
   - `relations.go` (cited at `:657`, `:631` for G5/G6) **does not exist** — Go call/channel logic moved to `internal/parse/golang/{statements.go, concurrency.go}`, both newer than the spec date (HEAD commit `2026-05-29 W-A`). The `_ = info` dead code is gone; `types.Info` is used (statements.go:206,295; resolve.go:104 `NeedTypesInfo`).
   - `code_snippet` column (G3) **never exists** in `schema.sql`; source is in the `blobs` table, populated at build (`pipeline.go:531-532`). Do **not** add a `code_snippet` column.
   - The "fake BM25 score" (G1) is in **cks** (`ckgclient/real.go:196`), not ckg. ckg already returns real `SearchHit.Score`/`RawScore`. The fix is a cks seam change (doc `03`), not ckg.
   → **Implication:** ckg's effective scope collapses to **G7 (net-new) + LLM excision**; G1/G2/G3/G5/G6 become guard tests. Re-scope the session estimate accordingly.

2. **`pkg/impact` partially covers concurrency but is unusable for the contract (HIGH).** `impact.Compute` has a `concurrent` bucket (`spawns/sends_to/recvs_from`, impact.go:45) but **excludes the 2 lock edges by design** (impact.go:35-38) and takes the **internal** `persist.StoreReader` (impact.go:102) cks cannot name. The contract's `ImpactOfChange` (`00` C2) is satisfied by `impact.Compute`'s call-graph buckets, but **`ConcurrencyImpact` cannot reuse it** — G7 needs the new `pkg/concurrency.Analyze` over `store.Reader` covering all 5 edges. (Opinion, High: this is the single most important design correction vs. a naive "just expose impact.Compute" reading of the spec.)

3. **`SubgraphByQname` and `GetNodePRs` already exist and are partly wired (NONE/fact).** `Reader.SubgraphByQname` (sqlite_reader.go:408, both-directions BFS) — cks already calls it (`ckgclient/real.go:90,366`). `Reader.GetNodePRs(nodeID, cutoff)` (store_interface.go:153) exists, but cks's `Real.GetNodePRs` (real.go:348) still returns empty — again a **cks** wiring gap (doc `03`), not ckg. The contract's `GetSubgraph`/`GetNodePRs` freeze is already met on the ckg side.

4. **`impact.Compute` takes an internal type — possible C2 freeze gap (MID).** The `00` C2 freeze lists `ImpactOfChange` as a method cks's `ckgclient.Client` needs. `pkg/impact.Compute(store persist.StoreReader, ...)` signatures on `persist.StoreReader` (internal). Since `store.Reader = persist.StoreReader` (alias, store.go:46), an external caller *can* pass a `store.Reader` — it satisfies the same interface. **Verify** cks can call `impact.Compute(myStoreReader, ...)` from outside the module (the alias should make it work, but the parameter type prints as `persist.StoreReader` in godoc, which is confusing). If it fails to compile externally, add a thin `pkg/impact` wrapper taking `store.Reader` explicitly. (Low risk — the alias identity should hold; flagged for a compile check in Step 6/Part C external_surface_test.)

5. **Doc-date conflict W-B/W-C (spec §6) — RESOLVED for G5/G6 (HIGH).** Spec §6 warns to "verify against HEAD before touching G5/G6." Verified: G5 (typed calls) and G6 (channel pairs) are landed and newer than the spec evidence. **No re-implementation needed** — only the guard tests in Steps 4–5. `NodeAwaitPoint`/`EdgeAwaits`/`EdgeOverrides` are slot-reserved (detectors "land in Phase 5", enums.go:87-96, 386-418) — **out of scope**, do not touch.

6. **`releases_lock` is a 6th lock edge not in the contract's 5 (MID).** `EdgeReleasesLock="releases_lock"` exists (enums.go:267). The contract's S1 lists exactly 5 (`spawns/sends_to/recvs_from/acquires_lock/accessed_under_lock`). Design decision: **exclude `releases_lock`** from `ConcurrencyImpact` (the unlock half adds no affected-by signal). Documented in `ConcurrencyEdgeTypes`. If a reviewer wants symmetry, it's a one-line add — but default to the contract's 5.

7. **Channel reach is one hop deeper than call reach (MID).** Because channel edges are goroutine→channel (not function→function), a function seed needs `depth≥2` (often 3) to reach the peer goroutine across the channel. Default `Depth:2` may under-return on real go-stablenet. **Mitigation:** document it; cks passes `depth:3` for `concurrency_impact` (the `00` C1 `depth` knob exists for exactly this). Named-function goroutines (`go worker(ch)`) are skipped by the parser (concurrency.go:530) — a known recall gap, **out of scope** (D1 cross-file resolution).

8. **Orphaned-scorer disposition is a judgment call (MID).** `score.go/citation.go/hallucination_check.go/report.go/task.go/baseline*.go/filter.go` don't import anthropic/cli-wrapper but are dead once `runner.go` goes. `00` §5 says they "move to the agent/session eval layer." **Recommendation: delete from ckg** (the agent repo re-implements what it needs; `internal/eval/doc.go` already names a `code-knowledge-graph-eval` sister). If the session wants to be conservative, it may *keep* them compiling as pure functions (they're LLM-free), but they'd be unreachable dead code — prefer deletion. Flag for human confirm at Step 10.

9. **`go mod tidy` transitive-drop set is inferred, not guaranteed (LOW).** `creack/pty`, `vmihailenco/*` are almost certainly cli-wrapper/anthropic-only; `tidwall/*`, `easyjson`, `jsonparser` *might* be pulled by `mcp-go` or `pgx` and survive tidy. Trust `go mod tidy` output, don't hand-prune `go.mod`. Run `go test ./...` after tidy to catch any accidental removal.

---

### Fact-based summary
**Fact (None-label, code-verified):** G1/G2/G3/G5/G6 are implemented on HEAD; `relations.go` and `code_snippet` do not exist; the 5 concurrency edge constants exist in `pkg/types/enums.go`; `NeighborhoodByQname` accepts an edge-type filter + direction; `pkg/impact.Compute` excludes lock edges and takes `persist.StoreReader`; only `cmd/ckg/eval.go` + `internal/eval/{llm,llm_cli,gamma_loop,runner}.go` reference the LLM clients; `internal/eval/retrieval/` does not import its parent; `--policy-file`/`--security-pattern-file` build flags + loaders already exist; the repo currently `go build ./...` exits 0.

**Opinion — High:** the only substantive work is `pkg/concurrency.Analyze` (G7) + the LLM excision; everything else is guard tests. **Mid:** `impact.Compute`'s internal-type parameter may need an external compile check; channel-depth default may need `depth:3` from cks. **Low:** exact transitive-dep drop set from `go mod tidy`.
