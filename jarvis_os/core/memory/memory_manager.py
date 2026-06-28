from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from jarvis_os.core.domain.exceptions import RepositoryException
from jarvis_os.core.domain.entities import LLMMessage
from jarvis_os.core.memory.exceptions import MemoryError, MemoryNotFoundError, MemoryValidationError
from jarvis_os.core.memory.models import MemoryImportance, MemoryQuery, MemoryRecord, MemoryResult, MemoryType
from jarvis_os.core.ports.repository import RepositoryPort


class MemoryManager:
    """In-memory manager for memory records with persistence through repository ports."""

    def __init__(
        self,
        repository: RepositoryPort[MemoryRecord],
    ) -> None:
        self._repository = repository
        self._lock = threading.RLock()

    def create(self, record: MemoryRecord) -> None:
        if not record.id or not record.content or not isinstance(record.memory_type, MemoryType):
            raise MemoryValidationError("MemoryRecord.id, content, and memory_type are required")
        with self._lock:
            try:
                self._repository.save(record)
            except RepositoryException as exc:
                raise MemoryError(f"Failed to create memory record: {exc}") from exc

    def read(self, record_id: str) -> MemoryRecord:
        if not record_id:
            raise MemoryValidationError("record_id is required")
        with self._lock:
            try:
                record = self._repository.get_by_id(record_id)
            except RepositoryException as exc:
                raise MemoryError(f"Failed to read memory record: {exc}") from exc

            if record is None or record.is_expired():
                raise MemoryNotFoundError(f"Memory record '{record_id}' not found or expired")

            return record

    def update(self, record: MemoryRecord) -> None:
        if not record.id:
            raise MemoryValidationError("MemoryRecord.id is required for update")
        with self._lock:
            existing = self._repository.get_by_id(record.id)
            if existing is None or existing.is_expired():
                raise MemoryNotFoundError(f"Memory record '{record.id}' not found or expired")
            try:
                self._repository.save(record)
            except RepositoryException as exc:
                raise MemoryError(f"Failed to update memory record: {exc}") from exc

    def delete(self, record_id: str) -> None:
        if not record_id:
            raise MemoryValidationError("record_id is required")
        with self._lock:
            try:
                existing = self._repository.get_by_id(record_id)
            except RepositoryException as exc:
                raise MemoryError(f"Failed to delete memory record: {exc}") from exc
            if existing is None or existing.is_expired():
                raise MemoryNotFoundError(f"Memory record '{record_id}' not found or expired")
            try:
                self._repository.delete(record_id)
            except RepositoryException as exc:
                raise MemoryError(f"Failed to delete memory record: {exc}") from exc

    def query(self, query: MemoryQuery) -> MemoryResult:
        if not query.text and not query.memory_types and not query.metadata_filters:
            raise MemoryValidationError("At least one query parameter is required")
        with self._lock:
            try:
                all_records = self._repository.list_all()
            except RepositoryException as exc:
                raise MemoryError(f"Failed to query memory records: {exc}") from exc

            alive_records = [r for r in all_records if not r.is_expired()]
            filtered = self._apply_filters(alive_records, query)
            sorted_records = sorted(
                filtered,
                key=lambda record: (
                    -int(record.importance.value),
                    record.created_at,
                    record.id,
                ),
            )
            return MemoryResult(records=tuple(sorted_records[: query.top_k]), total_matches=len(filtered))

    def _apply_filters(self, records: Iterable[MemoryRecord], query: MemoryQuery) -> List[MemoryRecord]:
        filtered: List[MemoryRecord] = []
        for record in records:
            if query.memory_types and record.memory_type not in query.memory_types:
                continue
            if query.metadata_filters:
                if not all(record.metadata.get(k) == v for k, v in query.metadata_filters.items()):
                    continue
            if query.text:
                if query.text.lower() not in record.content.lower():
                    continue
            filtered.append(record)
        return filtered

    def conversation_history(self, limit: int = 50) -> List[LLMMessage]:
        if limit <= 0:
            raise MemoryValidationError("limit must be a positive integer")
        with self._lock:
            try:
                all_records = self._repository.list_all()
            except RepositoryException as exc:
                raise MemoryError(f"Failed to load conversation history: {exc}") from exc

            history = [
                r
                for r in all_records
                if r.memory_type == MemoryType.CONVERSATION and not r.is_expired()
            ]
            history.sort(key=lambda record: record.created_at)
            return [
                LLMMessage(role=record.metadata.get("role", "assistant"), content=record.content, timestamp=record.created_at)
                for record in history[-limit:]
            ]

    def user_profile(self) -> Dict[str, Any]:
        with self._lock:
            try:
                all_records = self._repository.list_all()
            except RepositoryException as exc:
                raise MemoryError(f"Failed to load user profile: {exc}") from exc

            profile = {}
            for record in all_records:
                if record.memory_type == MemoryType.USER_PROFILE and not record.is_expired():
                    profile[record.id] = record.content
            return profile
