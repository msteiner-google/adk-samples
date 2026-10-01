"""Unit tests for the SQLite NL2SQL runtime."""

import pytest

from src.utils.sql_runtime import MAX_ROWS, SqlDatabase, SqlExecutionError


@pytest.fixture
def db() -> SqlDatabase:
    """A fresh in-memory database seeded from the checked-in schema."""
    database = SqlDatabase()
    yield database
    database.close()


def test_seed_data_is_queryable(db: SqlDatabase):
    """The golden dataset depends on these exact seeded rows."""
    result = db.run("SELECT COUNT(*) FROM customers")
    assert result.rows == [[5]]


def test_results_carry_column_names(db: SqlDatabase):
    """A result set without column names cannot be compared or rendered."""
    result = db.run("SELECT city, COUNT(*) AS n FROM customers GROUP BY city")
    assert result.columns == ["city", "n"]


def test_bigquery_flavoured_sql_runs(db: SqlDatabase):
    """The point of the transpile step: the model's natural dialect works."""
    result = db.run("SELECT full_name FROM `proj.ds.customers` WHERE customer_id = 1")
    assert result.rows == [["Ada Lovelace"]]


def test_executed_sql_is_reported(db: SqlDatabase):
    """Debugging a wrong answer needs the SQL that actually ran."""
    result = db.run("SELECT * FROM `customers` LIMIT 1")
    assert "`" not in result.executed_sql


def test_unknown_column_error_keeps_the_database_wording(db: SqlDatabase):
    """That exact wording is the feedback the self-healing retry needs."""
    with pytest.raises(SqlExecutionError, match="no such column: customer_nmae"):
        db.run("SELECT customer_nmae FROM customers")


def test_errors_include_the_schema(db: SqlDatabase):
    """The model cannot correct a name it has not been shown."""
    with pytest.raises(SqlExecutionError, match="full_name"):
        db.run("SELECT customer_nmae FROM customers")


def test_errors_include_the_failed_sql(db: SqlDatabase):
    """Reflection works better when the model sees what it actually sent."""
    with pytest.raises(SqlExecutionError, match="SELECT nope FROM customers"):
        db.run("SELECT nope FROM customers")


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM customers",
        "DROP TABLE customers",
        "UPDATE accounts SET balance = 0",
        "INSERT INTO customers VALUES (9, 'x', 'y', 'z')",
    ],
)
def test_writes_are_refused(db: SqlDatabase, statement: str):
    """An eval run must not depend on the order its cases executed in."""
    with pytest.raises(SqlExecutionError):
        db.run(statement)


def test_write_disguised_inside_a_select_is_refused(db: SqlDatabase):
    """A read-only prefix check alone would let this through."""
    with pytest.raises(SqlExecutionError):
        db.run("SELECT 1 FROM customers WHERE 1=0; DROP TABLE customers")


def test_cte_queries_are_allowed(db: SqlDatabase):
    """WITH is a read, and the harder golden queries need it."""
    result = db.run(
        "WITH rich AS (SELECT * FROM accounts WHERE balance > 10000) "
        "SELECT COUNT(*) FROM rich"
    )
    assert result.rows == [[2]]


def test_large_results_are_capped(db: SqlDatabase):
    """A runaway cross join must not hang an eval run."""
    result = db.run(
        "SELECT a.customer_id FROM customers a, customers b, customers c, "
        "customers d, customers e, customers f"
    )
    assert result.row_count == MAX_ROWS
    assert result.truncated


def test_small_results_are_not_flagged_as_truncated(db: SqlDatabase):
    """Truncation is a warning; a false one would be misleading."""
    assert not db.run("SELECT 1").truncated


def test_schema_description_is_read_from_the_live_database(db: SqlDatabase):
    """Derived from sqlite_master, so it cannot drift from reality."""
    description = db.schema_description()
    assert "customers(" in description
    assert "transactions(" in description
    assert "amount REAL" in description


def test_two_databases_are_isolated():
    """Parallel eval jobs must not see each other's state."""
    first, second = SqlDatabase(), SqlDatabase()
    try:
        assert first.run("SELECT COUNT(*) FROM customers").rows == [[5]]
        assert second.run("SELECT COUNT(*) FROM customers").rows == [[5]]
    finally:
        first.close()
        second.close()
