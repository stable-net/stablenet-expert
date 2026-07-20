"""m2_graph_full.py — Method 2: full graph dump via get_subgraph.

Context strategy: call cks ``get_subgraph(symbol=<root_pkg>, depth=2,
max_total=2000)`` for each of the four canonical root packages, then
serialize the resulting subgraphs compactly and inject them as context.

Root packages (hard-coded, matching related-code.json):
  - consensus/wbft
  - systemcontracts
  - core/txpool
  - core/types

Token budget: max_total=2000 nodes per seed (cks enforces); if the
serialized context exceeds 100k chars, the cell is marked failed.

cks dependency: required. If cks returns an error, the driver is called
with a synthetic empty context and cell is flagged cks_partial.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from drivers.base import AskResult, Driver
from methods.m1_raw_files import _SYSTEM_PROMPT_PREAMBLE

_ROOT_PACKAGES = [
    "consensus/wbft",
    "systemcontracts",
    "core/txpool",
    "core/types",
]

# M2's premise is "the entire graph at once", so this cap is deliberately
# generous — it only guards against a pathological multi-hundred-k payload
# that would exceed the model context. ~300k chars ≈ ~75k tokens, well within
# Claude's window, and lets M2 honestly represent its info-heavy design as the
# high-information-volume contrast to M4's auto-selected pack.
_MAX_CONTEXT_CHARS = 300_000


def _call_get_subgraph(
    cks_tool: Callable, symbol: str, depth: int = 2, max_total: int = 2000
) -> Dict[str, Any]:
    """Call cks get_subgraph; return the result dict or an error dict."""
    try:
        result = cks_tool("get_subgraph", {
            "symbol": symbol,
            "depth": depth,
            "max_total": max_total,
        })
        return result if isinstance(result, dict) else {"nodes": result}
    except Exception as exc:
        return {"error": str(exc), "nodes": []}


def _serialize_subgraph(subgraph: Dict[str, Any]) -> str:
    """Compact JSON serialization of a subgraph result."""
    return json.dumps(subgraph, separators=(",", ":"), ensure_ascii=False)


class M2GraphFull:
    """Method 2 — full graph dump over 4 root packages (depth=2, max_total=2000)."""

    method_id = "M2_graph_full"

    def __init__(
        self,
        go_stablenet_root: str,
        cks_tool: Optional[Callable] = None,
    ) -> None:
        self._root = go_stablenet_root
        # cks_tool(tool_name, arguments) -> result; injected at run-time
        self._cks_tool = cks_tool

    def build_prompt(
        self,
        question: Dict[str, Any],
        subgraphs: Optional[List[str]] = None,
        cks_partial: bool = False,
    ) -> tuple:
        """Return (system_prompt, user_prompt).

        Parameters
        ----------
        subgraphs : list of serialized subgraph strings (already fetched)
        cks_partial : True when some subgraphs failed to load
        """
        if subgraphs is None:
            subgraphs = []

        context_block = ""
        for pkg, sg in zip(_ROOT_PACKAGES, subgraphs):
            context_block += f"// --- SUBGRAPH: {pkg} ---\n{sg}\n\n"

        if cks_partial:
            context_block += "// [WARNING: some subgraphs unavailable — cks returned error]\n"

        system_prompt = _SYSTEM_PROMPT_PREAMBLE.strip()
        user_prompt = (
            f"CODE KNOWLEDGE GRAPH CONTEXT:\n{context_block}\n"
            f"QUESTION:\n{question.get('prompt', '')}"
        )
        return system_prompt, user_prompt

    def _fetch_subgraphs(self) -> tuple:
        """Fetch subgraphs for all root packages; return (list_of_str, cks_partial)."""
        if self._cks_tool is None:
            return [], True

        results: List[str] = []
        partial = False
        for pkg in _ROOT_PACKAGES:
            sg = _call_get_subgraph(self._cks_tool, pkg)
            if "error" in sg:
                partial = True
                results.append(json.dumps({"error": sg["error"]}))
            else:
                results.append(_serialize_subgraph(sg))
        return results, partial

    def run(self, question: Dict[str, Any], driver: Driver) -> AskResult:
        """Run M2 for a single question."""
        subgraphs, cks_partial = self._fetch_subgraphs()
        system_prompt, user_prompt = self.build_prompt(
            question, subgraphs=subgraphs, cks_partial=cks_partial
        )

        # Token budget guard
        total_chars = len(system_prompt) + len(user_prompt)
        if total_chars > _MAX_CONTEXT_CHARS:
            return AskResult.from_error(
                f"M2 context too large ({total_chars} chars > {_MAX_CONTEXT_CHARS}); "
                "cell failed",
                driver_name=driver.name,
            )

        try:
            result = driver.ask(system_prompt, user_prompt, max_turns=1)
            # Tag cks_partial in error field if it happened (not a hard failure)
            if cks_partial and result.ok:
                return AskResult(
                    response_text=result.response_text,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    injected_tokens=result.injected_tokens,
                    turns=result.turns,
                    transcript_path=result.transcript_path,
                    tool_calls=result.tool_calls,
                    error="cks_partial",
                    driver_name=result.driver_name,
                )
            return result
        except Exception as exc:
            return AskResult.from_error(f"M2 unexpected error: {exc}", driver_name=driver.name)
