from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    """Token budget for prompt assembly."""

    max_prompt_tokens: int

