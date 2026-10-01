"""Unit tests for reading adk eval result files."""

import json
import pathlib

from src.utils.eval_history import (
    latest_result_file,
    list_result_files,
    summarize_result_file,
)

PASSED = 1
FAILED = 2


def make_result(cases: list[dict]) -> dict:
    """Builds an EvalSetResult payload shaped like the one adk eval writes."""
    return {
        "eval_set_result_id": "simple_agent_golden_evalset_123",
        "eval_set_id": "golden_evalset",
        "creation_timestamp": 1735689600.0,
        "eval_case_results": cases,
    }


def make_case(eval_id: str, status: int, metrics: list[tuple[str, float, int]]) -> dict:
    """Builds one eval case result with its overall metric scores."""
    return {
        "eval_id": eval_id,
        "final_eval_status": status,
        "overall_eval_metric_results": [
            {"metric_name": name, "score": score, "eval_status": metric_status}
            for name, score, metric_status in metrics
        ],
    }


def write_history(tmp_path: pathlib.Path, payload: dict, name: str) -> pathlib.Path:
    """Writes a result file into an agent's .adk/eval_history directory."""
    history = tmp_path / ".adk" / "eval_history"
    history.mkdir(parents=True, exist_ok=True)
    path = history / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_summary_counts_cases_and_metrics(tmp_path: pathlib.Path):
    """Case-level and metric-level pass rates are both reported."""
    path = write_history(
        tmp_path,
        make_result([
            make_case("TC001", PASSED, [("final_response_match_v2", 0.9, PASSED)]),
            make_case("TC002", FAILED, [("final_response_match_v2", 0.5, FAILED)]),
        ]),
        "run.json",
    )

    summary = summarize_result_file(path, "simple_agent")

    assert summary.cases_total == 2
    assert summary.cases_passed == 1
    assert summary.pass_rate == 0.5
    metric = summary.metrics["final_response_match_v2"]
    assert metric.mean_score == 0.7
    assert metric.pass_rate == 0.5


def test_per_case_status_is_retained(tmp_path: pathlib.Path):
    """A report needs to name which case regressed, not just how many."""
    path = write_history(
        tmp_path,
        make_result([
            make_case("TC001", PASSED, []),
            make_case("TC007_10K_LAYOUT", FAILED, []),
        ]),
        "run.json",
    )

    summary = summarize_result_file(path, "layout_aware_agent")

    assert summary.case_status == {"TC001": True, "TC007_10K_LAYOUT": False}


def test_metric_without_a_score_still_counts_its_outcome(tmp_path: pathlib.Path):
    """A metric that errored has no score but did still fail the case."""
    path = write_history(
        tmp_path,
        make_result([
            {
                "eval_id": "TC001",
                "final_eval_status": FAILED,
                "overall_eval_metric_results": [
                    {
                        "metric_name": "rubric_based_final_response_quality_v1",
                        "score": None,
                        "eval_status": FAILED,
                    }
                ],
            }
        ]),
        "run.json",
    )

    metric = summarize_result_file(path, "simple_agent").metrics[
        "rubric_based_final_response_quality_v1"
    ]
    assert metric.mean_score is None
    assert metric.total == 1
    assert metric.passed == 0


def test_empty_run_has_no_pass_rate(tmp_path: pathlib.Path):
    """An empty run must report None, not a misleading 0% or a crash."""
    path = write_history(tmp_path, make_result([]), "run.json")
    assert summarize_result_file(path, "simple_agent").pass_rate is None


def test_missing_history_directory_is_not_an_error(tmp_path: pathlib.Path):
    """An agent that has never been evaluated simply has no results."""
    assert list_result_files(tmp_path) == []
    assert latest_result_file(tmp_path) is None


def test_latest_result_file_is_the_newest(tmp_path: pathlib.Path):
    """Benchmarks read back the run they just triggered."""
    first = write_history(tmp_path, make_result([]), "old.json")
    second = write_history(tmp_path, make_result([]), "new.json")
    import os

    os.utime(first, (1_000_000, 1_000_000))
    os.utime(second, (2_000_000, 2_000_000))

    assert latest_result_file(tmp_path) == second
    assert list_result_files(tmp_path) == [first, second]
