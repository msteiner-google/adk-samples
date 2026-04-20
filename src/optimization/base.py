"""Base classes and data types for prompt optimization."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PromptVariant(BaseModel):
    """Represents a candidate prompt with its performance metadata."""

    instruction: str = Field(description="The system instruction for the agent.")
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="A map from example UID to the score on that example.",
    )
    trajectories: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict,
        description="A map from example UID to the execution trajectory.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional metadata for the variant (e.g., parent, mutation type)."
        ),
    )

    @property
    def overall_score(self) -> float:
        """Returns the average score across all examples."""
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)


class OptimizationConfig(BaseModel):
    """Configuration for the optimization process."""

    max_iterations: int = Field(
        default=5, description="Maximum number of evolution steps."
    )
    population_size: int = Field(
        default=4, description="Number of variants to maintain."
    )
    mutation_rate: float = Field(default=0.5, description="Probability of mutation.")
    judge_model: str = Field(
        default="gemini-2.5-flash", description="Model used for reflection."
    )
