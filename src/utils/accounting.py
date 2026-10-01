"""An ADK plugin that records per-agent token usage and cost for every run.

Attach it to an `App` rather than a `Runner`: ADK's agent loader looks for an
`app` attribute before `root_agent` (`cli/utils/agent_loader.py`), and the
eval harness merges `app.plugins` with its own internal ones, so a plugin
declared on the App is active under `adk eval` and `adk optimize` as well as
in normal serving.
"""

from __future__ import annotations

import json
import pathlib
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from google.adk.plugins.base_plugin import BasePlugin
from pydantic import BaseModel, Field

from src.utils.pricing import UnknownModelError, estimate_cost
from src.utils.usage import TokenUsage

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.models.llm_response import LlmResponse

DEFAULT_USAGE_LOG = pathlib.Path("reports/token_usage.jsonl")

_UNKNOWN_MODEL = "unknown"
_UNKNOWN_APP = "unknown"


class UsageRecord(BaseModel):
    """Aggregated usage for one (app, agent, model) triple in one invocation."""

    app_name: str = Field(
        default=_UNKNOWN_APP,
        description="Owning App, so reports can total cost per agent app",
    )
    invocation_id: str
    agent_name: str
    model: str
    usage: TokenUsage
    total_usd: float | None = Field(
        default=None,
        description="None when the model has no entry in the pricing table",
    )
    thinking_usd: float | None = None


class TokenAccountantPlugin(BasePlugin):
    """Collects token usage from every model response and writes it to JSONL.

    Usage is keyed by (invocation, agent, model) so that a multi-agent run
    such as `layout_aware_agent` attributes its spend to the orchestrator, the
    analyst and the extractor separately, which is what makes a thinking-budget
    comparison legible.

    Costing is best-effort: a model missing from the pricing table still gets
    its tokens recorded, with the dollar fields left as None. Token data is
    the measurement, dollars are the interpretation, and losing the former to
    a stale rate table would be the worse failure.
    """

    def __init__(
        self,
        name: str = "token_accountant",
        output_path: pathlib.Path | None = None,
        app_name: str | None = None,
        *,
        write_on_run_end: bool = True,
    ) -> None:
        """Initialises the accountant.

        Args:
          name: Plugin name, as required by ADK's plugin manager.
          output_path: JSONL file to append to. Defaults to
            `reports/token_usage.jsonl`.
          app_name: Fallback App name for records, used when the session does
            not carry one. Normally left unset.
          write_on_run_end: Whether to flush automatically when a run finishes.
            Set False to collect in-process and flush by hand, which is what
            the benchmark script does.
        """
        super().__init__(name=name)
        self._output_path = output_path or DEFAULT_USAGE_LOG
        self._app_name = app_name
        self._write_on_run_end = write_on_run_end
        self._records: dict[tuple[str, str, str, str], UsageRecord] = {}
        self._lock = threading.Lock()

    def _resolve_app_name(self, callback_context: CallbackContext) -> str:
        """Finds the App name for a record, preferring the live session."""
        session = getattr(callback_context, "session", None)
        return getattr(session, "app_name", None) or self._app_name or _UNKNOWN_APP

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> None:
        """Adds one model response's usage to the running totals."""
        if llm_response.partial:
            # Streaming chunks repeat cumulative counts; only the final
            # response for a turn carries the authoritative usage block.
            return

        usage = TokenUsage.from_usage_metadata(llm_response.usage_metadata)
        if usage.calls == 0:
            return

        key = (
            self._resolve_app_name(callback_context),
            callback_context.invocation_id,
            callback_context.agent_name,
            llm_response.model_version or _UNKNOWN_MODEL,
        )
        with self._lock:
            existing = self._records.get(key)
            merged = existing.usage + usage if existing else usage
            self._records[key] = UsageRecord(
                app_name=key[0],
                invocation_id=key[1],
                agent_name=key[2],
                model=key[3],
                usage=merged,
            )

    async def after_run_callback(
        self, *, invocation_context: InvocationContext
    ) -> None:
        """Flushes collected usage to disk at the end of a run."""
        del invocation_context
        if self._write_on_run_end:
            self.flush()

    def snapshot(self) -> list[UsageRecord]:
        """Returns the collected records, each costed where possible."""
        with self._lock:
            records = list(self._records.values())
        return [self._with_cost(record) for record in records]

    def totals(self) -> TokenUsage:
        """Returns usage summed across every agent and model seen so far."""
        total = TokenUsage()
        for record in self.snapshot():
            total += record.usage
        return total

    def reset(self) -> None:
        """Drops everything collected so far."""
        with self._lock:
            self._records.clear()

    def flush(self) -> pathlib.Path | None:
        """Appends the collected records to the JSONL log and resets.

        Returns the path written to, or None when there was nothing to write.
        """
        records = self.snapshot()
        if not records:
            return None

        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()
        with self._output_path.open("a", encoding="utf-8") as handle:
            for record in records:
                line = {"timestamp": timestamp, **record.model_dump()}
                handle.write(json.dumps(line) + "\n")

        self.reset()
        return self._output_path

    @staticmethod
    def _with_cost(record: UsageRecord) -> UsageRecord:
        """Attaches dollar figures, leaving them None for unpriced models."""
        try:
            cost = estimate_cost(record.usage, record.model)
        except UnknownModelError:
            return record
        return record.model_copy(
            update={"total_usd": cost.total_usd, "thinking_usd": cost.thinking_usd}
        )
