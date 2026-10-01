"""Module to convert golden datasets to ADK format by embedding files."""

import base64
import json
import mimetypes
import os
import pathlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


def process_node(node: Any, project_root: pathlib.Path) -> Any:  # ruff: ignore[any-type]
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


def discover_agent_dirs(project_root: pathlib.Path) -> list[pathlib.Path]:
    """Returns every agent package under src/agents (one containing agent.py)."""
    agents_root = project_root / "src" / "agents"
    if not agents_root.is_dir():
        return []
    return sorted(d for d in agents_root.iterdir() if (d / "agent.py").is_file())


def link_evalset_into_agents(
    output_file: pathlib.Path,
    project_root: pathlib.Path,
    agent_names: Sequence[str] | None = None,
) -> None:
    """Symlinks a generated evalset next to the agents that use it.

    `adk optimize` resolves `train_eval_set` by id, so it looks for
    `<eval_set_id>.evalset.json` beside the agent module.

    `agent_names` is None for a dataset every agent shares, in which case
    the targets are derived from the filesystem. Naming agents explicitly
    keeps an agent-specific evalset, such as the NL2SQL one, from appearing
    beside agents that cannot run it.
    """
    targets = (
        [project_root / "src" / "agents" / name for name in agent_names]
        if agent_names is not None
        else discover_agent_dirs(project_root)
    )

    link_name = f"{output_file.stem}.evalset.json"
    for agent_dir in targets:
        if not agent_dir.is_dir():
            print(f"Skipping missing agent dir: {agent_dir}")
            continue
        link_path = agent_dir / link_name
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(os.path.relpath(output_file, agent_dir))
        print(f"Created symlink: {link_path}")


def convert_to_adk_format(
    input_path: str, output_path: str, agent_names: Sequence[str] | None = None
) -> None:
    """Converts a template evalset to a full ADK evalset by embedding binaries."""
    input_file = pathlib.Path(input_path)
    if not input_file.exists():
        print(f"Error: Input file not found: {input_path}")
        return

    with input_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    project_root = input_file.parent.parent
    processed_data = process_node(data, project_root)

    output_file = pathlib.Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(processed_data, f, indent=2)
    print(f"Successfully generated: {output_path}")

    link_evalset_into_agents(output_file, project_root, agent_names)


#: Each dataset, where its evalset is written, and which agents get a link.
#: None means every agent, for a dataset they all share.
DATASETS: tuple[tuple[str, str, Sequence[str] | None], ...] = (
    (
        "golden_dataset_template.json",
        "golden_evalset.json",
        ("simple_agent", "layout_aware_agent"),
    ),
    ("nl2sql_golden_dataset.json", "nl2sql_evalset.json", ("nl2sql_agent",)),
)


if __name__ == "__main__":
    script_dir = pathlib.Path(__file__).parent.resolve()
    project_root = script_dir.parent
    evalsets_dir = project_root / "tests" / "eval" / "evalsets"

    for source_name, output_name, agents in DATASETS:
        convert_to_adk_format(
            str(project_root / "data" / source_name),
            str(evalsets_dir / output_name),
            agents,
        )
