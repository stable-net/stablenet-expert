# DESIGN v1 — LOCAL-20260609_003552 (CKG Benchmark)

No production-code change. New package layout under `.stablenet-expert/bench/ckg-bench/`.

```
.stablenet-expert/bench/ckg-bench/
├── README.md
├── qa-manifest.schema.json
├── __init__.py
├── run.py                       # CLI entrypoint (stub Step 1, fleshed Step 9)
├── manifests/default.json       # Step 9
├── golden-set/{G01..G30}.yaml, index.yaml   # Step 2
├── validate_golden.py           # Step 2
├── drivers/{__init__,base,claude_cli,replay}.py   # Step 3
├── methods/{__init__,m1_raw_files,m2_graph_full,m3_incremental,m4_get_for_task}.py   # Step 4
├── io/{envelope,extract}.py     # Step 5
├── scorers/{location,correctness,hallucination,info_volume}.py   # Step 6
├── runner.py, state.py          # Step 7
├── report.py                    # Step 8
└── tests/                       # Step 10
```

## Step 1 — manifest schema
`qa-manifest.schema.json` (draft-07): required `experiment, golden_set, methods, driver,
go_stablenet_root, sha_pin`; `methods` enum `M1_raw|M2_graph_full|M3_incremental|M4_get_for_task`;
`driver` enum `claude_cli|replay`; `batch_size` default 8.

## Step 2 — golden-set
Per-question YAML `version: 2` extends cks-eval v1 (additive: `id, bucket, language, intent,
difficulty, sha_pin, expected_keywords, invariant_refs`). `index.yaml` lists questions + bucket counts
+ shared `sha_pin`. `validate_golden.py` runs stablenet-knowledge `find_symbol(symbol)` for each entry against
indexed_head; asserts reported file == entry file and range overlaps `[start_line,end_line]`.

## Step 3 — drivers
`base.py`: `AskResult{response_text, input_tokens, output_tokens, turns, transcript_path}`;
`Driver` Protocol `ask(system_prompt, user_prompt, max_turns=1, tool_broker=None) -> AskResult`.
`claude_cli.py` wraps local Claude CLI/SDK (temp prompt file, capture stdout JSON, char/4 fallback
for usage — same shape as coding-agent `bench/lib/capture.py`). `replay.py` returns canned responses
keyed by prompt SHA-256 for offline/CI determinism. `tool_broker` (M3 only) exposes
semantic_search/find_symbol/get_subgraph/find_callers and logs every call to the transcript.

## Step 4 — methods
Each method: `build_prompt(question) -> (system_prompt, user_prompt)` + `run(question, driver) -> AskResult`.
Shared system prompt forces the strict JSON envelope. M1: full file bodies from
`expected_citations[].file` ∪ ≤1 sibling. M2: `get_subgraph(symbol=<root-pkg>, depth=2, max_total=2000)`
for `{consensus/wbft, systemcontracts, core/txpool, core/types}`, serialized compactly. M3: `tool_broker`
+ `max_turns=8`, loop ends on envelope or max_turns. M4: single `get_for_task(query=question.prompt)`.
All four use the same Driver so token counts are commensurable. stablenet-knowledge tool failure → synthetic AskResult
`response_text="" + cks_error` → cell fails, run continues.

## Step 5 — envelope/extract
`Citation{file, start_line?, end_line?, symbol?}`; `ParsedResponse{answer, citations, parse_mode}`
(`strict|lenient|failed`). Extractor: strict JSON first; lenient regex-scan of prose `file:NN-MM` /
`path.go:LINE` next; else `failed` (zero citations + correctness False). Extractor never raises.

## Step 6 — scorers
`location.py`: P/R/F1 overlap matcher (Python port of `code-knowledge-system/internal/eval/metrics.go`).
`correctness.py`: `recall ≥ 0.5` AND first expected_keyword present AND any expected_keyword present.
`hallucination.py`: per citation — (1) file exists on disk, (2) if symbol given, stablenet-knowledge `find_symbol`
matches file, (3) line-range plausibility; plus prose `*.go:NN` scan. stablenet-knowledge empty → disk `exists()` +
`grep -n` fallback, record `cks_partial`. `info_volume.py`: `ask.input_tokens`.

## Step 7 — runner/state
`runner.run(manifest, continue_)`: load manifest → init/load state (cells = questions × methods) →
`validate_golden_set_against_cks` (fail-fast) → run `batch_size` pending cells → save state atomically →
print resume hint or build report. Per-cell `result.json`: location{p,r,f1}, correctness, hallucinations,
info_volume_tokens, parse_mode, ask{turns,output_tokens,transcript}. SIGINT writes state, exits 130.

## Step 8 — report
`build_report(exp_dir)` → `report/{report.md, report.json, report.csv}`. Rollup row:
`method | n | loc_p | loc_r | loc_f1 | correct_rate | hallucs | avg_input_tokens`. Per-question matrix.
Delta table: `M1_raw → M4_get_for_task | Δ_correct_rate | token_reduction_%`. Missing cell → "—", never crash.

## Step 9 — entry point
`run.py` argparse: `--manifest, --experiment, --continue, --driver, --batch-size`. `manifests/default.json`
pins `sha_pin=9978930ba…`, all 4 methods, 30 golden-set questions, `go_stablenet_root` absolute.

## Step 10 — tests + README
Per-module `unittest`; e2e replay test asserts report.md has all 4 method rows. README documents layout,
4×4 matrix, relationship to bench-orchestration/cks-eval (no duplication), SHA-pin policy, replay mode.

## Side-effect checklist (aggregate)
- Public interface: only new package; no external coupling. Cross-cutting dataclasses (AskResult,
  ParsedResponse, Citation) each defined once, imported elsewhere.
- Error paths: every external boundary (stablenet-knowledge tool, file IO, AI driver) returns structured failure
  (`cks_partial`, `parse_mode=failed`, `cell.status=failed`); runner never sees an uncaught raise.
- Concurrency: single-process sequential; atomic state.json rename. No shared mutable state.
- Reproducibility (AC#4): `sha_pin` + `validate_golden_set_against_cks` precheck + replay driver.

## Self-review
No inconsistent signatures, all nil/error paths covered, inter-step deps match plan.md, scale bounds
(M2 max_total, M3 max_turns) enforced. No v2 revision required; finalize under autonomy=auto.
