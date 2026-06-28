from __future__ import annotations

import threading
from typing import Dict, List, Tuple

from jarvis_os.core.memory.models import MemoryRecord, MemoryType
from jarvis_os.core.retrieval.models import RetrievalRequest, RetrievalResult, RetrievalStrategy
from jarvis_os.core.ports.repository import RepositoryPort
from jarvis_os.core.domain.exceptions import RepositoryException


class Retriever:
    """Retrieves relevant memories using deterministic ranking and filtering."""

    def __init__(self, repository: RepositoryPort[MemoryRecord]) -> None:
        self._repository = repository
        self._lock = threading.RLock()

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        if request.top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        with self._lock:
            try:
                all_records = self._repository.list_all()
            except RepositoryException as exc:
                raise RepositoryException(f"Failed to retrieve memories: {exc}") from exc

            records = [r for r in all_records if not r.is_expired()]
            records = self._filter_by_type(records, request.memory_types)
            records = self._filter_by_metadata(records, request.metadata_filters)

            ranked = self._rank(records, request)
            return RetrievalResult(records=tuple(ranked[: request.top_k]), total_matches=len(ranked))

    def _filter_by_type(self, records: List[MemoryRecord], memory_types: Tuple[MemoryType, ...]) -> List[MemoryRecord]:
        if not memory_types:
            return records
        return [record for record in records if record.memory_type in memory_types]

    def _filter_by_metadata(self, records: List[MemoryRecord], metadata_filters: Dict[str, object]) -> List[MemoryRecord]:
        if not metadata_filters:
            return records
        return [record for record in records if all(record.metadata.get(k) == v for k, v in metadata_filters.items())]

    def _rank(self, records: List[MemoryRecord], request: RetrievalRequest) -> List[MemoryRecord]:
        if request.strategy == RetrievalStrategy.IMPORTANCE:
            return sorted(
                records,
                key=lambda record: (
                    -int(record.importance.value),
                    record.created_at,
                    record.id,
                ),
            )

        query_lower = request.query_text.lower().strip()
        def score(record: MemoryRecord) -> Tuple[int, int, str]:
            content_lower = record.content.lower()
            if not query_lower:
                return (-int(record.importance.value), record.created_at, record.id)
            keyword_count = content_lower.count(query_lower)
            return (-keyword_count, -int(record.importance.value), record.created_at, record.id)

        ranked = sorted(records, key=score)
        # preserve deterministic ordering for zero-score records
        if query_lower:
            ranked = [r for r in ranked if r.content.lower().count(query_lower) > 0] + [r for r in ranked if r.content.lower().count(query_lower) == 0]
        return ranked
