"""Unit tests for run comparison and report rendering."""

import pytest

from src.utils.eval_history import MetricSummary, RunSummary
from src.utils.report import (
    SCORE_NOISE_FLOOR,
    CaseOutcome,
    compare_runs,
    render_markdown,
)
from src.utils.usage import TokenUsage


def make_run(
    cases: dict[str, bool],
    metrics: dict[str, float] | None = None,
    app_name: str = "simple_agent",
) -> RunSummary:
    """Builds a RunSummary without touching disk."""
    return RunSummary(
        app_name=app_name,
        eval_set_id="golden_evalset",
        result_id="res-1",
        source_path="/tmp/res-1.json",
        cases_total=len(cases),
        cases_passed=sum(cases.values()),
        case_status=cases,
        metrics={
            name: MetricSummary(metric_name=name, mean_score=score, passed=1, total=1)
            for name, score in (metrics or {}).items()
        },
    )


def test_regression_is_detected():
    """A case that passed and now fails is the headline finding."""
    comparison = compare_runs(
        current=make_run({"TC001": True, "TC002": False}),
        previous=make_run({"TC001": True, "TC002": True}),
    )

    assert [d.eval_id for d in comparison.regressions] == ["TC002"]
    assert comparison.fixes == []


def test_fix_is_detected():
    """A case that failed and now passes is reported as fixed."""
    comparison = compare_runs(
        current=make_run({"TC001": True}),
        previous=make_run({"TC001": False}),
    )

    assert [d.eval_id for d in comparison.fixes] == ["TC001"]
    assert comparison.regressions == []


def test_new_case_is_not_a_regression():
    """Adding a failing test case must not read as a regression."""
    comparison = compare_runs(
        current=make_run({"TC001": True, "TC999": False}),
        previous=make_run({"TC001": True}),
    )

    outcomes = {d.eval_id: d.outcome for d in comparison.case_deltas}
    assert outcomes["TC999"] == CaseOutcome.NEW
    assert comparison.regressions == []


def test_removed_case_is_reported_not_dropped():
    """Deleting a case should be visible, not silently change the rate."""
    comparison = compare_runs(
        current=make_run({"TC001": True}),
        previous=make_run({"TC001": True, "TC002": True}),
    )

    outcomes = {d.eval_id: d.outcome for d in comparison.case_deltas}
    assert outcomes["TC002"] == CaseOutcome.REMOVED


def test_first_run_has_no_regressions():
    """With no baseline, every failure is a starting point, not a trend."""
    comparison = compare_runs(current=make_run({"TC001": False}))

    assert comparison.is_first_run
    assert comparison.regressions == []
    assert comparison.case_deltas[0].outcome == CaseOutcome.NEW


def test_metric_delta_is_computed():
    """Metric trends are the other half of 'performance over time'."""
    comparison = compare_runs(
        current=make_run({"TC001": True}, {"final_response_match_v2": 0.9}),
        previous=make_run({"TC001": True}, {"final_response_match_v2": 0.6}),
    )

    delta = comparison.metric_deltas[0]
    assert delta.delta == pytest.approx(0.3)
    assert delta.is_meaningful


def test_tiny_metric_move_is_treated_as_noise():
    """LLM judges jitter; a sub-threshold move is not a trend."""
    comparison = compare_runs(
        current=make_run({"TC001": True}, {"m": 0.9}),
        previous=make_run({"TC001": True}, {"m": 0.9 + SCORE_NOISE_FLOOR / 2}),
    )

    assert not comparison.metric_deltas[0].is_meaningful


def test_metric_present_in_only_one_run_has_no_delta():
    """Adding a metric must not render as an infinite improvement."""
    comparison = compare_runs(
        current=make_run({"TC001": True}, {"new_metric": 0.8}),
        previous=make_run({"TC001": True}, {}),
    )

    delta = comparison.metric_deltas[0]
    assert delta.delta is None
    assert not delta.is_meaningful


def test_report_leads_with_regressions():
    """Regressions appear before the per-app detail, since they need action."""
    comparison = compare_runs(
        current=make_run({"TC002": False}),
        previous=make_run({"TC002": True}),
        usage=TokenUsage(prompt=100, candidates=10, thoughts=40, calls=1),
        total_usd=0.0123,
    )

    markdown = render_markdown([comparison], generated_at="2026-10-01T00:00:00Z")

    assert markdown.index("## Regressions") < markdown.index("## simple_agent")
    assert "TC002" in markdown
    assert "$0.0123" in markdown


def test_clean_report_says_so_explicitly():
    """A report with nothing wrong must say 'None.', not show a blank table."""
    comparison = compare_runs(
        current=make_run({"TC001": True}), previous=make_run({"TC001": True})
    )

    markdown = render_markdown([comparison], generated_at="2026-10-01T00:00:00Z")

    assert "## Regressions\n\nNone." in markdown


def test_unpriced_run_renders_a_dash_not_zero():
    """A missing price must not be presented as a free run."""
    comparison = compare_runs(current=make_run({"TC001": True}), total_usd=None)

    markdown = render_markdown([comparison], generated_at="2026-10-01T00:00:00Z")

    assert "$0.0000" not in markdown


def test_multiple_apps_each_get_a_section():
    """Batch runs cover several agents and the report covers all of them."""
    comparisons = [
        compare_runs(current=make_run({"TC001": True}, app_name="simple_agent")),
        compare_runs(current=make_run({"TC001": False}, app_name="layout_aware_agent")),
    ]

    markdown = render_markdown(comparisons, generated_at="2026-10-01T00:00:00Z")

    assert "## simple_agent" in markdown
    assert "## layout_aware_agent" in markdown
