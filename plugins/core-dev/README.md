# core-dev

A Claude Code plugin that turns a Jira ticket into a reviewed pull request — autonomously.

`core-dev` is the **core 개발** plugin of the [`stablenet-expert`](../../README.md)
marketplace: a multi-agent development pipeline for **go-stablenet** (a geth fork with WBFT
consensus). You point it at a ticket; it analyzes, plans, designs, implements, tests, opens a
PR, folds in review feedback, and merges — pausing for your confirmation on anything
irreversible.

It is built on two ideas:

- **Orchestration over a document-backed state machine.** Every stage writes its artifact
  (`analysis.md`, `plan.md`, `design-v{N}.md`, `test-report.md`) to disk, so a truncated
  context or a new session resumes exactly where it left off.
- **Retrieval-grounded decisions.** Instead of guessing about a large unfamiliar codebase, the
  planner queries a knowledge service (**stablenet-knowledge**) with RAG (semantic search) and graph-RAG (call
  graphs, impact and concurrency analysis), and grounds every design choice in real code.

---

## How it works

```
Jira ticket (STABLE-xxxx)
   │  Atlassian MCP (official plugin, OAuth)
   ▼
TICKET_INTAKE → ANALYSIS → PLANNING → DESIGN → IMPLEMENTATION → EVALUATION → COMPLETION
                   │                                                │
              stablenet-knowledge retrieval                        4-stage gate
            (RAG + graph-RAG)                       (unit+race · lint · security · chainbench)
                                                                    │
                                                   PASS → PR + Jira update
                                                   FAIL → bugfix cycle (≤3) or BLOCKED
```

Four isolated agents do the work; the **orchestrator** is the only one that sees the whole flow:

| Agent | Role |
|-------|------|
| **orchestrator** | Drives state transitions, MCP pre-flight, PR/Jira completion, bug-cycle re-entry |
| **planner** | ANALYSIS / PLANNING / DESIGN. The sole stablenet-knowledge consumer — RAG + graph-RAG retrieval |
| **implementer** | Branch isolation, one commit per atomic step, build handoff |
| **evaluator** | 4-stage verification: unit (+`-race`), lint/format, security scan, chainbench integration |

It declares two MCP servers of its own — **stablenet-knowledge** (`code-knowledge-system`, a
sibling repo that composes semantic + graph retrieval) and **chainbench** (a sibling repo, the
deterministic test runner) — and reads Jira through the **official Atlassian MCP plugin**, an
external dependency that `/stablenet-expert:doctor` installs and authenticates for you
([ADR-0013](../../docs/adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md)). The agent-facing tool surface is frozen in
[`../../scripts/contract/agent-mcp.schema.json`](../../scripts/contract/agent-mcp.schema.json)
and enforced by [`../../scripts/contract/lint-tool-names.sh`](../../scripts/contract/lint-tool-names.sh).

**Security model.** Outbound text (PR bodies, commit bodies, Jira comments) passes through
the `pr-sanitize` skill before it is published, using
[`../../packages/sensitive-guard/patterns.json`](../../packages/sensitive-guard/patterns.json).

Inbound Jira content is **not** filtered. The retired `jira-gateway` server screened tickets
and comments before the model saw them; the official Atlassian MCP has no such stage, and
that protection was given up knowingly when it was adopted — see
[ADR-0013](../../docs/adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md) §2.3 for what
was traded for what. Treat a ticket body as untrusted input that the model will read in full.

---

## Install

```
/plugin marketplace add <stablenet-expert-url>
/plugin install core-dev@stablenet-expert
```

Restart Claude Code, then run `/help` — you should see `/core-dev:work-with-jira`,
`/core-dev:review-jira`, `/core-dev:status`, and `/core-dev:merge`.

> **Local development install.** To run from a clone instead, point your user config at the
> plugin directory:
> ```jsonc
> { "plugins": { "core-dev": { "path": "/abs/path/to/stablenet-expert/plugins/core-dev" } } }
> ```

---

## Configure

The plugin reads secrets and server locations from environment variables that `.mcp.json`
forwards into the MCP servers. Export them in your shell profile so Claude Code's child
processes inherit them.

```bash
# Jira needs no variables — the Atlassian MCP plugin authenticates over OAuth and Claude Code
# keeps the credential. `/stablenet-expert:doctor` installs and authenticates it.

# stablenet-knowledge — a remote HTTP service; ask whoever runs it for the URL
export STABLENET_KNOWLEDGE_MCP_URL="http://<host>:<port>/mcp"

# chainbench — the deterministic test runner (sibling repo)
export CHAINBENCH_DIR="$HOME/Work/chainbench"
```

| Requirement | Why |
|-------------|-----|
| Claude Code | Hosts the plugin |
| Atlassian (Jira) Cloud + the official Atlassian MCP plugin | Source of tickets — installed and authenticated by `/stablenet-expert:doctor` |
| `gh` CLI ≥ 2.50 | PR create / comment / merge |
| `code-knowledge-system` (stablenet-knowledge) + Ollama + `bge-m3` | Code retrieval (RAG + graph-RAG). Without it, stablenet-knowledge runs **degraded** and the pipeline still works at lower retrieval quality |
| `chainbench` | Evaluator Stage 4 (integration). Skippable; Stage 4 fails loudly if absent |

`code-knowledge-system` and `chainbench` are sibling repositories resolved by path at runtime.
Building and indexing them (the slow `bge-m3` embed of go-stablenet) is covered step by step in
**[../../docs/SETUP.md](../../docs/SETUP.md)**.

After install, verify the contract is intact:

```bash
bash ../../scripts/contract/lint-tool-names.sh    # exits 0 when prompt tool names match the schema
```

---

## Usage

| Command | What it does |
|---------|---------------|
| `/core-dev:work-with-jira STABLE-1234` | Start from a Jira ticket: reads it, then runs the full pipeline to a PR. Needs the Atlassian MCP |
| `/core-dev:work-with-prompt "<requirement>"` | Start from a requirement you type. Same pipeline, no Jira |
| `/core-dev:status [STABLE-1234]` | Progress of one ticket, or all active workspaces |
| `/core-dev:review-jira STABLE-1234` | Collect that ticket's PR comments → classify → re-enter the pipeline in bugfix mode |
| `/core-dev:review-pr <PR-URL>` | Review any PR in an isolated clone: invariants, blast radius, vulnerabilities. Approves or comments, after asking |
| `/core-dev:merge STABLE-1234` | The only command that touches `main`: squash-merge (refuses unless approved + green + mergeable), then close the Jira ticket |
| `/core-dev:doctor` | Read-only environment diagnostics |
| `/core-dev:setup` | Check/register the settings the plugin needs |

Try a small bugfix ticket first, or do a no-Jira smoke test with `work-with-prompt`
([../../docs/SETUP.md §7](../../docs/SETUP.md)).

---

## Documentation

- **[../../docs/SETUP.md](../../docs/SETUP.md)** — full build, configure, index, and smoke-test guide
- **[../../docs/OVERVIEW.md](../../docs/OVERVIEW.md)** — architecture overview + design decision log
- **[../../scripts/contract/agent-mcp.schema.json](../../scripts/contract/agent-mcp.schema.json)** — the agent-facing tool contract
- **[../../docs/adr/ADR-0005-stablenet-expert-marketplace-split.md](../../docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)** — why this plugin is scoped the way it is

## License

Apache-2.0 — see [../../LICENSE](../../LICENSE).
