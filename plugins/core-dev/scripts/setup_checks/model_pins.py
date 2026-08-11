"""Will this session's sub-agent model pins actually take effect?

Sub-agent `model:` frontmatter is a request, not a guarantee. Claude Code resolves it
against the provider's available-model list and, when it does not resolve, **silently
falls back** — to the newest model in the same family, or failing that to the parent
model — logging at `warn`. Nothing surfaces in the UI. So a pipeline whose tiers have
collapsed looks exactly like one whose tiers held.

That is harmless on the first-party API, where the tier aliases always resolve. It is
not harmless on Bedrock or Vertex, where the available set is whatever the account has
enabled in the configured region, and where the alias resolves through the deployment's
own `ANTHROPIC_DEFAULT_<TIER>_MODEL`. Unset, the alias falls back to a built-in id
carrying the main model's region prefix, which an account may simply not have.

This module reports whether the wiring is in place *before* a run, so the failure mode
is a line of output rather than a pipeline that quietly ran every stage on one model.

**It never reads a model id.** On Bedrock a model name is a region-prefixed inference
profile or an ARN, which is an internal cloud resource identifier under the group
security policy. Every check here is `is this variable set`, never `what is it set to`,
so no value can reach a transcript through this path. Do not "improve" it by printing
the resolved id.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Aliases Claude Code resolves per provider. A frontmatter value outside this set is a
# concrete model id, which is exactly what does not travel between providers.
TIER_ALIASES = ("opus", "sonnet", "haiku", "fable")
INHERIT = "inherit"

_MODEL_LINE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)


def detect_provider(env: dict | None = None) -> str:
    """`bedrock` | `vertex` | `first_party`, read as the operator meant it.

    A provider variable counts as on only when its value says on -- `1`, `true`, `yes`,
    `on`. `CLAUDE_CODE_USE_BEDROCK=0` reads as off here, because that is what someone
    setting `0` means by it, and `0` is how people switch a flag off temporarily.

    **This deliberately does not match Claude Code's own rule, and the difference is
    load-bearing.** The CLI selects the provider with a bare JavaScript truthiness test:

        re.CLAUDE_CODE_USE_BEDROCK ? "bedrock" : ...        # CLI 2.1.228, verbatim

    There is no comparison in front of `?`, so *any* non-empty string is true and the
    CLI reads `0` and `false` as **Bedrock**. Only unset or empty turns it off there.

    So on a machine with `CLAUDE_CODE_USE_BEDROCK=0` this function answers
    `first_party` while the CLI still routes requests to Bedrock, and the Bedrock checks
    that follow are skipped. `provider_flag_disagrees()` exists to surface exactly that
    window; `doctor` reports it so the gap is visible rather than silent.

    To actually reach the first-party API, unset the variable or set it empty.
    """
    e = os.environ if env is None else env
    if _truthy(e.get("CLAUDE_CODE_USE_BEDROCK")):
        return "bedrock"
    if _truthy(e.get("CLAUDE_CODE_USE_VERTEX")):
        return "vertex"
    return "first_party"


# What an operator writes to mean "on". Anything else -- including `0` and `false` --
# is off, per ADR-0022.
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

# The CLI's rule, kept separately so the two can be compared rather than confused.
_PROVIDER_VARS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")


def _truthy(v) -> bool:
    """Is this env value an affirmative? `0`/`false`/`off` are not."""
    return v is not None and str(v).strip().lower() in _TRUE_VALUES


def _cli_truthy(v) -> bool:
    """The CLI's own test: any non-empty string is true. Used only to detect a mismatch."""
    return bool(v is not None and str(v) != "")


def provider_flag_disagrees(env: dict | None = None) -> list[str]:
    """Provider vars this module reads as off but the CLI still reads as on.

    Non-empty and not affirmative -- `0`, `false`, `off`, `no` -- is the whole set. It
    is worth naming because it is invisible: the CLI routes to the provider anyway, and
    every check keyed on `detect_provider()` has already been skipped.
    """
    e = os.environ if env is None else env
    return [k for k in _PROVIDER_VARS
            if _cli_truthy(e.get(k)) and not _truthy(e.get(k))]


