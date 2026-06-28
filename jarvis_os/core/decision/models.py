from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class DecisionType(str, Enum):
    DIRECT_LLM_RESPONSE = "direct_llm_response"
    MEMORY_RETRIEVAL = "memory_retrieval"
    DOCUMENT_RETRIEVAL = "document_retrieval"
    TOOL_EXECUTION_PLAN = "tool_execution_plan"
    CLARIFICATION = "clarification"


@dataclass(frozen=True)
class DecisionContext:
    request_text: str

    # Optional intent label from upstream
    user_intent: Optional[str] = None

    # Precomputed signals from orchestration layers
    requires_memory: bool = False
    requires_documents: bool = False
    requires_tools: bool = False
    requires_clarification: bool = False

    # Tool candidate names for planning-only
    tool_candidates: Tuple[str, ...] = field(default_factory=tuple)

    # Arbitrary metadata for diagnostics (must be deterministic)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionResult:
    decision_type: DecisionType
    reason: str
    why: Dict[str, Any] = field(default_factory=dict)
    tool_plan: Tuple[str, ...] = field(default_factory=tuple)

