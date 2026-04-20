# ADK Agent Evaluations

This project implements an AI agent using the Google ADK (Agent Development Kit) to extract structured data from bank documents, and includes a custom **GEPA (Genetic Evolutionary Prompt Algorithms)** optimization loop to refine system instructions.

## Repository Structure

```
.
├── Makefile                # Entry point for common commands (eval, optimize, convert, check)
├── data/
│   └── golden_dataset_template.json  # Source dataset in ADK format (using local file paths)
├── scripts/
│   └── convert_dataset.py  # Utility to embed local files as base64 and stringify JSON
├── src/
│   ├── agents/
│   │   └── simple_agent/
│   │       ├── __init__.py # Module initialization
│   │       ├── _patch.py    # Monkeypatch for ADK LocalEvalSampler crash
│   │       ├── agent.py     # Root agent definition and logic
│   │       └── wrapper.py   # Wrapper for optimization support
│   └── utils/
│       └── model.py        # Model utilities and geofenced Gemini factory
├── tests/
│   └── eval/
│       ├── eval_config.json      # Evaluation criteria and thresholds
│       ├── optimizer_config.json # Configuration for the optimization process
│       ├── sampler_config.json   # Sampler configuration for training/validation
│       └── evalsets/             # Generated ADK-compatible evalsets
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

The `make eval` command automatically runs `scripts/convert_dataset.py`, which performs binary embedding and JSON stringification for the `text` fields.

## Prompt Optimization (GEPA)

The project leverages the official **GEPA (Genetic Evolutionary Prompt Algorithms)** optimizer provided by the ADK library (`GEPARootAgentPromptOptimizer`), which automates the refinement of the agent's system instruction based on empirical performance.

### How it Works

The optimization loop follows these phases in each iteration:

1.  **Sampling**: The current population of prompt variants is evaluated against the training set.
2.  **Reflection**: An LLM "Reflector" analyzes execution trajectories of failed cases to diagnose systemic issues.
3.  **Mutation**: The Reflector proposes new instruction variants that specifically address the identified failures.
4.  **Crossover**: Genetic operators combine successful parts of different prompt variants to create new candidates.
5.  **Selection**: Identifying the "non-dominated" set of variants based on performance metrics, keeping the population size stable.

### Running Optimization

To start the optimization process:

```bash
make optimize
```

This will run the GEPA loop using the built-in ADK optimizer as configured in `tests/eval/optimizer_config.json`,
sampling examples according to `tests/eval/sampler_config.json`. The results will be displayed in the terminal
and saved according to the ADK's default behavior.

### Metrics Used

- **Semantic Match (`final_response_match_v2`)**: Uses LLM-as-a-judge to verify that the extracted data is semantically correct.
- **Trajectory Analysis (`tool_trajectory_avg_score`)**: Validates that the agent used the expected tools (in any order).
- **Rubric-Based Quality (`rubric_based_final_response_quality_v1`)**: Enforces strict schema fidelity and penalizes missing fields or null values.

## Reproducibility vs. Production

To maximize **reproducibility** in this environment, we use local PDF files stored in `data/` and embed them into the evalsets as base64 strings during the conversion process.

In a **production setting**, it is recommended to host multimodal assets on **Google Cloud Storage (GCS)**. This avoids heavy JSON files and leverages Vertex AI's ability to read directly from GCS URIs.

To use GCS in your `golden_dataset_template.json`, you would replace the `file_path` entries with `file_uri`:

```json
{
  "user_content": {
    "parts": [
      { "text": "Extract data from this file" },
      {
        "file_uri": "gs://your-bucket-name/bank-statements/statement_01.pdf",
        "mime_type": "application/pdf"
      }
    ]
  }
}
```

## Adding New Test Cases

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
        "parts": [{ "text": { "expected": "json_output" } }]
      }
    }
  ]
}
```
