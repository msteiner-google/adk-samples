"""Regression tests against invocations captured from a real `adk eval` run.

Why this file exists: the first live run scored both custom SQL metrics as
null on all ten cases, while every unit test passed. `Invocation.
intermediate_data` is a union. A golden case loaded from a file carries
`IntermediateData`, which has `.tool_uses` and `.tool_responses`. A live run
carries `InvocationEvents`, where the calls and responses are buried inside
event content parts. Reading the attribute directly worked against the shape
the unit tests built by hand and raised AttributeError against the real one,
which ADK swallowed into a null score.

Hand-built fixtures could not catch that, so the fixture here is real: three
invocations lifted verbatim from an eval run, covering a clean pass, a case
that healed, and a case the agent got wrong.

Keep using `get_all_tool_calls` and `get_all_tool_responses`. They are ADK's
own accessors and handle both shapes.
"""

import json
import pathlib

import pytest
from google.adk.evaluation.eval_case import (
    Invocation,
    InvocationEvents,
    get_all_tool_calls,
)
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.evaluator import EvalStatus

from src.evaluation.sql_metrics import (
    _expected_rows,
    _sql_queries,
    sql_result_match,
    sql_self_heal_recovery,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "live_nl2sql_invocations.json"


def load_cases() -> list[dict]:
    """Returns the captured invocations."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def invocations(eval_id: str) -> tuple[Invocation, Invocation]:
    """Returns the (actual, expected) pair for one captured case."""
    for case in load_cases():
        if case["eval_id"] == eval_id:
            return (
                Invocation.model_validate(case["actual_invocation"]),
                Invocation.model_validate(case["expected_invocation"]),
            )
    msg = f"No fixture case {eval_id}"
    raise AssertionError(msg)


def test_fixture_really_is_the_live_shape():
    """Guards the guard.

    If this fixture ever got regenerated as IntermediateData, the rest of
    this file would pass while testing nothing.
    """
    for case in load_cases():
        actual = Invocation.model_validate(case["actual_invocation"])
        assert isinstance(actual.intermediate_data, InvocationEvents), case["eval_id"]


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["eval_id"])
def test_tool_calls_are_recoverable_from_live_invocations(case: dict):
    """The exact read that silently returned nothing before."""
    actual = Invocation.model_validate(case["actual_invocation"])
    assert get_all_tool_calls(actual.intermediate_data)
    assert _sql_queries(actual), "no SQL recovered from a run that ran SQL"


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["eval_id"])
def test_expected_rows_are_recoverable_from_golden_invocations(case: dict):
    """The golden side is the other shape, and must still work."""
    expected = Invocation.model_validate(case["expected_invocation"])
    assert _expected_rows(expected) is not None


def test_metric_scores_a_live_run_instead_of_returning_none():
    """The actual regression: a real run must produce a number."""
    actual, expected = invocations("SQL001_count_customers")

    result = sql_result_match(
        EvalMetric(metric_name="sql_result_match", threshold=1.0), [actual], [expected]
    )

    assert result.overall_score is not None
    assert result.overall_eval_status != EvalStatus.NOT_EVALUATED


def test_correct_live_answer_scores_one():
    """A case the agent got right scores 1.0 end to end."""
    actual, expected = invocations("SQL001_count_customers")

    result = sql_result_match(
        EvalMetric(metric_name="sql_result_match", threshold=1.0), [actual], [expected]
    )

    assert result.overall_score == 1.0


def test_wrong_live_answer_scores_zero():
    """SQL007: the agent filtered on 'Savings' where the data has 'savings',
    so the query ran and returned no rows. The metric must catch it."""
    actual, expected = invocations("SQL007_cte_required")

    result = sql_result_match(
        EvalMetric(metric_name="sql_result_match", threshold=1.0), [actual], [expected]
    )

    assert result.overall_score == 0.0


def test_recovery_metric_runs_against_live_invocations():
    """Must return a result object rather than raising on the live shape.

    The score itself is not asserted: in this captured run no first attempt
    raised, so NOT_EVALUATED is the correct answer, and pinning a number
    here would encode that run's luck.
    """
    actual, expected = invocations("SQL008_heal_wrong_column_name")

    result = sql_self_heal_recovery(
        EvalMetric(metric_name="sql_self_heal_recovery", threshold=1.0),
        [actual],
        [expected],
    )

    assert result is not None
