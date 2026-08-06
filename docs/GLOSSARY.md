# Glossary

Every abbreviation and short identifier that appears in this repository's docs, agent
instructions, and skills. If a term is not here, it should not be abbreviated — see
[ADR-0016](adr/ADR-0016-naming-and-abbreviations.md) for the rule and why it exists.

## Systems and products

| Term | Stands for | What it is |
|------|-----------|------------|
| **cks** | code-knowledge-system | The retrieval system that answers "what does this code do / where is it". Upstream project name; this marketplace talks to its downstream fork through the `stablenet-knowledge` MCP server. |
| **ckg** | code-knowledge-graph | The symbol/relation graph component (callers, callees, imports, defines). |
| **ckv** | code-knowledge-vector | The embedding component. Uses `bge-m3` (1024-dim, multilingual). |
| **stablenet-knowledge** | — | The MCP server name this repository's agents actually call. Backed by the sibling `stablenet-knowledge-mcp` repository. Not an abbreviation, but easily confused with `cks` above: `cks` is the upstream project, `stablenet-knowledge` is the server surface used here. |
| **chainbench** | — | The multi-node integration harness the Evaluator drives in Stage 4. |
| **WBFT** | WEMIX Byzantine Fault Tolerance | go-stablenet's consensus engine (QBFT lineage, RPC namespace `istanbul`). Per the go-stablenet README. Some older notes expand this as "Weighted BFT" — that is incorrect. |
| **WKRC** | — | go-stablenet's native asset, a KRW-pegged stablecoin. Not an abbreviation of an English phrase. |

## Formats and general terms

| Term | Stands for |
|------|-----------|
| **ADF** | Atlassian Document Format — the rich-text shape Jira API v3 returns |
| **MCP** | Model Context Protocol |
| **ADR** | Architecture Decision Record — `docs/adr/` |
| **SSoT** | single source of truth |
| **RED / GREEN** | A test that fails / passes. "RED gate" = the reproduction must fail before a fix exists. |

## Identifiers used across files

These are real cross-references, not decoration. Each links documents that would otherwise
have no way to point at each other.

| ID | Meaning | Defined in |
|----|---------|-----------|
| **G1** | Goal: correctness and efficiency of the go-stablenet implementation | [VISION.md](VISION.md) |
| **G2** | Goal: reduce time, tokens, and headcount | [VISION.md](VISION.md) |
| **D-1** | Symptom-bound RED — the assertion that fails must be the one encoding the ticket's symptom, not a sibling | [reproduce-first/SKILL.md](../plugins/core-dev/skills/reproduce-first/SKILL.md) |
| **D-2** | Anti-pivot — a strong hypothesis that will not reproduce means the *setup* is wrong, not the hypothesis | [reproduce-first/SKILL.md](../plugins/core-dev/skills/reproduce-first/SKILL.md) |
| **D-3** | Idle / empty-block window primitive — required for staleness and "persists-then-clears" symptoms | [reproduce-first/SKILL.md](../plugins/core-dev/skills/reproduce-first/SKILL.md) |

## Retired identifiers

Do not introduce new references to these. They are listed so that old documents remain
readable.

| ID | What it was | Why it is retired |
|----|-------------|-------------------|
| **RI-nn** | "Review Issue" numbers from `coding-agent`'s `docs/archive/v1-build/plan/REVIEW_ISSUES.md` | That file lives in a different repository, under an archive of a superseded build. A reader here could never resolve the reference. The prose at each site already stated the requirement, so the markers were removed; the surviving mentions in [ADR-0013](adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md) are left in place because an ADR records history and is not rewritten. (`packages/jira-gateway-mcp/README.md` also carried some; it was deleted with the server when ADR-0013 was implemented.) |
| **RI-1..RI-11** (single digit) | The eleven StableNet domain invariants | The same prefix meant two unrelated things depending on the document. Benchmark docs now say "invariant *n*" and point at [invariants.md](../plugins/core-dev/domains/go-stablenet/invariants.md), which numbers them 1–11. |
| **C1, C4** | Contract IDs from a `HANDOFF.md` that was deleted | Replaced by the artefact they actually referred to — `scripts/contract/agent-mcp.schema.json`. |
| **R1′** | A revision label for the current architecture | Prefer describing the architecture directly. The prime symbol also makes the term hard to search for and to type. |
