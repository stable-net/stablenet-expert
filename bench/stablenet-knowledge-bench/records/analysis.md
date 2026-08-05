# ANALYSIS — LOCAL-20260609_003552 (CKG Benchmark)

## 1.1 Ticket framing
- type: feature, requirement_source=local, autonomy.mode=auto, pipeline_variant=full
- Summary: build an automated CKG benchmark that quantifies whether the stablenet-knowledge engine improves
  AI code-understanding on go-stablenet, by submitting 30 known-answer questions under 4
  context-provision methods and measuring 4 metrics (location accuracy, correctness rate,
  hallucination/error count, information volume).

## 1.2 stablenet-knowledge retrieval backend (health + freshness)
- `cks.ops.health` returned `status=ok`.
  - ckg: reachable, schema_version `1.15`, indexed_head `9978930ba62380a428f67ad6ff664a6a52e4a547`
  - ckv: reachable, stats_hash matches indexed_head, last_index_at `2026-06-08T04:44:32Z`
- Freshness: current go-stablenet HEAD = `9978930ba62380a428f67ad6ff664a6a52e4a547` — equals
  `indexed_head`. No reindex needed; ckv is in full-semantic mode (not Smart-Dummy).
- Freshness matters only for golden-set anchors (file+line); the deliverable changes no production code.

## 1.3 Domain & complexity (path-based)
- Primary domain of the deliverable: harness/eval — not a go-stablenet production module.
  Lives at `.stablenet-expert/bench/ckg-bench/` (sibling to existing `bench-orchestration` cells dir).
- Domains referenced by golden-set targets: `consensus`, `core` (types + txpool), `systemcontracts`, `state`.
- Complexity: **complex**. Drivers:
  - 4 methods × 30 questions = 120 cells/run (vs. 3-way harness's 1–3 cells)
  - Two semantic metrics (correctness, hallucination) require a deterministic verifier on top of LLM output
  - Glue between two existing assets in different repos/languages: coding-agent `bench/` (Python,
    3-way, end-to-end pipeline correctness) and stablenet-knowledge `internal/eval/` (Go, retrieval P/R/F1)
  - Reproducibility: golden-set anchors must survive code drift via SHA-pinning + live re-resolution

## 1.4 4-method ↔ existing-asset mapping (resolves ticket-parsed warning[0])

| Ticket method | Input to AI | Closest existing asset | Verdict |
|---|---|---|---|
| **방식 1** (baseline: raw file contents) | curated full file contents, no graph, no skills | `bench-orchestration` mode B_code_only | partial — B_code_only lets the planner do its own grep/read; method 1 pre-supplies files in one shot. Build a thin "file-bundle" prompt-builder; cannot reuse the agent as-is. |
| **방식 2** (entire stablenet-knowledge graph at once) | a graph dump scoped to the question's modules | none | **new**. stablenet-knowledge has no "dump everything" API; full repo is 781 files. Bound to `get_subgraph(depth=2, max_total=2000)` over 4 root packages. |
| **방식 3** (incremental stablenet-knowledge lookups) | multi-turn `semantic_search` / `find_symbol` / `get_subgraph` / `find_callers` | `bench-orchestration` mode A_stablenet_knowledge_mcp (real planner) | direct match — A_stablenet_knowledge_mcp already does multi-turn stablenet-knowledge retrieval. |
| **방식 4** (stablenet-knowledge auto-selected single shot) | one `cks.context.get_for_task` call | stablenet-knowledge's own `internal/eval/` + `cmd/cks-eval` | direct match on the stablenet-knowledge side: cks-eval already feeds `expected_citations` YAMLs to `get_for_task` and scores P/R/F1. |

Conclusion: existing assets cover ~50% of the 4 methods, but **neither closes the loop with an
LLM-in-the-loop Q&A measurement**. The new harness sits between them and must:
1. Reuse cks-eval's `expected_citations` schema (file + start_line/end_line) and overlap matcher
   (`code-knowledge-system/internal/eval/metrics.go`).
2. Reuse coding-agent `bench/lib/{usage,report,collect}.py` shapes for token accounting + rollup.
3. Add: 4 method dispatchers, an AI invocation layer, a structured-citation extractor, and a
   hallucination verifier (calls `cks.context.find_symbol` on each citation; unmatched = hallucination).

## 1.5 Related code (CKV-grounded — golden-set seeds, 10 pre-validated)
See related-code.json `ckv.results` for SN01–SN10 anchors (resolved against indexed HEAD `9978930ba`).
These 10 are exported as-is to the golden-set; 20 more are authored by the plan.

## 1.6 Structural context (CKG)
No production symbol is mutated, so no caller/callee fan-out applies to the deliverable. stablenet-knowledge is used
*as subject of measurement* (the harness grades stablenet-knowledge tool outputs) and *as verifier* (re-resolve every
golden-set anchor via `cks.context.find_symbol` at run start, flagging drift). Golden-set policy
mandates ≥1 question per concurrency invariant (invariant 11, `plugins/core-dev/domains/go-stablenet/invariants.md`): `consensus/wbft/core.currentMutex` and the
`pool.loop()`-only mutation of txpool maps.

## 1.7 Impact analysis (indirect)
- **stablenet-knowledge tool-surface coupling** (desirable): exercises semantic_search, find_symbol, get_subgraph,
  find_callers, find_callees, impact_analysis, concurrency_impact, get_for_task. Any breaking change
  fails this harness — exactly the regression detector stablenet-knowledge needs.
- **coding-agent `bench/` coupling**: reuses libraries; lives in a sibling cells directory so the
  existing A/B/C 3-way harness is unaffected.
- **go-stablenet code**: zero direct impact. SHA pinning protects against drift.

## 1.8 Risk assessment
- Race risk: low (sequential Python harness). Cross-module production risk: none.
- Historical hotspots → golden-set questions: WBFT round-change races (`c37994e9b`), justification
  forgery (`9978930ba`), zero-balance gov_council alloc (`3eada119e`), gasprice tip env refresh (`98f05c2a0`).
- Golden-set staleness: SHA pin + live `find_symbol` re-resolution + drift flag before scoring.
- Hallucination ambiguity: require AI responses in a strict JSON envelope
  `{answer, citations: [{file, start_line, end_line, symbol?}]}`. Citations graded via stablenet-knowledge;
  unparseable / failing-find_symbol → hallucination.
- "정보량" = AI **input** tokens (M1/M2/M4 single-shot; M3 summed across turns).
- Method 2 scale: bound to modules-of-interest; `max_total=2000` per seed × 4 seeds ≈ <50k tokens.

## 1.9 Open questions (carried to PLANNING)
1. Home: `.stablenet-expert/bench/ckg-bench/` (recommended).
2. Manifest: new Q&A manifest schema (different unit-of-measurement than end-to-end pipelines).
3. AI client: pluggable `Driver` protocol — `claude-cli` impl for live; `replay-fixture` for CI determinism.
4. Entry point: Python CLI now; optional `/coding-agent:ckg-bench` slash wrapper later.
5. 20 new golden-set questions: 11 invariant-anchored (invariants 1..11) + 6 hotspot + 3 cherry-pick boundary.
