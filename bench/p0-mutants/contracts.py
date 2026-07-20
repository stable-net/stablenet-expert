#!/usr/bin/env python3
"""contracts.py — extract the P0 machine-readable contract blocks from artifacts.

P0 (stream-6) made the planner emit two fenced ```yaml blocks that downstream
agents parse instead of prose:

  - plan-contract        (planner §4.5)  → `steps:` list   (Implementer §2.1)
  - write-site-contract  (planner §5.2b) → `sites:` list   (Implementer §4.2b, Evaluator §4.6c)

This module is the *deterministic reference parser* for those blocks. The
mutant-corpus scorer works on normalized case JSON, but this parser lets the
agent-in-the-loop layer (and a future PreToolUse lint hook) validate the blocks a
real planner actually wrote: same rules, no LLM.

Stdlib + PyYAML.
"""
from __future__ import annotations

import re
from typing import Any

import yaml

# A fenced yaml/yml block. Non-greedy body; DOTALL so it spans lines.
_FENCE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.DOTALL)


def extract_yaml_blocks(md_text: str) -> list[dict[str, Any]]:
    """Return every fenced yaml block in `md_text` that parses to a mapping."""
    blocks: list[dict[str, Any]] = []
    for m in _FENCE.finditer(md_text):
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            blocks.append(data)
    return blocks


def find_plan_contract(md_text: str) -> dict[str, Any] | None:
    """The plan-contract block: a mapping with a `steps:` list. None if absent."""
    for b in extract_yaml_blocks(md_text):
        if isinstance(b.get("steps"), list):
            return b
    return None


def find_write_site_contract(md_text: str) -> dict[str, Any] | None:
    """The write-site-contract block: has `sites:` (or at least `derived_state`)."""
    for b in extract_yaml_blocks(md_text):
        if isinstance(b.get("sites"), list) or "derived_state" in b:
            return b
    return None


# Prose headings the legacy (pre-P0) Implementer §2.1 parsed by regex.
_STEP_HEADING = re.compile(r"^##\s+Step\s+\d+\s*:", re.MULTILINE)


def count_prose_step_headings(md_text: str) -> int:
    """Count `## Step N:` headings the way the pre-P0 heading parser did.

    A malformed heading (e.g. `## Step 3 - foo`, missing the colon) is NOT
    counted — which is exactly the silent step-drop P0's plan-contract closes.
    """
    return len(_STEP_HEADING.findall(md_text))
