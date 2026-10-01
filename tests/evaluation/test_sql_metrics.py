"""Unit tests for the NL2SQL custom metrics."""

import pytest
from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.evaluator import EvalStatus
from google.genai import types

from src.evaluation.sql_metrics import (
    SQL_TOOL,
    sql_result_match,
    sql_self_heal_recovery,
)

REFLECT = "reflect_and_retry"


def metric(name: str = "sql_result_match", threshold: float = 1.0) -> EvalMetric:
    """Builds the EvalMetric ADK would hand the function."""
    return EvalMetric(metric_name=name, threshold=threshold)


def actual(*calls: tuple[str, dict | None]) -> Invocation:
    """Builds an agent invocation from (sql, response) pairs.

    A None response means the call failed and the retry plugin intercepted
    it; anything else is used as the tool response verbatim.
    """
    return Invocation(
        invocation_id="inv-1",
        user_content=types.Content(parts=[types.Part(text="q")]),
        intermediate_data=IntermediateData(
            tool_uses=[
                types.FunctionCall(name=SQL_TOOL, args={"query": sql})
                for sql, _ in calls
            ],
            tool_responses=[
                types.FunctionResponse(
                    name=SQL_TOOL,
                    response=response
                    if response is not None
                    else {"response_type": REFLECT, "error_details": "boom"},
                )
                for _, response in calls
            ],
        ),
    )


def expected(rows: list) -> Invocation:
    """Builds a golden invocation carrying the expected result set."""
    return Invocation(
        invocation_id="inv-1",
        user_content=types.Content(parts=[types.Part(text="q")]),
        intermediate_data=IntermediateData(
            tool_uses=[],
            tool_responses=[
                types.FunctionResponse(
                    name=SQL_TOOL, response={"expected_rows": rows}
                )
            ],
        ),
    )


def test_correct_query_scores_one():
    """The baseline: right rows, full marks."""
    result = sql_result_match(
        metric(),
        [actual(("SELECT COUNT(*) FROM customers", {"rows": [[5]]}))],
        [expected([[5]])],
    )
    assert result.overall_score == 1.0
    assert result.overall_eval_status == EvalStatus.PASSED


def test_wrong_rows_score_zero():
    """A query that runs but answers the wrong question still fails."""
    result = sql_result_match(
        metric(),
        [actual(("SELECT COUNT(*) FROM accounts", {"rows": [[7]]}))],
        [expected([[5]])],
    )
    assert result.overall_score == 0.0


def test_different_sql_with_the_same_answer_passes():
    """The whole point of comparing rows: spelling must not matter."""
    result = sql_result_match(
        metric(),
        [actual(("SELECT COUNT(customer_id) FROM `proj.ds.customers`", None))],
        [expected([[5]])],
    )
    assert result.overall_score == 1.0


def test_row_order_is_ignored():
    """Without an ORDER BY the engine may return rows in any order."""
    result = sql_result_match(
        metric(),
        [actual(("SELECT full_name FROM customers WHERE city = 'Milan'", None))],
        [expected([["Katherine Johnson"], ["Grace Hopper"]])],
    )
    assert result.overall_score == 1.0


def test_float_noise_does_not_fail_a_correct_answer():
    """SUM/COUNT and AVG can differ in the last bits of the double."""
    result = sql_result_match(
        metric(),
        [actual(("SELECT SUM(balance)/COUNT(*) FROM accounts", None))],
        [expected([[10327.357142857143]])],
    )
    assert result.overall_score == 1.0


def test_genuinely_different_number_still_fails():
    """Float tolerance must not swallow a real difference."""
    result = sql_result_match(
        metric(),
        [actual(("SELECT AVG(balance) FROM accounts", None))],
        [expected([[10328.0]])],
    )
    assert result.overall_score == 0.0


def test_only_the_final_query_is_scored():
    """Earlier attempts are the failures the healing loop corrected."""
    result = sql_result_match(
        metric(),
        [
            actual(
                ("SELECT customer_nmae FROM customers", None),
                ("SELECT COUNT(*) FROM customers", {"rows": [[5]]}),
            )
        ],
        [expected([[5]])],
    )
    assert result.overall_score == 1.0


def test_unrunnable_final_query_scores_zero():
    """An agent that gave up with a broken query has not answered."""
    result = sql_result_match(
        metric(), [actual(("SELECT nope FROM customers", None))], [expected([[5]])]
    )
    assert result.overall_score == 0.0


def test_no_query_at_all_scores_zero():
    """Answering from memory without touching the database is not a pass."""
    invocation = Invocation(
        invocation_id="inv-1",
        user_content=types.Content(parts=[types.Part(text="q")]),
        intermediate_data=IntermediateData(tool_uses=[], tool_responses=[]),
    )
    result = sql_result_match(metric(), [invocation], [expected([[5]])])
    assert result.overall_score == 0.0


def test_recovery_counts_only_invocations_that_failed_first():
    """Easy cases must not inflate the recovery rate."""
    healed = actual(
        ("SELECT bad FROM customers", None),
        ("SELECT COUNT(*) FROM customers", {"rows": [[5]]}),
    )
    never_failed = actual(("SELECT COUNT(*) FROM customers", {"rows": [[5]]}))

    result = sql_self_heal_recovery(
        metric("sql_self_heal_recovery"), [healed, never_failed], None
    )

    assert len(result.per_invocation_results) == 1
    assert result.overall_score == 1.0


def test_failure_without_recovery_scores_zero():
    """Failing and then giving up is the case this metric exists to catch."""
    gave_up = actual(("SELECT bad FROM customers", None))

    result = sql_self_heal_recovery(metric("sql_self_heal_recovery"), [gave_up], None)

    assert result.overall_score == 0.0
    assert result.overall_eval_status == EvalStatus.FAILED


def test_recovery_is_not_evaluated_when_nothing_failed():
    """Reporting 0% recovery for a clean run would be a false alarm."""
    clean = actual(("SELECT COUNT(*) FROM customers", {"rows": [[5]]}))

    result = sql_self_heal_recovery(metric("sql_self_heal_recovery"), [clean], None)

    assert result.overall_eval_status == EvalStatus.NOT_EVALUATED
    assert result.overall_score is None


def test_partial_recovery_rate_is_averaged():
    """Two cases needing healing, one recovered: 50%."""
    healed = actual(
        ("SELECT bad FROM customers", None),
        ("SELECT COUNT(*) FROM customers", {"rows": [[5]]}),
    )
    gave_up = actual(("SELECT bad FROM customers", None))

    result = sql_self_heal_recovery(
        metric("sql_self_heal_recovery"), [healed, gave_up], None
    )

    assert result.overall_score == pytest.approx(0.5)
