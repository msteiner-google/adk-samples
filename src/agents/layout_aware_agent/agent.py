"""Module for the Layout Aware A2A orchestrator agent."""

from google.adk.agents.llm_agent import Agent

from src.utils.model import get_geofenced_gemini_model

from .analyst.agent import layout_analyst_agent
from .extractor.agent import complex_extractor_agent

orchestrator_agent = Agent(
    name="layout_aware_orchestrator",
    instruction=(
        "You are the orchestrator for complex document extraction. "
        "1. Delegate to layout_analyst to understand the document structure. "
        "2. Pass the resulting Layout Map and the document to complex_extractor "
        "to get the data. "
        "3. Ensure the final response is a structured extraction."
    ),
    model=get_geofenced_gemini_model(),
    sub_agents=[layout_analyst_agent, complex_extractor_agent],
)

root_agent = orchestrator_agent
