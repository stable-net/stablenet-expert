# 04 — chainbench Refactor

> **Derives from:** `00-system-contract.md` (C1, C4, §5). **Repo:** `chainbench` (TS MCP server + Go `network/` wire + bash adapters).
> **Role in R1′:** the deterministic evaluation backend (pipeline stage 11). Given a built `gstable` binary, stand up a local go-stablenet network, verify block production + tx tests, emit a JSON report. LLM judgement of the report stays in the coding-agent.
> **Isolatable:** Yes. This is the one non-pure-Go component, so the C1 JSON Schema (language-neutral) is the binding contract.

> **⚠ Superseded by `plans/04-chainbench-plan.md` (live-code, authoritative).** Live-code corrections: (1) **Tool names already exist** (`chainbench_init/start/status/stop/test_run/report/failure_context`) — the evaluator mismatch is a **`05` fix**, not a chainbench rename. (2) **G3 "9 literals" stale** — only 3 live defaults; the real leak is stop/`pkill` keying off the profile-default name vs the launched basename. (3) **M1 confirmed** — go-stablenet uses the `stablenet` adapter via `default.yaml`; **no `go-stablenet` profile exists** (`05` must use `profile:"default"`). (4) **C4 report shape already correct.** (5) **NEW contract-blocking bug D1:** `chainbench_report{format:"json"}` is silently ignored (`cmd_report.sh` parses `--format json`, tool passes `--json`) → returns text → breaks `summary.failed` loop-back. Fix D1 first. Use the plan for execution.

## 1. Contract this repo must satisfy

- **Exposes (C1 + C4):** the `chainbench_*` tool subset the `evaluator` agent calls, by **actual server names**, registered so coding-agent can reach them.
- **Input (C4):** built binary via `build/bin/gstable` convention or explicit `binary_path` arg. **Binary handoff (S6):** the coding-agent *implementer* produces the modified go-stablenet binary at `build/bin/gstable` (its build step), and the *evaluator* passes that path to `chainbench_init{binary_path}`. chainbench treats it as an opaque executable; version/commit is tracked by the agent (see `05` §5). chainbench must NOT assume the binary is named `gstable` (see G3).
- **Output (C4):** `chainbench report --format json` → `{summary:{passed,failed,assertions:{passed,failed}}, tests:[{status,pass,fail,...}]}`. coding-agent parses `summary.failed > 0` for loop-back.

## 2. Load-bearing gap: tool-name contract drift

| ID | Gap | Evidence | Action |
|---|---|---|---|
| **G1** | coding-agent `evaluator` expects `chainbench_setup`/`chainbench_run_tests` which **do not exist**; actual server exposes `chainbench_init`/`chainbench_test_run` | evaluator.md §7.0; `mcp-server/src/tools/lifecycle.ts`, `test.ts` | Adopt actual names as canonical in C1. Fix the evaluator's expected set in `05`. Do **not** add alias tools. |
| **G2** | chainbench MCP not registered in coding-agent | `plugin/.mcp.json` has no `chainbench` entry | Register the TS MCP server in `.mcp.json` (done in `05`); ensure a stable launch command + env. |

The agent's evaluation loop (C1 subset to lock): `chainbench_init(profile, binary_path)` → `chainbench_start` → `chainbench_status` (consensus up) → `chainbench_test_run(test)` → `chainbench_report(format=json)` → on fail `chainbench_failure_context`.

## 3. Adapter decoupling (C4) — remove `gstable` hardcoding

| ID | Gap | Evidence | Action |
|---|---|---|---|
| **G3** | 9 literal `gstable` occurrences → only `gstable`-named binaries work; others leak processes on stop/kill | HARDCODING_AUDIT.md; `lib/cmd_stop.sh:14`, `lib/cmd_node.sh:262`, cmd_init/cmd_start | Add `adapter_binary_name` to the adapter contract; route all `pkill`/launch through it. |
| G4 | `adapter_supported_tx_types` hardcoded `{stablenet, wbft}` | `network/cmd/chainbench-net/handlers_node_tx.go` | Gate tx-type support through the Adapter interface. |

go-stablenet runs on the **stablenet adapter** (fully ported, golden-file pinned). wbft/wemix adapters are stubs — out of scope unless a profile needs them.

> **Verify (M1):** the *adapter* name is `stablenet` (named after the chain/`gstable` binary), while go-stablenet's *consensus engine* is WBFT — do not conflate them. Confirm the go-stablenet profile selects the `stablenet` adapter and that `adapter_consensus_rpc_namespace` resolves WBFT's RPC namespace (istanbul-compatible per the adapter digest). If a profile mis-selects the stub `wbft` adapter, init fails with `ErrNotImplemented`.

## 4. Go-wire completion (binary = deterministic) — `00` §2.2

| ID | Gap | Evidence | Action |
|---|---|---|---|
| G5 | `init`/`start`/`restart`/`clean` still shell-out to bash via `runChainbench`; only ~13% (5/38) of tools on Go wire | NEXT_WORK / Sprint 5c.4.2 | Implement Go-wire handlers `network.init`/`start_all`/`restart`/`clean`; reroute lifecycle tools. (Incremental; not contract-blocking once names are correct.) |

chainbench already keeps signer key material out of stdout/stderr/logs (sealed struct + redaction, tested) — keep that invariant. No LLM in chainbench; report judgement is the agent's job (`00` §5).

## 5. Work order (this repo)

1. G1 (lock the C1 tool subset by actual names) — unblocks `05` evaluator wiring.
2. G3 (`adapter_binary_name`, remove `gstable` hardcoding) — prevents process leaks for any non-`gstable` binary.
3. G2 launch/registration prerequisites (the actual registration is in `05`).
4. G4, G5 — Go-wire completion (incremental).

**Acceptance (M2) — done when:** (a) the C1 tool subset the evaluator calls exists by exact name and matches the SSoT schema (vitest golden); (b) a non-`gstable`-named binary can be init/started/stopped without leaked processes (`adapter_binary_name` honored); (c) `chainbench_init{binary_path}` accepts an arbitrary path and `chainbench_report --format json` returns the C4 shape; (d) go-stablenet profile selects the `stablenet` adapter and produces blocks.

## 6. Out of scope / risks

- wbft/wemix/ethereum adapters — stubs, only if a future profile demands.
- chainbench is TS+Go+bash; the C1 JSON Schema (not Go types) is the cross-language binding — keep tool I/O schemas in sync with the SSoT file.
