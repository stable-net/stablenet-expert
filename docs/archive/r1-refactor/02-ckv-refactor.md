# 02 — code-knowledge-vector (ckv) Refactor

> **Derives from:** `00-system-contract.md` (C2, C3, §4, §5). **Repo:** `github.com/0xmhha/code-knowledge-vector`.
> **Role in R1′:** meaning→vocabulary backend. A vague/Korean/English request → exact code keywords used in the codebase, via semantic search. Consumed by cks **in-process**.
> **Isolatable:** Yes. The load-bearing change (the Ollama embedder promotion) is mechanical and self-contained.

> **⚠ Superseded by `plans/02-ckv-plan.md` (live-code, authoritative).** Live-code corrections: (1) Tier-2 invariant indexing is **already wired** into build/reindex (`pipeline.go:88-96`) — verification only. (2) §5 "drop go.mod deps" is **wrong for ckv** — it has no `anthropic-sdk-go`/`cli-wrapper`; the LLM coupling is pure `exec.Command("claude")`. (3) `pkg/ckv` is **not CGO-free** (sqlite-vec store). (4) Real remaining scope = G1 (ollama promote), structured `Freshness()` (only `CheckFreshness() error` exists today), `SkipTier3InTests` override, `--model-name` bug, LLM-`exec` excision, bge-m3 rebuild (~10h). Use the plan for execution.

> **Cross-repo contract pins (integrated audit — these bind `03`-cks):** the plan (`plans/02-ckv-plan.md`) must pin three shapes `03` consumes, or they drift at integration: **(B1)** the `cks.ops.index{mode:"incremental"}` tool calls a `ckv reindex` CLI — confirm/define the exact `ckv reindex --src --out` subcommand + flags so cks G8 has a real producer contract. **(B2)** ship `Freshness()` as a **concrete public `ckv.FreshnessReport` struct** with named fields `{Fresh, IndexedHead, CurrentHead, ChangedFiles}` (NOT an alias of the internal `freshness.Report`) so cks field-copies can't drift. **(B4)** document the promoted `pkg/embed/ollama` adapter's **exact public method signature** (`Embed(ctx, []string) ([][]float32, error)` per `types.Embedder`) so cks knows whether a bridge to `intent.Embedder` (`Embed(ctx, string)`) is needed — it is; specify the one-line adapter.

## 1. Contract this repo must satisfy (C2)

cks imports, in-process, with **no CGO**:
- `pkg/ckv` — `Open(path, OpenOptions{Embedder})`, `Engine.SemanticSearch(ctx, intent, SearchOptions)`, `Manifest()`, `CheckFreshness()`, `Warmup()`, `Close()` (already public).
- **NEW:** `pkg/embed/ollama` — promoted from `internal/embed/ollama` (see G1).
- `pkg/types.Embedder` (already public).

## 2. Load-bearing gap: in-process embedder (deep-dive D-a)

| ID | Gap | Evidence | Action |
|---|---|---|---|
| **G1** | The only public embedders are mocks; the real one (`bgeonnx`) is `internal/`+CGO → external module (cks) cannot construct a real embedder, forcing the subprocess proxy | `docs/embedder-integration.md:139`; cks `ckvclient/real.go:39-43` | **Promote `internal/embed/ollama` → `pkg/embed/ollama`** (pure HTTP, zero CGO, ~126 LOC, package-decl change). **Only one non-test importer to update: `cmd/ckv/embedder.go:9` (grep-verified, M4).** No behavior change. |

After G1, cks does:
```go
adapter, _ := ollama.Open(ollama.Options{ModelName: "bge-m3"})   // dim auto-probed = 1024
engine, _ := ckv.Open(".ckv-data", ckv.OpenOptions{Embedder: adapter})
resp, _ := engine.SemanticSearch(ctx, intent, ckv.SearchOptions{K: 10})
```
No ONNX native deps (the embedder is pure HTTP), no `bgeonnx`, no subprocess. **Note:** `pkg/ckv` still pulls **sqlite-vec CGO** (the store) — so cks's build inherits that light CGO dep; it is *not* fully CGO-free. The avoided cost is the heavy ONNX/tokenizers stack.

## 3. Embedder fitness (bge-m3) — `00` §7

