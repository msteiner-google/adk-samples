# Worked examples, by topic

A guided tour of this repository for the six development topics in
[topics.md](topics.md). Each section says what the example is, how to run it,
what technique it demonstrates, and where the honest limits are.

The repository is a set of **worked examples**, not a product. The value is in
the patterns and the trade-offs behind them, which are written down next to
the code rather than left to be inferred.

**Three documents, three questions:**

| Document | Answers |
| --- | --- |
| This one | How is each topic demonstrated, and how do I run it? |
| [topic-coverage.md](topic-coverage.md) | Which file implements which activity? |
| [delivery-log.md](delivery-log.md) | What changed, in what order, and why? |

---

## Before running anything

### Configuration

Both variables are read in `src/utils/model.py`:

```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=europe-west4   # any Vertex AI region
```

> **Set `GOOGLE_CLOUD_PROJECT` before your first run.** The fallback in
> `src/utils/model.py` is a development project you will not have access to,
> so leaving it unset produces a permission error rather than a clear message.

Then authenticate for Vertex AI and install:

```bash
gcloud auth application-default login
uv sync
```

### What costs money

Half the commands call Gemini. The other half read artefacts already on disk
and are free to run as often as you like, which is deliberate: the expensive
feedback loop should not be the only one available.

| Free | Paid |
| --- | --- |
| `make check` — lint | `make eval-simple` |
| `make test` — 239 tests | `make eval-layout` |
| `make convert` — build evalsets | `make eval-nl2sql` |
| `make report` — build the report | `make bench-thinking` |
| | `make batch`, `make optimize` |

A good first command is `make test`. It exercises the metrics, the cost
model, the SQL runtime and the self-healing loop without a single API call.

---

## Topic 1 — Methodology and golden datasets

> **Objective:** create a standard for reproducible and objective testing.

### The example

Two golden datasets in the standard ADK EvalSet schema:
`data/golden_dataset_template.json` (10 document-extraction cases) and
`data/nl2sql_golden_dataset.json` (10 natural-language-to-SQL cases).

`scripts/convert_dataset.py` turns a readable template into the evalset ADK
consumes, embedding PDFs as base64 and stringifying expected JSON, so the
source stays reviewable in a pull request.

### Run it

```bash
make convert   # free
```

### What it demonstrates

**Keep the authored form and the machine form separate.** The template is
written to be read and reviewed; the evalset is generated. You never hand-edit
a file with a megabyte of base64 in it.

**Test the dataset, not just the code.** This is the technique most worth
taking away. A golden dataset is a measuring instrument, and when it is wrong
every score derived from it is wrong while everything still looks green.
`tests/eval/test_golden_datasets.py` and
`tests/evaluation/test_nl2sql_dataset.py` check that referenced documents
exist, ids are unique, expected answers satisfy the schema the agent is held
to, and — for the SQL cases, where it is possible — that every expected result
set is reproducible from the real database.

That is not a precaution. Building this repo turned up two expected values
that disagreed with their own source, and both had been scoring runs for as
long as they existed.

### Limits

Document cases get structural checks only. Confirming that a figure is right
needs the source PDF and a human, and no test substitutes for that.

---

## Topic 2 — Prompt evolution and regression management

> **Objective:** implement automatic prompt optimization based on reflection
> and genetic algorithms.

### The example

The GEPA loop is ADK's own `GEPARootAgentPromptOptimizer`, configured by
`tests/eval/optimizer_config.json` and the per-agent sampler configs. Sampling,
reflection, mutation and Pareto-frontier selection are all the library's.

What this repo adds is the **regression half**: `src/utils/report.py` diffs a
run against the previous one and names what broke.

### Run it

```bash
make optimize-simple   # paid
make report            # free
```

### What it demonstrates

**Use the framework's optimizer.** Reimplementing genetic prompt search is a
large amount of work to arrive at what the library already does.

**Optimization without regression detection is unsafe.** A prompt that lifts
the average can quietly destroy a case that used to pass. The report leads
with regressions because that is the only section demanding action, and
`generate_report.py --fail-on-regression` turns it into a build gate.

**Distinguish noise from movement.** Metric changes below a threshold render
as `~`. LLM-judged scores jitter between identical runs, and a report that
treats a 0.003 drift as a trend trains people to ignore it.

**A new or removed case is never a regression.** Adding a failing test case
must not look like something broke.

### Limits

`src/utils/patch.py` works around a crash in ADK's sampler when a metric
produces no score. Check whether it is still needed when you upgrade ADK.

---

## Topic 3 — Complex documents and tables

