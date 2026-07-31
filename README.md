# stablenet-expert

**stablenet-expert** is a marketplace of [Claude Code plugins](https://docs.anthropic.com/en/docs/claude-code/plugins)
for developers building **go-stablenet** (a geth fork with WBFT consensus) and the apps that
run on it. The plugins help you run a Jira-driven, autonomous development pipeline against the
node itself, and — as the marketplace grows — write and review Solidity contracts, scaffold
dapp frontends, run quality/test gates, and manage the local toolchain, all from inside Claude
Code.

The repo root carries no functional content — every plugin under `plugins/` is self-contained
and independently installable.

## At a glance

- **3** plugins published today (`core-dev`, `contract-dev`, `stablenet-expert`); 2 more
  categories planned (see below)
- Design rationale: [`docs/adr/ADR-0005-stablenet-expert-marketplace-split.md`](docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)

## Install

Install the meta-plugin first and run its diagnostics to confirm your environment is ready:

```bash
claude plugin marketplace add <stablenet-expert-url>
claude plugin install --scope user stablenet-expert@stablenet-expert
```

```
/stablenet-expert:doctor
```

Then install whichever plugin(s) you actually need:

```bash
claude plugin install --scope user core-dev@stablenet-expert
claude plugin install --scope user contract-dev@stablenet-expert
```

Or from inside Claude Code: run `/plugin`, choose **Add marketplace**, and browse plugins.

> **Note.** Slash commands from a plugin installed mid-session only register after you
> **restart Claude Code**. Skills and agents activate right away.

## Plugins

### Ecosystem

<table>
  <thead>
    <tr><th>Plugin</th><th>Description</th></tr>
  </thead>
  <tbody>
  <tr>
    <td><strong><a href="plugins/stablenet-expert/">stablenet-expert</a></strong></td>
    <td>Meta-plugin (named after the marketplace itself). Ecosystem doctor — plugin install/enable status, cross-plugin MCP server registration conflicts. Install this first.
    <pre lang="bash">claude plugin install --scope user stablenet-expert@stablenet-expert</pre></td>
  </tr>
  </tbody>
</table>

### Core Development

<table>
  <thead>
    <tr><th>Plugin</th><th>Description</th></tr>
  </thead>
  <tbody>
  <tr>
    <td><strong><a href="plugins/core-dev/">core-dev</a></strong></td>
    <td>Jira-driven automated development pipeline for go-stablenet — analyzes a ticket, plans, designs, implements, evaluates (unit+race/lint/security/chainbench), opens a PR, folds in review feedback, and merges.
    <pre lang="bash">claude plugin install --scope user core-dev@stablenet-expert</pre></td>
  </tr>
  </tbody>
</table>

### Contract Development

<table>
  <thead>
    <tr><th>Plugin</th><th>Description</th></tr>
  </thead>
  <tbody>
  <tr>
    <td><strong><a href="plugins/contract-dev/">contract-dev</a></strong></td>
    <td>Solidity smart contract authoring, review, and security audit for go-stablenet's embedded <code>systemcontracts/</code> (governance, minting, native-coin adapter). 1st-stage scope only — see <a href="docs/adr/ADR-0009-contract-dev-plugin-design.md">ADR-0009</a>.
    <pre lang="bash">claude plugin install --scope user contract-dev@stablenet-expert</pre></td>
  </tr>
  </tbody>
</table>

### Planned categories (not yet published)

These categories are scoped in [ADR-0005](docs/adr/ADR-0005-stablenet-expert-marketplace-split.md)
but do not have plugin content yet — they are listed here so the marketplace shape is visible
ahead of the work landing.

| Category | Working name | Scope |
|---|---|---|
| Toolchain & Infrastructure | `stablenet-tooling` | Node/devnet/chainbench install, diagnostics, release notes |
| Test & QA | `stablenet-qa` | Cross-project test/quality-gate tooling — **not currently planned as a standalone plugin, see caveat below** |

**Test & QA is not a separate plugin today.** An earlier draft of ADR-0005 planned to split
`core-dev`'s evaluator (unit+race/lint/security/chainbench checks) into a standalone
`stablenet-cq` plugin so other categories could reuse it. That was reconsidered and reversed
(ADR-0005 §2.3): the checks are Go/go-stablenet-specific (hardcoded around `go test`/
`golangci-lint`/`gosec`), so a Solidity-based `contract-dev` couldn't actually reuse
them, and splitting would have added cross-plugin domain-pack/MCP-duplication costs for no real
reuse benefit. The evaluator stays inside `core-dev`. `stablenet-qa` is listed above only as a
**future-reconsideration candidate** — e.g. if `contract-dev` eventually needs its own
verification plugin, it would be designed for that domain directly, not as a generic wrapper
around today's evaluator, and that design work would revisit this row.

A `stablenet-expert` meta plugin (ecosystem doctor, cross-plugin dependency audit) is also
planned once there is more than one plugin to audit against.

## Repository layout

```
stablenet-expert/
├── .claude-plugin/marketplace.json   # marketplace manifest
├── packages/                         # shared, independently-buildable components
│   ├── jira-gateway-mcp/             # Go MCP: Jira proxy with sensitive-info filter
│   └── sensitive-guard/patterns.json # sensitive-information policy (SSoT)
├── scripts/contract/                 # agent-facing MCP tool contract (SSoT) + drift lint
├── plugins/
│   └── core-dev/                     # the Claude Code plugin (see its own README)
├── docs/                             # SETUP, VISION, OVERVIEW, ADRs, WORKLIST — repo-internal, not shipped in any plugin
└── bench/                            # 3-way (stablenet-knowledge / code-only / code+skills) comparison harness — dev tooling, not shipped
```

## Documentation

- **[docs/SETUP.md](docs/SETUP.md)** — full build, configure, index, and smoke-test guide
- **[docs/OVERVIEW.md](docs/OVERVIEW.md)** — architecture overview + design decision log
- **[docs/adr/](docs/adr/)** — architecture decision records, including the marketplace split (ADR-0005)
- **[scripts/contract/agent-mcp.schema.json](scripts/contract/agent-mcp.schema.json)** — the agent-facing tool contract

## License

GNU Affero General Public License v3.0 (AGPL-3.0) — see [LICENSE](LICENSE).
