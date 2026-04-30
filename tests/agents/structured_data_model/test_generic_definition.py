from src.agents.structured_data_model.generic_definition import StructuredResponse, ExtractionItem

def test_generic_extraction_with_context():
    item = {
        "key": "Total Assets",
        "value": 1000000,
        "context": "As of Dec 31, 2024, per Item 8"
    }
    response = StructuredResponse(answer=[item])
    assert response.answer[0].key == "Total Assets"
    assert response.answer[0].context == "As of Dec 31, 2024, per Item 8"
