---
description: Run the 3-way comparison bench. The same task runs autonomously in A (stablenet-knowledge) / B (code-only) / C (code+skills) mode, comparing tokens, cost, correctness and safety. Batched and resumable for token limits.
argument-hint: "<path to manifest.json> | <experiment-id>   (an id resumes a stopped experiment with --continue)"
---

# /core-dev:bench

The entry point for harness-engineering automation. It runs the same go-stablenet task
autonomously under three information regimes (A = stablenet-knowledge retrieval / B = code only /
C = code + comprehension skills) and compares {final-code correctness, tokens, cost, latency,
safety} with deterministic measurement tools.

The orchestration procedure, state and checkpoint contract live in the `bench-orchestration`
skill. This command is only the entry point — it calls the skill.

---

## 0. Argument shape

- **New experiment:** `/core-dev:bench bench/manifests/example.json`
  - Reads the manifest, creates `.stablenet-expert/bench/{experiment}/`, initializes the cells
    (task × mode) and runs the first batch.
- **Resume:** `/core-dev:bench gsn-retrieval-abc-2026-06 --continue`
  - Runs batch_size more pending cells of an existing experiment (token limits make running the
    whole matrix at once impossible).

## 1. What it does

```
1. Call the bench-orchestration skill (its §4 protocol):
   - new: copy the manifest + initialize state.json.
   - --continue: load the experiment directory.
2. MCP pre-flight: if the matrix includes A_stablenet_knowledge_mcp, confirm registration and env
   for stablenet-knowledge/jira/chainbench (reusing orchestrator §2.0). For B/C-only, proceed
   without stablenet-knowledge.
3. Take batch_size pending cells and run each:
   the per-mode ANALYSIS agent (analyzer | bench-analyzer-codeonly | bench-analyzer-skills)
   -> shared planner -> shared implementer -> shared evaluator. A transcript hook records
   sub-agent I/O into the cell workspace.
4. After the batch, call the measurement tool:
   bash: python3 bench/compare.py --experiment-dir .stablenet-expert/bench/{experiment}
   -> report/{comparison.md,json,csv}. Print the md summary table.
5. Report progress: point at `--continue` when cells remain, otherwise give the final report path.
```

## 2. Caveats

- **Token limits**: this runs plugin-native, inside the current session's budget. It runs only
  `manifest.batch_size` cells and stops. Run a large matrix in several passes with `--continue`.
- **Prerequisites for a real run**: A_stablenet_knowledge_mcp mode needs stablenet-knowledge-mcp
  (plus Ollama/bge-m3 and built ckv/ckg indexes) and chainbench (`docs/SETUP.md`). Without them
  stablenet-knowledge degrades, and that is recorded in the results as-is.
- **Bench isolation**: cell workspaces are created under `.stablenet-expert/bench/`, separate
  from `/work`'s `.stablenet-expert/tickets/`.

## 3. Example output (measurement tool)

```
| mode          | tasks | correct | avg_tokens | avg_cost($) | avg_latency(s) | safety_flags |
|---------------|-------|---------|------------|-------------|----------------|--------------|
| A_stablenet_knowledge_mcp         |   1   |   1/1   |   ...      |   ...       |   ...          |   0          |
| B_code_only   |   1   |   0/1   |   ...      |   ...       |   ...          |   1          |
| C_code_skills |   1   |   1/1   |   ...      |   ...       |   ...          |   0          |
```

The correctness, token and cost deltas between modes answer the §9 thesis with data: does
stablenet-knowledge beat grep and skills on accuracy and token count?
