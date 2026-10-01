"""Thinking-budget control, driven by an environment variable.

Topic 6 asks when advanced reasoning is worth paying for. Answering that
means running the same agent over the same evalset at several thinking
budgets, which in turn means the budget has to be settable from outside the
agent definition. `adk eval` offers no flag for it, so the channel is an
environment variable that the benchmark script sets per subprocess.
"""

from __future__ import annotations

import logging
import os

from google.adk.planners.built_in_planner import BuiltInPlanner
from google.genai import types

logger = logging.getLogger(__name__)

THINKING_BUDGET_ENV = "ADK_THINKING_BUDGET"

# Values accepted by the Gemini API for thinking_budget, beyond a plain count.
BUDGET_DISABLED = 0
BUDGET_DYNAMIC = -1

#: Budgets the benchmark sweeps by default. 0 turns thinking off, -1 lets the
#: model decide, and the rest bracket the useful range for Flash.
DEFAULT_BUDGET_SWEEP = (0, 512, 2048, 8192, BUDGET_DYNAMIC)


def budget_label(budget: int | None) -> str:
    """Returns a short human-readable name for a budget value."""
    if budget is None:
        return "default"
    if budget == BUDGET_DISABLED:
        return "off"
    if budget == BUDGET_DYNAMIC:
        return "dynamic"
    return str(budget)


def parse_budget(raw: str | None) -> int | None:
    """Parses a budget from its string form, returning None when unset.

    An unparseable value is logged and treated as unset rather than raising:
    a malformed env var should not take down an eval run that would otherwise
    have used the model default.
    """
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Ignoring %s=%r: expected an integer token budget, %d to disable "
            "or %d for dynamic.",
            THINKING_BUDGET_ENV,
            raw,
            BUDGET_DISABLED,
            BUDGET_DYNAMIC,
        )
        return None


def planner_from_env() -> BuiltInPlanner | None:
    """Builds a planner from `ADK_THINKING_BUDGET`, or None when it is unset.

    Returning None leaves the agent on the model's default thinking behaviour,
    so normal `make eval` runs are unchanged by this module's existence.
    """
    budget = parse_budget(os.environ.get(THINKING_BUDGET_ENV))
    if budget is None:
        return None

    logger.info("Thinking budget set to %s", budget_label(budget))
    return BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            thinking_budget=budget,
            # Without this the API may omit thoughts_token_count, which would
            # leave the accountant unable to price the reasoning.
            include_thoughts=budget != BUDGET_DISABLED,
        )
    )
