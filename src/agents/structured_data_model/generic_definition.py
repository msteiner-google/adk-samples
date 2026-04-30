"""Generic definitions for structured data models."""

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
