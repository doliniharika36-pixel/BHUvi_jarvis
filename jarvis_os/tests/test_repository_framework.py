"""
Unit tests for the generic Repository Framework (BaseRepository, SQLiteRepository, RowMapper).
"""
from dataclasses import dataclass
import sqlite3
import threading
import unittest
from typing import Any, Dict, List, Optional

from jarvis_os.core.domain.exceptions import RepositoryException
from jarvis_os.infrastructure.database.connection import SQLiteConnectionManager
from jarvis_os.infrastructure.database.repository import RowMapper, SQLiteRepository


# ═══════════════════════════════════════════════════════════════════════ #
#  Mock Domain Entity & Mapper                                            #
# ═══════════════════════════════════════════════════════════════════════ #

@dataclass
class DummyEntity:
    """Mock domain entity for repository framework testing."""
    id: str
    name: str
    score: int


class DummyEntityMapper(RowMapper[DummyEntity]):
    """Mapper implementation for DummyEntity."""

    def to_domain(self, row: sqlite3.Row) -> DummyEntity:
        # Intentionally propagate custom errors if schema is invalid/missing columns
        return DummyEntity(
            id=row["id"],
            name=row["name"],
            score=row["score"],
        )

    def to_row(self, entity: DummyEntity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "name": entity.name,
            "score": entity.score,
        }


