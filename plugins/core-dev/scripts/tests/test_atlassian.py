#!/usr/bin/env python3
"""Tests for the Atlassian dependency module.

The CLI is injected rather than mocked globally, so these run without a `claude` binary and
never touch the machine's plugin registry. The `claude mcp list` fixtures are verbatim lines
observed on 2026-08-06 -- if the CLI changes that format, detection silently degrades to
"missing" and re-installs an installed plugin, so pinning the real shape matters more here
than a tidy fake would.

Run:  python3 plugins/core-dev/scripts/tests/test_atlassian.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from setup_checks import atlassian  # noqa: E402

CONNECTED = ("plugin:atlassian:atlassian: https://mcp.atlassian.com/v1/mcp/authv2 "
             "(HTTP) - ✔ Connected")
NEEDS_AUTH = ("plugin:atlassian:atlassian: https://mcp.atlassian.com/v1/mcp/authv2 "
              "(HTTP) - ! Needs authentication")
OTHER_SERVERS = ("plugin:core-dev:chainbench: chainbench-mcp  - ✔ Connected\n"
                 "plugin:core-dev:stablenet-knowledge: http://10.0.0.1:8930/mcp (HTTP) "
                 "- ✔ Connected")


def runner(script):
    """A fake CLI: maps a command to (exit, output), and records what was called."""
    calls = []

    def run(args, timeout=120):
        calls.append(args)
        for prefix, result in script:
            if args[:len(prefix)] == prefix:
                return result
        return 0, ""

    run.calls = calls
    return run


class TestCheck(unittest.TestCase):
    def test_connected_is_ready(self):
        run = runner([(["claude", "mcp", "list"], (0, OTHER_SERVERS + "\n" + CONNECTED))])
        self.assertEqual(atlassian.check(run)["status"], atlassian.READY)

    def test_needs_authentication_is_not_ready(self):
        """The distinction the HTTP probe in check-mcp-connectivity.sh cannot make: an
        OAuth server answers while unauthenticated, so reachable != usable."""
        run = runner([(["claude", "mcp", "list"], (0, OTHER_SERVERS + "\n" + NEEDS_AUTH))])
        state = atlassian.check(run)
        self.assertEqual(state["status"], atlassian.UNAUTHENTICATED)
        self.assertIn("OAuth", state["detail"])

    def test_absent_is_missing(self):
        run = runner([(["claude", "mcp", "list"], (0, OTHER_SERVERS))])
        self.assertEqual(atlassian.check(run)["status"], atlassian.MISSING)

    def test_unreachable_cli_is_unknown_not_missing(self):
        """"Could not ask" is not "not installed". Reporting MISSING here would offer to
        install a plugin that may already be there, on the strength of an unrelated failure
        — and an environment that answers wrongly is not hypothetical: `claude mcp list`
        run without HOME reported an *uninstalled* plugin as connected."""
        for code, out in ((127, "claude CLI not found on PATH"),
                          (124, "timed out after 45s"),
                          (1, "some other failure")):
            with self.subTest(code=code):
                run = runner([(["claude", "mcp", "list"], (code, out))])
                self.assertEqual(atlassian.check(run)["status"], atlassian.UNKNOWN)

    def test_empty_output_is_unknown(self):
        """`claude mcp list` always prints something; nothing recognisable means the call
        did not do what we think, not that there are no servers."""
        run = runner([(["claude", "mcp", "list"], (0, "   \n"))])
        self.assertEqual(atlassian.check(run)["status"], atlassian.UNKNOWN)

    def test_unknown_state_offers_nothing_and_acts_on_nothing(self):
        run = runner([(["claude", "mcp", "list"], (127, "claude CLI not found on PATH"))])
        result = atlassian.fix(run, login=lambda: (_ for _ in ()).throw(
            AssertionError("must not act while the state is undetermined")))
        self.assertEqual(result["status"], atlassian.UNKNOWN)
        self.assertNotIn(["claude", "plugin", "install", atlassian.PLUGIN], run.calls)

        row = atlassian.row({"status": atlassian.UNKNOWN, "detail": "x"})
        self.assertFalse(row["auto_fixable"], "cannot fix what cannot be diagnosed")
        self.assertFalse(row["opens_browser"])

    def test_another_servers_auth_state_is_not_read_as_ours(self):
        """Substring matching on the whole output would let a neighbouring server's
        '✔ Connected' answer for us."""
        run = runner([(["claude", "mcp", "list"],
                       (0, "plugin:other:atlassian-ish: https://x (HTTP) - ✔ Connected"))])
        self.assertEqual(atlassian.check(run)["status"], atlassian.MISSING)

    def test_endpoint_is_not_echoed_in_the_detail(self):
        """detail is surfaced by doctor into the conversation; a server address is config,
        not report material."""
        run = runner([(["claude", "mcp", "list"], (0, OTHER_SERVERS + "\n" + NEEDS_AUTH))])
        self.assertNotIn("mcp.atlassian.com", atlassian.check(run)["detail"])


class TestFix(unittest.TestCase):
    def test_ready_dependency_is_left_alone(self):
        run = runner([(["claude", "mcp", "list"], (0, CONNECTED))])
        result = atlassian.fix(run, login=lambda: (_ for _ in ()).throw(
            AssertionError("must not attempt login when already authenticated")))
        self.assertFalse(result["changed"])
        self.assertEqual(result["status"], atlassian.READY)

    def test_installed_but_unauthenticated_skips_install(self):
        run = runner([(["claude", "mcp", "list"], (0, NEEDS_AUTH))])
        atlassian.fix(run, login=lambda: (True, "ok"))
        self.assertNotIn(["claude", "plugin", "install", atlassian.PLUGIN], run.calls)

    def test_missing_adds_marketplace_then_installs(self):
        run = runner([
            (["claude", "mcp", "list"], (0, OTHER_SERVERS)),
            (["claude", "plugin", "marketplace", "list"], (0, "coding-agent")),
        ])
        atlassian.fix(run, login=lambda: (True, "ok"))
        self.assertIn(["claude", "plugin", "marketplace", "add", atlassian.MARKETPLACE],
                      run.calls)
        self.assertIn(["claude", "plugin", "install", atlassian.PLUGIN], run.calls)

    def test_existing_marketplace_is_not_re_added(self):
        run = runner([
            (["claude", "mcp", "list"], (0, OTHER_SERVERS)),
            (["claude", "plugin", "marketplace", "list"], (0, atlassian.MARKETPLACE_NAME)),
        ])
        atlassian.fix(run, login=lambda: (True, "ok"))
        self.assertNotIn(["claude", "plugin", "marketplace", "add", atlassian.MARKETPLACE],
                         run.calls)

    def test_failed_install_does_not_attempt_login(self):
        run = runner([
            (["claude", "mcp", "list"], (0, OTHER_SERVERS)),
            (["claude", "plugin", "marketplace", "list"], (0, atlassian.MARKETPLACE_NAME)),
            (["claude", "plugin", "install"], (1, "network unreachable")),
        ])
        result = atlassian.fix(run, login=lambda: (_ for _ in ()).throw(
            AssertionError("must not log in to a plugin that failed to install")))
        self.assertEqual(result["status"], atlassian.MISSING)

    def test_abandoned_consent_is_reported_not_swallowed(self):
        """The status is re-read from the CLI after the attempt, so a login the user walked
        away from cannot be reported as success -- doctor would otherwise tell them to
        restart into a pipeline with no Jira access."""
        run = runner([(["claude", "mcp", "list"], (0, NEEDS_AUTH))])
        result = atlassian.fix(run, login=lambda: (False, "login_timeout"))
        self.assertEqual(result["status"], atlassian.UNAUTHENTICATED)
        self.assertIn("login_timeout", result["detail"])


class TestRow(unittest.TestCase):
    def test_row_carries_what_the_caller_renders(self):
        row = atlassian.row({"status": atlassian.MISSING, "detail": "plugin not installed"})
        for field in ("key", "row_kind", "description", "how_to_find", "status",
                      "auto_fixable", "opens_browser", "secret"):
            self.assertIn(field, row)
        self.assertEqual(row["row_kind"], "plugin")
        self.assertFalse(row["secret"])

    def test_unready_row_warns_about_the_browser(self):
        """doctor puts this in the confirmation prompt; a browser opening unannounced is
        the kind of side effect a user should agree to first."""
        for status in (atlassian.MISSING, atlassian.UNAUTHENTICATED):
            row = atlassian.row({"status": status, "detail": "x"})
            self.assertTrue(row["auto_fixable"])
            self.assertTrue(row["opens_browser"])

    def test_ready_row_offers_nothing_to_do(self):
        row = atlassian.row({"status": atlassian.READY, "detail": "x"})
        self.assertFalse(row["auto_fixable"])
        self.assertFalse(row["opens_browser"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
