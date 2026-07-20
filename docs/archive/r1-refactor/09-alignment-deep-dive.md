# 09 — Alignment Deep-Dive & Cross-Module Integration Patterns

> **Date:** 2026-06-08 · **Scope:** Post-mortem and design reference for the
> three R1' cross-module integration defects discovered in the 2026-06-07
> session, and the ckv→ckg alignment algorithm that resolved them. Pairs
> with `06-integration-verification.md` §4 (case-level verdict updates)
> and `00-system-contract.md` §C2 (cks ↔ ckv/ckg in-process boundary).

This document records (1) the three cross-module defects that the per-repo
plans (`plans/02-ckv-plan.md`, `plans/03-cks-plan.md`) did not foresee,
(2) the alignment algorithm that fixes the load-bearing one, and (3) the
process change recommended for future plan-level specs so that this class
of defect surfaces during planning, not at integration time.

---

## 1. The three cross-module defects (06-04 not foresaw)

All three were discovered during the 2026-06-07 integration build and
verification. None was named in `plans/02-ckv-plan.md` /
`plans/03-cks-plan.md`. Each break the R1' thesis (`00-system-contract.md`
§1) — that retrieval can beat the LLM's grep/read loop — because they
silently degrade composer accuracy.

| # | Defect | Affected modules | Surface symptom | Resolved by |
|---|---|---|---|---|
| 1 | **`ckv build --ckg <path>` was a noop** | ckv (flag), cks (consumer) | `chunks.ckg_node_id` 0 / 26,036 (0%) despite the flag being passed and `pkg/types/chunk.go` advertising "1:1 alignment when CKG path is provided" | Task #17 — new `internal/ckgalign` package (Load + 1-step Lookup) + Builder wiring |
| 2 | **`cks` composer threw away ckv chunk metadata at the boundary** | ckv (provides), cks (drops) | ckv `query.Hit.{Symbol, CKGNodeID}` were populated but `ckvclient/real.go::SemanticSearch` did not copy them onto `contract.Hit`; `extractKeywords` then fell back to `filepath.Base(file)` — losing the only signal that can disambiguate same-named symbols across packages (eight `Finalize` methods) | Task #18 — added `Symbol` / `CKGNodeID` to `contract.Hit`, ckvclient translation, stage1 keyword extraction |
| 3 | **`cks-domain-sync` emitted bare symbol names; ckg stored qualified names** | cks (emit), ckg (consume) | `governs[]` carried `DefaultAnzeonConfig` while ckg's `qualified_name` was `params.DefaultAnzeonConfig`. ckg's policy loader emitted 27 "no code node found" warnings and 0 `governed_by` edges | Task #16 / #21 — `qualifyGovernsSymbol(file, symbol)` derives the Go package name from the anchor file's directory and prepends it |

These defects share a pattern: **each per-repo spec described its side of
the boundary correctly, but the spec for the contract between repos was
missing or incomplete**. The fix in each case was a single 20–100 LOC
change once the gap was identified.

### 1.1 Defect class

All three are *cross-module data flow defects*:

- **#1 (`--ckg` noop)** — flag accepted at the boundary but not threaded
  to the consumer.
- **#2 (Hit metadata dropped)** — boundary translator (`SemanticSearch`)
  lost fields the source had populated, and the destination type
  (`contract.Hit`) did not declare slots for them.
- **#3 (qname shape mismatch)** — producer and consumer used the same
  field name (`symbol` / `qualified_name`) for syntactically different
  values (bare vs prefixed).

Each defect is invisible inside a single repo's tests. A unit test of
ckv's chunk writer cannot detect that cks's `extractKeywords` ignores
`symbol_name`. A unit test of cks's `extractKeywords` cannot fail when
ckv silently drops the field upstream. **The defects only surface when
real data flows end-to-end** — which is exactly what the 2026-06-07
integration build did for the first time.

---

## 2. The alignment algorithm (Task #17 → #31)

`internal/ckgalign` in ckv exists to populate `chunks.ckg_node_id`.
Without it, defect #2 above has nothing to consume — `Hit.CKGNodeID`
would always be empty, and composer Stage 1 could not disambiguate.

### 2.1 Index shape

`Index.byFile : map[file_path] → []Entry sorted by start_line`, where
`Entry = {ID, StartLine, EndLine}`. Pseudo nodes (`file:`, `hunk:`,
`import:` qname prefixes) and rows with empty file_path or zero
start_line are filtered at Load time. For a 256k-node go-stablenet
graph this is ~24 MB resident.

### 2.2 Four-step lookup (final form, after #31's regression fix)

For a chunk at `(file, startLine, endLine)`:

