"""Module for the Layout Aware A2A orchestrator agent."""

from google.adk.agents.llm_agent import Agent
from google.adk.apps.app import App

from src.utils.accounting import TokenAccountantPlugin
from src.utils.model import get_geofenced_gemini_model
from src.utils.patch import apply_adk_patch
from src.utils.thinking import planner_from_env

from .analyst.agent import layout_analyst_agent
from .extractor.agent import complex_extractor_agent

# Apply monkeypatch for ADK LocalEvalSampler
apply_adk_patch()

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
    # None unless ADK_THINKING_BUDGET is set; see src/utils/thinking.py.
    planner=planner_from_env(),
)

root_agent = orchestrator_agent

# The App name must match the directory name: `adk optimize` derives app_name
# from the path and rejects a mismatch against the sampler config.
# One accountant for the whole app attributes spend across all three agents.
app = App(
    name="layout_aware_agent",
    root_agent=root_agent,
    plugins=[TokenAccountantPlugin()],
)