# ═══════════════════════════════════════════════════════════════════════ #
#  Test Suite                                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class TestRepositoryFramework(unittest.TestCase):
    """Test suite for the generic SQLiteRepository implementation."""

    def setUp(self) -> None:
        # Use a fresh in-memory database for each test
        self.db = SQLiteConnectionManager(":memory:")
        self.db.open()

        # Initialize the table needed for the dummy entity
        self.db.execute(
            """
            CREATE TABLE dummy_table (
                id    TEXT PRIMARY KEY,
                name  TEXT NOT NULL,
                score INTEGER NOT NULL
            );
            """
        )

        self.mapper = DummyEntityMapper()
        self.repo = SQLiteRepository[DummyEntity](
            connection_manager=self.db,
            table_name="dummy_table",
            pk_column="id",
            mapper=self.mapper,
        )

    def tearDown(self) -> None:
        self.db.close()

    # ------------------------------------------------------------------ #
    # CRUD - Create                                                        #
    # ------------------------------------------------------------------ #

    def test_save_inserts_new_entity(self) -> None:
        """save() successfully inserts a new entity when it does not exist."""
        entity = DummyEntity(id="e1", name="Alpha", score=100)
        self.repo.save(entity)

        # Inspect DB row directly to verify insertion
        row = self.db.fetch_one("SELECT * FROM dummy_table WHERE id = ?;", ("e1",))
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "Alpha")
        self.assertEqual(row["score"], 100)

    # ------------------------------------------------------------------ #
    # CRUD - Read                                                          #
    # ------------------------------------------------------------------ #

    def test_get_by_id_returns_entity(self) -> None:
        """get_by_id() fetches and maps an existing database record."""
        self.db.execute(
            "INSERT INTO dummy_table (id, name, score) VALUES (?, ?, ?);",
            ("e2", "Beta", 200),
        )

        entity = self.repo.get_by_id("e2")
        self.assertIsNotNone(entity)
        self.assertEqual(entity.id, "e2")
        self.assertEqual(entity.name, "Beta")
        self.assertEqual(entity.score, 200)

    def test_get_by_id_returns_none_for_missing(self) -> None:
        """get_by_id() returns None when the entity ID is not in the database."""
        entity = self.repo.get_by_id("non-existent")
        self.assertIsNone(entity)

    # ------------------------------------------------------------------ #
    # CRUD - Update                                                        #
    # ------------------------------------------------------------------ #

    def test_save_updates_existing_entity(self) -> None:
        """save() updates an existing record if primary key matches."""
        # Insert initial record
        self.db.execute(
            "INSERT INTO dummy_table (id, name, score) VALUES (?, ?, ?);",
            ("e3", "Gamma", 300),
        )

        # Update and save
        updated_entity = DummyEntity(id="e3", name="Gamma Updated", score=350)
        self.repo.save(updated_entity)

        # Verify database has updated values
        row = self.db.fetch_one("SELECT * FROM dummy_table WHERE id = ?;", ("e3",))
        self.assertEqual(row["name"], "Gamma Updated")
        self.assertEqual(row["score"], 350)

    # ------------------------------------------------------------------ #
    # CRUD - Delete                                                        #
    # ------------------------------------------------------------------ #

    def test_delete_removes_entity(self) -> None:
        """delete() removes the matching database row."""
        self.db.execute(
            "INSERT INTO dummy_table (id, name, score) VALUES (?, ?, ?);",
            ("e4", "Delta", 400),
        )

        self.repo.delete("e4")

        row = self.db.fetch_one("SELECT * FROM dummy_table WHERE id = ?;", ("e4",))
        self.assertIsNone(row)

    # ------------------------------------------------------------------ #
    # CRUD - List All                                                      #
    # ------------------------------------------------------------------ #

    def test_list_all_returns_all_entities(self) -> None:
        """list_all() returns all entities present in the table."""
        entities = [
            DummyEntity(id="e5", name="Epsilon", score=50),
            DummyEntity(id="e6", name="Zeta", score=60),
        ]
        for e in entities:
            self.repo.save(e)

        all_records = self.repo.list_all()
        self.assertEqual(len(all_records), 2)
        ids = {r.id for r in all_records}
        self.assertEqual(ids, {"e5", "e6"})

    # ------------------------------------------------------------------ #
    # Exception Translation                                                #
    # ------------------------------------------------------------------ #

    def test_save_handles_db_errors_safely(self) -> None:
        """Database errors during save() are wrapped in RepositoryException."""
        # Force a database constraint error (missing required column values, etc.)
        # Here we simulate table modification to make an operation fail
        self.db.execute("DROP TABLE dummy_table;")

        entity = DummyEntity(id="e1", name="Alpha", score=100)
        with self.assertRaises(RepositoryException):
            self.repo.save(entity)

    def test_get_by_id_handles_db_errors_safely(self) -> None:
        """Database errors during get_by_id() are wrapped in RepositoryException."""
        self.db.execute("DROP TABLE dummy_table;")
        with self.assertRaises(RepositoryException):
            self.repo.get_by_id("e1")

    def test_list_all_handles_db_errors_safely(self) -> None:
        """Database errors during list_all() are wrapped in RepositoryException."""
        self.db.execute("DROP TABLE dummy_table;")
        with self.assertRaises(RepositoryException):
            self.repo.list_all()

    def test_delete_handles_db_errors_safely(self) -> None:
        """Database errors during delete() are wrapped in RepositoryException."""
        self.db.execute("DROP TABLE dummy_table;")
        with self.assertRaises(RepositoryException):
            self.repo.delete("e1")

    # ------------------------------------------------------------------ #
    # Mapping Correctness & Error Isolation                                #
    # ------------------------------------------------------------------ #

    def test_mapping_failure_in_to_row_raises_repository_exception(self) -> None:
        """If RowMapper.to_row raises an exception, it is wrapped in RepositoryException."""
        def bad_to_row(entity):
            raise ValueError("Mapping calculation failed")

        self.mapper.to_row = bad_to_row  # type: ignore[assignment]
        entity = DummyEntity(id="e1", name="Alpha", score=100)

        with self.assertRaises(RepositoryException) as ctx:
            self.repo.save(entity)
        self.assertIn("Error mapping domain entity", str(ctx.exception))

    def test_mapping_failure_in_to_domain_raises_repository_exception(self) -> None:
        """If RowMapper.to_domain raises an exception, it is wrapped in RepositoryException."""
        # Populate DB directly
        self.db.execute("INSERT INTO dummy_table VALUES (?, ?, ?);", ("e1", "Alpha", 100))

        def bad_to_domain(row):
            raise KeyError("Missing critical schema field mapping")

        self.mapper.to_domain = bad_to_domain  # type: ignore[assignment]

        with self.assertRaises(RepositoryException) as ctx:
            self.repo.get_by_id("e1")
        self.assertIn("Error mapping database row", str(ctx.exception))

    # ------------------------------------------------------------------ #
    # Transaction & Rollback                                               #
    # ------------------------------------------------------------------ #

    def test_transaction_commits_group_on_success(self) -> None:
        """Multiple operations commit as a single atomic unit."""
        with self.repo.transaction():
            self.repo.save(DummyEntity(id="e7", name="Eta", score=70))
            self.repo.save(DummyEntity(id="e8", name="Theta", score=80))

        # Verify both persisted
        self.assertIsNotNone(self.repo.get_by_id("e7"))
        self.assertIsNotNone(self.repo.get_by_id("e8"))

    def test_transaction_rolls_back_group_on_error(self) -> None:
        """If an error occurs, all repository modifications in transaction roll back."""
        try:
            with self.repo.transaction():
                self.repo.save(DummyEntity(id="e9", name="Iota", score=90))
                # Trigger a deliberate exception
                raise RuntimeError("Abort transactional save block")
        except RuntimeError:
            pass

        # Verify nothing was committed
        self.assertIsNone(self.repo.get_by_id("e9"))

    def test_nested_transaction_rollback_behavior(self) -> None:
        """Exceptions in nested transaction blocks roll back the entire transaction context."""
        try:
            with self.repo.transaction():
                self.repo.save(DummyEntity(id="e10", name="Kappa", score=100))

                # Nested transaction block
                with self.repo.transaction():
                    self.repo.save(DummyEntity(id="e11", name="Lambda", score=110))
                    raise ValueError("Nested exception rollback")
        except ValueError:
            pass

        # Entire block must have rolled back
        self.assertIsNone(self.repo.get_by_id("e10"))
        self.assertIsNone(self.repo.get_by_id("e11"))

    # ------------------------------------------------------------------ #
    # Thread safety / Concurrent access                                     #
    # ------------------------------------------------------------------ #

    def test_concurrent_access_is_thread_safe(self) -> None:
        """Concurrent saves and reads from multiple threads execute without race conditions."""
        errors: List[Exception] = []

        def worker(thread_idx: int) -> None:
            try:
                for i in range(10):
                    entity_id = f"thread_{thread_idx}_item_{i}"
                    entity = DummyEntity(id=entity_id, name=f"Name {i}", score=i)
                    self.repo.save(entity)
                    # Read check
                    fetched = self.repo.get_by_id(entity_id)
                    assert fetched is not None
                    assert fetched.score == i
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [], f"Concurrent repository operations raised errors: {errors}")

        # Total count check
        all_records = self.repo.list_all()
        self.assertEqual(len(all_records), 50)


if __name__ == "__main__":
    unittest.main()
