#!/usr/bin/env python3
"""sync-mcp-namespace.py — enforce that every stablenet-knowledge tool reference
matches the single source (mcp-namespace.json).

The stablenet-knowledge MCP server's tool-name prefix is a runtime setting on
that server (namespace=cks today), not something this repo controls. Every
place this repo names a specific tool (agent-mcp.schema.json's tool keys,
ToolSearch "select:..." strings, pseudocode tool calls in agent .md files)
spells the prefix out literally — a classic dual/N-source that drifts the
moment the server's namespace changes. This makes mcp-namespace.json the one
source: this script verifies every literal reference matches it (and can
--apply the fix in one pass across scripts/contract/agent-mcp.schema.json and
every plugins/*/**/*.{md,py} file).

    python3 scripts/contract/sync-mcp-namespace.py            # verify; exit 1 on any drift
    python3 scripts/contract/sync-mcp-namespace.py --apply    # rewrite to match, then verify

Migration recipe: edit tool_prefix in mcp-namespace.json, then run with --apply.
Scope: production plugin + schema only (plugins/, scripts/contract/). bench/
also has cks_* references (its own MCP client code) but is dev tooling, not
shipped — out of scope here, see docs/WORKLIST.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                      # scripts/contract -> repo root
NAMESPACE = HERE / "mcp-namespace.json"
SCHEMA = HERE / "agent-mcp.schema.json"
PLUGINS_DIR = REPO / "plugins"


def _pattern(base_names: list[str]) -> re.Pattern:
    # Longest alternatives first so a shorter base name can't shadow a longer
    # one that starts the same way (e.g. ops_health vs ops_health_detail).
    #
    # Prefix group is non-greedy and allows SINGLE underscores (a tool_prefix
    # can be multi-word, e.g. stablenet_knowledge, not just cks — a
    # single-word-only prefix group would misread an already-correct
    # "stablenet_knowledge_context_*" as "knowledge" being a stale prefix).
    # But it must never swallow a DOUBLE underscore: "__" is the structural
    # mcp__<server>__<tool> delimiter, e.g.
    # "...stablenet-knowledge__cks_context_get_for_task" — crossing it would
    # merge "knowledge__cks" into one bogus "prefix". [A-Za-z0-9]+ (one-or-more,
    # not *) after each internal "_" enforces that: matching "__" would need
    # an EMPTY alnum run between the two underscores, which + forbids, so the
    # optional repetition simply can't extend across it — finditer instead
    # finds the correct, later match starting right after the "__" at "cks".
    # No leading \b: '_' is a word char, so there's no boundary between "__"
    # and "cks" to anchor on anyway; leftmost-match-wins scanning is what
    # ensures "cks" (not "ks") gets captured once a starting position works.
    alts = sorted((re.escape(b) for b in base_names), key=len, reverse=True)
    prefix = r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*?"
    return re.compile(r"(" + prefix + r")_(" + "|".join(alts) + r")\b")


def _expected(doc: dict) -> dict[str, str]:
    """{prefixed_name: base_name}, e.g. {'cks_ops_health': 'ops_health'}."""
    prefix = doc["tool_prefix"]
    return {f"{prefix}_{b}": b for b in doc["base_tool_names"]}


def _sync_schema(doc: dict, pattern: re.Pattern, apply: bool,
                  schema_path: Path) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    fixed: list[str] = []
    server, prefix = doc["server"], doc["tool_prefix"]
    want = _expected(doc)  # prefixed -> base

    schema = json.loads(schema_path.read_text())
    provider = schema.get("providers", {}).get(server)
    if provider is None:
        problems.append(f"{schema_path}: no provider '{server}' in schema")
        return problems, fixed
    current_keys = set(provider.get("tools", {}).keys())

    # map each current key to a recognized base name (via the shared pattern),
    # so a rename (old prefix -> new prefix) can find its old key even when
    # the whole key string changed.
    old_by_base: dict[str, str] = {}
    for k in current_keys:
        m = pattern.fullmatch(k)
        if m:
            old_by_base[m.group(2)] = k

    text = schema_path.read_text()
    changed = False
    for prefixed, base in want.items():
        old_key = old_by_base.get(base)
        if old_key is None:
            problems.append(f"{schema_path}: no tool key for base '{base}' (expected '{prefixed}')")
            continue
        if old_key == prefixed:
            continue
        if apply:
            old_lit, new_lit = json.dumps(old_key), json.dumps(prefixed)
            if old_lit not in text:
                problems.append(f"{schema_path}: could not locate literal key {old_lit} to rename")
                continue
            text = text.replace(old_lit, new_lit)
            changed = True
            fixed.append(f"{schema_path}: {old_key} -> {prefixed}")
        else:
            problems.append(f"{schema_path}: tool key '{old_key}' should be '{prefixed}'")

    recognized_old_keys = set(old_by_base.values())
    for k in current_keys - recognized_old_keys:
        problems.append(f"{schema_path}: tool key '{k}' does not match any base_tool_names entry")

    if apply and changed:
        schema_path.write_text(text)

    return problems, fixed


def _sync_plugin_files(prefix: str, pattern: re.Pattern, apply: bool,
                        plugins_dir: Path) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    fixed: list[str] = []

    targets = sorted(p for p in plugins_dir.rglob("*") if p.suffix in (".md", ".py"))
    for path in targets:
        text = path.read_text()
        matches = [(m.group(1), m.group(2)) for m in pattern.finditer(text)]
        stale = [(found_prefix, base) for found_prefix, base in matches if found_prefix != prefix]
        if not stale:
            continue
        if apply:
            new_text = text
            local: list[str] = []
            for found_prefix, base in sorted(set(stale)):
                old, new = f"{found_prefix}_{base}", f"{prefix}_{base}"
                if old in new_text:
                    new_text = new_text.replace(old, new)
                    local.append(f"{old} -> {new}")
            if new_text != text:
                path.write_text(new_text)
                for lf in local:
                    fixed.append(f"{path}: {lf}")
        else:
            for found_prefix, base in sorted(set(stale)):
                problems.append(f"{path}: '{found_prefix}_{base}' should be '{prefix}_{base}'")

    return problems, fixed


def check(apply: bool, *, namespace_path: Path = NAMESPACE, schema_path: Path = SCHEMA,
          plugins_dir: Path = PLUGINS_DIR) -> int:
    doc = json.loads(namespace_path.read_text())
    prefix = doc["tool_prefix"]
    pattern = _pattern(doc["base_tool_names"])

    schema_problems, schema_fixed = _sync_schema(doc, pattern, apply, schema_path)
    plugin_problems, plugin_fixed = _sync_plugin_files(prefix, pattern, apply, plugins_dir)

    problems = schema_problems + plugin_problems
    fixed = schema_fixed + plugin_fixed

    for f in fixed:
        print(f"applied: {f}")
    if problems:
        print(f"\nMCP-NAMESPACE DRIFT ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"mcp-namespace OK — {doc['server']} tools conform to mcp-namespace.json "
          f"(tool_prefix={prefix!r}, {len(doc['base_tool_names'])} tools)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="verify/apply the stablenet-knowledge MCP tool-name prefix")
    ap.add_argument("--apply", action="store_true",
                     help="rewrite references to match mcp-namespace.json")
    args = ap.parse_args(argv)
    rc = check(apply=args.apply)
    if args.apply and rc == 1:
        # after applying fixes, re-verify (unrecognized-key problems may remain)
        rc = check(apply=False)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
