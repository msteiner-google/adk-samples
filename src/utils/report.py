"""Compares eval runs and renders a technical report.

Topic 5 asks for automatic reports on model health and performance trends. A
single run's pass rate is health; the trend needs the run before it. The
comparison logic lives here, separate from the script that does the I/O, so
that regression detection can be tested without running an agent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from src.utils.eval_history import RunSummary
from src.utils.usage import TokenUsage

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: Metric score moves smaller than this are treated as noise, not as a trend.
#: LLM-judged metrics jitter between runs, so a tiny delta is not a signal.
SCORE_NOISE_FLOOR = 0.01


class CaseOutcome(StrEnum):
    """How a single eval case changed between two runs."""

    REGRESSED = "regressed"
    FIXED = "fixed"
    STILL_PASSING = "still_passing"
    STILL_FAILING = "still_failing"
    NEW = "new"
    REMOVED = "removed"


class CaseDelta(BaseModel):
    """One eval case, before and after."""

    eval_id: str
    previous: bool | None = None
    current: bool | None = None
    outcome: CaseOutcome


class MetricDelta(BaseModel):
    """One metric's mean score, before and after."""

    metric_name: str
    previous_mean: float | None = None
    current_mean: float | None = None

    @property
    def delta(self) -> float | None:
        """Change in mean score, or None if either side is missing."""
        if self.previous_mean is None or self.current_mean is None:
            return None
        return self.current_mean - self.previous_mean

    @property
    def is_meaningful(self) -> bool:
        """Whether the move is larger than run-to-run judge noise."""
        delta = self.delta
        return delta is not None and abs(delta) >= SCORE_NOISE_FLOOR


class RunComparison(BaseModel):
    """A run, optionally set against the run before it."""

    current: RunSummary
    previous: RunSummary | None = None
    case_deltas: list[CaseDelta] = Field(default_factory=list)
    metric_deltas: list[MetricDelta] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    total_usd: float | None = None

    @property
    def regressions(self) -> list[CaseDelta]:
        """Cases that passed before and fail now. The headline of a report."""
        return [d for d in self.case_deltas if d.outcome == CaseOutcome.REGRESSED]

    @property
    def fixes(self) -> list[CaseDelta]:
        """Cases that failed before and pass now."""
        return [d for d in self.case_deltas if d.outcome == CaseOutcome.FIXED]

    @property
    def is_first_run(self) -> bool:
        """Whether there is no baseline to compare against."""
        return self.previous is None


def _classify(*, previous: bool | None, current: bool | None) -> CaseOutcome:
    """Maps a before/after pair of pass flags to an outcome."""
    if previous is None:
        return CaseOutcome.NEW
    if current is None:
        return CaseOutcome.REMOVED
    if previous and not current:
        return CaseOutcome.REGRESSED
    if not previous and current:
        return CaseOutcome.FIXED
    return CaseOutcome.STILL_PASSING if current else CaseOutcome.STILL_FAILING


def compare_runs(
    current: RunSummary,
    previous: RunSummary | None = None,
    usage: TokenUsage | None = None,
    total_usd: float | None = None,
) -> RunComparison:
    """Builds the case- and metric-level diff between two runs.

    A case present in only one of the runs is reported as NEW or REMOVED
    rather than being dropped, so that adding a test case cannot quietly
    look like a pass-rate change.
    """
    previous_cases = previous.case_status if previous else {}
    all_ids = sorted(set(current.case_status) | set(previous_cases))

    case_deltas = [
        CaseDelta(
            eval_id=eval_id,
            previous=previous_cases.get(eval_id),
            current=current.case_status.get(eval_id),
            outcome=_classify(
                previous=previous_cases.get(eval_id) if previous else None,
                current=current.case_status.get(eval_id),
            ),
        )
        for eval_id in all_ids
    ]

    previous_metrics = previous.metrics if previous else {}
    metric_deltas = [
        MetricDelta(
            metric_name=name,
            previous_mean=(
                previous_metrics[name].mean_score if name in previous_metrics else None
            ),
            current_mean=(
                current.metrics[name].mean_score if name in current.metrics else None
            ),
        )
        for name in sorted(set(current.metrics) | set(previous_metrics))
    ]

    return RunComparison(
        current=current,
        previous=previous,
        case_deltas=case_deltas,
        metric_deltas=metric_deltas,
        usage=usage or TokenUsage(),
        total_usd=total_usd,
    )


