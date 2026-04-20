"""Pareto-Frontier selection for multi-objective prompt optimization."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.optimization.base import PromptVariant


class ParetoSelector:
    """Selects the non-dominated set of prompt variants based on multiple objectives."""

    @staticmethod
    def is_dominated(
        candidate: PromptVariant, others: list[PromptVariant], metrics: list[str]
    ) -> bool:
        """Checks if a candidate is dominated by any other variant in the list.

        A variant is dominated if there exists another variant that is better or equal
        in all metrics and strictly better in at least one.
        """
        for other in others:
            if other == candidate:
                continue

            better_in_all = True
            strictly_better_in_one = False

            for metric in metrics:
                # We assume higher is better for all metrics in this implementation
                val_other = other.metadata.get(
                    metric, other.overall_score if metric == "accuracy" else 0.0
                )
                val_cand = candidate.metadata.get(
                    metric, candidate.overall_score if metric == "accuracy" else 0.0
                )

                if val_other < val_cand:
                    better_in_all = False
                    break
                if val_other > val_cand:
                    strictly_better_in_one = True

            if better_in_all and strictly_better_in_one:
                return True

        return False

    def select_frontier(
        self, variants: list[PromptVariant], metrics: list[str] | None = None
    ) -> list[PromptVariant]:
        """Returns the set of variants that are not dominated by any other variant."""
        if metrics is None:
            metrics = ["accuracy"]
        return [v for v in variants if not self.is_dominated(v, variants, metrics)]
