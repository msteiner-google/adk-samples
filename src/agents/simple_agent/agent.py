"""Agent using LlmAgent to extract data from bank documents via multimodal input."""

from google.adk.agents.llm_agent import LlmAgent

from src.agents.simple_agent._patch import apply_patch
from src.agents.structured_data_model.generic_definition import StructuredResponse
from src.utils.model import get_geofenced_gemini_model

# Apply monkeypatch for ADK LocalEvalSampler
apply_patch()


root_agent = LlmAgent(
    name="simple_bank_agent",
    instruction=(
        "You are an expert at extracting structured information from bank "
        "documents provided as attachments. Analyze the provided document "
        "content and extract the requested information. Always return your "
        "answer as a valid JSON object matching the requested schema."
    ),
    model=get_geofenced_gemini_model(),
    output_schema=StructuredResponse,
    output_key="structured_extraction",
)
