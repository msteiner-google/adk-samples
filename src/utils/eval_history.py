"""Reads the eval result files that `adk eval` leaves behind.

`adk eval` persists an `EvalSetResult` per run under
`src/agents/<app>/.adk/eval_history/`. Those files are the only machine
readable record of a run, so both the thinking benchmark and the report
generator read them through this module rather than scraping stdout.
"""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Iterable

EVAL_HISTORY_DIR = pathlib.Path(".adk/eval_history")

# EvalStatus.PASSED in google.adk.evaluation.eval_case; stored as an int.
_STATUS_PASSED = 1


class MetricSummary(BaseModel):
    """Aggregate of one metric across every case in a run."""

    metric_name: str
    mean_score: float | None = Field(
        default=None, description="None when no case produced a score"
    )
    passed: int = 0
    total: int = 0

    @property
    def pass_rate(self) -> float | None:
        """Share of cases that met the threshold, or None for an empty run."""
        if self.total == 0:
            return None
        return self.passed / self.total


class RunSummary(BaseModel):
    """A whole eval run, reduced to what a report or benchmark needs."""

    app_name: str
    eval_set_id: str
    result_id: str
    timestamp: float | None = None
    source_path: str
    cases_total: int = 0
    cases_passed: int = 0
    metrics: dict[str, MetricSummary] = Field(default_factory=dict)
    case_status: dict[str, bool] = Field(default_factory=dict)

    @property
    def pass_rate(self) -> float | None:
        """Share of cases that passed overall, or None for an empty run."""
        if self.cases_total == 0:
            return None
        return self.cases_passed / self.cases_total


def eval_history_dir(agent_dir: pathlib.Path) -> pathlib.Path:
    """Returns the eval history directory for an agent directory."""
    return agent_dir / EVAL_HISTORY_DIR


def list_result_files(agent_dir: pathlib.Path) -> list[pathlib.Path]:
    """Returns the agent's result files, oldest first by modification time."""
    history = eval_history_dir(agent_dir)
    if not history.is_dir():
        return []
    return sorted(history.glob("*.json"), key=lambda p: p.stat().st_mtime)


def latest_result_file(agent_dir: pathlib.Path) -> pathlib.Path | None:
    """Returns the agent's most recent result file, if any."""
    files = list_result_files(agent_dir)
    return files[-1] if files else None


def summarize_result_file(path: pathlib.Path, app_name: str) -> RunSummary:
    """Reduces one `EvalSetResult` file to a `RunSummary`.

    Parsed from raw JSON rather than through the ADK pydantic models so that
    a schema addition in a future ADK release cannot break report generation.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    case_results = raw.get("eval_case_results") or []

    scores: dict[str, list[float]] = {}
    outcomes: dict[str, list[bool]] = {}
    case_status: dict[str, bool] = {}

    for case in case_results:
        eval_id = case.get("eval_id", "<unknown>")
        case_status[eval_id] = _is_passed(case.get("final_eval_status"))
        for metric in case.get("overall_eval_metric_results") or []:
            name = metric.get("metric_name")
            if name is None:
                continue
            if (score := metric.get("score")) is not None:
                scores.setdefault(name, []).append(float(score))
            outcomes.setdefault(name, []).append(_is_passed(metric.get("eval_status")))

    metrics = {
        name: MetricSummary(
            metric_name=name,
            mean_score=_mean(scores.get(name, [])),
            passed=sum(results),
            total=len(results),
        )
        for name, results in outcomes.items()
    }

    return RunSummary(
        app_name=app_name,
        eval_set_id=raw.get("eval_set_id", "<unknown>"),
        result_id=raw.get("eval_set_result_id", path.stem),
        timestamp=raw.get("creation_timestamp"),
        source_path=str(path),
        cases_total=len(case_status),
        cases_passed=sum(case_status.values()),
        metrics=metrics,
        case_status=case_status,
    )


def _is_passed(status: object) -> bool:
    """Interprets an ADK EvalStatus, which serialises as an int."""
    return status == _STATUS_PASSED


def _mean(values: Iterable[float]) -> float | None:
    """Returns the mean, or None for an empty sequence."""
    items = list(values)
    if not items:
        return None
    return sum(items) / len(items)
