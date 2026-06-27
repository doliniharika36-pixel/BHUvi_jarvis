"""
Unit tests for SQLiteConnectionManager and MigrationRunner.
"""
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from jarvis_os.core.domain.exceptions import RepositoryException
from jarvis_os.infrastructure.database.connection import SQLiteConnectionManager
from jarvis_os.infrastructure.database.migrations import Migration, MigrationRunner


# ═══════════════════════════════════════════════════════════════════════ #
#  Helpers                                                                #
# ═══════════════════════════════════════════════════════════════════════ #

def make_manager(path: str = ":memory:") -> SQLiteConnectionManager:
    mgr = SQLiteConnectionManager(path)
    mgr.open()
    return mgr


# ═══════════════════════════════════════════════════════════════════════ #
#  SQLiteConnectionManager tests                                          #
# ═══════════════════════════════════════════════════════════════════════ #

class TestSQLiteConnectionManager(unittest.TestCase):
    """Tests for SQLiteConnectionManager lifecycle, pragmas, and query helpers."""

    def setUp(self) -> None:
        self.mgr = SQLiteConnectionManager(":memory:")

    def tearDown(self) -> None:
        self.mgr.close()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def test_open_sets_is_open_true(self):
        """is_open is False before open() and True after."""
        self.assertFalse(self.mgr.is_open)
        self.mgr.open()
        self.assertTrue(self.mgr.is_open)

    def test_close_sets_is_open_false(self):
        """is_open returns False after close()."""
        self.mgr.open()
        self.mgr.close()
        self.assertFalse(self.mgr.is_open)

    def test_open_is_idempotent(self):
        """Calling open() twice does not raise and leaves one connection."""
        self.mgr.open()
        self.mgr.open()      # second call — must be a no-op
        self.assertTrue(self.mgr.is_open)

    def test_close_is_idempotent(self):
        """Calling close() on an already-closed manager does not raise."""
        self.mgr.open()
        self.mgr.close()
        self.mgr.close()     # second call — must be a no-op

    def test_close_without_open_is_noop(self):
        """Calling close() on a never-opened manager does not raise."""
        mgr = SQLiteConnectionManager(":memory:")
        mgr.close()           # must not raise

    def test_context_manager_opens_and_closes(self):
        """__enter__ opens the connection; __exit__ closes it."""
        mgr = SQLiteConnectionManager(":memory:")
        with mgr as m:
            self.assertTrue(m.is_open)
        self.assertFalse(mgr.is_open)

    # ------------------------------------------------------------------ #
    # WAL mode                                                             #
    # ------------------------------------------------------------------ #

    def test_wal_mode_enabled_in_memory(self):
        """WAL pragma is set (returns 'memory' for :memory: — SQLite behaviour)."""
        self.mgr.open()
        mode = self.mgr.get_journal_mode()
        # :memory: always reports 'memory' even after PRAGMA journal_mode=WAL
        # because WAL requires a real file.  Verify we at least get a response.
        self.assertIn(mode, {"wal", "memory"})

    def test_wal_mode_enabled_on_real_file(self):
        """WAL journal mode is confirmed on a real on-disk file."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "test.db")
            with SQLiteConnectionManager(db_path) as mgr:
                mode = mgr.get_journal_mode()
        self.assertEqual(mode, "wal")

    def test_foreign_keys_enabled(self):
        """Foreign-key enforcement pragma is active after open."""
        self.mgr.open()
        self.assertTrue(self.mgr.get_foreign_keys_enabled())

    # ------------------------------------------------------------------ #
    # File creation                                                        #
    # ------------------------------------------------------------------ #

    def test_creates_database_file(self):
        """open() creates the .db file and any parent directories."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "sub" / "dir" / "jarvis.db")
            with SQLiteConnectionManager(db_path) as mgr:
                self.assertTrue(Path(db_path).exists())

    def test_reopens_existing_database(self):
        """Data persists when a file-backed database is closed and reopened."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "persist.db")

            with SQLiteConnectionManager(db_path) as mgr:
                mgr.execute("CREATE TABLE t (x INTEGER);")
                mgr.execute("INSERT INTO t VALUES (42);")

            # Reopen — data must survive
            with SQLiteConnectionManager(db_path) as mgr:
                row = mgr.fetch_one("SELECT x FROM t;")
                self.assertEqual(row["x"], 42)

    def test_invalid_path_raises_repository_exception(self):
        """Opening a path whose parent cannot be created raises RepositoryException."""
        # Use a Windows-reserved device name nested as a directory component.
        # This is universally un-creatable on Windows and will also fail on
        # POSIX because the mkdir in open() will succeed but sqlite3.connect
        # to a nonsensical deep path under /dev/null (or similar) will fail.
        import sys
        if sys.platform == "win32":
            # CON is a reserved device name — cannot be used as a directory
            bad_path = "C:\\CON\\impossible\\db.sqlite"
        else:
            bad_path = "/dev/null/impossible/db.sqlite"

        mgr = SQLiteConnectionManager(bad_path)
        with self.assertRaises(RepositoryException):
            mgr.open()

    # ------------------------------------------------------------------ #
    # Query helpers                                                        #
    # ------------------------------------------------------------------ #

    def test_execute_without_open_raises(self):
        """Calling execute() before open() raises RepositoryException."""
        with self.assertRaises(RepositoryException):
            self.mgr.execute("SELECT 1;")

    def test_execute_creates_table_and_inserts(self):
        """execute() runs DDL and DML statements correctly."""
        self.mgr.open()
        self.mgr.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);")
        self.mgr.execute("INSERT INTO items (name) VALUES (?);", ("alpha",))
        row = self.mgr.fetch_one("SELECT name FROM items WHERE id = 1;")
        self.assertEqual(row["name"], "alpha")

    def test_fetch_one_returns_none_when_empty(self):
        """fetch_one returns None for an empty result set."""
        self.mgr.open()
        self.mgr.execute("CREATE TABLE empty (x INTEGER);")
        result = self.mgr.fetch_one("SELECT * FROM empty;")
        self.assertIsNone(result)

    def test_fetch_all_returns_all_rows(self):
        """fetch_all returns every matching row."""
        self.mgr.open()
        self.mgr.execute("CREATE TABLE nums (n INTEGER);")
        self.mgr.execute_many("INSERT INTO nums VALUES (?);", [(i,) for i in range(5)])
        rows = self.mgr.fetch_all("SELECT n FROM nums ORDER BY n;")
        self.assertEqual([r["n"] for r in rows], [0, 1, 2, 3, 4])

    def test_bad_sql_raises_repository_exception(self):
        """Malformed SQL raises RepositoryException (not bare sqlite3.Error)."""
        self.mgr.open()
        with self.assertRaises(RepositoryException):
            self.mgr.execute("THIS IS NOT SQL;")

    # ------------------------------------------------------------------ #
    # Transaction                                                          #
    # ------------------------------------------------------------------ #

    def test_transaction_commits_on_success(self):
        """Statements inside transaction() are committed when block exits normally."""
        self.mgr.open()
        self.mgr.execute("CREATE TABLE t (v INTEGER);")
        with self.mgr.transaction():
            self.mgr.execute("INSERT INTO t VALUES (1);")
        row = self.mgr.fetch_one("SELECT v FROM t;")
        self.assertEqual(row["v"], 1)

    def test_transaction_rolls_back_on_exception(self):
        """Statements inside transaction() are rolled back when block raises."""
        self.mgr.open()
        self.mgr.execute("CREATE TABLE t (v INTEGER);")
        try:
            with self.mgr.transaction():
                self.mgr.execute("INSERT INTO t VALUES (99);")
                raise RuntimeError("abort")
        except RuntimeError:
            pass
        row = self.mgr.fetch_one("SELECT COUNT(*) AS cnt FROM t;")
        self.assertEqual(row["cnt"], 0)

    # ------------------------------------------------------------------ #
    # Thread safety                                                        #
    # ------------------------------------------------------------------ #

    def test_concurrent_inserts_are_thread_safe(self):
        """Multiple threads inserting concurrently produce the correct total row count."""
        self.mgr.open()
        self.mgr.execute("CREATE TABLE counter (val INTEGER);")

        errors = []
        def insert_rows():
            try:
                for _ in range(10):
                    self.mgr.execute("INSERT INTO counter VALUES (1);")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=insert_rows) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [])
        row = self.mgr.fetch_one("SELECT COUNT(*) AS cnt FROM counter;")
        self.assertEqual(row["cnt"], 50)


# ═══════════════════════════════════════════════════════════════════════ #
#  MigrationRunner tests                                                  #
# ═══════════════════════════════════════════════════════════════════════ #

class TestMigrationRunner(unittest.TestCase):
    """Tests for MigrationRunner idempotency, ordering, and error handling."""

    def setUp(self) -> None:
        self.mgr = make_manager()

    def tearDown(self) -> None:
        self.mgr.close()

    # ------------------------------------------------------------------ #
    # Basic execution                                                      #
    # ------------------------------------------------------------------ #

    def test_run_applies_migration_and_returns_count(self):
        """run() applies one migration and returns 1."""
        runner = MigrationRunner(self.mgr, [
            Migration(1, "create foo", ["CREATE TABLE foo (id INTEGER);"]),
        ])
        count = runner.run()
        self.assertEqual(count, 1)

    def test_run_creates_table(self):
        """After run(), the table specified in the migration exists."""
        runner = MigrationRunner(self.mgr, [
            Migration(1, "create bar", ["CREATE TABLE bar (x TEXT);"]),
        ])
        runner.run()
        row = self.mgr.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bar';"
        )
        self.assertIsNotNone(row)

    def test_schema_version_table_created_after_run(self):
        """schema_version tracking table is created by the first run."""
        runner = MigrationRunner(self.mgr, [])
        runner.run()
        row = self.mgr.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version';"
        )
        self.assertIsNotNone(row)

    def test_current_version_returns_highest_applied(self):
        """current_version() returns the version of the last applied migration."""
        runner = MigrationRunner(self.mgr, [
            Migration(1, "v1", ["CREATE TABLE t1 (a INTEGER);"]),
            Migration(2, "v2", ["CREATE TABLE t2 (b INTEGER);"]),
        ])
        runner.run()
        self.assertEqual(runner.current_version(), 2)

    def test_current_version_returns_zero_when_no_migrations(self):
        """current_version() returns 0 when no migrations have been applied."""
        runner = MigrationRunner(self.mgr, [])
        runner.run()
        self.assertEqual(runner.current_version(), 0)

    # ------------------------------------------------------------------ #
    # Idempotency                                                          #
    # ------------------------------------------------------------------ #

    def test_run_twice_skips_already_applied(self):
        """Running the same migration list twice applies each migration only once."""
        migrations = [
            Migration(1, "create t", ["CREATE TABLE t (x INTEGER);"]),
        ]
        runner = MigrationRunner(self.mgr, migrations)
        count1 = runner.run()
        count2 = runner.run()

        self.assertEqual(count1, 1)
        self.assertEqual(count2, 0)   # nothing new to apply
        self.assertEqual(runner.applied_count(), 1)

    def test_adding_new_migration_applies_only_new_one(self):
        """When a new migration is added, only the new one is applied on second run."""
        runner_v1 = MigrationRunner(self.mgr, [
            Migration(1, "v1", ["CREATE TABLE a (x INTEGER);"]),
        ])
        runner_v1.run()

        runner_v2 = MigrationRunner(self.mgr, [
            Migration(1, "v1", ["CREATE TABLE a (x INTEGER);"]),
            Migration(2, "v2", ["CREATE TABLE b (y INTEGER);"]),
        ])
        count = runner_v2.run()
        self.assertEqual(count, 1)
        self.assertEqual(runner_v2.current_version(), 2)

    # ------------------------------------------------------------------ #
    # Ordering                                                             #
    # ------------------------------------------------------------------ #

    def test_migrations_applied_in_ascending_version_order(self):
        """Migrations are applied in ascending version order regardless of list order."""
        applied_order = []

        # Provide in reverse order
        migrations = [
            Migration(3, "v3", ["CREATE TABLE c3 (x INTEGER);"]),
            Migration(1, "v1", ["CREATE TABLE c1 (x INTEGER);"]),
            Migration(2, "v2", ["CREATE TABLE c2 (x INTEGER);"]),
        ]
        runner = MigrationRunner(self.mgr, migrations)
        runner.run()

        rows = self.mgr.fetch_all(
            "SELECT version FROM schema_version ORDER BY applied_at, version;"
        )
        self.assertEqual([r["version"] for r in rows], [1, 2, 3])

    # ------------------------------------------------------------------ #
    # Multi-statement migration                                            #
    # ------------------------------------------------------------------ #

    def test_multi_statement_migration_runs_all_statements(self):
        """A migration with multiple SQL statements executes all of them."""
        runner = MigrationRunner(self.mgr, [
            Migration(1, "multi", [
                "CREATE TABLE p (id INTEGER PRIMARY KEY);",
                "CREATE TABLE q (fk INTEGER REFERENCES p(id));",
                "INSERT INTO p VALUES (1);",
            ]),
        ])
        runner.run()
        row = self.mgr.fetch_one("SELECT id FROM p;")
        self.assertEqual(row["id"], 1)

    # ------------------------------------------------------------------ #
    # Error handling                                                       #
    # ------------------------------------------------------------------ #

    def test_bad_migration_raises_and_rolls_back(self):
        """A migration with bad SQL raises RepositoryException and rolls back."""
        runner = MigrationRunner(self.mgr, [
            Migration(1, "bad", [
                "CREATE TABLE good (x INTEGER);",
                "THIS IS INVALID SQL;",
            ]),
        ])
        with self.assertRaises(RepositoryException):
            runner.run()

        # good table must not have been committed
        row = self.mgr.fetch_one(
            "SELECT name FROM sqlite_master WHERE name='good';"
        )
        self.assertIsNone(row)

    def test_runner_requires_open_manager(self):
        """MigrationRunner raises RepositoryException if manager is not open."""
        closed_mgr = SQLiteConnectionManager(":memory:")
        with self.assertRaises(RepositoryException):
            MigrationRunner(closed_mgr, [])


if __name__ == "__main__":
    unittest.main()
