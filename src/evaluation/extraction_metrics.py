"""Deterministic metrics for document extraction.

Topic 3 asks for "metrics to measure data extraction accuracy from complex
layouts", and Topic 1 for "granular accuracy" and "schema adherence". Until
now both were judged by an LLM rubric, which has two problems for this job:
it costs money per case, and it is not reproducible, so a score moving
between runs tells you nothing about whether the agent changed.

These metrics compare the agent's `StructuredResponse` against the golden
one by value. They are free, they are stable, and they fail for a reason you
can point at.

`extraction_f1` is the headline: per-field precision, recall and F1 over the
extracted key/value pairs. F1 rather than exact-match because a response
that finds nine of ten fields is meaningfully better than one that finds
none, and a single number that cannot tell those apart cannot drive
optimization.

`schema_adherence` checks structure alone: does it parse, and is every field
populated. Kept separate from F1 because the two fail for different reasons
and the fix differs. A malformed response scores 0 on both, which would
otherwise be indistinguishable from a well-formed but wrong one.
"""

from __future__ import annotations

import json
import math
import re
from typing import TYPE_CHECKING, Any

from google.adk.evaluation.evaluator import (
    EvalStatus,
    EvaluationResult,
    PerInvocationResult,
)
from pydantic import ValidationError

from src.utils.data_model import StructuredResponse

if TYPE_CHECKING:
    from google.adk.evaluation.eval_case import ConversationScenario, Invocation
    from google.adk.evaluation.eval_metrics import EvalMetric

#: Relative tolerance when comparing two numbers. Documents round and restate
#: figures ("353,592" against "353592.0"), and an exact float match would
#: fail correct extractions.
NUMERIC_RELATIVE_TOLERANCE = 1e-6

_PASS = 1.0
_FAIL = 0.0

_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")
_NUMERIC = re.compile(r"^-?[\d,]*\.?\d+$")

#: A comma sitting between two digits is a thousands separator, not
#: punctuation. Removed before anything else so that "CHF 31,287" and
#: "CHF 31287" compare equal even though neither parses as a bare number.
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d)")

#: Stripped before comparing a key. Golden keys and model keys describe the
#: same field in different registers ("net_profit_2024" / "Net Profit 2024").
_KEY_NOISE = re.compile(r"[_\-]+")


