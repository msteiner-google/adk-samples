"""Unit tests for data models."""

from src.utils.data_model import (
    ExtractionItem,
    LayoutComponent,
    LayoutMap,
    StructuredResponse,
)


def test_structured_response():
    """Test StructuredResponse validation."""
    item = ExtractionItem(key="Net Income", value=100.0, context="Page 1")
    response = StructuredResponse(answer=[item])
    assert len(response.answer) == 1
    assert response.answer[0].key == "Net Income"


def test_layout_map():
    """Test LayoutMap validation."""
    comp = LayoutComponent(
        type="table", description="Income Statement", coordinates_hint="Top"
    )
    layout = LayoutMap(components=[comp], nested_table_count=0)
    assert len(layout.components) == 1
    assert layout.components[0].type == "table"
