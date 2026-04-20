"""Reflection loop for automated prompt diagnosis and refinement."""

from typing import TYPE_CHECKING, Any

from src.utils.model import get_geofenced_gemini_model

if TYPE_CHECKING:
    from src.optimization.base import PromptVariant


class Reflector:
    """Uses a judge model to analyze agent failures and suggest prompt improvements."""

    def __init__(self, model_name: str = "gemini-2.5-flash") -> None:
        """Initializes the Reflector.

        Args:
            model_name: The name of the Gemini model to use for reflection.
        """
        self.model = get_geofenced_gemini_model(model=model_name)

    def diagnose_failures(
        self, variant: PromptVariant, failed_examples: list[dict[str, Any]]
    ) -> str:
        """Analyzes a set of failed execution trajectories to identify common issues."""
        if not failed_examples:
            return "No failures identified."

        prompt = (
            "Analyze the following failed execution trajectories for an agent. "
            "Identify why the agent failed and provide a concise diagnosis in "
            "natural language. Focus on systemic issues that could be fixed by "
            "updating the system instruction.\n\n"
            f"Current Instruction: {variant.instruction}\n\n"
            "Failures:\n"
        )

        max_failures_to_analyze = 3
        for i, failure in enumerate(failed_examples[:max_failures_to_analyze]):
            prompt += f"--- Failure {i + 1} ---\n"
            prompt += f"Input: {failure.get('input', 'N/A')}\n"
            prompt += f"Expected: {failure.get('expected', 'N/A')}\n"
            prompt += f"Actual: {failure.get('actual', 'N/A')}\n"
            prompt += f"Trajectory: {failure.get('trajectory', 'N/A')}\n\n"

        response = self.model.generate_content(prompt)
        return response.text

    def propose_mutation(self, current_instruction: str, diagnosis: str) -> str:
        """Generates a mutated version of the instruction based on a diagnosis."""
        prompt = (
            "You are an expert prompt engineer. Your goal is to improve an agent's "
            "system instruction based on a diagnosis of its recent failures. "
            "Provide the full updated instruction that addresses the identified "
            "issues while maintaining the agent's core capabilities.\n\n"
            f"Current Instruction: {current_instruction}\n\n"
            f"Diagnosis: {diagnosis}\n\n"
            "New Instruction:"
        )

        response = self.model.generate_content(prompt)
        return response.text.strip()