| Step | Rule | Tiebreak | Rationale |
|---|---|---|---|
| **1** | Exact `startLine == node.StartLine` | smallest range | Method body at `func` line — direct hit |
| **2** | Range containment: `node.StartLine ≤ startLine ≤ node.EndLine` | smallest range | Field/method inside an enclosing type — pick inner |
| **3** | Range overlap: `[startLine, endLine] ∩ [node.StartLine, node.EndLine] ≠ ∅` **AND overlap ≥ `MinOverlapLines` (= 2)** | smallest range | Chunk and node share substantive lines |
| **4** | Nearest non-overlapping node within `NearestTolerance` (= 5) lines | smallest gap | Go signature/body split: ckg jumps to `func ChainConfig.IsConstantinople@:1017-1019`; ckv chunk is the body `@:1020-1022`; gap = 1, matched |
| — | `""` otherwise | — | No safe match |

### 2.3 Two constants are load-bearing

- **`MinOverlapLines = 2`** — without this floor, a chunk whose closing
  line falls on the next function's signature line silently binds to
  the wrong function. We discovered this as a 16.7% accuracy regression
  on `ChainConfig.*` (30 of 36 methods bound to the NEXT method until
  the floor was added). Set to 2 because a single shared line is almost
  always the chunk's `}` meeting `func bar() {` on the same line.
- **`NearestTolerance = 5`** — covers the Go signature/body gap (1–3
  lines typical) plus a small margin. Larger values introduce false
  positives for densely packed const/var declarations.

### 2.4 What the algorithm does NOT solve

- **Sub-node binding**: ckg emits `IfStmt` / `CallSite` nodes inside a
  function (e.g.
  `params.ChainConfig.Rules#CallSite@69503`); a chunk for the
  function's body sometimes binds to the sub-node instead of the
  function node. Semantically the same, syntactically not. 3 of the
  remaining 6 `ChainConfig.*` misses are this pattern.
- **Multi-line chunks**: a single chunk spanning 50+ lines (e.g.
  `CheckConfigForkOrder@:1170-1236`) can land on a nearby unrelated
  variable when no node covers the entire span. 3 of the remaining 6.
- **ckg-missing nodes**: ckg does not parse `*_cgo.go` or asm-stub
  files (`bls12381/arithmetic_decl.go`). cks cannot fix this from its
  side; ckg parser must add build-tag handling.

### 2.5 Measured outcome (3 builds)

