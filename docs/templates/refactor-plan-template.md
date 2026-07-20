# NN — `<repo>` Refactor: Detailed Design + Implementation Plan (TEMPLATE)

> **Date authored: when this plan was written** · **Derives from:** the
> per-repo spec (`NN-<repo>-refactor.md`) and `00-system-contract.md`
> sections that define the cross-repo contracts this plan touches.
> **Repo:** `github.com/<org>/<repo>` at `<absolute local path>` (`go X.Y.Z`,
> HEAD `<short SHA>`).
> **Isolation:** state whether this plan is implementable in a single
> isolated session against this repo alone, and what blocks it if not.
> **Dependency note:** what this repo's `pkg/` surface (or other artifact)
> publishes that consumers in OTHER repos need to compile / run, and which
> shipping artifacts from OTHER repos this repo's build needs first.

> **⚠️ Major finding up front (read before estimating):** flag any case
> where the per-repo spec's evidence is stale or where this plan changes
> the per-repo spec's scope. The reader who skips this risks estimating
> against the old spec.

---

## Part A — Detailed Design

For each gap or change item the per-repo spec identifies, write:

### G<N> — `<short name>` (status: already-landed | remaining | stale | net-new)

**Current state:** evidence in the live code that supports the
classification. Include `path:line` citations. Grep-confirm every claim.

**Target design:** the minimum change that closes the gap. Code excerpts
preferred over prose for non-trivial mechanics. Identify the public types
or contracts the change touches.

**Notes / edge cases:** failure modes the obvious implementation misses,
backward-compat constraints, performance implications, anything that
warrants a one-line comment in the eventual PR.

Repeat per gap. Group related gaps (same file, same surface) under a
shared `### Gx+y` header when sensible.

---

## Part B — Cross-Module Boundary

> **Why this section exists.** Per-repo plans describe their side of each
> contract correctly. The R1' 2026-06-07 integration build surfaced THREE
> cross-module data-flow defects that no per-repo plan named (see
> `06-integration-verification.md` §4.2 and `09-alignment-deep-dive.md` §1).
> Each cost ~30 min to fix once identified; ~5h of integration debugging
> to identify. This section forces the writer to read the consumer's
> code while planning the producer's change — the cheapest preventive
> review available.

### B.1 Boundary inventory

For every external boundary this plan's repo crosses, list:

| Contract surface | Producer | Consumer | Worked example |
|---|---|---|---|
| `<type or YAML shape>` | `<this-repo>` (`<file:line>`) | `<other-repo>` (`<file:line>`) | one concrete value flowing end-to-end |

The "worked example" cell is load-bearing. Write the actual JSON / YAML /
Go literal that will flow on a representative call. The defect class this
section catches is "field name agrees, value shape disagrees" (#3 in
09 §1), which prose alone hides.

### B.2 Failure modes if mis-shaped

For each row in B.1, write one line on what the system looks like when
producer and consumer disagree:

- **Silent zero / empty result** (most common — no exception, no log line,
  just bad retrieval scores). Examples from the 2026-06-07 session:
  - `chunks.ckg_node_id = ""` for every row when `--ckg` flag wasn't
    threaded into the builder (defect #1).
  - `governed_by_edges = 0` when `governs[]` carried bare symbols but
    ckg expected `package.symbol` (defect #3).
- **Type mismatch at compile time** — caught by `go build`, not a runtime
  defect; cheap.
- **Schema rejection at load time** — caught by the consumer's validator
  (e.g. cks `inventory-check`); cheap if a validator exists, expensive
  if not.

If any row's failure mode is "silent", the test plan in Part C MUST
include an integration test that observes the value flowing end-to-end
under realistic load. A unit test on either side will not detect a
silent-zero defect.

### B.3 Consumer code path read

For each row in B.1, paste a 5–10 line excerpt of the consumer code that
reads this contract. Annotate where the value is consumed. This proves
the plan writer actually read the other side, not just the producer's
docs.

---

## Part C — Implementation Plan (ordered, test-gated)

> Ordering keeps the repo compiling at every commit. Verification-only
> steps come first (they're zero-risk and prove the "already landed"
> claims). Net-new code follows. Destructive changes (file deletion, API
> rename) last (largest blast radius).

**Step 1 — Baseline green.**
- Files: none. · Do: `go build ./... && go test ./...` to capture the
  pre-change green baseline. · Test: build exit 0. · Commit: none.

**Step 2 — `<title>`.**
- Files: `<list>`. · Do: `<one-paragraph what>`. · Test:
  `<go test ./pkg/X -run TestY>`. · Commit:
  `"<conventional commit message>"`.

Repeat. Each step is a single commit, scoped to one logical change,
gated by a runnable test.

**Cross-module integration step (required when Part B is non-trivial):**
- Files: a smoke test that exercises the boundary end-to-end with real
  data shapes. For an MCP boundary: spin up the server, send a real
  JSON-RPC call, parse the result. For a YAML boundary: write the
  YAML, run the consumer's loader against it. · Do: assert the
  worked-example value from B.1 flows through correctly. · Test:
  `<runnable>`. · Commit: `"<conventional message>"`.

---

## Part D — Verification & Acceptance

**Full-repo gate (run before "done"):**

```
go build ./...
go test ./...
go vet ./...
golangci-lint run ./...        # if .golangci.yml present
<repo-specific check>
```

**Per-spec acceptance (`<NN-…-refactor.md>` §M2) → command map:**

| Acceptance clause | Proof command |
|---|---|
| (a) ... | `<runnable>` |
| (b) ... | `<runnable>` |

**Cross-module acceptance (matching Part B rows):**

| Boundary surface | Proof — value flows end-to-end |
|---|---|
| `<type or YAML>` | `<runnable: producer → consumer; assert worked-example value>` |

---

## Part E — Risks / Unknowns

Number each risk. For each:

1. **<short title>** (confidence: HIGH | MID | LOW). One paragraph on
   the risk, with `path:line` evidence where applicable. End with a
   one-line mitigation or "flagged for human confirm at Step <N>."

Risks classified MID or HIGH must have either a mitigation step in
Part C or an explicit human-confirm gate in Part D.

---

### Fact-based summary

**Fact (None-label, code-verified):** every load-bearing claim grep- or
read-verified against HEAD. Cite `path:line`. The reader can confirm
each fact in under 30 seconds without re-running the analysis.

**Opinion — High:** the load-bearing design judgments — usually 1–3
sentences. State the position, not the rationale (rationale lives in
Part A).

**Opinion — Mid / Low:** ambiguities, choices made under uncertainty,
items the author would revisit if the integration evaluation surfaces
new data.

---

## Template-usage notes (delete before committing the real plan)

- **Tone:** plans/01–plans/05 in this directory establish the house tone.
  Match it: dense, concrete, grep-verified, no marketing language.
- **Cross-module section (Part B) is required.** If you genuinely
  cannot identify a boundary, write "no external contract — pure
  internal refactor" and explain why. Empty Part B is a warning sign.
- **Worked examples are load-bearing.** "Producer emits a Symbol field"
  is not a contract spec; `Symbol = "params.DefaultAnzeonConfig"` is.
- **Cite the per-repo spec (`NN-<repo>-refactor.md`) and `00-system-contract.md`** at the top so the reader can resolve "supersedes" claims without guessing.
- **Date the plan.** Stale plans confuse integration; the date lets a
  reader judge how aged the evidence is.
- The header banner `**⚠️ Major finding up front**` is the single most
  important place in the plan. It is where the spec-author hands the
  implementer the one fact they will skip otherwise. Use it whenever
  the live code diverges from the per-repo spec by ≥10%.
