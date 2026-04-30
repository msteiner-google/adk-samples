"""Data models for document extraction and layout analysis."""

from typing import Any

from pydantic import BaseModel, Field


class ExtractionItem(BaseModel):
    """A financial metric or field extracted from a document."""

    key: str = Field(description="The financial metric or field name")
    value: Any = Field(description="The extracted value")
    context: str = Field(description="Context or footnote reference for this value")


class StructuredResponse(BaseModel):
    """Structured response for bank document extraction."""

    answer: list[ExtractionItem] = Field(
        description="The extracted information in a list of contextualized items."
    )


class LayoutComponent(BaseModel):
    """A structural component of a document."""

    type: str = Field(
        description="Type of component: table, text_block, list, footnote"
    )
    description: str = Field(
        description="Description of the component content and logical role"
    )
    coordinates_hint: str = Field(
        description=(
            "Natural language or approximate position hint "
            "(e.g. 'Top left', 'Bottom of page')"
        )
    )


class LayoutMap(BaseModel):
    """The layout map of a document page."""

    components: list[LayoutComponent] = Field(
        description="List of structural components identified in the document"
    )
    nested_table_count: int = Field(
        description="Number of complex or nested tables found"
    )
