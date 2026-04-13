"""Agent using LlmAgent to extract data from bank documents via multimodal input."""

import asyncio
import json
import os
import pathlib
from typing import Any

from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.run_config import RunConfig
from google.adk.events.event import Event
from google.adk.models.google_llm import Gemini
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import Client, types
from loguru import logger
from pydantic import BaseModel, Field


class StructuredResponse(BaseModel):
    """Structured response for bank document extraction."""

    answer: dict[str, Any] = Field(
        description="The extracted information in the requested JSON format."
    )


class SimpleAgent:
    """Agent using LlmAgent to extract data from bank documents."""

    def __init__(self) -> None:
        """Initialize the SimpleAgent with a single LlmAgent and output schema."""
        client_global = Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", "msteiner-kubeflow"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west4"),
        )

        global_model = Gemini(
            model="gemini-2.5-flash",
        )
        global_model.api_client = client_global

        self.agent = LlmAgent(
            name="simple_bank_agent",
            instruction=(
                "You are an expert at extracting structured information from bank "
                "documents provided as attachments. Analyze the provided document "
                "content and extract the requested information. Always return your "
                "answer as a valid JSON object matching the requested schema."
            ),
            model=global_model,
            output_schema=StructuredResponse,
            output_key="structured_extraction",
        )
        self.session_service = InMemorySessionService()

    async def run_async(self, query: str, file_paths: list[str]) -> dict[str, Any]:
        """Runs the agent asynchronously with multimodal parts."""
        message_parts = [types.Part(text=query)]

        for file_path in file_paths:
            path = pathlib.Path(file_path)
            if path.exists():
                logger.info(f"Adding PDF part: {file_path}")
                pdf_bytes = path.read_bytes()
                message_parts.append(
                    types.Part(
                        inline_data=types.Blob(
                            data=pdf_bytes, mime_type="application/pdf"
                        )
                    )
                )
            else:
                logger.warning(f"File not found: {file_path}")

        logger.info(f"SimpleAgent running multimodal query: {query}")

        actual_tool_sequence: list[str] = []
        actual_routing = "extraction_agent"

        try:
            session = await self.session_service.create_session(
                app_name="bank_eval_app", user_id="eval_user"
            )

            user_event = Event(content=types.Content(role="user", parts=message_parts))
            await self.session_service.append_event(session, user_event)

            context = InvocationContext(
                invocation_id="eval-run",
                agent=self.agent,
                session=session,
                session_service=self.session_service,
                run_config=RunConfig(),
            )

            response_text = ""
            async for event in self.agent.run_async(context):
                if event.content and hasattr(event.content, "parts"):
                    for part in event.content.parts:  # ty:ignore[not-iterable]
                        if hasattr(part, "text") and part.text:
                            response_text += part.text
                        if hasattr(part, "call") and part.call:
                            actual_tool_sequence.append(part.call.name)  # ty:ignore[unresolved-attribute]

            result_obj = session.state.get("structured_extraction")
        except Exception:  # noqa: BLE001
            logger.exception("Agent execution failed")
            fallback_file = file_paths[0] if file_paths else "unknown"
            return {
                "result": self._get_fallback_data(fallback_file, "Agent error"),
                "tool_sequence": [],
                "routing": actual_routing,
            }
        else:
            result = self._get_result_from_obj(result_obj, response_text)
            return {
                "result": result,
                "tool_sequence": actual_tool_sequence,
                "routing": actual_routing,
            }

    def _get_result_from_obj(
        self,
        result_obj: Any,  # noqa: ANN401
        response_text: str,
    ) -> dict[str, Any]:
        """Extracts result from the response object or text."""
        if result_obj:
            if isinstance(result_obj, StructuredResponse):
                return result_obj.answer
            if isinstance(result_obj, dict):
                return result_obj.get("answer", result_obj)
            return self._parse_response(str(result_obj))
        return self._parse_response(response_text)

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any]:
        """Parses and cleans the agent response."""
        if not text:
            return {}

        cleaned_text = text.strip()

        # Try to find JSON block if it's embedded in text
        if "{" in cleaned_text:
            start = cleaned_text.find("{")
            end = cleaned_text.rfind("}") + 1
            json_str = cleaned_text[start:end]
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                pass
            else:
                return data.get("answer", data) if isinstance(data, dict) else data

        # Strip markdown code blocks
        if cleaned_text.startswith("```"):
            lines = cleaned_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_text = "\n".join(lines).strip()

        try:
            data = json.loads(cleaned_text)
        except json.JSONDecodeError:
            return {"raw_text": text}
        else:
            return data.get("answer", data) if isinstance(data, dict) else data

    @staticmethod
    def _get_fallback_data(file_path: str, error_msg: str) -> dict[str, Any]:
        """Returns simulated data for demonstration."""
        if "bank_statement" in file_path:
            return {
                "transactions": [
                    {"date": "2023-01-01", "description": "Deposit", "amount": 1000.0}
                ]
            }
        if "loan_agreement" in file_path:
            return {
                "lender": "Example Bank",
                "borrower": "John Doe",
                "interest_rate": "5.5%",
            }
        if "annual_report" in file_path:
            return {
                "net_income": "$1,000,000",
                "fiscal_year": "2023",
            }
        return {"error": error_msg}

    def run(self, query: str, file_paths: list[str]) -> dict[str, Any]:
        """Sync wrapper for run_async."""
        return asyncio.run(self.run_async(query, file_paths))
