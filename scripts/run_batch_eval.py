"""Runs an evaluation matrix across agents, then writes a report.

Topic 5: a template for executing tests at scale. Expands agents against
thinking budgets into a job list, runs each job as its own `adk eval`
subprocess, and records a manifest of what ran.

Concurrency is opt-in and off by default. These jobs call a paid API and
share a project quota, so an accidental wide fan-out is expensive; --jobs
makes that choice explicit.

Usage:
    make batch
    uv run python scripts/run_batch_eval.py --agents simple_agent --jobs 2
    uv run python scripts/run_batch_eval.py --budgets 0,2048 --dry-run
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.utils.thinking import THINKING_BUDGET_ENV, budget_label

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENTS_ROOT = PROJECT_ROOT / "src" / "agents"
EVALSET = PROJECT_ROOT / "tests" / "eval" / "evalsets" / "golden_evalset.json"
EVAL_CONFIG = PROJECT_ROOT / "tests" / "eval" / "eval_config.json"
REPORTS_DIR = PROJECT_ROOT / "reports"


@dataclasses.dataclass(frozen=True)
class Job:
    """One cell of the evaluation matrix."""

    agent: str
    budget: int | None

    @property
    def label(self) -> str:
        """A short name for logs and the manifest."""
        if self.budget is None:
            return self.agent
        return f"{self.agent}@{budget_label(self.budget)}"


@dataclasses.dataclass
class JobResult:
    """The outcome of running one job."""

    job: Job
    returncode: int
    duration_s: float
    stdout_tail: str

    @property
    def ok(self) -> bool:
        """Whether adk eval reported success."""
        return self.returncode == 0


def parse_args() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agents",
        default=None,
        help="Comma-separated agent names (default: every agent under src/agents)",
    )
    parser.add_argument(
        "--budgets",
        default=None,
        help=(
            "Comma-separated thinking budgets to cross with each agent. "
            "Omit to use each agent's default."
        ),
    )
    parser.add_argument(
        "--evalset", type=pathlib.Path, default=EVALSET, help="Evalset JSON to run"
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Jobs to run in parallel. Default 1: these calls cost money.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List the matrix and exit"
    )
    return parser.parse_args()


def discover_agents() -> list[str]:
    """Returns the name of every agent package under src/agents."""
    if not AGENTS_ROOT.is_dir():
        return []
    return sorted(d.name for d in AGENTS_ROOT.iterdir() if (d / "agent.py").is_file())


def build_matrix(agents: list[str], budgets: list[int] | None) -> list[Job]:
    """Expands agents against budgets into a flat job list."""
    if not budgets:
        return [Job(agent=agent, budget=None) for agent in agents]
    return [Job(agent=agent, budget=budget) for agent in agents for budget in budgets]


def run_job(job: Job, evalset: pathlib.Path) -> JobResult:
    """Runs one eval as a subprocess and captures its outcome."""
    command = [
        "adk",
        "eval",
        str(AGENTS_ROOT / job.agent),
        str(evalset),
        "--config_file_path",
        str(EVAL_CONFIG),
    ]
    env = dict(os.environ)
    if job.budget is not None:
        env[THINKING_BUDGET_ENV] = str(job.budget)

    started = time.monotonic()
    completed = subprocess.run(
        command,
        env=env,
        check=False,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    duration = time.monotonic() - started

    tail = "\n".join((completed.stdout or "").strip().splitlines()[-5:])
    return JobResult(
        job=job, returncode=completed.returncode, duration_s=duration, stdout_tail=tail
    )


def write_manifest(results: list[JobResult], started_at: datetime) -> pathlib.Path:
    """Records what ran, so a report can be traced back to its inputs."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"batch-{started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(
        json.dumps(
            {
                "started_at": started_at.isoformat(),
                "jobs": [
                    {
                        "label": r.job.label,
                        "agent": r.job.agent,
                        "budget": r.job.budget,
                        "returncode": r.returncode,
                        "duration_s": round(r.duration_s, 2),
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def main() -> int:
    """Runs the matrix and summarises it."""
    args = parse_args()

    agents = (
        [a.strip() for a in args.agents.split(",") if a.strip()]
        if args.agents
        else discover_agents()
    )
    unknown = [a for a in agents if not (AGENTS_ROOT / a / "agent.py").is_file()]
    if unknown:
        print(f"No such agent(s): {', '.join(unknown)}", file=sys.stderr)
        return 1

    budgets = (
        [int(b) for b in args.budgets.split(",") if b.strip()] if args.budgets else None
    )
    matrix = build_matrix(agents, budgets)
    if not matrix:
        print("Empty matrix: no agents found.", file=sys.stderr)
        return 1

    if args.dry_run:
        for job in matrix:
            print(job.label)
        return 0

    if not args.evalset.exists():
        print(
            f"Evalset not found: {args.evalset}. Run 'make convert' first.",
            file=sys.stderr,
        )
        return 1

    started_at = datetime.now(UTC)
    print(f"Running {len(matrix)} job(s) with concurrency {args.jobs}")

    results: list[JobResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_job, job, args.evalset): job for job in matrix}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            mark = "ok" if result.ok else f"exit {result.returncode}"
            print(f"  {result.job.label}: {mark} in {result.duration_s:.1f}s")

    results.sort(key=lambda r: r.job.label)
    manifest = write_manifest(results, started_at)

    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} job(s) succeeded")
    print(f"Wrote {manifest}")
    print("Next: make report")

    # A metric below threshold makes adk eval exit non-zero. The batch still
    # ran correctly, so report it without failing the whole command.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
