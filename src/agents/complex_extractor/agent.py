"""Module for complex document extraction."""

from google.adk.agents.llm_agent import LlmAgent

from src.utils.data_model import StructuredResponse
from src.utils.model import get_geofenced_gemini_model

complex_extractor_agent = LlmAgent(
    name="complex_extractor",
    instruction=(
        "You are a specialized data extraction agent. Using the provided Layout Map, "
        "extract the financial metrics and fields from the document. Ensure you "
        "capture context and footnote references accurately. Always return the "
        "answer as a structured list of items."
    ),
    model=get_geofenced_gemini_model(),
    output_schema=StructuredResponse,
    output_key="structured_extraction",
)
