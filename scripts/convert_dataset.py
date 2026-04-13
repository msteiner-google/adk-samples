"""Module to convert golden datasets to ADK format."""

import base64
import json
import pathlib


def convert_to_adk_format(input_path: str, output_path: str) -> None:
    """Converts a custom golden dataset to an ADK-compatible evalset.

    Args:
        input_path: Path to the source golden dataset JSON.
        output_path: Path where the generated ADK evalset should be saved.
    """
    input_file = pathlib.Path(input_path)
    if not input_file.exists():
        return

    with input_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    eval_set = {
        "eval_set_id": "golden_evalset",
        "name": "Golden Eval Set",
        "description": "Automatically generated from golden_dataset_template.json",
        "eval_cases": [],
    }

    for case in data["test_cases"]:
        eval_case = {
            "eval_id": case["id"],
            "conversation": [],
        }

        parts = [{"text": case["input"]["query"]}]

        for file_path in case["input"]["file_paths"]:
            path = pathlib.Path(file_path)
            if path.exists():
                content = path.read_bytes()
                encoded = base64.b64encode(content).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": encoded,
                    }
                })

        # Extract expected output and tool sequence
        expected_output = case.get("expected_output", {}).copy()
        expected_tool_sequence = expected_output.pop("sequence_of_tools", [])

        final_response_text = json.dumps(expected_output, indent=2)

        invocation = {
            "invocation_id": "inv_1",
            "user_content": {"parts": parts},
            "final_response": {
                "role": "model",
                "parts": [{"text": final_response_text}],
            },
            "intermediate_data": {
                "tool_uses": [
                    {"name": tool, "args": {}} for tool in expected_tool_sequence
                ]
            },
        }

        eval_case["conversation"].append(invocation)
        eval_set["eval_cases"].append(eval_case)

    output_file = pathlib.Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(eval_set, f, indent=2)


if __name__ == "__main__":
    # Ensure paths are relative to project root
    script_dir = pathlib.Path(__file__).parent.resolve()
    project_root = script_dir.parent

    src_data_path = project_root / "data" / "golden_dataset_template.json"
    out_evalset_path = (
        project_root / "tests" / "eval" / "evalsets" / "golden_evalset.json"
    )

    convert_to_adk_format(str(src_data_path), str(out_evalset_path))
