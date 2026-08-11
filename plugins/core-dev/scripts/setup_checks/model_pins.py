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
    """`bedrock` | `vertex` | `first_party`, by the same rule Claude Code uses.

    Claude Code selects the provider with a bare JavaScript truthiness test on the
    variable -- `CLAUDE_CODE_USE_BEDROCK ? "bedrock" : ...` -- so **any non-empty value
    means Bedrock, `"0"` and `"false"` included**. Only unsetting it (or setting it
    empty) goes back to the first-party API.

    That is a trap worth mirroring exactly rather than "fixing" here. A checker that
    read `=0` as first-party would report the wrong provider on the one machine the
    check exists for, and would hide the misconfiguration instead of reporting it.
    """
    e = os.environ if env is None else env
    if _truthy(e.get("CLAUDE_CODE_USE_BEDROCK")):
        return "bedrock"
    if _truthy(e.get("CLAUDE_CODE_USE_VERTEX")):
        return "vertex"
    return "first_party"


def _truthy(v) -> bool:
    """JavaScript truthiness for an env value: any non-empty string counts."""
    return bool(v is not None and str(v) != "")


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
