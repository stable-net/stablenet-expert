# 05 — coding-agent Refactor

> **Derives from:** `00-system-contract.md` (C1, C5, §4.3, §5). **Repo:** `github.com/0xmhha/coding-agent` (Claude Code plugin + Go MCP sub-tools).
> **Role in R1′:** the orchestrator/consumer. Owns retrieval **control** (when/what to retrieve, sufficiency, follow-ups) and all LLM work. Depends on `03` (real cks) + `04` (chainbench names).
> **Isolatable:** Yes — only consumes the C1 surface frozen in `00`.

> **⚠ Superseded by `plans/05-coding-agent-plan.md` (live-code, authoritative).** Live-code corrections: (1) **Nothing here is landed** — all of G1–G6 remain. (2) **S6 is under-stated:** the implementer does **not** build a binary (`implementer.md:167` = `go build ./...`); the evaluator self-builds at `{workspace}/logs/gstable` (`evaluator.md:278`), not `build/bin/gstable` — so the handoff is a real new change, and the plan picks the design (evaluator-builds is the live reality). (3) **SSoT schema:** coding-agent authors the one canonical `contract/agent-mcp.schema.json` (13 cks + 7 chainbench + 6 jira) + `contract/lint-tool-names.sh`; cks/chainbench only validate against it. (4) **`profile:"default"`** (no go-stablenet profile). (5) **SETUP wholesale stale** (documents the shim + `nomic-embed-text`). (6) Steps are **blocked on `03` (real cks) + `04` D1** shipping. Use the plan for execution.

## 1. Contract this repo must satisfy

- **Consumes (C1):** the agent-facing tools of cks (`cks.context.*`/`cks.ops.*`), chainbench (actual names), jira (6). No direct access to ckv/ckg/chainbench internals.
- **Owns (C5):** the `.coding-agent/tickets/{JIRA-ID}_{YYYYMMDD_HHMMSS}/` artifact + state convention — **keep as-is** (well-designed; it is the trace sink, `00` §8).

## 2. Load-bearing changes

| ID | Change | Evidence | Action |
|---|---|---|---|
| **G1** | Plugin uses its **own cks shim** (`tools/cks-mcp`, 5 tools `ckv_search`/`ckg_query`/…), not the real cks (11+ dotted tools) | `plugin/.mcp.json` → `tools/cks-mcp/bin/cks-server` | **Delete `tools/cks-mcp`.** Point `.mcp.json` `cks` server at the real `code-knowledge-system` cks-mcp binary. **(M3)** Remove the `./tools/cks-mcp` member from `go.work`. |
| **G2** | Agent prompts call shim tool names | planner.md §3.2/§3.4/§3.5, evaluator.md | Rename to C1: `ckv_search`→`cks.context.semantic_search`; `ckg_query`→`cks.context.get_subgraph`/`find_callers`; `ckg_impact`→`cks.context.impact_analysis`; **add `cks.context.concurrency_impact` for the stage-7 concurrency-impact step (S1)**; **add `cks.ops.index` (incremental) after a `cks.ops.freshness` stale result (S2)**; `change_history` as needed. |
| **G3** | chainbench not registered; evaluator expects non-existent `chainbench_setup`/`run_tests` | `.mcp.json`, evaluator.md §7.0 | Register chainbench MCP in `.mcp.json`; update evaluator to actual names (`chainbench_init`/`test_run`/`report` per `04` G1). |
| **G4** | Non-standard model IDs `opus-4.7`/`sonnet-4.6` may fail dispatch | `plugin/agents/*.md` frontmatter, F-5 | Fix to valid GA model IDs (correct `claude-…` format). |

## 3. Domain knowledge — `00` §4

