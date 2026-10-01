"""Verifies the NL2SQL golden rows against the real database.

This is the check the document dataset cannot have: the SQLite database is
in the repo and deterministic, so every expected result set can be proved
achievable rather than trusted.

It is what caught SQL010's average being wrong by hand (10327.21 against
the actual 10327.357142857143), and it is why that cannot happen silently
again.
"""

import json
import pathlib

import pytest

from src.evaluation.sql_metrics import _normalise
from src.utils.sql_runtime import SqlDatabase

DATASET = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "nl2sql_golden_dataset.json"
)

#: A reference query per case. These are not the agent's queries and are
#: not what it is scored against; they exist only to prove the expected rows
#: are reachable from the schema. A deliberately different spelling from the
#: obvious one also exercises the metric's order and float tolerance.
REFERENCE_QUERIES = {
    "SQL001_count_customers": "SELECT COUNT(*) FROM customers",
    "SQL002_filter_by_city": (
        "SELECT full_name FROM customers WHERE city = 'Milan' ORDER BY full_name DESC"
    ),
    "SQL003_aggregate_group_by": (
        "SELECT city, COUNT(*) FROM customers GROUP BY city ORDER BY city"
    ),
    "SQL004_join_two_tables": (
        "SELECT SUM(a.balance) FROM accounts a "
        "JOIN customers c ON c.customer_id = a.customer_id "
        "WHERE c.full_name = 'Ada Lovelace'"
    ),
    "SQL005_three_table_join": (
        "SELECT c.city, SUM(t.amount) FROM transactions t "
        "JOIN accounts a ON a.account_id = t.account_id "
        "JOIN customers c ON c.customer_id = a.customer_id "
        "WHERE t.category = 'travel' GROUP BY c.city "
        "ORDER BY SUM(t.amount) ASC LIMIT 1"
    ),
    "SQL006_negative_amounts": "SELECT COUNT(*) FROM transactions WHERE amount < 0",
    "SQL007_cte_required": (
        "WITH rich AS (SELECT * FROM accounts WHERE balance > 10000) "
        "SELECT COUNT(*) FROM rich WHERE account_type = 'savings'"
    ),
    "SQL008_heal_wrong_column_name": (
        "SELECT full_name FROM customers WHERE joined_date < '2021-01-01'"
    ),
    "SQL009_heal_unsupported_function": (
        "SELECT COUNT(*) FROM transactions WHERE txn_date LIKE '2024%'"
    ),
    # Deliberately SUM/COUNT rather than AVG: the two differ in the last
    # bits of the double, so this also pins the metric's float tolerance.
    "SQL010_heal_wrong_table_name": "SELECT SUM(balance) / COUNT(*) FROM accounts",
}


def cases() -> list[dict]:
    """Returns the NL2SQL eval cases."""
    return json.loads(DATASET.read_text(encoding="utf-8"))["eval_cases"]


def expected_rows(case: dict) -> list:
    """Returns a case's expected result set."""
    responses = case["conversation"][0]["intermediate_data"]["tool_responses"]
    return responses[0]["response"]["expected_rows"]


@pytest.fixture(scope="module")
def db() -> SqlDatabase:
    """One database for the whole module; queries are read-only."""
    database = SqlDatabase()
    yield database
    database.close()


def test_every_case_has_a_reference_query():
    """A new case without one would skip verification unnoticed."""
    missing = [c["eval_id"] for c in cases() if c["eval_id"] not in REFERENCE_QUERIES]
    assert missing == []


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["eval_id"])
def test_expected_rows_are_reachable(db: SqlDatabase, case: dict):
    """Every golden result set must be producible from the real database."""
    result = db.run(REFERENCE_QUERIES[case["eval_id"]])
    actual = [list(row) for row in result.rows]

    assert _normalise(actual) == _normalise(expected_rows(case)), (
        f"{case['eval_id']}: expected {expected_rows(case)}, "
        f"reference query returned {actual}"
    )


def test_healing_cases_are_present():
    """Self-healing is untested if nothing in the dataset fails first."""
    healing = [c["eval_id"] for c in cases() if "_heal_" in c["eval_id"]]
    assert len(healing) >= 3


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["eval_id"])
def test_healing_cases_steer_the_model_wrong(case: dict):
    """A healing case only works if the prompt plants the mistake.

    Without a wrong name or an unsupported function in the question, the
    agent has no reason to fail, and the case silently stops testing
    recovery.
    """
    if "_heal_" not in case["eval_id"]:
        pytest.skip("not a healing case")

    question = case["conversation"][0]["user_content"]["parts"][0]["text"]
    bait = ("customer_name", "EXTRACT", "bank_accounts")
    assert any(token in question for token in bait), question
