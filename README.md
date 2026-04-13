# ADK Agent Evaluations

This project implements an AI agent using the Google ADK (Agent Development Kit) to extract structured data from bank documents.

## Repository Structure

```
.
├── Makefile                # Entry point for common commands (eval, convert, check)
├── data/
│   └── golden_dataset_template.json  # Source dataset with local file paths
├── scripts/
│   └── convert_dataset.py  # Utility to convert template dataset to ADK format
├── src/
│   └── agents/
│       └── simple_agent/
│           ├── __init__.py # Module initialization (exposes agent)
│           └── agent.py     # Root agent definition and logic
├── tests/
│   └── eval/
│       ├── eval_config.json # Evaluation criteria and thresholds
│       └── evalsets/        # Generated ADK-compatible evalsets
└── pyproject.toml          # Project dependencies and configuration
```

## Evaluation

The project uses the official **ADK Evaluation Framework** to measure agent performance.

### Running Evaluations

To run the evaluation suite:

```bash
make eval
```

**Note on Multimodal Data:** The ADK CLI requires multimodal content (PDFs) to be base64-encoded within the `evalset.json`. To keep the repository clean, we store local file paths in `data/golden_dataset_template.json`. The `make eval` command automatically runs a conversion script (`scripts/convert_dataset.py`) to generate the heavy ADK-compatible `golden_evalset.json` before execution.

### Metrics Used

- **Semantic Match (`final_response_match_v2`)**: Uses LLM-as-a-judge to verify that the extracted data is semantically correct.
- **Trajectory Analysis (`tool_trajectory_avg_score`)**: Validates that the agent used the expected tools (in any order).
- **Rubric-Based Quality (`rubric_based_final_response_quality_v1`)**: Enforces strict schema fidelity and penalizes missing fields or null values.

### Adding New Test Cases

1. Add your test case to the source dataset in `data/golden_dataset_template.json`.
2. Convert the dataset to ADK format:
   ```bash
   make convert
   ```
3. Run the evaluation again with `make eval`.
