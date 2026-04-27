"""Persistent command memory for cross-session assistant recall."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import STORAGE_DIR


class MemoryStore:
    """Stores recent commands and responses for lightweight assistant memory."""

    def __init__(self, storage_path: Path | None = None, limit: int = 100) -> None:
        self.storage_path = storage_path or STORAGE_DIR / "memory.json"
        self.limit = limit

    def load(self) -> list[dict[str, str]]:
        """Load memory entries from disk."""
        if not self.storage_path.exists():
            return []
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        return [self._normalize_entry(item) for item in payload]

    def recent(self, limit: int = 15) -> list[dict[str, str]]:
        """Return the most recent memory entries."""
        return self.load()[-limit:]

    def append(self, command: str, response: str, timestamp: datetime | None = None) -> list[dict[str, str]]:
        """Persist a new memory entry and return the trimmed memory window."""
        memories = self.load()
        memories.append(
            {
                "timestamp": (timestamp or datetime.now()).isoformat(timespec="seconds"),
                "command": command.strip(),
                "response": response.strip(),
            }
        )
        memories = memories[-self.limit:]
        self._save(memories)
        return memories[-15:]

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Return recent memory entries matching a free-text query."""
        lowered = query.strip().lower()
        if not lowered:
            return []
        matches = [
            entry
            for entry in self.load()
            if lowered in entry["command"].lower() or lowered in entry["response"].lower()
        ]
        return matches[-limit:]

    def _save(self, memories: list[dict[str, str]]) -> None:
        self.storage_path.write_text(json.dumps(memories, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_entry(entry: dict[str, str]) -> dict[str, str]:
        return {
            "timestamp": str(entry.get("timestamp", "")),
            "command": str(entry.get("command", "")).strip(),
            "response": str(entry.get("response", "")).strip(),
        }
