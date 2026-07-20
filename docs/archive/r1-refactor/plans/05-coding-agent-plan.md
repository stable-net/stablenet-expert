# 05 — coding-agent Refactor: Detailed Design + Implementation Plan

> **Derives from:** `00-system-contract.md` (C1 incl. NEW `cks.context.concurrency_impact` + `cks.ops.index`; C5; §4.3 L3 injection; §5; the S4 SSoT schema file `coding-agent/contract/agent-mcp.schema.json`) + `05-coding-agent-refactor.md` (G1–G6, retrieval control, binary handoff, M2 acceptance).
> **Repo:** `github.com/0xmhha/coding-agent` at `/Users/wm-it-22-00661/Work/github/tools/coding-agent` (Claude Code plugin: markdown agents/commands/skills + Go MCP sub-tools `tools/cks-mcp`, `tools/jira-gateway-mcp`). HEAD `f0c0f38`, `go.work` go 1.25.0.
> **Role in R1′:** orchestrator/consumer. Owns retrieval **control** + all LLM work + authors the cross-cutting C1 SSoT schema file. Consumes the cks + chainbench + jira MCP surfaces.
> **Isolation:** Mostly markdown + JSON edits (no Go logic in this repo's own code beyond deleting the shim). **Dependency note (hard):** the planner/evaluator rewiring is only *testable end-to-end* after **03 ships the real cks** (real dotted tool names registered) and **04 fixes D1** (`chainbench_report{format:"json"}` returns JSON, not text). The pure-markdown edits (G4 model IDs, G5 skill, G6 L3 injection) and the SSoT schema file can land independently first.

---

## Part A — Detailed Design

### Verification verdict vs the 05 spec

Every 05 item verified against live code. **Net: nothing in 05 has already landed** — the shim is intact, all tool calls use shim names, model IDs are non-GA, the skill is stale, no L3 injection exists, no `contract/` dir exists, and (a spec gap) the **implementer does not build the binary at all** — the *evaluator* builds it at the wrong path. Details per item below.

---

### G1 — delete shim + `.mcp.json` repoint to real cks + register chainbench + `go.work` member removal

**STATUS: remaining (shim fully present).** Verified:
- `tools/cks-mcp/internal/server/server.go:31-58` registers exactly **5** shim tools: `ckv_search` (`:32`), `ckv_index` (`:39`), `ckg_query` (`:46`), `ckg_impact` (`:52`), `ckg_index` (`:58`). Package doc (`:1-2`) still says "Phase 4 will extend …". This is the removed-shim the 05 spec names.
- `plugin/.mcp.json:13-23` `cks` server points at `${CLAUDE_PLUGIN_ROOT}/../tools/cks-mcp/bin/cks-server` (the shim binary), with shim-flavored env (`CKS_INDEX_PATH`, `OLLAMA_BASE_URL`, `OLLAMA_EMBED_MODEL`, `CKS_DISABLE_OLLAMA`).
- `plugin/.mcp.json` has **no `chainbench` entry** (only `jira-gateway` + `cks`).
- `go.work:3-6` lists `./tools/jira-gateway-mcp` + `./tools/cks-mcp`.

**Target — three concrete edits:**

**(a) Delete the shim + drop the `go.work` member.**
- `rm -rf tools/cks-mcp/` (the whole tree: `cmd/server`, `internal/{ckg,ckv,filter,server,types}`, `bin/cks-server`, `go.mod`, `go.sum`).
- `go.work` (rewrite the `use` block):
  ```
  go 1.25.0

  use (
  	./tools/jira-gateway-mcp
  )
  ```
- Remove the now-orphaned shim entries from `go.work.sum` via `go work sync` (or leave — harmless; prefer `go work sync` for hygiene).

**(b) Repoint `.mcp.json` `cks` server at the real `code-knowledge-system` cks-mcp binary.** The real cks builds `cmd/cks-mcp` (per 03-plan) and is **CGO-inheriting post-G1** (sqlite-vec). It is a *sibling repo*, not vendored into coding-agent, so the command must be an absolute/env-resolved path to the real cks build, and the env must match the real cks's `CKVConfig`/`Deps` (OllamaURL + bge-m3 + index/source paths), NOT the shim's `CKS_INDEX_PATH`. Exact entry:
```json
"cks": {
  "command": "${CKS_MCP_BIN}",
  "args": [],
  "env": {
    "CKS_CONFIG":      "${CKS_CONFIG}",
    "CKS_SOURCE_ROOT": "${GO_STABLENET_ROOT}",
    "CKS_CKV_DATA":    "${CKS_CKV_DATA}",
    "CKS_CKG_DATA":    "${CKS_CKG_DATA}",
    "OLLAMA_URL":      "${OLLAMA_URL}",
    "CKS_EMBED_MODEL": "bge-m3"
  }
}
```
> **Cross-repo coupling note (resolve at edit time):** the exact env var names must match what 03's `cmd/cks-mcp/main.go` reads from `cfg`/flags. 03-plan Step 9 points cks at go-stablenet via `policies/cks.yaml.example` (config-file driven), so the *minimal* portable entry is `command: ${CKS_MCP_BIN}` + `env:{CKS_CONFIG: <path to cks.yaml>}` and let the YAML carry source/index/ollama paths. **Decision:** drive cks via a single `CKS_CONFIG` file (matches 03's config-first design); the per-var env above is the fallback if 03 exposes flags. Pin the real var names against 03's shipped `main.go` before committing (Part D #2).

