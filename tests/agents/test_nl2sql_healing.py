"""Tests for the NL2SQL self-healing loop.

Exercises the real ADK plugin against the real database, with no model in
the loop: a model's willingness to act on feedback is not what is under
test here. What is under test is that the database's error actually reaches
the model as actionable guidance, and that the retry budget is enforced.
"""

from dataclasses import dataclass

import pytest
from google.adk.plugins.reflect_retry_tool_plugin import ReflectAndRetryToolPlugin

from src.agents.nl2sql_agent.agent import MAX_SQL_RETRIES
from src.agents.nl2sql_agent.tools import run_sql_query
from src.utils.sql_runtime import SqlExecutionError


@dataclass
class FakeTool:
    """Stands in for an ADK BaseTool; the plugin reads only the name."""

    name: str = "run_sql_query"


@dataclass
class FakeToolContext:
    """Stands in for ToolContext; failures are tracked per invocation."""

    invocation_id: str = "inv-1"


@pytest.fixture
def plugin() -> ReflectAndRetryToolPlugin:
    """The plugin configured exactly as the agent configures it."""
    return ReflectAndRetryToolPlugin(max_retries=MAX_SQL_RETRIES)


async def fail_once(
    plugin: ReflectAndRetryToolPlugin,
    query: str,
    context: FakeToolContext | None = None,
) -> dict:
    """Runs a bad query and pushes the resulting error through the plugin."""
    try:
        run_sql_query(query)
    except SqlExecutionError as exc:
        return await plugin.on_tool_error_callback(
            tool=FakeTool(),
            tool_args={"query": query},
            tool_context=context or FakeToolContext(),
            error=exc,
        )
    msg = f"Expected {query!r} to fail"
    raise AssertionError(msg)


async def test_database_error_reaches_the_model(plugin: ReflectAndRetryToolPlugin):
    """The exact sqlite wording is the signal the model corrects from."""
    guidance = await fail_once(plugin, "SELECT customer_nmae FROM customers")

    assert "no such column: customer_nmae" in guidance["error_details"]


async def test_guidance_carries_the_schema(plugin: ReflectAndRetryToolPlugin):
    """A model cannot correct to a column name it has not been shown."""
    guidance = await fail_once(plugin, "SELECT customer_nmae FROM customers")

    assert "full_name" in guidance["error_details"]


async def test_guidance_tells_the_model_not_to_repeat_itself(
    plugin: ReflectAndRetryToolPlugin,
):
    """Without this the cheapest next action is resending the same query."""
    guidance = await fail_once(plugin, "SELECT nope FROM customers")

    assert "Do not repeat the exact same call" in guidance["reflection_guidance"]


async def test_retry_count_climbs_within_one_invocation(
    plugin: ReflectAndRetryToolPlugin,
):
    """The budget is per invocation, so repeated failures must accumulate."""
    counts = [
        (await fail_once(plugin, f"SELECT bad_{i} FROM customers"))["retry_count"]
        for i in range(MAX_SQL_RETRIES)
    ]

    assert counts == list(range(1, MAX_SQL_RETRIES + 1))


async def test_exhausting_the_budget_raises(plugin: ReflectAndRetryToolPlugin):
    """A hopeless query must stop, not loop until the eval times out."""
    for i in range(MAX_SQL_RETRIES):
        await fail_once(plugin, f"SELECT bad_{i} FROM customers")

    with pytest.raises(SqlExecutionError):
        await fail_once(plugin, "SELECT still_bad FROM customers")


async def test_separate_invocations_get_separate_budgets(
    plugin: ReflectAndRetryToolPlugin,
):
    """One eval case failing must not consume the next case's retries."""
    for i in range(MAX_SQL_RETRIES):
        await fail_once(
            plugin, f"SELECT bad_{i} FROM customers", FakeToolContext("inv-1")
        )

    guidance = await fail_once(
        plugin, "SELECT bad FROM customers", FakeToolContext("inv-2")
    )
    assert guidance["retry_count"] == 1


async def test_a_success_resets_the_budget(plugin: ReflectAndRetryToolPlugin):
    """A working query means the agent recovered; the slate should clear."""
    await fail_once(plugin, "SELECT bad FROM customers")

    await plugin.after_tool_callback(
        tool=FakeTool(),
        tool_args={"query": "SELECT 1"},
        tool_context=FakeToolContext(),
        result=run_sql_query("SELECT 1"),
    )

    guidance = await fail_once(plugin, "SELECT bad_again FROM customers")
    assert guidance["retry_count"] == 1


async def test_dialect_slip_is_recoverable(plugin: ReflectAndRetryToolPlugin):
    """EXTRACT survives transpilation but SQLite rejects it.

    This is the dialect-mismatch case in the golden dataset: the guidance
    has to show a syntax error the model can act on, not a silent wrong
    answer.
    """
    guidance = await fail_once(
        plugin, "SELECT EXTRACT(YEAR FROM txn_date) FROM transactions"
    )

    assert "syntax error" in guidance["error_details"]


async def test_write_attempt_is_reported_as_a_rule_not_a_bug(
    plugin: ReflectAndRetryToolPlugin,
):
    """The agent should learn the constraint, not retry the same mutation."""
    guidance = await fail_once(plugin, "DELETE FROM customers")

    assert "Only SELECT and WITH queries are allowed" in guidance["error_details"]
