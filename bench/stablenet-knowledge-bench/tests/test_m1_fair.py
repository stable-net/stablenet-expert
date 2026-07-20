"""test_m1_fair.py — unit tests for M1FairFiles (non-oracle keyword-search baseline).

Tests verify:
1. build_prompt NEVER reads expected_citations.
2. For a prompt mentioning "QuorumSize", build_prompt selects a file
   that actually contains "QuorumSize" (live repo on disk).
3. Terms are extracted correctly from prompt text.
4. Graceful fallback when no terms match any repo file.
5. Context block always contains the audit header comment.
6. M1_fair is present in METHOD_REGISTRY.

None of these tests require a live cks server or a live AI backend.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

# Detect the repo root: two levels above the bench directory.
# stablenet-knowledge-bench is at:  <repo>/.stablenet-expert/bench/stablenet-knowledge-bench
_REPO_ROOT = os.path.abspath(os.path.join(_BENCH_ROOT, "..", "..", ".."))
_HAS_REPO = os.path.isdir(os.path.join(_REPO_ROOT, "consensus"))


from methods.m1_fair_files import M1FairFiles, _extract_terms, _rank_files


class TestExtractTerms(unittest.TestCase):
    """Unit tests for the term-extraction helper."""

    def test_extracts_camel_case_identifiers(self):
        prompt = "How does QuorumSize() compute the minimum quorum?"
        terms = _extract_terms(prompt)
        self.assertIn("QuorumSize", terms)

    def test_drops_stopwords(self):
        prompt = "How does the function work in the code file?"
        terms = _extract_terms(prompt)
        # All words should be filtered by stopwords or too-short rule.
        for t in terms:
            self.assertGreater(len(t), 3, f"Short term leaked: {t!r}")

    def test_extracts_backtick_quoted_identifiers(self):
        prompt = "What is the value of `defaultValidatorSet` in the code?"
        terms = _extract_terms(prompt)
        self.assertIn("defaultValidatorSet", terms)

    def test_strips_trailing_cite_sentence(self):
        prompt = (
            "How does QuorumSize() work? "
            "Cite the exact function and file."
        )
        terms = _extract_terms(prompt)
        # "Cite" sentence stripped; QuorumSize still present.
        self.assertIn("QuorumSize", terms)
        # "file" is in stopwords so it must not appear.
        self.assertNotIn("file", terms)

    def test_no_duplicates(self):
        prompt = "QuorumSize QuorumSize QuorumSize in QuorumSize"
        terms = _extract_terms(prompt)
        self.assertEqual(terms.count("QuorumSize"), 1)

    def test_empty_prompt_returns_empty(self):
        self.assertEqual(_extract_terms(""), [])


class TestBuildPromptNoOracleAccess(unittest.TestCase):
    """Verify build_prompt never touches expected_citations."""

    def setUp(self):
        self._method = M1FairFiles(go_stablenet_root="/nonexistent_repo_root")

    def _poisoned_question(self, prompt: str) -> dict:
        """Build a question where expected_citations is a sentinel that
        raises AttributeError / TypeError if iterated — any attempt to
        read it will cause the test to fail."""
        class _Poison:
            """Attribute access raises to catch accidental reads."""
            def __iter__(self_inner):
                raise AssertionError(
                    "M1_fair must NOT read expected_citations"
                )
            def __getitem__(self_inner, item):
                raise AssertionError(
                    "M1_fair must NOT read expected_citations"
                )
            def get(self_inner, *args, **kwargs):
                raise AssertionError(
                    "M1_fair must NOT read expected_citations"
                )

        return {
            "id": "TEST_POISON",
            "prompt": prompt,
            "expected_citations": _Poison(),
        }

    def test_build_prompt_never_reads_expected_citations(self):
        """A poisoned expected_citations must survive without raising."""
        question = self._poisoned_question(
            "How does QuorumSize work in WBFT validator?"
        )
        # If M1_fair touches expected_citations, AssertionError propagates.
        try:
            system_prompt, user_prompt = self._method.build_prompt(question)
        except AssertionError:
            self.fail("build_prompt read expected_citations (oracle access)")
        # Minimal shape check.
        self.assertIsInstance(system_prompt, str)
        self.assertIsInstance(user_prompt, str)
        self.assertIn("QUESTION:", user_prompt)

    def test_build_prompt_no_crash_on_missing_citations_key(self):
        """Works fine when expected_citations is entirely absent."""
        question = {"id": "T1", "prompt": "What is QuorumSize?"}
        system_prompt, user_prompt = self._method.build_prompt(question)
        self.assertIn("QUESTION:", user_prompt)

    def test_build_prompt_oracle_file_not_necessarily_selected(self):
        """When the oracle file doesn't contain any keyword from the prompt,
        M1_fair must NOT select it (selection is driven by grep only).

        We use a prompt whose extracted terms have zero overlap with the
        expected_citations file list — we can't verify the exact negative on
        a non-existent repo, so we just verify the method completes without
        reading the citations key.
        """
        question = self._poisoned_question("How does XYZUniqueToken123 behave?")
        # Must not raise.
        system_prompt, user_prompt = self._method.build_prompt(question)
        self.assertIn("QUESTION:", user_prompt)


class TestBuildPromptFallback(unittest.TestCase):
    """Test graceful fallback when no terms match any file."""

    def test_no_match_fallback_comment(self):
        """When no files match, context includes a placeholder comment."""
        # Use a root that has no source dirs.
        method = M1FairFiles(go_stablenet_root="/nonexistent_repo_root")
        question = {
            "id": "T_NOMATCH",
            "prompt": "ZZZUNIQUETERMTHATCANNOTEXIST999",
        }
        _, user_prompt = method.build_prompt(question)
        self.assertIn("[no files matched keyword search]", user_prompt)

    def test_empty_prompt_fallback_comment(self):
        """Empty prompt → no terms → fallback placeholder."""
        method = M1FairFiles(go_stablenet_root="/nonexistent_repo_root")
        question = {"id": "T_EMPTY", "prompt": ""}
        _, user_prompt = method.build_prompt(question)
        self.assertIn("[no files matched keyword search]", user_prompt)


class TestBuildPromptAuditHeader(unittest.TestCase):
    """Context block must always contain the audit header when files found."""

    @unittest.skipUnless(_HAS_REPO, "repo not present on disk")
    def test_audit_header_present_when_files_found(self):
        method = M1FairFiles(go_stablenet_root=_REPO_ROOT)
        question = {
            "id": "G01",
            "prompt": (
                "In go-stablenet's WBFT consensus, how does QuorumSize() "
                "compute the minimum quorum for a validator set? "
                "Cite the exact function and file."
            ),
        }
        _, user_prompt = method.build_prompt(question)
        self.assertIn("[M1_fair selected files", user_prompt)

    def test_audit_header_or_fallback_always_present(self):
        """Either audit header or fallback placeholder must be in user_prompt."""
        method = M1FairFiles(go_stablenet_root="/nonexistent_repo_root")
        question = {"id": "T_AUDIT", "prompt": "QuorumSize validator"}
        _, user_prompt = method.build_prompt(question)
        has_audit = "[M1_fair selected files" in user_prompt
        has_fallback = "[no files matched keyword search]" in user_prompt
        self.assertTrue(
            has_audit or has_fallback,
            "Neither audit header nor fallback comment found in user_prompt",
        )


@unittest.skipUnless(_HAS_REPO, "repo not present on disk")
class TestLiveRepoSelection(unittest.TestCase):
    """Live-repo tests: require go-stablenet source tree at _REPO_ROOT."""

    def setUp(self):
        self._method = M1FairFiles(go_stablenet_root=_REPO_ROOT)

    def test_quorum_size_prompt_selects_file_with_quorum_size(self):
        """Prompt mentioning 'QuorumSize' must cause at least one selected
        file to contain the string QuorumSize."""
        question = {
            "id": "G01",
            "prompt": (
                "In go-stablenet's WBFT consensus, how does QuorumSize() "
                "compute the minimum quorum for a validator set? "
                "Cite the exact function and file."
            ),
        }
        _, user_prompt = self._method.build_prompt(question)
        # The context block must include content from a file containing QuorumSize.
        self.assertIn("QuorumSize", user_prompt,
                      "Expected QuorumSize content in selected files' context")

    def test_selected_files_are_repo_relative(self):
        """All selected file paths in audit header should be valid repo paths."""
        import re
        question = {
            "id": "G01_rel",
            "prompt": "How does QuorumSize compute quorum for WBFT validators?",
        }
        _, user_prompt = self._method.build_prompt(question)
        if "[no files matched keyword search]" in user_prompt:
            return  # Fallback path — acceptable.
        # Extract the audit block: from "[M1_fair selected files" up to "// ]"
        m = re.search(
            r'\[M1_fair selected files.*?\n((?://   [^\n]*\n)*)// \]',
            user_prompt,
            re.DOTALL,
        )
        if m is None:
            self.fail("Audit block not found in user_prompt")
        # Each "//   path" line in the captured group.
        file_lines = re.findall(r'^//   (.+)$', m.group(1), re.MULTILINE)
        self.assertGreater(len(file_lines), 0, "Expected at least one file path in audit header")
        for rel_path in file_lines:
            rel_path = rel_path.strip()
            abs_path = os.path.join(_REPO_ROOT, rel_path)
            self.assertTrue(
                os.path.isfile(abs_path),
                f"Audit path does not exist on disk: {abs_path}",
            )

    def test_no_test_files_selected(self):
        """_test.go files must never be selected."""
        question = {
            "id": "G01_notestfiles",
            "prompt": "How does QuorumSize work for validator sets?",
        }
        _, user_prompt = self._method.build_prompt(question)
        # Split on FILE markers.
        import re
        file_headers = re.findall(r'// --- FILE: ([^ ]+) ---', user_prompt)
        for path in file_headers:
            self.assertFalse(
                path.endswith("_test.go"),
                f"_test.go file should never be selected: {path}",
            )

    def test_rank_files_returns_nonempty_for_quorumsize(self):
        """_rank_files should find at least one file for 'QuorumSize'."""
        ranked = _rank_files(_REPO_ROOT, ["QuorumSize"])
        self.assertGreater(len(ranked), 0, "Expected at least one hit for 'QuorumSize'")
        # All returned paths must exist.
        for path in ranked:
            self.assertTrue(os.path.isfile(path), f"Non-existent path returned: {path}")


class TestMethodRegistry(unittest.TestCase):
    """M1_fair must be present in the central method registry."""

    def test_m1_fair_in_registry(self):
        from methods import METHOD_REGISTRY
        self.assertIn("M1_fair", METHOD_REGISTRY)

    def test_m1_fair_registry_class_is_m1_fair_files(self):
        from methods import METHOD_REGISTRY
        from methods.m1_fair_files import M1FairFiles
        self.assertIs(METHOD_REGISTRY["M1_fair"], M1FairFiles)

    def test_m1_fair_instantiates_without_cks_tool(self):
        """M1FairFiles must not require a cks_tool argument."""
        from methods import METHOD_REGISTRY
        cls = METHOD_REGISTRY["M1_fair"]
        instance = cls(go_stablenet_root="/tmp")
        self.assertIsNotNone(instance)

    def test_m1_fair_method_id_attribute(self):
        from methods.m1_fair_files import M1FairFiles
        self.assertEqual(M1FairFiles.method_id, "M1_fair")


if __name__ == "__main__":
    unittest.main()
