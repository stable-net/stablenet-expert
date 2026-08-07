#!/usr/bin/env python3
"""Mechanical checks on a value before it is written to settings.

Two different jobs, and only one of them is fully effective:

**Shape.** A URL that does not parse, or a directory that does not exist, is caught before it
reaches settings. Wholly effective -- a wrong value never gets stored, and the user is told what
was expected instead of discovering it when an MCP server fails to start.

**Credential smell.** A value that looks like a token is refused. This cannot un-expose anything:
if the value arrived through a question in the conversation, it was in the transcript before this
code ran. What it does prevent is the second, worse outcome -- a credential coming to rest in
settings.json, where it persists and gets read by every session. So it refuses the write and says
to use the hidden-input path instead, without ever repeating the value back.

The detection is deliberately conservative. A false positive costs the user one retry through a
slightly slower path; a false negative persists a secret. Prefixes are matched exactly rather
than by entropy, because entropy flags things like a long deployment path and teaches people to
ignore the warning.

No judgement calls are left to a caller: this returns a reason or None, and callers act on it.

Stdlib only, per ADR-0014.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

# Issuer prefixes, not shapes. Each is a documented format from a service whose tokens people
# actually paste by accident.
CREDENTIAL_PREFIXES = (
    "ATATT",        # Atlassian API token
    "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_",
    "sk-", "sk_live_", "sk_test_",   # OpenAI / Stripe
    "xoxb-", "xoxp-", "xapp-",       # Slack
    "AKIA",         # AWS access key id
    "glpat-",       # GitLab
    "-----BEGIN",   # a PEM private key pasted whole
)

# A JWT: three base64url segments. Long enough to not collide with ordinary text.
_JWT = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$")


def looks_like_credential(value: str) -> str | None:
    """A reason string when the value looks like a secret, else None."""
    v = value.strip()
    for prefix in CREDENTIAL_PREFIXES:
        if v.startswith(prefix):
            return f"starts with {prefix!r}, which is a credential prefix"
    if _JWT.match(v):
        return "has the three-part shape of a JWT"
    return None


def _check_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        return "must start with http:// or https://"
    if not parsed.netloc:
        return "has no host — expected http://host:port/path"
    if parsed.username or parsed.password:
        # Credentials in a URL are a credential, and they would be stored in a settings file
        # that is not treated as secret.
        return "carries credentials in the URL (user:pass@) — put those somewhere else"
    return None


def _check_dir(value: str) -> str | None:
    path = Path(value).expanduser()
    if not path.is_absolute():
        return "must be an absolute path"
    if not path.exists():
        return "does not exist on this machine"
    if not path.is_dir():
        return "is not a directory"
    return None


# What each key is, so the check can be specific rather than generic. A key that is not listed
# gets the credential check only -- being unlisted means we do not know its shape, and inventing
# a rule for it would reject valid values.
SHAPE = {
    "STABLENET_KNOWLEDGE_MCP_URL": ("an http(s) endpoint", _check_url),
    "CHAINBENCH_DIR": ("an existing directory", _check_dir),
    "GO_STABLENET_ROOT": ("an existing directory", _check_dir),
}


def check(key: str, value: str) -> str | None:
    """Return a reason the value is unacceptable, or None.

    The reason never contains the value. Callers print it, and a caller may be printing into a
    conversation -- repeating a rejected credential there would defeat the refusal.
    """
    if not value or not value.strip():
        return "is empty"

    reason = looks_like_credential(value)
    if reason:
        return (f"{reason}. Values like this are not written to settings.json — it is not a "
                f"secret store. Use scripts/set-mcp-env.sh, which prompts with hidden input in "
                f"your own terminal. If this really is {key}'s value and not a token, say so "
                f"and it can be set with --force-value.")

    named = SHAPE.get(key)
    if named:
        expected, fn = named
        reason = fn(value.strip())
        if reason:
            return f"{reason}. {key} expects {expected}."
    return None