| Metric | Original (build #5) | 4-step (build #6) | + MinOverlapLines (build #7) |
|---|---|---|---|
| Total chunks aligned | 89.0% | 91.55% | 90.32% |
| **Symbol chunks aligned** | 91.9% | **98.4%** | **98.4%** |
| Invariant chunks aligned | 80.8% | 99.4% | 99.4% |
| File header chunks | 57.7% | 84.2% | 69.5% (intentional retreat — boundary noise) |
| **`ChainConfig.*` semantic accuracy** | (baseline) | 16.7% (regression) | **83.3%** |
| Random 100-sample `file_path` accuracy | 100% | 100% | 100% |
| Tier-2 marker recall (seeded) | n/a | 100% (10/10) | 100% (10/10) |

The 16.7% → 83.3% recovery on `ChainConfig.*` is the load-bearing
result. Without step-3's `MinOverlapLines` floor, `ckg_node_id` would
be filled but pointing at the *next* function — a worse outcome than
leaving it empty, because composer reranking would silently amplify
the wrong neighbor.

---

## 3. Process change — cross-module data flow review

The per-repo plans (`plans/01`–`plans/05`) are excellent at the level
they target (per-repo refactor steps). They are NOT structured to
catch defects that live in the seams *between* repos. The three
defects above are evidence.

### 3.1 Recommended addition to plan template

When the next per-repo plan is written, add a **"Cross-module data
flow"** section before "Implementation Plan":

```markdown
## Cross-module data flow

For each external boundary this repo crosses, list:

1. **Contract** — type name + field shapes the OTHER repo consumes.
2. **Producer side** — where this repo populates the contract.
3. **Consumer side** — where the OTHER repo reads the contract.
4. **Worked example** — one concrete value flowing end-to-end.
5. **Failure mode if mis-shaped** — what the system looks like when
   producer and consumer disagree on shape (often: silent zero / empty
   result, not a crash).
```

This forces the writer to **read the consumer's code while planning
the producer's change**, which is the cheapest way to surface the
defect class.

### 3.2 Worked examples for the three R1' defects

| Defect | Contract | Producer | Consumer | Worked value | Mis-shape failure mode |
|---|---|---|---|---|---|
| #1 `--ckg` | `Builder.Options.CKGPath` | `cmd/ckv/build.go` parses `--ckg` flag | `internal/build/builder.go::Run` loads the index | `--ckg /…/.ckg-stablenet` → 238k entries loaded → chunk emit reads from Index | flag accepted, field unset, `chunks.ckg_node_id = ""` for every row; no error |
| #2 Hit metadata | `contract.Hit{Symbol, CKGNodeID}` | `internal/ckvclient/real.go::SemanticSearch` | `internal/composer/stage1/candidates.go::extractKeywords` | ckv `query.Hit.Symbol = "Finalize"` → contract.Hit.Symbol → stage1 uses it as candidate keyword | ckvclient drops the field; stage1 falls back to file basename; same-named methods across 8 packages all matched |
| #3 `governs[]` qname | YAML string: ckg's `qualified_name` shape | `cmd/cks-domain-sync/main.go::deriveViews` writes the YAML | `internal/policy/policy.go` (ckg) resolves YAML strings against `nodes.qualified_name` | `governs: [params.DefaultAnzeonConfig]` → ckg policy loader finds the node → `EdgeGovernedBy` emitted | producer writes `DefaultAnzeonConfig`, consumer looks up `params.DefaultAnzeonConfig`; 27 'no code node found' warnings, 0 edges |

### 3.3 Add to PR review checklist

A one-line addition to the per-repo PR review template:

> **Cross-module:** Does this PR change any field, flag, or YAML
> shape that the other R1' modules read? If yes, link the consumer
> code path here.

### 3.4 Add to `00-system-contract.md`?

Consider adding a §C2.1 sub-section that enumerates every cross-repo
contract surface (cks↔ckv `pkg/ckv.Engine`, cks↔ckg `pkg/store.Reader`,
cks-domain-sync↔ckg `policy.yaml`, etc.) with a `tests/contract`
reference each. Today these are implicit; making them a first-class
table in the spec gives spec writers a checklist.

---

## 4. What this changes for the future

The three defects collectively cost ~5h of integration debugging plus
two ckv full rebuilds (~22 min each) plus one ckg full rebuild
(~1.5 min). Catching them at spec-review would have cost ~30 min.

The cross-module review section (§3.1) plus the PR checklist (§3.3) are
the cheapest preventive change. The contract-surface table (§3.4) is
optional but improves spec ergonomics.

The alignment algorithm itself (§2) is now production-ready at 98.4%
symbol coverage and 100% file_path accuracy. Further gains require
ckg-side changes (CGO/asm parsing, sub-node policy) — these are normal
parser work, not the cross-module defect class.

---

## 5. Open follow-ups (linked to 06 §4.3.1)

- **ckg parser CGO build-tag** (~61 chunks recovery; symbol alignment
  98.4 → ~99%). Out of scope for cks-side change.

  **Root cause confirmed (2026-06-08 investigation):** ckg's `buildpipe`
  drives Go indexing through `packages.Load(cfg, "./...")` followed by
  iteration over `pkg.GoFiles`. Files whose `//go:build` tags do not
  match the current environment (e.g.
  `kzg4844_ckzg_cgo.go` requiring `ckzg && cgo && !gofuzz`,
  `bls12381/arithmetic_decl.go` requiring `amd64 && (blsasm || blsadx)`,
  `signature_nocgo.go` requiring `!cgo || nacl`) are deposited into
  `pkg.IgnoredFiles` by `go/packages` and never reach `ParseFile`. The
  parser's "AST-only mode" exists as a fallback but is not exercised
  by buildpipe.

  **Possible fix (~30–50 LOC, deferred to ckg maintainer):** after the
  GoFiles loop, walk `pkg.IgnoredFiles` and call `ParseFile` AST-only.
  These nodes would carry INFERRED confidence (no `types.Info` available
  to resolve receivers / type identities) — a meaningful change to ckg's
  node graph shape that the ckg side should ratify, not cks. The cks
  alignment work is feature-complete at 98.4% symbol coverage without
  it.
- **Sub-node binding policy** in `ckgalign.Lookup` — when the smallest-
  range tiebreak picks an `IfStmt` inside a function over the function
  itself, prefer the enclosing function. Needs a node-kind hint that
  the current Index does not store; minor schema addition.
- **Multi-line chunk policy** — a chunk spanning 50+ lines with no
  node fully containing it should match by start-line proximity rather
  than range overlap. Marginal — affects 3 entries in 36 ChainConfig
  cases.

---

## 6. Fact / Opinion

| Type | Statement | Confidence |
|---|---|---|
| Fact | Three cross-module defects (#1/#2/#3) were discovered during 2026-06-07 integration build; none was identified in plans/02 or plans/03 | None |
| Fact | After Task #17 + #31, symbol alignment = 98.4%, ChainConfig.* semantic accuracy = 83.3%, random 100-sample file_path accuracy = 100% | None |
| Fact | `MinOverlapLines = 2` and `NearestTolerance = 5` are the two load-bearing constants in `Lookup` | None |
| Opinion | The cross-module defect class is the highest-ROI process improvement available — a 30-min spec-time review prevents ~5h of integration debugging | High |
| Opinion | Sub-node binding is the next solvable accuracy gain (3/6 remaining ChainConfig misses); CGO parsing is a separate ckg-side work item | Mid |
| Opinion | The alignment algorithm should not be further tuned for file_header chunks (currently 69.5%) — those are weakly semantic and the boundary-noise floor is the right trade-off | Mid |
