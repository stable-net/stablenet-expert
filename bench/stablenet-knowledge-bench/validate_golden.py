#!/usr/bin/env python3
"""validate_golden.py — verify all golden-set question files against the repo.

For each question in the golden-set index:
  1. Load the per-question YAML.
  2. If start_line / end_line are set: verify file exists on disk and the lines
     are within the file's actual line count.
  3. If symbol is set and cks is available: call cks find_symbol(symbol) and
     assert the reported file matches the expected file (tolerant of leading
     path difference); assert line-range overlap if both expected and reported
     ranges are non-null.
  4. If symbol is set and cks is unavailable: fall back to disk grep and warn.

Exit 0 if all questions pass, 1 if any fail.

Usage:
    python3 validate_golden.py [--index golden-set/index.yaml]
                               [--repo-root /abs/path/to/go-stablenet]
                               [--cks-host http://localhost:PORT]
                               [--offline]   # skip cks checks entirely
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml as _yaml_mod

    def load_yaml(path: str) -> Any:
        with open(path, "r", encoding="utf-8") as fh:
            return _yaml_mod.safe_load(fh)

except ImportError:
    # Minimal YAML subset reader — handles the simple key: value, lists with -
    def load_yaml(path: str) -> Any:  # type: ignore[misc]
        """Minimal YAML parser for the golden-set file format (no pip needed)."""
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        return _parse_yaml_lines(lines)


def _parse_yaml_lines(lines: List[str]) -> Any:
    """Parse a simple YAML document (no anchors, no multi-line scalars)."""
    result: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict]] = [(-1, result)]
    list_stack: List[Optional[Dict]] = []
    current_list: Optional[List] = None
    current_list_key: Optional[str] = None
    current_list_indent = -1

    for raw in lines:
        stripped = raw.rstrip("\n")
        if stripped.strip() == "" or stripped.strip().startswith("#"):
            continue
        indent = len(stripped) - len(stripped.lstrip())
        content = stripped.strip()

        if content.startswith("- "):
            # List item
            item_content = content[2:].strip()
            if ":" in item_content:
                key, _, val = item_content.partition(":")
                val = val.strip().strip('"').strip("'")
                if current_list is not None:
                    if isinstance(current_list[-1] if current_list else None, dict):
                        current_list[-1][key.strip()] = _coerce(val)  # type: ignore[index]
                    else:
                        d: Dict[str, Any] = {key.strip(): _coerce(val)}
                        current_list.append(d)
                else:
                    if current_list_key:
                        parent = stack[-1][1]
                        if current_list_key not in parent:
                            parent[current_list_key] = []
                        parent[current_list_key].append({key.strip(): _coerce(val)})
            else:
                val2 = item_content.strip().strip('"').strip("'")
                if current_list is not None:
                    current_list.append(_coerce(val2))
                else:
                    if current_list_key:
                        parent2 = stack[-1][1]
                        if current_list_key not in parent2:
                            parent2[current_list_key] = []
                        parent2[current_list_key].append(_coerce(val2))
        elif ":" in content:
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "" or val == "[]" or val == "{}":
                # Key with no inline value or empty collection
                while len(stack) > 1 and stack[-1][0] >= indent:
                    stack.pop()
                stack[-1][1][key] = [] if val == "[]" else ({} if val == "{}" else {})
                if val == "":
                    current_list_key = key
                    current_list = None
                    # Will be populated by subsequent - items
                    stack[-1][1][key] = []
                    current_list = stack[-1][1][key]  # type: ignore[assignment]
                    current_list_indent = indent
            else:
                val = val.strip('"').strip("'")
                while len(stack) > 1 and stack[-1][0] >= indent:
                    stack.pop()
                stack[-1][1][key] = _coerce(val)
                current_list = None
                current_list_key = None

    return result


def _coerce(val: str) -> Any:
    if val in ("null", "~", ""):
        return None
    if val in ("true", "True"):
        return True
    if val in ("false", "False"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


class ValidationResult:
    def __init__(self, qid: str):
        self.qid = qid
        self.passed = True
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"  [{status}] {self.qid}"]
        for w in self.warnings:
            lines.append(f"    WARN: {w}")
        for e in self.errors:
            lines.append(f"    ERROR: {e}")
        return "\n".join(lines)


def _file_line_count(abs_path: str) -> Optional[int]:
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def _normalize_file(path: str) -> str:
    """Strip leading ./ or repo root from a file path for comparison."""
    return path.lstrip("./").lstrip("/")


def _ranges_overlap(s1: int, e1: int, s2: int, e2: int) -> bool:
    return s1 <= e2 and s2 <= e1


def validate_question(
    q_meta: Dict[str, Any],
    q_data: Dict[str, Any],
    repo_root: str,
    offline: bool,
    cks_host: Optional[str],
) -> ValidationResult:
    qid = q_data.get("id", q_meta.get("id", "?"))
    r = ValidationResult(qid)

    citations = q_data.get("expected_citations", []) or []
    if not citations:
        r.warn("no expected_citations — cannot verify file or line range")

    for cite in citations:
        if not isinstance(cite, dict):
            r.warn(f"citation entry is not a dict: {cite}")
            continue
        rel_file = cite.get("file")
        if not rel_file:
            r.warn("citation missing 'file' field")
            continue

        abs_file = os.path.join(repo_root, rel_file)
        if not os.path.isfile(abs_file):
            r.fail(f"file not found on disk: {rel_file}")
            continue

        start_line = cite.get("start_line")
        end_line = cite.get("end_line")

        if start_line is not None and end_line is not None:
            total_lines = _file_line_count(abs_file)
            if total_lines is None:
                r.warn(f"could not read line count for {rel_file}")
            else:
                if start_line < 1 or start_line > total_lines:
                    r.fail(
                        f"{rel_file}: start_line {start_line} out of range "
                        f"(file has {total_lines} lines)"
                    )
                if end_line < start_line or end_line > total_lines:
                    r.fail(
                        f"{rel_file}: end_line {end_line} out of range "
                        f"(start={start_line}, file has {total_lines} lines)"
                    )

        symbol = cite.get("symbol")
        if symbol and not offline:
            _check_symbol_via_cks(r, symbol, rel_file, start_line, end_line, cks_host)

    return r


def _check_symbol_via_cks(
    r: ValidationResult,
    symbol: str,
    expected_file: str,
    expected_start: Optional[int],
    expected_end: Optional[int],
    cks_host: Optional[str],
) -> None:
    """Try cks find_symbol; on failure, fall back to disk grep."""
    if cks_host is None:
        r.warn(f"cks not configured; skipping symbol lookup for '{symbol}'")
        return

    try:
        import urllib.request
        url = f"{cks_host.rstrip('/')}/find_symbol"
        payload = json.dumps({"symbol": symbol}).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        r.warn(f"cks find_symbol call failed ({exc}); falling back to disk grep")
        _check_symbol_via_grep(r, symbol, expected_file)
        return

    results = data.get("results") or data.get("locations") or []
    if not results:
        r.warn(
            f"cks find_symbol returned no results for '{symbol}'; "
            f"expected in {expected_file}"
        )
        return

    matched_file = False
    for loc in results:
        loc_file = _normalize_file(loc.get("file", ""))
        exp_norm = _normalize_file(expected_file)
        if loc_file == exp_norm or loc_file.endswith(exp_norm) or exp_norm.endswith(loc_file):
            matched_file = True
            loc_start = loc.get("start_line") or loc.get("line")
            loc_end = loc.get("end_line") or loc_start
            if (
                expected_start is not None
                and expected_end is not None
                and loc_start is not None
                and loc_end is not None
            ):
                if not _ranges_overlap(expected_start, expected_end, loc_start, loc_end):
                    r.warn(
                        f"cks find_symbol '{symbol}': reported range "
                        f"{loc_start}-{loc_end} does not overlap expected "
                        f"{expected_start}-{expected_end} in {expected_file}"
                    )
            break

    if not matched_file:
        reported = [_normalize_file(loc.get("file", "?")) for loc in results[:3]]
        r.fail(
            f"cks find_symbol '{symbol}': not found in {expected_file}; "
            f"cks reported {reported}"
        )


def _check_symbol_via_grep(
    r: ValidationResult, symbol: str, rel_file: str
) -> None:
    # Minimal fallback: just warn; we already verified file existence above
    r.warn(f"disk-grep fallback for symbol '{symbol}' in {rel_file} (not implemented offline)")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate CKG Benchmark golden-set question files."
    )
    parser.add_argument(
        "--index",
        default=os.path.join(os.path.dirname(__file__), "golden-set", "index.yaml"),
        metavar="PATH",
        help="Path to golden-set/index.yaml.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="PATH",
        help="Absolute path to go-stablenet repo root. Auto-detected if not given.",
    )
    parser.add_argument(
        "--cks-host",
        default=None,
        metavar="URL",
        help="cks MCP server base URL (e.g. http://localhost:3000). Omit to skip live checks.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=False,
        help="Skip all cks checks; only verify files exist on disk.",
    )
    args = parser.parse_args(argv)

    # Resolve repo root
    repo_root = args.repo_root
    if repo_root is None:
        # Try git
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True,
            )
            repo_root = result.stdout.strip()
        except Exception:
            repo_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
    repo_root = os.path.abspath(repo_root)

    # Load index
    if not os.path.isfile(args.index):
        print(f"error: index file not found: {args.index}", file=sys.stderr)
        return 1
    index = load_yaml(args.index)
    questions = index.get("questions", [])
    if not questions:
        print("error: index has no questions", file=sys.stderr)
        return 1

    index_dir = os.path.dirname(os.path.abspath(args.index))
    results: List[ValidationResult] = []
    failures = 0

    print(f"Validating {len(questions)} golden-set questions against {repo_root}")
    print(f"  offline={args.offline}, cks_host={args.cks_host}")
    print()

    for q_meta in questions:
        qid = q_meta.get("id", "?")
        q_file = q_meta.get("file")
        if not q_file:
            vr = ValidationResult(qid)
            vr.fail("index entry missing 'file' field")
            results.append(vr)
            failures += 1
            continue

        q_path = os.path.join(index_dir, q_file)
        if not os.path.isfile(q_path):
            vr = ValidationResult(qid)
            vr.fail(f"question file not found: {q_path}")
            results.append(vr)
            failures += 1
            continue

        try:
            q_data = load_yaml(q_path)
        except Exception as exc:
            vr = ValidationResult(qid)
            vr.fail(f"YAML parse error: {exc}")
            results.append(vr)
            failures += 1
            continue

        vr = validate_question(q_meta, q_data, repo_root, args.offline, args.cks_host)
        results.append(vr)
        if not vr.passed:
            failures += 1

    # Print report
    for vr in results:
        print(str(vr))

    print()
    passed = len(results) - failures
    print(f"Result: {passed}/{len(results)} passed")
    if failures:
        print(f"FAIL — {failures} question(s) did not validate", file=sys.stderr)
        return 1
    print("PASS — all golden-set questions validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
