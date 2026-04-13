"""ADK Agent entry point for evaluation."""
from google.adk.apps.app import App

from src.agents.simple_agent import SimpleAgent

simple_agent_instance = SimpleAgent()
# The SimpleAgent class initializes self.agent which is an LlmAgent
agent = App(root_agent=simple_agent_instance.agent, name="src")
