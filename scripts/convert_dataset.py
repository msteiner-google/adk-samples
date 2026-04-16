"""Module to convert golden datasets to ADK format by embedding files."""

import base64
import json
import mimetypes
import pathlib
from typing import Any


def process_node(node: Any, project_root: pathlib.Path) -> Any:  # noqa: ANN401
    """Recursively processes the JSON tree to embed files and stringify text."""
    if isinstance(node, dict):
        # 1. Handle file embedding: {"file_path": "..."} -> {"inline_data": {...}}
        if "file_path" in node:
            path = project_root / node["file_path"]
            if path.exists():
                mime_type, _ = mimetypes.guess_type(path)
                mime_type = mime_type or "application/octet-stream"
                content = path.read_bytes()
                encoded = base64.b64encode(content).decode("utf-8")
                return {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": encoded,
                    }
                }
            return node

        # 2. Handle text stringification: {"text": {...}} -> {"text": "{...}"}
        # This allows keeping expected JSON output readable in the template.
        if "text" in node and isinstance(node["text"], (dict, list)):
            return {"text": json.dumps(node["text"], indent=2)}

        return {k: process_node(v, project_root) for k, v in node.items()}

    if isinstance(node, list):
        return [process_node(item, project_root) for item in node]

    return node


def convert_to_adk_format(input_path: str, output_path: str) -> None:
    """Converts a template evalset to a full ADK evalset by embedding binaries."""
    input_file = pathlib.Path(input_path)
    if not input_file.exists():
        print(f"Error: Input file not found: {input_path}")  # noqa: T201
        return

    with input_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    project_root = input_file.parent.parent
    processed_data = process_node(data, project_root)

    output_file = pathlib.Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(processed_data, f, indent=2)
    print(f"Successfully generated: {output_path}")  # noqa: T201


if __name__ == "__main__":
    script_dir = pathlib.Path(__file__).parent.resolve()
    project_root = script_dir.parent

    src_data_path = project_root / "data" / "golden_dataset_template.json"
    out_evalset_path = (
        project_root / "tests" / "eval" / "evalsets" / "golden_evalset.json"
    )

    convert_to_adk_format(str(src_data_path), str(out_evalset_path))
