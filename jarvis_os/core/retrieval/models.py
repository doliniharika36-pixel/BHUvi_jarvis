from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from jarvis_os.core.memory.models import MemoryRecord, MemoryType


class RetrievalStrategy(str, Enum):
    KEYWORD = "keyword"
    IMPORTANCE = "importance"


@dataclass(frozen=True)
class RetrievalRequest:
    query_text: str
    top_k: int = 5
    memory_types: Tuple[MemoryType, ...] = field(default_factory=tuple)
    metadata_filters: Dict[str, Any] = field(default_factory=dict)
    strategy: RetrievalStrategy = RetrievalStrategy.KEYWORD


@dataclass(frozen=True)
class RetrievalResult:
    records: Tuple[MemoryRecord, ...]
    total_matches: int
