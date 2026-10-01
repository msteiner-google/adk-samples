"""Unit tests for cross-dialect SQL post-processing."""

import pytest

from src.utils.sql_dialect import strip_code_fence, to_sqlite


@pytest.mark.parametrize(
    ("fenced", "expected"),
    [
        ("```sql\nSELECT 1\n```", "SELECT 1"),
        ("```\nSELECT 1\n```", "SELECT 1"),
        ("  SELECT 1  ", "SELECT 1"),
    ],
)
def test_code_fences_are_stripped(fenced: str, expected: str):
    """Models answer with fenced blocks; a parser error there says nothing."""
    assert strip_code_fence(fenced) == expected


def test_backticked_identifiers_become_portable():
    """BigQuery backticks are a syntax error in SQLite."""
    assert "`" not in to_sqlite("SELECT * FROM `customers`")


def test_qualified_table_names_are_flattened():
    """A local database has no project or dataset to resolve."""
    result = to_sqlite("SELECT * FROM `my-proj.banking.customers`")
    assert "customers" in result
    assert "banking" not in result
    assert "my-proj" not in result


def test_safe_cast_becomes_cast():
    """SAFE_CAST is BigQuery-only and the nearest portable form is CAST."""
    assert "SAFE_CAST" not in to_sqlite(
        "SELECT SAFE_CAST(balance AS STRING) FROM accounts"
    )


def test_ifnull_becomes_coalesce():
    """Null handling differs by vendor; COALESCE is the portable spelling."""
    assert "COALESCE" in to_sqlite('SELECT IFNULL(city, "none") FROM customers')


def test_double_quoted_literals_become_single_quoted():
    """BigQuery treats "x" as a string; SQLite treats it as an identifier."""
    assert "'none'" in to_sqlite('SELECT IFNULL(city, "none") FROM customers')


def test_trailing_semicolon_is_tolerated():
    """A stray semicolon must not read as a second statement."""
    assert to_sqlite("SELECT 1;") == "SELECT 1"


def test_sqlite_source_passes_through():
    """An agent already writing SQLite must not be mangled."""
    assert to_sqlite("SELECT 1", source_dialect="sqlite") == "SELECT 1"


def test_empty_query_is_rejected_with_an_instruction():
    """Retry feedback has to say what to do, not only what broke."""
    with pytest.raises(ValueError, match="single SELECT"):
        to_sqlite("   ")


def test_multiple_statements_are_rejected():
    """One query per call keeps results and errors attributable."""
    with pytest.raises(ValueError, match="single statement"):
        to_sqlite("SELECT 1; SELECT 2")


def test_unparseable_sql_names_the_dialect():
    """The model needs to know which grammar its text failed against."""
    with pytest.raises(ValueError, match="bigquery"):
        to_sqlite("SELECT FROM WHERE GROUP")


def test_unsupported_dialect_lists_the_alternatives():
    """A misconfiguration should say what was expected."""
    with pytest.raises(ValueError, match="sqlite"):
        to_sqlite("SELECT 1", source_dialect="oracle")
