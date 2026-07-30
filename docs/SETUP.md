# Setup Guide

This document gets you from "I just cloned the repo" to "I can run
`/core-dev:work STABLE-1234` on go-stablenet". Follow the sections in
order; each one ends with a quick verification command so you know it worked.

If something fails, skip to [§9 Troubleshooting](#9-troubleshooting).

> **R1' architecture.** The core-dev plugin is the orchestrator/consumer. It talks
> to three MCP servers: `jira-gateway` (in this repo), `stablenet-knowledge`
> (code-knowledge-system, a sibling repo that composes ckv semantic + ckg graph
> retrieval), and `chainbench` (a sibling repo, the deterministic test runner).
> ckv/ckg are dev-only and not reached directly. The agent-facing tool surface
> is frozen in `scripts/contract/agent-mcp.schema.json`.

---

## 1. Prerequisites

| Tool | Why | Check |
|------|-----|-------|
| Go ≥ 1.25 | Build jira-gateway + the sibling stablenet-knowledge/chainbench Go wire | `go version` |
| C toolchain (cc/clang) | stablenet-knowledge links sqlite-vec (CGO) | `cc --version` |
| Node ≥ 18 + npm | chainbench MCP server (TypeScript) | `node --version` |
| git ≥ 2.40 | Branch/commit/log throughout the pipeline | `git --version` |
| GitHub CLI (`gh`) ≥ 2.50 | PR creation, comments, status checks, merge | `gh auth status` |
| Claude Code | Hosts the plugin | (CLI/IDE) |
| Atlassian (Jira) Cloud account | Source of tickets | (web) |
| Ollama + `bge-m3` | Required for full stablenet-knowledge retrieval (semantic + intent) | `ollama list` |
| Python 3 | Lint script + ad-hoc JSON inspection | `python3 --version` |

A note on optionality:

- **Ollama + bge-m3** is load-bearing for retrieval quality. bge-m3 is
  multilingual (Korean + English), 1024-dim, and is shared by the intent
  classifier and the ckv embedder. Without it, stablenet-knowledge runs in a **degraded** mode
  (Smart Dummy embedder); the pipeline still works but retrieval quality drops,
  and `cks.ops.health` reports `degraded` so you know.
- **chainbench** is required for Stage 4 of the Evaluator. If you skip it, the
  Evaluator fails Stage 4 with a clear message identifying the missing MCP
  tools, and the rest of the pipeline still runs.

---

## 2. Clone the repositories

core-dev depends on two sibling repos resolved by path at runtime
(not vendored): `code-knowledge-system` (stablenet-knowledge) and `chainbench`.

```bash
git clone <stablenet-expert-url> stablenet-expert
git clone <code-knowledge-system-url> code-knowledge-system
git clone <chainbench-url> chainbench
cd stablenet-expert
```

The stablenet-expert layout you should see:

```
stablenet-expert/
├── plugins/
│   └── core-dev/  # Claude Code plugin (commands, agents, skills, hooks)
│       └── .mcp.json        # MCP server registration (jira-gateway, stablenet-knowledge, chainbench)
├── scripts/
│   └── contract/
│       ├── agent-mcp.schema.json   # C1 SSoT: every tool the agents may call
│       └── lint-tool-names.sh      # drift gate: prompt tool names must be in the schema
├── packages/
│   ├── jira-gateway-mcp/    # Sensitive-filter proxy in front of Jira REST API
│   └── sensitive-guard/
│       └── patterns.json    # Sensitive-information policy (jira-gateway)
└── docs/                    # Specs and plans
```

The stablenet-knowledge shim that used to live at `packages/stablenet-knowledge-mcp/` is gone —
stablenet-knowledge is the sibling `code-knowledge-system` repo now.

---

## 3. Build the servers

### 3.1 jira-gateway (in this repo)

```bash
cd packages/jira-gateway-mcp
go build -o bin/jira-gateway-mcp ./cmd/server
go test ./...
```

### 3.2 stablenet-knowledge (sibling repo, CGO)

stablenet-knowledge inherits sqlite-vec, so it needs `CGO_ENABLED=1` and a C
toolchain. Build the MCP binary into `bin/stablenet-knowledge-mcp`:

```bash
cd ../../../code-knowledge-system
CGO_ENABLED=1 make build-bins      # produces bin/stablenet-knowledge-mcp (+ cks-eval, etc.)
ls -l bin/stablenet-knowledge-mcp
```

### 3.3 chainbench (sibling repo, TS + Go wire)

chainbench is tri-language; the launcher needs the built TS bundle and the Go
wire binary:

```bash
cd ../chainbench
( cd mcp-server && npm install && npm run build )   # produces mcp-server/dist/index.js
go build -C network -o chainbench-net ./cmd/chainbench-net
```

The `chainbench-mcp` launcher (on PATH after `./install.sh`, or invoked
directly) execs `${CHAINBENCH_DIR}/mcp-server/dist/index.js`.

---

## 4. Configure environment variables

The plugin reads its secrets and server locations from environment variables
forwarded into the MCP servers via `plugins/core-dev/.mcp.json`. Set them once in your
shell profile so Claude Code's child processes inherit them.

### 4.1 Jira (required)

Create an API token at
<https://id.atlassian.com/manage-profile/security/api-tokens>.

```bash
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_USER_EMAIL="you@example.com"
export JIRA_API_TOKEN="atlassian_api_token_here"
```

Verify:

```bash
curl -s -u "$JIRA_USER_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/myself" | python3 -m json.tool | head -5
```

A successful call returns your account info. A 401 means the token or email
is wrong.

### 4.2 stablenet-knowledge (required)

stablenet-knowledge is config-file driven (a single `-config <cks.yaml>` flag); the YAML carries
the ckv/ckg index paths, the go-stablenet source root, the embedder model, and
the Ollama endpoint. Point `.mcp.json` at the built binary and a config file:

```bash
export STABLENET_KNOWLEDGE_MCP_BIN="$HOME/Work/code-knowledge-system/bin/stablenet-knowledge-mcp"
export STABLENET_KNOWLEDGE_CONFIG="$HOME/Work/code-knowledge-system/cks.yaml"
```

Create `cks.yaml` from the example and edit the paths:

```bash
cp "$HOME/Work/code-knowledge-system/policies/cks.yaml.example" "$STABLENET_KNOWLEDGE_CONFIG"
# In cks.yaml set:
#   backends.ckg.path        -> the ckg SQLite store (from `ckg build`)
#   backends.ckg.source_root -> the go-stablenet working tree
#   backends.ckv.path        -> the ckv vector store dir (from `ckv build`)
#   backends.ckv.embed_model -> bge-m3
#   backends.ckv.ollama_url  -> http://localhost:11434
```

### 4.3 Ollama + bge-m3 (required for full retrieval)

```bash
brew install ollama        # or per https://ollama.com/download
ollama serve &              # background daemon
ollama pull bge-m3          # multilingual, 1024-dim
```

Verify:

```bash
curl -s http://localhost:11434/api/embed \
  -d '{"model":"bge-m3","input":"hello"}' | head -c 80
```

A JSON body with an `embeddings` array confirms it works. If Ollama or bge-m3
is unavailable, stablenet-knowledge boots in degraded mode (Smart Dummy) and `cks.ops.health`
reports `degraded` — the pipeline does not crash.

### 4.4 chainbench (required for Evaluator Stage 4)

The `chainbench-mcp` launcher self-resolves `CHAINBENCH_DIR` from
`$HOME/.chainbench` by default; for a dev checkout point it explicitly:

```bash
export CHAINBENCH_DIR="$HOME/Work/chainbench"
```

Prerequisites (built in §3.3): `mcp-server/dist/index.js` and the
`network/chainbench-net` wire binary must exist. The Evaluator initializes the
network with `profile: "default"` — `default.yaml` IS the go-stablenet
(stablenet-adapter) profile; there is no separate `go-stablenet` profile.

---

## 5. Install the plugin in Claude Code

The plugin lives at `stablenet-expert/plugins/core-dev/`. Point Claude Code
at it via your user-level config, or add the `stablenet-expert` marketplace and
install `core-dev` from it.

### 5.1 Direct path install (recommended for local development)

```jsonc
{
  "plugins": {
    "core-dev": {
      "path": "/absolute/path/to/stablenet-expert/plugins/core-dev"
    }
  }
}
```

Claude Code's plugin loader discovers `plugins/core-dev/.claude-plugin/plugin.json`,
`plugins/core-dev/commands/*.md`, `plugins/core-dev/agents/*.md`,
`plugins/core-dev/skills/{name}/SKILL.md`,
`plugins/core-dev/hooks/hooks.json`, and `plugins/core-dev/.mcp.json`.

### 5.2 Verify Claude Code picks it up

Restart Claude Code and run `/help`; you should see `/core-dev:work`,
`/core-dev:analyze`, `/core-dev:review`, `/core-dev:status`,
`/core-dev:merge`.

Open the MCP status panel; **`jira-gateway`, `stablenet-knowledge`, and `chainbench`** should
all show as connected. If a server fails to start, check the launching
process's env — `.mcp.json` substitutes `${...}` from the parent shell, so the
variables from §4 must be exported.

Run the tool-name drift gate to confirm the prompts and the contract agree:

```bash
bash scripts/contract/lint-tool-names.sh        # exits 0 when there is no drift
```

---

## 6. First-time indexing of go-stablenet

Before the Planner can retrieve anything, ckv and ckg must ingest the
go-stablenet working tree.

### 6.1 Build the indexes (sibling stablenet-knowledge CLIs)

```bash
# Semantic (ckv) — requires Ollama + bge-m3; this is the slow one.
ckv build --src /abs/path/to/go-stablenet --out /abs/path/to/ckv-store \
          --embedder=ollama --model-name=bge-m3
# Graph (ckg)
ckg build --src /abs/path/to/go-stablenet --out /abs/path/to/ckg.db
```

Point the paths you used here at `cks.yaml` (§4.2). A full bge-m3 embed of
go-stablenet is throughput-gated and can take hours — run it once on a capable
machine. Afterwards the agent keeps the index warm: the Planner calls
`cks.ops.freshness` and, when stale, `cks.ops.index{mode:"incremental"}`.

### 6.2 Verify the index

Ask stablenet-knowledge (through Claude Code's MCP UI, or by asking the LLM to call the tool):

```jsonc
// cks.context.semantic_search
{ "query": "consensus finalize block", "k": 5 }
```

You should get results mentioning `consensus/...` symbols. For the graph:

```jsonc
// cks.context.get_subgraph
{ "symbol": "Finalize", "depth": 1 }
```

A non-empty subgraph indicates the graph was built. `cks.ops.health` should
report `ok` (or `degraded` if Ollama is down).

---

## 7. Smoke test the pipeline

### 7.1 Local-mode `/work` (no Jira)

```bash
cat > /tmp/test-ticket.json <<'EOF'
{
  "ticket_id": "TEST-1",
  "type": "Bug Fix",
  "summary": "Sample sanity ticket",
  "description": "## 작업 유형: Bug Fix\n## 요약\nNothing to do.\n## 재현 방법\n1. nothing\n## 기대 동작\nworks\n## 실제 동작\nworks\n## 영향 범위\n- 모듈: consensus\n- 심각도: low\n## 수용 기준\n- [ ] sample\n",
  "assignee": null,
  "status": "To Do",
  "status_category": "todo",
  "labels": [],
  "created": "2026-05-29T00:00:00Z",
  "updated": "2026-05-29T00:00:00Z",
  "_filter_metadata": { "scan_result": "CLEAN", "redacted_count": 0,
                        "redacted_patterns": [], "blocked_patterns": [],
                        "warnings": [], "scanned_at": "2026-05-29T00:00:00Z" }
}
EOF
```

Then in Claude Code:

```
/core-dev:work TEST-1 --local /tmp/test-ticket.json
```

You should see the Orchestrator pick up `TEST-1`, the Planner produce an
`analysis.md`, and the pipeline halt politely when it can't find real code to
modify (or when it asks you to confirm).

### 7.1b Free-text autonomous entry — `/analyze` (no Jira)

`/core-dev:analyze` runs the same planner→implementer→evaluator pipeline from a
plain requirement string — no Jira ticket, no `--local` JSON. It synthesizes a
`ticket.json` internally and runs with `requirement_source: "local"`.

```
/core-dev:analyze "consensus Finalize 의 nil pointer 패닉을 graceful skip 으로 고쳐줘"
```

Autonomy (set automatically for `/analyze`; see state.config.autonomy):
- **mode=auto** — no permission/decision prompts: entry-recovery, sanitize-REDACTED,
  branch/rebase conflicts, and design-revision/eval-cycle limits all auto-resolve
  (escalate → simplified retry → graceful `BLOCKED-summary.md`, never a silent halt).
- **auto_merge=false (default)** — autonomy stops at PR creation; the squash-merge to
  `main` stays the manual `/core-dev:merge`. Pass `--auto-merge` to let the pipeline
  merge/tag/push autonomously — its §3 safety preconditions (APPROVED / CI green /
  MERGEABLE) and destructive-git guards are **never** bypassed.

For hands-off tool use, run `/core-dev:setup --autonomous` first: it registers a
granular `permissions.allow` covering the pipeline's whole write path (Write/Edit,
go/make build, feature-branch git, `gh pr create`) plus a `permissions.deny` for
secret files — merge/tag stay prompted, and the git-guard hook's deny rules still
apply. `permissions.defaultMode: bypassPermissions` (see the go-stablenet
`scripts/coding-agent.sh` launcher) remains the blunt fallback for tools outside
that allowlist.

> `/work` remains the Jira-driven entry (interactive: prompts on BLOCKED recovery,
> sensitive content, etc.). `/analyze` is the autonomous, Jira-free entry.

### 7.2 Status check

```
/core-dev:status
/core-dev:status TEST-1
```

### 7.3 Cleanup

```bash
rm -rf .stablenet-expert/tickets/TEST-1_*
```

---

## 8. Wire in your real workflow

Once the smoke test passes:

1. Pick an actual Jira ticket. Try a small bugfix first.
2. Run `/core-dev:work STABLE-XXXX` without `--local`.
3. Watch the Orchestrator advance through ANALYSIS → PLANNING → DESIGN →
   IMPLEMENTATION → EVALUATION. The Implementer builds the modified binary at
   `build/bin/gstable`; the Evaluator hands that path to chainbench.
4. When the Evaluator reaches Stage 4 (ChainBench), it fails loudly if your
   chainbench MCP isn't wired up — a configuration problem, not a pipeline bug.
5. After EVALUATION_PASS, the Orchestrator creates a PR.
6. If reviewers leave comments, run `/core-dev:review <PR-URL>`.
7. When ready, run `/core-dev:merge STABLE-XXXX` — the only command that
   touches `main`; it refuses unless the PR is approved, checks are green, and
   it's mergeable.

---

## 9. Troubleshooting

### 9.1 `MCP server 'stablenet-knowledge' is not connected`

- Check `STABLENET_KNOWLEDGE_MCP_BIN` points at the built `bin/stablenet-knowledge-mcp` and `STABLENET_KNOWLEDGE_CONFIG` at a
  valid `cks.yaml`.
- Read the server's stderr. `Ollama unavailable` is a warning, not a fatal
  error: stablenet-knowledge boots in degraded (Smart Dummy) mode and `cks.ops.health` reports
  `degraded`.
- A CGO link error means stablenet-knowledge was built without a C toolchain — rebuild with
  `CGO_ENABLED=1` (§3.2).

### 9.2 `Jira: authentication failed`

- Re-issue the token: <https://id.atlassian.com/manage-profile/security/api-tokens>.
- Confirm `JIRA_USER_EMAIL` matches the account that owns the token.
- Try the `curl` from §4.1 to isolate token vs plugin.

### 9.3 `state.json transition blocked`

The pipeline refuses to advance when an artifact is missing or incomplete (by
design). The error lists the missing files. Fix the artifact (or delete a stale
workspace) and re-run `/core-dev:work`.

### 9.4 `cks.ops.health reports degraded`

Ollama or bge-m3 is unavailable. Start Ollama (`ollama serve &`) and
`ollama pull bge-m3`, or accept degraded retrieval. The pipeline keeps running;
retrieval quality is just lower until the embedder is back.

### 9.5 `gh pr merge: PR is not mergeable`

The merge command checks: (1) PR approved, (2) all status checks succeeded,
(3) GitHub reports `mergeable: MERGEABLE`. If CHANGES_REQUESTED, run
`/core-dev:review <PR-URL>`. If CONFLICTING, resolve on the branch and push.

### 9.6 `Evaluator Stage 4: ChainBench MCP interface mismatch`

The expected tool names are the C1 set (`chainbench_init`, `chainbench_start`,
`chainbench_status`, `chainbench_test_run`, `chainbench_report`,
`chainbench_stop`). If the chainbench server is unregistered or its names
drift, reconcile against `scripts/contract/agent-mcp.schema.json` (provider
`chainbench`) and confirm §3.3/§4.4 prerequisites are built. The Evaluator
detects the mismatch before running so it doesn't leak processes.

### 9.7 `jira-gateway: patterns.json not found`

The jira-gateway filter engine looks for `packages/sensitive-guard/patterns.json`
via `PATTERNS_PATH`, then relative paths, then `./packages/sensitive-guard/patterns.json`.
It fails closed (returns `BLOCKED`) rather than passing data unscanned. Set it
explicitly:

```bash
export PATTERNS_PATH="/absolute/path/to/stablenet-expert/packages/sensitive-guard/patterns.json"
```

stablenet-knowledge sanitization is separate — it is driven by `sanitize.rules_path` in
`cks.yaml`, not by an env var.

### 9.8 Hooks not firing

The hooks are best-effort logging; they never block the pipeline. If you don't
see entries in `{workspace}/logs/impl.log`, check the hook scripts have the
executable bit (`ls -l plugins/core-dev/hooks/*.sh`) and that `${CLAUDE_PLUGIN_ROOT}`
resolves in your Claude Code build.

---

## 10. What to look at next

- `scripts/contract/agent-mcp.schema.json` — the C1 SSoT for every agent-facing tool
- `packages/jira-gateway-mcp/README.md` — jira-gateway server documentation
- the sibling `code-knowledge-system` and `chainbench` repos — stablenet-knowledge and
  chainbench server documentation

When you're comfortable on a small ticket, scale up. The Orchestrator caps
automatic retries at `max_eval_cycles` (default 3) so the pipeline never spins
forever — see the BLOCKED state report and intervene manually when needed.
