# Setup Guide

This document gets you from "I just cloned the repo" to "I can run
`/core-dev:work-with-jira STABLE-1234` on go-stablenet". Follow the sections in
order; each one ends with a quick verification command so you know it worked.

If something fails, skip to [§9 Troubleshooting](#9-troubleshooting).

> **R1' architecture.** The core-dev plugin is the orchestrator/consumer. It talks to two MCP
> servers this repo owns — `stablenet-knowledge` (`stablenet-knowledge-mcp`, a sibling repo —
> the stablenet-specialized distribution of the upstream `knowledge-system` project, fusing ckv
> semantic + ckg graph retrieval behind one HTTP server) and `chainbench` (a sibling repo, the
> deterministic test runner) — plus one it doesn't: the official **Atlassian** MCP plugin for
> Jira (see §4.1; per [ADR-0013](adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md), the
> self-hosted `jira-gateway` this repo used to run has been retired). Unlike chainbench (launched
> per-session over stdio), `stablenet-knowledge` is a persistent HTTP server you start once and
> point `.mcp.json` at by URL — see §3.1/§4.2. ckv/ckg are dev-only and not reached directly. The
> agent-facing tool surface for this repo's own servers is frozen in
> `scripts/contract/agent-mcp.schema.json` (the Atlassian plugin's tools aren't this repo's to
> define a contract for).
>
> **`contract-dev`** (Solidity work on go-stablenet's embedded `systemcontracts/`) has **no MCP
> server** — it reads the checkout directly. See §5.3/§7.4. Never enable it and `core-dev`
> together with `coding-agent` (or any other plugin that also registers `stablenet-knowledge`) —
> §9.9 explains why.

---

## 1. Prerequisites

| Tool | Why | Check |
|------|-----|-------|
| Go ≥ 1.25 | Build the sibling stablenet-knowledge-mcp/chainbench Go wire | `go version` |
| C toolchain (cc/clang) | stablenet-knowledge links sqlite-vec (CGO) | `cc --version` |
| git ≥ 2.40 | Branch/commit/log throughout the pipeline | `git --version` |
| GitHub CLI (`gh`) ≥ 2.50 | PR creation, comments, status checks, merge | `gh auth status` |
| Claude Code | Hosts the plugin | (CLI/IDE) |
| Atlassian (Jira) Cloud account + official Atlassian MCP plugin | Source of tickets — see §4.1 for install + OAuth login, not an env var | `claude mcp list` |
| Ollama + `bge-m3` | Required for full stablenet-knowledge retrieval (semantic + intent) | `ollama list` |
| Python 3.12+ | core-dev 훅 4종(`git-guard`/`doc-guard`/`session-context`/`on-stop`), doctor의 check 스크립트, 각 플러그인의 `scripts/setup.py` — 없으면 doctor가 플러그인 셋업 자체를 못 한다([ADR-0015](adr/ADR-0015-python-interpreter-selection.md)) | `python3 --version` |

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

core-dev depends on two sibling repos resolved by path/URL at runtime
(not vendored): `stablenet-knowledge-mcp` (the `stablenet-knowledge` MCP server) and `chainbench`.

```bash
git clone <stablenet-expert-url> stablenet-expert
git clone <stablenet-knowledge-mcp-url> stablenet-knowledge-mcp
git clone <chainbench-url> chainbench
cd stablenet-expert
```

`stablenet-knowledge-mcp` is the stablenet-specialized distribution of the upstream
[`knowledge-system`](https://github.com/0xmhha/knowledge-system) project (three formerly-separate
repos — `code-knowledge-graph`/`code-knowledge-vector`/`code-knowledge-system` — consolidated into
one Go module). If you see `code-knowledge-system` referenced anywhere else, that's the old
pre-consolidation name for this same functionality.

The stablenet-expert layout you should see:

```
stablenet-expert/
├── plugins/
│   ├── core-dev/       # Claude Code plugin (commands, agents, skills, hooks)
│   │   └── .mcp.json           # MCP server registration (stablenet-knowledge, chainbench — Jira is the
│   │                            #   external Atlassian MCP plugin, not registered here, see §4.1)
│   └── contract-dev/   # Solidity plugin for go-stablenet's embedded systemcontracts/ — no .mcp.json (§5.3)
├── scripts/
│   └── contract/
│       ├── agent-mcp.schema.json   # single source of truth: every tool the agents may call (this repo's own servers only)
│       ├── mcp-namespace.json      # SSoT for stablenet-knowledge's tool-name prefix (cks vs stablenet_knowledge)
│       └── lint-tool-names.sh      # drift gate: prompt tool names must be in the schema
├── packages/
│   └── sensitive-guard/
│       └── patterns.json    # Sensitive-information policy, used by the pr-sanitize skill (outbound only —
│                              #   see ADR-0013 for why there's no inbound Jira filter anymore)
└── docs/                    # Specs and plans
```

---

## 3. Build the servers

### 3.1 stablenet-knowledge (sibling repo `stablenet-knowledge-mcp`, CGO)

stablenet-knowledge inherits sqlite-vec, so it needs `CGO_ENABLED=1` and a C
toolchain. `make build-mcp` builds the three MCP server binaries (`system-mcp` is the fused
server core-dev/contract-dev actually talk to; `graph-mcp`/`vector-mcp` are the standalone
engines, dev-only):

```bash
cd ../../../stablenet-knowledge-mcp
CGO_ENABLED=1 make build-mcp NAMESPACE=      # empty NAMESPACE — see the warning below
ls -l bin/system-mcp
```

> **`NAMESPACE=` (empty) is required, not optional.** `make build-mcp`'s **default** stamps
> the `stablenet_knowledge` tool-namespace root (`stablenet_knowledge.context.*`/
> `stablenet_knowledge.ops.*`), but `core-dev`/`contract-dev`'s current committed contract
> (`scripts/contract/mcp-namespace.json`, `tool_prefix: "cks"`) still expects the bare/upstream
> `cks.*` names. Building with the Makefile's own default silently produces a server neither
> plugin's prompts can call correctly. If that SSoT is ever migrated to `stablenet_knowledge`
> (see `docs/WORKLIST.md` §B / the namespace-migration ADRs), drop `NAMESPACE=` here and rerun
> `scripts/contract/sync-mcp-namespace.py --apply` in this repo to match.

Separately, build the dataset-build CLIs (needed for §6):

```bash
make build-dataset-bins   # produces bin/{knowledge-setup,ckg,ckv,filelist-gen,cks-domain-*}
```

### 3.2 chainbench (sibling repo, TS + Go wire)

chainbench is tri-language; the launcher needs the built TS bundle and the Go
wire binary:

```bash
cd ../chainbench
make build          # go build -> bin/{chainbench,chainbenchd,chainbench-mcp}
```

`chainbench-mcp` is a Go binary. `./install.sh` puts it on PATH; `.mcp.json` launches it by
name, so "not found or not executable" from doctor means this build has not been run.

(It was TypeScript once, and `mcp-server/` still holds a stale `node_modules` with no
`package.json` beside it. Nothing builds from there — do not follow an `npm run build` in an
older copy of these instructions.)

---

## 4. Configure environment variables

The plugin reads its secrets and server locations from environment variables
forwarded into the MCP servers via `plugins/core-dev/.mcp.json`. Set them once in your
shell profile so Claude Code's child processes inherit them.

### 4.1 Jira (required)

Per [ADR-0013](adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md), `core-dev` no longer
runs its own Jira MCP server — it uses the official **Atlassian** MCP plugin, a remote/OAuth
connector from Anthropic's own `claude-plugins-official` marketplace. This is **not** part of
this repo's own marketplace (`stablenet-expert`) and is **not** installed by the steps in §3 —
it's a separate, one-time setup on your own machine, and (since it's OAuth/identity-based) every
team member authenticates with their **own** Atlassian account, not a shared token.

> **Or let doctor do it.** `/stablenet-expert:doctor` reports this plugin's state alongside
> everything else and, if you pick it, runs the install and the OAuth login for you
> ([ADR-0017](adr/ADR-0017-setup-external-plugin-dependencies.md)). The steps below are the
> manual equivalent — useful when you want to do it yourself, or when doctor reports that the
> consent did not complete.

**Install the plugin** (skip the `marketplace add` if you've already added
`claude-plugins-official` for something else):

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install atlassian@claude-plugins-official
```

Restart Claude Code (plugin-provided MCP servers only register after a restart, same rule as
any other plugin install).

**Authenticate.** Either run this from your shell:

```bash
claude mcp login "plugin:atlassian:atlassian"
```

or, from inside a Claude Code session, run `/mcp`, select `atlassian`, and choose
**Authenticate** — either path opens a browser for Atlassian's OAuth login. Log in with the
Atlassian Cloud account that has access to your Jira site, and approve the permission grant.

Verify:

```bash
claude mcp list
```

Look for `plugin:atlassian:atlassian: https://mcp.atlassian.com/v1/mcp/authv2 (HTTP) - ✔ Connected`.
If it instead shows `! Needs authentication`, re-run the `claude mcp login` step above.

There is no `JIRA_API_TOKEN`/`JIRA_BASE_URL`/`JIRA_USER_EMAIL` to export anymore — those were
specific to the retired `jira-gateway` server (§9.2 has the current troubleshooting steps for
the OAuth-based flow).

### 4.2 stablenet-knowledge (required)

Unlike chainbench, `.mcp.json` does **not** launch stablenet-knowledge via stdio — it
connects to an **already-running HTTP server** by URL:

```json
"stablenet-knowledge": { "type": "http", "url": "${STABLENET_KNOWLEDGE_MCP_URL}" }
```

So there are two separate things to set up: the server's own config file, and the URL env var
that points `.mcp.json` at wherever you're running it.

**Server config** — `bin/system-mcp -config <mcp.yaml>` reads a single YAML file carrying the
ckv/ckg index paths, the go-stablenet source root, the embedder model, and the listen address:

```bash
cd ../../../stablenet-knowledge-mcp
cp projects/stablenet/mcp.yaml.example projects/stablenet/mcp.yaml   # gitignored, deployment-local
$EDITOR projects/stablenet/mcp.yaml
# Fill in the <angle-bracket> placeholders:
#   backends.ckg.path        -> <dataset>/graph/graph.db   (a FILE, not the graph dir — see §6)
#   backends.ckg.source_root -> the go-stablenet working tree you indexed
#   backends.ckv.path        -> <dataset>/vector           (a DIRECTORY)
#   backends.ckv.ollama_url  -> http://localhost:11434
#   listen.http_addr         -> 127.0.0.1:8930 for loopback-only, or 0.0.0.0:8930 + allow_remote:
#                                true if another machine/session needs to reach it
```

`bin/system-mcp gen-config -out <path> -dataset-dir <dataset> -source-root <checkout> ...` can
generate this file from flags instead of hand-editing the template — pass `-lan` to auto-fill a
remote-reachable listen address. Run either way, then start the server (it stays running — this
is a long-lived process, not something Claude Code launches per session):

```bash
./bin/system-mcp -config projects/stablenet/mcp.yaml &
```

**Point `.mcp.json` at it**:

```bash
export STABLENET_KNOWLEDGE_MCP_URL="http://127.0.0.1:8930/mcp"   # or the LAN IP if not loopback
```

That URL is the whole wiring. There is nothing else to export: the server runs elsewhere, so
this machine has no binary to point at and no `mcp.yaml` to validate.

`STABLENET_KNOWLEDGE_MCP_BIN` and `STABLENET_KNOWLEDGE_CONFIG` used to be set here for local
sanity checks. They are gone — they described a stdio deployment that `.mcp.json` no longer
declares, and on a machine that only *talks to* the index they either point at nothing or at an
unrelated checkout. Index health is checked live against the server that is actually serving,
via `cks_ops_health`.

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

Prerequisites (built in §3.2): `mcp-server/dist/index.js` and the
`network/chainbench-net` wire binary must exist. The Evaluator initializes the
network with `profile: "default"` — `default.yaml` IS the go-stablenet
(stablenet-adapter) profile; there is no separate `go-stablenet` profile.

---

## 5. Install the plugin(s) in Claude Code

`core-dev` lives at `stablenet-expert/plugins/core-dev/`; `contract-dev` at
`stablenet-expert/plugins/contract-dev/`. Point Claude Code at either via your user-level config
(§5.1, best for local development against an unpublished checkout), or add the `stablenet-expert`
marketplace and install by name (§5.3).

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

Restart Claude Code and run `/help`; you should see `/core-dev:work-with-jira`,
`/core-dev:work-with-prompt`, `/core-dev:review-jira`, `/core-dev:status`,
`/core-dev:merge`.

Open the MCP status panel (or run `claude mcp list`); **`stablenet-knowledge`, `chainbench`, and
`plugin:atlassian:atlassian`** should all show as connected. If one of the two servers this repo
registers fails to start, check the launching process's env — `.mcp.json` substitutes `${...}`
from the parent shell, so the variables from §4.2/§4.3 must be exported. If `atlassian` shows
unauthenticated instead, that's a §4.1 OAuth issue, not an env var — see §9.2.

Run the tool-name drift gate to confirm the prompts and the contract agree:

```bash
bash scripts/contract/lint-tool-names.sh        # exits 0 when there is no drift
```

### 5.3 Installing via the marketplace (either plugin)

```bash
claude plugin marketplace add <stablenet-expert-url-or-path>
claude plugin install core-dev@stablenet-expert
claude plugin install contract-dev@stablenet-expert   # optional — Solidity work only
```

`contract-dev` has **no MCP server and no env vars to configure** — it reads
`systemcontracts/` in your go-stablenet checkout directly via `Read`/`Grep`/`Glob`. Installing it
alongside `core-dev` is the normal case (full go-stablenet dev, contracts included) and is safe —
they don't share any server registration. What's **not** safe is enabling `core-dev` together
with `coding-agent` (a different marketplace/plugin that also registers `stablenet-knowledge`
under a different name) — see §9.9.

Whichever install method you used, slash commands only register after a session **restart**;
skills and agents activate immediately.

---

## 6. First-time indexing of go-stablenet

Before the Planner can retrieve anything, ckv and ckg must ingest the
go-stablenet working tree.

### 6.1 Build the dataset (`knowledge-setup`, sibling repo)

Don't call the `ckg`/`ckv` engine binaries directly for a first build — `knowledge-setup`
orchestrates both (graph build → vector build aligned to that graph → alignment verify) in one
pass. The stablenet pack ships a thin wrapper over it:

```bash
cd ../../../stablenet-knowledge-mcp
GSN_SRC=/abs/path/to/go-stablenet OUT=/abs/path/to/knowledge-data/stablenet \
  ./projects/stablenet/scripts/build-dataset.sh
# SKIP_CKV=1 ...   # graph only — skips the multi-hour Ollama embed, for a quick smoke test
```

This produces `<OUT>/graph/graph.db` and `<OUT>/vector/` — point `mcp.yaml`'s `backends.ckg.path`
and `backends.ckv.path` (§4.2) at exactly those two paths. A full bge-m3 embed of go-stablenet is
throughput-gated and can take hours — run it once on a capable machine. Afterwards the agent keeps
the index warm: the Planner calls `cks.ops.freshness` and, when stale, `cks.ops.index{mode:"incremental"}`.

> Production/shared deployments use the versioned `<family>@<ver>/` layout + blue-green promotion
> (`knowledge-setup --version <ver>` or the `cks.ops.reindex` MCP tool) instead of building
> straight into `OUT`, so a bad rebuild never breaks what's already being served. See
> `stablenet-knowledge-mcp/system/docs/ops-blue-green-reindex.md` — the single-checkout flow above
> is enough to get started.

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

### 7.1 First run without Jira — `/core-dev:work-with-prompt`

The quickest smoke test needs no ticket and no Atlassian setup: type the requirement.

`/core-dev:work-with-prompt` runs the same planner→implementer→evaluator pipeline
from a plain requirement string. It synthesizes a `ticket.json` internally and runs
with `requirement_source: "local"`.

```
/core-dev:work-with-prompt "consensus Finalize 의 nil pointer 패닉을 graceful skip 으로 고쳐줘"
```

You should see the Planner produce an `analysis.md`, and the pipeline stop politely
when it cannot find real code to change (or when it asks you to confirm).

To start from a Jira ticket instead, use `/core-dev:work-with-jira STABLE-1234` — that
path needs the Atlassian MCP installed and authenticated (§4.1).

Autonomy (set automatically for `work-with-prompt`; see state.config.autonomy):
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
> sensitive content, etc.). `work-with-prompt` is the autonomous, Jira-free entry.

