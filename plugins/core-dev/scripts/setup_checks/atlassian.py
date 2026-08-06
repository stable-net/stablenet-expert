#!/usr/bin/env python3
"""Atlassian MCP plugin — detection and setup.

core-dev reads Jira tickets through the official Atlassian MCP plugin, which lives in
Anthropic's `claude-plugins-official` marketplace rather than this one. It is a hard
dependency of the pipeline (the ticket is the pipeline's input), so setup.py both reports
on it and, when asked, installs and authenticates it.

Three things about the `claude` CLI shape this module, all measured on 2026-08-06:

1. `claude mcp list` reports a just-installed plugin's server *without a session restart*.
   The CLI is a fresh process reading config from disk; only the running session's server
   list is stale. That is why install and login can happen in one doctor pass.

2. `claude mcp login` refuses to run when stdin is not a terminal -- in *both* modes. It
   opens the browser and starts waiting, then aborts with "stdin isn't a terminal". So
   `--no-browser` is not a fallback for automation: it is *more* interactive, since it
   also wants the redirect URL pasted back.

3. Allocating a pty satisfies that check. The browser flow then completes on its own via
   the CLI's local callback -- the terminal only has to exist, not to be typed into.

Consequently the login path here allocates a pty and imposes its own deadline: the CLI
waits indefinitely ("^C to cancel"), so without one an unattended doctor run would hang
forever.

Stdlib only, per ADR-0014.
"""

from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import time

PLUGIN = "atlassian@claude-plugins-official"
MARKETPLACE = "anthropics/claude-plugins-official"
MARKETPLACE_NAME = "claude-plugins-official"
SERVER = "plugin:atlassian:atlassian"

# How long to wait for the human to finish the browser consent before giving up. Generous:
# the flow includes an OAuth login and a permission grant, and a premature kill looks to
# the user like the tool broke rather than like they were slow.
LOGIN_TIMEOUT_SECONDS = 180

# Status values, in increasing order of readiness.
MISSING = "missing"              # plugin not installed
UNAUTHENTICATED = "installed"    # installed, OAuth not completed
READY = "authenticated"
UNKNOWN = "unknown"              # the CLI could not be consulted -- state undetermined

DESCRIPTION = ("Jira access for the pipeline -- reads the ticket, posts comments, moves "
               "status. core-dev takes its work item from here, so /core-dev:work cannot "
               "start without it.")
HOW_TO_FIND = (f"external plugin: claude plugin marketplace add {MARKETPLACE} && "
               f"claude plugin install {PLUGIN}, then claude mcp login {SERVER}")


