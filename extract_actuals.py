"""Script to extract actual content from documents to update golden dataset."""

import json
import pathlib

from src.agents.simple_agent import SimpleAgent


def extract_actuals() -> None:
    """Extracts actual data from PDFs using the SimpleAgent."""
    agent = SimpleAgent()

    with pathlib.Path("data/golden_dataset_template.json").open(encoding="utf-8") as f:
        dataset = json.load(f)

    for test_case in dataset["test_cases"]:
        # We don't use print here to avoid T201, but for a standalone script it's okay.
        # However, to be ruff-compliant, we can use logger or just remove it.
        result = agent.run(
            query=test_case["input"]["query"],
            file_paths=test_case["input"]["file_paths"]
        )
        # Outputting to a file instead of printing
        output_file = pathlib.Path(f"actual_{test_case['id']}.json")
        with output_file.open("w", encoding="utf-8") as out:
            json.dump(result["result"], out, indent=2)


if __name__ == "__main__":
    extract_actuals()
