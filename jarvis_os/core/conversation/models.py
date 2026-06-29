from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ConversationMetadata:
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Optional[ConversationMetadata] = None


@dataclass(frozen=True)
class ConversationRequest:
    message: ConversationMessage
    session_id: Optional[str] = None
    metadata: Optional[ConversationMetadata] = None


@dataclass(frozen=True)
class ConversationResponse:
    session_id: str
    message: ConversationMessage
    metadata: Optional[ConversationMetadata] = None
