"""Module for layout map data models."""

from pydantic import BaseModel, Field


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
