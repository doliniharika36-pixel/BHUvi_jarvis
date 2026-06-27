"""
Simple migration runner for Jarvis OS SQLite database.

Design:
- Migrations are plain dataclasses containing a version integer and a list
  of SQL statements to execute atomically.
- A 'schema_version' table tracks which migrations have been applied.
- Migrations are applied in ascending version order; already-applied ones
  are skipped, making the runner fully idempotent.
- Each migration runs inside a single transaction — either all its
  statements commit or none do.
- Pure stdlib; no third-party ORM or migration framework.
"""
import logging
from dataclasses import dataclass, field
from typing import List

from jarvis_os.core.domain.exceptions import RepositoryException
from jarvis_os.infrastructure.database.connection import SQLiteConnectionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Migration data contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Migration:
    """Represents a single, ordered schema change.

    Attributes:
        version:     Monotonically increasing integer (1, 2, 3, …).
        description: Human-readable summary shown in logs.
        statements:  Ordered list of SQL DDL/DML statements executed atomically.
    """
    version: int
    description: str
    statements: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


class MigrationRunner:
    """Applies pending database migrations in version order.

    Usage::

        migrations = [
            Migration(1, "Create users table", ["CREATE TABLE users ..."]),
            Migration(2, "Add index",           ["CREATE INDEX ..."]),
        ]
        runner = MigrationRunner(manager, migrations)
        runner.run()
    """

    def __init__(
        self,
        manager: SQLiteConnectionManager,
        migrations: List[Migration],
    ) -> None:
        if not manager.is_open:
            raise RepositoryException(
                "MigrationRunner requires an open SQLiteConnectionManager."
            )
        self._manager = manager
        # Sort ascending by version so callers need not pre-sort
        self._migrations = sorted(migrations, key=lambda m: m.version)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def run(self) -> int:
        """Apply all pending migrations and return the count of migrations run.

        Raises:
            RepositoryException: On SQL error or version conflict.
        """
        self._bootstrap()
        applied = self._applied_versions()
        ran = 0

        for migration in self._migrations:
            if migration.version in applied:
                logger.debug(
                    "Migration v%d ('%s') already applied — skipping.",
                    migration.version,
                    migration.description,
                )
                continue

            self._apply(migration)
            ran += 1
            logger.info(
                "Migration v%d ('%s') applied successfully.",
                migration.version,
                migration.description,
            )

        return ran

    def current_version(self) -> int:
        """Return the highest applied migration version, or 0 if none."""
        self._bootstrap()
        row = self._manager.fetch_one(
            "SELECT MAX(version) FROM schema_version;"
        )
        return int(row[0]) if row and row[0] is not None else 0

    def applied_count(self) -> int:
        """Return the number of migrations recorded in schema_version."""
        self._bootstrap()
        row = self._manager.fetch_one(
            "SELECT COUNT(*) FROM schema_version;"
        )
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _bootstrap(self) -> None:
        """Create the schema_version tracking table if it does not exist."""
        self._manager.execute(_BOOTSTRAP_SQL)

    def _applied_versions(self) -> set:
        rows = self._manager.fetch_all("SELECT version FROM schema_version;")
        return {int(row[0]) for row in rows}

    def _apply(self, migration: Migration) -> None:
        """Execute a migration's statements in one atomic transaction."""
        with self._manager.transaction():
            for sql in migration.statements:
                try:
                    self._manager.execute(sql)
                except RepositoryException as exc:
                    raise RepositoryException(
                        f"Migration v{migration.version} ('{migration.description}') "
                        f"failed at statement:\n  {sql}\nReason: {exc}"
                    ) from exc

            # Record this migration as applied
            self._manager.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?);",
                (migration.version, migration.description),
            )
