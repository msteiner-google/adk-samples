"""Module for document layout analysis."""

from google.adk.agents.llm_agent import LlmAgent

from src.agents.structured_data_model.layout_map import LayoutMap
from src.utils.model import get_geofenced_gemini_model

layout_analyst_agent = LlmAgent(
    name="layout_analyst",
    instruction=(
        "You are an expert at document layout analysis. Analyze the provided page "
        "and identify all structural components like tables, lists, and footnotes. "
        "Focus on finding nested tables and complex hierarchies."
    ),
    model=get_geofenced_gemini_model(),
    output_schema=LayoutMap,
    output_key="layout_map",
)
