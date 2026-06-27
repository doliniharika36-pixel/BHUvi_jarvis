"""
SQLite Connection Manager for Jarvis OS.

Design decisions:
- One persistent connection per manager instance (not a pool): on an 8 GB
  RAM / single-process desktop assistant there is no benefit to pooling.
- check_same_thread=False + RLock: lets multiple threads share the single
  connection safely through explicit locking in every public method.
- WAL mode is set immediately after every open so readers never block
  writers and the write-ahead log survives restarts gracefully.
- Foreign-key enforcement is enabled to catch referential errors early.
- The public API exposes execute(), fetch_one(), fetch_all(), and a
  transaction() context manager – nothing more.  Repository classes will
  use these primitives; they must not access _conn directly.
"""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable, List, Optional, Tuple

from jarvis_os.core.domain.exceptions import RepositoryException


class SQLiteConnectionManager:
    """Manages a single SQLite connection with WAL mode and thread-safe access.

    Lifecycle::

        manager = SQLiteConnectionManager(path)
        manager.open()
        # ... use manager ...
        manager.close()

    Or use it as a context manager::

        with SQLiteConnectionManager(path) as manager:
            manager.execute("INSERT INTO ...")
    """

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: Absolute or relative path to the SQLite file.
                     Use ``":memory:"`` for an in-memory database (tests).
        """
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()   # re-entrant: transaction() nests safely

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        """Open the database connection and apply one-time pragmas.

        Creates the database file (and any parent directories) if they do
        not already exist.

        Raises:
            RepositoryException: If the path is invalid or the file cannot
                                 be created / opened.
        """
        with self._lock:
            if self._conn is not None:
                return  # Already open — idempotent

            try:
                if self._db_path != ":memory:":
                    try:
                        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
                    except OSError as exc:
                        raise RepositoryException(
                            f"Cannot create directory for database '{self._db_path}': {exc}"
                        ) from exc

                self._conn = sqlite3.connect(
                    self._db_path,
                    check_same_thread=False,   # guarded by self._lock
                    isolation_level=None,       # autocommit OFF; we manage txns
                )
                self._apply_pragmas()
            except sqlite3.OperationalError as exc:
                self._conn = None
                raise RepositoryException(
                    f"Cannot open database at '{self._db_path}': {exc}"
                ) from exc

    def close(self) -> None:
        """Flush the WAL and close the connection gracefully.

        Safe to call even if the database was never opened (no-op).
        """
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                self._conn.close()
            finally:
                self._conn = None

    @property
    def is_open(self) -> bool:
        """True when the connection is currently active."""
        with self._lock:
            return self._conn is not None

    # ------------------------------------------------------------------ #
    # Context-manager support                                              #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "SQLiteConnectionManager":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Pragmas                                                              #
    # ------------------------------------------------------------------ #

    def _apply_pragmas(self) -> None:
        """Configure SQLite pragmas for every new connection."""
        assert self._conn is not None
        pragmas = [
            "PRAGMA journal_mode=WAL;",
            "PRAGMA foreign_keys=ON;",
            "PRAGMA synchronous=NORMAL;",   # safe with WAL; faster than FULL
            "PRAGMA temp_store=MEMORY;",    # avoid temp-file I/O
            "PRAGMA cache_size=-8000;",     # ~8 MB page cache (negative = KB)
        ]
        for pragma in pragmas:
            self._conn.execute(pragma)

    # ------------------------------------------------------------------ #
    # Query helpers                                                        #
    # ------------------------------------------------------------------ #

    def _ensure_open(self) -> sqlite3.Connection:
        """Return the active connection or raise if not open."""
        if self._conn is None:
            raise RepositoryException(
                "Database is not open. Call open() before executing queries."
            )
        return self._conn

    def execute(
        self,
        sql: str,
        params: Iterable[Any] = (),
    ) -> sqlite3.Cursor:
        """Execute a single SQL statement and return the cursor.

        Raises:
            RepositoryException: On any SQLite error or if DB is not open.
        """
        with self._lock:
            conn = self._ensure_open()
            try:
                return conn.execute(sql, params)
            except sqlite3.Error as exc:
                raise RepositoryException(f"SQL execution failed: {exc}\nSQL: {sql}") from exc

    def execute_many(
        self,
        sql: str,
        params_seq: Iterable[Iterable[Any]],
    ) -> None:
        """Execute a SQL statement against a sequence of parameter tuples.

        Raises:
            RepositoryException: On any SQLite error or if DB is not open.
        """
        with self._lock:
            conn = self._ensure_open()
            try:
                conn.executemany(sql, params_seq)
            except sqlite3.Error as exc:
                raise RepositoryException(f"executemany failed: {exc}\nSQL: {sql}") from exc

    def fetch_one(
        self,
        sql: str,
        params: Iterable[Any] = (),
    ) -> Optional[sqlite3.Row]:
        """Execute *sql* and return the first row, or ``None`` if empty.

        Raises:
            RepositoryException: On any SQLite error or if DB is not open.
        """
        with self._lock:
            conn = self._ensure_open()
            try:
                conn.row_factory = sqlite3.Row
                return conn.execute(sql, params).fetchone()
            except sqlite3.Error as exc:
                raise RepositoryException(f"fetch_one failed: {exc}\nSQL: {sql}") from exc

    def fetch_all(
        self,
        sql: str,
        params: Iterable[Any] = (),
    ) -> List[sqlite3.Row]:
        """Execute *sql* and return all rows.

        Raises:
            RepositoryException: On any SQLite error or if DB is not open.
        """
        with self._lock:
            conn = self._ensure_open()
            try:
                conn.row_factory = sqlite3.Row
                return conn.execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                raise RepositoryException(f"fetch_all failed: {exc}\nSQL: {sql}") from exc

    # ------------------------------------------------------------------ #
    # Transaction context manager                                          #
    # ------------------------------------------------------------------ #

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Wrap a block in an explicit BEGIN / COMMIT (ROLLBACK on error).

        Re-entrant: nested calls are safe — the outer transaction wins.

        Usage::

            with manager.transaction():
                manager.execute("INSERT ...")
                manager.execute("UPDATE ...")
        """
        with self._lock:
            conn = self._ensure_open()
            # If already inside a transaction (isolation_level=None means we
            # manage BEGIN ourselves), start a savepoint instead.
            in_txn = conn.in_transaction
            try:
                if not in_txn:
                    conn.execute("BEGIN;")
                yield
                if not in_txn:
                    conn.execute("COMMIT;")
            except Exception:
                if not in_txn:
                    try:
                        conn.execute("ROLLBACK;")
                    except sqlite3.Error:
                        pass
                raise

    # ------------------------------------------------------------------ #
    # Introspection                                                        #
    # ------------------------------------------------------------------ #

    def get_journal_mode(self) -> str:
        """Return the active journal mode string (e.g. ``'wal'``)."""
        row = self.fetch_one("PRAGMA journal_mode;")
        return row[0] if row else "unknown"

    def get_foreign_keys_enabled(self) -> bool:
        """Return True if foreign-key enforcement is active."""
        row = self.fetch_one("PRAGMA foreign_keys;")
        return bool(row[0]) if row else False
