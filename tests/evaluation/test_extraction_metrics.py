"""Unit tests for the deterministic extraction metrics."""

import json

import pytest
from google.adk.evaluation.eval_case import Invocation
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.evaluator import EvalStatus
from google.genai import types

from src.evaluation.extraction_metrics import (
    extraction_f1,
    normalise_key,
    schema_adherence,
    score_extraction,
    score_schema,
    values_match,
)


def metric(name: str = "extraction_f1", threshold: float = 0.8) -> EvalMetric:
    """Builds the EvalMetric ADK would hand the function."""
    return EvalMetric(metric_name=name, threshold=threshold)


def response(items: list[dict] | str) -> Invocation:
    """Builds an invocation whose final response is the given payload."""
    text = items if isinstance(items, str) else json.dumps({"answer": items})
    return Invocation(
        invocation_id="inv-1",
        user_content=types.Content(parts=[types.Part(text="extract")]),
        final_response=types.Content(role="model", parts=[types.Part(text=text)]),
    )


def item(key: str, value: object, context: str = "ctx") -> dict:
    """Builds one extracted field."""
    return {"key": key, "value": value, "context": context}


# --- key and value normalisation -------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("net_profit_2024", "Net Profit 2024"),
        ("Total revenues", "total  revenues"),
        ("interest-rate", "interest rate"),
    ],
)
def test_keys_match_across_naming_styles(left: str, right: str):
    """Golden keys and model keys name the same field in different registers."""
    assert normalise_key(left) == normalise_key(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (353592, "353,592"),
        ("$1,876.02", 1876.02),
        (0.26, "0.26"),
        ("CHF 31287", "chf 31,287"),
    ],
)
def test_formatted_numbers_match_their_values(left: object, right: object):
    """Documents restate the same figure in several formats."""
    assert values_match(left, right)


def test_different_numbers_do_not_match():
    """Tolerance must not swallow a real difference."""
    assert not values_match(353592, 353593)


def test_lists_match_regardless_of_order():
    """A set of risk factors has no inherent order."""
    assert values_match(["Credit risk", "Market risk"], ["Market risk", "Credit risk"])


def test_lists_with_different_members_do_not_match():
    """Order-insensitivity must not become membership-insensitivity."""
    assert not values_match(["Credit risk"], ["Credit risk", "Market risk"])


# --- extraction F1 ----------------------------------------------------------


def test_perfect_extraction_scores_one():
    """The baseline."""
    items = [item("net_profit", 100), item("revenue", 200)]
    assert score_extraction(items, items) == (1.0, 1.0, 1.0)


def test_half_the_fields_found_scores_partial_credit():
    """Nine of ten fields is better than none, and the score must say so."""
    predicted = [item("net_profit", 100)]
    expected = [item("net_profit", 100), item("revenue", 200)]

    precision, recall, f1 = score_extraction(predicted, expected)

    assert precision == 1.0
    assert recall == 0.5
    assert f1 == pytest.approx(2 / 3)


def test_hallucinated_fields_cost_precision():
    """Inventing fields is a failure mode recall alone would reward."""
    predicted = [item("net_profit", 100), item("made_up", 999)]
    expected = [item("net_profit", 100)]

    precision, recall, _ = score_extraction(predicted, expected)

    assert precision == 0.5
    assert recall == 1.0


def test_right_key_wrong_value_is_not_a_match():
    """Finding the field but misreading it is still wrong."""
    precision, recall, f1 = score_extraction(
        [item("net_profit", 999)], [item("net_profit", 100)]
    )
    assert (precision, recall, f1) == (0.0, 0.0, 0.0)


def test_repeating_a_correct_field_cannot_inflate_the_score():
    """Each golden pair is consumed once."""
    predicted = [item("net_profit", 100), item("net_profit", 100)]
    expected = [item("net_profit", 100)]

    precision, recall, _ = score_extraction(predicted, expected)

    assert precision == 0.5
    assert recall == 1.0


def test_empty_prediction_against_empty_expectation_is_a_pass():
    """Correctly finding nothing is correct."""
    assert score_extraction([], []) == (1.0, 1.0, 1.0)


def test_empty_prediction_against_real_expectation_fails():
    """Returning nothing when fields exist is a total miss."""
    assert score_extraction([], [item("a", 1)]) == (0.0, 0.0, 0.0)


def test_metric_reports_f1_over_invocations():
    """The ADK entry point averages per-invocation F1."""
    result = extraction_f1(
        metric(),
        [response([item("a", 1)]), response([item("b", 2)])],
        [response([item("a", 1)]), response([item("b", 99)])],
    )

    assert result.overall_score == pytest.approx(0.5)
    assert len(result.per_invocation_results) == 2


def test_unparseable_response_scores_zero_not_an_error():
    """A model that answers in prose must fail, not crash the run."""
    result = extraction_f1(
        metric(),
        [response("I could not find the figures.")],
        [response([item("a", 1)])],
    )
    assert result.overall_score == 0.0


# --- schema adherence -------------------------------------------------------


def test_well_formed_response_adheres():
    """The baseline."""
    assert score_schema([item("a", 1)]) == 1.0


@pytest.mark.parametrize(
    "items",
    [
        [{"key": "a", "value": None, "context": "c"}],
        [{"key": "", "value": 1, "context": "c"}],
        [{"key": "a", "value": "", "context": "c"}],
        [{"key": "a", "value": [], "context": "c"}],
    ],
)
def test_empty_fields_fail_adherence(items: list[dict]):
    """This is what the LLM rubric was asked to catch, now done exactly."""
    assert score_schema(items) == 0.0


def test_missing_required_field_fails_adherence():
    """context is part of the declared schema."""
    assert score_schema([{"key": "a", "value": 1}]) == 0.0


def test_empty_answer_list_fails_adherence():
    """A valid envelope containing nothing has not answered."""
    assert score_schema([]) == 0.0


def test_unparseable_response_fails_adherence():
    """Prose is not a StructuredResponse."""
    assert score_schema(None) == 0.0


def test_schema_metric_runs_without_expectations():
    """Adherence is a property of the response alone."""
    result = schema_adherence(
        metric("schema_adherence", threshold=1.0), [response([item("a", 1)])], None
    )
    assert result.overall_score == 1.0
    assert result.overall_eval_status == EvalStatus.PASSED


def test_zero_value_is_populated():
    """0 and 0.0 are real extracted values, not missing ones."""
    assert score_schema([item("count", 0)]) == 1.0
