"""m3_incremental.py — Method 3: Python-driven incremental cks context assembly.

Context strategy: a Python tool-broker drives cks lookups incrementally
(semantic_search → find_symbol → get_subgraph as needed, max_turns=8),
assembles the evidence into a context block, then makes a single final
driver.ask() call with the assembled context.

This is deterministic and reliable: the Claude CLI never needs tool_use
support.  The Python broker controls which cks tools are called and in what
order, then all gathered evidence is concatenated and injected as context
for the final answer turn.

info_volume counts injected_tokens as sum of the injected context across
all turns (the assembly turns contribute to context size).

cks dependency: required for evidence assembly. If cks is unavailable,
falls back to empty context and the cell is flagged cks_partial.

max_turns default: 8 (per design — the broker may run up to 8 tool calls
before assembling the final prompt).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from drivers.base import AskResult, Driver
from methods.m1_raw_files import _SYSTEM_PROMPT_PREAMBLE

_MAX_TURNS_DEFAULT = 8

# The sequence of cks tools the broker tries, in order
_BROKER_SEQUENCE = [
    "semantic_search",
    "find_symbol",
    "get_subgraph",
]


def _count_injected(system_prompt: str, user_prompt: str) -> int:
    return (len(system_prompt) + len(user_prompt)) // 4


class _PythonBroker:
    """Drives cks lookups from Python and accumulates evidence blocks.

    Parameters
    ----------
    cks_tool : callable or None
        The cks dispatch callable.  If None all lookups return empty.
    max_turns : int
        Maximum number of cks tool calls to make.
    """

    def __init__(self, cks_tool: Optional[Callable], max_turns: int) -> None:
        self._cks = cks_tool
        self._max_turns = max_turns
        self._calls: List[Dict[str, Any]] = []
        self.partial = cks_tool is None

    def _do_call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._cks is None:
            self.partial = True
            return {"error": "cks not available", "results": []}
        try:
            result = self._cks(tool_name, args)
            self._calls.append({"tool": tool_name, "args": args, "ok": True})
            return result if isinstance(result, dict) else {"result": result}
        except Exception as exc:
            self.partial = True
            self._calls.append({"tool": tool_name, "args": args, "error": str(exc)})
            return {"error": str(exc), "results": []}

    def gather(self, query: str) -> Tuple[str, int]:
        """Run up to max_turns cks lookups for the query.

        Returns
        -------
        context_block : str
            Assembled context string to inject.
        total_injected : int
            Sum of len(each_call_prompt) // 4 across turns (measures how
            much context was produced / would have been injected per turn).
        """
        evidence_parts: List[str] = []
        calls_made = 0
        total_injected = 0

        # Turn 1: semantic_search
        if calls_made < self._max_turns:
            r = self._do_call("semantic_search", {"query": query})
            calls_made += 1
            r_str = json.dumps(r, separators=(",", ":"), ensure_ascii=False)
            evidence_parts.append(f"// --- semantic_search ---\n{r_str}")
            total_injected += len(r_str) // 4

        # Extract symbol names from semantic_search result for find_symbol
        symbols: List[str] = []
        if "results" in r and isinstance(r["results"], list):
            for item in r["results"][:3]:
                name = item.get("name") or item.get("symbol")
                if name:
                    symbols.append(name)

        # Turn 2+: find_symbol for each extracted symbol
        for sym in symbols[:2]:
            if calls_made >= self._max_turns:
                break
            r2 = self._do_call("find_symbol", {"name": sym})
            calls_made += 1
            r2_str = json.dumps(r2, separators=(",", ":"), ensure_ascii=False)
            evidence_parts.append(f"// --- find_symbol({sym!r}) ---\n{r2_str}")
            total_injected += len(r2_str) // 4

            # Turn N: get_subgraph for each symbol
            if calls_made < self._max_turns:
                r3 = self._do_call("get_subgraph", {"symbol": sym, "depth": 1, "max_total": 200})
                calls_made += 1
                r3_str = json.dumps(r3, separators=(",", ":"), ensure_ascii=False)
                evidence_parts.append(f"// --- get_subgraph({sym!r}, depth=1) ---\n{r3_str}")
                total_injected += len(r3_str) // 4

        context_block = "\n\n".join(evidence_parts)
        return context_block, total_injected


class M3Incremental:
    """Method 3 — Python-driven incremental cks lookup + single final ask."""

    method_id = "M3_incremental"

    def __init__(
        self,
        go_stablenet_root: str,
        cks_tool: Optional[Callable] = None,
        max_turns: int = _MAX_TURNS_DEFAULT,
    ) -> None:
        self._root = go_stablenet_root
        self._cks_tool = cks_tool
        self._max_turns = max_turns

    def build_prompt(
        self,
        question: Dict[str, Any],
        context_block: str = "",
        cks_partial: bool = False,
    ) -> tuple:
        """Return (system_prompt, user_prompt) with assembled cks context."""
        if context_block:
            ctx = f"// --- CKS INCREMENTAL CONTEXT ---\n{context_block}\n"
        else:
            ctx = "// [No incremental cks context available — cks returned error]\n"

        if cks_partial:
            ctx += "// [WARNING: cks_partial — context may be incomplete]\n"

        system_prompt = _SYSTEM_PROMPT_PREAMBLE.strip()
        user_prompt = (
            f"INCREMENTAL CKS CONTEXT:\n{ctx}\n"
            f"QUESTION:\n{question.get('prompt', '')}"
        )
        return system_prompt, user_prompt

    def run(self, question: Dict[str, Any], driver: Driver) -> AskResult:
        """Run M3 for a single question."""
        query = question.get("prompt", "")

        # Phase 1: Python broker gathers cks evidence
        broker = _PythonBroker(self._cks_tool, self._max_turns)
        context_block, broker_injected = broker.gather(query)
        cks_partial = broker.partial

        # Phase 2: single final driver.ask() with assembled context
        system_prompt, user_prompt = self.build_prompt(
            question, context_block=context_block, cks_partial=cks_partial
        )

        try:
            result = driver.ask(system_prompt, user_prompt, max_turns=1)

            # Add broker_injected to reflect total context gathered across turns
            total_injected = result.injected_tokens + broker_injected

            if cks_partial and result.ok:
                return AskResult(
                    response_text=result.response_text,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    injected_tokens=total_injected,
                    turns=result.turns,
                    transcript_path=result.transcript_path,
                    tool_calls=result.tool_calls,
                    error="cks_partial",
                    driver_name=result.driver_name,
                )

            return AskResult(
                response_text=result.response_text,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                injected_tokens=total_injected,
                turns=result.turns,
                transcript_path=result.transcript_path,
                tool_calls=result.tool_calls,
                error=result.error,
                driver_name=result.driver_name,
            )

        except Exception as exc:
            return AskResult.from_error(
                f"M3 unexpected error: {exc}", driver_name=driver.name
            )
