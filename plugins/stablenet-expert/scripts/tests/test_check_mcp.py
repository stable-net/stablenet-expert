#!/usr/bin/env python3
"""Tests for check-mcp-connectivity.sh / check-mcp-conflicts.sh marketplace scoping.

Both scripts scan *every* enabled plugin, across every marketplace — deliberately, since a
foreign plugin can genuinely collide with one of ours (ADR-0010's motivating case). What they
must not do is present a foreign plugin's problem as something this doctor can fix: Step 4's
delegation is scoped to this marketplace's plugins and a foreign plugin ships no ADR-0014
`scripts/setup.py`, so a `critical` row for one becomes a checkbox that leads nowhere
(ADR-0019).

The contract fixed here: rows for plugins outside this marketplace carry status `external`,
which doctor reports but never offers as a fix.

Run:  python3 -m unittest discover -s plugins/stablenet-expert/scripts/tests
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
CONNECTIVITY = _SCRIPTS / "check-mcp-connectivity.sh"
CONFLICTS = _SCRIPTS / "check-mcp-conflicts.sh"

MARKETPLACE = "stablenet-expert"
OURS = f"core-dev@{MARKETPLACE}"
FOREIGN = "coding-agent@coding-agent"
FOREIGN2 = "other-agent@other-marketplace"

# PATH is kept so `command -v python3` works inside the scripts. Everything else is dropped so
# a developer's own exported CHAINBENCH_DIR/etc. cannot resolve a var the test means to leave
# missing -- both scripts fall back to os.environ after settings `env`.
_CLEAN_ENV = {"PATH": os.environ.get("PATH", "")}

# An absolute path that exists and is executable on every platform CI runs on, for stdio
# servers that should resolve cleanly without touching the network.
REAL_BIN = "/bin/sh"


class Sandbox:
    """A fake HOME with a plugin registry, settings, and per-plugin .mcp.json files."""

    def __init__(self, tmp: Path):
        self.home = tmp / "home"
        (self.home / ".claude" / "plugins").mkdir(parents=True)
        self.plugins: dict[str, dict] = {}
        self.enabled: dict[str, bool] = {}
        self.env: dict[str, str] = {}

    def add(self, key: str, servers: dict, enabled: bool = True) -> "Sandbox":
        root = self.home / "installed" / key.replace("@", "_at_")
        root.mkdir(parents=True, exist_ok=True)
        (root / ".mcp.json").write_text(json.dumps({"mcpServers": servers}))
        self.plugins[key] = {"installPath": str(root)}
        self.enabled[key] = enabled
        return self

    def write(self) -> "Sandbox":
        claude = self.home / ".claude"
        (claude / "settings.json").write_text(json.dumps(
            {"enabledPlugins": self.enabled, "env": self.env}))
        (claude / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {k: [v] for k, v in self.plugins.items()}}))
        return self

    def run(self, script: Path) -> list[tuple[str, str, str]]:
        self.write()
        env = dict(_CLEAN_ENV, HOME=str(self.home))
        proc = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)
        assert proc.returncode == 0, f"{script.name} exited {proc.returncode}: {proc.stderr}"
        rows = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("|", 2)]
            assert len(parts) == 3, f"malformed row: {line!r}"
            rows.append(tuple(parts))
        return rows


def statuses(rows, name_contains: str) -> list[str]:
    return [s for n, s, _ in rows if name_contains in n]


def detail_for(rows, name_contains: str) -> str:
    return next(d for n, _, d in rows if name_contains in n)


def stdio(command: str, args=None, env=None) -> dict:
    cfg: dict = {"command": command}
    if args is not None:
        cfg["args"] = args
    if env is not None:
        cfg["env"] = env
    return cfg


class TestConnectivityScoping(unittest.TestCase):
    """check-mcp-connectivity.sh — Step 2."""

    def test_owned_plugin_missing_env_stays_critical(self):
        """Our own plugin's unconfigured env is actionable: Step 4 can delegate to its setup.py."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(OURS, {"chainbench": stdio("${MISSING_BIN}")})
                    .run(CONNECTIVITY))
            self.assertEqual(statuses(rows, OURS), ["critical"])

    def test_foreign_plugin_missing_env_is_external_not_critical(self):
        """The regression this fixes: coding-agent's three unconfigured servers became
        checkboxes doctor had no setup.py to act on."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(FOREIGN, {"cks": stdio("${CKS_MCP_BIN}", ["-config", "${CKS_CONFIG}"])})
                    .run(CONNECTIVITY))
            self.assertEqual(statuses(rows, FOREIGN), ["external"])

    def test_foreign_plugin_missing_binary_is_external(self):
        """Not just env refs -- an unresolvable binary for a foreign plugin is equally
        unfixable from here."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(FOREIGN, {"chainbench": stdio("/nonexistent/chainbench-mcp")})
                    .run(CONNECTIVITY))
            self.assertEqual(statuses(rows, FOREIGN), ["external"])

    def test_foreign_plugin_does_not_block_overall_pass(self):
        """A foreign plugin's broken server is not this marketplace's failure."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(OURS, {"ok": stdio(REAL_BIN)})
                    .add(FOREIGN, {"cks": stdio("${CKS_MCP_BIN}")})
                    .run(CONNECTIVITY))
            self.assertIn("ALL_MCP_CONNECTIVITY_PASS", [n for n, _, _ in rows])

    def test_owned_failure_still_blocks_overall_pass(self):
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(OURS, {"broken": stdio("${MISSING_BIN}")})
                    .add(FOREIGN, {"cks": stdio(REAL_BIN)})
                    .run(CONNECTIVITY))
            self.assertNotIn("ALL_MCP_CONNECTIVITY_PASS", [n for n, _, _ in rows])

    def test_external_row_says_why_it_is_not_actionable(self):
        """A bare status change would leave the reader guessing; the row has to say that this
        doctor does not configure the plugin."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(FOREIGN, {"cks": stdio("${CKS_MCP_BIN}")})
                    .run(CONNECTIVITY))
            detail = detail_for(rows, FOREIGN).lower()
            self.assertIn(MARKETPLACE, detail)

    def test_external_row_still_names_the_missing_vars(self):
        """Downgrading actionability must not downgrade the diagnosis -- the whole point of
        reporting the row at all is telling the user what is unconfigured."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(FOREIGN, {"cks": stdio("${CKS_MCP_BIN}", ["-config", "${CKS_CONFIG}"])})
                    .run(CONNECTIVITY))
            detail = detail_for(rows, FOREIGN)
            self.assertIn("CKS_MCP_BIN", detail)
            self.assertIn("CKS_CONFIG", detail)

    def test_external_row_never_prints_a_resolved_value(self):
        """ADR-0012's non-disclosure rule is independent of scoping and must survive it."""
        with tempfile.TemporaryDirectory() as d:
            box = Sandbox(Path(d)).add(FOREIGN, {"api": {"type": "http", "url": "${SECRET_URL}"}})
            box.env = {"SECRET_URL": "http://10.1.2.3:9999/internal"}
            rows = box.run(CONNECTIVITY)
            joined = " ".join(d for _, _, d in rows)
            self.assertNotIn("10.1.2.3", joined)

    def test_disabled_foreign_plugin_is_not_reported_at_all(self):
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(FOREIGN, {"cks": stdio("${CKS_MCP_BIN}")}, enabled=False)
                    .run(CONNECTIVITY))
            self.assertEqual(statuses(rows, FOREIGN), [])


