# ADK Agent Evaluations

This project implements an AI agent using the Google ADK (Agent Development Kit) to extract structured data from bank documents.

## Repository Structure

```
.
├── Makefile                # Entry point for common commands (eval, convert, check)
├── data/
│   └── golden_dataset_template.json  # Source dataset in ADK format (using local file paths)
├── scripts/
│   └── convert_dataset.py  # Utility to embed local files as base64 and stringify JSON
├── src/
│   └── agents/
│       └── simple_agent/
│           ├── __init__.py # Module initialization (exposes agent)
│           └── agent.py     # Root agent definition and logic
├── tests/
│   └── eval/
│       ├── eval_config.json # Evaluation criteria and thresholds
│       └── evalsets/        # Generated ADK-compatible evalsets (with embedded binaries)
└── pyproject.toml          # Project dependencies and configuration
```

## Evaluation

The project uses the official **ADK Evaluation Framework** to measure agent performance.

### Running Evaluations

To run the evaluation suite:

```bash
make eval
```

**Note on Template Format:** To ensure transparency and ease of maintenance, the source dataset in `data/golden_dataset_template.json` follows the standard **ADK EvalSet schema**. 

The `make eval` command automatically runs `scripts/convert_dataset.py`, which performs two key tasks:
1. **Binary Embedding**: Replaces `{"file_path": "path/to/file"}` with base64-encoded `inline_data`.
2. **JSON Stringification**: Automatically converts structured JSON objects in `text` fields into strings, allowing the template to remain readable while meeting ADK's strict string requirement for model responses.

### Reproducibility vs. Production

To maximize **reproducibility** in this environment, we use local PDF files stored in `data/` and embed them into the evalsets as base64 strings during the conversion process.

In a **production setting**, it is recommended to host multimodal assets on **Google Cloud Storage (GCS)**. This avoids heavy JSON files and leverages Vertex AI's ability to read directly from GCS URIs.

To use GCS in your `golden_dataset_template.json`, you would replace the `file_path` entries with `file_uri`:

```json
{
  "user_content": {
    "parts": [
      { "text": "Extract data from this file" },
      { "file_uri": "gs://your-bucket-name/bank-statements/statement_01.pdf", "mime_type": "application/pdf" }
    ]
  }
}
```

### Metrics Used

- **Semantic Match (`final_response_match_v2`)**: Uses LLM-as-a-judge to verify that the extracted data is semantically correct.
- **Trajectory Analysis (`tool_trajectory_avg_score`)**: Validates that the agent used the expected tools (in any order).
- **Rubric-Based Quality (`rubric_based_final_response_quality_v1`)**: Enforces strict schema fidelity and penalizes missing fields or null values.

### Adding New Test Cases

Add your test case to `data/golden_dataset_template.json` using the standard ADK format:

```json
{
  "eval_id": "new_test_case",
  "conversation": [
    {
      "user_content": {
        "parts": [
          { "text": "Extract data from this file" },
          { "file_path": "data/your_document.pdf" }
        ]
      },
      "final_response": {
        "role": "model",
        "parts": [
          { "text": { "expected": "json_output" } }
        ]
      }
    }
  ]
}
```
