# ADR-0016 — Naming and abbreviations

- Status: Accepted
- Date: 2026-08-05
- Related: [GLOSSARY.md](../GLOSSARY.md)

## Context

An audit of this repository found short identifiers that no reader could resolve.

`RI-nn` appeared 31 times across 13 files, including production agent instructions
(`evaluator.md`, `analyzer.md`, `state-machine/SKILL.md`). It stands for "Review Issue" and is
defined in `coding-agent/docs/archive/v1-build/plan/REVIEW_ISSUES.md` — a different repository,
under an archive of a superseded build, which this repository does not carry. An agent or a
person reading `## 4. Stage 1 — Unit Test (RI-21)` had no way to learn what RI-21 required.

Worse, the same prefix meant two unrelated things. In `bench/stablenet-knowledge-bench/`,
`RI-1..RI-11` referred to the eleven StableNet domain invariants, not to review issues. One
directory used both schemes.

`C1` and `C4` had the same shape: contract identifiers from a `HANDOFF.md` that has since been
deleted. `SSoT` was used 14 times and never expanded. `WBFT` is expanded two different ways in
the wider corpus, one of them wrong.

These entered mostly through migration — `RI-nn` arrived with the `coding-agent` import
(`07f36e3`, `dbbcd19`). Without a rule, the next migration brings in the next set.

Counter-example from this same repository: `G1` and `G2` are defined where they are introduced,
in `VISION.md`, as `**G1 — 정확성·효율**`. That form costs nothing and works.

## Decision

**1. Do not invent new abbreviations.** Write the full word. `go_version`, not `gv`;
`plugin_path`, not `P`; `timestamp`, not `ts`. Length is not the scarce resource here.

**2. If an abbreviation is unavoidable, expand it at first use in each document and register it
in [GLOSSARY.md](../GLOSSARY.md).** Unavoidable means the abbreviation *is* the name — product
names (`cks`, `ckg`, `ckv`), protocol names (`MCP`), or established industry terms (`ADR`).

**3. An identifier must resolve inside this repository.** Never introduce an ID whose definition
lives in another repository, in an archive, or in a deleted document. If the definition cannot be
carried here, inline the meaning as prose instead of citing the ID.

**4. One prefix, one meaning.** Before reusing a prefix, grep for it.

**5. A provenance marker is not worth a reference.** "This section exists because of issue N" is
history, not instruction. If the requirement matters, the prose must state it; the marker then
adds nothing and can be dropped.

**6. Historical documents are exempt.** ADRs and the READMEs of retired components record what
was true when written and are not rewritten to satisfy this rule. Retired identifiers are listed
in GLOSSARY.md instead so old documents stay readable.

## Consequences

- Documents get slightly longer and considerably more self-contained.
- A reviewer has a concrete thing to ask for: "which glossary entry is this?"
- Product names are unaffected — `cks`/`ckg`/`ckv` keep their names and gain a glossary line.
- Files indexed as domain knowledge (`plugins/core-dev/domains/**`) are not edited to satisfy
  this rule, because changing their text shifts the chunks the retrieval system indexes and moves
  the evaluation baselines in `stablenet-knowledge-mcp`. Reference sites are expanded instead.
