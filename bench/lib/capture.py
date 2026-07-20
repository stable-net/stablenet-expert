"""Usage capture: two sources feeding the token/cost accounting.

1. session JSONL (real tokens) — Claude Code writes per-session token usage to
   ~/.claude/projects/<cwd-slug>/<uuid>.jsonl; each assistant message carries
   `message.usage` {input_tokens, output_tokens, cache_creation_input_tokens,
   cache_read_input_tokens} and `message.model`. (Pattern from
   oh-my-claudecode src/hud/transcript.ts.) No cost field exists there — cost is
   computed from a price table (usage.py).
2. transcript chars (estimate) — the P4 hook records {subagent_type,
   prompt_chars, response_chars} per agent turn into a cell's
   logs/agent-transcript.jsonl; tokens are estimated chars/4. Used when real
   session usage is not available for a cell.

Both return a per-MODEL breakdown so cost can be computed at each model's rates
then summed. Stdlib only.
"""

from __future__ import annotations

import json
from pathlib import Path

from .usage import CanonicalUsage

# Estimate path lacks a model field, so map the dispatched sub-agent to its model.
# SINGLE SOURCE: bench/model-pins/models.json (tier -> model id, agent -> tier).
# Read it at runtime so this is not a second copy that can drift from frontmatter
# (check.py enforces frontmatter == models.json). Fall back to a literal map only
# if the file is missing/unparseable, so the bench still runs.
_MODELS_JSON = Path(__file__).resolve().parents[1] / "model-pins" / "models.json"
_FALLBACK_AGENT_MODEL: dict[str, str] = {
    "orchestrator": "claude-opus-4-8", "planner": "claude-opus-4-8",
    "analyzer": "claude-opus-4-8", "bench-analyzer-codeonly": "claude-opus-4-8",
    "bench-analyzer-skills": "claude-opus-4-8", "bench-solver-codeonly": "claude-opus-4-8",
    "bench-solver-project-skills": "claude-opus-4-8",
    "implementer": "claude-sonnet-4-6", "evaluator": "claude-sonnet-4-6",
}
_FALLBACK_MODEL = "claude-sonnet-4-6"


def _load_agent_model() -> dict[str, str]:
    """Resolve {agent: model_id} from models.json; fall back to the literal map."""
    try:
        doc = json.loads(_MODELS_JSON.read_text())
        tiers = doc["tiers"]
        return {agent: tiers[tier] for agent, tier in doc["agents"].items()}
    except (OSError, json.JSONDecodeError, KeyError):
        return dict(_FALLBACK_AGENT_MODEL)


DEFAULT_AGENT_MODEL: dict[str, str] = _load_agent_model()


def _iter_jsonl(path: Path):
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a partial trailing write


def usage_by_model_from_transcript(
    path: str | Path,
    agent_model: dict[str, str] | None = None,
    divisor: int = 4,
) -> dict[str, CanonicalUsage]:
    """Estimate per-model usage from a cell's agent-transcript.jsonl (chars/4)."""
    p = Path(path)
    out: dict[str, CanonicalUsage] = {}
    if not p.is_file():
        return out
    amap = agent_model or DEFAULT_AGENT_MODEL
    for rec in _iter_jsonl(p):
        subagent = rec.get("subagent_type") or "unknown"
        model = amap.get(subagent, _FALLBACK_MODEL)
        u = CanonicalUsage.from_chars(
            rec.get("prompt_chars", 0) or 0,
            rec.get("response_chars", 0) or 0,
            divisor=divisor,
        )
        out[model] = out.get(model, CanonicalUsage()) + u
    return out


def usage_by_model_from_session(path: str | Path) -> dict[str, CanonicalUsage]:
    """Real per-model usage from a Claude session JSONL (message.usage)."""
    p = Path(path)
    out: dict[str, CanonicalUsage] = {}
    if not p.is_file():
        return out
    for rec in _iter_jsonl(p):
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        model = msg.get("model") or _FALLBACK_MODEL
        out[model] = out.get(model, CanonicalUsage()) + CanonicalUsage.from_claude_usage(usage)
    return out


def collect_cell_usage(
    cell_dir: str | Path,
    session_path: str | Path | None = None,
    agent_model: dict[str, str] | None = None,
) -> tuple[dict[str, CanonicalUsage], str]:
    """Per-model usage for one cell, preferring real session tokens.

    Returns (usage_by_model, source). `source` is "session_jsonl" when a session
    path is given and yields data, else "char_estimate" from the cell transcript.
    """
    if session_path:
        by_model = usage_by_model_from_session(session_path)
        if by_model:
            return by_model, "session_jsonl"
    transcript = Path(cell_dir) / "logs" / "agent-transcript.jsonl"
    return usage_by_model_from_transcript(transcript, agent_model=agent_model), "char_estimate"
