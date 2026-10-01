"""Post-processing to make model-written SQL run on the local engine.

Topic 4 asks for "post-processing techniques to improve compatibility across
different SQL dialects". Gemini writes BigQuery-flavoured SQL by default:
backtick-quoted identifiers, `SAFE_CAST`, `SAFE_DIVIDE`, `project.dataset.table`
names, `EXTRACT(YEAR FROM ...)`. None of that runs on SQLite.

The approach is to transpile with sqlglot rather than to patch strings with
regexes. Regex rewriting of SQL fails silently on quoting, nesting and
comments, and a silent miscorrection is far worse here than an honest error,
because an honest error is what drives the self-healing retry.

Two things are handled before sqlglot sees the query, because they are
lexical rather than syntactic: stripping markdown code fences the model wraps
its answer in, and flattening fully-qualified BigQuery table names.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

#: The dialect Gemini writes unless told otherwise.
DEFAULT_SOURCE_DIALECT = "bigquery"

TARGET_DIALECT = "sqlite"

#: Dialects this module accepts as a source.
SUPPORTED_SOURCE_DIALECTS = ("bigquery", "sqlite", "postgres", "mysql", "duckdb")

_CODE_FENCE = re.compile(
    r"^\s*```(?:sql)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE
)

_TRAILING_SEMICOLONS = re.compile(r";\s*$")


def strip_code_fence(sql: str) -> str:
    """Removes a markdown code fence around a query, if present.

    Models asked for SQL frequently answer with a fenced block. Passing the
    fence to a parser produces a confusing syntax error that says nothing
    about the actual query.
    """
    match = _CODE_FENCE.match(sql)
    return match.group("body") if match else sql.strip()


def flatten_qualified_tables(tree: exp.Expression) -> exp.Expression:
    """Rewrites `project.dataset.table` references down to `table`.

    The local database has no catalogs or schemas. A model that has seen
    BigQuery will often qualify names anyway, and the resulting "no such
    table: project.dataset.table" is a dead end rather than a useful hint.
    """
    for table in tree.find_all(exp.Table):
        table.set("catalog", None)
        table.set("db", None)
    return tree


def to_sqlite(sql: str, source_dialect: str = DEFAULT_SOURCE_DIALECT) -> str:
    """Translates a query into SQLite-compatible SQL.

    Args:
      sql: The query as written, possibly inside a markdown fence.
      source_dialect: The dialect to read it as.

    Returns:
      An equivalent single statement in SQLite syntax.

    Raises:
      ValueError: if the text is empty, unparseable, or more than one
        statement. The message is written to be handed to a model as retry
        feedback, so it says what to do rather than only what went wrong.
    """
    if source_dialect not in SUPPORTED_SOURCE_DIALECTS:
        msg = (
            f"Unsupported source dialect {source_dialect!r}. "
            f"Supported: {', '.join(SUPPORTED_SOURCE_DIALECTS)}."
        )
        raise ValueError(msg)

    cleaned = _TRAILING_SEMICOLONS.sub("", strip_code_fence(sql)).strip()
    if not cleaned:
        msg = "Empty query. Write a single SELECT statement."
        raise ValueError(msg)

    try:
        statements = sqlglot.parse(cleaned, read=source_dialect)
    except ParseError as exc:
        msg = f"Could not parse the query as {source_dialect} SQL: {exc}"
        raise ValueError(msg) from exc

    parsed = [s for s in statements if s is not None]
    if not parsed:
        msg = "Empty query. Write a single SELECT statement."
        raise ValueError(msg)
    if len(parsed) > 1:
        msg = (
            f"Expected a single statement, found {len(parsed)}. "
            "Combine them into one query or use a CTE."
        )
        raise ValueError(msg)

    tree = flatten_qualified_tables(parsed[0])

    try:
        return tree.sql(dialect=TARGET_DIALECT)
    except Exception as exc:
        msg = (
            f"Could not translate the query to SQLite: {exc}. "
            "Try standard SQL without vendor-specific functions."
        )
        raise ValueError(msg) from exc
