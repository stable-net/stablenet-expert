"""Map the tier aliases to this deployment's own Bedrock models, without committing them.

`opus` and `sonnet` in an agent's `model:` frontmatter resolve through
`ANTHROPIC_DEFAULT_<TIER>_MODEL`. On Bedrock that value is a region-prefixed inference
profile or an ARN — an internal cloud resource identifier under the group security
policy, so it cannot live in this repo. It also cannot live in `~/.claude/settings.json`,
which is where `setup --fix` puts every other env value (ADR-0018):

  * that file has no conditionals, so a Bedrock-only value applies on every machine and
    every provider, breaking sessions that are not on Bedrock at all;
  * its `env` block takes literals only — there is no `${VAR}` expansion (Claude Code
    expands `${...}` in HTTP-hook headers and MCP arguments, not here), so the ARN would
    have to be written out in full.

So this module writes a separate file that the *shell* sources, which is the one layer
that is per-machine, conditional, and already holds `CLAUDE_CODE_USE_BEDROCK` itself.
The repo keeps the variable names; the machine keeps the values.

**Values are never printed.** Every report here is `is this tier mapped`, never what it
maps to, matching `setup_checks/model_pins.py`. Do not "improve" this by echoing the
resolved id.

**The generated file is executed, not parsed.** A shell sources it at startup, so a value
is code. Values are accepted only if they match `_VALUE_OK` — the character set a model
id or ARN actually uses. Anything else is rejected rather than quoted-and-hoped-for.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# The tiers Claude Code resolves through an env var. `fable` is included for symmetry;
# nothing in core-dev pins it today.
TIERS = ("opus", "sonnet", "haiku", "fable")

DEFAULT_PATH = Path.home() / ".claude" / "bedrock-models.env"

_HEADER = "# Written by core-dev (scripts/bedrock_tiers.py). Do not commit."
# Matches `setup_checks.model_pins._truthy` exactly: only `1` is on (ADR-0022). Not the
# CLI's bare truthiness, under which `0` would still mean Bedrock.
_GUARD_OPEN = 'if [ "${CLAUDE_CODE_USE_BEDROCK:-}" = "1" ]; then'
_GUARD_CLOSE = "fi"

# A model id or inference-profile ARN uses only these. Everything else -- whitespace,
# quotes, `$`, backticks, `;` -- is rejected, because this value is written into a file
# the shell executes.
_VALUE_OK = re.compile(r"\A[A-Za-z0-9._:/-]+\Z")

_EXPORT_LINE = re.compile(
    r'^\s*export\s+ANTHROPIC_DEFAULT_([A-Z]+)_MODEL\s*=\s*"([^"]*)"\s*$', re.MULTILINE)


def env_var(tier: str) -> str:
    return f"ANTHROPIC_DEFAULT_{tier.upper()}_MODEL"


class ValueRejected(ValueError):
    """A supplied value is not shaped like a model id, so it is not written."""


def validate(tier: str, value: str) -> str:
    """Return the value if it is safe to write, else raise. Never echoes the value."""
    if tier not in TIERS:
        raise ValueRejected(f"unknown tier {tier!r}; expected one of {', '.join(TIERS)}")
    if not value:
        raise ValueRejected(f"{tier}: empty value")
    if not _VALUE_OK.match(value):
        # Deliberately does not include the value: it may be an ARN, and a rejected
        # value is exactly the kind that should not be echoed anywhere.
        raise ValueRejected(
            f"{tier}: value contains characters a model id never uses "
            f"(allowed: letters, digits and . _ : / -). Refusing to write it into a "
            f"file the shell executes.")
    return value


def read_existing(path: Path = DEFAULT_PATH) -> dict[str, str]:
    """{tier: value} already recorded. Used to merge, never to display."""
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    for m in _EXPORT_LINE.finditer(text):
        tier = m.group(1).lower()
        if tier in TIERS:
            out[tier] = m.group(2)
    return out


def render(values: dict[str, str]) -> str:
    """The file body. Ordered by TIERS so re-running produces no spurious diff."""
    lines = [
        _HEADER,
        "#",
        "# Maps the tier aliases used in agent frontmatter to the models this account",
        "# actually has. Sourced from your shell profile; the guard keeps it inert when",
        "# Bedrock is not in use, so a first-party session is unaffected.",
        "#",
        "# The guard matches core-dev's rule, not the CLI's: only CLAUDE_CODE_USE_BEDROCK=1",
        "# exports. Any other value, `true` included, does not. Note the CLI itself reads",
        "# any non-empty value as Bedrock -- unset the variable to switch provider for real.",
        "",
        _GUARD_OPEN,
    ]
    for tier in TIERS:
        if tier in values:
            lines.append(f'  export {env_var(tier)}="{values[tier]}"')
    lines.append(_GUARD_CLOSE)
    lines.append("")
    return "\n".join(lines)


def write(values: dict[str, str], path: Path = DEFAULT_PATH,
          merge: bool = True) -> dict:
    """Record `values`, keeping any tier already present. Returns presence only.

    The file is created 0600 before anything is written to it: it holds internal cloud
    resource identifiers, and a world-readable window between create and chmod is a
    window.
    """
    for tier, value in values.items():
        validate(tier, value)

    existing = read_existing(path) if merge else {}
    merged = {**existing, **values}
    body = render(merged)

    path.parent.mkdir(parents=True, exist_ok=True)
    # Write via a private temp file in the same directory, then replace, so a reader
    # never sees a partial file and the mode is never briefly wider.
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    os.chmod(path, 0o600)

    return {
        "path": str(path),
        "tiers": sorted(merged),
        "added": sorted(set(values) - set(existing)),
        "updated": sorted(t for t in values if t in existing and existing[t] != values[t]),
        "mode": "0600",
    }


def shell_line(path: Path = DEFAULT_PATH) -> str:
    """The single line a user adds to their shell profile."""
    shown = str(path)
    home = str(Path.home())
    if shown.startswith(home + os.sep):
        shown = "~" + shown[len(home):]
    return f'[ -f {shown} ] && source {shown}'


def profile_has_source(profile: Path, path: Path = DEFAULT_PATH) -> bool:
    """Is the file already wired into this shell profile?"""
    if not profile.is_file():
        return False
    text = profile.read_text(encoding="utf-8", errors="replace")
    return path.name in text


def status(path: Path = DEFAULT_PATH, env: dict | None = None,
           profiles: list[Path] | None = None) -> dict:
    """Where each tier stands: in the file, live in the session, wired into a profile.

    Presence only. `file` says a tier is recorded, not what it records.
    """
    e = os.environ if env is None else env
    recorded = read_existing(path)
    if profiles is None:
        home = Path.home()
        profiles = [home / ".zshrc", home / ".zshenv", home / ".zprofile",
                    home / ".bash_profile", home / ".bashrc"]
    sourced_by = [str(p) for p in profiles if profile_has_source(p, path)]
    return {
        "path": str(path),
        "exists": path.is_file(),
        "mode": oct(path.stat().st_mode & 0o777) if path.is_file() else None,
        "file": {t: (t in recorded) for t in TIERS},
        "live": {t: bool(e.get(env_var(t))) for t in TIERS},
        "sourced_by": sourced_by,
        "wired": bool(sourced_by),
    }


def render_status(st: dict) -> list[str]:
    """Lines for human output. Carries no model id."""
    lines = [f"  bedrock tiers : {st['path']} "
             f"{'exists' if st['exists'] else 'MISSING'}"
             f"{' mode=' + st['mode'] if st['mode'] else ''}"]
    recorded = [t for t, ok in st["file"].items() if ok]
    live = [t for t, ok in st["live"].items() if ok]
    lines.append(f"                  recorded={','.join(recorded) or '-'} "
                 f"live={','.join(live) or '-'}")
    if st["exists"] and not st["wired"]:
        lines.append("    ⚠ [tier_file_not_sourced] the file exists but no shell profile "
                     "sources it, so the session never sees it — add:")
        lines.append(f"        {shell_line(Path(st['path']))}")
    if st["exists"] and st["mode"] not in (None, "0o600"):
        lines.append(f"    ⚠ [tier_file_mode] {st['mode']} — holds internal cloud resource "
                     f"identifiers; expected 0600")
    return lines


def _parse_set(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise ValueRejected(f"--set expects TIER=VALUE, got {raw.split('=')[0]!r}")
        tier, value = raw.split("=", 1)
        out[tier.strip().lower()] = value.strip()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Map tier aliases to this deployment's Bedrock models. "
                    "Values are written to a local file the shell sources; they never "
                    "enter this repo and are never printed.")
    ap.add_argument("--set", action="append", default=[], metavar="TIER=VALUE",
                    help="e.g. --set opus=\"$MY_OPUS_ARN\". Pass the shell variable, not "
                         "the literal ARN, so your shell history keeps the name only.")
    ap.add_argument("--path", default=str(DEFAULT_PATH),
                    help=f"target file (default {DEFAULT_PATH})")
    ap.add_argument("--fix", action="store_true", help="write (default is report only)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.path).expanduser()

    try:
        values = _parse_set(args.set)
        for tier, value in values.items():
            validate(tier, value)
    except ValueRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if values and not args.fix:
        print("--set given without --fix; nothing written. Re-run with --fix.",
              file=sys.stderr)
        return 1

    result = write(values, path) if (values and args.fix) else None

    st = status(path)
    if args.json:
        import json
        print(json.dumps({"status": st, "write": result}, indent=2))
        return 0

    if result:
        print(f"wrote {result['path']} (mode {result['mode']}) "
              f"tiers={','.join(result['tiers'])}")
        if result["added"]:
            print(f"  added   : {','.join(result['added'])}")
        if result["updated"]:
            print(f"  updated : {','.join(result['updated'])}")
    for line in render_status(st):
        print(line)
    if not st["wired"]:
        print("\nAdd this to your shell profile, then restart the session:")
        print(f"  {shell_line(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
