# 04 — chainbench Refactor: Detailed Design + Implementation Plan

> **Derives from:** `00-system-contract.md` (C1, C4, §2.2 binary=deterministic) + `04-chainbench-refactor.md` (G1–G5, M1 adapter mapping, M2 acceptance).
> **Repo:** `chainbench` at `/Users/wm-it-22-00661/Work/github/tools/chainbench` — a tri-language stack: TypeScript MCP server (`mcp-server/`), Go wire (`network/cmd/chainbench-net`, built binary `network/chainbench-net`), bash adapters + CLI (`chainbench.sh` + `lib/`).
> **Isolation:** Yes — the only cross-project surface is the **C1 JSON Schema** (language-neutral), not Go types. chainbench is the ONE non-pure-Go component in R1′; its conformance binding is a vitest golden against `coding-agent/contract/agent-mcp.schema.json` (that SSoT file is authored in `05`; this plan specifies only chainbench's slice).
> **Dependency note:** Nothing in R1′ ships before chainbench (build order row 4, depends only on `00`). chainbench's outputs feed `05` (the `.mcp.json` registration + the evaluator's expected tool-name set). So **G1 (names) must be verified/locked first** to unblock `05`, and **the report-format bug (D1 below) must be fixed** or C4 `summary.failed` parsing silently returns text.

> **⚠️ Major finding up front (read before estimating).** As with the ckg/ckv/cks plans, the `04` spec evidence is **partly stale**. Verified against HEAD:
> - **G1 names already correct.** The actual tools `chainbench_init / start / status / test_run / report / failure_context` **all exist by exact name** (test.ts, lifecycle.ts). The spec's "actual server exposes `chainbench_test_run`" is right; the evaluator's `chainbench_setup/run_tests` mismatch is a **`05` (coding-agent) fix**, not a chainbench change. chainbench's job is to *lock + golden-test* the subset.
> - **G3 "9 hardcoded `gstable` literals" is stale.** Only **3** live executable defaults remain (`profile.sh:406`, `cmd_stop.sh:14`, `cmd_node.sh:262`); the rest are comments. And the live code is *already* mostly binary-name-agnostic via `CHAINBENCH_BINARY` + `resolve_binary`. The real residual leak risk is narrower than "9 literals" — see G3.
> - **A NEW load-bearing bug not in the spec:** `chainbench_report{format:"json"}` is broken end-to-end (D1). This *is* contract-blocking for C4.
> - **G5 is genuinely remaining:** `init/start/restart` still shell out via `runChainbench`; only `stop/status` route through the Go wire. There is **no** `network.init/start_all/restart/clean` wire handler.
> - **G4 is genuinely remaining:** `feeDelegationAllowedChains` is a hardcoded map at `handlers_node_tx.go:706`.
>
> Part D enumerates every stale/surprise item with live proof. **Effective scope collapses to: D1 report-bug fix (contract-blocking) + G1 golden test + G3 narrow hardening + G4 + G5 (incremental).**

---

## Part A — Detailed Design

### G1 — tool-name contract (the C1 subset)

**STATUS: already-landed (names correct) · file:line below.** No rename needed in chainbench.

The evaluator's loop from `04` §2 — `init → start → status → test_run → report → failure_context` — maps 1:1 to **existing** registered tool names:

| Evaluator step | Actual tool name | Registered at | Routing |
|---|---|---|---|
| init | `chainbench_init` | `mcp-server/src/tools/lifecycle.ts:91` | bash `runChainbench("init …")` (G5) |
| start | `chainbench_start` | `lifecycle.ts:129` | bash `runChainbench("start …")` (G5) |
| status | `chainbench_status` | `lifecycle.ts:179` (`_statusHandler`, lifecycle.ts:36) | **Go wire** `network.status` |
| stop | `chainbench_stop` | `lifecycle.ts:149` (`_stopHandler`, lifecycle.ts:18) | **Go wire** `network.stop_all` |
| test_run | `chainbench_test_run` | `test.ts:103` | bash `runChainbench("test run …")` |
| report | `chainbench_report` | `test.ts:151` | bash `runChainbench("report …")` — **BROKEN for json, see D1** |
| failure_context | `chainbench_failure_context` | `test.ts:173` | TS-native (reads `state/failures/*/context.json`) |

Total registered surface = **46 tools** (grep-confirmed across `src/tools/*.ts`). The evaluator's locked subset is the 7 above.

