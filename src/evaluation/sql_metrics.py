"""Custom ADK metrics for the NL2SQL agent.

Two things need measuring that no built-in metric covers.

`sql_result_match` scores whether the agent got the right *answer*, by
re-running the SQL it chose and comparing the result set against the
expected one. String-comparing SQL would be the wrong test: there are many
correct spellings of the same query, and an LLM judge reading SQL grades
plausibility rather than correctness. Running it is cheap here, because the
database is a deterministic in-memory SQLite.

`sql_self_heal_recovery` scores the behaviour Topic 4 is actually about:
when the first query fails, does the agent recover? A case that never fails
is neutral, not a pass, so that padding the dataset with easy queries cannot
inflate the number.

Registered through `custom_metrics` in the eval config; ADK imports them by
the dotted path given in `code_config.name`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from google.adk.evaluation.eval_case import (
    get_all_tool_calls,
    get_all_tool_responses,
)
from google.adk.evaluation.evaluator import (
    EvalStatus,
    EvaluationResult,
    PerInvocationResult,
)

from src.utils.sql_runtime import SqlDatabase, SqlExecutionError

if TYPE_CHECKING:
    from google.adk.evaluation.eval_case import ConversationScenario, Invocation
    from google.adk.evaluation.eval_metrics import EvalMetric

#: Tool name the agent calls to run a query.
SQL_TOOL = "run_sql_query"

#: Marker ADK's retry plugin puts on a tool response it has intercepted.
_REFLECT_RESPONSE_TYPE = "reflect_and_retry"

#: Decimal places floats are rounded to before comparison. Currency answers
#: need two; the extra places absorb reassociation noise without masking a
#: genuinely different number.
FLOAT_PLACES = 6

_PASS = 1.0
_FAIL = 0.0


def _tool_uses(invocation: Invocation | None) -> list[Any]:
    """Returns the tool calls made during an invocation.

    Goes through ADK's accessor rather than reading `.tool_uses` directly.
    `intermediate_data` is a union: golden cases loaded from a file carry
    `IntermediateData`, but a live run carries `InvocationEvents`, where the
    calls are buried in event content parts. Reading the attribute directly
    works against the golden shape and raises AttributeError against the
    live one, which ADK swallows into a null score.
    """
    if invocation is None:
        return []
    return list(get_all_tool_calls(invocation.intermediate_data) or [])


def _tool_responses(invocation: Invocation | None) -> list[Any]:
    """Returns the tool responses received during an invocation."""
    if invocation is None:
        return []
    return list(get_all_tool_responses(invocation.intermediate_data) or [])


def _sql_queries(invocation: Invocation | None) -> list[str]:
    """Returns every SQL string the agent sent, in order."""
    queries = []
    for call in _tool_uses(invocation):
        if getattr(call, "name", None) != SQL_TOOL:
            continue
        args = getattr(call, "args", None) or {}
        if query := args.get("query"):
            queries.append(query)
    return queries


def _normalise_value(value: Any) -> Any:  # ruff: ignore[any-type]
    """Makes one cell comparable.

    Floats are rounded to FLOAT_PLACES. Two correct queries can compute the
    same average by different routes, say SUM/COUNT against AVG, and differ
    in the last bits of the double. Failing a right answer over floating
    point noise would make the metric worse than useless.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, FLOAT_PLACES)
    return value


def _normalise(rows: object) -> list[tuple[Any, ...]]:
    """Reduces a result set to a comparable, order-independent form.

    Row order is ignored unless the query asked for it, which this cannot
    know, so sorting is the safer default: a correct query that happens to
    emit rows in another order is not a wrong answer.

    Sorting is by the repr of each row rather than the row itself, because a
    result set can mix types across columns and tuples of mixed types are
    not orderable in Python.
    """
    if not isinstance(rows, list):
        return []
    normalised = [
        tuple(_normalise_value(v) for v in row)
        if isinstance(row, list)
        else (_normalise_value(row),)
        for row in rows
    ]
    return sorted(normalised, key=repr)


def _expected_rows(expected: Invocation | None) -> list[Any] | None:
    """Reads the expected result set from the golden case.

    Stored under the `expected_rows` key of the case's reference tool
    response, which keeps the golden file readable: it states the answer,
    not a particular spelling of the query that produces it.
    """
    for response in _tool_responses(expected):
        payload = getattr(response, "response", None)
        if isinstance(payload, dict) and "expected_rows" in payload:
            return payload["expected_rows"]
    return None


