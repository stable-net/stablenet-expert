"""base.py — AskResult dataclass and Driver Protocol for the CKG Benchmark harness.

All concrete drivers (claude_cli, replay) implement the Driver Protocol.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation made by the AI during a multi-turn exchange."""

    turn: int
    name: str
    arguments: Dict[str, Any]
    result: Any = None


@dataclass
class AskResult:
    """Result of a single Driver.ask() call.

    Fields
    ------
    response_text : str
        The final response text from the AI (last turn in a multi-turn exchange).
    input_tokens : int
        Total input tokens billed by the CLI/API across all turns.  This includes
        Claude Code's own system-prompt overhead and is NOT used for the
        info_volume metric.  Kept for cost accounting only.
    output_tokens : int
        Total output tokens generated across all turns.
    injected_tokens : int
        Token count of the context the harness *injected* (system_prompt +
        user_prompt the method builds), measured as ``len(text) // 4``.  This
        is what the info_volume metric uses, so M1-vs-M4 comparisons are fair
        (constant CLI overhead is excluded).  For M3 multi-turn this is the
        sum across all turns of the injected context for each turn.
    turns : int
        Number of AI turns taken (1 for single-shot drivers).
    transcript_path : Optional[str]
        Absolute path to the JSONL transcript file if the driver wrote one, else None.
    tool_calls : List[ToolCall]
        Ordered list of tool invocations during the exchange (M3 multi-turn only).
    error : Optional[str]
        Non-None if the driver encountered an error; response_text may be empty.
    driver_name : str
        Identifies the driver that produced this result.
    """

    response_text: str
    input_tokens: int
    output_tokens: int
    injected_tokens: int = 0
    turns: int = 1
    transcript_path: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    error: Optional[str] = None
    driver_name: str = "unknown"

    @classmethod
    def from_error(cls, error: str, driver_name: str = "unknown") -> "AskResult":
        """Convenience constructor for failed cells."""
        return cls(
            response_text="",
            input_tokens=0,
            output_tokens=0,
            injected_tokens=0,
            turns=0,
            error=error,
            driver_name=driver_name,
        )

    @property
    def ok(self) -> bool:
        """True when no error occurred."""
        return self.error is None


# ---------------------------------------------------------------------------
# Driver Protocol
# ---------------------------------------------------------------------------

class Driver:
    """Protocol / base class for AI drivers.

    Concrete subclasses override ``ask``.  The Protocol pattern is used rather
    than ``typing.Protocol`` so that the code is compatible with Python 3.7+
    without ``typing_extensions``.
    """

    name: str = "base"

    def ask(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_turns: int = 1,
        tool_broker: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> AskResult:
        """Send a prompt to the AI and return the result.

        Parameters
        ----------
        system_prompt : str
            The system prompt preamble (instructions, context).
        user_prompt : str
            The user question / task.
        max_turns : int
            Maximum number of AI turns for multi-turn drivers (M3).  For
            single-shot drivers this is ignored.
        tool_broker : callable, optional
            ``tool_broker(tool_name, arguments) -> result`` for M3 multi-turn
            cks tool loop.  If None, tool use is disabled.

        Returns
        -------
        AskResult
            Structured result; never raises (errors surfaced via AskResult.error).
        """
        raise NotImplementedError(f"{self.__class__.__name__}.ask() not implemented")
