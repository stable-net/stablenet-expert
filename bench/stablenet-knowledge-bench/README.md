# CKG Benchmark

Automated evaluation pipeline that measures whether the **stablenet-knowledge Code Knowledge
Graph** improves AI code understanding of go-stablenet.

---

## Layout

```
.stablenet-expert/bench/stablenet-knowledge-bench/
├── README.md
├── qa-manifest.schema.json    # JSON Schema for manifest files
├── __init__.py
├── run.py                     # CLI entrypoint
├── runner.py                  # Per-cell run loop + resume
├── state.py                   # Atomic run-state management
├── report.py                  # Report aggregation (md/csv/json)
├── validate_golden.py         # Golden-set pre-flight validator
│
├── manifests/
│   └── default.json           # Default manifest (replay driver, all 30 Qs)
│
├── golden-set/                # 30 known-answer questions
│   ├── index.yaml
│   ├── G01.yaml … G30.yaml
│
├── drivers/                   # AI driver implementations
│   ├── base.py                # AskResult, Driver protocol
│   ├── replay.py              # Offline/CI deterministic driver
│   └── claude_cli.py          # Live Claude CLI driver
│
├── methods/                   # Context-provision method dispatchers
│   ├── m1_raw_files.py        # M1: raw file contents from anchors
│   ├── m2_graph_full.py       # M2: get_subgraph (depth=2, max=2000)
│   ├── m3_incremental.py      # M3: multi-turn stablenet-knowledge tool loop
│   └── m4_get_for_task.py     # M4: single get_for_task EvidencePack
│
├── bench_io/                  # Structured-response parsing
│   ├── envelope.py            # Citation, ParsedResponse dataclasses
│   └── extract.py             # strict→lenient→failed cascade
│
├── scorers/                   # Four metric scorers
│   ├── location.py            # P/R/F1 overlap matcher
│   ├── correctness.py         # recall≥0.5 + keyword check
│   ├── hallucination.py       # file+symbol+line-range verifier
│   └── info_volume.py         # input token count
│
├── tests/                     # Unit and integration tests
│   ├── test_drivers.py
│   ├── test_extract.py
│   ├── test_scorers.py
│   ├── test_runner.py
│   ├── test_report.py
│   └── test_e2e_replay.py
│
└── runs/                      # Experiment output (gitignored in live use)
    └── ckg-bench-default/     # Default run artifacts
```

---

## 4 Methods × 4 Metrics

| Method | Context strategy | stablenet-knowledge dependency |
|--------|-----------------|----------------|
| **M1_raw** | Full file contents from citation anchors + 1 sibling | None (disk I/O) |
| **M2_graph_full** | `get_subgraph(depth=2, max_total=2000)` for 4 root packages | Required |
| **M3_incremental** | Multi-turn tool-broker loop (max 8 turns) | Required |
| **M4_get_for_task** | Single `get_for_task(query)` EvidencePack | Required |

| Metric | Description |
|--------|-------------|
| **loc_f1** | Location F1 — precision/recall overlap of cited file+range vs expected |
| **correct_rate** | Boolean: loc_recall≥0.5 AND first+any expected_keyword present |
| **hallucinations** | Citations that fail file-exists / line-range / symbol checks |
| **info_volume** | Input tokens consumed (lower = more targeted context) |

---

## Quick Start

```bash
# Run tests offline (no AI, no stablenet-knowledge)
python3 -m unittest discover -s .stablenet-expert/bench/stablenet-knowledge-bench/tests

# Validate golden-set against repo
python3 .stablenet-expert/bench/stablenet-knowledge-bench/validate_golden.py --offline

# Dry run (validate + print plan, no LLM calls)
python3 .stablenet-expert/bench/stablenet-knowledge-bench/run.py \
  --manifest .stablenet-expert/bench/stablenet-knowledge-bench/manifests/default.json \
  --dry-run

# Replay run (deterministic, no live AI)
python3 .stablenet-expert/bench/stablenet-knowledge-bench/run.py \
  --manifest .stablenet-expert/bench/stablenet-knowledge-bench/manifests/default.json \
  --driver replay

# Resume interrupted run
python3 .stablenet-expert/bench/stablenet-knowledge-bench/run.py \
  --manifest .stablenet-expert/bench/stablenet-knowledge-bench/manifests/default.json \
  --continue

# Live run (requires claude CLI + stablenet-knowledge MCP server)
python3 .stablenet-expert/bench/stablenet-knowledge-bench/run.py \
  --manifest .stablenet-expert/bench/stablenet-knowledge-bench/manifests/default.json \
  --driver claude_cli
```

---

## Golden-Set (30 questions)

Composition:
- **G01–G10** (10): Seeded from cks-eval scenario anchors (SN01–SN10)
- **G11–G21** (11): One question per StableNet invariant 1..11
  (`plugins/core-dev/domains/go-stablenet/invariants.md` — the 11 numbered entries; these are domain invariants, not review issues)
- **G22–G27** (6): Hotspot probes for recent bugfix commits
  (race in newRoundChangeTimer c37994e9b, WBFT justification forgery 9978930ba,
  zero-balance alloc 3eada119e, AnzeonTipEnv refresh 98f05c2a0,
  txpool fee-delegation balance fix)
- **G28–G30** (3): Cherry-pick boundary probes distinguishing geth from
  StableNet glue (handler_istanbul.go, tx_fee_delegation.go, quorum_protocol.go)

All questions are validated offline against the repo via `validate_golden.py`.

---

## SHA-Pin Policy

The manifest `sha_pin` field records the go-stablenet commit at which the
golden-set was authored. `validate_golden.py` checks file existence and
line-range bounds against the current checkout; any drift causes a
pre-flight failure before any LLM call.

For live stablenet-knowledge runs (M2/M3/M4), `validate_golden.py --cks-host <url>` also
calls `find_symbol()` to verify symbol locations match the CKG's indexed_head.

---

## Replay Mode

The `replay` driver returns canned responses keyed by the SHA-256 of
`(system_prompt, user_prompt)`. Use `ReplayDriver.write_fixture()` to
record new responses:

```python
from drivers.replay import ReplayDriver
ReplayDriver.write_fixture(
    replay_dir="tests/fixtures/replay",
    system_prompt=...,
    user_prompt=...,
    response_text='{"answer": "...", "citations": [...]}',
    input_tokens=1234,
)
```

Non-strict mode (`strict=False`) returns a placeholder response on cache
miss — use this for unit tests that do not care about LLM output quality.

---

## Relationship to bench-orchestration and cks-eval

This harness is **separate** from the existing bench-orchestration 3-way
harness (which compares `N_chat / A_raw / A_stablenet_knowledge_mcp` coding task performance).
It is also separate from the Go `code-knowledge-system/cmd/cks-eval` tool
(which evaluates stablenet-knowledge precision/recall against YAML scenarios).

- bench-orchestration: coding task completion quality
- cks-eval: CKG retrieval quality
- **stablenet-knowledge-bench (this)**: AI answer quality with different CKG context strategies

The golden-set YAML schema is compatible with cks-eval v1 (additive fields
only), so questions can be cross-referenced.

---

## go test / ChainBench Note

No go-stablenet production code is modified by this harness.
`go build ./...` and `go test -race ./...` are not applicable here.
ChainBench is not applicable. (The skip is recorded explicitly.)
