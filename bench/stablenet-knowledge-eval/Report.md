# CKG Retrieval Evaluation (Report v8) — 5-Way incl. Hybrid

> Test set: 30 questions across 12 go-stablenet domains (`ckg-query-testset.md`).
> Index: built from go-stablenet `dev` (`c051d50b`), scoped to the `gstable`
> build files (unused consensus engines excluded, Solidity contract sources
> included). Retrieval averaged over 3 runs; relevance/sufficiency judged by
> Sonnet over all 3 runs (450 cells, PARSE_FAIL 0, single vote). Inputs are
> keyword/sentence only; ground-truth answers are kept separate (no leakage).
>
> v8 change: a 5th method, **ε (graph-only auto-select)**, is added to isolate
> the contribution of the ckv vector layer — ε is identical to γ except its
> seed comes from ckg BM25 keyword search (no vector). This realises the
> "방식4 그래프 단독 vs 방식5 하이브리드" comparison: δ (get_for_task) is the
> ckv+ckg hybrid (방식5), ε is graph-only (방식4).

## How the test was run (methodology)

The harness (`run_retrieval.py`) drives the live cks MCP server (`cks-mcp`
binary) over stdio against the indexed go-stablenet `dev` tree. For each of the
30 questions it runs all 5 methods, 3 times, and records the surfaced file set
per cell. The deterministic scorer (`score()`) compares surfaced files to the
ground-truth `expected_files`; the LLM judge (`run_judge.py`, Sonnet) reads the
actual context each method produced and rates relevance / design-sufficiency,
plus classifies every surfaced file as answer / related / unrelated for
relevance-precision. The input to every method is the **natural-language
question only** (e.g. "제네시스에서 거버넌스 밸리데이터 컨트랙트 상태를 어떻게
초기화하는가?"); the gold identifier is never given to β/γ/δ/ε.

What each method queries (the actual cks tool calls):

| Method | 방식 | Seed (recall) | Expansion | Selection |
|--------|------|---------------|-----------|-----------|
| **α** grep | 1 | OS `grep` for keyword terms | — | top-3 files by hit-count, whole files |
| **β** graph dump | 2 | `semantic_search` k=3 (ckv) | `get_subgraph` depth=2, max=1500 per hit | node bodies ≤70k chars |
| **γ** incremental | 3 | `semantic_search` k=5 (ckv) | `find_symbol` + `get_subgraph` depth=1, max=200 | node bodies ≤40k chars |
| **ε** graph-only | 4 | `search_text` k=5 (**ckg BM25, no ckv**) | `find_symbol` + `get_subgraph` depth=1, max=200 | node bodies ≤40k chars |
| **δ** hybrid auto | 5 | `get_for_task` → composer: ckv recall+rerank → ckg BM25 seed → graph expand (RRF) | (internal) | composer budget pack |

Shared query options on β/γ/δ/ε: `exclude_tests=true` (drop test/test-support
files) and glossary `expand=true` (append concept→symbol keywords). **ε differs
from γ in exactly one place: the seed is `search_text` (ckg BM25) instead of
`semantic_search` (ckv vector).** That one substitution isolates "what does the
vector layer add?". The composer's internal BM25 seeding is untouched by the
tool-layer OR fix, so δ reflects the production hybrid.

## Metrics
- **Answer-present**: ground-truth answer file is in the surfaced set.
- **Answer-focus** (strict): (answer)/total surfaced.
- **Relevance-precision** (LLM): (answer + design-relevant)/total surfaced.
- **Design-sufficiency** (LLM): context is enough to modify/design the feature.
- **Tokens** + **Efficiency** = sufficiency / 1k tokens. **Read efficiency only
  alongside sufficiency** — a near-empty pack scores a misleadingly high ratio.
- **Test-pollution**: cells (of 90) with ≥1 test/test-support file.

## Overall comparison

| Method | Answer-present | Answer-focus | Relevance-precision | Design-sufficiency | Avg tokens | Efficiency | Test-pollution |
|--------|---------------:|-------------:|--------------------:|-------------------:|-----------:|-----------:|---------------:|
| α grep (1) | 70% | 0.266 | 0.763 | 83% | 10,829 | 7.70 | 15/90 |
| β graph dump (2) | 83% | 0.051 | 0.400 | 88% | 6,842 | 12.83 | 0/90 |
| γ incremental (3) | 93% | 0.124 | 0.458 | 87% | 4,571 | 18.96 | 0/90 |
| **ε graph-only (4)** | **30%** | 0.192 | 0.497 | **6%** | 195 | (28.45)¹ | 0/90 |
| **δ hybrid (5)** | **97%** | 0.263 | **0.652** | 86% | 4,800 | 17.82 | 0/90 |

¹ ε's efficiency is an artifact: sufficiency 6% over ~195 tokens. A near-empty
pack inflates the ratio; ε is effectively unusable, not efficient.

## Headline: the hybrid (방식5) vs graph-only (방식4)

| | ε graph-only (4) | δ hybrid (5) | Δ |
|--|---:|---:|---:|
| Answer-present | 30% | 97% | **+67pp** |
| Design-sufficiency | 6% | 86% | **+80pp** |

The spec's goal — 방식5 beats 방식4 by ≥5% — is exceeded by **+67pp
answer-present and +80pp design-sufficiency**. The ckv vector layer is what
makes domain-query retrieval work; without it, graph search alone answers 30%
of questions and is design-sufficient for only 6%.

## Why graph-only (ε) finds so few answers — root cause

ε is identical to γ except the seed is ckg BM25 (`search_text`) instead of ckv
vector. BM25 matches only when a query **token literally appears** in the code.
Per-question breakdown of the 30 (ε answer-present = 9/30 = 30%):

| Outcome | Count | Cause |
|---------|------:|-------|
| **BM25 seed returns 0 hits** | 9/30 | The NL query + glossary expansion produced no token that matches any document. Korean prose shares no tokens with Go identifiers, and the glossary only covers concepts that have an entry, so e.g. Q01/Q05/Q11–13/Q19/Q21/Q24/Q25 get an empty seed — graph expansion never even starts. |
| **Seed found, but answer not reached** | 12/30 | BM25 latched onto a *lexically* similar but wrong symbol (e.g. Q14 → `crypto/blake2b/blake2b.go`), and 1-hop graph expansion from that wrong seed never reaches the semantically-correct answer file. |
| **Answer retrieved** | 9/30 | BM25 happened to surface the right identifier — almost always because the glossary injected it (gov-validator/minter: Q17/18/22/23) or the query carried a unique literal term (Q16/27/30). |

So ε fails for two structural reasons, both of which the vector layer fixes:
1. **No semantic recall.** BM25 needs the literal token; an NL question rarely
   contains the target identifier. ckv embeds meaning, so "거버넌스 밸리데이터
   초기화" retrieves `initializeValidator` without sharing any token.
2. **Lexical seeds don't bridge to the answer.** Even when BM25 returns
   *something*, it is often the wrong symbol, and a 1-hop graph walk cannot
   cross the meaning gap. The vector seed lands on (or adjacent to) the right
   node, so the same graph expansion then works.

This is the quantified justification for the hybrid: the graph is valuable for
*expanding* around a correct anchor, but it cannot *find* that anchor from a
natural-language question — that is the vector layer's job.

## Domain-level design-sufficiency (v8)

| Domain | α(1) | β(2) | γ(3) | ε(4) | δ(5) |
|--------|--:|--:|--:|--:|--:|
| anzeon-gasprice | 100% | 100% | 100% | 0% | 100% |
| fee-delegation | 67% | 67% | 67% | 0% | 67% |
| gov-council | 100% | 100% | 100% | 0% | 100% |
| gov-minter | 100% | 100% | 100% | 33% | 100% |
| gov-validator | 100% | 100% | 100% | 0% | 100% |
| native-manager | 50% | 50% | 0% | 0% | 50% |
| wbft-finalize | 50% | 100% | 100% | 0% | 100% |
| wbft-header | 100% | 100% | 100% | 0% | 100% |
| wbft-justification | 100% | 100% | 100% | 0% | 100% |
| wbft-prepare-commit | 100% | 78% | 100% | 22% | 100% |
| wbft-roundchange | 100% | 100% | 100% | 0% | 100% |
| wbft-seal | 67% | 67% | 100% | 0% | 56% |
| wbft-validator | 67% | 100% | 67% | 0% | 67% |

ε is design-sufficient in only 2 of 13 domains (gov-minter 33%, prepare-commit
22%) — exactly the domains where the glossary injects the answer identifier.

## Findings
1. **Hybrid (δ, 방식5) is the production choice** — 97% answer-present, 86%
   sufficiency, 0 pollution, 4,800 tokens.
2. **The vector layer is essential, not incremental** — removing it (ε) drops
   answer-present 97%→30% and sufficiency 86%→6%.
3. **γ (vector-seeded incremental) rivals δ** — 93%/87% at 4,571 tokens (best
   efficiency among usable methods, 18.96).
4. **Efficiency must be read with sufficiency** — ε's 28.45 is a near-empty-pack
   artifact, not a win.

## Limitations
- ε is the floor by construction (no vector); its purpose is to quantify the
  vector contribution, not to be a viable mode.
- All cross-language coverage here is Go↔Solidity (no TypeScript in the build);
  a dedicated cross-language question set and an RRF-weight sweep are the next
  steps (not in this report).
- Domain rows use 1–3 questions each (trend only). Retrieval over 3 runs; judged
  over all 3 runs (90 cells/method), single vote.