def _pct(value: float | None) -> str:
    """Formats a 0-1 ratio as a percentage, or a dash when unknown."""
    return "-" if value is None else f"{value * 100:.0f}%"


def _score(value: float | None) -> str:
    """Formats a score, or a dash when unknown."""
    return "-" if value is None else f"{value:.3f}"


def _signed(value: float | None) -> str:
    """Formats a delta with an explicit sign, or a dash when unknown."""
    return "-" if value is None else f"{value:+.3f}"


def _usd(value: float | None) -> str:
    """Formats a dollar amount, or a dash when the model was not priced."""
    return "-" if value is None else f"${value:.4f}"


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    """Renders a markdown table."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render_markdown(comparisons: Sequence[RunComparison], generated_at: str) -> str:
    """Renders the full report.

    Leads with regressions because that is the only section that demands
    action; totals and per-case detail follow.
    """
    lines = [
        "# Agent evaluation report",
        "",
        f"Generated {generated_at}",
        "",
    ]

    lines += _render_headline(comparisons)
    lines += _render_regressions(comparisons)

    for comparison in comparisons:
        lines += _render_app(comparison)

    return "\n".join(lines) + "\n"


def _render_headline(comparisons: Sequence[RunComparison]) -> list[str]:
    """Renders the one-table summary across every app."""
    rows = []
    for comparison in comparisons:
        run = comparison.current
        trend = (
            "first run"
            if comparison.is_first_run
            else (
                f"{len(comparison.regressions)} regressed, "
                f"{len(comparison.fixes)} fixed"
            )
        )
        rows.append([
            run.app_name,
            f"{run.cases_passed}/{run.cases_total}",
            _pct(run.pass_rate),
            trend,
            f"{comparison.usage.thoughts:,}",
            _usd(comparison.total_usd),
        ])

    return [
        "## Summary",
        "",
        *_table(
            ["App", "Passed", "Pass rate", "Vs. previous", "Thinking tokens", "Cost"],
            rows,
        ),
        "",
    ]


def _render_regressions(comparisons: Sequence[RunComparison]) -> list[str]:
    """Renders the regression section, or a clean bill of health."""
    rows = [
        [comparison.current.app_name, delta.eval_id]
        for comparison in comparisons
        for delta in comparison.regressions
    ]

    if not rows:
        return ["## Regressions", "", "None.", ""]

    return [
        "## Regressions",
        "",
        f"{len(rows)} case(s) passed in the previous run and fail now.",
        "",
        *_table(["App", "Case"], rows),
        "",
    ]


def _render_app(comparison: RunComparison) -> list[str]:
    """Renders the per-app detail section."""
    run = comparison.current
    lines = [
        f"## {run.app_name}",
        "",
        f"Eval set `{run.eval_set_id}`, result `{run.result_id}`.",
        "",
    ]

    if comparison.metric_deltas:
        lines += [
            "### Metrics",
            "",
            *_table(
                ["Metric", "Mean", "Previous", "Delta", "Pass rate"],
                [
                    [
                        delta.metric_name,
                        _score(delta.current_mean),
                        _score(delta.previous_mean),
                        _signed(delta.delta) if delta.is_meaningful else "~",
                        _pct(
                            run.metrics[delta.metric_name].pass_rate
                            if delta.metric_name in run.metrics
                            else None
                        ),
                    ]
                    for delta in comparison.metric_deltas
                ],
            ),
            "",
        ]

    lines += [
        "### Cases",
        "",
        *_table(
            ["Case", "Result", "Change"],
            [
                [
                    delta.eval_id,
                    _case_mark(passed=delta.current),
                    delta.outcome.value,
                ]
                for delta in comparison.case_deltas
            ],
        ),
        "",
    ]

    usage = comparison.usage
    lines += [
        "### Cost",
        "",
        *_table(
            ["Prompt", "Output", "Thinking", "Calls", "Total"],
            [
                [
                    f"{usage.prompt:,}",
                    f"{usage.candidates:,}",
                    f"{usage.thoughts:,} ({usage.thinking_ratio:.0%} of output)",
                    str(usage.calls),
                    _usd(comparison.total_usd),
                ]
            ],
        ),
        "",
    ]
    return lines


def _case_mark(*, passed: bool | None) -> str:
    """Renders a case result."""
    if passed is None:
        return "absent"
    return "pass" if passed else "FAIL"
