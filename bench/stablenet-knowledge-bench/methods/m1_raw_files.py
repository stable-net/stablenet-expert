"""m1_raw_files.py — Method 1: raw file contents from citation anchors.

Context strategy: read the full text of each file referenced in
``question.expected_citations``, plus up to one sibling file from the
same directory. This provides dense, exact context without any graph
traversal — the baseline for comparison.

Token budget: no hard cap; large files are included in full.
cks dependency: none (pure disk I/O).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from drivers.base import AskResult, Driver

# Shared system prompt preamble injected by every method.
_SYSTEM_PROMPT_PREAMBLE = """\
You are an expert Go and Solidity engineer working on the go-stablenet blockchain client.
Answer the question using ONLY the provided code context.
Respond in strict JSON with the following envelope:
{
  "answer": "<concise answer>",
  "citations": [
    {"file": "<relative path>", "start_line": <int or null>, "end_line": <int or null>, "symbol": "<optional>"}
  ]
}
Do not include any text outside the JSON object.
"""


def _read_file(path: str) -> Optional[str]:
    """Read a file; return None on error."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _find_sibling(directory: str, exclude: str) -> Optional[str]:
    """Return the path of one .go or .sol sibling in directory, excluding exclude."""
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return None
    for entry in entries:
        if entry == os.path.basename(exclude):
            continue
        if entry.endswith((".go", ".sol")):
            return os.path.join(directory, entry)
    return None


class M1RawFiles:
    """Method 1 — raw file context from anchor list plus one sibling."""

    method_id = "M1_raw"

    def __init__(self, go_stablenet_root: str) -> None:
        self._root = go_stablenet_root

    def build_prompt(self, question: Dict[str, Any]) -> tuple:
        """Return (system_prompt, user_prompt) for the question."""
        citations = question.get("expected_citations", []) or []

        # Collect unique files
        file_paths: List[str] = []
        seen = set()
        for cite in citations:
            rel = cite.get("file")
            if rel and rel not in seen:
                file_paths.append(rel)
                seen.add(rel)

        # Add one sibling per anchor file
        sibling_paths: List[str] = []
        for rel in list(file_paths):
            abs_path = os.path.join(self._root, rel)
            sibling = _find_sibling(os.path.dirname(abs_path), abs_path)
            if sibling:
                rel_sibling = os.path.relpath(sibling, self._root)
                if rel_sibling not in seen:
                    sibling_paths.append(rel_sibling)
                    seen.add(rel_sibling)

        all_files = file_paths + sibling_paths

        # Build context block
        context_parts: List[str] = []
        for rel in all_files:
            abs_path = os.path.join(self._root, rel)
            content = _read_file(abs_path)
            if content is None:
                context_parts.append(f"// --- FILE: {rel} (NOT FOUND ON DISK) ---\n")
            else:
                context_parts.append(f"// --- FILE: {rel} ---\n{content}\n")

        context_block = "\n".join(context_parts)

        system_prompt = _SYSTEM_PROMPT_PREAMBLE.strip()
        user_prompt = (
            f"CODE CONTEXT:\n{context_block}\n\n"
            f"QUESTION:\n{question.get('prompt', '')}"
        )
        return system_prompt, user_prompt

    def run(self, question: Dict[str, Any], driver: Driver) -> AskResult:
        """Run this method for a single question using the given driver."""
        system_prompt, user_prompt = self.build_prompt(question)
        try:
            return driver.ask(system_prompt, user_prompt, max_turns=1)
        except Exception as exc:
            return AskResult.from_error(f"M1 unexpected error: {exc}", driver_name=driver.name)