**I/O JSON for each (the chainbench slice of the C1 schema):**

- `chainbench_init` — in: `{ profile?: string="default", project_root?: abs-path, binary_path?: abs-path }`; out: text (CLI stdout or `Error (exit N): …`). Profile name validated `^[a-zA-Z0-9_\-/]+$` (lifecycle.ts:103); `binary_path`/`project_root` must start `/` (lifecycle.ts:71,80).
- `chainbench_start` — in: `{ project_root?, binary_path? }`; out: text.
- `chainbench_status` — in: `{ network?: string }` (`StatusArgs`, lifecycle.ts:31, `.strict()`); out: wire JSON (per-node block height, peers, running, consensus health).
- `chainbench_test_run` — in: `{ test: "category/name", format?: "text"|"jsonl"="text" }` (test.ts:106); out: text or NDJSON. Name validated `^[a-zA-Z0-9_\-]+(\/[a-zA-Z0-9_\-]+)*$` (test.ts:50).
- `chainbench_report` — in: `{ format?: "text"|"json"|"summary"="text" }` (test.ts:154); out: **C4 shape when json** (see C4 + D1).
- `chainbench_failure_context` — in: `{}`; out: latest `context.json` text (test.ts:203).

**What to add to `coding-agent/contract/agent-mcp.schema.json` (chainbench's slice):** the file does not exist yet (authored in `05`). This plan specifies the chainbench entries to insert: the 7 tool names above, each with the input JSON Schema (derived from the zod `.shape`) and, for `chainbench_report`, the output schema = the C4 report shape (`{summary:{total_tests,passed,failed,assertions:{passed,failed}},tests:[…]}`). The vitest golden (Part B Step 2) asserts the *registered* tools are a superset of this locked subset and that each input shape matches.

**Remaining work:** none on names. Add a **golden conformance vitest** (Step 2) so the subset cannot silently drift, and a **schema-fragment file** chainbench owns (`mcp-server/test/fixtures/agent-subset.schema.json`) that `05` folds into the SSoT.

---

### D1 — `chainbench_report{format:"json"}` returns text, not JSON (NEW — contract-blocking for C4)

**STATUS: remaining (bug, not in `04` spec).** This breaks C4's `summary.failed > 0` loop-back parse.

- `test.ts:167`: `const formatFlag = format === "json" ? " --json" : format === "summary" ? " --summary" : "";` → runs `report --json`.
- `lib/cmd_report.sh:44–58`: the arg parser **only** accepts `--format <text|json|markdown>` / `--format=…`. The bare `--json`/`--summary` flags hit the `*)` branch (cmd_report.sh:64) → `log_warn "Unknown report option … (ignoring)"` → format stays `"text"`.
- **Net effect:** `chainbench_report{format:"json"}` returns the **text** report; the agent's `JSON.parse(summary.failed)` fails or mis-parses. Also `format:"summary"` is silently degraded.

**Target design (minimal):** change `test.ts:167` to emit the flag the CLI actually parses:
```ts
const formatFlag =
  format === "json" ? " --format json" :
  format === "summary" ? " --format summary" : "";
```
But `cmd_report.sh` validates only `text|json|markdown|md` (cmd_report.sh:72) — `summary` is **not** a valid CLI format. Two coherent options:
- **(A, recommended)** Drop `summary` from the MCP tool's allowed set (test.ts `validateReportFormat`, test.ts:57 → `["text","json"]`) and map `json → --format json`. `summary` was never reachable correctly anyway. Smallest blast radius, fixes C4.
- **(B)** Add a `summary` branch to `cmd_report.sh` + `tests/lib/report.sh`. More surface; defer unless `05` needs `summary`.
**Decision: (A).** The evaluator's C4 path is `report --format json`; `summary` is out of the locked subset.

**Acceptance:** a vitest that stubs `runChainbench` and asserts `chainbench_report({format:"json"})` invokes `report --format json` (not `--json`); + a bash test that `chainbench report --format json` emits parseable JSON with `.summary.failed`.

---

### G2 — registration (`.mcp.json`)

**STATUS: partial — launcher + writer exist; the actual coding-agent registration lands in `05`.**

- Launch entry point: `bin/chainbench-mcp` (resolves `CHAINBENCH_DIR=${CHAINBENCH_DIR:-$HOME/.chainbench}`, execs `node ${CHAINBENCH_DIR}/mcp-server/dist/index.js`).
- MCP server entry: `mcp-server/src/index.ts` → built to `mcp-server/dist/index.js` via `npm run build` (`tsc`; package.json:8). Stdio transport (index.ts:34).
- The `.mcp.json` writer already exists: `lib/cmd_mcp.sh` (`chainbench mcp enable`) writes:
  ```json
  { "mcpServers": { "chainbench": { "command": "chainbench-mcp" } } }
  ```
  (cmd_mcp.sh:89–91). No `args`/`env` needed — the launcher self-resolves `CHAINBENCH_DIR` from `$HOME`.

**The `.mcp.json` entry `05` must add** (specified here, edit lands in `05`):
```json
"chainbench": {
  "command": "chainbench-mcp",
  "env": { "CHAINBENCH_DIR": "<abs path to chainbench checkout>" }
}
```
Use explicit `CHAINBENCH_DIR` env in the coding-agent plugin's `.mcp.json` rather than relying on the `$HOME/.chainbench` default, because the dev checkout is at `…/tools/chainbench`, not `~/.chainbench`.

**Build step prerequisite (this repo):** `cd mcp-server && npm install && npm run build` must have run so `dist/index.js` exists (the launcher errors otherwise, chainbench-mcp:15). Also `network/chainbench-net` (the Go wire binary) must be built — `chainbench_status/stop` call it via `callWire`. Document both as launch prerequisites for `05`.

**Remaining work in this repo:** ensure `dist/` and the Go wire binary are buildable from a clean tree (Part C verification); no code change for registration itself.

---

### G3 — `gstable` hardcoding / `adapter_binary_name`

**STATUS: partial — premise mostly stale; one real residual + the adapter contract addition.**

The `04` spec ("9 literal `gstable` occurrences → others leak processes") overcounts. Live `gstable` occurrences in `lib/` (grep-confirmed):

| file:line | kind | leak risk? |
|---|---|---|
| `lib/profile.sh:406` | default for `CHAINBENCH_BINARY` (`.chain.binary`, default `gstable`) | No — it's the *configurable* default; overridable per-profile. |
| `lib/cmd_stop.sh:14` | `_BINARY_NAME="${CHAINBENCH_BINARY:-gstable}"` then `pgrep -f "${_BINARY_NAME} --datadir"` | **Latent** — only if `CHAINBENCH_BINARY` is unset in the stop context. |
| `lib/cmd_node.sh:262` | python `node.get("binary","gstable")` (pids.json fallback) | Low — pids.json normally records the real binary. |
| `cmd_init.sh:183,190,192` · `cmd_node.sh:231,234,356` · `cmd_start.sh:220` · `stablenet.sh:2,201` | **comments only** | None. |

**The actual binary plumbing is already name-agnostic:**
- `CHAINBENCH_BINARY` ← profile `.chain.binary` (profile.sh:406), env-overridable (profile.sh:390 `CHAINBENCH_PROFILE_ENV_OVERRIDE`).
- `resolve_binary "${CHAINBENCH_BINARY}" "${CHAINBENCH_BINARY_PATH}"` (common.sh:79) resolves explicit path → git-root `build/bin/<name>` → `$PWD/build/bin/<name>` → `$PATH`. Used by `cmd_init.sh:21`, `cmd_start.sh:85`, `cmd_node.sh:359`.
- `cmd_init.sh:87,89` `pkill -15/-9 "${CHAINBENCH_BINARY}"` — already uses the resolved name, **not** a literal.

**The genuine gap the spec is pointing at:** the **stop/kill path keys off a binary *name*** (`pgrep -f "${_BINARY_NAME} --datadir"`, cmd_stop.sh:19/36/45/60). If a coding-agent passes `binary_path=/…/build/bin/gstable-pr1234` (a renamed PR build) to `chainbench_init/start`, the launched process's argv[0] is that path, but `cmd_stop.sh` resolves `_BINARY_NAME` from `CHAINBENCH_BINARY` (profile default `gstable`) — the `pgrep` pattern won't match `gstable-pr1234 --datadir` → **process leak on stop**. This is the real M2(b) failure mode.

**`adapter_binary_name` design (the adapter-contract addition `04` G3 calls for):**
Add a fourth bash adapter function alongside `adapter_extra_start_flags` / `adapter_consensus_rpc_namespace`:
```bash
# lib/adapters/stablenet.sh
# adapter_binary_name
# Canonical short binary name for this chain type (used for genesis/init log
# labels only — NOT for process matching; the resolved CHAINBENCH_BINARY is
# authoritative for pgrep/pkill).
adapter_binary_name() { printf 'gstable\n'; }
```
But the **load-bearing fix is in the stop path, not the adapter name**: `cmd_stop.sh` and the `pkill` sites must match against the **resolved binary basename actually launched**, recorded in `pids.json`, not a profile default. Concretely:
1. At start, persist the resolved binary basename into `pids.json` (cmd_start.sh already saves the full launch_cmd at cmd_start.sh:219 `.node${i}.launch_args`; extend `pids_state` to record `binary_basename`).
2. `cmd_stop.sh:14` derives `_BINARY_NAME` from `pids.json` (the basename of the actually-launched binary) with `${CHAINBENCH_BINARY:-gstable}` as fallback only when pids.json is absent.
3. `adapter_binary_name` becomes the *default*/label source (when no explicit binary), keeping the adapter contract symmetric for future non-`gstable` chains.

**Routing change:** `cmd_stop.sh` and the `pkill` in `cmd_init.sh:87,89` read the launched basename from `pids.json` (single source of truth = what was actually spawned), falling back to `adapter_binary_name` → `CHAINBENCH_BINARY` → `gstable`. This makes a `gstable-pr1234` binary init/start/stop cleanly with no leak (M2.b).

**Remaining work:** (i) add `adapter_binary_name` to the 3 adapters (stablenet real, wbft/wemix stubs return their canonical names); (ii) record launched basename in `pids.json`; (iii) reroute `cmd_stop.sh` + `cmd_init.sh` pkill to read it. The Go-side mirror (`adapters.Adapter.BinaryName()`) is **optional** — only needed once G5 moves stop to the wire; defer with G5.

---

### G4 — tx-types through the adapter

**STATUS: remaining · `network/cmd/chainbench-net/handlers_node_tx.go:706`.**

```go
// handlers_node_tx.go:702
// feeDelegationAllowedChains is the chain-type allowlist for
// … lifting to an Adapter.SupportedTxTypes() method is a Sprint 5 concern.
var feeDelegationAllowedChains = map[string]bool{   // :706
	"stablenet": true,
	"wbft":      true,
}
// :834  if !feeDelegationAllowedChains[chainType] { … NOT_SUPPORTED }
```
The Go `Adapter` interface (`network/internal/adapters/spec/types.go:52`) currently has only `GenerateGenesis / GenerateToml / ExtraStartFlags / ConsensusRpcNamespace` — **no** `SupportedTxTypes`.

**Target design:** add to the `spec.Adapter` interface:
```go
// SupportedTxTypes reports the tx type bytes this chain accepts beyond the
// Ethereum baseline (e.g. go-stablenet's 0x16 FeeDelegateDynamicFeeTx).
SupportedTxTypes() []byte
```
- `stablenet` adapter returns `[]byte{feeDelegateTxType}` (the `0x16` byte, handlers_node_tx.go:696).
- `wbft` adapter returns `[]byte{feeDelegateTxType}` (matches the current allowlist).
- `wemix` returns `nil` (no fee-delegation).
Then `newHandleNodeTxFeeDelegationSend` (handlers_node_tx.go:711) replaces the map lookup with `adapters.Load(chainType)` → `slices.Contains(a.SupportedTxTypes(), feeDelegateTxType)`. The `chainType` is already resolved in the handler; route the gate through the interface instead of the literal map.

**Remaining work:** interface method + 3 impls + 1 handler edit + update `handlers_test.go` expectations. Pure Go, `go test ./network/...`-gated. **Not contract-blocking** (the C1/C4 surface is unaffected; this is an internal decoupling for non-`gstable` chains).

---

### G5 — Go-wire lifecycle handlers (`init`/`start`/`restart`/`clean`)

**STATUS: remaining (partial wire migration) · evidence below.**

Current wire dispatch table (`handlers.go:46–69`) registers: `network.{load,probe,stop_all,status,attach,capabilities}` + `node.{stop,start,restart,rpc,tail_log,account_state,block_number,chain_id,balance,contract_call,contract_deploy,events_get,gas_price,tx_send,tx_fee_delegation_send,tx_wait}`. **There is no `network.init`, `network.start_all`, `network.restart`, or `network.clean`.**

Consequently in `lifecycle.ts`:
- `chainbench_init` (lifecycle.ts:101) → `runChainbench("init …")` — **bash shell-out.**
- `chainbench_start` (lifecycle.ts:135) → `runChainbench("start …")` — **bash shell-out.**
- `chainbench_restart` (lifecycle.ts:165) → `runChainbench("restart …")` — **bash shell-out.**
- `chainbench_stop` (lifecycle.ts:154) → `callWire("network.stop_all")` — **already wire.**
- `chainbench_status` (lifecycle.ts:184) → `callWire("network.status")` — **already wire.**

So ~the spec's "5/38 on the wire" is directionally right; lifecycle is **2 wire (stop/status), 3 bash (init/start/restart)**. The bash handlers stay correct and deterministic — G5 is **incremental**, not contract-blocking (`04` §4: "not contract-blocking once names are correct").

**Target design:** add Go-wire handlers mirroring the existing `network.stop_all`/`node.start` pattern (they wrap `local.NewDriver(chainbenchDir)` and shell to `chainbench.sh`, see handlers_node_lifecycle.go:40–41):
- `network.init` (args `{profile, binary_path?}`) → `driver.Init(...)` → `chainbench.sh init --profile … --quiet [--binary-path …]`.
- `network.start_all` (args `{binary_path?}`) → `chainbench.sh start --quiet [--binary-path …]`.
- `network.restart` (args `{profile?, binary_path?}`) → `chainbench.sh restart …`.
- `network.clean` (args `{}`) → `chainbench.sh clean` (cmd_clean.sh exists).
Register them in `allHandlers` (handlers.go:46). Then reroute `lifecycle.ts` `chainbench_init/start/restart` from `runChainbench` to `callWire("network.init"/"network.start_all"/"network.restart")`, mirroring `_stopHandler` (lifecycle.ts:18) — this also unifies binary_path forwarding through the wire envelope (as `node.start` already does, node.ts:83).

**Remaining work:** 4 Go handlers + driver methods (the LocalDriver shells to `chainbench.sh`, so it's thin) + lifecycle.ts reroute + tests. Largest of the remaining items; do **last** (incremental). **Note:** keep the bash CLI handlers intact — the wire handlers delegate to them; this is a transport migration, not a reimplementation.

---

### M1 — adapter mapping (go-stablenet → `stablenet`, consensus RPC namespace)

**STATUS: already-landed · verified.**

- **Profile selection:** profiles set `.chain.type` (→ `CHAINBENCH_CHAIN_TYPE`, profile.sh:410, **default `stablenet`**). `profiles/default.yaml` does **not** set `type:`, so it resolves to `stablenet` — the go-stablenet path. Only `profiles/remote-example.yaml` sets a `type:`. **There is no separate `go-stablenet` profile file** — `default.yaml` (and the hardfork/regression profiles) *are* the go-stablenet profiles via the `stablenet` default.
- **Adapter load:** `cb_adapter_load "$_CHAIN_TYPE"` (cmd_init.sh:114) sources `lib/adapters/stablenet.sh` — the **fully-ported** adapter (genesis + TOML + start flags + RPC namespace). The `wbft`/`wemix` bash adapters are stubs that `_cb_*_not_implemented` on genesis/toml (wbft.sh:13, wemix.sh:14).
- **Consensus engine vs adapter name (the `04` M1 caution):** confirmed — the *adapter* is named `stablenet` (after the chain/`gstable` binary), while the *consensus engine* is WBFT. `adapter_consensus_rpc_namespace()` returns **`istanbul`** (stablenet.sh:216), i.e. WBFT's istanbul-compatible RPC namespace — **correct**, do not conflate with the stub `wbft` adapter. The Go mirror agrees: `stablenet`/`wbft` adapters both `ConsensusRpcNamespace() == "istanbul"` (wbft.go bottom; stablenet.go).
- **Mis-selection guard:** if a profile sets `chain.type: wbft`, init fails at genesis with the stub's `ErrNotImplemented` / `_cb_wbft_not_implemented` — matching `04` M1. go-stablenet profiles must leave `type` unset (default `stablenet`) or set it explicitly to `stablenet`.

**Remaining work:** none (verification only). Add a bash test asserting `default.yaml` resolves `CHAINBENCH_CHAIN_TYPE=stablenet` and that `adapter_consensus_rpc_namespace == istanbul` (Part B Step 6). Optionally document in a profile comment that go-stablenet == default == `stablenet` adapter, to prevent a future author adding a redundant `go-stablenet.yaml` that mis-selects `wbft`.

---

## Part B — Implementation Plan (ordered, test-gated)

> Order rationale: **D1 (report bug) + G1 (golden) first** — they unblock `05` and fix the C4 loop-back. Then **G3** (prevent process leaks for renamed PR binaries — M2.b). Then **G4** (Go decoupling, isolated). Then **G5** (largest, incremental, last). Each step keeps the tree green.

**Step 0 — Baseline green.**
- Files: none. · Action: `cd mcp-server && npm install && npm run build && npm test`; `cd network && go build ./... && go test ./cmd/chainbench-net/...`; `bash tests/run.sh` (or the repo's bash test entry — confirm). · Test: all green / capture current state. · Commit: none.

**Step 1 — D1: fix `chainbench_report` json flag (contract-blocking for C4).**
- Files: `mcp-server/src/tools/test.ts` (`validateReportFormat` :57 → `["text","json"]`; format flag :167 → `--format json`). · Action: map `json → " --format json"`, drop `summary` from the tool's allowed set (option A). · Test: `mcp-server/test/report.test.ts` (new) — stub `runChainbench`, assert `chainbench_report({format:"json"})` calls `report --format json`; reject `summary` at the boundary. Plus a bash test: `chainbench report --format json | python3 -c "import json,sys;json.load(sys.stdin)['summary']['failed']"`. · Commit: "fix(report): route json format through --format (C4 loop-back)".

**Step 2 — G1: golden conformance vitest + schema fragment.**
- Files: `mcp-server/test/fixtures/agent-subset.schema.json` (new — the 7-tool chainbench slice of the C1 schema, input shapes + the C4 report output shape); `mcp-server/test/contract.test.ts` (new). · Action: instantiate the `McpServer`, register all tools, assert the registered set ⊇ `{chainbench_init,start,status,test_run,report,failure_context}` (+ `stop`), and each input shape matches the fragment. · Test: `npm test -- contract`. · Commit: "test(contract): pin agent-facing tool subset to C1 fragment (G1/M2.a)".

**Step 3 — G3: add `adapter_binary_name` to the bash adapter contract.**
- Files: `lib/adapters/stablenet.sh` (+`adapter_binary_name(){ printf 'gstable\n'; }`), `lib/adapters/wbft.sh` (`gwbft`), `lib/adapters/wemix.sh` (`gwemix`). · Action: add the function to all three; document it is a label/default source, not the pgrep key. · Test: `tests/lib` bash test asserting each adapter, once sourced, prints its name. · Commit: "feat(adapter): add adapter_binary_name to chain-adapter contract (G3)".

**Step 4 — G3: record launched binary basename in pids.json; reroute stop/kill.**
- Files: `lib/pids_state.sh` (persist `binary_basename` at start), `lib/cmd_start.sh` (write the resolved basename), `lib/cmd_stop.sh:14` (derive `_BINARY_NAME` from pids.json, fallback `adapter_binary_name`→`CHAINBENCH_BINARY`→`gstable`), `lib/cmd_init.sh:87,89` (pkill against the recorded basename). · Action: make the kill path key off *what was actually launched*, not the profile default. · Test: a bash integration test — init+start with `binary_path=/tmp/gstable-pr1234` (a copy/symlink of the built binary), then `chainbench stop`, assert `pgrep -f 'gstable-pr1234'` is empty (M2.b). Gate/skip when no built binary present. · Commit: "fix(stop): kill by launched binary basename to prevent leaks for renamed binaries (G3/M2.b)".

**Step 5 — G4: lift tx-type support to the Go Adapter interface.**
- Files: `network/internal/adapters/spec/types.go` (`SupportedTxTypes() []byte` on `Adapter`), `network/internal/adapters/{stablenet,wbft,wemix}/*.go` (impls), `network/cmd/chainbench-net/handlers_node_tx.go` (:706 remove `feeDelegationAllowedChains`; :834 gate via `adapters.Load(chainType).SupportedTxTypes()`), `handlers_test.go` (update expectations). · Action: route the fee-delegation gate through the interface. · Test: `go test ./network/internal/adapters/... ./network/cmd/chainbench-net/ -run 'TxFeeDelegation|SupportedTxTypes'`. · Commit: "refactor(tx): gate fee-delegation through Adapter.SupportedTxTypes (G4)".

**Step 6 — M1: adapter-mapping verification tests.**
- Files: `tests/lib` bash test (new). · Action: assert loading `default.yaml` resolves `CHAINBENCH_CHAIN_TYPE=stablenet`; `cb_adapter_load stablenet` then `adapter_consensus_rpc_namespace == istanbul`; `cb_adapter_load wbft` then `adapter_generate_genesis` exits non-zero (`_cb_wbft_not_implemented`). · Test: bash test green. · Commit: "test(adapter): pin go-stablenet→stablenet adapter + istanbul namespace (M1)".

**Step 7 — G5: Go-wire lifecycle handlers (incremental, last).**
- Files: `network/cmd/chainbench-net/handlers_network.go` (+`newHandleNetworkInit/StartAll/Restart/Clean`), `handlers.go:46` (register), `network/internal/drivers/local/*.go` (driver `Init/StartAll/Restart/Clean` shelling to `chainbench.sh`), `handlers_test.go` (+cases). · Action: mirror `newHandleNetworkStopAll` (handlers.go:49) / `newHandleNodeStart` (handlers_node_lifecycle.go:64). · Test: `go test ./network/cmd/chainbench-net/ -run 'NetworkInit|StartAll|Restart|Clean'`. · Commit: "feat(wire): add network.init/start_all/restart/clean handlers (G5)".

**Step 8 — G5: reroute lifecycle.ts to the wire.**
- Files: `mcp-server/src/tools/lifecycle.ts` (`chainbench_init/start/restart` → `callWire`, mirroring `_stopHandler`). · Action: replace `runChainbench` calls with `callWire` envelopes forwarding `profile`/`binary_path`. · Test: `mcp-server/test/lifecycle.test.ts` (extend — stub `callWire`, assert correct wire command + args). · Commit: "refactor(lifecycle): route init/start/restart through Go wire (G5)".

---

## Part C — Verification & Acceptance

**Full-repo gate (run before "done"):**
```
# TS
cd mcp-server && npm install && npm run build && npm test           # vitest
# Go wire
cd network && go build ./... && go vet ./... && go test ./...
# bash
bash tests/run.sh            # (confirm the bash test entry point; or run tests/lib/*.sh)
# launch smoke (G2 prereq)
test -f mcp-server/dist/index.js && test -x network/chainbench-net
```

**M2 acceptance (`04` §5) → proof map:**

| M2 clause | Proof |
|---|---|
| (a) C1 subset exists by exact name + matches SSoT schema (vitest golden) | Step 2 `contract.test.ts` (names already correct, G1) |
| (b) non-`gstable`-named binary init/start/stop with no leaked processes (`adapter_binary_name` honored) | Step 4 bash test: `gstable-pr1234` → stop → `pgrep` empty |
| (c) `chainbench_init{binary_path}` accepts arbitrary path; `chainbench report --format json` returns C4 shape | lifecycle.ts validators (abs-path, lifecycle.ts:77) + Step 1 fix + bash json parse |
| (d) go-stablenet profile selects `stablenet` adapter, produces blocks | Step 6 mapping test + a full init→start→status block-height assertion (gated on built binary) |

**C4 report shape check:** `chainbench report --format json` must emit
```json
{ "summary": { "total_tests": N, "passed": P, "failed": F,
               "assertions": { "passed": AP, "failed": AF } },
  "tests": [ { "status": "passed|failed", "pass": x, "fail": y, … } ] }
```
This is exactly what `tests/lib/report.sh:_report_json` (report.sh:63–74) emits, and per-test records carry `status`/`pass`/`fail` (assert.sh:241,272). After Step 1, `chainbench_report{format:"json"}` reaches this path. The agent parses `summary.failed > 0`.

---

## Part D — Risks / Unknowns (live-code findings)

1. **`chainbench_report{format:"json"}` is broken today (HIGH, code-verified — NEW, not in `04`).** `test.ts:167` emits `--json`; `cmd_report.sh` only parses `--format json` (cmd_report.sh:44) → unknown flag ignored → **text returned**. This silently defeats C4's `summary.failed` parse. **Must fix (Step 1) before `05` wires the evaluator.** This is the single most load-bearing surprise.

2. **G1 names are already correct; the mismatch is in coding-agent, not chainbench (HIGH).** `chainbench_init/start/status/test_run/report/failure_context` all exist (test.ts/lifecycle.ts). The evaluator's `chainbench_setup/run_tests` expectation is fixed in `05`, not here. chainbench's only G1 work is the golden test.

3. **"9 hardcoded `gstable`" is stale (HIGH).** Only 3 live executable defaults (`profile.sh:406`, `cmd_stop.sh:14`, `cmd_node.sh:262`); the rest are comments. Binary resolution is already name-agnostic (`CHAINBENCH_BINARY` + `resolve_binary`, common.sh:79). The **real** leak vector is narrower: the **stop/pkill path keys off the profile-default binary name, not the actually-launched basename** — so a renamed PR binary (`gstable-pr1234`) leaks. G3 should fix *that* (Step 4), not chase comment occurrences.

4. **`adapter_binary_name` alone does not fix the leak (MID).** The adapter function the spec names is a *label/default* source; the load-bearing change is recording the launched basename in `pids.json` and keying `pgrep`/`pkill` off it. Adding `adapter_binary_name` without the pids.json reroute would not satisfy M2.b. Plan reflects both.

5. **No separate `go-stablenet` profile exists (MID).** `default.yaml` (+ hardfork/regression) *are* the go-stablenet profiles via the `stablenet` default (profile.sh:410). `04` M1 says "confirm the go-stablenet profile selects `stablenet`" — confirmed, but there is no file literally named `go-stablenet`. If `05`/evaluator passes `profile:"go-stablenet"`, `chainbench_init` will fail (no such profile). **Action for `05`:** the evaluator should pass `profile:"default"` (or a purpose-built profile), not `"go-stablenet"`. Flag this cross-doc.

6. **Go wire is a built artifact in-tree (MID).** `network/chainbench-net` (a 14 MB committed binary) is what `chainbench_status/stop` (and post-G5 `init/start/restart`) invoke via `callWire` → `wire.ts`. If G5 lands but the binary isn't rebuilt, the new `network.init/start_all` handlers won't exist at runtime. Part C gate must rebuild the Go wire (`go build -o network/chainbench-net ./network/cmd/chainbench-net`) and confirm `dist/index.js` exists. The TS↔Go↔bash boundary means **three build artifacts** must be in sync; document for `05`.

7. **G4/G5 are incremental, not contract-blocking (NONE/fact).** `04` §4 explicitly: Go-wire completion is "not contract-blocking once names are correct." The C1/C4 surface is satisfied by Steps 1–2 alone. G4/G5 improve determinism + non-`gstable` support but can land in a follow-up if the session is time-boxed — sequence them last.

8. **`summary` report format was always broken (LOW).** Dropping it (Step 1 option A) removes a never-correct path. If any existing consumer relied on `chainbench_report{format:"summary"}`, it was getting text anyway. Confirm no caller in `05`/evaluator expects `summary` before deleting (grep the coding-agent evaluator).

---

### Fact-based summary
**Fact (None-label, code-verified):** the 6+1 evaluator tools exist by exact name (`chainbench_init/start/status/stop/test_run/report/failure_context`); `chainbench_report{format:"json"}` emits `--json` which `cmd_report.sh` ignores → returns text; only `chainbench_stop`/`status` route through the Go wire (`network.stop_all`/`network.status`), while `init/start/restart` shell out via `runChainbench`; the wire dispatch table (handlers.go:46) has no `network.init/start_all/restart/clean`; `feeDelegationAllowedChains` is a hardcoded map at handlers_node_tx.go:706; the Go `Adapter` interface (spec/types.go:52) has 4 methods, none for binary-name or tx-types; bash adapters lack `adapter_binary_name`; only 3 live `gstable` defaults exist (profile.sh:406, cmd_stop.sh:14, cmd_node.sh:262), rest are comments; `default.yaml` resolves `chain.type=stablenet` (default) and `adapter_consensus_rpc_namespace=istanbul`; `tests/lib/report.sh:_report_json` already emits the C4 shape; `.mcp.json` writer (cmd_mcp.sh:89) emits `{command:"chainbench-mcp"}`; launcher self-resolves `CHAINBENCH_DIR` from `$HOME/.chainbench`.

**Opinion — High:** the only contract-blocking work is D1 (report-json fix) + the G1 golden test; everything else (G3 leak-hardening, G4, G5) is incremental. **Mid:** the real G3 fix is the pids.json-basename stop reroute, not `adapter_binary_name` alone; `05` must not pass `profile:"go-stablenet"` (no such file). **Low:** dropping the `summary` report format is safe but verify no evaluator caller depends on it.