def _run(args, timeout=120):
    """Run a claude CLI command, capturing output. Never raises on non-zero exit."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return 127, "claude CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"


def check(run=_run) -> dict:
    """Current state of the Atlassian dependency.

    Reads `claude mcp list`, whose line for a server carries both existence and auth state:

        plugin:atlassian:atlassian: https://... (HTTP) - ! Needs authentication
        plugin:atlassian:atlassian: https://... (HTTP) - ✔ Connected

    An HTTP probe cannot substitute for this: an OAuth server answers while unauthenticated,
    so reachability and authorisation are different questions and only the CLI reports the
    second one.
    """
    # A short leash: `claude mcp list` health-checks every configured server, so it is a
    # network call, not a config read. Doctor should report a slow CLI, not inherit its wait.
    code, out = run(["claude", "mcp", "list"], timeout=45)
    if code != 0:
        # Do not translate "could not ask" into "not installed" -- that would offer to
        # install something that may already be there, and would report a dependency as
        # absent on the strength of an unrelated failure.
        reason = {127: "claude CLI not found on PATH",
                  124: "claude mcp list timed out"}.get(code, f"claude mcp list failed ({code})")
        return {"status": UNKNOWN, "detail": reason}

    for line in out.splitlines():
        if not line.startswith(SERVER + ":"):
            continue
        if "Needs authentication" in line:
            return {"status": UNAUTHENTICATED,
                    "detail": "plugin installed, OAuth not completed"}
        if "Connected" in line:
            return {"status": READY, "detail": "installed and authenticated"}
        # Some other state (failed, connecting). Report it rather than guessing, minus the
        # URL -- an endpoint belongs in the user's config, not in a report that may be read
        # aloud into a conversation.
        tail = line.split(" - ", 1)[-1] if " - " in line else "unknown state"
        return {"status": UNAUTHENTICATED, "detail": tail.strip()}

    if "Checking MCP server health" in out or ":" in out:
        return {"status": MISSING, "detail": "plugin not installed"}
    # Exit 0 with nothing recognisable in it. Rather than read that as "no servers, so it
    # is missing", say so: an empty answer from a tool that always prints something is a
    # sign the tool did not do what we think.
    return {"status": UNKNOWN, "detail": "claude mcp list returned no server list"}


def _install(run=_run) -> tuple[bool, str]:
    """Add the marketplace if needed, then install the plugin."""
    code, out = run(["claude", "plugin", "marketplace", "list"])
    if MARKETPLACE_NAME not in out:
        code, out = run(["claude", "plugin", "marketplace", "add", MARKETPLACE], timeout=180)
        if code != 0:
            return False, f"marketplace add failed: {out.strip()[:200]}"

    code, out = run(["claude", "plugin", "install", PLUGIN], timeout=180)
    if code != 0:
        return False, f"plugin install failed: {out.strip()[:200]}"
    return True, "plugin installed"


def _login(timeout=LOGIN_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Run the OAuth flow, returning (ok, status-word).

    A pty is allocated because the CLI checks `isatty` before starting (see module docstring).
    Nothing is ever written to it: the browser callback completes the flow, and the pty exists
    only to pass that check. Output is drained so the child cannot block on a full buffer.
    """
    try:
        master, slave = pty.openpty()
    except OSError as exc:                       # no pty available (rare; some containers)
        return False, f"no_pty:{exc}"

    try:
        proc = subprocess.Popen(["claude", "mcp", "login", SERVER],
                                stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    except FileNotFoundError:
        os.close(master); os.close(slave)
        return False, "claude_cli_missing"
    os.close(slave)

    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if select.select([master], [], [], 0.5)[0]:
                try:
                    if not os.read(master, 4096):
                        break
                except OSError:
                    break
        else:
            proc.kill()
            proc.wait(timeout=5)
            return False, "login_timeout"
    finally:
        try:
            os.close(master)
        except OSError:
            pass

    if proc.poll() is None:                      # exited the loop without finishing
        proc.kill()
        proc.wait(timeout=5)
        return False, "login_timeout"
    return (proc.returncode == 0), ("ok" if proc.returncode == 0 else "login_failed")


def fix(run=_run, login=_login) -> dict:
    """Install and authenticate as needed. Idempotent: a ready dependency is left alone.

    Returns {"changed", "status", "detail"} -- `status` is re-derived from the CLI rather
    than assumed from the actions taken, so a login that silently failed cannot be reported
    as success.
    """
    state = check(run)
    if state["status"] == READY:
        return {"changed": False, "status": READY, "detail": "already authenticated"}
    if state["status"] == UNKNOWN:
        # Installing on a guess could duplicate an existing install or fire an OAuth flow
        # the user does not need. Report and stop.
        return {"changed": False, "status": UNKNOWN, "detail": state["detail"]}

    steps = []
    if state["status"] == MISSING:
        ok, detail = _install(run)
        if not ok:
            return {"changed": False, "status": MISSING, "detail": detail}
        steps.append(detail)

    ok, why = login()
    steps.append("authenticated" if ok else f"authentication incomplete ({why})")

    after = check(run)
    return {"changed": True, "status": after["status"], "detail": "; ".join(steps)}


def row(state: dict) -> dict:
    """The --json row for this dependency, in setup.py's schema."""
    return {
        "key": "atlassian-mcp",
        "row_kind": "plugin",
        "kind": "external plugin",
        "description": DESCRIPTION,
        "how_to_find": HOW_TO_FIND,
        "status": state["status"],
        "detail": state["detail"],
        # A plugin install plus an OAuth grant is fixable without asking for any value, but
        # it is not silent: a browser window opens and the user must consent. `opens_browser`
        # exists so the caller can say so *before* asking, rather than surprising them.
        # Actionable only when we know what is wrong. UNKNOWN offers nothing: the fix for
        # "I could not ask" is for the user to repair their CLI, not for us to guess.
        "auto_fixable": state["status"] in (MISSING, UNAUTHENTICATED),
        "opens_browser": state["status"] in (MISSING, UNAUTHENTICATED),
        "secret": False,
    }