- bge-m3: multilingual (Korean+English), 8192-token window (vs bge-large-en's 512), **1024-dim = same as bge-large → no sqlite-vec schema migration.**
- **Rebuild required:** the manifest validates model name; an index built with `bge-large-en-v1.5` won't open under name `bge-m3`. Run `ckv build --embedder=ollama --model-name=bge-m3 --src <go-stablenet>`.
- Prereq: Ollama running with `bge-m3` pulled.
- **Verify (M5):** confirm Ollama serves bge-m3 as an *embedding* model via `/api/embed` (the adapter calls that endpoint and auto-probes dim). If a given Ollama build/tag does not expose bge-m3 embeddings, fall back to serving bge-m3 through bgeonnx (CGO) — but then cks cannot import the embedder cleanly (defeats `00` C2). Validate this in the spike's Layer A before committing.
- Minor 1-line fix: `cmd/ckv/embedder.go:27` ignores `--model-name` on the bgeonnx path (forward `globalFlags.modelName` to `bgeonnx.Open`). Low priority (bgeonnx path only).

## 4. Domain/invariant indexing — `00` §4

ckv is the runtime surface for domain guidance (the only channel live today):
- `policy/stablenet.yaml` (path→category→`guidance{watch_out, also_review, required_tests}`) is **derived** from cks entries (`00` §4.1). Keep it as the ingested operational view; consume via the existing `category`/`guidance` columns (schema MCP v1.1, already live).
- Invariant extractor (`internal/invariant/extractor.go`) already supports Tier-2 `// INVARIANT:`/`// CONSENSUS:`/`// SECURITY:`. After markers are seeded in go-stablenet (`00` §4.2), they auto-index on reindex.
- Set `SkipTier3InTests: false` for the `systemcontracts/test/` subtree (governance test invariants — TOCTOU, burn atomicity).
- Add a `Freshness()` method to the client surface cks consumes (cks `cks.ops.freshness` depends on it — S-11).

## 5. Binary = deterministic (excise LLM) — `00` §2.2 / §5

| Action | File | Note |
|---|---|---|
| EXCISE | `internal/judge/judge.go` | `ClaudeCLI.Grade` spawns `claude -p` |
| EXCISE | `cmd/ckv/eval.go:28,64` | `--judge` flag + `Options.Judge` wiring |
| EXCISE | `internal/eval/prregress/agent.go` | `ClaudePlanAgent` (spawns claude) |
| EXCISE | `internal/eval/prregress/score.go:22-137` | `ClaudeJudgeScorer` (spawns claude) |
| EXCISE | `internal/eval/prregress/runner.go:32-56` | default-fill to Claude agent/scorer; keep `PlanAgent`/`JudgeScorer` interfaces |
| **KEEP** | recall@k, MRR, citation, hallucination byte-check, `prregress/metrics.go` (F1, BM25 cosine, IntentScore, PlanStepsScore), checkout/fetcher (git/gh) | deterministic — binary self-test + CI |
| DELETE or annotate | `internal/chunk/prefix.go` `PrefixLLM`/`PrefixDual`/`LLMPrefixGenerator` | already dead code (never wired); binary is D.2-clean |

The LLM-based plan generation + judging move to the agent/session eval layer.

## 6. Work order (this repo)

1. **G1** — promote `pkg/embed/ollama` (unblocks cks in-process import; gates everything in `03`).
2. bge-m3 path + go-stablenet rebuild (§3, C3).
3. Invariant/Tier-2 indexing + governance-test override + `Freshness()` (§4).
4. Excise LLM eval (§5).

**Acceptance (M2) — done when:** (a) `pkg/embed/ollama` is importable by an external module and `ollama.Open` + `pkg/ckv.Open` + `SemanticSearch` run from a throwaway external main with zero CGO; (b) a go-stablenet index is built with bge-m3 and `cks.ops.freshness`-equivalent reports fresh; (c) seeded Tier-2 markers appear as retrievable chunks with `guidance`; (d) `go.mod`/build has no `claude`-spawning code (judge/prregress-Claude removed); deterministic eval metrics still run.

## 7. Out of scope / risks

- `keyword_search` permanent BM25 index, `find_invariants`/`get_conventions` (Phase B) — quality backlog, not contract-blocking; cks's keyword extraction uses `semantic_search` results.
- Throughput ~0.74 chunks/s → full go-stablenet embed ~6h+ (risk on rebuild/A-B). bge-m3 chosen to keep the validation spike to one build.
- vec0 dimension is DDL-baked; any future non-1024 embedder requires full DB rebuild (no migration).
