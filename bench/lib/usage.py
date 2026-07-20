"""Token + cost accounting for the 3-way comparison harness.

Modeled on patterns from the harness study (see bench/README.md):
- hermes-agent `agent/usage_pricing.py` — CanonicalUsage buckets + a CostResult
  carrying provenance (status: actual|estimated|unknown), and a per-MTok price
  table. The status/source seam is exactly the "char-estimate now, real-usage
  later" pluggability.
- oh-my-claudecode `src/hud/transcript.ts` / oh-my-opencode token shape — the
  Claude usage buckets {input, output, cache_creation, cache_read}.

Stdlib only. Money math uses Decimal; results expose rounded floats for JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

_MILLION = Decimal(1_000_000)
_CENTS = Decimal("0.000001")  # round cost to 6 decimal places (sub-cent)


@dataclass(frozen=True)
class CanonicalUsage:
    """Provider-neutral token buckets for one run (or aggregate)."""

    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0
    reasoning: int = 0  # informational; billed within output, NOT added again

    def __add__(self, other: "CanonicalUsage") -> "CanonicalUsage":
        return CanonicalUsage(
            input=self.input + other.input,
            output=self.output + other.output,
            cache_write=self.cache_write + other.cache_write,
            cache_read=self.cache_read + other.cache_read,
            reasoning=self.reasoning + other.reasoning,
        )

    def total(self) -> int:
        """Total tokens touched (all buckets), for a coarse size signal."""
        return self.input + self.output + self.cache_write + self.cache_read

    def as_dict(self) -> dict:
        return {
            "input": self.input,
            "output": self.output,
            "cache_write": self.cache_write,
            "cache_read": self.cache_read,
            "reasoning": self.reasoning,
            "total": self.total(),
        }

    @classmethod
    def from_claude_usage(cls, usage: dict) -> "CanonicalUsage":
        """Map a Claude session-JSONL `message.usage` block (real tokens)."""
        return cls(
            input=int(usage.get("input_tokens", 0) or 0),
            output=int(usage.get("output_tokens", 0) or 0),
            cache_write=int(usage.get("cache_creation_input_tokens", 0) or 0),
            cache_read=int(usage.get("cache_read_input_tokens", 0) or 0),
            reasoning=int(usage.get("reasoning_tokens", 0) or 0),
        )

    @classmethod
    def from_chars(cls, prompt_chars: int, response_chars: int, divisor: int = 4) -> "CanonicalUsage":
        """Estimate tokens from character counts (chars/divisor heuristic).

        The P4 transcript hook records prompt_chars/response_chars per agent
        turn; this is the estimate path used when real session usage is absent.
        """
        d = divisor if divisor > 0 else 4
        return cls(
            input=(int(prompt_chars) + d - 1) // d,
            output=(int(response_chars) + d - 1) // d,
        )


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens, per bucket."""

    input: Decimal
    output: Decimal
    cache_write: Decimal
    cache_read: Decimal


# Snapshot of Anthropic list prices ($/MTok). VERIFY against current pricing —
# override with `bench/prices.json` (same shape) when they change. cache_write
# = 5m ephemeral write tier; cache_read = read tier.
DEFAULT_PRICES: dict[str, ModelPrice] = {
    "claude-opus-4-7": ModelPrice(Decimal("15"), Decimal("75"), Decimal("18.75"), Decimal("1.50")),
    "claude-opus-4-8": ModelPrice(Decimal("15"), Decimal("75"), Decimal("18.75"), Decimal("1.50")),
    "claude-sonnet-4-6": ModelPrice(Decimal("3"), Decimal("15"), Decimal("3.75"), Decimal("0.30")),
    "claude-haiku-4-5": ModelPrice(Decimal("1"), Decimal("5"), Decimal("1.25"), Decimal("0.10")),
}


def load_prices(path: str | Path | None) -> dict[str, ModelPrice]:
    """Load a price-table override JSON ({model: {input,output,cache_write,cache_read}})
    merged over DEFAULT_PRICES. Returns DEFAULT_PRICES when path is falsy."""
    prices = dict(DEFAULT_PRICES)
    if not path:
        return prices
    raw = json.loads(Path(path).read_text())
    for model, p in raw.items():
        if model.startswith("_") or not isinstance(p, dict):
            continue  # skip comments / metadata keys
        prices[model] = ModelPrice(
            input=Decimal(str(p["input"])),
            output=Decimal(str(p["output"])),
            cache_write=Decimal(str(p.get("cache_write", 0))),
            cache_read=Decimal(str(p.get("cache_read", 0))),
        )
    return prices


@dataclass(frozen=True)
class CostResult:
    """Cost with provenance. `status` distinguishes a measured cost (real
    session tokens) from an estimate (char-derived) so the report can flag it."""

    amount_usd: float
    status: str  # "actual" | "estimated" | "unknown"
    source: str  # e.g. "session_jsonl", "char_estimate"
    model: str

    def as_dict(self) -> dict:
        return {
            "amount_usd": self.amount_usd,
            "status": self.status,
            "source": self.source,
            "model": self.model,
        }


def estimate_cost(
    usage: CanonicalUsage,
    model: str,
    source: str,
    prices: dict[str, ModelPrice] | None = None,
) -> CostResult:
    """Compute USD cost for `usage` at `model`'s rates.

    status: "actual" when the usage came from real session tokens
    (source startswith "session"), "estimated" for char-derived usage, and
    "unknown" (amount 0) when the model has no price entry.
    """
    table = prices if prices is not None else DEFAULT_PRICES
    price = table.get(model)
    if price is None:
        return CostResult(amount_usd=0.0, status="unknown", source=source, model=model)

    amount = (
        Decimal(usage.input) * price.input
        + Decimal(usage.output) * price.output
        + Decimal(usage.cache_write) * price.cache_write
        + Decimal(usage.cache_read) * price.cache_read
    ) / _MILLION
    amount = amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
    status = "actual" if source.startswith("session") else "estimated"
    return CostResult(amount_usd=float(amount), status=status, source=source, model=model)
