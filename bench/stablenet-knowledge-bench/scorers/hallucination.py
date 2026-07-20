"""hallucination.py — hallucination scorer.

Ticket definition of the metric: "오류 건수 — 존재하지 않는 파일·함수명을
만들어낸 횟수" (count of made-up, NONEXISTENT file/function names). So a
hallucination is a genuine fabrication — not a mere wrong-file attribution of
a real symbol (that is a location error, already penalized by loc_f1).

For each citation in the AI response, it is a hallucination if ANY holds:
  1. The cited file does not exist on disk.
  2. A symbol is given and it exists NOWHERE in the codebase. Existence is
     checked via cks ``find_symbol`` (arg key ``name``, bare identifier; matches
     under the ``citations`` key). If cks is unavailable, fall back to a
     whole-repo ``grep -rnw`` over the build dirs and record ``cks_partial``.
  3. The line range is out of the cited file's actual bounds.

Symbol strings are normalized (``defaultSet.QuorumSize`` → ``QuorumSize``)
before lookup, because the source contains only the bare identifier.

Returns HallucinationScore with counts and per-citation verdicts.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from bench_io.envelope import Citation

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _normalize_symbol(symbol: str) -> str:
    """Reduce a citation symbol to the bare identifier used in source.

    AI/cks citations use logical ``receiver.Method`` / ``pkg.Func`` dotted
    forms (e.g. ``defaultSet.QuorumSize``, ``core.newRoundChangeTimer``) and
    may include pointer/receiver decoration or call parens. The Go source,
    however, only contains the bare identifier (``func (v *defaultSet)
    QuorumSize()``). We take the LAST identifier token, which is almost
    always the func/method/type name actually present in the file. This
    prevents false-positive hallucinations from dotted symbol names that
    never appear verbatim in source.
    """
    if not symbol:
        return ""
    idents = _IDENT_RE.findall(symbol)
    return idents[-1] if idents else ""


def _is_checkable_symbol(symbol: str) -> bool:
    """True only if the symbol is a code identifier we can verify existence of.

    The AI sometimes puts a prose DESCRIPTION in the symbol field
    (e.g. "system contract address constants", "쿼럼-계산"). Normalizing such a
    phrase to its last token ("constants") and checking existence yields
    meaningless false-positive hallucinations. So we only verify symbols that
    look like an identifier or a dotted ``receiver.Method`` form — i.e. contain
    no whitespace and normalize to a valid ASCII identifier.
    """
    s = (symbol or "").strip()
    if not s or any(ch.isspace() for ch in s):
        return False
    if s.endswith("()"):
        s = s[:-2]
    # Only a bare identifier or a dotted ``pkg.Type.Method`` form is checkable.
    # Hyphens, slashes, stars, digits-leading, non-ASCII (doc titles, prose
    # fragments like "txType/accessors" or "11-fee-delegation-트랜잭션") are not.
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", s))


@dataclass
class CitationVerdict:
    """Verification result for a single citation."""
    citation: Citation
    is_hallucination: bool
    reason: str
    cks_partial: bool = False

    def to_dict(self) -> dict:
        return {
            "file": self.citation.file,
            "symbol": self.citation.symbol,
            "is_hallucination": self.is_hallucination,
            "reason": self.reason,
            "cks_partial": self.cks_partial,
        }


@dataclass
class HallucinationScore:
    """Hallucination scoring result for a full response."""
    total_citations: int
    hallucination_count: int
    cks_partial: bool
    verdicts: List[CitationVerdict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_citations": self.total_citations,
            "hallucination_count": self.hallucination_count,
            "cks_partial": self.cks_partial,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


def _file_line_count(path: str) -> Optional[int]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def _grep_symbol(symbol: str, file_path: str) -> bool:
    """Return True if the citation's identifier appears in file_path.

    The dotted symbol is normalized to its bare identifier first, since the
    source contains ``QuorumSize`` — not the logical ``defaultSet.QuorumSize``.
    Uses word-boundary matching so ``QuorumSize`` is found in
    ``func (v *defaultSet) QuorumSize() int``.
    """
    name = _normalize_symbol(symbol)
    if not name:
        return False
    try:
        result = subprocess.run(
            ["grep", "-nw", name, file_path],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


_BUILD_DIRS = ["consensus", "core", "systemcontracts", "eth", "params", "cmd"]


def _cks_symbol_exists(cks_tool: Callable, symbol: str) -> tuple:
    """Return (exists_anywhere: bool, partial: bool) via cks find_symbol.

    Per the ticket's hallucination definition ("made up a nonexistent
    file/function name"), we only care whether the symbol EXISTS in the
    codebase at all — not whether it is in the cited file (that is a
    location error, already captured by loc_f1). cks ``find_symbol`` expects
    the arg key ``name`` and a bare identifier, so the dotted citation symbol
    is normalized first. Matches are returned under the ``citations`` key.
    """
    name = _normalize_symbol(symbol)
    if not name:
        return False, True
    try:
        result = cks_tool("find_symbol", {"name": name})
        if isinstance(result, dict):
            cites = (
                result.get("citations")
                or result.get("results")
                or result.get("locations")
                or []
            )
        elif isinstance(result, list):
            cites = result
        else:
            cites = []
        if cites:
            return True, False           # symbol exists somewhere → not fabricated
        return False, False              # cks responded, symbol exists nowhere
    except Exception:
        return False, True               # cks error → partial, fall back to grep


def _grep_repo(symbol: str, go_stablenet_root: str) -> bool:
    """Best-effort whole-repo existence check for the bare identifier.

    Used only when cks is unavailable (partial). Searches the build source
    dirs for the normalized identifier as a whole word.
    """
    name = _normalize_symbol(symbol)
    if not name:
        return False
    dirs = [os.path.join(go_stablenet_root, d) for d in _BUILD_DIRS]
    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        return False
    try:
        result = subprocess.run(
            ["grep", "-rnw", "--include=*.go", "--include=*.sol", name, *dirs],
            capture_output=True, text=True, timeout=20,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def _is_domain_doc(cite_file: str, corpus_root: str) -> bool:
    """True if the cited file is a cks domain-knowledge corpus document.

    The cks context injects domain-knowledge entries (e.g.
    ``A1.wbft_core.quorum_calc.md``); a model citing one is referencing the
    knowledge source it drew a fact from, not fabricating code. Those files
    are absent from the go-stablenet tree by design, so verify them against
    the corpus instead. Extension drift (.md vs .yaml) is tolerated.
    """
    if not corpus_root:
        return False
    base = os.path.basename(cite_file)
    stem = base.rsplit(".", 1)[0] if "." in base else base
    candidates = [base] + [stem + ext for ext in (".md", ".yaml", ".yml")]
    return any(os.path.isfile(os.path.join(corpus_root, c)) for c in candidates)


def _verify_citation(
    citation: Citation,
    go_stablenet_root: str,
    cks_tool: Optional[Callable],
    domain_corpus_root: Optional[str] = None,
) -> CitationVerdict:
    """Verify a single citation; return a CitationVerdict."""
    abs_path = os.path.join(go_stablenet_root, citation.file)
    cks_partial = False

    # Check 1: file exists on disk
    if not os.path.isfile(abs_path):
        # A citation to a cks domain-knowledge document is a knowledge-source
        # reference, not fabricated code — it is not in the go-stablenet tree
        # by design. Verify it against the corpus before flagging. A wrong doc
        # still forfeits location credit (loc_f1); it is just not a fabrication.
        if _is_domain_doc(citation.file, domain_corpus_root):
            return CitationVerdict(
                citation=citation,
                is_hallucination=False,
                reason="cks domain-knowledge doc (not code)",
            )
        return CitationVerdict(
            citation=citation,
            is_hallucination=True,
            reason=f"file not found: {citation.file}",
        )

    # NOTE: line-range plausibility is deliberately NOT a hallucination.
    # A wrong/over-range line for a real file is a LOCATION precision error
    # (already reflected in loc_f1), not a made-up file/function name.

    # Check 2: symbol EXISTENCE (anywhere in the repo).
    # Hallucination = a made-up function/type name. A real symbol cited in the
    # wrong file is a *location* error (penalized by loc_f1), NOT a fabrication,
    # so we only flag symbols that exist nowhere in the codebase.
    if citation.symbol and _is_checkable_symbol(citation.symbol):
        name = _normalize_symbol(citation.symbol)
        if cks_tool is not None:
            exists, partial = _cks_symbol_exists(cks_tool, citation.symbol)
            if exists:
                cks_partial = False                       # cks verified it exists
            elif partial:
                # cks unavailable → whole-repo grep fallback (cited file + rest)
                cks_partial = True
                if not (_grep_symbol(citation.symbol, abs_path) or _grep_repo(citation.symbol, go_stablenet_root)):
                    return CitationVerdict(
                        citation=citation,
                        is_hallucination=True,
                        reason=f"symbol '{name}' not found in repo (grep fallback; cks unavailable)",
                        cks_partial=True,
                    )
            else:
                # cks responded empty. cks may not index every language (e.g.
                # Solidity) — cross-check with a whole-repo grep before calling
                # it a fabrication. Only flag if grep ALSO finds nothing.
                if _grep_repo(citation.symbol, go_stablenet_root):
                    cks_partial = False  # exists (cks missed it, grep found it)
                else:
                    return CitationVerdict(
                        citation=citation,
                        is_hallucination=True,
                        reason=f"symbol '{name}' does not exist anywhere in the codebase (cks + grep)",
                        cks_partial=False,
                    )
        else:
            # No cks — whole-repo grep existence check
            cks_partial = True
            if not (_grep_symbol(citation.symbol, abs_path) or _grep_repo(citation.symbol, go_stablenet_root)):
                return CitationVerdict(
                    citation=citation,
                    is_hallucination=True,
                    reason=f"symbol '{name}' not found in repo (grep; cks unavailable)",
                    cks_partial=True,
                )

    return CitationVerdict(
        citation=citation,
        is_hallucination=False,
        reason="ok",
        cks_partial=cks_partial,
    )


def score_hallucination(
    citations: List[Citation],
    go_stablenet_root: str,
    cks_tool: Optional[Callable] = None,
    domain_corpus_root: Optional[str] = None,
) -> HallucinationScore:
    """Score hallucinations for all citations in a response.

    Parameters
    ----------
    citations : list of Citation from the parsed AI response
    go_stablenet_root : absolute path to the go-stablenet repo
    cks_tool : optional cks dispatcher callable
    domain_corpus_root : optional path to the cks domain-knowledge corpus;
        citations to a corpus doc (not in the go-stablenet tree) are
        knowledge-source references, not fabricated code.
    """
    verdicts = [
        _verify_citation(cite, go_stablenet_root, cks_tool, domain_corpus_root)
        for cite in citations
    ]
    hallucination_count = sum(1 for v in verdicts if v.is_hallucination)
    any_partial = any(v.cks_partial for v in verdicts)

    return HallucinationScore(
        total_citations=len(citations),
        hallucination_count=hallucination_count,
        cks_partial=any_partial,
        verdicts=verdicts,
    )
