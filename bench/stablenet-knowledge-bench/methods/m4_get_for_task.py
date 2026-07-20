"""m4_get_for_task.py — Method 4: single get_for_task() EvidencePack.

Context strategy: call cks ``get_for_task(query=question.prompt)`` to get
a pre-assembled EvidencePack, then inject the pack content as context in a
single AI turn.

This is the most semantically targeted method — cks selects the relevant
code rather than the harness or the AI.

cks dependency: required. If cks is unavailable, the cell is marked
cks_partial (not hard-failed) and the AI is called with empty context so
the run continues.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from drivers.base import AskResult, Driver
from methods.m1_raw_files import _SYSTEM_PROMPT_PREAMBLE


def _call_get_for_task(
    cks_tool: Callable, query: str
) -> Dict[str, Any]:
    """Call cks get_for_task; return result or error dict."""
    try:
        # cks get_for_task requires the arg key ``prompt`` (NOT ``query``).
        # The wrong key returns an EMPTY pack (0 citations), silently crippling
        # M4 — the AI got no evidence and (correctly) said "no context", scoring
        # as a failure. This was a measurement bug, not an AI/retrieval failure.
        result = cks_tool("get_for_task", {"prompt": query})
        return result if isinstance(result, dict) else {"evidence": result}
    except Exception as exc:
        return {"error": str(exc), "evidence": []}


def _serialize_evidence_pack(pack: Dict[str, Any]) -> str:
    """Compact JSON serialization of an EvidencePack."""
    return json.dumps(pack, separators=(",", ":"), ensure_ascii=False)


class M4GetForTask:
    """Method 4 — single get_for_task() EvidencePack context."""

    method_id = "M4_get_for_task"

    def __init__(
        self,
        go_stablenet_root: str,
        cks_tool: Optional[Callable] = None,
    ) -> None:
        self._root = go_stablenet_root
        self._cks_tool = cks_tool

    def build_prompt(
        self,
        question: Dict[str, Any],
        evidence_pack: Optional[str] = None,
        cks_partial: bool = False,
    ) -> tuple:
        """Return (system_prompt, user_prompt)."""
        if evidence_pack:
            context_block = (
                f"// --- EVIDENCE PACK (cks.get_for_task) ---\n{evidence_pack}\n"
            )
        else:
            context_block = "// [No evidence pack available — cks returned error]\n"

        if cks_partial:
            context_block += "// [WARNING: cks_partial — evidence may be incomplete]\n"

        system_prompt = _SYSTEM_PROMPT_PREAMBLE.strip()
        user_prompt = (
            f"EVIDENCE PACK:\n{context_block}\n"
            f"QUESTION:\n{question.get('prompt', '')}"
        )
        return system_prompt, user_prompt

    def run(self, question: Dict[str, Any], driver: Driver) -> AskResult:
        """Run M4 for a single question."""
        query = question.get("prompt", "")
        cks_partial = False
        evidence_str: Optional[str] = None

        if self._cks_tool is not None:
            pack = _call_get_for_task(self._cks_tool, query)
            if "error" in pack:
                cks_partial = True
                evidence_str = None
            else:
                evidence_str = _serialize_evidence_pack(pack)
        else:
            cks_partial = True

        system_prompt, user_prompt = self.build_prompt(
            question, evidence_pack=evidence_str, cks_partial=cks_partial
        )

        try:
            result = driver.ask(system_prompt, user_prompt, max_turns=1)
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
            return AskResult.from_error(
                f"M4 unexpected error: {exc}", driver_name=driver.name
            )
