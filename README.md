# stablenet-expert

**stablenet-expert** is a marketplace of [Claude Code plugins](https://docs.anthropic.com/en/docs/claude-code/plugins)
for developers building **go-stablenet** (a geth fork with WBFT consensus) and the apps that
run on it. From inside Claude Code, the plugins let you run a Jira-driven, autonomous
development pipeline against the node, write and review its Solidity system contracts, and keep
your local toolchain healthy.

Each plugin under `plugins/` is self-contained and installed independently — pick only the
ones you need.

## Install

### Using the Claude CLI

Register the marketplace, then install the meta-plugin first and run its diagnostics to confirm
your environment is ready:

```bash
claude plugin marketplace add stable-net/stablenet-expert
claude plugin install --scope user stablenet-expert@stablenet-expert
```

Restart Claude Code (slash commands from a plugin installed mid-session only register after a
restart — see the note below), then run:

```
/stablenet-expert:doctor
```

Then install whichever plugin(s) you actually need:

```bash
claude plugin install --scope user core-dev@stablenet-expert
claude plugin install --scope user contract-dev@stablenet-expert
```

Use `--scope user` to install **globally for your user** (available in every project),
`--scope project` for the current project only, or `--scope local` for an unmanaged local install.

### From within Claude Code

1. Run `/plugin` to open the plugin manager.
2. Choose **Add marketplace** and enter `stable-net/stablenet-expert` (or the full
   `https://github.com/stable-net/stablenet-expert` URL).
3. Use **Browse plugins** to pick which plugins to install — `stablenet-expert` (the meta-plugin,
   diagnostics) first, then `core-dev`/`contract-dev` as needed.

> **Note.** Slash commands from a plugin installed mid-session only register after you
> **restart Claude Code**. Skills and agents activate right away — if a command isn't found
> immediately after installing, restart and try again.

### Update / reinstall

Installing again over an existing install doesn't pull new content — refresh the marketplace
first, then reinstall:

```bash
claude plugin marketplace update stablenet-expert
claude plugin uninstall core-dev@stablenet-expert
claude plugin install --scope user core-dev@stablenet-expert
```

(Repeat the uninstall/install pair for whichever plugin(s) you need updated.) Restart afterward —
same rule as any other install.

### Uninstall

```bash
claude plugin uninstall core-dev@stablenet-expert
claude plugin uninstall contract-dev@stablenet-expert
claude plugin uninstall stablenet-expert@stablenet-expert
```

Add `--scope project` or `--scope local` if you installed with that scope instead of the
`user`-scope default. To also remove the marketplace registration itself (not just the plugins):

```bash
claude plugin marketplace remove stablenet-expert
```

## Plugins

### Ecosystem

<table>
  <thead>
    <tr><th>Plugin</th><th>Description</th></tr>
  </thead>
  <tbody>
  <tr>
    <td><strong><a href="plugins/stablenet-expert/">stablenet-expert</a></strong></td>
    <td>Meta-plugin (named after the marketplace itself). Ecosystem doctor — common toolchain prerequisites, plugin install/enable status, MCP server connectivity, and cross-plugin MCP server registration conflicts. Install this first.
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
    <td>Solidity smart contract authoring, review, and security audit for go-stablenet's embedded <code>systemcontracts/</code> (governance, minting, native-coin adapter).
    <pre lang="bash">claude plugin install --scope user contract-dev@stablenet-expert</pre></td>
  </tr>
  </tbody>
</table>

Each plugin has its own README with its full command list, configuration, and usage —
follow the plugin links in the tables above.

## Documentation

- **[docs/SETUP.md](docs/SETUP.md)** — full build, configure, index, and smoke-test guide
- **[docs/OVERVIEW.md](docs/OVERVIEW.md)** — architecture overview

## License

GNU Affero General Public License v3.0 (AGPL-3.0) — see [LICENSE](LICENSE).
