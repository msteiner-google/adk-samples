# Delivery log

What each merged PR added, measured against the baseline at commit `6b690a9`
("Update deps"), the last state before this series.

For *where a topic lives now*, read [topic-coverage.md](topic-coverage.md).
This document is the other question: **what changed, and why**. It is a record
of a delivery, so it does not get updated as the repo moves on.

## Baseline

| | At `6b690a9` | After #6 |
| --- | --- | --- |
| Agents | 2 | 3 |
| Modules under `src/` | 14 | 28 |
| Test files | 1 | 17 |
| Tests | 2 | 239 |
| Custom metrics | 0 | 4 |
| `make` targets | 8 | 14 |
| CI | none | 2 workflows |

Totals across the series: 64 files changed, 8306 insertions, 1727 deletions.

Topic status at baseline: Topic 1 and Topic 2 were in place, Topic 3 partial,
Topics 4, 5 and 6 had no code at all.

---

## #1 Repo hygiene

*9 files, +107/-1638. Tests: 2.*

No behaviour change. `make check` failed on the baseline, which is how most of
the rest went unnoticed.

| Problem | Fix |
| --- | --- |
| `make check` failed | 7 ruff violations in `src/utils/patch.py` |
| `apply_adk_patch()` wrapped twice | Both agents call it at import. Now tagged and idempotent. |
| Dead entry points | `[project.scripts]` pointed at `src.main:main`; no such module |
| Hand-made symlink | `convert_dataset.py` hardcoded `simple_agent`, so a fresh clone got a dangling link for `layout_aware_agent`. Now derived from the filesystem. |
| Stale docs | README predated `data_model.py`; the 2025-01-24 plan was unticked despite having shipped |
| 1.2 MB of console output in git | `eval_results.txt`, `optimize_results.txt` untracked |

Most of the deletions are those two text files.

## #2 Token accounting and cost — Topic 6

*19 files, +1541/-5. Tests: 49.*

Nothing could previously say what a run cost, or how much of it was reasoning.

**New:** `src/utils/{usage,pricing,accounting,thinking,eval_history}.py`,
`data/model_pricing.json`, `scripts/thinking_benchmark.py`,
`make bench-thinking`.

Every agent now carries a `TokenAccountantPlugin` writing costed records to
`reports/token_usage.jsonl`, attributed per `(app, agent, model)`.

Two token relationships drive the arithmetic, both easy to invert and both
pinned by tests:

- `thoughts_token_count` is **not** inside `candidates_token_count`; billable
  output is their sum.
- `cached_content_token_count` **is** inside `prompt_token_count`; full-price
  input is `prompt - cached`.

**Choices worth knowing.** Rates are a checked-in snapshot, not a live lookup,
so runs stay reproducible; it drifts, and the `_meta` block says so. An
unpriced model still records tokens with `None` dollars, because tokens are the
measurement and dollars the interpretation. Plugins hang off the `App`, not the
`Runner`, so they survive `adk eval` and `adk optimize`. The benchmark uses one
subprocess per budget, because ADK caches agent modules under the fixed name
`"agent"` and a single process would silently reuse the first planner.

## #3 Batch evaluation, reports and CI — Topic 5

*14 files, +1274/-39. Tests: 69.*

**New:** `scripts/run_batch_eval.py`, `scripts/generate_report.py`,
`src/utils/report.py`, `make batch`, `make report`, `make test`,
`.github/workflows/{ci,nightly-eval}.yml`, `.pre-commit-config.yaml`.

Reports read only what earlier runs left on disk, so they call no model. They
lead with regressions, the only section that demands action, then per-metric
deltas, per-case results, and cost per agent.

**Three judgement calls, each tested.** A case present in only one run is `NEW`
or `REMOVED`, never a regression, so adding a failing case does not look like a
break. Metric moves below `SCORE_NOISE_FLOOR` render as `~`, because LLM judges
jitter. An unpriced model renders `-`, never `$0.0000`.

CI is split by cost: `ci.yml` needs no credentials and runs on every PR;
`nightly-eval.yml` is scheduled, skips itself when credentials are absent, and
uploads the report before the regression gate can fail the run. Batch
concurrency defaults to 1 because the jobs are billable.

## #4 Self-healing NL2SQL — Topic 4

*23 files, +2371/-26. Tests: 122.* The largest PR, and the topic that had no code.

**New:** `src/agents/nl2sql_agent/`, `src/utils/{sql_runtime,sql_dialect}.py`,
`src/evaluation/sql_metrics.py`, `data/nl2sql_schema.sql`,
`data/nl2sql_golden_dataset.json`, `docs/patterns/nl2sql.md`,
`make eval-nl2sql`, `make optimize-nl2sql`. Adds one dependency, `sqlglot`.

The loop: `run_sql_query` raises with the database's own error text, the failed
SQL and the live schema attached; ADK's `ReflectAndRetryToolPlugin` catches it,
counts the failure, and tells the model not to repeat the call. Three attempts.
The retry machinery is the library's; what this PR adds is the error message.

