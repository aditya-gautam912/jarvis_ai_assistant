"""Persistent command memory for cross-session assistant recall."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import STORAGE_DIR


class MemoryStore:
    """Stores recent commands and responses in SQLite for assistant memory."""

    def __init__(self, storage_path: Path | None = None, limit: int = 100) -> None:
        self.storage_path = storage_path or STORAGE_DIR / "assistant.db"
        self.limit = limit
        self._initialize_schema()
        self._migrate_legacy_json()

    def load(self) -> list[dict[str, str]]:
        """Load memory entries in chronological order."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT timestamp, command, response FROM memory_entries ORDER BY id ASC"
            ).fetchall()
        return [
            self._normalize_entry(
                {"timestamp": row["timestamp"], "command": row["command"], "response": row["response"]}
            )
            for row in rows
        ]

    def recent(self, limit: int = 15) -> list[dict[str, str]]:
        """Return the most recent memory entries."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT timestamp, command, response FROM memory_entries ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            self._normalize_entry(
                {"timestamp": row["timestamp"], "command": row["command"], "response": row["response"]}
            )
            for row in reversed(rows)
        ]

    def append(self, command: str, response: str, timestamp: datetime | None = None) -> list[dict[str, str]]:
        """Persist a new memory entry and return the trimmed memory window."""
        entry = {
            "timestamp": (timestamp or datetime.now()).isoformat(timespec="seconds"),
            "command": command.strip(),
            "response": response.strip(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_entries (timestamp, command, response)
                VALUES (?, ?, ?)
                """,
                (entry["timestamp"], entry["command"], entry["response"]),
            )
            connection.execute(
                """
                DELETE FROM memory_entries
                WHERE id NOT IN (
                    SELECT id FROM memory_entries ORDER BY id DESC LIMIT ?
                )
                """,
                (self.limit,),
            )
            connection.commit()
        return self.recent(limit=15)

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Return recent memory entries matching a free-text query."""
        lowered = query.strip().lower()
        if not lowered:
            return []
        wildcard = f"%{lowered}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, command, response
                FROM memory_entries
                WHERE lower(command) LIKE ? OR lower(response) LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (wildcard, wildcard, limit),
            ).fetchall()
        return [
            self._normalize_entry(
                {"timestamp": row["timestamp"], "command": row["command"], "response": row["response"]}
            )
            for row in reversed(rows)
        ]

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    command TEXT NOT NULL,
                    response TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _migrate_legacy_json(self) -> None:
        legacy_path = self.storage_path.with_name("memory.json")
        if self.storage_path.name == "memory.json" or not legacy_path.exists():
            return

        with self._connect() as connection:
            has_data = connection.execute(
                "SELECT 1 FROM memory_entries LIMIT 1"
            ).fetchone()
            if has_data is not None:
                return

        import json

        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        entries = [self._normalize_entry(item) for item in payload if isinstance(item, dict)]
        if not entries:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO memory_entries (timestamp, command, response)
                VALUES (?, ?, ?)
                """,
                [(item["timestamp"], item["command"], item["response"]) for item in entries[-self.limit :]],
            )
            connection.commit()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.storage_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _normalize_entry(entry: dict[str, str]) -> dict[str, str]:
        return {
            "timestamp": str(entry.get("timestamp", "")),
            "command": str(entry.get("command", "")).strip(),
            "response": str(entry.get("response", "")).strip(),
        }
