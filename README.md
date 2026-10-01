# ADK Agent Evaluations

This project implements an AI agent using the Google ADK (Agent Development Kit) to extract structured data from bank documents, and includes a custom **GEPA (Genetic Evolutionary Prompt Algorithms)** optimization loop to refine system instructions.

## What This Project Covers

Every development topic and final deliverable is mapped to the code that
implements it in **[docs/topic-coverage.md](docs/topic-coverage.md)**, with an
honest account of what has been verified by a live run and what has only been
unit tested. Start there.

**[docs/topic-examples.md](docs/topic-examples.md)** is the guided tour: for
each topic, what the worked example is, the command to run it, the technique
it demonstrates, and where the limits are. Read that if you are here to learn
from the examples rather than to navigate the code.

For how the project got here, [docs/delivery-log.md](docs/delivery-log.md)
records what each merged PR changed against the baseline it started from, the
reasoning behind the choices, and the bugs found along the way.

## Repository Structure

```
.
├── Makefile                # Entry point for common commands (eval, optimize, batch, report, check)
├── data/
│   ├── golden_dataset_template.json  # Source dataset in ADK format (using local file paths)
│   ├── nl2sql_golden_dataset.json    # NL questions with expected result sets
│   ├── nl2sql_schema.sql   # Schema and seed rows for the NL2SQL database
│   └── model_pricing.json  # Checked-in snapshot of Vertex AI token rates
├── scripts/
│   ├── convert_dataset.py  # Utility to embed local files as base64 and stringify JSON
│   ├── run_batch_eval.py   # Runs the agent x thinking-budget evaluation matrix
│   ├── generate_report.py  # Builds a markdown report with regression detection
│   └── thinking_benchmark.py # Accuracy vs. latency vs. cost across thinking budgets
├── src/
│   ├── agents/
│   │   ├── layout_aware_agent/ # Agent optimized for complex document layouts
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   ├── analyst/        # Specialized sub-agent for layout analysis
│   │   │   └── extractor/      # Specialized sub-agent for data extraction
│   │   ├── nl2sql_agent/       # Self-healing SQL agent over a local SQLite DB
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   └── tools.py        # describe_schema and run_sql_query
│   │   └── simple_agent/       # Baseline agent for standard documents
│   │       ├── __init__.py
│   │       └── agent.py
│   ├── evaluation/
│   │   └── sql_metrics.py  # Custom metrics: result match and self-heal recovery
│   └── utils/
│       ├── accounting.py   # TokenAccountantPlugin: per-agent token and cost capture
│       ├── data_model.py   # Pydantic schemas: StructuredResponse and LayoutMap
│       ├── eval_history.py # Reads the result files adk eval leaves on disk
│       ├── model.py        # Model utilities and geofenced Gemini factory
│       ├── patch.py        # ADK optimization stability patches
│       ├── pricing.py      # Token counts to dollars
│       ├── sql_dialect.py  # Cross-dialect SQL transpilation via sqlglot
│       ├── sql_runtime.py  # In-memory SQLite and the read-only query tool
│       ├── report.py       # Run comparison and markdown rendering
│       ├── thinking.py     # Thinking-budget control via ADK_THINKING_BUDGET
│       └── usage.py        # Token usage accounting primitives
├── tests/
│   ├── eval/
│   │   ├── eval_config.json      # Evaluation criteria and thresholds
│   │   ├── optimizer_config.json # Configuration for the optimization process
│   │   ├── sampler_config.json   # Sampler config for simple_agent
│   │   ├── layout_aware_agent_sampler_config.json # Sampler config for layout_aware_agent
│   │   └── evalsets/             # Generated ADK-compatible evalsets
│   └── utils/                    # Unit tests for the shared utilities
└── pyproject.toml          # Project dependencies and configuration
```

## Evaluation

The project uses the official **ADK Evaluation Framework** to measure agent performance.

### Running Evaluations

To run the evaluation suite for all agents:

```bash
make eval
```

To evaluate a specific agent:

```bash
make eval-simple
# or
make eval-layout
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

To start the optimization process for all agents:

```bash
make optimize
```

To optimize a specific agent:

```bash
make optimize-simple
# or
make optimize-layout
```

This will run the GEPA loop using the built-in ADK optimizer as configured in `tests/eval/optimizer_config.json`,
sampling examples according to the respective sampler configuration file (`sampler_config.json` or `layout_aware_agent_sampler_config.json`). The results will be displayed in the terminal and saved according to the ADK's default behavior.

### Metrics Used

Deterministic metrics come first: they are free, stable between runs, and
fail for a reason you can point at. Judge-based metrics cover what cannot be
checked exactly.

**Deterministic (no model call):**

- **`extraction_f1`**: Per-field precision, recall and F1 over the extracted
  key/value pairs, compared by value. Partial credit, so finding nine of ten
  fields scores better than finding none. Presentation is ignored
  (`net_profit_2024` matches `Net Profit 2024`, `353592` matches `353,592`,
  list order does not matter); meaning is not.
- **`schema_adherence`**: 1.0 when the response parses as `StructuredResponse`
  with every field populated.

**Judge-based:**

- **Semantic Match (`final_response_match_v2`)**: Uses LLM-as-a-judge to verify that the extracted data is semantically correct.
- **Trajectory Analysis (`tool_trajectory_avg_score`)**: Validates that the agent used the expected tools (in any order).
- **Rubric-Based Quality (`rubric_based_final_response_quality_v1`)**: Judges
  layout understanding, which is the part that cannot be checked exactly. The
  former `schema_fidelity` rubric is gone, replaced by `schema_adherence`.

### Trusting the Golden Data

The golden datasets are the measuring instrument, so they are tested too
(`tests/eval/test_golden_datasets.py`, `tests/evaluation/test_nl2sql_dataset.py`).
Every NL2SQL expected result set is re-derived from the real database. The
document cases get structural checks: referenced PDFs exist, ids are unique,
expected answers satisfy the schema the agent is held to.

This matters more than it sounds. Two expected values in `TC007_10K_LAYOUT`
disagreed with the 10-K they cite, so an agent reading the table correctly was
marked wrong on half the case.

## Self-Healing NL2SQL

`nl2sql_agent` answers natural-language questions by writing SQL against a
local SQLite database seeded from `data/nl2sql_schema.sql`. SQLite keeps the
topic reproducible: no project, no credentials, no shared state between runs.

```bash
make eval-nl2sql
```

When a query fails, the tool raises with the database's own error text, the
failed SQL and the live schema attached. ADK's `ReflectAndRetryToolPlugin`
feeds that back to the model, which rewrites the query and tries again, up to
three times. That is the loop Topic 4 asks for.

Model-written SQL is transpiled with `sqlglot` before it runs, so the
BigQuery-flavoured SQL Gemini produces by default (backticks, `SAFE_CAST`,
`project.dataset.table`) works without special prompting.

Two custom metrics score it, both registered in
`tests/eval/nl2sql_eval_config.json`:

- **`sql_result_match`** re-runs the agent's final query and compares result
  sets. Query text is not compared, because many spellings are correct and
  only the rows settle it.
- **`sql_self_heal_recovery`** scores only the cases whose first query failed.
  Cases that never failed are skipped, so easy questions cannot inflate it.

Three of the ten golden cases are built to fail on the first attempt, on a
wrong column name, an unsupported function and a wrong table name, so the
healing loop is exercised rather than assumed.

See [docs/patterns/nl2sql.md](docs/patterns/nl2sql.md) for the patterns, the
trade-offs behind them, and the known limits.

## Batch Evaluation and Reports

`make batch` runs every agent, then writes a markdown report. The matrix can be
widened to cross agents with thinking budgets:

```bash
make batch                                        # every agent, default settings
make batch AGENTS=simple_agent BUDGETS=0,2048     # one agent, two budgets
make batch JOBS=2                                 # two evals in parallel
```

Concurrency defaults to 1 because each job calls a paid API against a shared
project quota.

`make report` builds the report on its own from results already on disk. It
calls no model, so it is free to re-run:

```bash
make report
uv run python scripts/generate_report.py --fail-on-regression   # CI gate
```

The report leads with **regressions**: cases that passed in the previous run and
fail in the current one. It also carries per-metric score deltas, per-case
results, and token and cost totals per agent. Reports land in `reports/`, which
is gitignored.

## Cost and Thinking Tokens

Every agent runs with a `TokenAccountantPlugin` that records token usage per
agent and per model to `reports/token_usage.jsonl`, costed against the rate
table in `data/model_pricing.json`.

Thinking tokens are reported as their own line rather than folded into output,
because the question Topic 6 asks is what reasoning costs. To measure whether it
pays for itself:

```bash
make bench-thinking BUDGETS=0,2048,-1
```

That runs the evalset once per budget (`0` disables thinking, `-1` lets the
model decide) and prints accuracy, latency, tokens and dollars side by side.

> **Note on rates:** `data/model_pricing.json` is a checked-in snapshot of
> published Vertex AI pricing, not a live lookup, so that eval runs stay
> reproducible and offline. It drifts. Re-check the source in its `_meta` block
> before quoting a figure externally.

## Continuous Integration

- `.github/workflows/ci.yml` runs on every pull request: lint, tests, evalset
  conversion and a dry run of the batch and report scripts. No model is called
  and no credentials are needed.
- `.github/workflows/nightly-eval.yml` runs the matrix on a schedule, uploads
  the report as an artifact, and fails on a regression. It skips itself when
  Google Cloud credentials are not configured.

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