**Choices worth knowing.** SQLite, not BigQuery, so the topic stays
reproducible and offline. Dialect handling transpiles with `sqlglot` rather
than rewriting with regexes, because a silent miscorrection is worse than an
honest error when the honest error is what drives the retry. Scoring compares
result sets, not query text. Writes are refused at the tool with both a prefix
check and a keyword scan, since the prefix check alone passes
`SELECT 1; DROP TABLE customers`.

Three of the ten cases are built to fail first, each on a different cause, so
the loop is exercised rather than assumed.

**Found while building:** verifying the golden rows against the real database
caught a hand-written expectation that was wrong — SQL010's average was
`10327.21`, actually `10327.357142857143`.

## #5 Deterministic extraction metrics — Topics 3 and 1

*10 files, +1204/-75. Tests: 214.*

**New:** `src/evaluation/extraction_metrics.py`, three complex-table cases,
`tests/eval/test_golden_datasets.py`,
`tests/evaluation/test_nl2sql_dataset.py`.

**Found while building:** two of `TC007_10K_LAYOUT`'s four expected values
disagreed with the 10-K the case cites — total revenues 2024 was `353,592`
against an actual `350,018`, and net income 2024 was `94,126` against
`100,118`. An agent reading that table correctly was marked wrong on half the
case, which made the suite's only complex-layout test worse than no test.

`extraction_f1` and `schema_adherence` replace LLM rubric judging where an
exact check is possible: free, stable between runs, and specific about what
failed. F1 rather than exact match, because nine fields of ten is better than
none and a metric that cannot tell them apart cannot drive GEPA. `layout_fidelity`
stays a rubric, because judging whether a layout was *understood* is not
something an exact check does.

Writing the tests surfaced a gap: `"CHF 31,287"` did not match `"CHF 31287"`,
which is the exact shape of TC003's golden value, so the metric would have
failed a correct extraction.

The golden datasets are now tested themselves. NL2SQL gets the strong check,
with every expected result set re-derived from the real database; the document
cases get structural checks only, because verifying a figure needs the source
PDF.

## #6 Live-run fixes and the coverage map

*11 files, +1876/-11. Tests: 239.*

**New:** `docs/topic-coverage.md`, `tests/test_topic_coverage.py`,
`tests/evaluation/test_sql_metrics_live_shape.py` and its captured fixture.

The first real `adk eval` run of `nl2sql_agent` exposed a bug that no unit test
could. **Both custom SQL metrics scored null on all ten cases while every unit
test passed.** `Invocation.intermediate_data` is a union: a golden case from a
file carries `IntermediateData` with `.tool_uses`, a live run carries
`InvocationEvents` with the calls buried in event content parts. Reading the
attribute directly worked against the hand-built shape and raised
`AttributeError` against the real one, which ADK records as a null score.

Fixed by using ADK's own accessors. Replayed against that run,
`sql_result_match` scores 0.7. The regression test uses three invocations
lifted verbatim from the run, because hand-built fixtures are precisely what
missed it.

The three failures it then surfaced were genuine agent errors, and two shared a
cause the healing loop was structurally blind to: filtering on `'Travel'` where
the data holds `'travel'`. The query **succeeded** and returned nothing, so
there was no exception to react to. Empty results now carry a hint when a
literal case-matches a stored value. The general lesson is written up as
Pattern 3b: self-healing keyed on exceptions only covers failures loud enough
to raise.

---

## What this series did not verify

Carried forward verbatim, because it is the part most likely to be forgotten.

**One live run happened**, of `nl2sql_agent`, and it immediately found a bug
that 122 passing tests had not. That is the main evidence-quality finding of
the series: for anything touching ADK's data shapes, a live run is worth more
than a unit test.

**Never run:** `make eval-simple`, `make eval-layout`, `make bench-thinking`,
`make batch`, and the nightly workflow. The document-extraction metrics, the
token accountant, the cost estimator and the report generator have not seen a
real model response.

**Unmeasured:** the empty-result hint from #6 is a hypothesis with a mechanism,
not a result.

## Open issues on `main`

1. **CI could not install dependencies.** Not caused by this series.
   `uv.lock` carries 1381 references to an internal package index
   (`airlock-proxy.uplink.goog`), introduced by the baseline `6b690a9`
   commit, which GitHub runners cannot reach, so the install step failed
   before any code ran. Fixed by resolving from the public index in CI
   instead, which leaves the lockfile and local development untouched. The
   consequence is that CI now tests the newest versions `pyproject.toml`
   allows rather than the pinned set, so a green run does not prove the
   lockfile itself is installable.
2. **A generated file is tracked.** `tests/eval/evalsets/nl2sql_evalset.json`
   is produced by `make convert` but is committed, while its sibling
   `golden_evalset.json` is gitignored. Introduced by #4.
3. The five known gaps in
   [topic-coverage.md](topic-coverage.md#known-gaps) still stand.
