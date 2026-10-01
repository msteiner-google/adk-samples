"""Structural checks on the golden datasets themselves.

A golden dataset is the measuring instrument: if it is wrong, every score
derived from it is wrong, and nothing downstream will say so. Two of
TC007's four expected values disagreed with the document they cited for as
long as the case existed, because nothing checked.

These tests run in CI, cost nothing, and do not call a model. They cannot
confirm that an expected value is the *right* one, which needs the source
document, but they do catch the mistakes that are mechanically detectable:
a missing file, a duplicate id, a malformed response, an unpopulated field.

The NL2SQL dataset gets the stronger check it can support: its expected
rows are verified against the real database in
tests/evaluation/test_nl2sql_dataset.py.
"""

import json
import pathlib

import pytest

from src.evaluation.extraction_metrics import parse_items, score_schema
from src.utils.data_model import StructuredResponse

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data"

DOCUMENT_DATASET = DATA / "golden_dataset_template.json"
NL2SQL_DATASET = DATA / "nl2sql_golden_dataset.json"


def load(path: pathlib.Path) -> dict:
    """Reads a dataset template."""
    return json.loads(path.read_text(encoding="utf-8"))


def document_cases() -> list[dict]:
    """Returns the document-extraction eval cases."""
    return load(DOCUMENT_DATASET)["eval_cases"]


def case_ids(dataset: pathlib.Path) -> list[str]:
    """Returns the eval ids in a dataset."""
    return [c["eval_id"] for c in load(dataset)["eval_cases"]]


@pytest.mark.parametrize("dataset", [DOCUMENT_DATASET, NL2SQL_DATASET])
def test_dataset_is_valid_json_with_cases(dataset: pathlib.Path):
    """A dataset that does not parse fails every run for the wrong reason."""
    payload = load(dataset)
    assert payload["eval_cases"], f"{dataset.name} has no cases"


@pytest.mark.parametrize("dataset", [DOCUMENT_DATASET, NL2SQL_DATASET])
def test_eval_ids_are_unique(dataset: pathlib.Path):
    """Duplicate ids make results ambiguous and silently overwrite."""
    ids = case_ids(dataset)
    assert len(ids) == len(set(ids))


def test_referenced_documents_exist():
    """A missing PDF fails at conversion, after someone has waited for it."""
    missing = [
        part["file_path"]
        for case in document_cases()
        for invocation in case["conversation"]
        for part in invocation["user_content"]["parts"]
        if "file_path" in part and not (PROJECT_ROOT / part["file_path"]).is_file()
    ]
    assert missing == []


@pytest.mark.parametrize("case", document_cases(), ids=lambda c: c["eval_id"])
def test_expected_response_matches_the_schema(case: dict):
    """The golden answer must satisfy the schema the agent is held to.

    An expected value the agent could never produce makes a case
    unpassable, and the failure would be read as an agent problem.
    """
    payload = case["conversation"][0]["final_response"]["parts"][0]["text"]
    StructuredResponse.model_validate(payload)


@pytest.mark.parametrize("case", document_cases(), ids=lambda c: c["eval_id"])
def test_expected_response_has_no_empty_fields(case: dict):
    """Held to the same schema_adherence bar the agent is scored against."""
    payload = case["conversation"][0]["final_response"]["parts"][0]["text"]
    assert score_schema(payload["answer"]) == 1.0


@pytest.mark.parametrize("case", document_cases(), ids=lambda c: c["eval_id"])
def test_expected_keys_are_distinct_within_a_case(case: dict):
    """Repeated keys make per-field matching ambiguous."""
    payload = case["conversation"][0]["final_response"]["parts"][0]["text"]
    keys = [item["key"] for item in payload["answer"]]
    assert len(keys) == len(set(keys))


def test_every_case_asks_a_question():
    """A case with no prompt measures nothing."""
    for case in document_cases():
        parts = case["conversation"][0]["user_content"]["parts"]
        assert any(part.get("text", "").strip() for part in parts), case["eval_id"]


def test_complex_layout_cases_are_present():
    """Topic 3 needs more than one complex-document case to mean anything."""
    layout_cases = [cid for cid in case_ids(DOCUMENT_DATASET) if "10K" in cid]
    assert len(layout_cases) >= 4


def test_generated_evalset_round_trips(tmp_path: pathlib.Path):
    """The conversion step must preserve the expected answers verbatim.

    Conversion stringifies the response objects, and a bug there would
    change what every case is scored against.
    """
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.convert_dataset import convert_to_adk_format

    output = tmp_path / "golden_evalset.json"
    convert_to_adk_format(str(DOCUMENT_DATASET), str(output), agent_names=())

    produced = json.loads(output.read_text(encoding="utf-8"))
    for source, converted in zip(document_cases(), produced["eval_cases"], strict=True):
        expected = source["conversation"][0]["final_response"]["parts"][0]["text"]
        text = converted["conversation"][0]["final_response"]["parts"][0]["text"]
        assert json.loads(text) == expected, source["eval_id"]


@pytest.mark.parametrize("case", document_cases(), ids=lambda c: c["eval_id"])
def test_expected_answer_scores_perfectly_against_itself(case: dict):
    """A sanity check on the metric and the data at once.

    If a golden answer cannot score 1.0 against a copy of itself, either
    the metric or the case is broken, and this says so before a paid run.
    """
    from google.adk.evaluation.eval_case import Invocation
    from google.genai import types

    from src.evaluation.extraction_metrics import score_extraction

    text = json.dumps(case["conversation"][0]["final_response"]["parts"][0]["text"])
    invocation = Invocation(
        invocation_id="i",
        user_content=types.Content(parts=[types.Part(text="q")]),
        final_response=types.Content(role="model", parts=[types.Part(text=text)]),
    )
    items = parse_items(invocation)
    assert items is not None
    assert score_extraction(items, items) == (1.0, 1.0, 1.0)