class TestConflictScoping(unittest.TestCase):
    """check-mcp-conflicts.sh — Step 5."""

    def test_conflict_involving_our_plugin_stays_critical(self):
        """ADR-0010's motivating case: a foreign plugin silently disconnecting ours is
        actionable, and Step 5 legitimately asks which to keep."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(OURS, {"chainbench": stdio(REAL_BIN)})
                    .add(FOREIGN, {"chainbench": stdio(REAL_BIN)})
                    .run(CONFLICTS))
            self.assertEqual(statuses(rows, "MCP conflict"), ["critical"])

    def test_conflict_between_two_foreign_plugins_is_external(self):
        """Neither participant is ours; disabling one would be this doctor acting on plugins
        it does not own."""
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(FOREIGN, {"cks": stdio(REAL_BIN)})
                    .add(FOREIGN2, {"cks": stdio(REAL_BIN)})
                    .run(CONFLICTS))
            self.assertEqual(statuses(rows, "MCP conflict"), ["external"])

    def test_foreign_only_conflict_still_reports_pass(self):
        with tempfile.TemporaryDirectory() as d:
            rows = (Sandbox(Path(d))
                    .add(OURS, {"mine": stdio("/opt/mine")})
                    .add(FOREIGN, {"cks": stdio(REAL_BIN)})
                    .add(FOREIGN2, {"cks": stdio(REAL_BIN)})
                    .run(CONFLICTS))
            self.assertIn("ALL_MCP_CONFLICTS_PASS", [n for n, _, _ in rows])


if __name__ == "__main__":
    unittest.main()