| ID | Change | Evidence | Action |
|---|---|---|---|
| **G5** | `stablenet-context` skill is **net-negative**: stale contract names (`GovStaking`/`GovConfig`/`GovNCP` vs actual `gov_council`/`gov_minter`/`gov_validator`), assumes WEMIX staking, no byzantine-fairness | deep-dive D-c | **Deprecate/rewrite:** replace static content with a pointer to cks domain entries + live cks retrieval. Remove the duplicated `consensus/**` guidance (ckv `policy.yaml` is the SSoT view). |
| **G6** | No always-on backstop for critical invariants (`00` §4.3 L3) | — | Add session-start injection (~500 tokens) of the 3–5 top invariants (e.g. "all StableNet validators have equal power=1; epoch-length changes affect diligence asymmetrically; round-change does not change proposer-share accounting"). Place in a session-loaded doc. |

## 4. Retrieval control (the agent's job) — `00` §2.3

- The `planner` already does staged retrieval (semantic → graph → impact). Keep this **agent-owned loop**; it is the "control" layer. After G2, it calls cks primitives + `cks.context.get_for_task` for the one-shot composed path, and decides whether follow-ups are needed.
- **Stage-7 retrieval (S1/S2):** for any consensus/txpool/systemcontracts target the planner must call `cks.context.concurrency_impact` (modules affected via goroutine/channel/lock) in addition to `impact_analysis` (call-graph). Before analysis, if `cks.ops.freshness` reports stale, call `cks.ops.index{mode:"incremental"}` first so retrieval reflects the current tree.
- **Un-indexed-diff loop (stage 12):** on a chainbench failure, the fix lives in the working branch (not in the cks index). The planner (bugfix mode) must combine `git diff` of the branch + cks retrieval of surrounding indexed code + the failure log, and let the session LLM reason. (cks does not index uncommitted code — `00` §C3.)

## 5. LLM-based evaluation home — `00` §5

- The `evaluator` agent is the home for LLM-based quality eval. The deterministic chainbench report is parsed here (`summary.failed`); the LLM judgement of *why* and *what to fix* stays here.
- **Binary handoff (S6):** the `implementer` agent's build step must produce the modified go-stablenet binary at `build/bin/gstable` (record the commit/branch in `state.json`). The `evaluator` reads that path and passes it as `chainbench_init{binary_path}`. Make this explicit in `implementer.md` (build → emit artifact path) and `evaluator.md` (consume artifact path) so the chainbench stage (`04` C4) never runs against a stale or default binary.
- Extend the same pattern for retrieval-quality eval (the validation spike `00` §9 is driven from here against the cks MCP).

## 6. Work order (this repo)

1. G1 (delete shim, point at real cks) + G2 (rename tool calls) — must follow `03` shipping real cks.
2. G3 (register chainbench, fix evaluator names) — must follow `04` G1.
3. G4 (model IDs).
4. G5 (deprecate/rewrite stablenet-context) + G6 (L3 injection).
5. **SETUP (S5):** document in `docs/SETUP.md` that cks-mcp requires a running Ollama daemon with `bge-m3` pulled; describe the degraded (Smart Dummy) fallback and how `cks.ops.health` surfaces it. Add the chainbench MCP launch command + build step.

**Acceptance (M2) — done when:** (a) `tools/cks-mcp` is gone, `go.work` updated, `.mcp.json` points at the real cks + chainbench, all tool names match the SSoT schema (pre-flight lint passes); (b) planner emits `concurrency_impact` calls for consensus/systemcontracts tasks and `ops.index` on stale; (c) model IDs are valid GA IDs; (d) `stablenet-context` no longer injects stale contract names; L3 invariant injection present; (e) a dry-run `/work` on a sample ticket reaches EVALUATION with chainbench receiving the implementer's `build/bin/gstable`.

## 7. Out of scope / risks

- The pipeline state machine, commands, hooks, pr-sanitize, template-parse, merge logic are mature — keep. This refactor is wiring + domain-knowledge correctness, not a rewrite.
- `jira-gateway-mcp` is already C1-aligned — no change.
- Order dependency: G1/G2 are blocked on `03`; G3 on `04`. G4/G5/G6 can land independently first.
