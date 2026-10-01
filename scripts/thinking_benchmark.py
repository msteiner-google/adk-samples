"""Sweeps the thinking budget and reports accuracy against latency and cost.

Topic 6: decide when advanced reasoning earns its keep. For each budget this
runs a full `adk eval` in its own subprocess, then joins three things the run
leaves behind:

  - accuracy, from the EvalSetResult in the agent's .adk/eval_history/
  - tokens and dollars, from reports/token_usage.jsonl
  - wall-clock latency, measured around the subprocess

A subprocess per budget is deliberate. ADK caches agent modules under a fixed
name, so two budgets evaluated in one process would silently share the first
one's planner.

Usage:
    uv run python scripts/thinking_benchmark.py --agent simple_agent
    uv run python scripts/thinking_benchmark.py --budgets 0,2048,-1
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.utils.accounting import DEFAULT_USAGE_LOG
from src.utils.eval_history import (
    latest_result_file,
    summarize_result_file,
)
from src.utils.thinking import (
    DEFAULT_BUDGET_SWEEP,
    THINKING_BUDGET_ENV,
    budget_label,
)
from src.utils.usage import TokenUsage

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENTS_ROOT = PROJECT_ROOT / "src" / "agents"
EVALSET = PROJECT_ROOT / "tests" / "eval" / "evalsets" / "golden_evalset.json"
EVAL_CONFIG = PROJECT_ROOT / "tests" / "eval" / "eval_config.json"
REPORTS_DIR = PROJECT_ROOT / "reports"

CSV_COLUMNS = (
    "budget",
    "pass_rate",
    "cases_passed",
    "cases_total",
    "latency_s",
    "prompt_tokens",
    "output_tokens",
    "thinking_tokens",
    "thinking_ratio",
    "total_usd",
    "thinking_usd",
)


def parse_args() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        default="simple_agent",
        help="Agent directory name under src/agents (default: simple_agent)",
    )
    parser.add_argument(
        "--budgets",
        default=",".join(str(b) for b in DEFAULT_BUDGET_SWEEP),
        help=(
            "Comma-separated thinking budgets. 0 disables thinking, "
            "-1 lets the model decide."
        ),
    )
    parser.add_argument(
        "--evalset", type=pathlib.Path, default=EVALSET, help="Evalset JSON to run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned runs and exit without calling the model",
    )
    return parser.parse_args()


def read_usage_since(
    path: pathlib.Path, offset: int
) -> tuple[TokenUsage, float | None, float | None]:
    """Reads usage records appended to the JSONL log after a byte offset.

    Returns summed usage, summed total cost and summed thinking cost. Either
    cost is None when no record carried one, which is how an unpriced model
    surfaces rather than being silently reported as free.
    """
    total = TokenUsage()
    cost: float | None = None
    thinking: float | None = None

    if not path.exists():
        return total, cost, thinking

    with path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            total += TokenUsage.model_validate(record["usage"])
            if (usd := record.get("total_usd")) is not None:
                cost = (cost or 0.0) + usd
            if (usd := record.get("thinking_usd")) is not None:
                thinking = (thinking or 0.0) + usd

    return total, cost, thinking


def run_one_budget(
    agent_dir: pathlib.Path, evalset: pathlib.Path, budget: int, usage_log: pathlib.Path
) -> dict[str, object]:
    """Runs a single eval at one thinking budget and collects its numbers."""
    usage_offset = usage_log.stat().st_size if usage_log.exists() else 0

    command = [
        "adk",
        "eval",
        str(agent_dir),
        str(evalset),
        "--config_file_path",
        str(EVAL_CONFIG),
    ]
    print(f"\n=== budget {budget_label(budget)}", flush=True)

    env = {**os.environ, THINKING_BUDGET_ENV: str(budget)}
    started = time.monotonic()
    completed = subprocess.run(command, env=env, check=False, cwd=PROJECT_ROOT)
    latency = time.monotonic() - started

    if completed.returncode != 0:
        # A metric below threshold makes adk eval exit non-zero. That is a
        # result worth recording, not a reason to abandon the sweep.
        print(f"    adk eval exited {completed.returncode}", flush=True)

    usage, cost, thinking_usd = read_usage_since(usage_log, usage_offset)
    result_file = latest_result_file(agent_dir)
    summary = (
        summarize_result_file(result_file, agent_dir.name) if result_file else None
    )

    return {
        "budget": budget_label(budget),
        "pass_rate": summary.pass_rate if summary else None,
        "cases_passed": summary.cases_passed if summary else None,
        "cases_total": summary.cases_total if summary else None,
        "latency_s": round(latency, 2),
        "prompt_tokens": usage.prompt,
        "output_tokens": usage.candidates,
        "thinking_tokens": usage.thoughts,
        "thinking_ratio": round(usage.thinking_ratio, 4),
        "total_usd": None if cost is None else round(cost, 6),
        "thinking_usd": None if thinking_usd is None else round(thinking_usd, 6),
    }


def write_csv(rows: list[dict[str, object]], agent: str) -> pathlib.Path:
    """Writes the sweep to a timestamped CSV and returns its path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / f"thinking_benchmark-{agent}-{stamp}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def format_cell(value: object) -> str:
    """Renders one table cell, showing missing data as a dash."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}" if value < 1 else f"{value:.2f}"
    return str(value)


def print_table(rows: list[dict[str, object]]) -> None:
    """Prints the sweep as a fixed-width table."""
    if not rows:
        print("No runs completed.")
        return

    widths = {
        col: max(len(col), *(len(format_cell(row[col])) for row in rows))
        for col in CSV_COLUMNS
    }
    header = "  ".join(col.ljust(widths[col]) for col in CSV_COLUMNS)
    print("\n" + header)
    print("  ".join("-" * widths[col] for col in CSV_COLUMNS))
    for row in rows:
        cells = (format_cell(row[col]).ljust(widths[col]) for col in CSV_COLUMNS)
        print("  ".join(cells))


def main() -> int:
    """Runs the sweep and writes the CSV."""
    args = parse_args()
    agent_dir = AGENTS_ROOT / args.agent
    if not agent_dir.is_dir():
        print(f"No such agent: {agent_dir}", file=sys.stderr)
        return 1
    if not args.evalset.exists():
        print(
            f"Evalset not found: {args.evalset}. Run 'make convert' first.",
            file=sys.stderr,
        )
        return 1

    budgets = [int(b) for b in args.budgets.split(",") if b.strip()]

    if args.dry_run:
        for budget in budgets:
            print(f"{THINKING_BUDGET_ENV}={budget} adk eval {agent_dir} {args.evalset}")
        return 0

    usage_log = PROJECT_ROOT / DEFAULT_USAGE_LOG
    rows = [
        run_one_budget(agent_dir, args.evalset, budget, usage_log) for budget in budgets
    ]

    print_table(rows)
    print(f"\nWrote {write_csv(rows, args.agent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
