# stablenet-expert

**stablenet-expert** is a marketplace of [Claude Code plugins](https://docs.anthropic.com/en/docs/claude-code/plugins)
for developers building **go-stablenet** (a geth fork with WBFT consensus) and the apps that
run on it. The plugins help you run a Jira-driven, autonomous development pipeline against the
node itself, and — as the marketplace grows — write and review Solidity contracts, scaffold
dapp frontends, run quality/test gates, and manage the local toolchain, all from inside Claude
Code.

Modeled on the [`midnight-expert`](https://midnightntwrk.expert/) marketplace structure: the
repo root carries no functional content — every plugin under `plugins/` is self-contained and
independently installable.

## At a glance

- **1** plugin published today (`stablenet-core-dev`); 4 more categories planned (see below)
- Design rationale: [`docs/adr/ADR-0005-stablenet-expert-marketplace-split.md`](docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)

## Install

```bash
claude plugin marketplace add <stablenet-expert-url>
claude plugin install --scope user stablenet-core-dev@stablenet-expert
```

Or from inside Claude Code: run `/plugin`, choose **Add marketplace**, and browse plugins.

> **Note.** Slash commands from a plugin installed mid-session only register after you
> **restart Claude Code**. Skills and agents activate right away.

## Plugins

### Core Development

<table>
  <thead>
    <tr><th>Plugin</th><th>Description</th></tr>
  </thead>
  <tbody>
  <tr>
    <td><strong><a href="plugins/stablenet-core-dev/">stablenet-core-dev</a></strong></td>
    <td>Jira-driven automated development pipeline for go-stablenet — analyzes a ticket, plans, designs, implements, evaluates (unit+race/lint/security/chainbench), opens a PR, folds in review feedback, and merges.
    <pre lang="bash">claude plugin install --scope user stablenet-core-dev@stablenet-expert</pre></td>
  </tr>
  </tbody>
</table>

### Planned categories (not yet published)

These categories are scoped in [ADR-0005](docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)
but do not have plugin content yet — they are listed here so the marketplace shape is visible
ahead of the work landing.

| Category | Working name | Scope |
|---|---|---|
| Contract Development | `stablenet-contract-dev` | Solidity/EVM smart contract authoring, review, and security audit |
| DApp Development | `stablenet-dapp-dev` | Client SDK / frontend scaffolding for apps built on go-stablenet |
| Toolchain & Infrastructure | `stablenet-tooling` | Node/devnet/chainbench install, diagnostics, release notes |

**Test & Code Quality is not a separate plugin.** An earlier draft of ADR-0005 planned to split
`stablenet-core-dev`'s evaluator (unit+race/lint/security/chainbench checks) into a standalone
`stablenet-cq` plugin so other categories could reuse it. That was reconsidered and reversed
(ADR-0005 §2.3): the checks are Go/go-stablenet-specific (hardcoded around `go test`/
`golangci-lint`/`gosec`), so a Solidity-based `stablenet-contract-dev` couldn't actually reuse
them, and splitting would have added cross-plugin domain-pack/MCP-duplication costs for no real
reuse benefit. The evaluator stays inside `stablenet-core-dev`. If `stablenet-contract-dev` ever
needs its own verification plugin, it will be designed for that domain directly, not as a
generic wrapper around today's evaluator.

A `stablenet-expert` meta plugin (ecosystem doctor, cross-plugin dependency audit) is also
planned once there is more than one plugin to audit against.

## Repository layout

```
stablenet-expert/
├── .claude-plugin/marketplace.json   # marketplace manifest
├── packages/                         # shared, independently-buildable components
│   ├── jira-gateway-mcp/             # Go MCP: Jira proxy with sensitive-info filter
│   └── shared-patterns/patterns.json # sensitive-information policy (SSoT)
├── scripts/contract/                 # agent-facing MCP tool contract (SSoT) + drift lint
├── plugins/
│   └── stablenet-core-dev/           # the Claude Code plugin (see its own README)
├── docs/                             # SETUP, VISION, ADRs, system contract — repo-internal, not shipped in any plugin
├── bench/                            # 3-way (cks / code-only / code+skills) comparison harness — dev tooling, not shipped
└── HANDOFF.md                        # cross-session engineering context
```

## Documentation

- **[docs/SETUP.md](docs/SETUP.md)** — full build, configure, index, and smoke-test guide
- **[HANDOFF.md](HANDOFF.md)** — cross-session context: architecture, design decisions, roadmap
- **[docs/adr/](docs/adr/)** — architecture decision records, including the marketplace split (ADR-0005)
- **[scripts/contract/agent-mcp.schema.json](scripts/contract/agent-mcp.schema.json)** — the agent-facing tool contract

## License

Apache-2.0 — see [LICENSE](LICENSE).
