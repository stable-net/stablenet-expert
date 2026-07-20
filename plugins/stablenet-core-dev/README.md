# stablenet-core-dev

A Claude Code plugin that turns a Jira ticket into a reviewed pull request — autonomously.

`stablenet-core-dev` is the **core 개발** plugin of the [`stablenet-expert`](../../README.md)
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
   │  jira-gateway MCP  ── sensitive-info filter (secrets blocked before they reach the LLM)
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

It talks to three MCP servers: **jira-gateway** (in the `stablenet-expert` repo, a
sensitive-info proxy in front of Jira), **stablenet-knowledge** (`code-knowledge-system`, a sibling repo that
composes semantic + graph retrieval), and **chainbench** (a sibling repo, the deterministic
test runner). The agent-facing tool surface is frozen in
[`../../scripts/contract/agent-mcp.schema.json`](../../scripts/contract/agent-mcp.schema.json)
and enforced by [`../../scripts/contract/lint-tool-names.sh`](../../scripts/contract/lint-tool-names.sh).

**Security model.** Sensitive data is blocked *before it reaches the model*, not after. All
inbound Jira content passes through the jira-gateway filter (regex + entropy + allowlist →
`REDACTED`/`BLOCKED`); all outbound text (PR bodies, commit bodies, Jira comments) passes
through the `pr-sanitize` skill using the same
[`../../packages/shared-patterns/patterns.json`](../../packages/shared-patterns/patterns.json).

---

## Install

```
/plugin marketplace add <stablenet-expert-url>
/plugin install stablenet-core-dev@stablenet-expert
```

Restart Claude Code, then run `/help` — you should see `/stablenet-core-dev:work`,
`/stablenet-core-dev:review`, `/stablenet-core-dev:status`, and `/stablenet-core-dev:merge`.

> **Local development install.** To run from a clone instead, point your user config at the
> plugin directory:
> ```jsonc
> { "plugins": { "stablenet-core-dev": { "path": "/abs/path/to/stablenet-expert/plugins/stablenet-core-dev" } } }
> ```

---

## Configure

The plugin reads secrets and server locations from environment variables that `.mcp.json`
forwards into the MCP servers. Export them in your shell profile so Claude Code's child
processes inherit them.

```bash
# Jira (required) — token: https://id.atlassian.com/manage-profile/security/api-tokens
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_USER_EMAIL="you@example.com"
export JIRA_API_TOKEN="atlassian_api_token_here"

# stablenet-knowledge — the code-knowledge service (sibling repo; see ../../docs/SETUP.md to build)
export STABLENET_KNOWLEDGE_MCP_BIN="$HOME/Work/code-knowledge-system/bin/stablenet-knowledge-mcp"
export STABLENET_KNOWLEDGE_CONFIG="$HOME/Work/code-knowledge-system/cks.yaml"

# chainbench — the deterministic test runner (sibling repo)
export CHAINBENCH_DIR="$HOME/Work/chainbench"
```

| Requirement | Why |
|-------------|-----|
| Claude Code | Hosts the plugin |
| Atlassian (Jira) Cloud | Source of tickets |
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
| `/stablenet-core-dev:work STABLE-1234` | Main entry point. Reads the ticket, runs the full pipeline to a PR. `--local <ticket.json>` runs without Jira |
| `/stablenet-core-dev:analyze "<requirement>"` | Free-text autonomous entry — no Jira ticket needed |
| `/stablenet-core-dev:status [STABLE-1234]` | Progress of one ticket, or all active workspaces |
| `/stablenet-core-dev:review <PR-URL>` | Collect PR comments → classify → re-enter the pipeline in bugfix mode |
| `/stablenet-core-dev:merge STABLE-1234` | The only command that touches `main`: squash-merge (refuses unless approved + green + mergeable), then close the Jira ticket |
| `/stablenet-core-dev:doctor` | Read-only environment diagnostics |
| `/stablenet-core-dev:setup` | Check/register the settings the plugin needs |

Try a small bugfix ticket first, or do a no-Jira smoke test with `--local`
([../../docs/SETUP.md §7](../../docs/SETUP.md)).

---

## Documentation

- **[../../docs/SETUP.md](../../docs/SETUP.md)** — full build, configure, index, and smoke-test guide
- **[../../HANDOFF.md](../../HANDOFF.md)** — cross-session context: architecture, design decisions, roadmap
- **[../../scripts/contract/agent-mcp.schema.json](../../scripts/contract/agent-mcp.schema.json)** — the agent-facing tool contract
- **[../../docs/system-contract.md](../../docs/system-contract.md)** — the keystone system contract
- **[../../docs/adr/ADR-0005-stablenet-expert-marketplace-split.md](../../docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)** — why this plugin is scoped the way it is

## License

Apache-2.0 — see [../../LICENSE](../../LICENSE).
