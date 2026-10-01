"""Unit tests for token usage accounting."""

from google.genai import types

from src.utils.usage import TokenUsage


def test_cached_tokens_are_subtracted_from_billable_input():
    """Cached tokens are a subset of prompt tokens, not an addition to them."""
    usage = TokenUsage(prompt=1000, cached=400)
    assert usage.billable_input == 600


def test_billable_input_never_goes_negative():
    """A cached count larger than the prompt count must not produce a credit."""
    usage = TokenUsage(prompt=100, cached=250)
    assert usage.billable_input == 0


def test_thoughts_are_added_to_billable_output():
    """Thinking tokens are billed on top of visible output, not inside it."""
    usage = TokenUsage(candidates=300, thoughts=700)
    assert usage.billable_output == 1000
    assert usage.thinking_ratio == 0.7


def test_thinking_ratio_of_a_silent_turn_is_zero():
    """A turn that generated nothing must not divide by zero."""
    assert TokenUsage(prompt=50).thinking_ratio == 0.0


def test_usage_records_add_field_by_field():
    """Aggregating two model calls sums every counter, call count included."""
    total = TokenUsage(prompt=10, candidates=5, thoughts=2, total=17, calls=1) + (
        TokenUsage(prompt=20, candidates=1, thoughts=3, total=24, calls=1)
    )
    assert total.prompt == 30
    assert total.thoughts == 5
    assert total.total == 41
    assert total.calls == 2


def test_from_usage_metadata_reads_every_counter():
    """All five counters survive the trip from the genai metadata object."""
    usage = TokenUsage.from_usage_metadata(
        types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100,
            cached_content_token_count=20,
            candidates_token_count=30,
            thoughts_token_count=40,
            total_token_count=170,
        )
    )
    assert usage.prompt == 100
    assert usage.cached == 20
    assert usage.candidates == 30
    assert usage.thoughts == 40
    assert usage.calls == 1


def test_from_usage_metadata_treats_missing_counters_as_zero():
    """Non-thinking models omit thoughts_token_count entirely."""
    usage = TokenUsage.from_usage_metadata(
        types.GenerateContentResponseUsageMetadata(prompt_token_count=100)
    )
    assert usage.thoughts == 0
    assert usage.calls == 1


def test_from_usage_metadata_of_none_does_not_count_a_call():
    """Responses with no usage block must not inflate the call count."""
    usage = TokenUsage.from_usage_metadata(None)
    assert usage.calls == 0
    assert usage.total == 0
