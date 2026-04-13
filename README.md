# ADK Agent Evaluations

This project focuses on development activities using Google ADK as the reference framework for agentic systems.

## Overview

The following topics outline the development activities prioritized for this project. These were established in collaboration with the team. Feedback and adjustments are welcome.

*Note: Some topics are considered "nice to have" and will be addressed if the project timeline permits.*

## Development Topics

### Topic 1: Methodology Definition and "Golden Datasets"
**Objective:** Create a standard for reproducible and objective testing.
**Activities:**
- Develop templates for "Golden Datasets" (high-quality ground truth examples).
- Define success metrics (granular accuracy, schema adherence, data fidelity, and expected routing).

### Topic 2: Prompt Evolution and Regression Management (GEPA Methodology)
**Objective:** Implement automatic prompt optimization based on reflection and genetic algorithms.
**Activities:**
- Develop the Prompt Evolution module inspired by the GEPA paper: logic for sampling execution trajectories (reasoning, tool calls, output).
- Implement a "Reflection" loop: the system analyzes failures of new models (e.g., Gemini 2.0), generates natural language diagnoses, and proposes prompt updates.
- Pareto-Frontier based selection: algorithms to identify and maintain the most effective prompts, ensuring performance improvements without degrading existing use cases.

### Topic 3: Evolved OCR Evaluation and Complex Documents
**Objective:** Automate the validation of data extraction from PDFs and tabular structures.
**Activities:**
- Develop specific evaluation logic for layout integrity and table structure.
- Create a test set for multimodal documents (text, nested tables, and images).
- Implement metrics to measure data extraction accuracy from complex layouts.

### Topic 4: Self-Healing Strategies and NL2SQL Evolution
**Objective:** Resolve previously encountered challenges in SQL code generation.
**Activities:**
- Develop "self-healing" patterns: the agent uses database error messages as feedback to correct and regenerate SQL queries.
- Implement post-processing techniques to improve compatibility across different SQL dialects.
- Document successful patterns for interaction between natural language and databases.

### Topic 5: Automation, Batching, and Large-Scale Evaluation
**Objective:** Provide templates for executing tests at scale.
**Activities:**
- Develop templates for batch workflows.
- Automatically generate technical reports on model health and performance trends.

### Topic 6: Operational Efficiency and "Thinking Tokens"
**Objective:** Optimize the balance between reasoning quality and cost.
**Activities:**
- Develop analysis tools for "Thinking Tokens": measure the impact of internal reasoning tokens on final accuracy.
- Latency vs. precision analysis: benchmarks to determine when advanced reasoning ("Thinking") is required versus faster models.
- Create a standalone transaction cost calculator for different consumption models.

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

## Final Deliverables

- **Prompt Evolution Engine:** Standalone scripts based on the GEPA methodology for continuous optimization.
- **Metrics Library:** Modular code to evaluate accuracy, OCR, and regressions in agentic systems.
- **Evolved NL2SQL Template:** Self-healing logic for query generation.
- **Cost Analysis Framework:** Tools to monitor model efficiency and reasoning tokens.