### 7.2 Status check

```
/core-dev:status
/core-dev:status TEST-1
```

### 7.3 Cleanup

```bash
rm -rf .stablenet-expert/tickets/TEST-1_*
```

### 7.4 `contract-dev` smoke test (if installed)

No env vars, no MCP server — just compile+test go-stablenet's embedded Solidity contracts through
their actual toolchain (a custom Go wrapper around `solc`, not Foundry/Hardhat):

```
/contract-dev:test-contract
```

This should report `Compile: OK` and a full `go test ./systemcontracts/test/...` pass. Two things
that trip up a fresh checkout — both self-diagnosed by the command, see §9.9's sibling entries in
the plugin's own `systemcontracts-structure` skill if you hit either: the compiler binary's
default flags assume the wrong working directory, and
`systemcontracts/solidity/openzeppelin/{contracts,contracts-upgradeable}` are git submodules that
need `git submodule update --init` if you cloned go-stablenet without `--recurse-submodules`.

---

## 8. Wire in your real workflow

Once the smoke test passes:

1. Pick an actual Jira ticket. Try a small bugfix first.
2. Run `/core-dev:work-with-jira STABLE-XXXX`.
3. Watch the Orchestrator advance through ANALYSIS → PLANNING → DESIGN →
   IMPLEMENTATION → EVALUATION. The Implementer builds the modified binary at
   `build/bin/gstable`; the Evaluator hands that path to chainbench.
