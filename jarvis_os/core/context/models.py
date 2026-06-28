from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple


class ContextPriority(int, Enum):
    """Higher value means higher priority inclusion."""

    SYSTEM = 100
    MEMORY = 60
    DOCUMENT = 40
    RUNTIME = 20
    HISTORY = 10
    USER = 5


@dataclass(frozen=True)
class ContextSection:
    """A typed prompt section to be assembled into the final LLM input."""

    name: str
    priority: ContextPriority
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextAssemblyResult:
    """Immutable result of ContextBuilder.build()."""

    system_prompt: str
    prompt_messages: Tuple[Tuple[str, str], ...]
    included_sections: Tuple[ContextSection, ...]
    excluded_sections: Tuple[ContextSection, ...]
    budget: int
    warnings: Tuple[str, ...] = field(default_factory=tuple)

