#!/usr/bin/env python3
"""Tests for the sub-agent model-pin pre-flight check and the session model reader.

The property both modules exist to hold: a pin that will not take effect is *reported*,
because at runtime it is silent. The property they must not break: no model id ever
reaches the output, since on Bedrock an id is a region-prefixed profile or an ARN.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import session_models  # noqa: E402
from setup_checks import model_pins  # noqa: E402

# A realistic Bedrock id and an ARN — neither may appear in any output.
BEDROCK_ID = "us.anthropic.claude-opus-4-8"
BEDROCK_ARN = "arn:aws:bedrock:ap-northeast-2:123456789012:inference-profile/custom-x"


def _agents(tmp: Path, pins: dict[str, str]) -> Path:
    d = tmp / "agents"
    d.mkdir()
    for name, model in pins.items():
        (d / f"{name}.md").write_text(f"---\nname: {name}\nmodel: {model}\n---\nbody\n")
    return d


class TestProviderDetection(unittest.TestCase):
    def test_bedrock_and_vertex_and_default(self):
        self.assertEqual(model_pins.detect_provider({"CLAUDE_CODE_USE_BEDROCK": "1"}), "bedrock")
        self.assertEqual(model_pins.detect_provider({"CLAUDE_CODE_USE_VERTEX": "true"}), "vertex")
        self.assertEqual(model_pins.detect_provider({}), "first_party")

    def test_only_affirmative_values_mean_bedrock(self):
        """`0` reads as off here -- that is what someone setting `0` means by it."""
        for v in ("1", "true", "TRUE", "yes", "on", " 1 "):
            self.assertEqual(model_pins.detect_provider({"CLAUDE_CODE_USE_BEDROCK": v}),
                             "bedrock", v)
        for v in ("0", "false", "no", "off", ""):
            self.assertEqual(model_pins.detect_provider({"CLAUDE_CODE_USE_BEDROCK": v}),
                             "first_party", v)
        self.assertEqual(model_pins.detect_provider({}), "first_party")

    def test_a_non_affirmative_value_is_reported_as_a_disagreement(self):
        """The CLI reads `0` as Bedrock, so reading it as off here opens a window where
        the tier checks are skipped while requests still go to Bedrock. The window is
        allowed (ADR-0022) but must not be silent."""
        for v in ("0", "false", "off", "no"):
            self.assertEqual(
                model_pins.provider_flag_disagrees({"CLAUDE_CODE_USE_BEDROCK": v}),
                ["CLAUDE_CODE_USE_BEDROCK"], v)

    def test_no_disagreement_when_the_two_rules_agree(self):
        for env in ({}, {"CLAUDE_CODE_USE_BEDROCK": ""},
                    {"CLAUDE_CODE_USE_BEDROCK": "1"},
                    {"CLAUDE_CODE_USE_BEDROCK": "true"}):
            self.assertEqual(model_pins.provider_flag_disagrees(env), [], env)

    def test_the_disagreement_surfaces_as_an_issue(self):
        with tempfile.TemporaryDirectory() as d:
            agents = Path(d)
            (agents / "a.md").write_text("---\nmodel: opus\n---\n")
            res = model_pins.check(agents, {"CLAUDE_CODE_USE_BEDROCK": "0"})
        kinds = [i["kind"] for i in res["issues"]]
        self.assertIn("provider_flag_disagrees", kinds)
        self.assertEqual(res["provider"], "first_party")


class TestPinCheck(unittest.TestCase):
    def test_aliases_on_first_party_are_clean(self):
        with tempfile.TemporaryDirectory() as d:
            ad = _agents(Path(d), {"planner": "opus", "implementer": "sonnet"})
            r = model_pins.check(ad, env={})
            self.assertTrue(r["ok"])
            self.assertEqual(r["aliases"], ["opus", "sonnet"])

    def test_bedrock_without_tier_env_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            ad = _agents(Path(d), {"planner": "opus"})
            r = model_pins.check(ad, env={"CLAUDE_CODE_USE_BEDROCK": "1"})
            self.assertFalse(r["ok"])
            self.assertIn("tier_alias_unmapped", [i["kind"] for i in r["issues"]])

    def test_bedrock_with_tier_env_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            ad = _agents(Path(d), {"planner": "opus"})
            r = model_pins.check(ad, env={"CLAUDE_CODE_USE_BEDROCK": "1",
                                          "ANTHROPIC_DEFAULT_OPUS_MODEL": BEDROCK_ID})
            self.assertTrue(r["ok"], r["issues"])
            self.assertEqual(r["alias_env_set"], {"opus": True})

    def test_concrete_id_is_flagged_on_any_provider(self):
        """The regression: a concrete id looks fine on first-party and dies quietly
        elsewhere, so it is rejected regardless of where the check runs."""
        for env in ({}, {"CLAUDE_CODE_USE_BEDROCK": "1"}):
            with tempfile.TemporaryDirectory() as d:
                ad = _agents(Path(d), {"planner": "claude-opus-4-8"})
                r = model_pins.check(ad, env=env)
                self.assertIn("pin_is_concrete_id", [i["kind"] for i in r["issues"]], env)

    def test_global_override_flattens_tiers(self):
        with tempfile.TemporaryDirectory() as d:
            ad = _agents(Path(d), {"planner": "opus", "implementer": "sonnet"})
            r = model_pins.check(ad, env={"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"})
            self.assertIn("subagent_model_override", [i["kind"] for i in r["issues"]])

    def test_inherit_is_not_treated_as_a_concrete_id(self):
        with tempfile.TemporaryDirectory() as d:
            ad = _agents(Path(d), {"x": "inherit"})
            r = model_pins.check(ad, env={"CLAUDE_CODE_USE_BEDROCK": "1"})
            self.assertTrue(r["ok"], r["issues"])


class TestNoValueLeaks(unittest.TestCase):
    """A Bedrock model id is an internal cloud resource identifier. It must not reach
    the result dict or the rendered lines by any path."""

    def _assert_clean(self, blob: str):
        for secret in (BEDROCK_ID, BEDROCK_ARN, "123456789012", "ap-northeast-2"):
            self.assertNotIn(secret, blob)

    def test_check_result_and_render_carry_no_id(self):
        with tempfile.TemporaryDirectory() as d:
            ad = _agents(Path(d), {"planner": "opus", "implementer": "sonnet"})
            env = {"CLAUDE_CODE_USE_BEDROCK": "1",
                   "ANTHROPIC_DEFAULT_OPUS_MODEL": BEDROCK_ID,
                   "ANTHROPIC_DEFAULT_SONNET_MODEL": BEDROCK_ARN}
            r = model_pins.check(ad, env=env)
            self._assert_clean(json.dumps(r))
            self._assert_clean("\n".join(model_pins.render(r)))

    def test_family_of_never_returns_input_fragments(self):
        self.assertEqual(session_models.family_of(BEDROCK_ID), "opus")
        self.assertEqual(session_models.family_of("apac.anthropic.claude-sonnet-5"), "sonnet")
        # An ARN with no family name in it must be refused, not guessed at.
        self.assertEqual(session_models.family_of(BEDROCK_ARN), session_models.UNIDENTIFIABLE)

    def test_scan_output_carries_no_id(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in [
                {"message": {"model": BEDROCK_ID, "usage": {}}},
                {"isSidechain": True, "message": {"model": BEDROCK_ARN, "usage": {}}},
            ]))
            self._assert_clean(json.dumps(session_models.verdict(session_models.scan(p))))


class TestSessionModels(unittest.TestCase):
    def _write(self, path: Path, rows):
        path.write_text("\n".join(json.dumps(r) for r in rows))

    def test_distinct_subagent_family_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            self._write(p, [
                {"message": {"model": "claude-sonnet-5"}},
                {"isSidechain": True, "message": {"model": "claude-opus-4-8"}},
            ])
            v = session_models.verdict(session_models.scan(p))
            self.assertTrue(v["has_distinct"])
            self.assertEqual(v["distinct_subagent_families"], ["opus"])

    def test_collapsed_subagent_is_not_distinct(self):
        """The adjudicator falling back to the parent model: same family both sides."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            self._write(p, [
                {"message": {"model": "claude-opus-4-8"}},
                {"isSidechain": True, "message": {"model": "claude-opus-4-8"}},
            ])
            v = session_models.verdict(session_models.scan(p))
            self.assertFalse(v["has_distinct"])
            self.assertTrue(v["subagent_turns_seen"])

    def test_no_subagent_turns_is_not_independence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            self._write(p, [{"message": {"model": "claude-opus-4-8"}}])
            v = session_models.verdict(session_models.scan(p))
            self.assertFalse(v["has_distinct"])
            self.assertFalse(v["subagent_turns_seen"])

    def test_synthetic_and_partial_lines_tolerated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_text(json.dumps({"message": {"model": "<synthetic>"}}) + "\n"
                         + json.dumps({"message": {"model": "claude-opus-4-8"}}) + "\n"
                         + '{"message": {"model": "claude-son')     # truncated write
            v = session_models.verdict(session_models.scan(p))
            self.assertEqual(v["main_families"], ["opus"])

    def test_missing_transcript_fails_require_distinct(self):
        """Unknown is not proof of independence -- --require-distinct must not pass."""
        with tempfile.TemporaryDirectory() as d:
            rc = session_models.main(["--transcript", str(Path(d) / "nope.jsonl"),
                                      "--require-distinct"])
            self.assertEqual(rc, 1)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            self._write(p, [
                {"message": {"model": "claude-sonnet-5"}},
                {"isSidechain": True, "message": {"model": "claude-opus-4-8"}},
            ])
            self.assertEqual(session_models.main(["--transcript", str(p)]), 0)
            self.assertEqual(
                session_models.main(["--transcript", str(p), "--require-distinct"]), 0)


if __name__ == "__main__":
    unittest.main()
