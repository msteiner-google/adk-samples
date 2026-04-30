"""Wrapper for layout_aware_agent to support prompt injection and optimization."""

from typing import TYPE_CHECKING

from src.agents.layout_aware_agent.agent import root_agent

if TYPE_CHECKING:
    from google.adk.agents.llm_agent import LlmAgent


def get_agent_with_instruction(instruction: str) -> LlmAgent:
    """Returns a clone of the root_agent with a new instruction."""
    return root_agent.clone(update={"instruction": instruction})
