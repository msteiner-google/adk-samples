from typing import Any, List
from pydantic import BaseModel, Field

class ExtractionItem(BaseModel):
    key: str = Field(description="The financial metric or field name")
    value: Any = Field(description="The extracted value")
    context: str = Field(description="Context or footnote reference for this value")

class StructuredResponse(BaseModel):
    """Structured response for bank document extraction."""
    answer: List[ExtractionItem] = Field(
        description="The extracted information in a list of contextualized items."
    )