> **Objective:** automate the validation of data extraction from PDFs and
> tabular structures.

### The example

`src/agents/layout_aware_agent/` splits the job in two: an analyst that maps
the page structure into a `LayoutMap`, and an extractor that pulls values
using that map. `src/agents/simple_agent/` is the single-shot baseline to
compare against.

Four cases run against a real 99-page 10-K, each targeting a different way
table extraction fails: a three-year income statement, a hierarchical table
with subtotals, two as-of columns where the wrong year is the easy mistake,
and small decimals on adjacent rows.

### Run it

```bash
make eval-layout   # paid
make eval-simple   # paid, the baseline to compare against
```

### What it demonstrates

**Deterministic metrics where an exact check is possible.**
`src/evaluation/extraction_metrics.py` provides `extraction_f1` and
`schema_adherence`. They are free, stable between runs, and specific about
what failed. Keep the LLM judge for what genuinely needs judgement — here,
whether a layout was *understood* — and stop paying it to check things a
comparison can decide.

**Score with F1, not exact match.** Nine fields of ten is meaningfully better
than none, and a metric that cannot tell those apart cannot drive
optimization. Precision is in there too, so inventing fields costs something;
recall alone would reward it.

**Compare meaning, not presentation.** `net_profit_2024` matches
`Net Profit 2024`. `353592` matches `"353,592"`. A list of risk factors
matches the same list reordered. Getting this wrong makes a correct
extraction fail, which is worse than no metric: it sends you debugging a
working agent.

### Limits

No deterministic metric covers whether a nested table was *structurally*
understood, only whether the values came out right. An agent that reads the
correct numbers for the wrong reason scores the same as one that understood
the hierarchy.

---

## Topic 4 — Self-healing and NL2SQL

> **Objective:** resolve previously encountered challenges in SQL code
> generation.

### The example

`src/agents/nl2sql_agent/` answers questions about a small banking database
by writing SQL. The database is SQLite, seeded from `data/nl2sql_schema.sql`,
so the whole example runs offline with no warehouse and no credentials beyond
the model.

When a query fails, the tool raises with the database's own error text, the
SQL that failed, and the live schema attached. ADK's
`ReflectAndRetryToolPlugin` feeds that back and the agent rewrites the query,
up to three attempts.

Three of the ten cases are built to fail on the first attempt, each on a
different cause, so the loop is exercised rather than assumed.

### Run it

```bash
make eval-nl2sql   # paid
```

### What it demonstrates

This is the richest example in the repo, and
[patterns/nl2sql.md](patterns/nl2sql.md) covers all six patterns in full. The
three most transferable:

