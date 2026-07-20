# 03 — code-knowledge-system (cks) Refactor

> **Derives from:** `00-system-contract.md` (C1, C2, C3, §4, §5). **Repo:** `github.com/0xmhha/code-knowledge-system`.
> **Role in R1′:** the **sole agent-facing MCP**. Composes ckv (semantic→keyword) + ckg (keyword→code) in-process, exposes the C1 surface to coding-agent. Largest refactor; depends on `01` + `02`.
> **Isolatable:** Yes, once `01`/`02` publish their `pkg/` surfaces. The C1 schema is frozen in `00`.

> **⚠ Superseded by `plans/03-cks-plan.md` (live-code, authoritative).** Live-code corrections: (1) **G4 (vocab resolver) already done** (144-LOC + glossary codegen shipped). (2) **G3 is 1/4 done** — `GetSubgraph` wired; only `ImpactOfChange`/`EvidenceForIntent`/`GetNodePRs` remain stubs. (3) **G2** prototypes are lazy-embedded at `intent.New()` — no on-disk regen, just swap embedder + 1024-dim assert. (4) **Hard cross-repo build order:** cks cannot build until `02` ships `pkg/embed/ollama` + `Freshness()` and `01` ships `pkg/concurrency.Analyze`. (5) **SSoT schema file `coding-agent/contract/agent-mcp.schema.json` does not exist yet** — author it in `05`; cks's M2.a golden test depends on it. Use the plan for execution.

## 1. Contract this repo must satisfy

- **Exposes (C1):** the `cks.context.*` / `cks.ops.*` tools exactly as the SSoT JSON Schema (`00` §3). This is the only agent-facing retrieval surface.
- **Consumes (C2):** `pkg/ckv` + `pkg/embed/ollama` (from `02`), `pkg/store` + `pkg/mcphandlers` + `pkg/bm25`/`pkg/impact`/`pkg/concurrency`/`pkg/evidence` (from `01`) — all in-process.
- **Build note (live-code):** importing `pkg/ckv` makes cks's build **inherit sqlite-vec CGO** (the ckv store). cks avoids the ONNX/bgeonnx stack (HTTP ollama embedder) but is **not** CGO-free — the build toolchain must support sqlite-vec. ckg's store is `modernc.org/sqlite` (CGO-free), so the CGO comes only from ckv.

## 2. Load-bearing changes

| ID | Change | Evidence | Action |
|---|---|---|---|
| **G1** | ckv consumed as subprocess MCP proxy (hangs: 2/9 dogfood timeouts) | `internal/ckvclient/real.go` (~543 LOC) | **Delete the proxy.** Import `pkg/ckv` + construct `pkg/embed/ollama` (bge-m3) in-process. Add `require code-knowledge-vector` to go.mod. |
| **G2** | Intent classifier uses `FakeEmbedder` (hash noise, **dim 32**) → intent routing meaningless | `cmd/cks-mcp/main.go:109` | Replace with the same Ollama bge-m3 embedder used for ckv. **(S3)** Also **regenerate the intent label/prototype embeddings with bge-m3** and remove any hardcoded `Dim: 32`/32-dim assumptions in `internal/composer/intent/*` — otherwise the query (1024-dim, bge-m3) is compared against stale/mismatched prototypes and intent stays broken. Add a startup check asserting query-dim == prototype-dim == embedder.Dimension(). |
| **G3** | 4 ckg methods unwired in `ckgclient.Client` | cks digest S-10 | Wire `ImpactOfChange`→`pkg/impact.Compute`, `EvidenceForIntent`→`pkg/evidence.BuildPack`, `GetNodePRs`→`store.Reader.GetNodePRs`, `GetSubgraph`→`store.Reader.SubgraphByQname`. Unblocks `impact_analysis`/`change_history`/`get_subgraph` tool handlers. |
| **G4** | `vocab.Resolver` nil → no Korean→code keyword expansion (ckv's keyword role's bridge) | S-5; `cmd/cks-mcp/main.go:118` | Implement `internal/vocab/resolver.go`; wire glossary path. Glossary populated per `00` §4.2 hybrid. |
| **G5** | BM25 score synthesized (fake) → bleeds into stage1 confidence / stage2 weight / budget order | `ckgclient/real.go:150-192`, F-1 | After `01` G1 exposes real Score/Rank, consume it; remove synthesis. |
| **G6** | `cks.ops.freshness` handler can't call through (ckv lacks `Freshness`) | S-11 | After `02` §4 adds `Freshness()`, wire it. |
| **G7** | **No `cks.context.concurrency_impact` tool** (stage-7 concurrency requirement has no agent-facing path) | grep-confirmed: cks exposes 11 tools, none concurrency | Register the **NEW** `cks.context.concurrency_impact` tool (`00` C1, S1); back it with `01` G7's `ConcurrencyImpact(symbol, depth)`. Add to the SSoT schema. |
| **G8** | **No `cks.ops.index` tool** — agent can detect staleness (`freshness`) but cannot trigger a refresh | grep-confirmed: no index/reindex handler in `internal/mcp` | Register the **NEW** `cks.ops.index{mode, since_commit}` tool (`00` C1/C3, S2); back it with `ckv reindex` + `ckg` incremental build. |