4. When the Evaluator reaches Stage 4 (ChainBench), it fails loudly if your
   chainbench MCP isn't wired up — a configuration problem, not a pipeline bug.
5. After EVALUATION_PASS, the Orchestrator creates a PR.
6. If reviewers leave comments, run `/core-dev:review-jira STABLE-XXXX`.
7. When ready, run `/core-dev:merge STABLE-XXXX` — the only command that
   touches `main`; it refuses unless the PR is approved, checks are green, and
   it's mergeable.

---

## 9. Troubleshooting

### 9.1 `MCP server 'stablenet-knowledge' is not connected`

- Check the server is actually **running** — `.mcp.json` connects over HTTP, it doesn't start it
  for you. `curl $STABLENET_KNOWLEDGE_MCP_URL/../healthz` (drop the `/mcp` suffix) should return
  `{"status":"ok", ...}`. If not, start it: `bin/system-mcp -config <mcp.yaml>` (§4.2).
- Check `STABLENET_KNOWLEDGE_MCP_URL` is exported and matches the address the server actually
  bound (its startup log prints `reachable at http://...`).
- Read the server's stderr. `Ollama unavailable` is a warning, not a fatal
  error: stablenet-knowledge boots in degraded (Smart Dummy) mode and `cks.ops.health` reports
  `degraded`.
