"""Monkeypatch for ADK LocalEvalSampler crash."""

import logging
from typing import Any

try:
    from google.adk.optimization import local_eval_sampler
except (ImportError, AttributeError):
    local_eval_sampler = None

logger = logging.getLogger(__name__)


def apply_adk_patch() -> None:
    """Fixes a TypeError in google.adk.optimization.local_eval_sampler.

    Specifically, it patches _extract_eval_data to ensure metric_result.score
    is not None before rounding.
    """
    if local_eval_sampler is None:
        return

    try:
        original_extract_eval_data = (
            local_eval_sampler.LocalEvalSampler._extract_eval_data  # noqa: SLF001
        )

        def patched_extract_eval_data(
            self: Any,  # noqa: ANN401
            eval_set_id: Any,  # noqa: ANN401
            eval_results: Any,  # noqa: ANN401
        ) -> Any:  # noqa: ANN401
            # We need to ensure that metric_result.score is not None before rounding.
            # This mirrors the logic in _extract_eval_data but with safety checks.
            for eval_result in eval_results:
                for per_inv_res in eval_result.eval_metric_result_per_invocation:
                    for metric_res in per_inv_res.eval_metric_results:
                        if metric_res.score is None:
                            metric_res.score = 0.0
            return original_extract_eval_data(self, eval_set_id, eval_results)

        local_eval_sampler.LocalEvalSampler._extract_eval_data = (  # noqa: SLF001
            patched_extract_eval_data
        )
        logger.info("Successfully applied ADK LocalEvalSampler patch")
    except (ImportError, AttributeError) as e:
        logger.warning("Failed to apply ADK LocalEvalSampler patch: %s", e)
