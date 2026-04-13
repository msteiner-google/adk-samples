"""Main entrypoint for ADK Agent Evaluations."""

import asyncio
import csv
import json
import pathlib

from loguru import logger

from src.agents.simple_agent import SimpleAgent
from src.eval import run_evaluation


async def main_async() -> None:
    """Demonstrate Topic 1: Golden Dataset and Evaluation Metrics using ADK Agent."""
    logger.info("Starting Topic 1: ADK Agent Evaluation demonstration.")

    # Initialize the Real ADK Agent
    agent = SimpleAgent()

    # Load the Golden Dataset
    try:
        path = pathlib.Path("data/golden_dataset_template.json")
        with path.open("r", encoding="utf-8") as f:
            dataset = json.load(f)
    except FileNotFoundError:
        logger.error("Golden dataset template not found.")
        return

    results = []
    for test_case in dataset["test_cases"]:
        logger.info(f"Evaluating Case: {test_case['id']} - {test_case['description']}")

        # Run the actual agent logic
        agent_output = await agent.run_async(
            query=test_case["input"]["query"],
            file_paths=test_case["input"]["file_paths"],
        )
        actual_result = agent_output["result"]
        actual_routing = agent_output["routing"]
        actual_tool_sequence = agent_output["tool_sequence"]

        # Run evaluation
        scores = run_evaluation(
            test_case, actual_result, actual_routing, actual_tool_sequence
        )

        logger.info(
            f"Result for {test_case['id']}: "
            f"Overall Score = {scores['overall_score']:.2f}"
        )

        # Collect data for CSV
        results.append({
            "test_case_id": test_case["id"],
            "description": test_case["description"],
            "expected_output": json.dumps(
                test_case.get("expected_output", {}), indent=2
            ),
            "actual_result": json.dumps(actual_result, indent=2),
            "actual_routing": actual_routing,
            "actual_tool_sequence": ", ".join(actual_tool_sequence),
            **scores,
        })

    # Summary
    logger.info("Evaluation Complete. Summary:")
    for res in results:
        logger.info(f"- {res['test_case_id']}: {res['overall_score']:.2f}")

    # Write to CSV
    csv_file = "evaluation_results.csv"
    if results:
        keys = results[0].keys()
        with pathlib.Path(csv_file).open("w", newline="", encoding="utf-8") as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
    logger.info(f"Evaluation results saved to {csv_file}")


def main() -> None:
    """Main entrypoint for the evaluation script."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
