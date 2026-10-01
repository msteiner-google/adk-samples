"""The query tool the NL2SQL agent calls.

Kept apart from the agent definition so the tool can be tested directly,
without a model in the loop.
"""

from __future__ import annotations

import functools

from src.utils.sql_runtime import QueryResult, SqlDatabase


@functools.lru_cache(maxsize=1)
def get_database() -> SqlDatabase:
    """Returns the process-wide database, building it on first use.

    One instance per process: `adk eval` runs each agent in its own process,
    and the database is read-only, so sharing it across invocations is safe
    and avoids re-running the schema script for every query.
    """
    return SqlDatabase()


def describe_schema() -> str:
    """Returns the database schema.

    Use this before writing a query if you are unsure of a table or column
    name. Names are exact and case-sensitive.

    Returns:
        The tables and their columns, one table per line.
    """
    return get_database().schema_description()


def run_sql_query(query: str) -> QueryResult:
    """Runs a read-only SQL query and returns the rows.

    Write a single SELECT (or WITH ... SELECT) statement. BigQuery syntax is
    accepted and translated automatically.

    Args:
        query: The SQL to run.

    Returns:
        The column names, the rows, and the SQL that was actually executed.

    Raises:
        SqlExecutionError: if the query is rejected or the database refuses
            it. The message carries the database's own error text, the failed
            SQL and the schema, so a failed call is directly correctable.
    """
    return get_database().run(query)
