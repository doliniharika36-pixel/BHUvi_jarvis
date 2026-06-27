"""
Repository Framework for Jarvis OS.

Provides base abstractions and generic SQLite implementations for data persistence,
including row mapping, transaction management, and standard CRUD operations.
"""
from abc import ABC, abstractmethod
from contextlib import contextmanager
import sqlite3
import threading
from typing import Any, Dict, Generator, Generic, List, Optional, TypeVar

from jarvis_os.core.ports.repository import RepositoryPort
from jarvis_os.core.domain.exceptions import RepositoryException
from jarvis_os.infrastructure.database.connection import SQLiteConnectionManager

T = TypeVar("T")


class RowMapper(Generic[T], ABC):
    """Interface for mapping between database rows and domain entities."""

    @abstractmethod
    def to_domain(self, row: sqlite3.Row) -> T:
        """Map a database row to a domain entity.

        Args:
            row: The database row to map.

        Returns:
            The mapped domain entity.

        Raises:
            Exception: If mapping fails.
        """
        pass

    @abstractmethod
    def to_row(self, entity: T) -> Dict[str, Any]:
        """Map a domain entity to a dictionary of database columns and values.

        Args:
            entity: The domain entity to map.

        Returns:
            A dictionary mapping column names to values.

        Raises:
            Exception: If mapping fails.
        """
        pass


class BaseRepository(RepositoryPort[T], Generic[T], ABC):
    """Abstract base class for all repositories in Jarvis OS."""
    pass


class SQLiteRepository(BaseRepository[T], Generic[T]):
    """Generic SQLite implementation of RepositoryPort.

    Implements standard CRUD operations (save, get_by_id, delete, list_all)
    using the SQLite connection manager. Provides exception translation
    and re-entrant locking for thread safety.
    """

    def __init__(
        self,
        connection_manager: SQLiteConnectionManager,
        table_name: str,
        pk_column: str = "id",
        mapper: Optional[RowMapper[T]] = None,
    ) -> None:
        """
        Args:
            connection_manager: The database connection manager.
            table_name: The database table name.
            pk_column: Name of the primary key column (defaults to "id").
            mapper: Optional RowMapper implementation. If not provided,
                    subclasses must implement _to_domain and _to_row.
        """
        self._db = connection_manager
        self._table_name = table_name
        self._pk_column = pk_column
        self._mapper = mapper
        self._lock = threading.RLock()  # Thread-safety for repository methods

    # ------------------------------------------------------------------ #
    # RepositoryPort implementation                                        #
    # ------------------------------------------------------------------ #

    def save(self, entity: T) -> None:
        """Persist a new entity or overwrite an existing entity.

        Raises:
            RepositoryException: If DB execution or mapping fails.
        """
        with self._lock:
            try:
                row_dict = self._to_row(entity)
                pk_val = row_dict.get(self._pk_column)

                exists = False
                if pk_val is not None:
                    exists_sql = f"SELECT 1 FROM {self._table_name} WHERE {self._pk_column} = ?;"
                    exists_row = self._db.fetch_one(exists_sql, (pk_val,))
                    exists = exists_row is not None

                if exists:
                    # UPDATE path
                    # Filter out PK to avoid modifying the identifier
                    update_cols = [col for col in row_dict if col != self._pk_column]
                    set_clause = ", ".join(f"{col} = ?" for col in update_cols)
                    sql = f"UPDATE {self._table_name} SET {set_clause} WHERE {self._pk_column} = ?;"
                    params = [row_dict[col] for col in update_cols] + [pk_val]
                    self._db.execute(sql, params)
                else:
                    # INSERT path
                    cols = list(row_dict.keys())
                    placeholders = ", ".join("?" for _ in cols)
                    sql = f"INSERT INTO {self._table_name} ({', '.join(cols)}) VALUES ({placeholders});"
                    params = [row_dict[col] for col in cols]
                    self._db.execute(sql, params)
            except Exception as exc:
                if isinstance(exc, RepositoryException):
                    raise
                raise RepositoryException(f"Failed to save entity to {self._table_name}: {exc}") from exc

    def get_by_id(self, entity_id: str) -> Optional[T]:
        """Fetch a single entity from the store by its unique string identifier.

        Raises:
            RepositoryException: If DB execution or mapping fails.
        """
        with self._lock:
            sql = f"SELECT * FROM {self._table_name} WHERE {self._pk_column} = ?;"
            try:
                row = self._db.fetch_one(sql, (entity_id,))
                if row is None:
                    return None
                return self._to_domain(row)
            except Exception as exc:
                if isinstance(exc, RepositoryException):
                    raise
                raise RepositoryException(
                    f"Failed to fetch entity from {self._table_name} by ID '{entity_id}': {exc}"
                ) from exc

    def delete(self, entity_id: str) -> None:
        """Remove an entity from the store by its identifier.

        Raises:
            RepositoryException: If DB execution fails.
        """
        with self._lock:
            sql = f"DELETE FROM {self._table_name} WHERE {self._pk_column} = ?;"
            try:
                self._db.execute(sql, (entity_id,))
            except Exception as exc:
                if isinstance(exc, RepositoryException):
                    raise
                raise RepositoryException(
                    f"Failed to delete entity from {self._table_name} with ID '{entity_id}': {exc}"
                ) from exc

    def list_all(self) -> List[T]:
        """Retrieve a list of all matching records currently in the repository.

        Raises:
            RepositoryException: If DB execution or mapping fails.
        """
        with self._lock:
            sql = f"SELECT * FROM {self._table_name};"
            try:
                rows = self._db.fetch_all(sql)
                return [self._to_domain(row) for row in rows]
            except Exception as exc:
                if isinstance(exc, RepositoryException):
                    raise
                raise RepositoryException(f"Failed to list all entities from {self._table_name}: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Transaction support                                                  #
    # ------------------------------------------------------------------ #

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Wrap a block of repository operations in a database transaction.

        Supports nested transactions (via SQLiteConnectionManager's savepoint
        handling). Rolls back automatically on error.
        """
        with self._lock:
            with self._db.transaction():
                yield

    # ------------------------------------------------------------------ #
    # Mapping delegates                                                    #
    # ------------------------------------------------------------------ #

    def _to_domain(self, row: sqlite3.Row) -> T:
        """Delegate row mapping to the mapper or raise NotImplementedError.

        Can be overridden by subclasses.
        """
        if self._mapper is not None:
            try:
                return self._mapper.to_domain(row)
            except Exception as exc:
                raise RepositoryException(f"Error mapping database row to domain entity: {exc}") from exc
        raise NotImplementedError("Subclasses must implement _to_domain or provide a RowMapper.")

    def _to_row(self, entity: T) -> Dict[str, Any]:
        """Delegate entity mapping to the mapper or raise NotImplementedError.

        Can be overridden by subclasses.
        """
        if self._mapper is not None:
            try:
                return self._mapper.to_row(entity)
            except Exception as exc:
                raise RepositoryException(f"Error mapping domain entity to database row: {exc}") from exc
        raise NotImplementedError("Subclasses must implement _to_row or provide a RowMapper.")