- A CGO link error at build time means stablenet-knowledge was built without a C toolchain —
  rebuild with `CGO_ENABLED=1` (§3.1).
- Tool calls failing with `cks_context_*: tool not found` even though the server connects: the
  server's namespace and this repo's `scripts/contract/mcp-namespace.json` disagree — see the
  `NAMESPACE=` warning in §3.1.

### 9.2 `Jira: authentication failed` / MCP tool calls to Jira fail

Per §4.1, Jira now goes through the official Atlassian MCP plugin (OAuth), not an API token —
so this is no longer a "check env vars" problem:

- `claude mcp list` — confirm `plugin:atlassian:atlassian` shows `✔ Connected`, not
  `! Needs authentication`.
- If it shows unauthenticated, re-run `claude mcp login "plugin:atlassian:atlassian"` (or `/mcp`
  → `atlassian` → Authenticate) and complete the OAuth login again — tokens can expire or get
  revoked on the Atlassian side independent of anything in this repo.
- If a specific call still fails after that (e.g. `getJiraIssue` for a real ticket 404s), confirm
  the authenticated Atlassian account actually has access to that Jira site/project — this is a
  permissions question on Atlassian's side, not a Claude Code or plugin config issue.

### 9.3 `state.json transition blocked`

The pipeline refuses to advance when an artifact is missing or incomplete (by
design). The error lists the missing files. Fix the artifact (or delete a stale
workspace) and re-run `/core-dev:work-with-jira`.

