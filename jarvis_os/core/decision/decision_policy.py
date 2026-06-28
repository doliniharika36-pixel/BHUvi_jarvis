from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from .exceptions import DecisionError
from .models import DecisionContext, DecisionResult, DecisionType


class DecisionPolicy(ABC):
    """Policy separating deterministic routing rules from the engine."""

    @abstractmethod
    def decide(self, ctx: DecisionContext) -> DecisionResult:
        raise NotImplementedError


class DefaultDecisionPolicy(DecisionPolicy):
    """Deterministic rule-based policy.

    Priority order:
      1) Clarification
      2) Tool execution planning
      3) Document retrieval
      4) Memory retrieval
      5) Direct LLM response
    """

    def decide(self, ctx: DecisionContext) -> DecisionResult:
        if not isinstance(ctx.request_text, str) or not ctx.request_text.strip():
            raise DecisionError("request_text must be a non-empty string")

        why: Dict[str, object] = {
            "requires_clarification": ctx.requires_clarification,
            "requires_tools": ctx.requires_tools,
            "requires_documents": ctx.requires_documents,
            "requires_memory": ctx.requires_memory,
            "tool_candidates": list(ctx.tool_candidates),
        }

        if ctx.requires_clarification:
            return DecisionResult(
                decision_type=DecisionType.CLARIFICATION,
                reason="Clarification required by upstream signals.",
                why=why,
            )

        if ctx.requires_tools:
            return DecisionResult(
                decision_type=DecisionType.TOOL_EXECUTION_PLAN,
                reason="Tool execution is required; returning planning-only tool list.",
                why=why,
                tool_plan=ctx.tool_candidates,
            )

        if ctx.requires_documents:
            return DecisionResult(
                decision_type=DecisionType.DOCUMENT_RETRIEVAL,
                reason="Document retrieval is required by upstream signals.",
                why=why,
            )

        if ctx.requires_memory:
            return DecisionResult(
                decision_type=DecisionType.MEMORY_RETRIEVAL,
                reason="Memory retrieval is required by upstream signals.",
                why=why,
            )

        return DecisionResult(
            decision_type=DecisionType.DIRECT_LLM_RESPONSE,
            reason="No retrieval/tool/planning required; direct LLM response.",
            why=why,
        )

