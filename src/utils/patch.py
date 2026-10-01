"""Monkeypatch for ADK LocalEvalSampler crash."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    from google.adk.optimization import local_eval_sampler
except ImportError, AttributeError:
    local_eval_sampler = None

logger = logging.getLogger(__name__)

_PATCH_MARKER = "_adk_none_score_patch_applied"


def _coerce_none_scores_to_zero(eval_results: Any) -> None:  # ruff: ignore[any-type]
    """Replaces every ``None`` metric score with 0.0, in place.

    ADK's ``_extract_eval_data`` rounds ``metric_result.score`` unconditionally,
    which raises ``TypeError`` when a metric failed to produce a score.
    """
    for eval_result in eval_results:
        for per_inv_res in eval_result.eval_metric_result_per_invocation:
            for metric_res in per_inv_res.eval_metric_results:
                if metric_res.score is None:
                    metric_res.score = 0.0


def _build_patched_extract_eval_data(
    original: Callable[..., Any],
) -> Callable[..., Any]:
    """Wraps ``original`` so that ``None`` scores are zeroed before it runs."""

    def patched_extract_eval_data(
        self: Any,  # ruff: ignore[any-type]
        eval_set_id: Any,  # ruff: ignore[any-type]
        eval_results: Any,  # ruff: ignore[any-type]
    ) -> Any:  # ruff: ignore[any-type]
        _coerce_none_scores_to_zero(eval_results)
        return original(self, eval_set_id, eval_results)

    setattr(patched_extract_eval_data, _PATCH_MARKER, True)
    return patched_extract_eval_data


def apply_adk_patch() -> None:
    """Fixes a TypeError in google.adk.optimization.local_eval_sampler.

    Specifically, it patches _extract_eval_data to ensure metric_result.score
    is not None before rounding.
    """
    if local_eval_sampler is None:
        return

    try:
        sampler = local_eval_sampler.LocalEvalSampler
        original = sampler._extract_eval_data  # ruff: ignore[private-member-access]
        if getattr(original, _PATCH_MARKER, False):
            return
        sampler._extract_eval_data = _build_patched_extract_eval_data(original)  # ruff: ignore[private-member-access]
    except (ImportError, AttributeError) as e:
        logger.warning("Failed to apply ADK LocalEvalSampler patch: %s", e)
    else:
        logger.info("Successfully applied ADK LocalEvalSampler patch")
