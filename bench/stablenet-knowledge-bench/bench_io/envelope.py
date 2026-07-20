"""envelope.py — Citation and ParsedResponse dataclasses.

The AI is instructed to respond with:
    {
      "answer": "<concise answer>",
      "citations": [
        {"file": "<relative path>", "start_line": <int or null>,
         "end_line": <int or null>, "symbol": "<optional>"}
      ]
    }

ParsedResponse captures the parsed structure along with a parse_mode
that records how the response was parsed (strict JSON, lenient regex,
or failed with zero citations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class Citation:
    """A single code citation extracted from an AI response.

    All fields except ``file`` are optional — the extractor tolerates
    responses that only mention a file path.
    """

    file: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    symbol: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol": self.symbol,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Citation":
        return cls(
            file=str(d.get("file", "")),
            start_line=_to_int_or_none(d.get("start_line")),
            end_line=_to_int_or_none(d.get("end_line")),
            symbol=d.get("symbol") or None,
        )


def _to_int_or_none(val: object) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


ParseMode = Literal["strict", "lenient", "failed"]


@dataclass
class ParsedResponse:
    """Result of parsing an AI response through the extractor.

    Attributes
    ----------
    answer : str
        The textual answer extracted (may be empty on failure).
    citations : list of Citation
        Parsed citations. Empty list if parse_mode == "failed".
    parse_mode : str
        "strict"  — JSON parsed successfully with expected schema.
        "lenient" — JSON parse failed; citations extracted via regex.
        "failed"  — No citations could be extracted at all.
    raw_text : str
        The original response_text from AskResult (for debugging).
    """

    answer: str
    citations: List[Citation]
    parse_mode: ParseMode
    raw_text: str = ""

    @property
    def ok(self) -> bool:
        return self.parse_mode != "failed"

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "parse_mode": self.parse_mode,
        }