## 3. Composer (mechanics, not control) — `00` §2.3

- Keep the 6-stage pipeline (`intent → stage1 → stage2 → stage3 → budget → sanitize`); confirmed LLM-free (`composer.go`, `intent/embedder.go:12`). With G2's real embedder, intent + stage1 become functional.
- **Tune over-retrieval:** dogfood precision was 2–24% (returns 35–53 citations regardless of need). Lower default citation count / tighten budget so the agent isn't flooded. The agent sets depth/budget knobs (control); composer respects them.
- Add per-stage latency instrumentation (currently only total `elapsed` at `composer.go:289-315`) so the validation spike (`00` §9) can attribute cost.

## 4. Domain SSoT sync — `00` §4.1

- cks `docs/domain-knowledge/projects/go-stablenet/entries/*.yaml` is the **master**.
- Write the sync codegen: on entry `status: verified`, derive (a) ckv `policy/stablenet.yaml` `watch_out` strings and (b) ckg `policy.yaml` `governed_by` mappings. One edit in cks → both consumers update on next reindex.
- Drive the curation of the ~6 manual byzantine-fairness entries (`00` §4.2) — but the *curation activity* is a Claude-session task (binary stays deterministic).

## 5. Binary = deterministic (already clean) — `00` §5

cks has **zero LLM** in non-test code (confirmed). `cks-eval` spawns the deterministic `cks-mcp` and computes P/R/F1 vs YAML ground truth — keep as binary self-test. No excision needed here.

## 6. Indexing (C3) & runtime prerequisites

Point ckv + ckg at the real go-stablenet tree (currently self-index). Provide config (`policies/cks.yaml`) for `Backends.CKV.Path`, `Backends.CKG.Path`, glossary path, Ollama URL/model.

**Ollama runtime dependency (S5):** in-process bge-m3 means **cks-mcp now requires a running Ollama daemon with `bge-m3` pulled.** Define the failure behavior explicitly:
- At startup, `ollama.Open` fails fast with a clear error if Ollama is unreachable — surface it as a `cks.ops.health` "degraded: embedder unavailable" rather than a crash.
- Degraded mode: fall back to the existing **Smart Dummy** ckv path (records would-be calls as LLM instructions) so the agent can still proceed, slower, via session retrieval. `cks.ops.health` must report this state.
- Document the prereq in coding-agent `SETUP.md` (cross-ref `05`).

## 7. Work order (this repo)

1. G1 (in-process pkg/ckv import, delete proxy) + G2 (real intent embedder).
2. G3 (wire 4 ckg methods) + G5 (real BM25 score) + G6 (freshness) + **G7 (concurrency_impact tool)** + **G8 (ops.index tool)**.
3. G4 (vocab resolver + glossary wiring).
4. Composer tuning + per-stage instrumentation (§3).
5. Domain sync script (§4) + go-stablenet config + Ollama prereq/degraded-mode (§6).

**Acceptance (M2) — done when:** (a) cks-mcp registers exactly the C1 SSoT tool set (now incl. `concurrency_impact` + `ops.index`) and passes the schema golden test; (b) no subprocess `ckvclient` remains; ckv consumed via `pkg/ckv` + Ollama bge-m3 in-process; (c) intent classifier returns stable, non-random intents on known queries (dim assertion passes); (d) `cks-eval` deterministic scenarios pass against go-stablenet index; (e) `cks.ops.health` reports degraded (not crash) when Ollama is down.

## 8. Out of scope / risks

- The "Smart Dummy" fallback (records would-be calls as LLM instructions) — keep as a degraded mode but the real path is now primary.
- cks is where the validation spike (`00` §9) is exercised end-to-end; treat its output as the go/no-go signal.
