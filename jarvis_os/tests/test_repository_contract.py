"""
Contract Test for RepositoryPort.
"""
import unittest
from datetime import datetime
from typing import List, Optional
from jarvis_os.core.ports.repository import RepositoryPort, ConfigRepositoryPort, LogRepositoryPort
from jarvis_os.core.domain.entities import ConfigEntry, LogRecord
from jarvis_os.core.domain.exceptions import RepositoryException

class TestRepositoryPortContract(unittest.TestCase):
    """Verifies that RepositoryPort interfaces conform to design specifications."""

    def test_interfaces_are_abstract(self):
        """Asserts that repository interfaces cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            RepositoryPort()  # type: ignore
        with self.assertRaises(TypeError):
            ConfigRepositoryPort()  # type: ignore
        with self.assertRaises(TypeError):
            LogRepositoryPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompleteRepo(ConfigRepositoryPort):
            pass

        with self.assertRaises(TypeError):
            IncompleteRepo()  # type: ignore

    def test_config_repository_signatures(self):
        """Asserts that a fully-conforming ConfigRepositoryPort mock can be instantiated and operated."""
        class MockConfigRepo(ConfigRepositoryPort):
            def __init__(self):
                self._items = {}

            def save(self, entity: ConfigEntry) -> None:
                if entity.key == "fail":
                    raise RepositoryException("DB error")
                self._items[entity.key] = entity

            def get_by_id(self, entity_id: str) -> Optional[ConfigEntry]:
                return self.get_by_key(entity_id)

            def delete(self, entity_id: str) -> None:
                if entity_id in self._items:
                    del self._items[entity_id]

            def list_all(self) -> List[ConfigEntry]:
                return list(self._items.values())

            def get_by_key(self, key: str) -> Optional[ConfigEntry]:
                return self._items.get(key)

        repo = MockConfigRepo()
        self.assertIsInstance(repo, ConfigRepositoryPort)
        
        entry = ConfigEntry(key="test.key", value="val", value_type="str", description="test desc")
        repo.save(entry)
        
        self.assertEqual(repo.get_by_key("test.key"), entry)
        self.assertEqual(repo.get_by_id("test.key"), entry)
        
        # Test failure propagation
        fail_entry = ConfigEntry(key="fail", value="val", value_type="str", description="fail desc")
        with self.assertRaises(RepositoryException):
            repo.save(fail_entry)

    def test_log_repository_signatures(self):
        """Asserts that a fully-conforming LogRepositoryPort mock can be instantiated and operated."""
        class MockLogRepo(LogRepositoryPort):
            def __init__(self):
                self._logs = []

            def save(self, entity: LogRecord) -> None:
                self._logs.append(entity)

            def get_by_id(self, entity_id: str) -> Optional[LogRecord]:
                return None

            def delete(self, entity_id: str) -> None:
                pass

            def list_all(self) -> List[LogRecord]:
                return self._logs

            def get_logs_by_level(self, level: str) -> List[LogRecord]:
                return [l for l in self._logs if l.level == level]

            def purge_old_logs(self, before_timestamp: str) -> int:
                before = datetime.fromisoformat(before_timestamp)
                old_len = len(self._logs)
                self._logs = [l for l in self._logs if l.timestamp >= before]
                return old_len - len(self._logs)

        repo = MockLogRepo()
        self.assertIsInstance(repo, LogRepositoryPort)
        
        log1 = LogRecord(timestamp=datetime(2026, 1, 1), level="INFO", message="log 1", module="core")
        log2 = LogRecord(timestamp=datetime(2026, 2, 1), level="ERROR", message="log 2", module="core")
        
        repo.save(log1)
        repo.save(log2)
        
        self.assertEqual(len(repo.get_logs_by_level("ERROR")), 1)
        
        purged = repo.purge_old_logs("2026-01-15T00:00:00")
        self.assertEqual(purged, 1)
        self.assertEqual(len(repo.list_all()), 1)

if __name__ == "__main__":
    unittest.main()
