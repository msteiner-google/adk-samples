"""Turns token counts into dollar estimates using a checked-in rate table.

The rates live in `data/model_pricing.json` rather than being fetched at
runtime: evaluation runs must stay reproducible and offline-friendly, and a
cost number that silently changes between two runs is worse than one that is
explicitly stale. See the `_meta` block in that file for provenance.
"""

from __future__ import annotations

import functools
import json
import pathlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.utils.usage import TokenUsage

TOKENS_PER_UNIT = 1_000_000

DEFAULT_PRICING_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "model_pricing.json"
)


class UnknownModelError(KeyError):
    """Raised when no rate card can be resolved for a model name."""


class RateCard(BaseModel):
    """Prices in USD per 1M tokens for a single billing tier."""

    input: float = Field(description="Uncached input tokens, USD per 1M")
    cached_input: float = Field(description="Cached input tokens, USD per 1M")
    output: float = Field(
        description="Output tokens, USD per 1M; covers reasoning tokens too"
    )


class ModelPricing(BaseModel):
    """Rate cards for one model, with an optional long-context tier."""

    input: float
    cached_input: float
    output: float
    long_context_threshold: int | None = None
    long_context: RateCard | None = None

    @property
    def base(self) -> RateCard:
        """The standard rate card."""
        return RateCard(
            input=self.input, cached_input=self.cached_input, output=self.output
        )

    def rate_for(self, prompt_tokens: int) -> RateCard:
        """Picks the rate card that applies to a prompt of this size."""
        if (
            self.long_context is not None
            and self.long_context_threshold is not None
            and prompt_tokens > self.long_context_threshold
        ):
            return self.long_context
        return self.base


class CostBreakdown(BaseModel):
    """A costed `TokenUsage`, in USD.

    `thinking_usd` is carved out of the output charge rather than added to it:
    `input_usd + cached_input_usd + output_usd + thinking_usd == total_usd`,
    where `output_usd` covers visible output only. That split is the whole
    point of the exercise, since it shows what reasoning actually costs.
    """

    model: str
    input_usd: float = 0.0
    cached_input_usd: float = 0.0
    output_usd: float = 0.0
    thinking_usd: float = 0.0
    total_usd: float = 0.0

    @property
    def thinking_share(self) -> float:
        """Fraction of the total spend attributable to reasoning tokens."""
        if self.total_usd == 0:
            return 0.0
        return self.thinking_usd / self.total_usd


class PricingTable(BaseModel):
    """A collection of model rate cards, resolvable by model name."""

    models: dict[str, ModelPricing]

    def resolve(self, model_name: str) -> ModelPricing:
        """Finds the rate card for a model name.

        Accepts the decorated names that actually show up in responses, such as
        `gemini-2.5-flash-001` or
        `publishers/google/models/gemini-2.5-flash`, by taking the longest
        table key contained in the name. Longest wins so that
        `gemini-2.5-flash-lite` is never served by the `gemini-2.5-flash` card.
        """
        bare = model_name.rsplit("/", 1)[-1]
        candidates = [key for key in self.models if bare.startswith(key)]
        if not candidates:
            msg = (
                f"No pricing entry for model {model_name!r}. "
                f"Known models: {sorted(self.models)}"
            )
            raise UnknownModelError(msg)
        return self.models[max(candidates, key=len)]


@functools.lru_cache(maxsize=4)
def load_pricing_table(path: pathlib.Path | None = None) -> PricingTable:
    """Loads and caches the rate table from disk."""
    pricing_path = path or DEFAULT_PRICING_PATH
    raw = json.loads(pricing_path.read_text(encoding="utf-8"))
    return PricingTable(models=raw["models"])


def estimate_cost(
    usage: TokenUsage, model: str, table: PricingTable | None = None
) -> CostBreakdown:
    """Estimates the USD cost of `usage` for `model`.

    Raises:
        UnknownModelError: if `model` has no entry in the pricing table.
    """
    pricing = (table or load_pricing_table()).resolve(model)
    rates = pricing.rate_for(usage.prompt)

    input_usd = usage.billable_input * rates.input / TOKENS_PER_UNIT
    cached_usd = usage.cached * rates.cached_input / TOKENS_PER_UNIT
    output_usd = usage.candidates * rates.output / TOKENS_PER_UNIT
    thinking_usd = usage.thoughts * rates.output / TOKENS_PER_UNIT

    return CostBreakdown(
        model=model,
        input_usd=input_usd,
        cached_input_usd=cached_usd,
        output_usd=output_usd,
        thinking_usd=thinking_usd,
        total_usd=input_usd + cached_usd + output_usd + thinking_usd,
    )
