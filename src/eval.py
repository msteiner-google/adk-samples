"""Evaluation module for ADK Agent Evaluations."""

from typing import Any


class EvalMetrics:
    """Class containing static methods for evaluation metrics."""

    @staticmethod
    def granular_accuracy(expected: dict[str, Any], actual: dict[str, Any]) -> float:
        """Calculate granular accuracy between expected and actual outputs."""
        if not expected:
            return 1.0
        matches = 0
        total_fields = 0
        for key, expected_val in expected.items():
            if key in {"routing", "sequence_of_tools"} or key.endswith("_found"):
                continue  # Special/Helper fields in expected output

            total_fields += 1
            if key in actual:
                if isinstance(expected_val, list):
                    if isinstance(actual[key], list) and len(actual[key]) > 0:
                        matches += 1
                elif actual[key] == expected_val or (
                    isinstance(expected_val, str)
                    and isinstance(actual[key], str)
                    and (
                        expected_val.lower() in actual[key].lower()
                        or actual[key].lower() in expected_val.lower()
                    )
                ):
                    matches += 1

        return matches / total_fields if total_fields > 0 else 1.0

    @staticmethod
    def schema_adherence(actual: dict[str, Any], schema: dict[str, Any]) -> float:
        """Verify that the actual output adheres to the specified schema."""
        required_fields = schema.get("required", [])
        if not required_fields:
            return 1.0
        for field in required_fields:
            if field not in actual:
                return 0.0
        return 1.0

    @staticmethod
    def data_fidelity(actual: dict[str, Any]) -> float:
        """Check the fidelity of the actual data output."""
        if not actual:
            return 0.0
        for val in actual.values():
            if val is None or not val:
                return 0.5
        return 1.0

    @staticmethod
    def tool_sequence_accuracy(
        actual_sequence: list[str], expected_sequence: list[str]
    ) -> float:
        """Calculate the accuracy of the tool call sequence."""
        if not expected_sequence:
            return 1.0 if not actual_sequence else 0.0
        if not actual_sequence:
            return 0.0

        # Simple comparison: check if all expected tools are present in order
        # (Could be more sophisticated, e.g., Levenshtein distance)
        if actual_sequence == expected_sequence:
            return 1.0

        # Partial credit if it contains the expected tools in any order
        matches = sum(1 for t in expected_sequence if t in actual_sequence)
        return (matches / len(expected_sequence)) * 0.5

    @staticmethod
    def expected_routing(actual_routing: str, expected_routing: str) -> float:
        """Check if the actual routing matches the expected routing."""
        return 1.0 if actual_routing == expected_routing else 0.0


def run_evaluation(
    test_case: dict[str, Any],
    actual_result: dict[str, Any],
    actual_routing: str,
    actual_tool_sequence: list[str],
) -> dict[str, float]:
    """Run evaluation for a single test case.

    Args:
        test_case: The test case dictionary.
        actual_result: The result from the agent.
        actual_routing: The routing used by the agent.
        actual_tool_sequence: The sequence of tools called by the agent.

    Returns:
        A dictionary containing the scores.
    """
    expected_output = test_case.get("expected_output", {})
    schema = test_case.get("schema", {})
    expected_route = expected_output.get("routing", "extraction_agent")
    expected_tool_sequence = expected_output.get("sequence_of_tools", [])

    scores = {
        "accuracy": EvalMetrics.granular_accuracy(expected_output, actual_result),
        "schema_adherence": EvalMetrics.schema_adherence(actual_result, schema),
        "data_fidelity": EvalMetrics.data_fidelity(actual_result),
        "routing_score": EvalMetrics.expected_routing(actual_routing, expected_route),
        "tool_sequence_score": EvalMetrics.tool_sequence_accuracy(
            actual_tool_sequence, expected_tool_sequence
        ),
    }

    scores["overall_score"] = sum(scores.values()) / len(scores)
    return scores
