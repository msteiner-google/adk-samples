"""Token usage accounting primitives.

Separated from `pricing` (which turns tokens into dollars) and from
`accounting` (which collects them from a live run) so that each piece can be
tested without the other two.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from google.genai import types


class TokenUsage(BaseModel):
    """Token counts for one or more model calls.

    Field names mirror `google.genai.types.GenerateContentResponseUsageMetadata`.

    Two relationships hold for Gemini and both matter for costing:

    - `thoughts` is NOT part of `candidates`; `total` is the sum of `prompt`,
      `candidates` and `thoughts`.
    - `cached` is a SUBSET of `prompt`. Uncached (full-price) input is therefore
      `prompt - cached`, which is what `billable_input` returns.
    """

    prompt: int = Field(default=0, description="Input tokens, cached ones included")
    cached: int = Field(default=0, description="Input tokens served from cache")
    candidates: int = Field(default=0, description="Visible output tokens")
    thoughts: int = Field(default=0, description="Internal reasoning tokens")
    total: int = Field(default=0, description="Total tokens reported by the API")
    calls: int = Field(default=0, description="Number of model calls aggregated")

    @property
    def billable_input(self) -> int:
        """Input tokens charged at the full (uncached) rate."""
        return max(self.prompt - self.cached, 0)

    @property
    def billable_output(self) -> int:
        """Output tokens charged at the output rate, reasoning included."""
        return self.candidates + self.thoughts

    @property
    def thinking_ratio(self) -> float:
        """Share of generated tokens spent on reasoning, between 0.0 and 1.0.

        Returns 0.0 when nothing was generated, so this is safe to average over
        a run that contains tool-only turns.
        """
        generated = self.billable_output
        if generated == 0:
            return 0.0
        return self.thoughts / generated

    def __add__(self, other: TokenUsage) -> TokenUsage:
        """Adds two usage records field by field."""
        return TokenUsage(
            prompt=self.prompt + other.prompt,
            cached=self.cached + other.cached,
            candidates=self.candidates + other.candidates,
            thoughts=self.thoughts + other.thoughts,
            total=self.total + other.total,
            calls=self.calls + other.calls,
        )

    @classmethod
    def from_usage_metadata(
        cls, metadata: types.GenerateContentResponseUsageMetadata | None
    ) -> Self:
        """Builds a `TokenUsage` from one API response's usage metadata.

        Every count is optional in the API, so each missing field is read as 0.
        A `None` metadata yields an all-zero record with `calls=0`, which keeps
        responses that carry no usage block (streaming partials, cached early
        exits) from inflating the call count.
        """
        if metadata is None:
            return cls()
        return cls(
            prompt=metadata.prompt_token_count or 0,
            cached=metadata.cached_content_token_count or 0,
            candidates=metadata.candidates_token_count or 0,
            thoughts=metadata.thoughts_token_count or 0,
            total=metadata.total_token_count or 0,
            calls=1,
        )