def normalise_key(key: object) -> str:
    """Reduces a field name to a comparable form.

    Case, underscores, hyphens and punctuation are all presentation choices
    rather than meaning, so none of them should decide a match.
    """
    text = _KEY_NOISE.sub(" ", str(key).lower())
    text = _PUNCTUATION.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def _as_number(value: object) -> float | None:
    """Returns value as a float if it reads as a number, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "").replace("%", "")
        if _NUMERIC.match(cleaned.replace(",", "")):
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def normalise_value(value: object) -> Any:  # ruff: ignore[any-type]
    """Reduces an extracted value to a comparable form.

    Lists become frozensets: "the risks present in the document" is a set,
    and an agent that lists them in another order has not made a mistake.
    """
    if isinstance(value, list):
        return frozenset(normalise_value(item) for item in value)
    if (number := _as_number(value)) is not None:
        return number
    text = _THOUSANDS_SEPARATOR.sub("", str(value).lower())
    text = _PUNCTUATION.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def values_match(left: object, right: object) -> bool:
    """Whether two extracted values mean the same thing."""
    a, b = normalise_value(left), normalise_value(right)
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=NUMERIC_RELATIVE_TOLERANCE)
    return a == b


def _response_text(invocation: Invocation | None) -> str | None:
    """Returns the final response text of an invocation."""
    if invocation is None or invocation.final_response is None:
        return None
    for part in invocation.final_response.parts or []:
        if getattr(part, "text", None):
            return part.text
    return None


def parse_items(invocation: Invocation | None) -> list[dict[str, Any]] | None:
    """Parses a response into its list of extracted items.

    Returns None when the response is absent or is not valid JSON in the
    expected shape, which the callers treat as a structural failure rather
    than as an empty extraction. The two are different: nothing found and
    nothing parseable need different fixes.
    """
    text = _response_text(invocation)
    if not text:
        return None
    try:
        payload = json.loads(text)
    except TypeError, json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "answer" not in payload:
        return None
    answer = payload["answer"]
    if not isinstance(answer, list):
        return None
    return [item for item in answer if isinstance(item, dict)]


def _pairs(items: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    """Reduces items to comparable (key, value) pairs."""
    return [
        (normalise_key(item.get("key")), item.get("value"))
        for item in items
        if item.get("key") is not None
    ]


def score_extraction(
    predicted: list[dict[str, Any]], expected: list[dict[str, Any]]
) -> tuple[float, float, float]:
    """Returns precision, recall and F1 over extracted key/value pairs.

    A predicted pair counts as correct when a golden pair has the same key
    and an equal value. Each golden pair is consumed once, so repeating a
    correct field cannot inflate the score.
    """
    predicted_pairs = _pairs(predicted)
    expected_pairs = _pairs(expected)

    if not predicted_pairs and not expected_pairs:
        return _PASS, _PASS, _PASS
    if not predicted_pairs or not expected_pairs:
        return _FAIL, _FAIL, _FAIL

    remaining = list(expected_pairs)
    matched = 0
    for key, value in predicted_pairs:
        for index, (exp_key, exp_value) in enumerate(remaining):
            if key == exp_key and values_match(value, exp_value):
                matched += 1
                remaining.pop(index)
                break

    precision = matched / len(predicted_pairs)
    recall = matched / len(expected_pairs)
    if precision + recall == 0:
        return precision, recall, _FAIL
    return precision, recall, 2 * precision * recall / (precision + recall)


def score_schema(items: list[dict[str, Any]] | None) -> float:
    """Returns 1.0 when the response is well-formed and fully populated.

    Enforces what the rubric asked an LLM to judge: the declared schema,
    with no field left null or blank.
    """
    if items is None:
        return _FAIL
    try:
        parsed = StructuredResponse.model_validate({"answer": items})
    except ValidationError:
        return _FAIL
    if not parsed.answer:
        return _FAIL

    for item in parsed.answer:
        if not str(item.key).strip():
            return _FAIL
        if item.value is None or (
            isinstance(item.value, (str, list)) and not item.value
        ):
            return _FAIL
    return _PASS


def extraction_f1(
    eval_metric: EvalMetric,
    actual_invocations: list[Invocation],
    expected_invocations: list[Invocation] | None = None,
    conversation_scenario: ConversationScenario | None = None,
) -> EvaluationResult:
    """Scores per-field F1 of the extracted key/value pairs.

    Deterministic and free: no judge model is called.
    """
    del conversation_scenario
    results = []
    for actual, expected in zip(
        actual_invocations, expected_invocations or [], strict=False
    ):
        predicted_items = parse_items(actual)
        expected_items = parse_items(expected)
        if predicted_items is None or expected_items is None:
            score = _FAIL
        else:
            _, _, score = score_extraction(predicted_items, expected_items)
        results.append(_build(actual, expected, score, eval_metric))

    return _aggregate(results, eval_metric)


def schema_adherence(
    eval_metric: EvalMetric,
    actual_invocations: list[Invocation],
    expected_invocations: list[Invocation] | None = None,
    conversation_scenario: ConversationScenario | None = None,
) -> EvaluationResult:
    """Scores whether each response matches the schema with no empty fields."""
    del conversation_scenario
    expected = expected_invocations or [None] * len(actual_invocations)
    results = [
        _build(actual, exp, score_schema(parse_items(actual)), eval_metric)
        for actual, exp in zip(actual_invocations, expected, strict=False)
    ]
    return _aggregate(results, eval_metric)


def _build(
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
    results: list[PerInvocationResult], eval_metric: EvalMetric
) -> EvaluationResult:
    """Averages per-invocation scores into an overall result."""
    if not results:
        return EvaluationResult(
            overall_score=None,
            overall_eval_status=EvalStatus.NOT_EVALUATED,
            per_invocation_results=[],
        )
    overall = sum(r.score or _FAIL for r in results) / len(results)
    return EvaluationResult(
        overall_score=overall,
        overall_eval_status=_status(overall, eval_metric),
        per_invocation_results=results,
    )
