# Topic coverage

Maps every topic and deliverable in [topics.md](topics.md) to the code that
implements it, so the state of the project can be read rather than
reconstructed.

`tests/test_topic_coverage.py` checks that every path named here exists. A map
that rots is worse than no map.

**Status at a glance**

| Topic | Status | Where |
| --- | --- | --- |
| 1. Methodology and golden datasets | Done | `data/`, `tests/eval/`, dataset guards |
| 2. Prompt evolution (GEPA) | Done, via the ADK optimizer | `tests/eval/optimizer_config.json`, `make optimize` |
| 3. OCR and complex documents | Done | `layout_aware_agent`, `extraction_metrics.py`, 4 complex cases |
| 4. Self-healing and NL2SQL | Done | `nl2sql_agent`, `sql_runtime.py`, `sql_metrics.py` |
| 5. Automation, batching, scale | Done | `run_batch_eval.py`, `generate_report.py`, CI |
| 6. Thinking tokens and cost | Done | `accounting.py`, `pricing.py`, `thinking_benchmark.py` |

One caveat applies throughout and is not hidden in a footnote: most of this has
been verified by unit tests and by replaying captured data, not by repeated
live runs. See [What has actually run](#what-has-actually-run).

---

## Topic 1: Methodology and golden datasets

| Activity | Where |
| --- | --- |
| Golden dataset templates | `data/golden_dataset_template.json` (10 document cases), `data/nl2sql_golden_dataset.json` (10 SQL cases) |
| Granular accuracy | `src/evaluation/extraction_metrics.py` → `extraction_f1` |
| Schema adherence | `src/evaluation/extraction_metrics.py` → `schema_adherence` |
| Data fidelity | `src/evaluation/sql_metrics.py` → `sql_result_match` |
| Expected routing | `rubric_based_tool_use_quality_v1` in `tests/eval/eval_config.json` |

The datasets are themselves tested, in `tests/eval/test_golden_datasets.py` and
`tests/evaluation/test_nl2sql_dataset.py`. This was not precautionary: two
expected values in `TC007_10K_LAYOUT` disagreed with the 10-K they cite, and
`SQL010`'s average was wrong by hand. Both had been scoring runs.

## Topic 2: Prompt evolution and regression management

| Activity | Where |
| --- | --- |
| Trajectory sampling | ADK's `LocalEvalSampler`, configured by `tests/eval/*sampler_config.json` |
| Reflection loop | ADK's `GEPARootAgentPromptOptimizer`, configured by `tests/eval/optimizer_config.json` |
| Pareto-frontier selection | Same, inside the ADK optimizer |
| Regression management | `src/utils/report.py` → `compare_runs`, and `generate_report.py --fail-on-regression` |

The GEPA half is the library's. What this repo adds is the regression half:
diffing a run against the one before it, and a CI gate that fails on a case
that used to pass. `src/utils/patch.py` works around a crash in ADK's sampler
when a metric produces no score.

## Topic 3: Complex documents

| Activity | Where |
| --- | --- |
| Layout and table evaluation logic | `src/evaluation/extraction_metrics.py` |
| Multimodal test set | `TC007`–`TC010` in `data/golden_dataset_template.json` |
| Extraction accuracy metrics | `extraction_f1` (per-field precision, recall, F1) |
| Layout-aware agent | `src/agents/layout_aware_agent/` (orchestrator, analyst, extractor) |

The four complex cases each target a different failure: a three-year income
statement (`TC007`), a hierarchical table with subtotals (`TC008`), two as-of
columns where the wrong year is the easy mistake (`TC009`), and small decimals
on adjacent rows (`TC010`). Every figure was traced to the source PDF.

Deterministic metrics replaced the `schema_fidelity` rubric. `layout_fidelity`
stays as a rubric, because judging whether a layout was understood is not
something an exact check can do.

## Topic 4: Self-healing and NL2SQL

| Activity | Where |
| --- | --- |
| Self-healing from database errors | `src/agents/nl2sql_agent/agent.py` with ADK's `ReflectAndRetryToolPlugin`; errors raised by `src/utils/sql_runtime.py` |
| Dialect post-processing | `src/utils/sql_dialect.py` (sqlglot, BigQuery to SQLite) |
| Documented patterns | [patterns/nl2sql.md](patterns/nl2sql.md) |
| Measurement | `sql_result_match`, `sql_self_heal_recovery` |

SQLite rather than BigQuery, so the topic stays reproducible and offline.

Two findings from the first live run are worth carrying forward. The custom
metrics scored null on every case, because `intermediate_data` is a union and a
live run supplies a different member than a golden file does; the fix and its
regression test are in `tests/evaluation/test_sql_metrics_live_shape.py`. And
two wrong answers came from case-mismatched filters, which the retry loop
cannot see because the query succeeds; that is Pattern 3b.

## Topic 5: Automation, batching and scale

| Activity | Where |
| --- | --- |
| Batch workflow template | `scripts/run_batch_eval.py`, `make batch` |
| Automatic technical reports | `scripts/generate_report.py`, `src/utils/report.py`, `make report` |
| Performance trends | `compare_runs` diffs the latest run against the previous one |
| CI | `.github/workflows/ci.yml` (free, every PR), `.github/workflows/nightly-eval.yml` (scheduled, paid) |

Reports read only what previous runs left on disk, so they call no model.

## Topic 6: Thinking tokens and cost

| Activity | Where |
| --- | --- |
| Thinking-token analysis | `src/utils/accounting.py`, `src/utils/usage.py` |
| Latency against precision | `scripts/thinking_benchmark.py`, `make bench-thinking` |
| Cost calculator | `src/utils/pricing.py`, `data/model_pricing.json` |
| Budget control | `src/utils/thinking.py`, via `ADK_THINKING_BUDGET` |

Thinking is reported as its own cost line rather than folded into output,
because what reasoning costs is the question. Rates are a checked-in snapshot,
not a live lookup, so runs stay reproducible; the snapshot drifts and its
`_meta` block says so.

---

## Final deliverables

| Deliverable | Where |
| --- | --- |
| Prompt Evolution Engine | `make optimize` over ADK's GEPA optimizer, plus the regression tooling in `src/utils/report.py` |
| Metrics Library | `src/evaluation/` — `extraction_f1`, `schema_adherence`, `sql_result_match`, `sql_self_heal_recovery` |
| Evolved NL2SQL Template | `src/agents/nl2sql_agent/`, `src/utils/sql_runtime.py`, `src/utils/sql_dialect.py`, [patterns/nl2sql.md](patterns/nl2sql.md) |
| Cost Analysis Framework | `src/utils/accounting.py`, `src/utils/pricing.py`, `scripts/thinking_benchmark.py` |

## What has actually run

Being straight about the evidence behind the table above.

**Verified by live run.** One `adk eval` of `nl2sql_agent` over all ten SQL
cases. It is what exposed the null-score bug and the case-sensitivity failures,
and it is the reason to trust live runs over unit tests for anything that
touches ADK's data shapes.

**Verified by replaying captured data.** The SQL metrics, against invocations
lifted verbatim from that run.

**Verified by unit test and by construction only.** Everything else: the
document-extraction metrics, the token accountant, the cost estimator, the
thinking benchmark, the batch runner, the report generator. The report
generator was additionally exercised end to end against synthetic fixtures.

**Not yet run at all.** `make eval-simple`, `make eval-layout`,
`make bench-thinking`, `make batch`, and the nightly workflow.

The honest summary: the plumbing is tested, and one of the two agents that has
met a real model revealed a bug that no unit test could have caught. Expect the
same from the others.

## Known gaps

1. **NL2SQL schema scale.** Three tables. Pasting a whole schema into every
   error message stops working at warehouse scale.
2. **Dialects accepted but never executed.** `sql_dialect.py` reads BigQuery,
   Postgres, MySQL and DuckDB; only the SQLite target is exercised.
3. **Recovery quality is binary.** `sql_self_heal_recovery` records whether the
   agent recovered, not how efficiently.
4. **Cost snapshot drifts.** `data/model_pricing.json` is manual.
5. **Layout fidelity still needs a judge.** No deterministic metric covers
   whether a nested table was structurally understood, only whether the values
   came out right.
