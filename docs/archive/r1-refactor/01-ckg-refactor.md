# 01 — code-knowledge-graph (ckg) Refactor

> **Derives from:** `00-system-contract.md` (C2, C3, §5). **Repo:** `github.com/0xmhha/code-knowledge-graph`.
> **Role in R1′:** keyword→code backend. Given exact code keywords, return related code + modification history + concurrency-impact, as an **in-process Go library** that cks imports. Most mature of the three; mostly hardening + de-LLM.
> **Isolatable:** Yes — implementable against this repo alone. The only external contract is the `pkg/` surface cks imports (frozen in §1).

> **⚠ Superseded by `plans/01-ckg-plan.md` (live-code, authoritative).** The detailed plan found this spec's gap evidence **mostly stale**: G1 (Score/Rank), G2 (`pkg/bm25` public), G3 (`code_snippet`/blobs), G5 (typed `calls`), G6 (channel send/recv pairs) are **already landed on HEAD**. Real remaining scope = **G7 (`ConcurrencyImpact`, net-new `pkg/concurrency`) + LLM excision**. Treat G1–G6 as guard-tests, not work. Use the plan for execution.

## 1. Contract this repo must satisfy (C2)

cks imports, in-process:
- `pkg/store` — `Reader`, `OpenReadOnly`, `GetManifest`, `SearchHit`, `PRRef`.
- `pkg/mcphandlers` — `RegisterAll(s, reader)` + 8 `Register*` + `NewLLMSafeReader` (already done, T-14).
- `pkg/bm25`, `pkg/impact`, `pkg/evidence`, `pkg/smartctx` as needed by cks's client.

**Freeze:** the methods cks's `ckgclient.Client` needs — `BM25Search`, `FindSymbol`, `Neighbors`, `ImpactOfChange`, `EvidenceForIntent`, `GetNodePRs`, `GetSubgraph`, **`ConcurrencyImpact`** (S1), `Health`, `Close`. ckg must expose all of these via `pkg/` (not `internal/`).

## 2. Gaps to close (evidence-based)

| ID | Gap | Evidence | Action |
|---|---|---|---|
| G1 | `pkg/store.Node` has no real `Score`/`Rank` → cks synthesizes a fake BM25 score (`1 − i/(N+1)`) | cks `ckgclient/real.go:150-192`; ckg-NEW-9 open P1 | Add real `Score`/`Rank` to `SearchHit`; surface okapi score from FTS5 |
| G2 | `pkg/bm25` not stable for external import | ckg-NEW-9 (P1) | Stabilize `pkg/bm25` public API; cks + ckv both import it |
| G3 | `code_snippet` column always empty | HANDOFF F-8 | Populate from blob store on node materialization |
| G4 | No const/var nodes | HANDOFF F-8 | Emit `Constant`/`Variable` nodes (config-as-code domain values, §4 of `00`, depend on these) |
| G5 | `calls` resolution name-based, ignores `types.Info` | HANDOFF F-2 (`relations.go:657 _ = info`) | Use loaded `types.Info` for `*types.Func` resolution; add interface→impl edges (verify if already landed per DISPATCH doc — repo docs conflict on dates) |
| G6 | `channels` may emit self-loops not producer→consumer pairs | HANDOFF F-3 (`relations.go:631`) | Verify against current code; if present, emit `sends_to`/`recvs_from` pairs (concurrency-impact accuracy — `00` §4 byzantine path depends on this) |
| **G7** | **No `pkg/` query that returns concurrency-impact** (the edges exist — `spawns`/`sends_to`/`recvs_from`/`acquires_lock`/`accessed_under_lock` — but no public traversal exposes them) | deep-dive D-c (edges live); grep-confirmed cks has no concurrency tool | Expose `ConcurrencyImpact(symbol, depth)` in `pkg/` — a `Neighbors` traversal filtered to the 5 concurrency edge types. Backs the **NEW** `cks.context.concurrency_impact` tool (`00` C1, S1). Pipeline stage-7 requires it. |

## 3. Binary = deterministic (excise LLM) — `00` §2.2 / §5

Remove all LLM/`claude`-spawn from the built binary:

| Action | File | Note |
|---|---|---|
| EXCISE | `cmd/ckg/eval.go` | `ckg eval` command, `selectLLMBackend`, `--llm-backend`/`--llm-claude-binary` flags |
| EXCISE | `internal/eval/llm.go` | `APIClient` (anthropic-sdk-go, `ANTHROPIC_API_KEY`) |
| EXCISE | `internal/eval/llm_cli.go` | `CLIClient` (spawns `claude -p` via `cliwrap.Manager`) |
| EXCISE | `internal/eval/gamma_loop.go` | multi-turn LLM loop |
| EXCISE | `internal/eval/runner.go` | α/β/γ/δ baseline LLM execution |
| DROP go.mod | — | `github.com/anthropics/anthropic-sdk-go`, `github.com/0xmhha/cli-wrapper` + transitive (`creack/pty`, `vmihailenco/msgpack`, …) |
| **KEEP** as binary self-test | `internal/eval/retrieval/` (runner.go, scorer.go) | deterministic store-probe P/R/F1 — no LLM. Expose as `ckg eval-retrieval`. |
| KEEP | `internal/validate/llm.go` | DryRun stub, no network call — leave as-is (enforces no-call invariant) |
| KEEP | all `exec.Command("git", …)` in temporal/, buildpipe/, server/ | deterministic |

The deterministic scorers entangled with the LLM answer (`score.go`, `hallucination_check.go`, `citation.go`) move to the agent/session eval layer (they score *LLM output*, which now lives there). `internal/eval/doc.go` already anticipates extraction to a `code-knowledge-graph-eval` sister.

## 4. Indexing (C3)

- Provide a clean `ckg build --src <go-stablenet> --out <graph.db>` run pointed at the real go-stablenet tree (live `.ckg-data` currently self-indexes ckg — repoint).
- Load go-stablenet `policy.yaml` (derived from cks entries, `00` §4.1) via `--policy-file`/`--security-pattern-file` so `Policy`/`SecurityPattern` nodes + `governed_by`/`has_security_pattern` edges populate (currently 0).
- Incremental: `ckg watch` (fsnotify) is live; `runIncremental` partial-cache stays disabled (cold rebuild ~40s fallback) until reverse-ref index lands.

## 5. Work order (this repo)

1. G1+G2 (Score/Rank + `pkg/bm25` stability) — unblocks cks's real ranking and ckv's BM25 import.
2. G4 (const/var nodes) — unblocks `00` §4 config-as-code extraction.
3. G3, G5, G6 (snippet fill, calls/channels accuracy).
4. Excise LLM eval (§3) → drop deps.
5. go-stablenet index + policy load (§4).

**Acceptance (M2) — done when:** (a) all frozen `pkg/` methods incl. `ConcurrencyImpact` compile and return non-empty on a go-stablenet symbol with known concurrency; (b) `internal/eval/retrieval` deterministic self-test passes in CI; (c) `go.mod` no longer requires `anthropic-sdk-go` or `cli-wrapper`; (d) `ckg build` against go-stablenet populates `Policy`/`SecurityPattern` nodes (count > 0).

## 6. Out of scope / risks

- δ-score parity, γ-latency, SSA concurrency (D1) — quality backlog, not contract-blocking.
- Doc-date conflicts (W-B/W-C landed vs "pending"): verify against HEAD code before touching G5/G6.
