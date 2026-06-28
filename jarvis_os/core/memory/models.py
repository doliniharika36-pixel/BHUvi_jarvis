from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple


class MemoryType(str, Enum):
    CONVERSATION = "conversation"
    USER_PROFILE = "user_profile"
    SYSTEM = "system"


class MemoryImportance(int, Enum):
    LOW = 1
    MEDIUM = 5
    HIGH = 10


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    content: str
    memory_type: MemoryType
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    importance: MemoryImportance = MemoryImportance.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, as_of: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        as_of = as_of or datetime.utcnow()
        return as_of >= self.expires_at


@dataclass(frozen=True)
class MemoryQuery:
    text: str
    memory_types: Sequence[MemoryType] = field(default_factory=tuple)
    metadata_filters: Dict[str, Any] = field(default_factory=dict)
    top_k: int = 5


@dataclass(frozen=True)
class MemoryResult:
    records: Tuple[MemoryRecord, ...]
    total_matches: int
