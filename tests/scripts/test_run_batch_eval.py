"""Unit tests for the batch evaluation matrix."""

from scripts.run_batch_eval import Job, build_matrix


def test_matrix_without_budgets_is_one_job_per_agent():
    """The common case: evaluate every agent once, on its default settings."""
    matrix = build_matrix(["simple_agent", "layout_aware_agent"], None)

    assert matrix == [
        Job(agent="simple_agent", budget=None),
        Job(agent="layout_aware_agent", budget=None),
    ]


def test_matrix_crosses_agents_with_budgets():
    """Agents times budgets, so a sweep covers every combination."""
    matrix = build_matrix(["a", "b"], [0, 2048])

    assert [job.label for job in matrix] == ["a@off", "a@2048", "b@off", "b@2048"]


def test_empty_budget_list_falls_back_to_defaults():
    """An empty --budgets must not produce an empty matrix."""
    assert build_matrix(["a"], []) == [Job(agent="a", budget=None)]


def test_label_omits_the_budget_when_unset():
    """A default run is labelled by agent alone, not "agent@default"."""
    assert Job(agent="simple_agent", budget=None).label == "simple_agent"


def test_dynamic_budget_is_labelled_not_numeric():
    """-1 means dynamic; a report column reading "-1" would be opaque."""
    assert Job(agent="a", budget=-1).label == "a@dynamic"
