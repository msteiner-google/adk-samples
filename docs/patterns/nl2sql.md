# Self-healing NL2SQL patterns

What worked, what did not, and why, for Topic 4's "document successful
patterns for interaction between natural language and databases".

Everything here is implemented in `src/agents/nl2sql_agent/`,
`src/utils/sql_runtime.py` and `src/utils/sql_dialect.py`.

---

## Pattern 1: Make the error message the product

**The pattern.** The query tool raises on failure, and the exception carries
three things: the database's own error text, the SQL that failed, and the live
schema.

```
OperationalError: no such column: customer_nmae

Failed SQL:
SELECT customer_nmae FROM customers

Available schema (SQLite):
  accounts(account_id INTEGER, customer_id INTEGER, ...)
  customers(customer_id INTEGER, full_name TEXT, city TEXT, joined_date TEXT)
  ...

Rewrite the query using only these tables and columns.
```

**Why.** This message is not for a human reading a log. It is the input to the
next model turn, and it is the only thing standing between a failed query and a
correct one. Each part earns its place: the error says what is wrong, the SQL
says what was sent (models do not reliably remember), and the schema gives
something to correct *toward*. Without the schema, the model's next guess is
another guess.

**What not to do.** Do not paraphrase the database. `"Invalid column
reference"` is strictly less useful than `no such column: customer_nmae`,
which names the typo. Pass the engine's wording through verbatim.

**Also.** Derive the schema text from `sqlite_master`, not from the `.sql`
file. What the model is told then cannot drift from what the database holds.

---

## Pattern 2: Use the framework's retry loop

**The pattern.** Attach `ReflectAndRetryToolPlugin(max_retries=3)` to the App
and let it own the loop. The tool raises; the plugin counts, formats guidance,
and tells the model not to repeat itself.

**Why.** A hand-written loop has to solve per-tool failure tracking,
concurrency-safe counters, invocation-scoped state, and reset-on-success.
ADK already does all four. The interesting work is the error message
(Pattern 1), not the plumbing.

**The budget matters.** Three attempts covers the common repairs: misspelled
column, unsupported function, dialect slip. Higher mostly burns tokens on
queries that were never going to work. Failures are scoped per invocation, so
one bad eval case cannot consume the next case's retries.

---

## Pattern 3: Transpile, do not regex

**The pattern.** Gemini writes BigQuery SQL by default. Rather than prompting
it not to, parse what it wrote with `sqlglot` and emit the target dialect.

| Model writes | Runs as |
| --- | --- |
| `` SELECT * FROM `proj.ds.customers` `` | `SELECT * FROM "customers"` |
| `SAFE_CAST(balance AS STRING)` | `CAST(balance AS TEXT)` |
| `IFNULL(city, "none")` | `COALESCE(city, 'none')` |

**Why not regex.** SQL rewriting by regex fails silently on quoting, nesting
and comments. A silent miscorrection is worse than an honest error here,
because the honest error is what drives Pattern 1. A parser either understands
the query or says it does not.

**Limits worth knowing.** Transpilation is not total. `EXTRACT(YEAR FROM ...)`
parses and emits unchanged, then SQLite rejects it. That is acceptable, and the
golden dataset includes it as case `SQL009`: the failure surfaces as a syntax
error the model can act on, and the healing loop handles it. Prefer a known
gap that triggers recovery over a clever rewrite that might change the meaning.

**Fence stripping is separate.** Models answer with ```` ```sql ```` blocks.
Strip that before parsing, or the parse error talks about backticks instead of
the query.

---

## Pattern 4: Grade the rows, not the SQL

**The pattern.** Score a query by re-running it and comparing result sets
against the expected rows. Do not compare query text, and do not ask an LLM to
judge the SQL.

**Why.** There are many correct spellings of any query. `COUNT(*)` against
`COUNT(customer_id)`, a join written two ways, a CTE against a subquery, all
correct. Text comparison fails them. An LLM judge reading SQL grades whether
the query *looks* right, which is a different question from whether it returns
the right answer.

**Two details that bite.**

- **Row order.** Without `ORDER BY`, the engine may return any order. Sort
  before comparing, or correct answers fail at random.
- **Floats.** `AVG(balance)` and `SUM(balance)/COUNT(*)` are both right and
  differ in the last bits of the double. Round before comparing. Keep the
  tolerance tight enough that a genuinely different number still fails.

**This only works with a deterministic database.** Re-running the query is
cheap and safe because the SQLite database is seeded from a fixed script and
read-only. Against a live warehouse this pattern needs a snapshot.

---

## Pattern 5: Measure recovery separately from correctness

**The pattern.** `sql_self_heal_recovery` scores only the invocations whose
first query failed. Cases that never failed are skipped, not counted as passes.

**Why.** Self-healing is the behaviour under test, and a dataset of easy
questions would report a perfect recovery rate while never exercising it. If
nothing failed, the honest answer is `NOT_EVALUATED`, not 100%.

**Build failures in on purpose.** Three of the ten golden cases are written to
fail first, each on a different cause (wrong column, unsupported function,
wrong table). Each steers the model wrong in the prompt itself, for example by
asserting that the name column is `customer_name` when it is `full_name`. A
self-healing agent that is never given anything to heal is untested.

---

## Pattern 6: Refuse writes at the tool, not in the prompt

**The pattern.** The tool allows only `SELECT` and `WITH`, enforced by a prefix
check *and* a forbidden-keyword scan.

**Why both.** A prefix check alone passes
`SELECT 1 FROM customers WHERE 1=0; DROP TABLE customers`. Its first token is
harmless.

**Why not just ask.** An instruction not to mutate is a request. For an eval
suite the stronger reason is determinism: if any case could write, results
would depend on the order cases ran in, and a flaky suite teaches nothing.
Results are also capped at `MAX_ROWS`, so a runaway cross join cannot hang a
run.

---

## Open questions

- **Scale.** The schema is three tables. Real warehouses have hundreds, and
  pasting the whole schema into every error stops working. The next step is
  retrieving the relevant subset rather than sending all of it.
- **Dialect coverage.** Only the SQLite target is exercised. `sql_dialect.py`
  accepts BigQuery, Postgres, MySQL and DuckDB as sources, but nothing in the
  suite runs against those engines.
- **Recovery quality.** The metric records *whether* the agent recovered, not
  how efficiently. An agent that flails for three attempts scores the same as
  one that fixes the query immediately.