def alias_env_var(alias: str) -> str:
    """The per-tier override a non-first-party deployment sets to name its own model."""
    return f"ANTHROPIC_DEFAULT_{alias.upper()}_MODEL"


def read_pins(agents_dir: Path) -> dict[str, str]:
    """{agent: frontmatter model value} for every agent that pins one."""
    pins: dict[str, str] = {}
    for md in sorted(agents_dir.glob("*.md")):
        m = _MODEL_LINE.search(md.read_text(encoding="utf-8", errors="replace"))
        if m:
            pins[md.stem] = m.group(1)
    return pins


def check(agents_dir: Path, env: dict | None = None) -> dict:
    """Report whether each pinned tier can resolve. Values are never included."""
    e = dict(os.environ if env is None else env)
    provider = detect_provider(e)
    pins = read_pins(agents_dir)

    aliases = sorted({v for v in pins.values() if v in TIER_ALIASES})
    literals = sorted({v for v in pins.values()
                       if v not in TIER_ALIASES and v != INHERIT})

    issues: list[dict] = []

    # Read as off here, still on in the CLI. Everything below keys on `provider`, so
    # without this line the whole Bedrock section would just quietly not appear.
    for var in provider_flag_disagrees(e):
        issues.append({
            "kind": "provider_flag_disagrees",
            "detail": f"{var} is set to a value that is neither empty nor affirmative, "
                      f"so this check reads it as off — but Claude Code tests it with "
                      f"bare truthiness and still routes to that provider. The tier "
                      f"checks below were skipped while the CLI is not on the "
                      f"first-party API. Unset it (or set it empty) to actually switch "
                      f"off, or set it to 1 to keep using it",
        })

    # A global override outranks every frontmatter pin, so both tiers become one model.
    if e.get("CLAUDE_CODE_SUBAGENT_MODEL", "").strip() not in ("", INHERIT):
        issues.append({
            "kind": "subagent_model_override",
            "detail": "CLAUDE_CODE_SUBAGENT_MODEL is set, which outranks every agent's "
                      "model: frontmatter — deep and exec tiers collapse to one model",
        })

    # A concrete id is provider-specific. Off first-party it usually does not resolve,
    # and not resolving is silent.
    if literals:
        issues.append({
            "kind": "pin_is_concrete_id",
            "detail": f"{len(literals)} agent pin(s) name a concrete model id rather than a "
                      f"tier alias {TIER_ALIASES[:2]}; on Bedrock/Vertex these resolve "
                      f"through a region-prefixed profile that the account may not have, "
                      f"and the fallback is silent",
        })

    # The deployment's own alias mapping. Presence only.
    unmapped = [a for a in aliases if not e.get(alias_env_var(a))]
    if provider != "first_party" and unmapped:
        issues.append({
            "kind": "tier_alias_unmapped",
            "detail": f"provider={provider} but "
                      f"{', '.join(alias_env_var(a) for a in unmapped)} "
                      f"{'is' if len(unmapped) == 1 else 'are'} unset, so the "
                      f"{', '.join(unmapped)} tier(s) fall back to a built-in id carrying "
                      f"the main model's region prefix — if that profile is not enabled in "
                      f"this account the sub-agent silently runs on the parent model",
        })

    return {
        "provider": provider,
        "pins": pins,
        "aliases": aliases,
        "concrete_ids": len(literals),
        # Presence only — deliberately not the values (see module docstring).
        "alias_env_set": {a: bool(e.get(alias_env_var(a))) for a in aliases},
        "subagent_model_override": bool(
            e.get("CLAUDE_CODE_SUBAGENT_MODEL", "").strip() not in ("", INHERIT)),
        "issues": issues,
        "ok": not issues,
    }


def render(result: dict) -> list[str]:
    """Lines for doctor's text output. Carries no model id."""
    lines = [f"  model pins : provider={result['provider']} "
             f"tiers={','.join(result['aliases']) or '-'} "
             f"agents={len(result['pins'])}"]
    if result["provider"] != "first_party":
        state = ", ".join(f"{alias_env_var(a)}={'set' if ok else 'UNSET'}"
                          for a, ok in result["alias_env_set"].items())
        if state:
            lines.append(f"               {state}")
    for i in result["issues"]:
        lines.append(f"    ⚠ [{i['kind']}] {i['detail']}")
    return lines
