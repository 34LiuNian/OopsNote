"""Ordered SQLite migrations for OopsNote's application control plane."""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator


_MIGRATION_NAME = re.compile(r"^(?P<version>0*[1-9][0-9]*)_[a-z0-9_]+\.sql$")
_MIGRATION_LOCKS: dict[Path, threading.RLock] = {}
_MIGRATION_LOCKS_GUARD = threading.Lock()


class ControlDatabaseError(RuntimeError):
    """The control database schema cannot be opened safely."""


class ControlDatabase:
    """Open and migrate the backend-owned application SQLite database."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 5_000) -> None:
        self.path = Path(path)
        self.busy_timeout_ms = max(1, busy_timeout_ms)
        lock_key = self.path.resolve()
        with _MIGRATION_LOCKS_GUARD:
            self._migration_lock = _MIGRATION_LOCKS.setdefault(
                lock_key,
                threading.RLock(),
            )

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1_000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> tuple[int, ...]:
        """Apply every bundled migration once and return applied versions."""
        with self._migration_lock:
            return self._migrate_locked()

    def _migrate_locked(self) -> tuple[int, ...]:
        migrations = self._migrations()
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied_rows = connection.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            ).fetchall()
            applied = {int(row["version"]): str(row["name"]) for row in applied_rows}
            available = {version: name for version, name, _sql in migrations}
            unknown = sorted(set(applied) - set(available))
            if unknown:
                raise ControlDatabaseError(
                    f"Control database contains unknown migration version(s): {unknown}"
                )
            for version, name in applied.items():
                if available[version] != name:
                    raise ControlDatabaseError(
                        f"Migration {version} is recorded as {name!r}, expected {available[version]!r}"
                    )

            for version, name, sql in migrations:
                if version in applied:
                    continue
                quoted_name = name.replace("'", "''")
                script = (
                    "BEGIN IMMEDIATE;\n"
                    f"{sql.rstrip()}\n"
                    "INSERT INTO schema_migrations(version, name, applied_at) "
                    f"VALUES ({version}, '{quoted_name}', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));\n"
                    "COMMIT;"
                )
                try:
                    connection.executescript(script)
                except sqlite3.Error as error:
                    if connection.in_transaction:
                        connection.rollback()
                    raise ControlDatabaseError(
                        f"Failed to apply control migration {name}: {error}"
                    ) from error
                applied[version] = name
        return tuple(sorted(applied))

    @staticmethod
    def _migrations() -> list[tuple[int, str, str]]:
        root = resources.files("oopsnote.control").joinpath("migrations")
        migrations: list[tuple[int, str, str]] = []
        for entry in root.iterdir():
            match = _MIGRATION_NAME.fullmatch(entry.name)
            if match is None:
                continue
            migrations.append(
                (int(match.group("version")), entry.name, entry.read_text(encoding="utf-8"))
            )
        migrations.sort(key=lambda item: item[0])
        versions = [version for version, _name, _sql in migrations]
        if versions != list(range(1, len(versions) + 1)):
            raise ControlDatabaseError(
                f"Control migrations must be contiguous from 1; found {versions}"
            )
        return migrations
