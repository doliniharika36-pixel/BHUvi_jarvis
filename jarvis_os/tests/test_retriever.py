"""Unit tests for the Retriever subsystem."""
import unittest
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from jarvis_os.core.memory.models import MemoryImportance, MemoryRecord, MemoryType
from jarvis_os.core.retrieval.models import RetrievalRequest, RetrievalStrategy
from jarvis_os.core.retrieval.retriever import Retriever
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


class TestRetriever(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryMemoryRepository()
        self.retriever = Retriever(self.repo)

    def test_retrieve_top_k_by_keyword(self) -> None:
        records = [
            MemoryRecord(id="r1", content="hello jarvis", memory_type=MemoryType.CONVERSATION),
            MemoryRecord(id="r2", content="hello world", memory_type=MemoryType.CONVERSATION),
            MemoryRecord(id="r3", content="something else", memory_type=MemoryType.CONVERSATION),
        ]
        for record in records:
            self.repo.save(record)

        result = self.retriever.retrieve(RetrievalRequest(query_text="hello", top_k=2))
        self.assertEqual(result.total_matches, 3)
        self.assertEqual([r.id for r in result.records], ["r1", "r2"])

    def test_retrieve_by_memory_type_and_metadata(self) -> None:
        records = [
            MemoryRecord(id="r1", content="alpha", memory_type=MemoryType.USER_PROFILE, metadata={"tag": "keep"}),
            MemoryRecord(id="r2", content="beta", memory_type=MemoryType.CONVERSATION, metadata={"tag": "keep"}),
        ]
        for record in records:
            self.repo.save(record)

        request = RetrievalRequest(
            query_text="",
            memory_types=(MemoryType.USER_PROFILE,),
            metadata_filters={"tag": "keep"},
            top_k=5,
        )
        result = self.retriever.retrieve(request)
        self.assertEqual(result.total_matches, 1)
        self.assertEqual(result.records[0].id, "r1")

    def test_importance_ranking_orders_by_importance(self) -> None:
        records = [
            MemoryRecord(id="r1", content="x", memory_type=MemoryType.USER_PROFILE, importance=MemoryImportance.LOW),
            MemoryRecord(id="r2", content="x", memory_type=MemoryType.USER_PROFILE, importance=MemoryImportance.HIGH),
        ]
        for record in records:
            self.repo.save(record)
        result = self.retriever.retrieve(
            RetrievalRequest(query_text="", strategy=RetrievalStrategy.IMPORTANCE, top_k=5)
        )
        self.assertEqual([r.id for r in result.records], ["r2", "r1"])

    def test_zero_top_k_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.retriever.retrieve(RetrievalRequest(query_text="x", top_k=0))

    def test_expired_records_are_skipped(self) -> None:
        self.repo.save(
            MemoryRecord(
                id="e1",
                content="expired",
                memory_type=MemoryType.USER_PROFILE,
                expires_at=datetime.utcnow() - timedelta(seconds=1),
            )
        )
        result = self.retriever.retrieve(RetrievalRequest(query_text="expired", top_k=5))
        self.assertEqual(result.total_matches, 0)

    def test_repository_failure_bubbles(self) -> None:
        class BadRepository(InMemoryMemoryRepository):
            def list_all(self) -> List[MemoryRecord]:
                raise RepositoryException("read failed")

        bad_repo = BadRepository()
        retriever = Retriever(bad_repo)
        with self.assertRaises(RepositoryException):
            retriever.retrieve(RetrievalRequest(query_text="x", top_k=1))


if __name__ == "__main__":
    unittest.main()