**(c) Register chainbench** (entry pinned by 04-plan §G2):
```json
"chainbench": {
  "command": "chainbench-mcp",
  "env": { "CHAINBENCH_DIR": "${CHAINBENCH_DIR}" }
}
```
04-plan: the `chainbench-mcp` launcher self-resolves `CHAINBENCH_DIR` from `$HOME/.chainbench` by default, but the dev checkout is `…/tools/chainbench`, so pass `CHAINBENCH_DIR` explicitly. Prereq (document in SETUP, §Part C): `cd <chainbench>/mcp-server && npm install && npm run build` (produces `dist/index.js`) + the Go wire binary `network/chainbench-net` must be built.

Resulting `.mcp.json` has 3 servers: `jira-gateway` (unchanged), `cks` (repointed), `chainbench` (new).

---

### G2 — rename tool calls in planner / evaluator (OLD → NEW)

**STATUS: remaining.** All call sites use shim names. The planner frontmatter (`planner.md:12-14`) grants `mcp__cks__ckv_search`, `mcp__cks__ckg_query`, `mcp__cks__ckg_impact`; the body calls them at §3.2/§3.4/§3.5/§6.3. The evaluator frontmatter (`evaluator.md:13-17`) grants `chainbench_setup`/`run_tests` (non-existent) + start/status/stop; body §7 uses them.

**Precise OLD→NEW mapping table (the spine of G2):**

