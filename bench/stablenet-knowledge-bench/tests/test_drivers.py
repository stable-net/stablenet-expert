"""test_drivers.py — unit tests for drivers.base, drivers.replay, drivers.claude_cli.

All tests are offline; no live AI calls are made.
"""

import json
import os
import sys
import tempfile
import unittest

# Ensure the stablenet-knowledge-bench package root is on the path
_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from drivers.base import AskResult, Driver, ToolCall
from drivers.replay import ReplayDriver
from drivers.claude_cli import ClaudeCLIDriver


class TestAskResult(unittest.TestCase):
    def test_ok_true_when_no_error(self):
        r = AskResult(response_text="hello", input_tokens=10, output_tokens=5)
        self.assertTrue(r.ok)
        self.assertIsNone(r.error)

    def test_ok_false_when_error(self):
        r = AskResult.from_error("something broke")
        self.assertFalse(r.ok)
        self.assertEqual(r.response_text, "")
        self.assertEqual(r.input_tokens, 0)

    def test_from_error_driver_name(self):
        r = AskResult.from_error("err", driver_name="replay")
        self.assertEqual(r.driver_name, "replay")


class TestDriverProtocol(unittest.TestCase):
    def test_base_driver_raises(self):
        d = Driver()
        with self.assertRaises(NotImplementedError):
            d.ask("sys", "usr")


class TestReplayDriver(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_write_and_read_fixture(self):
        """Write a fixture then read it back — exact match."""
        sys_p = "You are a helpful assistant."
        usr_p = "What is QuorumSize?"
        resp = '{"answer": "floor(2N/3)+1", "citations": []}'

        fixture_path = ReplayDriver.write_fixture(
            self._tmpdir,
            system_prompt=sys_p,
            user_prompt=usr_p,
            response_text=resp,
            input_tokens=123,
            output_tokens=45,
            turns=1,
        )
        self.assertTrue(os.path.isfile(fixture_path))

        driver = ReplayDriver(self._tmpdir, strict=True)
        result = driver.ask(sys_p, usr_p)
        self.assertTrue(result.ok)
        self.assertEqual(result.response_text, resp)
        self.assertEqual(result.input_tokens, 123)
        self.assertEqual(result.output_tokens, 45)
        self.assertEqual(result.turns, 1)
        self.assertEqual(result.driver_name, "replay")

    def test_replay_miss_strict(self):
        """Missing fixture in strict mode returns error result."""
        driver = ReplayDriver(self._tmpdir, strict=True)
        result = driver.ask("sys", "unknown question")
        self.assertFalse(result.ok)
        self.assertIn("REPLAY_MISS", result.error)

    def test_replay_miss_non_strict(self):
        """Missing fixture in non-strict mode returns placeholder."""
        driver = ReplayDriver(self._tmpdir, strict=False)
        result = driver.ask("sys", "unknown question")
        self.assertTrue(result.ok)
        self.assertIn("REPLAY_PLACEHOLDER", result.response_text)

    def test_prompt_sha_deterministic(self):
        """Same prompts always produce the same SHA."""
        sha1 = ReplayDriver.prompt_sha("sys", "usr")
        sha2 = ReplayDriver.prompt_sha("sys", "usr")
        self.assertEqual(sha1, sha2)

    def test_prompt_sha_different_for_different_prompts(self):
        sha1 = ReplayDriver.prompt_sha("sys", "usr1")
        sha2 = ReplayDriver.prompt_sha("sys", "usr2")
        self.assertNotEqual(sha1, sha2)

    def test_index_updated_on_write(self):
        """write_fixture updates index.json."""
        ReplayDriver.write_fixture(
            self._tmpdir, "sys", "q1", "resp1", input_tokens=1, output_tokens=1
        )
        idx_path = os.path.join(self._tmpdir, "index.json")
        self.assertTrue(os.path.isfile(idx_path))
        with open(idx_path) as fh:
            index = json.load(fh)
        sha = ReplayDriver.prompt_sha("sys", "q1")
        self.assertIn(sha, index)

    def test_invalid_replay_dir(self):
        """ReplayDriver raises ValueError if replay_dir does not exist."""
        with self.assertRaises(ValueError):
            ReplayDriver("/nonexistent/path/xyz123")

    def test_tool_calls_round_trip(self):
        """Fixture with tool_calls round-trips correctly."""
        tool_calls = [{"turn": 1, "name": "find_symbol", "arguments": {"symbol": "QuorumSize"}, "result": {"file": "validator.go"}}]
        ReplayDriver.write_fixture(
            self._tmpdir, "sys", "tc_q", "response", input_tokens=10,
            output_tokens=5, turns=2, tool_calls=tool_calls
        )
        driver = ReplayDriver(self._tmpdir)
        result = driver.ask("sys", "tc_q")
        self.assertTrue(result.ok)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, "find_symbol")


class TestClaudeCLIDriverSmoke(unittest.TestCase):
    """Smoke tests for ClaudeCLIDriver — exercises code paths without live CLI."""

    def test_driver_name(self):
        d = ClaudeCLIDriver()
        self.assertEqual(d.name, "claude_cli")

    def test_missing_binary_returns_error(self):
        """When the CLI binary is absent, ask() returns error (no raise)."""
        d = ClaudeCLIDriver(claude_bin="/nonexistent/claude_cli_binary_xyz")
        result = d.ask("sys", "usr")
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)

    def test_build_cmd_includes_model(self):
        """_build_cmd includes --model flag when model is set."""
        d = ClaudeCLIDriver(model="claude-3-opus")
        cmd = d._build_cmd("You are a helper.")
        self.assertIn("--model", cmd)
        self.assertIn("claude-3-opus", cmd)

    def test_build_cmd_no_model(self):
        """_build_cmd omits --model flag when model is None."""
        d = ClaudeCLIDriver()
        cmd = d._build_cmd("You are a helper.")
        self.assertNotIn("--model", cmd)

    def test_build_cmd_uses_print_flag(self):
        """-p flag is present in the command."""
        d = ClaudeCLIDriver()
        cmd = d._build_cmd("sys")
        self.assertIn("-p", cmd)

    def test_build_cmd_uses_json_output(self):
        """--output-format json is present."""
        d = ClaudeCLIDriver()
        cmd = d._build_cmd("sys")
        self.assertIn("--output-format", cmd)
        idx = cmd.index("--output-format")
        self.assertEqual(cmd[idx + 1], "json")

    def test_build_cmd_no_message_flag(self):
        """--message flag must NOT appear (old API)."""
        d = ClaudeCLIDriver()
        cmd = d._build_cmd("sys")
        self.assertNotIn("--message", cmd)


if __name__ == "__main__":
    unittest.main()
