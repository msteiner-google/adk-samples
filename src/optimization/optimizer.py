"""Main optimizer implementation tying together GEPA, Reflection, and Pareto."""

from typing import TYPE_CHECKING

from google.adk.optimization.agent_optimizer import AgentOptimizer
from google.adk.optimization.data_types import (
    AgentWithScores,
    OptimizerResult,
    UnstructuredSamplingResult,
)
from loguru import logger

from src.optimization.base import OptimizationConfig, PromptVariant
from src.optimization.gepa import GEPAEngine
from src.optimization.reflection import Reflector
from src.optimization.selection import ParetoSelector

if TYPE_CHECKING:
    from google.adk.agents.llm_agent import LlmAgent
    from google.adk.optimization.sampler import Sampler


class CustomGEPAOptimizer(AgentOptimizer[UnstructuredSamplingResult, AgentWithScores]):
    """Custom implementation of GEPA methodology for prompt optimization."""

    def __init__(self, config: OptimizationConfig) -> None:
        """Initializes the GEPA optimizer.

        Args:
            config: The optimization configuration.
        """
        self.config = config
        self.gepa = GEPAEngine(mutation_rate=config.mutation_rate)
        self.reflector = Reflector(model_name=config.judge_model)
        self.selector = ParetoSelector()

    async def optimize(
        self,
        initial_agent: LlmAgent,
        sampler: Sampler[UnstructuredSamplingResult],
    ) -> OptimizerResult[AgentWithScores]:
        """Runs the custom GEPA optimization loop."""
        # 1. Initialize population
        current_variant = PromptVariant(instruction=initial_agent.instruction)
        population = [current_variant]

        train_ids = sampler.get_train_example_ids()
        val_ids = sampler.get_validation_example_ids()

        for iteration in range(self.config.max_iterations):
            logger.info(
                "Starting iteration {}/{}", iteration + 1, self.config.max_iterations
            )

            # 2. Evaluate population (Sampling)
            for variant in population:
                if not variant.scores:
                    result = await sampler.sample_and_score(
                        initial_agent.clone(
                            update={"instruction": variant.instruction}
                        ),
                        example_set="train",
                        batch=train_ids,
                        capture_full_eval_data=True,
                    )
                    variant.scores = result.scores
                    variant.trajectories = result.data or {}

            # 3. Reflection Loop: Diagnose failures and mutate
            new_variants = []
            for variant in population:
                failed_examples = [
                    {
                        "input": k,
                        "actual": v.get("actual"),
                        "expected": v.get("expected"),
                        "trajectory": v.get("trajectory"),
                    }
                    for k, v in variant.trajectories.items()
                    if variant.scores.get(k, 0) < 1.0
                ]

                if failed_examples:
                    diagnosis = self.reflector.diagnose_failures(
                        variant, failed_examples
                    )
                    mutated_instruction = self.reflector.propose_mutation(
                        variant.instruction, diagnosis
                    )
                    new_variants.append(
                        PromptVariant(
                            instruction=mutated_instruction,
                            metadata={
                                "parent": variant.instruction,
                                "diagnosis": diagnosis,
                            },
                        )
                    )

            # 4. Genetic Operators: Crossover
            min_crossover_population = 2
            if len(population) >= min_crossover_population:
                parents = self.gepa.select_parents(population)
                crossed_instruction = self.gepa.crossover(parents[0], parents[1])
                new_variants.append(PromptVariant(instruction=crossed_instruction))

            # 5. Selection: Pareto-Frontier
            all_candidates = population + new_variants
            # For simplicity, we use accuracy as the primary metric here
            population = self.selector.select_frontier(
                all_candidates, metrics=["accuracy"]
            )
            population = population[: self.config.population_size]

        # 6. Final Evaluation on Validation Set
        optimized_agents = []
        for variant in population:
            val_result = await sampler.sample_and_score(
                initial_agent.clone(update={"instruction": variant.instruction}),
                example_set="validation",
                batch=val_ids,
            )
            optimized_agents.append(
                AgentWithScores(
                    optimized_agent=initial_agent.clone(
                        update={"instruction": variant.instruction}
                    ),
                    overall_score=sum(val_result.scores.values())
                    / len(val_result.scores)
                    if val_result.scores
                    else 0.0,
                )
            )

        return OptimizerResult(optimized_agents=optimized_agents)
