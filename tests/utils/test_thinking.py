"""Unit tests for thinking-budget configuration."""

import pytest

from src.utils.thinking import (
    BUDGET_DISABLED,
    BUDGET_DYNAMIC,
    THINKING_BUDGET_ENV,
    budget_label,
    parse_budget,
    planner_from_env,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0", 0), ("2048", 2048), ("-1", -1), (" 512 ", 512)],
)
def test_valid_budgets_parse(raw: str, expected: int):
    """Plain counts, the disable value and the dynamic value all parse."""
    assert parse_budget(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unset_budget_is_none(raw: str | None):
    """An absent or blank value means 'leave the model default alone'."""
    assert parse_budget(raw) is None


def test_malformed_budget_falls_back_instead_of_raising(
    caplog: pytest.LogCaptureFixture,
):
    """A typo in an env var must not abort an otherwise valid eval run."""
    assert parse_budget("lots") is None
    assert THINKING_BUDGET_ENV in caplog.text


@pytest.mark.parametrize(
    ("budget", "label"),
    [(None, "default"), (0, "off"), (-1, "dynamic"), (2048, "2048")],
)
def test_budget_labels_are_readable(budget: int | None, label: str):
    """Report columns need names, not magic numbers."""
    assert budget_label(budget) == label


def test_no_planner_when_env_is_unset(monkeypatch: pytest.MonkeyPatch):
    """Normal runs must behave exactly as they did before this module."""
    monkeypatch.delenv(THINKING_BUDGET_ENV, raising=False)
    assert planner_from_env() is None


def test_planner_carries_the_requested_budget(monkeypatch: pytest.MonkeyPatch):
    """The budget reaches the ThinkingConfig the model actually receives."""
    monkeypatch.setenv(THINKING_BUDGET_ENV, "4096")

    planner = planner_from_env()

    assert planner is not None
    assert planner.thinking_config.thinking_budget == 4096
    assert planner.thinking_config.include_thoughts is True


def test_disabling_thinking_also_stops_requesting_thoughts(
    monkeypatch: pytest.MonkeyPatch,
):
    """Asking for thought summaries with a zero budget is contradictory."""
    monkeypatch.setenv(THINKING_BUDGET_ENV, str(BUDGET_DISABLED))

    planner = planner_from_env()

    assert planner is not None
    assert planner.thinking_config.thinking_budget == BUDGET_DISABLED
    assert planner.thinking_config.include_thoughts is False


def test_dynamic_budget_still_requests_thoughts(monkeypatch: pytest.MonkeyPatch):
    """Dynamic thinking must stay measurable, so thoughts stay included."""
    monkeypatch.setenv(THINKING_BUDGET_ENV, str(BUDGET_DYNAMIC))

    planner = planner_from_env()

    assert planner is not None
    assert planner.thinking_config.include_thoughts is True
