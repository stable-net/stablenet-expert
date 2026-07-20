"""correctness.py — correctness scorer.

A response is "correct" when BOTH hold:
  1. Location recall >= threshold (default 0.5) — the AI cited the right place.
  2. ANY expected_keyword is present in the answer (case-insensitive).

(The earlier rule additionally required the *first* keyword specifically; that
positional constraint was arbitrary and is removed — see score_correctness.)

Returns bool. When parse_mode == "failed" the score is always False.
"""

from __future__ import annotations

from typing import List

from .location import LocationScore


_RECALL_THRESHOLD = 0.5


def score_correctness(
    answer: str,
    location: LocationScore,
    expected_keywords: List[str],
    *,
    recall_threshold: float = _RECALL_THRESHOLD,
    parse_failed: bool = False,
) -> bool:
    """Return True if the response is considered correct.

    Parameters
    ----------
    answer : str
        The answer text extracted from the AI response.
    location : LocationScore
        Precomputed location score for this cell.
    expected_keywords : list of str
        Keywords the answer must contain (from question YAML).
    recall_threshold : float
        Minimum location recall required (default 0.5).
    parse_failed : bool
        If True, automatically returns False (no JSON envelope).
    """
    if parse_failed:
        return False
    if not answer.strip():
        return False
    if location.recall < recall_threshold:
        return False
    if not expected_keywords:
        # No keywords → location alone determines correctness
        return True

    answer_lower = answer.lower()
    # Correct if it cites the right place (recall gate above) AND mentions ANY
    # expected keyword. We intentionally do NOT require the *first* keyword
    # specifically — that positional rule was arbitrary and produced false
    # negatives when the answer used an equivalent/synonym keyword while citing
    # the correct location (perfect loc_f1 but marked wrong).
    return any(kw.lower() in answer_lower for kw in expected_keywords)