### 9.4 `cks.ops.health reports degraded`

Ollama or bge-m3 is unavailable. Start Ollama (`ollama serve &`) and
`ollama pull bge-m3`, or accept degraded retrieval. The pipeline keeps running;
retrieval quality is just lower until the embedder is back.

### 9.5 `gh pr merge: PR is not mergeable`

The merge command checks: (1) PR approved, (2) all status checks succeeded,
(3) GitHub reports `mergeable: MERGEABLE`. If CHANGES_REQUESTED, run
`/core-dev:review-jira <TICKET>`. If CONFLICTING, resolve on the branch and push.

### 9.6 `Evaluator Stage 4: ChainBench MCP interface mismatch`

The expected tool names are the schema-declared set (`scripts/contract/agent-mcp.schema.json` —
`chainbench_init`, `chainbench_start`,
`chainbench_status`, `chainbench_test_run`, `chainbench_report`,
`chainbench_stop`). If the chainbench server is unregistered or its names
drift, reconcile against `scripts/contract/agent-mcp.schema.json` (provider
`chainbench`) and confirm §3.2/§4.4 prerequisites are built. The Evaluator
detects the mismatch before running so it doesn't leak processes.

### 9.7 `Jira: authentication failed` even though `claude mcp list` shows Connected

Historical note: this section number used to be "`jira-gateway: patterns.json not found`",
back when this repo ran its own Jira MCP server. Per
[ADR-0013](adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md) that server is retired —
see §9.2 for the current (OAuth-based) Jira troubleshooting steps. This entry number is kept
stable rather than renumbered, since `docs/adr/*` and other docs cite specific `§9.x` numbers
by value elsewhere in this repo.

