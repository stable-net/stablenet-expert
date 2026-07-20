# PLAN — LOCAL-20260609_003552 (CKG Benchmark)

Home: `.stablenet-expert/bench/ckg-bench/` (new sibling to the existing 3-way `bench-orchestration` assets).
No go-stablenet production code is modified. All paths below are relative to repo root unless absolute.

## Step 1: Repo skeleton + manifest schema
- New files: `.stablenet-expert/bench/ckg-bench/{README.md, qa-manifest.schema.json, __init__.py, run.py (stub)}`
- Rationale: establish home dir separate from the 3-way harness; define the Q&A manifest contract.
- Dependencies: []
- Verification: `python3 .stablenet-expert/bench/ckg-bench/run.py --help` exits 0; schema validates with `python -m json.tool`.

## Step 2: Golden-set library (30 questions)
- New files: `golden-set/G01.yaml … G30.yaml`, `golden-set/index.yaml`
- Schema reuses cks-eval YAML (file + start_line + end_line + symbol + intent), adds:
  `sha_pin`, `difficulty`, `invariant_refs`, `language`, `bucket`, `expected_keywords`.
- Composition: 10 from cks-eval (SN01–SN10) + 11 RI-1..RI-11 invariant probes + 6 hotspot probes + 3 cherry-pick boundary probes.
- Dependencies: [Step 1]
- Verification: `validate_golden.py` resolves every entry via cks `find_symbol` against indexed_head and asserts file+overlap; 30/30 must pass.

## Step 3: AI Driver protocol + 2 impls
- New files: `drivers/{__init__.py, base.py, claude_cli.py, replay.py}`
- `Driver` protocol: `ask(system_prompt, user_prompt, max_turns=1, tool_broker=None) -> AskResult`.
  `claude_cli` for live; `replay` for CI determinism/offline.
- Dependencies: [Step 1]
- Verification: `test_drivers.py` — replay reproduces a recorded transcript exactly; claude_cli mocked smoke-test.

## Step 4: Four method dispatchers
- New files: `methods/{__init__.py, m1_raw_files.py, m2_graph_full.py, m3_incremental.py, m4_get_for_task.py}`
- M1: full file contents from anchors (+1 sibling). M2: `get_subgraph(depth=2,max_total=2000)` over 4 root pkgs.
  M3: multi-turn tool-broker loop (max_turns=8). M4: single `get_for_task(query)` → EvidencePack.
- Dependencies: [Step 3]
- Verification: each method run against G01 returns a structured response + non-zero input-token count; M2/M3/M4 require live cks (cks-health precheck).

## Step 5: Structured-response envelope + extractor
- New files: `io/{envelope.py, extract.py}`
- Envelope `{answer, citations:[{file,start_line,end_line,symbol?}]}`; strict + lenient (prose `file:line`) modes.
- Dependencies: [Step 4]
- Verification: `test_extract.py` — strict JSON, malformed JSON, prose-with-citations, prose-without-citations.

## Step 6: Four metric scorers
- New files: `scorers/{location.py, correctness.py, hallucination.py, info_volume.py}`
- location: P/R/F1 overlap matcher ported from cks `internal/eval/metrics.go`.
  correctness: recall≥threshold AND keyword check. hallucination: per-citation cks `find_symbol` + disk fallback.
  info_volume: input tokens per cell.
- Dependencies: [Step 5]
- Verification: `test_scorers.py` — synthetic responses incl. a fabricated `nonexistent_function` citation scoring as 1 hallucination.

## Step 7: Runner + checkpoint/resume
- New files: `runner.py`, `state.py`
- Per cell: load question → dispatch method → Driver → extract → score 4 metrics → write `cells/{q}__{method}/result.json`.
  `batch_size` cells per invocation, then resume state. `state.json` mirrors bench-orchestration cell shape.
- Dependencies: [Step 4, Step 5, Step 6]
- Verification: `test_runner.py` kill-and-resume — start 4-cell run, interrupt after cell 2, resume, verify idempotent skip.

## Step 8: Report aggregation
- New files: `report.py`, `report_test.py`
- Reuses coding-agent `bench/lib/report.py` patterns (markdown + CSV + JSON). Per-method 4-metric rollup
  + per-question matrix + M4-vs-M1 delta table (Δ_correct_rate, token_reduction_pct).
- Dependencies: [Step 7]
- Verification: snapshot test on a 2-question × 4-method fixture; report.md byte-exact vs checked-in golden.

## Step 9: Top-level entry point + reproducibility plumbing
- New files: `run.py` (fleshed out), `manifests/default.json`
- Single command: `python3 .stablenet-expert/bench/ckg-bench/run.py --manifest manifests/default.json`.
  Re-run = same command; golden-set re-resolution catches drift.
- Dependencies: [Step 8]
- Verification: end-to-end smoke on 2 questions × 4 methods with replay driver; output diff vs checked-in expected.

## Step 10: Tests + README
- New files: `tests/` (per-module), `README.md`
- README: layout, 4-method/4-metric matrix, relationship to bench-orchestration & cks-eval, SHA-pin policy, replay mode.
- Dependencies: [Step 9]
- Verification: `python3 -m unittest discover -s .stablenet-expert/bench/ckg-bench/tests` passes.

## Verification Plan
- Unit tests per step (stdlib `unittest`). Integration: 2-question × 4-method replay run (deterministic, CI).
- Live smoke: 1-question × 4-method `claude_cli` run + cks-health precheck (manual, gated on indexed_head==HEAD).
- `go build` / `go test -race` / ChainBench: **not applicable** — no Go production changes (record skip explicitly per RI-13).
- AC mapping: AC#1→Step 9; AC#2→Step 8; AC#3→Step 8 delta table; AC#4→Step 9 rerun + Step 2 drift re-resolution.

## Risks
- Live AI cost: 120 LLM calls/full run → replay driver for CI; live run opt-in via `--driver claude_cli`; M3 max_turns bounded.
- cks-mcp availability for M2/M3/M4: precheck via `cks.ops.health`; abort cell cleanly on backend down.
- Golden-set drift: `validate_golden.py` fails fast before any benchmark run.
- Method 2 prompt size: `max_total=2000`/seed + 100k-token ceiling; oversize → cell failed.
- Hallucination scoring depends on cks correctness: fall back to disk `exists()` + `grep -n` when find_symbol empty; record both signals.