| Where (file:line) | OLD (shim) call | NEW (C1) call | Notes |
|---|---|---|---|
| `planner.md:12` frontmatter | `mcp__cks__ckv_search` | `mcp__cks__cks.context.semantic_search` | tool grant rename |
| `planner.md:13` frontmatter | `mcp__cks__ckg_query` | `mcp__cks__cks.context.get_subgraph`, `mcp__cks__cks.context.find_callers` | `ckg_query` split into the two C1 graph tools |
| `planner.md:14` frontmatter | `mcp__cks__ckg_impact` | `mcp__cks__cks.context.impact_analysis` | + add `mcp__cks__cks.context.concurrency_impact` (S1), `mcp__cks__cks.ops.freshness`, `mcp__cks__cks.ops.index` (S2), `mcp__cks__cks.context.change_history`, and optionally `mcp__cks__cks.context.get_for_task` (one-shot composed path) |
| `planner.md:79` §3.2 body | `mcp__cks__ckv_search(query, top_k=15, filters={package}, include_history, rerank)` | `cks.context.semantic_search(query, k=15, path_glob=<module>, language="go")` | input shape changes: `top_k`→`k`; `filters.package`→`path_glob`; drop shim-only `include_history`/`rerank` (semantic_search returns ckv hits only — history is a separate `change_history` call) |
| `planner.md:109` §3.4 body | `mcp__cks__ckg_query(symbols, depth=2, relation_types, include_history, include_concurrency)` | `cks.context.get_subgraph(symbol, depth=2, max_total)` per seed (+ `cks.context.find_callers` where caller-direction needed) | shim's batch `symbols[]`+`relation_types[]`+`include_concurrency` collapses to per-symbol `get_subgraph`; **concurrency moves to its own tool** (next row) |
| `planner.md:111-115` §3.4 `include_concurrency=true` | (folded into `ckg_query`) | `cks.context.concurrency_impact(symbol, depth=3, max_total)` **(NEW, S1)** | **stage-7 requirement:** for any seed in `consensus/**`, `core/txpool/**`, `core/state/**`, `miner/**`, `systemcontracts/**`, call `concurrency_impact` in addition to `impact_analysis`. Default `depth=3` (channel reach is one hop deeper than calls, per 03/01-plan). Persist into `related-code.json.ckg.concurrency_impact` (the evaluator reads this at `evaluator.md:117` for `-race` scope) |
| `planner.md:125` §3.5 body | `mcp__cks__ckg_impact(symbol, change_type=<logic\|signature>)` | `cks.context.impact_analysis(symbol, depth)` | drop shim-only `change_type` (C1 `impact_analysis` takes `symbol`+`depth`); the work-type→depth mapping stays agent-side (bugfix→shallower, feature→deeper) |
| `planner.md:391` §6.3 body | `mcp__cks__ckv_search(query, top_k=10)` | `cks.context.semantic_search(query, k=10)` | bugfix re-entry path |
| `planner.md:395` §6.3 body | `mcp__cks__ckg_query(symbols, depth=2, include_concurrency=true)` | `cks.context.get_subgraph(symbol, depth=2)` + `cks.context.concurrency_impact(symbol)` per affected symbol | same split |
| **NEW** before §3.4 analysis | — | `cks.ops.freshness()` → if stale, `cks.ops.index({mode:"incremental"})` **(NEW, S2)** | the in-loop staleness path the old `ckv_index`/`ckg_index` shim tools served. Add a step "3.3b Freshness gate" |
| `evaluator.md:13` frontmatter | `mcp__chainbench__chainbench_setup` | `mcp__chainbench__chainbench_init` | name fix (04-plan: `chainbench_init` exists at `lifecycle.ts:91`; `setup` never existed) |
| `evaluator.md:16` frontmatter | `mcp__chainbench__chainbench_run_tests` | `mcp__chainbench__chainbench_test_run` | name fix (04-plan: `test.ts:103`) |
| `evaluator.md:14,15,17` frontmatter | `chainbench_start`/`status`/`stop` | unchanged (names correct) | + add `mcp__chainbench__chainbench_report` (the C4 loop-back parse tool — currently absent from the grant) |
| `evaluator.md:291` §7.2 body | `chainbench_setup({binary_path, node_count:4, consensus:"wbft", genesis_config:"default"})` | `chainbench_init({profile:"default", binary_path:<path>, project_root:<go_stablenet_root>})` | **profile:"default" NOT "go-stablenet"** (04-plan D #5: no `go-stablenet.yaml` profile exists; `default.yaml` *is* the go-stablenet/`stablenet`-adapter profile). Drop `node_count`/`consensus`/`genesis_config` — those are profile-config, not init args (04-plan §G1 init input = `{profile?, project_root?, binary_path?}`) |
| `evaluator.md:354` §7.5 body | `chainbench_run_tests("standard")` | `chainbench_test_run({test:"<category/name>", format:"text"})` | 04-plan §G1: `chainbench_test_run` takes `{test:"category/name", format?}`; `"standard"` must become a real `category/name` test path (verify the chainbench test catalog at edit time; e.g. `tx/standard`) |
| **NEW** after §7.5 | — | `chainbench_report({format:"json"})` → parse `summary.failed > 0` | the C4 loop-back parse (`00` C4). **Blocked on 04 D1** — until D1 ships, `format:"json"` silently returns *text* and the parse fails. Add a §7.5b "Parse report" step that reads `summary.failed`, `summary.passed`, `summary.assertions` |

**Evaluator §7.0 pre-flight rewrite:** the existing pre-flight (`evaluator.md:258-272`) lists `expected = [chainbench_setup, …, chainbench_run_tests, …]` and on mismatch points the operator at a stale `docs/superpowers/specs/phase6-…` path. Replace `expected` with the C1 set `[chainbench_init, chainbench_start, chainbench_status, chainbench_test_run, chainbench_report, chainbench_stop]` and point the "update" instruction at `coding-agent/contract/agent-mcp.schema.json` (the new SSoT) instead of the dead spec path.

---

### G3 — register chainbench / fix evaluator names

Folded into G1(c) (`.mcp.json` registration) + the evaluator rows of the G2 table (name fixes + report parse). No separate work. The 05 spec lists G3 separately; in live code it is one `.mcp.json` edit + the evaluator markdown edits.

---

### G4 — model IDs: current → valid GA IDs

**STATUS: remaining (all 4 agents non-GA).** Verified frontmatter:
- `planner.md:3` `model: opus-4.7`
- `orchestrator.md:3` `model: opus-4.7`
- `implementer.md:3` `model: sonnet-4.6`
- `evaluator.md:3` `model: sonnet-4.6`

**Target — valid GA IDs (the `claude-…` dashed format):**

| File | OLD | NEW (proposed GA ID) |
|---|---|---|
| `planner.md:3` | `opus-4.7` | `claude-opus-4-7` |
| `orchestrator.md:3` | `opus-4.7` | `claude-opus-4-7` |
| `implementer.md:3` | `sonnet-4.6` | `claude-sonnet-4-6` |
| `evaluator.md:3` | `sonnet-4.6` | `claude-sonnet-4-6` |

> **Unknown (Part D #4):** the exact published GA aliases must be confirmed against the Claude Code model registry at edit time. The dashed `claude-<family>-<major>-<minor>` form is what `00` §6 prescribes (`opus-4.7`→`claude-opus-4-7`). If the harness requires fully-qualified dated IDs (e.g. `claude-opus-4-7-YYYYMMDD`) or a `claude-…[1m]` context suffix, use the registry value. Keep the *role→family* mapping fixed (planner/orchestrator = opus = deep reasoning; implementer/evaluator = sonnet = throughput), consistent with the user's model-routing rule.

---

### G5 — `stablenet-context` skill: deprecate / rewrite

**STATUS: remaining (stale content live).** Verified `skills/stablenet-context/SKILL.md`:
- `:24` System contracts row: `GovStaking, GovConfig, GovNCP, GovRewardeeImp` — the stale WEMIX-governance names (`00` §4.1 actual = `gov_council`/`gov_minter`/`gov_validator`).
- `:38`, `:71-74` repeat `GovStaking`/`GovConfig`/`GovNCP`/`GovRewardee` in the module table + symbol-classification rules.
- The whole skill (295 lines) duplicates `consensus/**` guidance that `00` §4.1 says is owned by ckv `policy/stablenet.yaml` (the SSoT runtime view) — net-negative duplication + drift.
- It is granted to the planner (`planner.md:18`) and called at `planner.md:92,95,99` (`classify_domain`, `estimate_complexity`).

**Target — rewrite to a thin pointer (deprecate the static knowledge):**
1. Replace `SKILL.md` body with a ~40-line pointer skill: (a) state it is deprecated as a knowledge source; (b) instruct the planner that domain classification + invariants now come from **live cks retrieval** (`cks.context.get_for_task` returns `guidance.watch_out`/`also_review`/`required_tests` injected from ckv `policy/stablenet.yaml`, `00` §4.1) and from the **cks domain entries** (`code-knowledge-system/docs/domain-knowledge/projects/go-stablenet/entries/*.yaml`); (c) keep ONLY the lightweight, non-drifting `file_path → module` mapping (§2.2 rules) as a deterministic helper, because that is path-based, not contract-name-based, and does not rot. **Remove every `GovStaking`/`GovConfig`/`GovNCP`/`GovRewardee` literal** (the symbol-classification rows `:71-74` and the system-contracts row `:24`,`:38`).
2. Keep the two function signatures the planner calls (`classify_domain`, `estimate_complexity`) so `planner.md:92-103` does not break — but reimplement them as "classify by path + defer domain-knowledge to cks retrieval," not as a static lookup table.
3. **Cross-edit planner §3.3** (`planner.md:90-103`): keep the `classify_domain`/`estimate_complexity` calls (now thin), and add a sentence that authoritative domain guidance comes from the cks `get_for_task`/`semantic_search` `guidance` fields, not this skill.

Alternative (cleaner but larger blast radius): delete the skill entirely and inline path-classification into the planner. **Decision: rewrite to pointer** — preserves the planner's call sites, minimal churn, satisfies G5 ("replace static content with a pointer + live retrieval").

---

### G6 — L3 session-start invariant injection (`00` §4.3 L3)

**STATUS: remaining (no L3 backstop exists; grep for `INVARIANT`/`backstop`/session injection → 0 hits in plugin).**

`00` §4.3 L3 = an always-on ~500-token injection of the 3–5 highest-priority byzantine-fairness invariants, present regardless of retrieval quality.

**Where it lives — decision:** Claude Code plugins have no guaranteed `SessionStart` hook that injects context into every agent (the live `hooks.json` only wires `PostToolUse` for `Agent`/`Bash`). The reliable injection point is **a session-loaded doc referenced by the agents that need it**. Two-part placement:
1. **Author `plugin/skills/stablenet-invariants/SKILL.md`** (or reuse the rewritten `stablenet-context` as the carrier) holding the ~500-token invariant block. A skill body is loaded when the agent lists it under `skills:` — deterministic, no hook needed.
2. **Grant it to `planner` and `evaluator`** (`planner.md:15-18` skills list; `evaluator.md:18-19` skills list) so both the design phase and the verification phase always see the invariants. The planner uses them to avoid Ethereum-assuming designs; the evaluator uses them to judge byzantine-fairness of the diff.

**The ~500-token content (the 3–5 top invariants, from `00` §4.3 L3 + §4.2):**
```
# StableNet Critical Invariants (always-on backstop — L3)

These hold for go-stablenet regardless of what retrieval surfaces. Violating
any is a byzantine-fairness or consensus-safety bug, even if tests pass.

1. EQUAL POWER. All StableNet validators have voting power = 1 (PoA equal-power,
   NOT WEMIX stake-weighted). Never introduce stake-weighted voting, reward, or
   quorum math. Quorum = ⌈N − (N−1)/3⌉ over equal-power validators.

2. EPOCH-LENGTH ASYMMETRY. Changing epoch length affects diligence/accounting
   ASYMMETRICALLY across validators. An epoch-length change is a byzantine-
   fairness change — require explicit fairness analysis, not just a constant edit.

3. ROUND-CHANGE NEUTRALITY. A round change (proposer rotation on timeout) must
   NOT alter proposer-share or reward accounting. Round changes are liveness
   mechanics, not economic events.

4. QUORUM FLOAT SAFETY. Quorum/threshold math must stay integer/⌈⌉-exact. No
   float comparison for quorum — float precision can flip a vote outcome.

5. STICKY-PROPOSER CONCENTRATION. Sticky proposer policy concentrates proposal
   rights; any change to proposer selection must preserve long-run fairness
   across the validator set (RoundRobin vs Sticky have different fairness
   profiles).

Consensus engine = WBFT (QBFT-family, istanbul RPC namespace). System contracts
are gov_council / gov_minter / gov_validator (NOT GovStaking/GovConfig/GovNCP).
```
(~480 tokens; trim to fit the 500 budget. Source the exact numbers from the cks `verified` entries once `00` §4.2 curation lands — until then this hardcoded block is the backstop, which is exactly L3's purpose: it does not depend on the index.)

---

### Binary handoff (S6) — implementer build → `build/bin/gstable`; evaluator reads it

**STATUS: remaining + a spec-gap surprise.** `05` S6 assumes the *implementer* builds the binary and the *evaluator* consumes the path. **Live reality:**
- The implementer does **NOT build a binary**. `implementer.md:167` runs only `go build ./...` (compile check, no `-o`), per step. There is no `build/bin/gstable` emission anywhere in `implementer.md` (grep confirmed: only the evaluator + the skill reference `gstable`).
- The **evaluator** builds it itself, at the wrong path: `evaluator.md:278` `go build -o {workspace_dir}/logs/gstable ./cmd/gstable`, then passes `binary_path: "{workspace_dir}/logs/gstable"` to the (renamed) init at `:292`.

So the S6 "implementer emits, evaluator consumes" contract is **not implemented** — the evaluator self-builds. Two coherent fixes:
- **(A, matches `05` S6 literally)** Move the build to the implementer: add a `## 6.1 Build artifact` step to `implementer.md` after "all steps complete" (`implementer.md:277-287`) that runs `go build -o {go_stablenet_root}/build/bin/gstable ./cmd/gstable`, and records `states.IMPLEMENTATION.binary_path` + `binary_commit` (the HEAD SHA) + `branch` into `state.json`. The evaluator §7.1 then *reads* `states.IMPLEMENTATION.binary_path` instead of self-building, and passes it to `chainbench_init{binary_path}`.
- **(B)** Keep the evaluator self-building but standardize the path to `build/bin/gstable` (the `00` C4 convention) and record it in `state.json`.

**Decision: (A).** It satisfies `05` S6 exactly ("implementer.md build step → `build/bin/gstable`; evaluator reads that path"), records the commit/branch in `state.json` for traceability (`00` C5 trace sink), and means the evaluator never builds against a stale tree. Concrete edits:
- `implementer.md` §6: add build-artifact emission to `{go_stablenet_root}/build/bin/gstable` + write `state.json.states.IMPLEMENTATION.{binary_path, binary_commit, branch}`. Keep the existing per-step `go build ./...` compile checks.
- `evaluator.md` §7.1: replace the `go build -o …/logs/gstable` block with "read `states.IMPLEMENTATION.binary_path` from `state.json`; if absent or stale (commit ≠ current HEAD), fall back to building `build/bin/gstable` and warn." This keeps the evaluator robust but prefers the implementer's artifact.
- `evaluator.md` §7.2: `chainbench_init({..., binary_path: <binary_path from state.json>})`.
- `evaluator.md` §7.6 cleanup: the `pgrep -f 'gstable'` kill is now redundant with 04's pids.json-basename stop (04 G3), but keep it as a defensive backstop — note it only matches `gstable`, so a renamed PR binary leak is handled by chainbench's own stop path (04 M2.b).

---

### SSoT schema authoring (S4) — `coding-agent/contract/agent-mcp.schema.json`

**STATUS: missing entirely.** Verified: no `contract/` dir, no schema file anywhere in the repo (`find . -iname 'SETUP*'`/dir survey confirm). `00` S4 names this repo as the **owner of record** ("the consumer of record"). 03-plan Step 6 and 04-plan Step 2 both need it to exist for their conformance tests; **03-plan #7 flags it must be authored — and proposes 03 author it.** This creates an ownership question (Part D #1).

**Decision: this (05) session authors the canonical file** at `coding-agent/contract/agent-mcp.schema.json`, because `00` S4 assigns ownership here and the agent prompts in *this* repo are linted against it. If 03 ships first and stubs the file for its golden test, this session reconciles to the canonical version (they must be byte-identical — it is one SSoT). Coordinate so only one authoritative copy exists.

**Design — language-neutral JSON Schema, structure:**
```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/0xmhha/coding-agent/contract/agent-mcp.schema.json",
  "title": "R1' Agent-facing MCP Contract (C1 SSoT)",
  "description": "Single source of truth for every tool the coding-agent calls. Providers: cks, chainbench, jira-gateway. ckv/ckg are dev-only and NOT in this contract.",
  "definitions": {
    "Citation": { "type":"object", "properties": { "file":{"type":"string"}, "start_line":{"type":"integer"}, "end_line":{"type":"integer"} }, "required":["file"] },
    "PRRef":    { "type":"object", "properties": { "number":{"type":"integer"}, "title":{"type":"string"}, "merged_at":{"type":"string"} } }
  },
  "providers": {
    "cks":        { "namespace":"cks.", "tools": { /* 13 tools */ } },
    "chainbench": { "namespace":"chainbench_", "tools": { /* 7-tool evaluator subset */ } },
    "jira":       { "namespace":"jira_", "tools": { /* 6 tools */ } }
  }
}
```
Each `tools` entry: `{ "name", "input": <JSON Schema>, "output": <JSON Schema>, "owner": "<provider>" }`.

**The cks 13 tools (the 11 live in 03 + 2 NEW)** — names + key input from `00` C1:
`cks.context.get_for_task`(prompt, +budget/depth/`max_citations`), `cks.context.semantic_search`(query, k, language, path_glob, kinds), `cks.context.search_text`(query, k, language, path_glob), `cks.context.find_symbol`(name, language, kinds), `cks.context.find_callers`/`find_callees`/`get_subgraph`(symbol, depth, max_total), `cks.context.impact_analysis`(symbol, depth), **`cks.context.concurrency_impact`(symbol, depth, max_total) [NEW S1]**, `cks.context.change_history`(intent|symbol, k, max_count), `cks.ops.health`(), `cks.ops.freshness`(), **`cks.ops.index`(mode, since_commit) [NEW S2]**.

**The chainbench evaluator subset (7, from 04-plan §G1):** `chainbench_init`(profile?, project_root?, binary_path?), `chainbench_start`(project_root?, binary_path?), `chainbench_status`(network?), `chainbench_test_run`(test, format?), `chainbench_report`(format?) — **output = the C4 report shape** `{summary:{total_tests,passed,failed,assertions:{passed,failed}}, tests:[{status,...}]}`, `chainbench_failure_context`(), `chainbench_stop`().

**The jira 6 (unchanged, `00` C1):** `jira_read_ticket`, `jira_read_comments`, `jira_search`, `jira_add_comment`, `jira_update_status`, `jira_update_assignee`.

**How providers validate against it (the S4 conformance mechanism):**
- **cks (Go golden test):** `code-knowledge-system/internal/mcp/schema_golden_test.go` (03-plan Step 6) boots the server, enumerates registered `cks.*` tool names, asserts the set == the schema's `providers.cks.tools` keys (no drift, no extras), and optionally validates each tool's input schema against the SSoT. Reads the file from a known relative/abs path (sibling-repo path or a vendored copy — pin in 03).
- **chainbench (vitest):** `mcp-server/test/contract.test.ts` (04-plan Step 2) instantiates the `McpServer`, asserts the registered set ⊇ the 7-tool subset and that each input shape matches `providers.chainbench`. 04 ships a `mcp-server/test/fixtures/agent-subset.schema.json` *fragment* that must be a subset-consistent slice of this SSoT.
- **coding-agent (pre-flight lint):** a tool-name drift check (a small script or a CI grep) that every `mcp__cks__cks.*` / `mcp__chainbench__chainbench_*` / `mcp__jira-gateway__jira_*` reference in `plugin/agents/*.md` + `plugin/commands/*.md` corresponds to a name present in the schema. This is the M2.a "pre-flight lint passes" gate. Implement as `contract/lint-tool-names.sh` (greps the agent/command markdown for `mcp__…__…` tokens, diffs against the schema's tool name set).

---

## Part B — Implementation Plan (ordered, test-gated)

> Order: land the **independent** items first (G4, G5, G6, the SSoT schema + lint) — they need neither 03 nor 04. Then the **03-blocked** rewiring (G1 cks repoint + G2 planner). Then the **04-blocked** rewiring (G1 chainbench register + G2 evaluator + report parse). Binary handoff (S6) is markdown-only and can land early but is only *exercised* once 04 is up. Each step keeps the plugin loadable (no broken frontmatter / no dangling skill grants).

**Step 0 — Baseline.** Files: none. Action: confirm plugin loads today (`jira-gateway`+`cks` connect via shim), capture `git status`. Test: `gh`/Claude Code lists the 2 current MCP servers. Commit: none. **Not blocked.**

**Step 1 — SSoT schema + pre-flight lint (S4, M2.a).** Files: `contract/agent-mcp.schema.json` (NEW, 13 cks + 7 chainbench + 6 jira), `contract/lint-tool-names.sh` (NEW). Action: author the schema per Part A S4; write the lint script that greps `plugin/agents/*.md` + `plugin/commands/*.md` for `mcp__…` tokens and asserts each is in the schema. Test (schema-lint): `bash contract/lint-tool-names.sh` — at this point it will REPORT drift (agents still use shim/old names) → that is the expected RED that Steps 6–8 turn GREEN. Run it as `--report-only` here. Commit: "feat(contract): author C1 SSoT agent-mcp.schema.json + tool-name lint (M2.a, S4)". **Not blocked.**

**Step 2 — G4 model IDs.** Files: `planner.md:3`, `orchestrator.md:3`, `implementer.md:3`, `evaluator.md:3`. Action: opus-4.7→`claude-opus-4-7`, sonnet-4.6→`claude-sonnet-4-6` (confirm exact GA aliases, Part D #4). Test: plugin frontmatter parses; a dry `/work` dispatch resolves each agent's model without "unknown model" error. Commit: "fix(agents): valid GA model IDs (G4)". **Not blocked.**

**Step 3 — G5 stablenet-context rewrite + planner §3.3 cross-edit.** Files: `skills/stablenet-context/SKILL.md` (rewrite to pointer; remove all `GovStaking/GovConfig/GovNCP/GovRewardee`), `planner.md:90-103`. Action: per Part A G5. Test: grep `GovStaking\|GovConfig\|GovNCP\|GovRewardee` across `skills/` + `plugin/` → 0 hits (M2.d); planner still grants/calls `classify_domain`/`estimate_complexity`. Commit: "refactor(skill): deprecate stablenet-context to live-retrieval pointer; drop stale gov names (G5)". **Not blocked.**

**Step 4 — G6 L3 invariant injection.** Files: `skills/stablenet-invariants/SKILL.md` (NEW, ~500 tokens per Part A G6), `planner.md:15-18` (add to skills), `evaluator.md:18-19` (add to skills). Action: author the invariant block; grant to both agents. Test: both agents' skills lists include `stablenet-invariants`; the block is ≤500 tokens and names equal-power/epoch-asymmetry/round-change. Commit: "feat(domain): add always-on L3 invariant backstop skill (G6, 00 §4.3)". **Not blocked.**

**Step 5 — S6 binary handoff (implementer emits, evaluator reads).** Files: `implementer.md` §6 (add build→`build/bin/gstable` + state.json `binary_path/binary_commit/branch`), `evaluator.md` §7.1/§7.2 (read `state.json.binary_path`, fallback-build, feed to init). Action: per Part A S6 decision (A). Test: a dry-run trace shows the implementer writes `binary_path`; the evaluator reads it. (Full exercise blocked on 04 — chainbench must accept the path.) Commit: "feat(handoff): implementer emits build/bin/gstable; evaluator consumes via state.json (S6)". **Markdown-only; not blocked, but E2E-gated on 04.**

**Step 6 — G1 cks repoint + go.work + shim delete. [BLOCKED ON 03]** Files: `rm -rf tools/cks-mcp/`, `go.work`, `go.work.sum` (`go work sync`), `plugin/.mcp.json` (`cks` entry). Action: per Part A G1(a)(b). **Gate:** verify the real cks-mcp binary exists + its env/config var names (Part D #2) before editing `.mcp.json`. Test: `go work sync` clean; plugin loads; `cks` MCP connects to the *real* cks (`cks.ops.health` responds). Commit: "feat(mcp): delete cks shim, repoint .mcp.json at real cks, drop go.work member (G1)". **Blocked on 03 shipping real cks.**

**Step 7 — G2 planner rewiring. [BLOCKED ON 03]** Files: `planner.md` (frontmatter `:12-14` + body `:79,109,111-115,125,391,395` + new §3.3b freshness gate). Action: apply the G2 table's cks rows + add `concurrency_impact` for stage-7 modules + `ops.freshness`→`ops.index` gate. Test (pre-flight): `bash contract/lint-tool-names.sh` now passes for the `cks.*` rows; a dry-run `/work` reaches PLANNING with `related-code.json.ckg.concurrency_impact` populated for a consensus ticket. Commit: "feat(planner): rewire to C1 cks tools + concurrency_impact + freshness/index gate (G2, S1, S2)". **Blocked on 03.**

**Step 8 — G1(c) chainbench register + G2 evaluator rewiring. [BLOCKED ON 04]** Files: `plugin/.mcp.json` (add `chainbench`), `evaluator.md` (frontmatter `:13-17` + §7.0 pre-flight + §7.2 init + §7.5 test_run + new §7.5b report parse). Action: per Part A G1(c) + the G2 evaluator rows (incl. `profile:"default"` + `chainbench_report{format:"json"}` parse). **Gate:** 04 D1 must be shipped or the report parse returns text. Test (pre-flight): `bash contract/lint-tool-names.sh` fully GREEN (all 3 providers); a dry-run `/work` reaches EVALUATION and chainbench receives `binary_path = build/bin/gstable` and a JSON report. Commit: "feat(evaluator): register chainbench, fix tool names, parse json report (G3, G2, depends 04-D1)". **Blocked on 04 D1.**

**Step 9 — SETUP additions (S5).** Files: `docs/SETUP.md`. Action: per Part C below. Test: SETUP describes Ollama+bge-m3, the real-cks env vars, chainbench build+launch, and the degraded path. Commit: "docs(setup): Ollama bge-m3 + real-cks env + chainbench prereqs (S5)". **Not blocked (but references 03/04 outputs).**

> **Final gate:** `bash contract/lint-tool-names.sh` GREEN + a dry-run `/work STABLE-xxxx --local <fixture>` traversing ANALYSIS→…→EVALUATION with chainbench fed the implementer's `build/bin/gstable`.

---

## Part C — Verification & Acceptance

**Map to `05` M2 acceptance:**

| M2 clause (`05` §6) | Proof |
|---|---|
| **(a)** `tools/cks-mcp` gone, `go.work` updated, `.mcp.json` → real cks + chainbench, all tool names match SSoT (pre-flight lint passes) | Step 6+8: `ls tools/cks-mcp` → absent; `go.work` has only jira-gateway; `.mcp.json` has 3 servers; `bash contract/lint-tool-names.sh` exits 0 |
| **(b)** planner emits `concurrency_impact` for consensus/systemcontracts tasks + `ops.index` on stale | Step 7: dry-run `/work` on a `consensus/**` fixture → `related-code.json.ckg.concurrency_impact` non-empty; `cks.ops.freshness`→`cks.ops.index` sequence present in planner §3.3b |
| **(c)** model IDs are valid GA IDs | Step 2: all 4 frontmatters `claude-…`; dispatch resolves without "unknown model" |
| **(d)** `stablenet-context` no longer injects stale contract names; L3 injection present | Step 3+4: grep `GovStaking\|GovConfig\|GovNCP` → 0; `skills/stablenet-invariants/SKILL.md` present + granted to planner+evaluator |
| **(e)** dry-run `/work` reaches EVALUATION with chainbench receiving the implementer's `build/bin/gstable` | Step 5+8: trace shows implementer writes `state.json.binary_path=…/build/bin/gstable`, evaluator passes it to `chainbench_init{binary_path}`, `chainbench_report{format:"json"}` parses `summary.failed` |

**Pre-flight lint (the M2.a drift gate):**
```
bash contract/lint-tool-names.sh        # 0 = no tool-name drift vs schema
grep -rn 'ckv_search\|ckg_query\|ckg_impact\|ckg_index\|ckv_index' plugin/agents/ plugin/commands/   # expect 0 (shim names gone)
grep -rn 'chainbench_setup\|chainbench_run_tests' plugin/   # expect 0 (non-existent names gone)
grep -rn 'GovStaking\|GovConfig\|GovNCP\|GovRewardee' plugin/ skills/   # expect 0 (G5)
test -f contract/agent-mcp.schema.json && ! test -d tools/cks-mcp   # schema exists, shim gone
```

**SETUP additions (S5) — concrete edits to `docs/SETUP.md`:** the current SETUP is stale for R1′ (it documents the **shim**: `nomic-embed-text` not bge-m3 at `:21,142`; `tools/cks-mcp` build at `:62-63`; `CKS_INDEX_PATH` at `:117-125`; ChainBench "install per its own instructions, plugin doesn't ship it" at `:161-169`). Rewrite:
- **§1 Prerequisites (`:11-26`):** change the Ollama row from "Optional: `nomic-embed-text`" to **required for full retrieval**: Ollama + **`bge-m3`** (1024-dim, multilingual), `ollama pull bge-m3`. Note bge-m3 is load-bearing (intent classifier + ckv share the model, `00` §C2).
- **§3 Build (`:56-79`):** remove the `tools/cks-mcp` build (it's deleted). Document building the **real cks-mcp** from the sibling `code-knowledge-system` repo, flagging `CGO_ENABLED=1` + a C toolchain (sqlite-vec inheritance, 03-plan build note).
- **§4.3 Ollama (`:128-159`):** `OLLAMA_EMBED_MODEL`/`CKS_EMBED_MODEL` → `bge-m3`; the verify curl uses `"model":"bge-m3"`.
- **§4.2 (`:117-126`):** replace shim `CKS_INDEX_PATH` with the real-cks config (`CKS_CONFIG` → `cks.yaml` pointing ckv/ckg data dirs + `CKS_SOURCE_ROOT=<go-stablenet>` + `OLLAMA_URL`), matching the `.mcp.json` env in G1(b).
- **§4.4 ChainBench (`:161-169`):** replace with the concrete launch: register `chainbench` in `.mcp.json` (G1(c)); prereqs `cd <chainbench>/mcp-server && npm install && npm run build` + build the Go wire `network/chainbench-net`; evaluator uses `profile:"default"`.
- **Degraded path:** document that when Ollama/bge-m3 is down, `cks.ops.health` reports `degraded` (03-plan G1 DegradedDummy) and the agent proceeds via Smart-Dummy instructions / session retrieval — the pipeline does not crash (`00` §6/S5).

---

## Part D — Risks / Unknowns (live-code findings)

1. **SSoT schema ownership collision (HIGH, cross-repo).** `00` S4 + this plan put `coding-agent/contract/agent-mcp.schema.json` here; but **03-plan #7 and Step 6 also author it** (cks is "the first provider needing it for its golden test"). Both can't author divergent copies — it is ONE SSoT. **Mitigation:** whichever session runs first authors it; the other reconciles to byte-identical. Recommend 05 owns the canonical file (per `00` S4 "consumer of record"), and 03's golden test reads it from the coding-agent checkout (sibling path) or a vendored copy that CI diff-checks against the canonical. Pin this handshake before either session edits the file.

2. **Real-cks `.mcp.json` env/command names are unverified against 03's shipped `main.go` (HIGH, blocking G1(b)).** 03-plan is config-first (`policies/cks.yaml.example`, `CKS_CONFIG`) but also mentions per-field config (`CKVConfig.OllamaURL`, `IndexConfig.SourceRoot`, etc.). The exact env var *names* cks reads at startup are not pinned. The `.mcp.json` `cks` entry here is a *proposed* shape — **must be reconciled with 03's actual `cmd/cks-mcp/main.go` flag/env parsing** at edit time. Also: the real cks binary path (`${CKS_MCP_BIN}`) is a sibling-repo build, not vendored — the operator must build+locate it (unlike the shim, which was in-tree at `tools/cks-mcp/bin/`).

3. **Implementer does NOT build the binary today — S6 is a real change, not a rename (HIGH, code-verified).** `05` S6 reads as if the implementer already emits an artifact; live, `implementer.md` only runs `go build ./...` (no `-o`), and the **evaluator self-builds** at `{workspace_dir}/logs/gstable` (`evaluator.md:278`). Decision (A) moves the build to the implementer + `build/bin/gstable` + state.json. This touches the implementer's "after all steps" §6 and the evaluator's §7.1 — slightly larger than a path rename. Risk: `./cmd/gstable` must be the correct main package in go-stablenet (the evaluator already assumes it at `:278`); confirm against the real go-stablenet layout.

4. **GA model-ID aliases unconfirmed (MID, blocking G4 correctness).** `00` §6 prescribes `opus-4.7`→`claude-opus-4-7`, but the *exact* string the Claude Code harness accepts (dashed alias vs dated vs `[1m]` suffix) must be read from the live model registry. Wrong IDs fail agent dispatch silently. Keep role→family fixed; only the version string is the unknown.

5. **`chainbench_test_run` test argument (`"standard"`) is not a valid `category/name` (MID, blocking G2 evaluator).** 04-plan §G1: `chainbench_test_run` takes `{test:"category/name"}` validated by `^[a-zA-Z0-9_\-]+(\/[a-zA-Z0-9_\-]+)*$`. The current `chainbench_run_tests("standard")` (`evaluator.md:354`) passes a bare `"standard"` — must map to a real catalog path (e.g. `tx/standard`). **Verify the chainbench test catalog** at edit time; the exact category is not pinned in the plans.

6. **04 D1 is a hard blocker for the C4 loop-back (HIGH, from 04-plan).** Until 04 ships D1 (`chainbench_report{format:"json"}` → `--format json`), the evaluator's new §7.5b `summary.failed` parse silently receives *text* and mis-parses. Step 8 is gated on 04 D1, not just 04's tool names.

7. **No `SessionStart` injection hook — L3 lives in a skill body (MID, design choice).** Claude Code plugins (live `hooks.json` = `PostToolUse` only) give no guaranteed every-turn context injection. L3 is therefore a **skill granted to planner+evaluator**, loaded when those agents run — not a true "session-start" injection. This is the most reliable mechanism available; if a future Claude Code exposes a SessionStart hook, migrate the block there for true always-on coverage (orchestrator + all sub-agents).

8. **L3 invariant values are hardcoded until cks curation lands (MID).** The ~500-token block is authored from `00` §4.3/§4.2; the *authoritative* numbers live in cks `verified` entries — but **0 entries are `verified` today** (03-plan #5). The hardcoded backstop is correct-by-design for L3 (it must not depend on the index), but keep it in sync with the entries once the `00` §4.2 curation session promotes them.

9. **SETUP is wholesale stale for R1′ (MID).** It documents the shim (`nomic-embed-text`, `tools/cks-mcp` build, `CKS_INDEX_PATH`, "plugin doesn't ship ChainBench"). §Part C lists the rewrites; this is more than an "add a section" — several existing sections are now wrong.

10. **`go.work.sum` cleanup (LOW).** Deleting the `./tools/cks-mcp` member leaves orphaned `go.work.sum` entries; `go work sync` cleans them. Harmless if left, but tidy.

---

### Fact-based summary

**Fact (None-label, code-verified):** the cks shim (`tools/cks-mcp/internal/server/server.go:31-58`) registers 5 tools (`ckv_search/ckv_index/ckg_query/ckg_impact/ckg_index`); `plugin/.mcp.json` points `cks` at the shim binary and has NO chainbench entry; `go.work` lists `./tools/cks-mcp`. Planner frontmatter (`planner.md:12-14`) grants `ckv_search/ckg_query/ckg_impact`; body calls them at §3.2(`:79`)/§3.4(`:109`)/§3.5(`:125`)/§6.3(`:391,395`). Evaluator frontmatter (`evaluator.md:13,16`) grants non-existent `chainbench_setup`/`chainbench_run_tests`; §7.2(`:291`) calls `chainbench_setup`, §7.5(`:354`) calls `chainbench_run_tests("standard")`, §7.0(`:258-272`) pre-flight expects the wrong set. All 4 agent model IDs are non-GA (`opus-4.7`×2, `sonnet-4.6`×2). `stablenet-context/SKILL.md:24,38,71-74` carries stale `GovStaking/GovConfig/GovNCP/GovRewardee`. No L3 invariant injection exists. No `contract/` dir / schema file exists. The implementer does NOT build a binary (`implementer.md:167` = `go build ./...` only); the evaluator self-builds at `{workspace_dir}/logs/gstable` (`evaluator.md:278`), NOT `build/bin/gstable`. `docs/SETUP.md` documents the shim + `nomic-embed-text`, not bge-m3/real-cks/chainbench.

**Opinion — High:** nothing in 05 has landed; real scope = 1 `.mcp.json` rewrite + shim delete + `go.work` edit (G1), a precise tool-name rename table in planner+evaluator (G2/G3), 4 model-ID edits (G4), a skill rewrite (G5), a new ~500-token invariant skill (G6), a binary-handoff move from evaluator to implementer (S6 — a real change, the spec under-states it), the net-new SSoT schema + lint (S4), and a SETUP rewrite (S5). **Mid:** the real-cks env/command shape (#2) and the GA model strings (#4) and the chainbench test-catalog path (#5) must be pinned against the shipped 03/04 before the blocked steps. **Low:** `go.work.sum` tidy. **Blocking unknowns:** (1) SSoT-schema ownership handshake with 03 — one canonical file, not two; (2) 03 must ship the real cks (Steps 6–7) and 04 must ship D1 (Step 8) before the rewiring is testable; (3) the exact `.mcp.json` `cks` env var names depend on 03's final `main.go`.
