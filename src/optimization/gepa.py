"""GEPA (Genetic Evolutionary Prompt Algorithms) implementation."""

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.optimization.base import PromptVariant


class GEPAEngine:
    """Handles genetic operations for prompt evolution."""

    def __init__(self, mutation_rate: float = 0.5) -> None:
        """Initializes the GEPA engine.

        Args:
            mutation_rate: The probability of mutation during evolution.
        """
        self.mutation_rate = mutation_rate

    @staticmethod
    def crossover(parent1: PromptVariant, parent2: PromptVariant) -> str:
        """Combines instructions from two parent variants.

        In the context of prompts, this can be a simple concatenation of unique
        instructional blocks or a more sophisticated LLM-based merge.
        """
        # Simple heuristic: split by double newline and take parts from both
        parts1 = parent1.instruction.split("\n\n")
        parts2 = parent2.instruction.split("\n\n")

        mid1 = len(parts1) // 2
        mid2 = len(parts2) // 2

        child_parts = parts1[:mid1] + parts2[mid2:]
        return "\n\n".join(child_parts)

    @staticmethod
    def select_parents(population: list[PromptVariant]) -> list[PromptVariant]:
        """Selects two parents using tournament selection."""
        min_population_size = 2
        if len(population) < min_population_size:
            return population * 2

        def tournament() -> PromptVariant:
            tournament_size = 3
            subset = random.sample(population, min(len(population), tournament_size))
            return max(subset, key=lambda v: v.overall_score)

        return [tournament(), tournament()]
