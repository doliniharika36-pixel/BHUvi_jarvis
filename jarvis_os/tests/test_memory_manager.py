"""Unit tests for the MemoryManager subsystem."""
import unittest
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from jarvis_os.core.memory.exceptions import MemoryError, MemoryNotFoundError, MemoryValidationError
from jarvis_os.core.memory.memory_manager import MemoryManager
from jarvis_os.core.memory.models import MemoryImportance, MemoryQuery, MemoryRecord, MemoryType
from jarvis_os.core.domain.exceptions import RepositoryException


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self._store: Dict[str, MemoryRecord] = {}

    def save(self, entity: MemoryRecord) -> None:
        if entity.id == "fail":
            raise RepositoryException("persist failed")
        self._store[entity.id] = entity

    def get_by_id(self, entity_id: str) -> Optional[MemoryRecord]:
        return self._store.get(entity_id)

    def delete(self, entity_id: str) -> None:
        if entity_id in self._store:
            del self._store[entity_id]

    def list_all(self) -> List[MemoryRecord]:
        return list(self._store.values())


class TestMemoryManager(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryMemoryRepository()
        self.manager = MemoryManager(self.repo)

    def test_create_and_read_memory(self) -> None:
        record = MemoryRecord(
            id="m1",
            content="test content",
            memory_type=MemoryType.USER_PROFILE,
            importance=MemoryImportance.HIGH,
        )
        self.manager.create(record)
        loaded = self.manager.read("m1")
        self.assertEqual(loaded, record)

    def test_read_missing_raises_not_found(self) -> None:
        with self.assertRaises(MemoryNotFoundError):
            self.manager.read("missing")

    def test_update_existing_memory(self) -> None:
        record = MemoryRecord(
            id="m2",
            content="value",
            memory_type=MemoryType.USER_PROFILE,
        )
        self.manager.create(record)
        updated = MemoryRecord(
            id="m2",
            content="new value",
            memory_type=MemoryType.USER_PROFILE,
        )
        self.manager.update(updated)
        self.assertEqual(self.manager.read("m2").content, "new value")

    def test_delete_existing_memory(self) -> None:
        record = MemoryRecord(
            id="m3",
            content="delete me",
            memory_type=MemoryType.USER_PROFILE,
        )
        self.manager.create(record)
        self.manager.delete("m3")
        with self.assertRaises(MemoryNotFoundError):
            self.manager.read("m3")

    def test_query_filters_by_text_and_type(self) -> None:
        records = [
            MemoryRecord(id="q1", content="hello world", memory_type=MemoryType.CONVERSATION),
            MemoryRecord(id="q2", content="hello jarvis", memory_type=MemoryType.USER_PROFILE),
            MemoryRecord(id="q3", content="unrelated stuff", memory_type=MemoryType.USER_PROFILE),
        ]
        for record in records:
            self.manager.create(record)
        result = self.manager.query(
            MemoryQuery(text="hello", memory_types=(MemoryType.USER_PROFILE,), top_k=10)
        )
        self.assertEqual(result.total_matches, 1)
        self.assertEqual(result.records[0].id, "q2")

    def test_query_returns_top_k_by_importance(self) -> None:
        records = [
            MemoryRecord(id="t1", content="item one", memory_type=MemoryType.USER_PROFILE, importance=MemoryImportance.LOW),
            MemoryRecord(id="t2", content="item two", memory_type=MemoryType.USER_PROFILE, importance=MemoryImportance.HIGH),
            MemoryRecord(id="t3", content="item three", memory_type=MemoryType.USER_PROFILE, importance=MemoryImportance.MEDIUM),
        ]
        for record in records:
            self.manager.create(record)
        result = self.manager.query(MemoryQuery(text="item", top_k=2))
        self.assertEqual([r.id for r in result.records], ["t2", "t3"])
        self.assertEqual(result.total_matches, 3)

    def test_expired_records_are_not_visible(self) -> None:
        expired = MemoryRecord(
            id="e1",
            content="expired",
            memory_type=MemoryType.USER_PROFILE,
            expires_at=datetime.utcnow() - timedelta(seconds=1),
        )
        self.manager.create(expired)
        with self.assertRaises(MemoryNotFoundError):
            self.manager.read("e1")
        query_result = self.manager.query(MemoryQuery(text="expired", top_k=5))
        self.assertEqual(query_result.total_matches, 0)

    def test_conversation_history_returns_ordered_messages(self) -> None:
        records = [
            MemoryRecord(
                id="h1",
                content="first message",
                memory_type=MemoryType.CONVERSATION,
                metadata={"role": "user"},
                created_at=datetime(2026, 1, 1, 0, 0, 0),
            ),
            MemoryRecord(
                id="h2",
                content="second message",
                memory_type=MemoryType.CONVERSATION,
                metadata={"role": "assistant"},
                created_at=datetime(2026, 1, 1, 0, 0, 1),
            ),
        ]
        for record in records:
            self.manager.create(record)
        history = self.manager.conversation_history(limit=10)
        self.assertEqual([m.content for m in history], ["first message", "second message"])
        self.assertEqual(history[0].role, "user")

    def test_user_profile_returns_profile_map(self) -> None:
        records = [
            MemoryRecord(id="p1", content="Alice", memory_type=MemoryType.USER_PROFILE),
            MemoryRecord(id="p2", content="Engineer", memory_type=MemoryType.USER_PROFILE),
        ]
        for record in records:
            self.manager.create(record)
        profile = self.manager.user_profile()
        self.assertEqual(profile, {"p1": "Alice", "p2": "Engineer"})

    def test_create_invalid_memory_raises_validation(self) -> None:
        invalid = MemoryRecord(id="", content="", memory_type=MemoryType.USER_PROFILE)
        with self.assertRaises(MemoryValidationError):
            self.manager.create(invalid)

    def test_repository_errors_raise_memory_error(self) -> None:
        failing_repo = InMemoryMemoryRepository()
        manager = MemoryManager(failing_repo)
        with self.assertRaises(MemoryError):
            manager.create(MemoryRecord(id="fail", content="x", memory_type=MemoryType.USER_PROFILE))


if __name__ == "__main__":
    unittest.main()
