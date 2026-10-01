"""Unit tests for the cost estimator and its rate table."""

import pytest

from src.utils.pricing import (
    TOKENS_PER_UNIT,
    ModelPricing,
    PricingTable,
    UnknownModelError,
    estimate_cost,
    load_pricing_table,
)
from src.utils.usage import TokenUsage


@pytest.fixture
def table() -> PricingTable:
    """A small table with a flat model and a long-context model."""
    return PricingTable(
        models={
            "flat-model": ModelPricing(input=1.0, cached_input=0.1, output=10.0),
            "tiered-model": ModelPricing(
                input=2.0,
                cached_input=0.2,
                output=20.0,
                long_context_threshold=100,
                long_context={"input": 4.0, "cached_input": 0.4, "output": 40.0},
            ),
        }
    )


def test_cost_splits_thinking_out_of_output(table: PricingTable):
    """Thinking is billed at the output rate but reported as its own line."""
    usage = TokenUsage(
        prompt=TOKENS_PER_UNIT,
        candidates=TOKENS_PER_UNIT // 2,
        thoughts=TOKENS_PER_UNIT // 2,
    )

    cost = estimate_cost(usage, "flat-model", table)

    assert cost.input_usd == pytest.approx(1.0)
    assert cost.output_usd == pytest.approx(5.0)
    assert cost.thinking_usd == pytest.approx(5.0)
    assert cost.total_usd == pytest.approx(11.0)
    assert cost.thinking_share == pytest.approx(5.0 / 11.0)


def test_cached_input_is_charged_at_the_cached_rate(table: PricingTable):
    """The cached share is discounted and the rest pays full price."""
    usage = TokenUsage(prompt=TOKENS_PER_UNIT, cached=TOKENS_PER_UNIT // 2)

    cost = estimate_cost(usage, "flat-model", table)

    assert cost.input_usd == pytest.approx(0.5)
    assert cost.cached_input_usd == pytest.approx(0.05)
    assert cost.total_usd == pytest.approx(0.55)


def test_long_context_tier_applies_above_the_threshold(table: PricingTable):
    """A prompt over the threshold is charged at the long-context rates."""
    small = estimate_cost(TokenUsage(prompt=100), "tiered-model", table)
    large = estimate_cost(TokenUsage(prompt=101), "tiered-model", table)

    assert small.input_usd == pytest.approx(100 * 2.0 / TOKENS_PER_UNIT)
    assert large.input_usd == pytest.approx(101 * 4.0 / TOKENS_PER_UNIT)


def test_flat_model_ignores_prompt_size(table: PricingTable):
    """A model with no long-context tier charges one rate at any size."""
    cost = estimate_cost(TokenUsage(prompt=10_000_000), "flat-model", table)
    assert cost.input_usd == pytest.approx(10.0)


def test_versioned_model_names_resolve(table: PricingTable):
    """Responses report decorated names like gemini-2.5-flash-001."""
    assert table.resolve("flat-model-001").input == 1.0
    assert table.resolve("publishers/google/models/flat-model").input == 1.0


def test_longest_matching_prefix_wins():
    """A -lite variant must not be priced with its parent's rate card."""
    table = PricingTable(
        models={
            "gemini-2.5-flash": ModelPricing(input=0.3, cached_input=0.03, output=2.5),
            "gemini-2.5-flash-lite": ModelPricing(
                input=0.1, cached_input=0.01, output=0.4
            ),
        }
    )
    assert table.resolve("gemini-2.5-flash-lite").output == 0.4


def test_unknown_model_names_the_alternatives(table: PricingTable):
    """The error has to be actionable: say what the table does know."""
    with pytest.raises(UnknownModelError, match="flat-model"):
        estimate_cost(TokenUsage(prompt=1), "claude-opus", table)


def test_shipped_table_prices_the_default_agent_model():
    """The checked-in table must cover the model the agents actually use."""
    pricing = load_pricing_table().resolve("gemini-2.5-flash")
    assert pricing.input > 0
    assert pricing.output > pricing.input
