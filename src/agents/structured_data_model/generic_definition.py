"""Generic definition."""

from typing import Any

from pydantic import BaseModel, Field


class StructuredResponse(BaseModel):
    """Structured response for bank document extraction."""

    answer: dict[str, Any] = Field(
        description="The extracted information in the requested JSON format."
    )
