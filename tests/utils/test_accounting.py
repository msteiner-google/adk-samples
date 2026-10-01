"""Unit tests for the token accounting plugin."""

import json
import pathlib
from dataclasses import dataclass, field

import pytest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from src.utils.accounting import TokenAccountantPlugin


@dataclass
class FakeSession:
    """Stands in for ADK's Session, which carries the App name."""

    app_name: str = "simple_agent"


@dataclass
class FakeContext:
    """Stands in for ADK's CallbackContext; the plugin reads three fields."""

    invocation_id: str = "inv-1"
    agent_name: str = "simple_bank_agent"
    session: FakeSession | None = field(default_factory=FakeSession)


def make_response(
    *,
    prompt: int = 0,
    cached: int = 0,
    candidates: int = 0,
    thoughts: int = 0,
    model: str | None = "gemini-2.5-flash",
    partial: bool = False,
    with_usage: bool = True,
) -> LlmResponse:
    """Builds an LlmResponse carrying the given usage metadata."""
    usage = (
        types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt,
            cached_content_token_count=cached,
            candidates_token_count=candidates,
            thoughts_token_count=thoughts,
            total_token_count=prompt + candidates + thoughts,
        )
        if with_usage
        else None
    )
    return LlmResponse(usage_metadata=usage, model_version=model, partial=partial)


@pytest.fixture
def plugin(tmp_path: pathlib.Path) -> TokenAccountantPlugin:
    """A plugin writing to a temp file, with automatic flushing disabled."""
    return TokenAccountantPlugin(
        output_path=tmp_path / "usage.jsonl", write_on_run_end=False
    )


async def test_usage_accumulates_across_calls(plugin: TokenAccountantPlugin):
    """Repeated calls by one agent on one model collapse into one record."""
    ctx = FakeContext()
    for _ in range(3):
        await plugin.after_model_callback(
            callback_context=ctx,
            llm_response=make_response(prompt=100, candidates=10, thoughts=40),
        )

    records = plugin.snapshot()
    assert len(records) == 1
    assert records[0].usage.calls == 3
    assert records[0].usage.prompt == 300
    assert records[0].usage.thoughts == 120


async def test_each_sub_agent_is_accounted_separately(plugin: TokenAccountantPlugin):
    """Attribution per agent is what makes a multi-agent run legible."""
    await plugin.after_model_callback(
        callback_context=FakeContext(agent_name="layout_analyst"),
        llm_response=make_response(prompt=100),
    )
    await plugin.after_model_callback(
        callback_context=FakeContext(agent_name="complex_extractor"),
        llm_response=make_response(prompt=200),
    )

    by_agent = {r.agent_name: r.usage.prompt for r in plugin.snapshot()}
    assert by_agent == {"layout_analyst": 100, "complex_extractor": 200}


async def test_partial_responses_are_ignored(plugin: TokenAccountantPlugin):
    """Streaming chunks repeat cumulative counts and would double-count."""
    await plugin.after_model_callback(
        callback_context=FakeContext(),
        llm_response=make_response(prompt=100, partial=True),
    )
    assert plugin.snapshot() == []


async def test_responses_without_usage_metadata_are_ignored(
    plugin: TokenAccountantPlugin,
):
    """A response carrying no usage block must not register as a call."""
    await plugin.after_model_callback(
        callback_context=FakeContext(), llm_response=make_response(with_usage=False)
    )
    assert plugin.snapshot() == []


async def test_known_model_gets_costed(plugin: TokenAccountantPlugin):
    """A model in the shipped pricing table produces dollar figures."""
    await plugin.after_model_callback(
        callback_context=FakeContext(),
        llm_response=make_response(prompt=1_000_000, candidates=1000, thoughts=9000),
    )

    record = plugin.snapshot()[0]
    assert record.total_usd is not None
    assert record.thinking_usd is not None
    assert record.thinking_usd > 0


async def test_unpriced_model_keeps_its_tokens(plugin: TokenAccountantPlugin):
    """Tokens are the measurement; a stale rate table must not discard them."""
    await plugin.after_model_callback(
        callback_context=FakeContext(),
        llm_response=make_response(prompt=500, model="some-unreleased-model"),
    )

    record = plugin.snapshot()[0]
    assert record.usage.prompt == 500
    assert record.total_usd is None


async def test_flush_writes_jsonl_and_clears(plugin: TokenAccountantPlugin):
    """Flushing appends one JSON object per record, then resets."""
    await plugin.after_model_callback(
        callback_context=FakeContext(), llm_response=make_response(prompt=100)
    )

    path = plugin.flush()

    assert path is not None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["agent_name"] == "simple_bank_agent"
    assert payload["usage"]["prompt"] == 100
    assert "timestamp" in payload
    assert plugin.snapshot() == []


def test_flushing_nothing_writes_no_file(plugin: TokenAccountantPlugin):
    """An empty run must not leave a stray empty log behind."""
    assert plugin.flush() is None


async def test_totals_sum_every_agent(plugin: TokenAccountantPlugin):
    """totals() is the run-level figure a report headline needs."""
    await plugin.after_model_callback(
        callback_context=FakeContext(agent_name="a"),
        llm_response=make_response(prompt=100, thoughts=10),
    )
    await plugin.after_model_callback(
        callback_context=FakeContext(agent_name="b"),
        llm_response=make_response(prompt=50, thoughts=5),
    )

    totals = plugin.totals()
    assert totals.prompt == 150
    assert totals.thoughts == 15
    assert totals.calls == 2


async def test_app_name_comes_from_the_session(plugin: TokenAccountantPlugin):
    """Reports total cost per app, so each record must name its app."""
    await plugin.after_model_callback(
        callback_context=FakeContext(
            session=FakeSession(app_name="layout_aware_agent")
        ),
        llm_response=make_response(prompt=100),
    )
    assert plugin.snapshot()[0].app_name == "layout_aware_agent"


async def test_app_name_falls_back_to_the_constructor(tmp_path: pathlib.Path):
    """A context without a session still produces an attributable record."""
    plugin = TokenAccountantPlugin(
        output_path=tmp_path / "usage.jsonl",
        app_name="fallback_app",
        write_on_run_end=False,
    )
    await plugin.after_model_callback(
        callback_context=FakeContext(session=None),
        llm_response=make_response(prompt=100),
    )
    assert plugin.snapshot()[0].app_name == "fallback_app"


async def test_two_apps_are_not_merged(plugin: TokenAccountantPlugin):
    """Same agent name under two apps must stay two records."""
    for app in ("simple_agent", "layout_aware_agent"):
        await plugin.after_model_callback(
            callback_context=FakeContext(session=FakeSession(app_name=app)),
            llm_response=make_response(prompt=100),
        )
    assert {r.app_name for r in plugin.snapshot()} == {
        "simple_agent",
        "layout_aware_agent",
    }
