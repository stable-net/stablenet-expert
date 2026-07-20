# 02 — ckv Refactor: Detailed Design + Implementation Plan

> **Derives from:** `00-system-contract.md` (C2, C3, §4, §5) + `02-ckv-refactor.md` (G1, embedder fitness, domain/invariant indexing, LLM excision, M2 acceptance).
> **Repo:** `github.com/0xmhha/code-knowledge-vector` at `/Users/wm-it-22-00661/Work/github/tools/code-knowledge-vector` (`go 1.25.5`, HEAD `38561a0`).
> **Isolation:** Implementable in a single isolated session. The only external contract is the `pkg/` surface cks imports. **Note: ckv has CGO (sqlite-vec amalgamation in `internal/store/sqlitevec`) — but that is in the *store*, not the *embedder*. The embedder promoted by G1 (`pkg/embed/ollama`) is pure HTTP, zero CGO, which is what C2's "no-CGO embedder construction" means.**
> **Dependency note (what 03-cks depends on from here):** cks (`03`) imports (a) `pkg/ckv` — `Open`, `OpenOptions{Embedder}`, `Engine.SemanticSearch`, `Manifest`, `CheckFreshness`, the **NEW `Freshness()`** structured method, `Warmup`, `Close` (all in-process), and (b) the **NEW `pkg/embed/ollama`** (G1) so it can construct a real embedder with no CGO and no `ckv` subprocess. **Step 1 (the ollama promotion) gates everything in 03.** Nothing in ckv depends on cks/ckg/chainbench, so it ships in build-order row 2 (after ckg).

> **⚠️ Major finding up front (read before estimating):** the live ckv code is ahead of the `02-ckv-refactor.md` evidence in one decisive way: **ckv has NO `anthropic-sdk-go` and NO `cli-wrapper` dependency** — neither in `go.mod` nor `go.sum` (grep-confirmed: `grep -c 'anthropic\|cli-wrapper' go.mod go.sum` → 0). The LLM coupling is *exclusively* `exec.Command("claude", ...)` subprocess spawning in `internal/judge`, `internal/eval/prregress/{agent,score}.go`, and their `cmd/ckv/eval.go` wiring. So **the §5 LLM excision drops ZERO go.mod deps** (contrast ckg, which dropped two). The excision is pure dead-weight deletion of spawn-claude code. Everything else in 02 is genuinely remaining: G1 ollama promotion (not yet done), bge-m3 rebuild (current index is `mock-feature-hash-v1` dim 64), `Freshness()` structured method (not present), and the bgeonnx `--model-name` one-liner. Part D enumerates the stale-vs-live deltas.

---

## Part A — Detailed Design

### G1 — Promote `internal/embed/ollama` → `pkg/embed/ollama`

**STATUS: remaining** (the package is `internal/`, so external module cks cannot import it).

**Proof of current state:**
- `internal/embed/ollama/adapter.go:11` — `package ollama`, pure HTTP via `/api/embed` (`adapter.go:92`), zero CGO (imports only `bytes encoding/json fmt io net/http os`). `Open` auto-probes dim by embedding `"dimension probe"` (`adapter.go:60-67`), `MaxInputTokens()` returns `8192` (`adapter.go:74`). `Options{Endpoint, ModelName}` (`adapter.go:35-38`).
- **Exactly one non-test importer** (grep-confirmed): `cmd/ckv/embedder.go:9` `"github.com/0xmhha/code-knowledge-vector/internal/embed/ollama"`, used at `embedder.go:33` `ollama.Open(ollama.Options{ModelName: globalFlags.modelName})`. Matches spec M4.
- Test sibling `internal/embed/ollama/adapter_test.go` uses `httptest` (`adapter_test.go:7,22,68`) — **no live Ollama needed** to keep its unit tests green after the move.

**Target changes (mechanical, no behavior change):**
1. `git mv internal/embed/ollama pkg/embed/ollama` (moves `adapter.go` + `adapter_test.go`). Package declaration stays `package ollama` (no edit needed — package name is unchanged, only the import path changes).
2. Update the one importer: `cmd/ckv/embedder.go:9`
   - from `"github.com/0xmhha/code-knowledge-vector/internal/embed/ollama"`
   - to   `"github.com/0xmhha/code-knowledge-vector/pkg/embed/ollama"`