**The error message is the product.** It is not a log line; it is the input to
the next model turn, and the only thing between a failed query and a correct
one. Pass the engine's own wording through verbatim — `no such column:
customer_nmae` names the typo, while a tidy "Invalid column reference" throws
away the useful part. Attach the schema, or the model's next attempt is
another guess.

**Transpile, don't regex.** Gemini writes BigQuery SQL by default.
`src/utils/sql_dialect.py` parses it with `sqlglot` and emits SQLite rather
than patching strings. Regex rewriting of SQL fails silently on quoting and
nesting, and a silent miscorrection is worse than an honest error when the
honest error is what drives the retry.

**Grade the rows, not the SQL.** Many different queries are correct. Text
comparison fails them, and an LLM judge reading SQL grades whether it *looks*
right. `sql_result_match` re-runs the query and compares result sets.

**A silent failure needs a voice.** The sharpest lesson came from a real run:
two wrong answers came from filtering on `'Travel'` where the data holds
`'travel'`. Those queries *succeeded* and returned nothing, so there was no
exception for the retry loop to catch. Self-healing keyed on exceptions only
covers failures loud enough to raise. Ask what a silent wrong answer looks
like in your domain and make it speak.

### Limits

The schema is three tables. Pasting a whole schema into every error message
stops working at warehouse scale; retrieving the relevant subset is the next
step. `sql_dialect.py` accepts BigQuery, Postgres, MySQL and DuckDB as
sources, but only the SQLite target is exercised.

---

## Topic 5 — Automation, batching and scale

> **Objective:** provide templates for executing tests at scale.

### The example

`scripts/run_batch_eval.py` expands agents against thinking budgets into a
matrix and runs each cell as its own subprocess.
`scripts/generate_report.py` turns the results into a markdown report.
Two GitHub Actions workflows wire it up.

### Run it

```bash
make batch                                      # paid
make batch AGENTS=simple_agent BUDGETS=0,2048   # paid, narrower
make report                                     # free
```

### What it demonstrates

**Separate running from reporting.** The report reads only what previous runs
left on disk, so it calls no model and can be regenerated freely while you
iterate on its format. Coupling the two would make every formatting change
cost an eval run.

**Split CI by cost.** `ci.yml` needs no credentials and runs on every pull
request. `nightly-eval.yml` is scheduled, skips itself when credentials are
absent rather than failing with an auth error that reads like a bug, and
uploads its report *before* the regression gate can fail the run — so the
evidence survives the failure.

**Put the cheap check in the cheap job.** Evalset conversion runs in CI, so a
broken template is caught before anyone pays for an eval.

**Make expensive concurrency opt-in.** Batch parallelism defaults to 1,
because the jobs bill against a shared quota.

### Limits

`make batch` and the nightly workflow have not been executed end to end
against a live model.

---

## Topic 6 — Thinking tokens and cost

> **Objective:** optimize the balance between reasoning quality and cost.

### The example

A `TokenAccountantPlugin` on every agent records usage per agent and per
model to `reports/token_usage.jsonl`, costed against a rate table in
`data/model_pricing.json`. `scripts/thinking_benchmark.py` sweeps the thinking
budget and reports accuracy against latency and dollars.

### Run it

```bash
make bench-thinking BUDGETS=0,2048,-1   # paid
```

`0` disables thinking, `-1` lets the model decide. The output is one row per
budget: pass rate, latency, prompt and output and thinking tokens, and cost.

### What it demonstrates

**Report reasoning as its own cost line.** Folding thinking into output
answers a different question. The whole point is to see what reasoning costs
you, per agent, so you can decide where it earns its keep.

**Get the token arithmetic right.** Two relationships are easy to invert and
both change the number materially: `thoughts_token_count` is *not* inside
`candidates_token_count`, so billable output is their sum; and
`cached_content_token_count` *is* inside `prompt_token_count`, so full-price
input is the difference. Both are pinned by tests in `tests/utils/`.

**Pin your prices, don't fetch them.** `data/model_pricing.json` is a
checked-in snapshot, so a run is reproducible and works offline. It drifts,
and its `_meta` block says so. A cost figure that silently changes between two
runs is worse than one that is explicitly stale.

**Keep the measurement when the interpretation fails.** A model missing from
the rate table still records its tokens, with the dollar fields empty.

### Limits

The rate table is maintained by hand. Re-check it against the published
pricing before quoting a figure externally.

---

## Final deliverables

| Deliverable | Where |
| --- | --- |
| Prompt Evolution Engine | `make optimize` over ADK's GEPA optimizer, plus regression detection in `src/utils/report.py` |
| Metrics Library | `src/evaluation/` — `extraction_f1`, `schema_adherence`, `sql_result_match`, `sql_self_heal_recovery` |
| Evolved NL2SQL Template | `src/agents/nl2sql_agent/`, `src/utils/sql_runtime.py`, `src/utils/sql_dialect.py`, [patterns/nl2sql.md](patterns/nl2sql.md) |
| Cost Analysis Framework | `src/utils/accounting.py`, `src/utils/pricing.py`, `scripts/thinking_benchmark.py` |

---

## Adapting this to your own domain

The four pieces that transfer with the least change:

1. **The custom metric pattern.** `src/evaluation/` shows how to register a
   deterministic metric with ADK through `custom_metrics` in the eval config.
   Any domain where correctness can be checked exactly should prefer this to
   an LLM judge: cheaper, stable, and specific about what failed.
2. **The self-healing tool contract.** A tool that raises with the
   environment's own error text, plus the context needed to correct it, works
   for any API with meaningful errors — not just databases.
3. **The cost plugin.** `TokenAccountantPlugin` is domain-agnostic. Point it
   at your own rate table.
4. **The dataset guard tests.** The cheapest high-value thing here. Whatever
   your domain, assert that your golden data is internally consistent and
   reachable from your source of truth.

## Status and evidence

Stated plainly, because an example you cannot calibrate is hard to trust.

**Verified by a live run:** `make eval-nl2sql`, across all ten SQL cases.
That run immediately surfaced a bug that the unit tests had not, which is the
single most useful finding here: for anything touching the framework's data
shapes, one live run is worth more than a suite of hand-built fixtures.

**Verified by unit test and by replaying captured data:** everything else.
239 tests, no network.

**Not yet executed:** `make eval-simple`, `make eval-layout`,
`make bench-thinking`, `make batch`, and the nightly workflow. The
document-extraction metrics and the cost tooling have not seen a live model
response.

The known gaps are listed in
[topic-coverage.md](topic-coverage.md#known-gaps).
