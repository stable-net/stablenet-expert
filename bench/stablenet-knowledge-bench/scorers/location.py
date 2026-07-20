"""location.py — location P/R/F1 scorer.

Python port of the overlap matcher in
code-knowledge-system/internal/eval/metrics.go.

A citation matches an expected reference if:
  1. The file paths normalize to the same value (trailing / stripped,
     leading ./ stripped).
  2. If both have start_line/end_line: the ranges overlap by at least 1 line.
     If either side has null lines: the file match alone counts.

Precision = (number of predicted citations that match any expected) / len(predicted)
Recall    = (number of expected citations matched by any predicted) / len(expected)
F1        = harmonic mean of P and R (0 if P + R == 0)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from bench_io.envelope import Citation


@dataclass
class LocationScore:
    """Location precision, recall, and F1."""
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> dict:
        return {"precision": self.precision, "recall": self.recall, "f1": self.f1}


def _normalize_path(path: str) -> str:
    """Strip leading ./ and normalize separators for comparison."""
    return path.lstrip("./").strip("/").replace("\\", "/")


def _ranges_overlap(s1: Optional[int], e1: Optional[int],
                    s2: Optional[int], e2: Optional[int]) -> bool:
    """Return True if [s1,e1] and [s2,e2] overlap, or if either side lacks range info."""
    if s1 is None or e1 is None or s2 is None or e2 is None:
        return True  # file-level match is sufficient when range is unknown
    return s1 <= e2 and s2 <= e1


def _citation_matches(predicted: Citation, expected: Citation) -> bool:
    """Return True if predicted citation matches expected."""
    if _normalize_path(predicted.file) != _normalize_path(expected.file):
        return False
    return _ranges_overlap(
        predicted.start_line, predicted.end_line,
        expected.start_line, expected.end_line,
    )


def score_location(
    predicted: List[Citation],
    expected: List[Citation],
) -> LocationScore:
    """Compute location P/R/F1.

    Parameters
    ----------
    predicted : citations extracted from the AI response
    expected  : citations from the golden-set question
    """
    if not expected:
        # Edge case: no expected citations → perfect score (nothing to miss)
        p = 1.0 if not predicted else 0.0
        return LocationScore(precision=p, recall=1.0, f1=p)

    if not predicted:
        return LocationScore(precision=0.0, recall=0.0, f1=0.0)

    # Precision: fraction of predicted that hit any expected
    pred_hits = sum(
        1
        for pred in predicted
        if any(_citation_matches(pred, exp) for exp in expected)
    )
    precision = pred_hits / len(predicted)

    # Recall: fraction of expected covered by any predicted
    exp_hits = sum(
        1
        for exp in expected
        if any(_citation_matches(pred, exp) for pred in predicted)
    )
    recall = exp_hits / len(expected)

    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return LocationScore(precision=round(precision, 4), recall=round(recall, 4), f1=round(f1, 4))
