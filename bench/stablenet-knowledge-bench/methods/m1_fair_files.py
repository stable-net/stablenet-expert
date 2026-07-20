"""m1_fair_files.py — Method M1_fair: non-oracle keyword-search baseline.

Context strategy: select files by grepping the repository for terms derived
from the question *prompt only* (never expected_citations). Mimics a
developer who only has keyword/grep search — no knowledge graph, no golden
answer key.

Selection algorithm:
  1. Extract search terms from the question prompt text only.
  2. Grep source dirs (consensus/, core/, systemcontracts/, eth/, params/,
     cmd/) over *.go and *.sol, excluding _test.go, vendor/, .stablenet-expert/.
  3. Rank candidates by number of distinct query terms that appear in the
     file content, plus a filename-match bonus; tie-break by file size.
  4. Take top-K (K=3) files. If no files match, fall back to basename-match
     only; if still none, emit a placeholder comment.
  5. Dump each file's FULL content, bounded by a ~60_000-char total cap;
     if over the cap, truncate the last file with "// [truncated]".

Audit: the context block is prefixed with a comment listing selected files
so non-oracle selection can be verified later.

cks dependency: none (pure disk I/O + subprocess grep).
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from drivers.base import AskResult, Driver
from methods.m1_raw_files import _SYSTEM_PROMPT_PREAMBLE, _read_file

# Top-K files to include in context.
_TOP_K = 3

# Approximate character cap for the combined context block.
_CHAR_CAP = 60_000

# Source directories searched (relative to repo root).
_SEARCH_DIRS = [
    "consensus",
    "core",
    "systemcontracts",
    "eth",
    "params",
    "cmd",
]

# File extensions searched.
_SOURCE_GLOBS = ["*.go", "*.sol"]

# Common English stopwords and domain-generic words that add no signal.
_STOPWORDS = frozenset(
    {
        # English function words
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "it", "its", "be", "was",
        "are", "were", "been", "has", "have", "had", "do", "does", "did",
        "not", "this", "that", "these", "those", "which", "who", "what",
        "when", "where", "how", "why", "if", "then", "than", "so", "up",
        "into", "out", "over", "under", "more", "most", "also", "just",
        "about", "through", "between", "after", "before", "within",
        # Question-boilerplate words
        "how", "does", "what", "which", "where", "when", "why", "cite",
        "exact", "value", "used", "using", "uses", "use", "based", "given",
        "define", "defined", "returns", "return", "get", "set",
        # Domain-generic programming/repo words that appear everywhere
        "file", "function", "code", "go", "sol", "solidity", "stablenet",
        "gostablenet", "ethereum", "geth", "blockchain", "contract",
        "address", "bytes", "uint", "int", "bool", "string", "error",
        "nil", "true", "false", "new", "make", "type", "struct", "interface",
        "package", "import", "var", "const", "func", "map", "slice",
    }
)

# Regex for quoted identifiers like `QuorumSize` or 'defaultSet'.
_QUOTED_IDENT_RE = re.compile(r'[`\'"]([\w.]+)[`\'"]')

# Regex for CamelCase / mixedCase identifiers (must have an inner uppercase
# letter OR be at least 4 characters to suppress noise like "go", "sol").
_CAMEL_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')

# Regex to strip a trailing "Cite the … file." instruction sentence.
_CITE_SENTENCE_RE = re.compile(
    r'\s+Cite\s+the\s+[^.]+\.',
    re.IGNORECASE,
)


def _extract_terms(prompt: str) -> List[str]:
    """Extract search terms from the question prompt.

    Strips trailing "Cite the … file." instructions, then collects:
    - All backtick/quoted identifiers.
    - CamelCase / mixedCase identifiers (inner uppercase letter or len>=4).
    Returns unique terms in discovery order, lowercased for deduplication,
    but stored in original case for grep (grep is case-sensitive by default).
    """
    # Remove trailing cite instruction sentence(s).
    cleaned = _CITE_SENTENCE_RE.sub("", prompt).strip()

    seen_lower: set = set()
    terms: List[str] = []

    def _add(word: str) -> None:
        lower = word.lower()
        if lower in seen_lower or lower in _STOPWORDS:
            return
        seen_lower.add(lower)
        terms.append(word)

    # Phase 1: quoted identifiers (high confidence).
    for m in _QUOTED_IDENT_RE.finditer(cleaned):
        _add(m.group(1))

    # Phase 2: camelCase / mixedCase / long identifiers.
    for m in _CAMEL_RE.finditer(cleaned):
        word = m.group(1)
        has_inner_upper = bool(re.search(r'[a-z][A-Z]', word))
        if has_inner_upper or len(word) >= 4:
            _add(word)

    return terms


def _grep_for_term(
    repo_root: str,
    term: str,
) -> List[str]:
    """Return list of matching file paths (absolute) for a single term."""
    results: List[str] = []
    for search_dir in _SEARCH_DIRS:
        abs_dir = os.path.join(repo_root, search_dir)
        if not os.path.isdir(abs_dir):
            continue
        for glob in _SOURCE_GLOBS:
            try:
                proc = subprocess.run(
                    [
                        "grep",
                        "-rl",           # recursive, list files only
                        "--include=" + glob,
                        "--exclude=*_test.go",
                        "--exclude-dir=vendor",
                        "--exclude-dir=.stablenet-expert",
                        term,
                        abs_dir,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    results.append(line)
    return results


def _rank_files(
    repo_root: str,
    terms: List[str],
) -> List[str]:
    """Rank candidate files by score (distinct term hits + basename bonus).

    Returns file paths sorted best-first (absolute paths).
    """
    # Map: abs_path -> set of terms found
    hit_map: Dict[str, set] = {}
    for term in terms:
        for path in _grep_for_term(repo_root, term):
            hit_map.setdefault(path, set()).add(term)

    if not hit_map:
        return []

    # Score: (#distinct terms) * 10 + (1 if any term matches basename, else 0).
    def _score(path: str) -> Tuple[int, int]:
        basename = os.path.basename(path).lower()
        distinct_hits = len(hit_map[path])
        basename_bonus = int(
            any(t.lower() in basename for t in hit_map[path])
        )
        # Tie-break by negative file size (prefer smaller files).
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        return (distinct_hits * 10 + basename_bonus, -size)

    sorted_paths = sorted(hit_map.keys(), key=_score, reverse=True)
    return sorted_paths


def _basename_fallback(repo_root: str, terms: List[str]) -> List[str]:
    """Fallback: find files whose basename contains any term."""
    matches: List[str] = []
    for search_dir in _SEARCH_DIRS:
        abs_dir = os.path.join(repo_root, search_dir)
        if not os.path.isdir(abs_dir):
            continue
        try:
            proc = subprocess.run(
                ["find", abs_dir, "-type", "f",
                 "!", "-name", "*_test.go",
                 "!", "-path", "*/vendor/*",
                 "!", "-path", "*/.stablenet-expert/*"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            ext = os.path.splitext(line)[1]
            if ext not in (".go", ".sol"):
                continue
            basename = os.path.basename(line).lower()
            if any(t.lower() in basename for t in terms):
                matches.append(line)
    return matches[:_TOP_K]


class M1FairFiles:
    """Method M1_fair — non-oracle keyword-search file context."""

    method_id = "M1_fair"

    def __init__(self, go_stablenet_root: str) -> None:
        # No cks_tool — this is a pure grep/disk baseline.
        self._root = go_stablenet_root

    def build_prompt(self, question: Dict[str, Any]) -> tuple:
        """Return (system_prompt, user_prompt) for the question.

        File selection is driven by the question prompt text only.
        expected_citations is never accessed here.
        """
        prompt_text: str = question.get("prompt", "") or ""
        terms = _extract_terms(prompt_text)

        # Select files by grep ranking.
        if terms:
            ranked = _rank_files(self._root, terms)
            selected_abs = ranked[:_TOP_K]
        else:
            selected_abs = []

        # Fallback: basename match if grep found nothing.
        if not selected_abs and terms:
            selected_abs = _basename_fallback(self._root, terms)

        # Convert to repo-relative paths.
        selected_rel: List[str] = []
        for path in selected_abs:
            try:
                rel = os.path.relpath(path, self._root)
            except ValueError:
                rel = path
            selected_rel.append(rel)

        # Build context block with selection audit header.
        context_parts: List[str] = []
        if not selected_rel:
            context_parts.append("// [no files matched keyword search]")
        else:
            audit_line = (
                "// [M1_fair selected files (keyword search, non-oracle):\n"
                + "\n".join(f"//   {r}" for r in selected_rel)
                + "\n// ]"
            )
            context_parts.append(audit_line)

            char_budget = _CHAR_CAP
            for rel in selected_rel:
                abs_path = os.path.join(self._root, rel)
                content = _read_file(abs_path)
                if content is None:
                    block = f"// --- FILE: {rel} (NOT FOUND ON DISK) ---\n"
                else:
                    header = f"// --- FILE: {rel} ---\n"
                    if len(header) + len(content) <= char_budget:
                        block = header + content + "\n"
                        char_budget -= len(block)
                    else:
                        available = char_budget - len(header) - len("// [truncated]\n") - 1
                        if available > 0:
                            block = header + content[:available] + "\n// [truncated]\n"
                        else:
                            block = header + "// [truncated]\n"
                        char_budget = 0
                context_parts.append(block)
                if char_budget <= 0:
                    break

        context_block = "\n".join(context_parts)
        system_prompt = _SYSTEM_PROMPT_PREAMBLE.strip()
        user_prompt = (
            f"CODE CONTEXT:\n{context_block}\n\n"
            f"QUESTION:\n{prompt_text}"
        )
        return system_prompt, user_prompt

    def run(self, question: Dict[str, Any], driver: Driver) -> AskResult:
        """Run this method for a single question using the given driver."""
        system_prompt, user_prompt = self.build_prompt(question)
        try:
            return driver.ask(system_prompt, user_prompt, max_turns=1)
        except Exception as exc:
            return AskResult.from_error(
                f"M1_fair unexpected error: {exc}", driver_name=driver.name
            )