`packages/sensitive-guard/patterns.json` is unaffected by any of this — it's read directly by
the `pr-sanitize` skill (outbound scrubbing), independent of which Jira backend is in use.

### 9.8 Hooks not firing

The hooks are best-effort logging; they never block the pipeline. If you don't
see entries in `{workspace}/logs/impl.log`, check the hook scripts have the
executable bit (`ls -l plugins/core-dev/hooks/*.sh`) and that `${CLAUDE_PLUGIN_ROOT}`
resolves in your Claude Code build.

### 9.9 One of `core-dev`/`contract-dev`'s MCP tools silently stops responding after enabling another plugin

**Never enable `core-dev` and `coding-agent` at the same time** (or any two plugins that both
register a `stablenet-knowledge`-equivalent server). They point at the identical server (same
`stablenet-knowledge-mcp` URL) under different plugin/server names.

This is not a server-side limitation — a single MCP server handling many concurrent clients is
completely normal. It's that Claude Code **deduplicates MCP server declarations by their resolved
endpoint** (URL for HTTP servers, resolved command+args for stdio servers), not by the name each
declaration is registered under. When two declarations from different scopes resolve to the same
endpoint, only the higher-precedence one actually connects — the precedence order is
**local > project > user > plugin-provided > connector** (see
[Scope hierarchy and precedence](https://code.claude.com/docs/en/mcp.md)). Since `core-dev` and
`coding-agent` are both plugin-provided and neither outranks the other by that rule, which one
"wins" is not something you should rely on — the losing plugin's copy silently shows as
disconnected for the whole session, with no error beyond "MCP server not connected".
`contract-dev` doesn't register any MCP server (§5.3), so it's always safe to run alongside either.

If you hit this: disable one of the two plugins (`~/.claude/settings.json`'s `enabledPlugins`,
or a project-local `.claude/settings.local.json` override to scope it to one project directory)
and restart. `/stablenet-expert:doctor`'s final step detects this pattern automatically across all
enabled plugins (not just this pair) and walks you through picking which one to keep.

---

## 10. What to look at next

- `scripts/contract/agent-mcp.schema.json` — the single source of truth for every agent-facing tool this repo
  owns (Jira, via the external Atlassian plugin, isn't in scope for this contract — see §4.1)
- `scripts/contract/mcp-namespace.json` — the SSoT for stablenet-knowledge's tool-name prefix
- the sibling `stablenet-knowledge-mcp` and `chainbench` repos — stablenet-knowledge and
  chainbench server documentation (start with `stablenet-knowledge-mcp/README.md`)
- [ADR-0013](adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md) — why Jira moved to the
  official Atlassian MCP plugin and what was traded off

When you're comfortable on a small ticket, scale up. The Orchestrator caps
automatic retries at `max_eval_cycles` (default 3) so the pipeline never spins
forever — see the BLOCKED state report and intervene manually when needed.
