"""extract.py — parse AI response text into a ParsedResponse.

Extraction cascade:
1. Strict: attempt JSON parse of entire response_text.
   Accept if it has "answer" key and "citations" list.
2. Lenient: if strict fails, attempt to extract a JSON object from the text
   (scan for ``{...}`` block that contains "answer" or "citations").
   Also regex-scan prose for file:line and path.go:LINE patterns.
3. Failed: return ParsedResponse with empty citations and parse_mode="failed".

The extractor never raises.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from .envelope import Citation, ParsedResponse

# Regex for prose citations like:
#   consensus/wbft/core/roundchange.go:45-67
#   core/state_transition.go:123
#   path/to/file.go line 45
_PROSE_CITE_RE = re.compile(
    r"([\w./\-]+\.(?:go|sol|py|ts|js|md))"  # file path
    r"(?::(\d+)(?:-(\d+))?)?"               # optional :start or :start-end
    r"(?:\s+lines?\s+(\d+)(?:-(\d+))?)?",   # optional " line N" or " lines N-M"
    re.IGNORECASE,
)

# Minimum number of path separators to qualify as a file citation
_MIN_SLASHES = 1


def _looks_like_file(path: str) -> bool:
    """Heuristic: at least one slash and ends in a source file extension."""
    return path.count("/") >= _MIN_SLASHES


def _parse_prose_citations(text: str) -> List[Citation]:
    """Extract file citations from free prose using regex."""
    citations: List[Citation] = []
    seen: set = set()
    for m in _PROSE_CITE_RE.finditer(text):
        file_path = m.group(1)
        if not _looks_like_file(file_path):
            continue
        start = _int_or_none(m.group(2)) or _int_or_none(m.group(4))
        end = _int_or_none(m.group(3)) or _int_or_none(m.group(5)) or start
        key = (file_path, start, end)
        if key in seen:
            continue
        seen.add(key)
        citations.append(Citation(file=file_path, start_line=start, end_line=end))
    return citations


def _int_or_none(val: Optional[str]) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _extract_json_block(text: str) -> Optional[str]:
    """Scan text for the first balanced {...} block that resembles our schema."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                block = text[start : i + 1]
                # Quick check: must mention "answer" or "citations"
                if '"answer"' in block or '"citations"' in block:
                    return block
                start = -1
    return None


def _parse_citations_from_json(raw: object) -> List[Citation]:
    """Convert a parsed JSON value (list or dict of dicts) into Citation objects."""
    if not isinstance(raw, list):
        return []
    result: List[Citation] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        file_val = item.get("file", "")
        if not file_val:
            continue
        result.append(Citation.from_dict(item))
    return result


def extract_response(response_text: str) -> ParsedResponse:
    """Parse response_text into a ParsedResponse.

    Never raises. Always returns a ParsedResponse.
    """
    if not response_text or not response_text.strip():
        return ParsedResponse(
            answer="",
            citations=[],
            parse_mode="failed",
            raw_text=response_text,
        )

    # ---- Stage 1: strict JSON parse ----
    try:
        data = json.loads(response_text.strip())
        if isinstance(data, dict) and ("answer" in data or "citations" in data):
            answer = str(data.get("answer", ""))
            citations = _parse_citations_from_json(data.get("citations", []))
            return ParsedResponse(
                answer=answer,
                citations=citations,
                parse_mode="strict",
                raw_text=response_text,
            )
    except (json.JSONDecodeError, ValueError):
        pass

    # ---- Stage 2: lenient — extract JSON block from prose ----
    block = _extract_json_block(response_text)
    if block:
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                answer = str(data.get("answer", ""))
                citations = _parse_citations_from_json(data.get("citations", []))
                if not citations:
                    # Also scan prose for additional citations
                    citations = _parse_prose_citations(response_text)
                return ParsedResponse(
                    answer=answer,
                    citations=citations,
                    parse_mode="lenient",
                    raw_text=response_text,
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # ---- Stage 2b: prose-only citation scan ----
    prose_citations = _parse_prose_citations(response_text)
    if prose_citations:
        # Use first 200 chars as a rough answer
        answer = response_text[:200].strip()
        return ParsedResponse(
            answer=answer,
            citations=prose_citations,
            parse_mode="lenient",
            raw_text=response_text,
        )

    # ---- Stage 3: failed ----
    return ParsedResponse(
        answer="",
        citations=[],
        parse_mode="failed",
        raw_text=response_text,
    )