3. Grep for any other refs (doc strings, other internal callers): `grep -rn "internal/embed/ollama" .` must return empty after the move. (Currently only `cmd/ckv/embedder.go` and the package's own files reference it.)
4. The `pkg/embed/ollama` doc comment (`adapter.go:1-11`) already documents external usage — keep it; optionally add an "importable by external modules" line.

**What cks then imports (03):**
```go
import (
    "github.com/0xmhha/code-knowledge-vector/pkg/ckv"
    "github.com/0xmhha/code-knowledge-vector/pkg/embed/ollama"
)
adapter, _ := ollama.Open(ollama.Options{ModelName: "bge-m3"}) // dim auto-probed = 1024
engine, _ := ckv.Open(".ckv-data", ckv.OpenOptions{Embedder: adapter})
resp, _ := engine.SemanticSearch(ctx, intent, ckv.SearchOptions{K: 10})
```
No CGO in the *embedder* path; no `libonnxruntime`; no `bgeonnx`; no `ckv mcp` subprocess.

---

### bge-m3 path + index rebuild + vec0 dim situation

**STATUS: registry already has bge-m3; rebuild remaining; vec0 = no migration (confirmed).**

**Registry (already present):** `internal/embed/registry/registry.go:149-164` registers `bge-m3`: `Dim: 1024`, `MaxInput: 8192`, `Normalize: "l2"`, `HFRepo: "BAAI/bge-m3"`. NB: the registry entry sets `Pooling: PoolingCLS` (`registry.go:162`) — but the **Ollama adapter ignores the registry entirely**; it embeds via Ollama's own model definition and only reads back the vector. So the registry's pooling field is bgeonnx-only and irrelevant to the Ollama path. (`registry.go:26-35` docstring claims bge-m3 uses `PoolingMean`, but the actual entry is `PoolingCLS` — a cosmetic inconsistency that only affects a hypothetical bgeonnx-bge-m3 build, **out of scope**; flag in Part D.)

**vec0 dim — no migration (confirmed against store.go):**
- vec0 dimension is DDL-baked: `internal/store/sqlitevec/store.go:178-181` `CREATE VIRTUAL TABLE ... chunk_vec USING vec0(... embedding FLOAT[%d])` interpolates `dim`.
- On reopen, dim is validated: `store.go:130-132` `if storedDim != 0 && storedDim != dim { return ...dim mismatch...rebuild required }`, and `store.go:131` again in `initSchema`.
- bge-large-en-v1.5 and bge-m3 are **both 1024-dim** (`registry.go:135,150`), so a 1024→1024 swap needs **no schema migration** — but a **full rebuild is still required** because the manifest validates the *model name* (see below). The current `ckv-stablenet/manifest.json` is `mock-feature-hash-v1` dim **64**, so going to bge-m3 (1024) is a dim change *from the current on-disk index* and forces a from-scratch DB anyway.

**Manifest model-name gate (rebuild trigger):** `internal/build/reindex.go:145-148` `if man.EmbeddingModel != "" && man.EmbeddingModel != o.Embedder.Name() { return ErrEmbedderMismatch }` — an index built under one model name won't reindex under another. `pkg/ckv.Open` surfaces the same as `ErrIndexUnavailable` (`ckv.go:42`, `query.Open` validates identity). So the bge-m3 index must be a fresh `ckv build`, not a reindex.

**Rebuild command (C3):**
```
ckv build --embedder=ollama --model-name=bge-m3 \
  --src /Users/wm-it-22-00661/Work/github/stable-net/go-stablenet-latest \
  --out ./ckv-stablenet
```
Prereq: `ollama serve` running + `ollama pull bge-m3`. (The go-stablenet tree already exists at that path — it's the `src_root` recorded in the current mock-built manifest.)

**M5 verify (Ollama serves bge-m3 embeddings):** `ollama.Open` auto-probes by POSTing to `/api/embed` (`adapter.go:60,92`). If `bge-m3` isn't exposed as an embedding model by the installed Ollama, `Open` returns `"ollama: connectivity check failed"` or `"returned empty embedding"` (`adapter.go:62,65`). This is the M5 gate — validate before committing to the bge-m3 build. Fallback (bgeonnx CGO) defeats C2's clean import and is last-resort only.

---

### `--model-name` bgeonnx bug

**STATUS: remaining (1-line fix); spec line number slightly off.**

Spec `02 §3` cites `cmd/ckv/embedder.go:27`. The actual bug site is `embedder.go:27`'s `bgeonnx.Open` call:
```go
// cmd/ckv/embedder.go:26-27 (current)
case "bgeonnx":
    a, err := bgeonnx.Open(bgeonnx.Options{ModelDir: modelDir})
```
`globalFlags.modelName` is **not forwarded** — bgeonnx always uses its default model (`registry.DefaultModelName = "bge-large-en-v1.5"`, `registry.go:129`), so `--model-name=bge-m3 --embedder=bgeonnx` silently ignores the flag. (Contrast the ollama case `embedder.go:33` which *does* forward `globalFlags.modelName`.)

**Fix (1 line):** add the model name to the bgeonnx options. Requires confirming `bgeonnx.Options` has a name field — grep shows bgeonnx reads the registry; the field is likely `ModelName`. Exact edit:
```go
case "bgeonnx":
    a, err := bgeonnx.Open(bgeonnx.Options{ModelDir: modelDir, ModelName: globalFlags.modelName})
```
(If the field is named differently, match `internal/embed/bgeonnx`'s `Options` struct — verify at edit time.) **Low priority** (bgeonnx path is not on the cks/contract path; the Ollama path is). Do it in the same step as G1 since it touches the same file.

---

### Domain / invariant indexing + `Freshness()`

**STATUS: Tier-2 extractor ALREADY wired into build; `SkipTier3InTests` hardcoded `true` (override remaining); `Freshness()` structured method REMAINING; policy yaml already ingested.**

**Tier-2 extractor IS wired (already-landed):** `internal/build/pipeline.go:88-96` — for every Go file with chunks, `invariant.Extract(relPath, src, invariant.Options{SkipTier3InTests: true})` runs, then `EmitChunks` + `AttachRefs` append `ChunkInvariant` chunks and staple back-refs. The extractor (`internal/invariant/extractor.go`) supports Tier-1 (`CRITICAL/IMPORTANT/WARNING/Deprecated`, `extractor.go:57-62`), **Tier-2 (`INVARIANT/CONSENSUS/SECURITY`, `extractor.go:65-69`)**, and Tier-3 heuristics (panic/Errorf with policy keywords, `extractor.go:78-81`). So once `// INVARIANT:` / `// CONSENSUS:` / `// SECURITY:` markers are seeded in go-stablenet (`00` §4.2, a go-stablenet-side change, **not a ckv code change**), they auto-index on the next `ckv build`/`reindex`. **No code change needed for Tier-2 wiring.**

**`SkipTier3InTests` override (remaining, small):** `pipeline.go:89` hardcodes `SkipTier3InTests: true` for *all* files. Spec `02 §4` wants `SkipTier3InTests: false` for the `systemcontracts/test/` subtree (governance test invariants — TOCTOU, burn atomicity). Current behavior: Tier-3 heuristics are suppressed in every `*_test.go` (`extractor.go:97` `skipTier3 := opts.SkipTier3InTests && strings.HasSuffix(relPath, "_test.go")`). 

**Target design for the override:** make the pipeline pass `SkipTier3InTests: false` when `relPath` is under a configured "include-test-invariants" path set (default: paths matching `systemcontracts/test/`). Minimal implementation — extend `processFile` to compute the flag per-file:
```go
// internal/build/pipeline.go (processFile, replacing the hardcoded true)
skipT3 := true
if includeTestInvariants(relPath) { // e.g. strings.Contains(relPath, "systemcontracts/test/")
    skipT3 = false
}
results, ierr := invariant.Extract(relPath, src, invariant.Options{SkipTier3InTests: skipT3})
```
Keep the include rule as a small package-level predicate (or thread a `projectcfg` knob if the cks-derived policy should drive it — but a hardcoded `systemcontracts/test/` matcher satisfies `02 §4` and is the lowest-risk option). **Decision: hardcode the `systemcontracts/test/` matcher in `internal/build` (a `var testInvariantPaths` slice) — promoting it to projectcfg is a follow-up, out of scope for the contract.**

**Policy/domain runtime surface (already-landed):** `policy/stablenet.yaml` exists (8 KB, 6 categories per HEAD commit `545a89e`), with `category → watch_out/also_review/required_tests` (grep: 52 matches of those keys). It's applied during build/reindex via `policy.Load` + `pol.Apply(chunks)` (`reindex.go:189,270`). The `category`/`guidance` columns are live (schema MCP v1.1). **No code change** — this is the derived operational view (`00` §4.1); its *production* from cks entries is an `03-cks` codegen task.

**`Freshness()` structured method (REMAINING — genuine gap):**
- `pkg/ckv.Engine` today exposes `CheckFreshness() error` (`ckv.go:174`) — returns `nil` / `ErrFreshnessStale` / git-error. That's a **boolean-ish** signal, not structured data.
- `cks.ops.freshness` (C1) needs the structured `freshness.Report` (`internal/freshness/freshness.go:13-20`: `IndexedHead, CurrentHead, ChangedFiles, Stale, Fresh, Warnings`). The MCP server already returns this shape (`pkg/mcp/server.go:396-401` `freshness.Check(man.SrcRoot, man.IndexedHead)` → `jsonResult(report)`), **but `pkg/ckv` does not expose a Report-returning method** — grep confirms `internal/query/engine.go` has only `CheckFreshness() error`, no `Freshness()`/`FreshnessReport()`.

**Target design — add structured Freshness to both layers:**

1. Re-export the Report type in `pkg/ckv` (so cks doesn't import `internal/freshness`):
```go
// pkg/ckv/ckv.go (new)
// FreshnessReport is the structured index-vs-HEAD comparison cks's
// cks.ops.freshness tool returns. Mirrors internal/freshness.Report.
type FreshnessReport = freshness.Report
```
(Requires moving `internal/freshness.Report` to a position cks can name, OR re-exporting via a type alias. Since `internal/freshness` is internal, the **alias re-export in pkg/ckv** is the clean path — `type FreshnessReport = freshness.Report` makes the struct usable externally through `pkg/ckv` without exposing the internal package. Verify the alias compiles across the module boundary; if Go rejects aliasing an internal type into a public package for external consumers, define a thin public struct in `pkg/ckv` and convert.)

2. Add the engine method:
```go
// internal/query/engine.go (new method beside CheckFreshness)
// FreshnessReport returns the structured freshness comparison.
func (e *Engine) FreshnessReport() (freshness.Report, error) {
    if e == nil || e.man == nil {
        return freshness.Report{}, errors.New("query: engine has no manifest")
    }
    return freshness.Check(e.srcRoot, e.man.IndexedHead)
}
```
3. Surface it on `pkg/ckv.Engine`:
```go
// pkg/ckv/ckv.go (new method)
// Freshness returns the structured index-vs-HEAD report. Unlike
// CheckFreshness (which returns only an error), this gives cks the
// full Report (IndexedHead, CurrentHead, ChangedFiles, Stale, Fresh)
// for cks.ops.freshness.
func (e *Engine) Freshness() (FreshnessReport, error) {
    if e == nil || e.inner == nil {
        return FreshnessReport{}, errors.New("ckv: engine is closed")
    }
    return e.inner.FreshnessReport()
}
```
Keep `CheckFreshness()` for back-compat (it's already public and documented). `Freshness()` is the additive structured variant cks consumes. **S-11 satisfied.**

---

### LLM excision (Binary = deterministic)

**STATUS: remaining (code deletion); ZERO go.mod deps drop (key delta from spec/ckg).**

**The LLM surface (exec-claude spawning only):**
| File:line | What it is | Disposition |
|---|---|---|
| `internal/judge/judge.go` | `ClaudeCLI.Grade` spawns `claude -p` (`judge.go:88` `exec.CommandContext(cctx, c.Binary, args...)`); `Judge` interface; `Verdict` | **DELETE** the whole package (`judge.go` + `judge_test.go`) |
| `internal/eval/eval.go:19,33-34,72-73,77-78,85` | `Options.Judge judge.Judge`, `Result.Verdicts`, `MeanJudge`, the `opts.Judge.Grade` call, `meanVerdictScore` | **EXCISE** the judge wiring; keep recall/MRR/citation/hallucination metrics |
| `cmd/ckv/eval.go:16,28-29,64-65,114-119,176-187,253-258` | `--judge`/`--judge-model` flags, `judge.ClaudeCLI` construction, verdict rendering, `prregress.ClaudePlanAgent`/`ClaudeJudgeScorer` construction | **EXCISE** the judge/agent flags + construction; keep the deterministic eval + pr-eval flow |
| `internal/eval/prregress/agent.go` | `ClaudePlanAgent` (spawns claude, `agent.go:75`); `NewClaudePlanAgent` | **DELETE** `ClaudePlanAgent` + `NewClaudePlanAgent`; **KEEP** the `PlanAgent` interface (`agent.go:21-23`) + `buildPlanPrompt`/`ExtractExpectedFiles` (deterministic parsers reused by tests) |
| `internal/eval/prregress/score.go:22-140` | `ClaudeJudgeScorer` (spawns claude, `score.go:116`); `NewClaudeJudgeScorer` | **DELETE** `ClaudeJudgeScorer` + `NewClaudeJudgeScorer`; **KEEP** the `JudgeScorer` interface (`score.go:18-20`), `Verdict`, `ExtractJudgeVerdict`, `buildJudgePrompt`, `stripJudgeFences` (deterministic) |
| `internal/eval/prregress/runner.go:53,56` | default-fill to `NewClaudePlanAgent()` / `NewClaudeJudgeScorer()` in `RunOptions.fill()` | **EXCISE** the Claude defaults; require Agent/Scorer be injected (return an error if nil) — keeps `PlanAgent`/`JudgeScorer` interfaces so the agent/session layer injects its own |

**KEEP (deterministic, no spawn — `00` §5 / `02 §5`):**
- `internal/eval/{score.go, fixture.go, record.go}` — recall@k, MRR, citation accuracy, hallucination byte-check, fixture loading, interactive record (record.go has **no** judge dependency, grep-confirmed). `internal/eval/eval.go` minus the judge field.
- `internal/eval/prregress/metrics.go` — `IntentScore`, `IntentCosine`, `SymbolF1`, `PlanStepsScore`, `ExtractPlanSteps`, `ExtractPlanSymbols`, `tokenF1`, `cosine` (all pure-Go, deterministic).
- `internal/eval/prregress/{ground.go, checkout.go, fetcher.go, types.go}` — `TruthFiles`, `SortedFiles`, `FileSetF1`, git/gh checkout + fetch (deterministic; `exec.Command("git"/"gh")` is data-fetch, not LLM).
- `internal/glossary/` — regex-based korean→english extraction (`extract.go`, **no LLM**, grep-confirmed: the "claude" ref is a docstring about `.claude/docs/` paths). KEEP entirely.
- `internal/chunk/prefix.go` — see next item.

**go.mod / go.sum:** **NO change.** `grep -c 'anthropic\|cli-wrapper' go.mod go.sum` is already `0`. The excision deletes spawn-claude Go code but pulls no modules. `go mod tidy` after deletion should be a no-op for the require block (run it anyway to drop any now-unused indirect, but expect none from this cut).

**`internal/chunk/prefix.go` — LLM-prefix is dead/unwired (confirmed).** `PrefixLLM`/`PrefixDual`/`LLMPrefixGenerator`/`ResolveEmbedTextFn` (`prefix.go:85-132`) are **never called** outside the package — grep shows only the build path uses `chunk.BuildEmbedText` (the rule-based fn) directly: `internal/build/pipeline.go:48 return chunk.BuildEmbedText` and `reindex.go:188`'s `resolveEmbedTextFn(disablePrefix)` toggles between `RawEmbedText` and `BuildEmbedText` only — never `ResolveEmbedTextFn`/`PrefixLLM`. So `ResolveEmbedTextFn`, `PrefixLLM`, `PrefixDual`, `PrefixMode`, `EmbedTextFn`, `LLMPrefixGenerator` are dead code.
- **Disposition (`02 §5`): DELETE the dead LLM-prefix API** (`prefix.go:80-132`: the `PrefixMode` const block, `EmbedTextFn` type, `LLMPrefixGenerator` interface, `ResolveEmbedTextFn`). **KEEP** `BuildEmbedText`, `RawEmbedText`, `languageLabel` (live, rule-based). This makes the binary D.2-clean (no LLM-prefix surface even latent). `prefix_test.go` only tests `BuildEmbedText` (grep-confirmed) — survives the cut unchanged.

---

## Part B — Implementation Plan (ordered, test-gated)

> Ordering keeps the repo compiling at every commit. **Step 1 (ollama promotion) MUST be first — it gates 03-cks.** Then the additive Freshness + invariant-override (low risk), then the destructive LLM excision last (largest blast radius). The bge-m3 rebuild (Step 6) is a runtime/operator step gated on Ollama.

**Step 0 — Baseline green.**
- Files: none. · Action: `go build ./... && go test ./...` to capture pre-change green (build already confirmed exit 0; CGO sqlite-vec warnings are benign). · Test: build exit 0. · Commit: none.

**Step 1 — G1: promote `pkg/embed/ollama` (GATES 03). [+ external-import smoke]**
- Files: `git mv internal/embed/ollama pkg/embed/ollama` (adapter.go + adapter_test.go); edit `cmd/ckv/embedder.go:9` import path; new `pkg/embed/ollama/external_smoke_test.go` (`package ollama_test`).
- Action: move the package; fix the one importer; add a `package ollama_test` smoke that (a) imports `pkg/embed/ollama` + `pkg/ckv`, (b) stands up an `httptest` server returning a fixed 1024-vector for `/api/embed`, (c) `ollama.Open(ollama.Options{Endpoint: ts.URL, ModelName: "bge-m3"})` → asserts `Dimension()==1024`, `MaxInputTokens()==8192`, `Name()=="bge-m3"`, (d) builds a tiny mock-embedder index with `ckv.MockEmbedder()` and asserts `ckv.Open`+`SemanticSearch` round-trip (proves the two public packages co-import with no CGO in the *embedder* path). This is the **G1 external-import gate** (M2.a).
- Test: `grep -rn "internal/embed/ollama" . | wc -l` == 0; `go test ./pkg/embed/ollama/ ./pkg/ckv/ -run 'TestExternal|TestOllama'`.
- Commit: "refactor(embed): promote internal/embed/ollama → pkg/embed/ollama (G1, gates cks)".

**Step 2 — bgeonnx `--model-name` 1-liner.**
- Files: `cmd/ckv/embedder.go` (the `bgeonnx.Open` call). · Action: forward `globalFlags.modelName` into `bgeonnx.Options` (verify field name against `internal/embed/bgeonnx` Options at edit time). · Test: `go build ./cmd/...`; add/extend a `cmd/ckv` unit test asserting `resolveEmbedder("bgeonnx", "")` passes the model name through (or skip-gated if bgeonnx model files absent). · Commit: "fix(cmd): forward --model-name to bgeonnx (02 §3)".

**Step 3 — `Freshness()` structured method (S-11, additive, gates 03 cks.ops.freshness).**
- Files: `internal/query/engine.go` (add `FreshnessReport()`), `pkg/ckv/ckv.go` (add `FreshnessReport` type re-export + `Freshness()` method). · Action: per Part A — `Engine.FreshnessReport()` wrapping `freshness.Check(e.srcRoot, e.man.IndexedHead)`; `pkg/ckv.Engine.Freshness()` delegating; `type FreshnessReport = freshness.Report` (fall back to a thin public struct + conversion if the internal-type alias fails the external-consumer compile). · Test: `go test ./pkg/ckv/ -run TestFreshness` — build a mock index, assert `Freshness()` returns `Fresh==true` when HEAD matches `IndexedHead`, and `Stale==true` with non-empty `ChangedFiles` after a simulated head change (or a temp git repo). Add an external `package ckv_test` assertion that `FreshnessReport` fields are reachable. · Commit: "feat(ckv): add structured Freshness() for cks.ops.freshness (S-11)".

**Step 4 — Tier-3 invariant override for `systemcontracts/test/` (02 §4).**
- Files: `internal/build/pipeline.go` (per-file `SkipTier3InTests` flag), maybe a small `internal/build/invariant_paths.go` helper. · Action: replace the hardcoded `SkipTier3InTests: true` at `pipeline.go:89` with a per-file predicate (`var testInvariantPaths = []string{"systemcontracts/test/"}`; `skipT3 := !matchesAny(relPath, testInvariantPaths)`). · Test: `go test ./internal/build/ -run TestInvariantTestOverride` — a fixture `systemcontracts/test/gov_test.go` with a Tier-3 policy-keyword panic yields a `ChunkInvariant` (proving Tier-3 runs there despite `_test.go`), while a generic `foo_test.go` does not. · Commit: "feat(build): index governance-test invariants under systemcontracts/test (02 §4)".

**Step 5 — LLM excision (one commit; repo must compile after).**
This is the largest-blast-radius step; do the deletions in sub-order so each intermediate `go build` is informative, but land as one commit.
- 5a. `cmd/ckv/eval.go`: remove `--judge`/`--judge-model` flags (`:64-65`), the `judge.ClaudeCLI` construction (`:114-119`), verdict rendering block (`:176-187`), and the `prregress.ClaudePlanAgent`/`ClaudeJudgeScorer` construction (`:253-258`). Drop the `internal/judge` import (`:16`). Keep all deterministic eval + pr-eval flow (recall/MRR/F1/IntentScore/PlanSteps + the multi-run aggregation `aggregateRuns`/`meanStd` that `cmd/ckv/eval_test.go` tests).
- 5b. `internal/eval/eval.go`: remove `Options.Judge` (`:19`), `Result.Verdicts`/`MeanJudge` (`:33-34`), the `opts.Judge.Grade` call (`:72-73`), the `MeanJudge` aggregation (`:77-78`), and `meanVerdictScore` (`:85-98`). Drop the `internal/judge` import (`:7`).
- 5c. Delete `internal/judge/` entirely (`judge.go`, `judge_test.go`).
- 5d. `internal/eval/prregress/agent.go`: delete `ClaudePlanAgent` + `NewClaudePlanAgent` (`:25-93`); keep `PlanAgent` interface + `buildPlanPrompt` + `ExtractExpectedFiles` + helpers. Drop `os/exec`, `errors`, `time` imports if now unused.
- 5e. `internal/eval/prregress/score.go`: delete `ClaudeJudgeScorer` + `NewClaudeJudgeScorer` + `buildJudgePrompt` (`:22-171`, the spawn + prompt); keep `JudgeScorer` interface, `Verdict`, `ExtractJudgeVerdict`, `stripJudgeFences`. (buildJudgePrompt is only used by the deleted scorer — delete it too.)
- 5f. `internal/eval/prregress/runner.go:52-57`: in `fill()`, replace the `NewClaudePlanAgent()`/`NewClaudeJudgeScorer()` defaults with `if o.Agent == nil || o.Scorer == nil { return fmt.Errorf("prregress: Agent and Scorer must be injected (LLM excised, 00 §5)") }`.
- 5g. `internal/chunk/prefix.go`: delete the dead LLM-prefix API (`:80-132`: `PrefixMode` consts, `EmbedTextFn`, `LLMPrefixGenerator`, `ResolveEmbedTextFn`). Keep `BuildEmbedText`/`RawEmbedText`/`languageLabel`.
- 5h. Fix the now-broken `*_test.go`: `internal/judge/judge_test.go` is deleted (5c); `internal/eval/prregress/{agent_test.go,score_test.go}` — trim assertions on the deleted Claude types, keep tests for the kept interfaces/parsers/`ExtractJudgeVerdict`/`ExtractExpectedFiles`; `internal/eval/prregress/runner_test.go` — inject stub `PlanAgent`/`JudgeScorer` (the harness already stubs them per `agent.go:18-23` doc) instead of relying on Claude defaults; `cmd/ckv/eval_test.go` — already tests only `aggregateRuns`/`meanStd`/`prregress.Score` (grep-confirmed, no judge), so it survives, but verify it compiles after the flag removal.
- Files: as above. · Action: deletions + the runner guard. · Test: `go build ./... && go test ./...`; specifically `go test ./internal/eval/... ./cmd/ckv/... ./internal/chunk/...`. · Test 2: `! grep -rn 'exec.Command.*claude\|ClaudeCLI\|ClaudePlanAgent\|ClaudeJudgeScorer\|ResolveEmbedTextFn\|PrefixLLM' --include='*.go' .` (expect zero hits). · Commit: "refactor: excise LLM (claude-spawn judge/planner + dead LLM-prefix); keep deterministic metrics (00 §5)".

**Step 6 — go.mod tidy + bge-m3 go-stablenet rebuild smoke (M2.b, operator-gated).**
- Files: `go.mod`, `go.sum` (expect no change); optional `Makefile`/CI target. · Action: `go mod tidy` (verify require block unchanged — no anthropic/cli-wrapper to drop, this just confirms cleanliness). Then, **gated on Ollama running**, run `ckv build --embedder=ollama --model-name=bge-m3 --src <go-stablenet> --out ./ckv-stablenet`; after build assert `manifest.json` has `embedding_model: "bge-m3"`, `embedding_dim: 1024`; open with `pkg/ckv.Open(... ollama adapter ...)` and assert `Freshness().Fresh==true` (M2.b) and a `SemanticSearch` returns hits carrying `guidance` for a `consensus/**` query (M2.c, requires seeded markers). · Test: `go test ./... && grep -c 'anthropic\|cli-wrapper' go.mod` (==0); the bge-m3 build is a make/CI smoke (`make rebuild-stablenet`) skipped when Ollama absent. · Commit: "chore: go mod tidy + bge-m3 go-stablenet rebuild smoke (M2)".

---

## Part C — Verification & Acceptance

**Full-repo gate (run after every destructive step, mandatory before "done"):**
```
go build ./...
go test ./...
go vet ./...
golangci-lint run ./...                      # if .golangci.yml present (check repo)
grep -rn 'internal/embed/ollama' . | wc -l   # expect 0 (G1 moved)
grep -c 'anthropic\|cli-wrapper' go.mod go.sum  # expect 0 (was already 0)
! grep -rn 'exec.Command.*claude\|ClaudeCLI\|ClaudePlanAgent\|ClaudeJudgeScorer' --include='*.go' .  # expect no LLM-spawn
```

**M2 acceptance (`02-ckv-refactor.md` §6) → command map:**

| M2 clause | Proof command |
|---|---|
| (a) `pkg/embed/ollama` importable by an external module; `ollama.Open` + `pkg/ckv.Open` + `SemanticSearch` run from a throwaway external main with **zero CGO in the embedder path** | Step-1 `pkg/embed/ollama/external_smoke_test.go` (`package ollama_test`, httptest-backed) + `pkg/ckv` round-trip; `grep -rn internal/embed/ollama . == 0` |
| (b) a go-stablenet index built with bge-m3 and `cks.ops.freshness`-equivalent reports fresh | Step-6 `ckv build --embedder=ollama --model-name=bge-m3 --src <gsn> --out ./ckv-stablenet`; assert manifest `embedding_model=bge-m3 dim=1024`; `pkg/ckv.Engine.Freshness().Fresh==true` (Step-3 method) |
| (c) seeded Tier-2 markers appear as retrievable chunks with `guidance` | Step-4 test (Tier-3 override) + a `SemanticSearch` over the bge-m3 index returning a `ChunkInvariant`/policy-tagged hit for a `consensus/**` query (Step-6 smoke). NB: marker *seeding* is a go-stablenet-side task (`00` §4.2). |
| (d) `go.mod`/build has no `claude`-spawning code; deterministic eval metrics still run | `! grep -rn 'exec.Command.*claude' --include='*.go' .`; `go test ./internal/eval/... ./internal/eval/prregress/...` (recall/MRR/citation/hallucination + IntentScore/SymbolF1/PlanStepsScore green) |

**Ollama + bge-m3 runtime prereq (M2.b/c only):** `ollama serve` + `ollama pull bge-m3`. The unit-level gates (Step 1 external smoke, Step 3 Freshness, Step 4 invariant, Step 5 excision) all run with **no Ollama** (httptest / mock embedder), so CI stays green without a model server; the bge-m3 build is the one operator-gated smoke.

---

## Part D — Risks / Unknowns (live-code findings the spec didn't anticipate)

1. **The §5 excision drops ZERO go.mod deps (HIGH, grep-proven).** ckv has **no** `anthropic-sdk-go` / `cli-wrapper` in `go.mod` *or* `go.sum`. The spec table (`02 §5`) and the parallel ckg plan both frame excision around dropping those deps — for ckv that framing is **stale**. ckv's LLM coupling is purely `exec.Command("claude", ...)` in `internal/judge` + `prregress/{agent,score}.go`. **Implication:** no `go mod tidy` dep-drop to verify; the excision is pure dead-code deletion. (The "claude" greps in `cmd/ckv/mcp.go`, `internal/glossary/extract.go`, `internal/projectcfg/config.go`, `pkg/mcp/server.go` are **docstrings/help text** about `.claude/` paths and `claude mcp add` — not LLM calls; do NOT touch them.)

2. **ckv has CGO — but only in the store, not the embedder (HIGH).** `internal/store/sqlitevec/store.go:18` imports `sqlite-vec-go-bindings/cgo`; the build emits CGO deprecation warnings (benign). C2's "no-CGO" promise is specifically about the **embedder** cks constructs (`pkg/embed/ollama`, pure HTTP). cks importing `pkg/ckv` *does* transitively pull the CGO sqlite-vec store — that is expected and unchanged (ckv has always been CGO for the store). The G1 win is "no `libonnxruntime`/`bgeonnx` CGO + no subprocess," not "ckv becomes CGO-free." Flag this so the cks session (03) doesn't expect a CGO-free `pkg/ckv`.

3. **`Freshness()` structured method is a genuine gap, and the type-alias-of-internal may not compile externally (MID).** `pkg/ckv` exposes only `CheckFreshness() error`; cks needs the structured `freshness.Report`. `internal/freshness` is **internal**, so `type FreshnessReport = freshness.Report` in `pkg/ckv` *may* expose an internal type to external consumers in a way the compiler/godoc handles awkwardly (mirrors the ckg plan's risk #4 about `impact.Compute`'s internal param type). **Mitigation:** the alias should work (the public method returns it through `pkg/ckv`), but if an external `package ckv_test` can't name `ckv.FreshnessReport`'s fields, define a thin public struct in `pkg/ckv` and convert from `freshness.Report` in the method body. Add the external-consumer assertion in Step 3's test to catch this at compile time.

4. **bge-m3 throughput / rebuild time (MID, spec-acknowledged).** `00` §10 / `02 §7`: ~0.74 chunks/s on dev. The current go-stablenet index is **26,015 chunks** (`ckv-stablenet/manifest.json`). At 0.74 chunks/s that's **~9.8 hours** for a full bge-m3 embed via Ollama — materially worse than the spec's "~6h+" estimate because the real chunk count is higher than assumed. **Implication:** the bge-m3 rebuild (Step 6) is a long, operator-supervised job, not a CI gate. Plan it as an overnight run; the unit gates (Steps 1,3,4,5) prove correctness without it. Consider Ollama batch/concurrency tuning (the adapter sends the whole batch in one `/api/embed` call, `adapter.go:83-86`, so larger `--batch-size` may help if Ollama parallelizes).

5. **Registry pooling inconsistency for bge-m3 (LOW, out of scope).** `registry.go:162` sets bge-m3 `Pooling: PoolingCLS`, but the package docstring (`registry.go:31-32`) says bge-m3 uses `PoolingMean`. This only matters for a hypothetical **bgeonnx**-served bge-m3 (the CGO fallback). The **Ollama path ignores the registry's pooling entirely** (Ollama does its own pooling), so the contract path is unaffected. Do not "fix" it as part of this refactor unless the bgeonnx fallback is taken — flag for a separate cleanup.

6. **The current `ckv-stablenet` index is mock/self-stale (NONE/fact).** `manifest.json`: `embedding_model: "mock-feature-hash-v1"`, `embedding_dim: 64`, `src_root: .../go-stablenet-latest`. So the bge-m3 rebuild is a *from-scratch* DB (dim 64→1024 forces it regardless of the model-name gate). The go-stablenet tree exists at the recorded `src_root` — no path discovery needed.

7. **Tier-2 extractor is already wired; only the Tier-3 test-override and marker seeding remain (NONE/fact).** `pipeline.go:88-96` runs `invariant.Extract` on every Go file in both `build` and `reindex` paths. The `02 §4` "after markers are seeded they auto-index" is already true on HEAD — the ckv-side work is just the `systemcontracts/test/` Tier-3 override (Step 4); the marker *seeding* in go-stablenet is a separate repo's task (`00` §4.2, ~30 min mechanical).

8. **`runner.go` default-fill change is a behavior break for any direct caller (LOW).** Making `RunOptions.fill()` error when Agent/Scorer are nil (5f) breaks any code that relied on the Claude defaults. Grep shows only `cmd/ckv/eval.go:249-259` constructs `RunOptions`, and after 5a it no longer injects Claude agents — so `pr-eval` without injected agents will now error cleanly (correct per `00` §2.2: LLM work moves to the agent layer). Confirm no test depends on the silent-Claude-default behavior; `runner_test.go` already stubs agents (the interface exists for exactly this).

---

### Fact-based summary
**Fact (None-label, code-verified):** ckv `go.mod`/`go.sum` contain no `anthropic-sdk-go`/`cli-wrapper` (grep `0`); the only `internal/embed/ollama` importer is `cmd/ckv/embedder.go:9`; the ollama adapter is pure HTTP (`/api/embed`, `adapter.go:92`) with dim auto-probe; `bge-m3` is registered (1024-dim, 8192-tok, `registry.go:149-164`); vec0 dim is DDL-baked + validated (`store.go:130-132,178-181`), 1024→1024 needs no migration but model-name gate forces rebuild (`reindex.go:145-148`); the invariant Tier-2 extractor is wired into `build`+`reindex` via `pipeline.go:88-96` with `SkipTier3InTests: true` hardcoded; `policy/stablenet.yaml` is live with 6 categories; `pkg/ckv` exposes `CheckFreshness() error` but **no** structured `Freshness()`/Report method; `freshness.Report` (with `Fresh`/`Stale`/`ChangedFiles`) exists in `internal/freshness`; the LLM coupling is `exec.Command("claude")` in `internal/judge/judge.go:88`, `prregress/agent.go:75`, `prregress/score.go:116`, wired in `cmd/ckv/eval.go`; `internal/chunk/prefix.go`'s `PrefixLLM`/`ResolveEmbedTextFn` are dead (unwired, grep-confirmed); the current `ckv-stablenet` index is `mock-feature-hash-v1` dim 64 over 26,015 chunks; `go build ./...` exits 0.

**Opinion — High:** the substantive work is G1 (ollama promotion, gates 03) + the structured `Freshness()` method + the LLM-spawn excision; the bge-m3 rebuild is correct but long (~10h on real chunk count). **Mid:** the `FreshnessReport` internal-type alias may need a public-struct fallback for external consumers; the Tier-3 override is small. **Low:** registry pooling inconsistency (bgeonnx-only, out of scope); `runner.go` default-fill break (only the excised `cmd/ckv/eval.go` was a caller).
