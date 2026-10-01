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

#: A text column with at most this many distinct values is treated as an
#: enumeration whose spellings are worth suggesting back to the model.
MAX_ENUM_VALUES = 12

#: Only read queries are allowed. The agent answers questions; it has no
#: reason to mutate, and an eval run must not depend on execution order.
_READ_ONLY_PREFIX = re.compile(r"^\s*(?:WITH|SELECT)\b", re.IGNORECASE)

_STRING_LITERAL = re.compile(r"'([^']*)'")

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
    hint: str | None = Field(
        default=None,
        description="Advice shown to the model when a result looks suspicious",
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

    @staticmethod
    def _looks_empty(rows: list[list[Any]]) -> bool:
        """Whether a result set found nothing, aggregates included.

        Zero rows is the obvious case. The subtler one is an aggregate: a
        COUNT over a filter that matched nothing returns one row holding 0,
        not an empty result, and that is the shape the first live run's
        SQL007 failure actually had.
        """
        if not rows:
            return True
        if len(rows) > 1:
            return False
        return all(value in {0, None} for value in rows[0])

    @staticmethod
    def _literals_in(sql: str) -> list[str]:
        """Returns the single-quoted string literals in a query."""
        return _STRING_LITERAL.findall(sql)

    def _known_text_values(self) -> set[str]:
        """Returns the distinct values of every low-cardinality text column.

        Only columns with few distinct values are collected, which is what
        makes this cheap: those are the category and status columns that
        appear in WHERE clauses, not free-text names.
        """
        values: set[str] = set()
        tables = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        for (table,) in tables:
            for column in self._connection.execute(
                f"PRAGMA table_info({table})"
            ).fetchall():
                name, declared_type = column[1], (column[2] or "").upper()
                if "CHAR" not in declared_type and "TEXT" not in declared_type:
                    continue
                rows = self._connection.execute(
                    f"SELECT DISTINCT {name} FROM {table} LIMIT ?",  # ruff: ignore[hardcoded-sql-expression]
                    (MAX_ENUM_VALUES + 1,),
                ).fetchall()
                if len(rows) <= MAX_ENUM_VALUES:
                    values.update(str(r[0]) for r in rows if r[0] is not None)
        return values

    def _empty_result_hint(self, sql: str) -> str | None:
        """Explains a zero-row result when a filter looks miscased.

        A query that runs and returns nothing is the failure the retry loop
        cannot see: there is no error to react to. Two of the first live
        run's three wrong answers were exactly this, filtering on 'Travel'
        and 'Savings' where the data holds 'travel' and 'savings'.

        Only fires when a literal in the query matches a known value apart
        from case, so a legitimately empty result stays silent.
        """
        literals = self._literals_in(sql)
        if not literals:
            return None

        known = self._known_text_values()
        lowered = {value.lower(): value for value in known}

        corrections = [
            f"{literal!r} -> {lowered[literal.lower()]!r}"
            for literal in literals
            if literal not in known and literal.lower() in lowered
        ]
        if not corrections:
            return None

        return (
            "The query ran but matched no rows. String comparison is "
            "case-sensitive and these literals differ from the stored values "
            "only by case: " + "; ".join(corrections) + ". "
            "Re-run with the exact stored spelling."
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
            hint=(
                self._empty_result_hint(executed) if self._looks_empty(rows) else None
            ),
        )
