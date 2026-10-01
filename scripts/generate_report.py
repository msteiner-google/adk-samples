"""Generates a technical report from the eval results already on disk.

Topic 5: automatic reports on model health and performance trends. Reads
nothing but artefacts left by previous runs, so it is safe to run at any
time and never calls a model:

  - the two most recent EvalSetResult files per agent, for health and trend
  - reports/token_usage.jsonl, for tokens and cost

Usage:
    make report
    uv run python scripts/generate_report.py --output reports/nightly.md
    uv run python scripts/generate_report.py --fail-on-regression
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.utils.accounting import DEFAULT_USAGE_LOG
from src.utils.eval_history import list_result_files, summarize_result_file
from src.utils.report import RunComparison, compare_runs, render_markdown
from src.utils.usage import TokenUsage

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENTS_ROOT = PROJECT_ROOT / "src" / "agents"
REPORTS_DIR = PROJECT_ROOT / "reports"


def parse_args() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help="Markdown file to write (default: reports/report-<timestamp>.md)",
    )
    parser.add_argument(
        "--usage-log",
        type=pathlib.Path,
        default=PROJECT_ROOT / DEFAULT_USAGE_LOG,
        help="Token usage JSONL to read cost from",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero if any case regressed. For use in CI.",
    )
    return parser.parse_args()


def discover_agent_dirs() -> list[pathlib.Path]:
    """Returns every agent package under src/agents."""
    if not AGENTS_ROOT.is_dir():
        return []
    return sorted(d for d in AGENTS_ROOT.iterdir() if (d / "agent.py").is_file())


def usage_by_app(path: pathlib.Path) -> dict[str, tuple[TokenUsage, float | None]]:
    """Totals token usage and cost per App from the JSONL log.

    Cost stays None for an app whose records were all unpriced, so that an
    unknown price is never rendered as a free run.
    """
    totals: dict[str, tuple[TokenUsage, float | None]] = {}
    if not path.exists():
        return totals

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            app = record.get("app_name", "unknown")
            usage, cost = totals.get(app, (TokenUsage(), None))
            usage += TokenUsage.model_validate(record["usage"])
            if (usd := record.get("total_usd")) is not None:
                cost = (cost or 0.0) + usd
            totals[app] = (usage, cost)

    return totals


def build_comparisons(
    usage_totals: dict[str, tuple[TokenUsage, float | None]],
) -> list[RunComparison]:
    """Compares each agent's latest run against the one before it."""
    comparisons = []
    for agent_dir in discover_agent_dirs():
        results = list_result_files(agent_dir)
        if not results:
            continue

        current = summarize_result_file(results[-1], agent_dir.name)
        previous = (
            summarize_result_file(results[-2], agent_dir.name)
            if len(results) > 1
            else None
        )
        usage, cost = usage_totals.get(agent_dir.name, (TokenUsage(), None))
        comparisons.append(compare_runs(current, previous, usage=usage, total_usd=cost))

    return comparisons


def main() -> int:
    """Writes the report and optionally fails on a regression."""
    args = parse_args()

    comparisons = build_comparisons(usage_by_app(args.usage_log))
    if not comparisons:
        print(
            "No eval results found. Run 'make eval' or 'make batch' first.",
            file=sys.stderr,
        )
        return 1

    now = datetime.now(UTC)
    markdown = render_markdown(comparisons, generated_at=now.isoformat())

    output = args.output or (
        REPORTS_DIR / f"report-{now.strftime('%Y%m%dT%H%M%SZ')}.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")

    regressions = [d for c in comparisons for d in c.regressions]
    for comparison in comparisons:
        run = comparison.current
        print(f"{run.app_name}: {run.cases_passed}/{run.cases_total} passed")
    print(f"Regressions: {len(regressions)}")
    print(f"Wrote {output}")

    if regressions and args.fail_on_regression:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