def _score_one(
    database: SqlDatabase, actual: Invocation, expected: Invocation
) -> float:
    """Scores one invocation by re-running its final query."""
    target = _expected_rows(expected)
    if target is None:
        return _FAIL

    queries = _sql_queries(actual)
    if not queries:
        return _FAIL

    # The last query is the one the answer was based on; earlier ones are
    # the failed attempts that the self-healing loop corrected.
    try:
        result = database.run(queries[-1])
    except SqlExecutionError:
        return _FAIL

    return _PASS if _normalise(result.rows) == _normalise(target) else _FAIL


def sql_result_match(
    eval_metric: EvalMetric,
    actual_invocations: list[Invocation],
    expected_invocations: list[Invocation] | None = None,
    conversation_scenario: ConversationScenario | None = None,
) -> EvaluationResult:
    """Scores 1.0 when the agent's SQL returns the expected rows.

    Compares result sets, not query text: many different queries are
    correct, and only the rows settle it.
    """
    del conversation_scenario
    expected = expected_invocations or []
    database = SqlDatabase()
    try:
        per_invocation = [
            _build_result(actual, exp, _score_one(database, actual, exp), eval_metric)
            for actual, exp in zip(actual_invocations, expected, strict=False)
        ]
    finally:
        database.close()

    return _aggregate(per_invocation, eval_metric)


def _first_attempt_failed(invocation: Invocation) -> bool:
    """Whether the agent's first SQL call came back as an error."""
    sql_responses = [
        getattr(r, "response", None)
        for r in _tool_responses(invocation)
        if getattr(r, "name", None) == SQL_TOOL
    ]
    if not sql_responses:
        return False
    first = sql_responses[0]
    return (
        isinstance(first, dict) and first.get("response_type") == _REFLECT_RESPONSE_TYPE
    )


def _recovered(invocation: Invocation) -> bool:
    """Whether a later SQL call succeeded after the first one failed."""
    for response in _tool_responses(invocation)[1:]:
        if getattr(response, "name", None) != SQL_TOOL:
            continue
        payload = getattr(response, "response", None)
        if isinstance(payload, dict) and "rows" in payload:
            return True
    return False


def sql_self_heal_recovery(
    eval_metric: EvalMetric,
    actual_invocations: list[Invocation],
    expected_invocations: list[Invocation] | None = None,
    conversation_scenario: ConversationScenario | None = None,
) -> EvaluationResult:
    """Scores whether the agent recovered after a failed first query.

    Invocations whose first query already worked are skipped rather than
    scored, so a dataset padded with easy queries cannot inflate the
    recovery rate. When no invocation failed at all the metric reports
    NOT_EVALUATED, which is honest: nothing needed healing.
    """
    del conversation_scenario
    expected = expected_invocations or [None] * len(actual_invocations)

    per_invocation = [
        _build_result(actual, exp, _PASS if _recovered(actual) else _FAIL, eval_metric)
        for actual, exp in zip(actual_invocations, expected, strict=False)
        if _first_attempt_failed(actual)
    ]

    if not per_invocation:
        return EvaluationResult(
            overall_score=None,
            overall_eval_status=EvalStatus.NOT_EVALUATED,
            per_invocation_results=[],
        )

    return _aggregate(per_invocation, eval_metric)


def _build_result(
    actual: Invocation,
    expected: Invocation | None,
    score: float,
    eval_metric: EvalMetric,
) -> PerInvocationResult:
    """Wraps one score in ADK's per-invocation result type."""
    return PerInvocationResult(
        actual_invocation=actual,
        expected_invocation=expected,
        score=score,
        eval_status=_status(score, eval_metric),
    )


def _status(score: float | None, eval_metric: EvalMetric) -> EvalStatus:
    """Compares a score against the metric's threshold."""
    if score is None:
        return EvalStatus.NOT_EVALUATED
    threshold = getattr(eval_metric, "threshold", None)
    if threshold is None:
        threshold = _PASS
    return EvalStatus.PASSED if score >= threshold else EvalStatus.FAILED


def _aggregate(
    per_invocation: list[PerInvocationResult], eval_metric: EvalMetric
) -> EvaluationResult:
    """Averages per-invocation scores into an overall result."""
    if not per_invocation:
        return EvaluationResult(
            overall_score=None,
            overall_eval_status=EvalStatus.NOT_EVALUATED,
            per_invocation_results=[],
        )

    overall = sum(r.score or _FAIL for r in per_invocation) / len(per_invocation)
    return EvaluationResult(
        overall_score=overall,
        overall_eval_status=_status(overall, eval_metric),
        per_invocation_results=per_invocation,
    )
