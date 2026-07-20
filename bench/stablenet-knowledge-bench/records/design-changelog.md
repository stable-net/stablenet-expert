# Design Changelog — LOCAL-20260609_003552

## v1 (2026-06-09)
- v1 finalized under autonomy=auto; no revision needed; all side-effect checklists clean.
- Key decision: build a new sibling Q&A harness at `.stablenet-expert/bench/ckg-bench/` that reuses
  (a) cks-eval's `expected_citations` overlap matcher and (b) coding-agent `bench/lib/` token/report
  patterns, while adding the LLM-in-the-loop layer (4 method dispatchers + structured citation envelope
  + 4 metric scorers + live-cks hallucination verifier) absent from both existing assets.
