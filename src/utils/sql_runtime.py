"""An in-memory SQLite database and the tool the NL2SQL agent runs against it.

SQLite is the backend so the whole NL2SQL topic stays reproducible and
offline: no project, no credentials, no shared state between runs. The
dialect work that Topic 4 asks for is handled by transpiling the model's SQL
before execution, not by running a second engine.

The central design choice is that `run_sql` raises on a bad query with the
database's own error text attached. That exception is what ADK's
ReflectAndRetryToolPlugin feeds back to the model, which is precisely the
self-healing loop Topic 4 describes: the agent corrects its SQL from the
error the database produced.
"""

from __future__ import annotations

import pathlib
import re
import sqlite3
from typing import Any

from pydantic import BaseModel, Field

from src.utils.sql_dialect import DEFAULT_SOURCE_DIALECT, to_sqlite

DEFAULT_SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "nl2sql_schema.sql"
)

#: Queries are capped so a runaway cross join cannot hang an eval run.
MAX_ROWS = 200

#: Only read queries are allowed. The agent answers questions; it has no
#: reason to mutate, and an eval run must not depend on execution order.
_READ_ONLY_PREFIX = re.compile(r"^\s*(?:WITH|SELECT)\b", re.IGNORECASE)

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|PRAGMA)\b",
    re.IGNORECASE,
)


class SqlExecutionError(RuntimeError):
    """Raised when a query cannot be run.

    The message deliberately carries the database's own wording plus the
    schema, because the whole message is handed back to the model as the
    feedback it must correct from.
    """


class QueryResult(BaseModel):
    """The outcome of a successful query."""

    columns: list[str] = Field(description="Column names, in order")
    rows: list[list[Any]] = Field(description="Result rows, in order")
    row_count: int = Field(description="Number of rows returned")
    executed_sql: str = Field(description="The SQL actually run, post-transpile")
    truncated: bool = Field(
        default=False, description="Whether the result hit MAX_ROWS"
    )


class SqlDatabase:
    """A throwaway SQLite database built from a schema file.

    Each instance owns a private in-memory connection, so tests and parallel
    eval jobs cannot see each other's state.
    """

    def __init__(self, schema_path: pathlib.Path | None = None) -> None:
        """Builds the database and applies the schema and seed rows."""
        self._schema_path = schema_path or DEFAULT_SCHEMA_PATH
        self._connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._connection.executescript(self._schema_path.read_text(encoding="utf-8"))
        self._connection.commit()

    def close(self) -> None:
        """Closes the underlying connection."""
        self._connection.close()

    def schema_description(self) -> str:
        """Renders the schema as compact text for a prompt or error message.

        Built by querying sqlite_master rather than re-reading the .sql file,
        so it cannot drift from what is actually in the database.
        """
        cursor = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        lines = []
        for (table,) in cursor.fetchall():
            columns = self._connection.execute(f"PRAGMA table_info({table})").fetchall()
            rendered = ", ".join(f"{col[1]} {col[2]}" for col in columns)
            lines.append(f"  {table}({rendered})")
        return "\n".join(lines)

    def _reject_if_not_read_only(self, sql: str) -> None:
        """Raises unless the statement is a plain read."""
        if not _READ_ONLY_PREFIX.match(sql):
            msg = "Only SELECT and WITH queries are allowed."
            raise SqlExecutionError(self._with_context(msg, sql))
        if _FORBIDDEN.search(sql):
            msg = "Statement contains a write or schema-changing keyword."
            raise SqlExecutionError(self._with_context(msg, sql))

    def _with_context(self, error: str, sql: str) -> str:
        """Attaches the schema to an error so the model can self-correct.

        The database's own wording comes first: it is the most specific
        signal, and burying it under boilerplate makes the retry worse.
        """
        return (
            f"{error}\n\n"
            f"Failed SQL:\n{sql}\n\n"
            f"Available schema (SQLite):\n{self.schema_description()}\n\n"
            "Rewrite the query using only these tables and columns."
        )

    def run(self, sql: str, dialect: str = DEFAULT_SOURCE_DIALECT) -> QueryResult:
        """Transpiles, validates and executes a read-only query.

        Args:
          sql: The query as the model wrote it.
          dialect: The dialect the model was writing in. Defaults to the
            BigQuery-flavoured SQL Gemini tends to produce.

        Returns:
          The rows, columns and the SQL that actually ran.

        Raises:
          SqlExecutionError: on a transpile failure, a rejected statement or
            any database error. The message carries the schema so that the
            retry has something to work from.
        """
        try:
            executed = to_sqlite(sql, source_dialect=dialect)
        except ValueError as exc:
            raise SqlExecutionError(self._with_context(str(exc), sql)) from exc

        self._reject_if_not_read_only(executed)

        try:
            cursor = self._connection.execute(executed)
            fetched = cursor.fetchmany(MAX_ROWS + 1)
        except sqlite3.Error as exc:
            # sqlite3's message is the feedback the model needs; keep its
            # exact wording rather than paraphrasing it.
            raise SqlExecutionError(
                self._with_context(f"{type(exc).__name__}: {exc}", executed)
            ) from exc

        truncated = len(fetched) > MAX_ROWS
        rows = [list(row) for row in fetched[:MAX_ROWS]]
        columns = [d[0] for d in cursor.description] if cursor.description else []

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            executed_sql=executed,
            truncated=truncated,
        )
