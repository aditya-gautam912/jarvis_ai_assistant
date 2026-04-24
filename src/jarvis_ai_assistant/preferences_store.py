"""Persistent GUI preferences for the desktop assistant."""

from __future__ import annotations

import json
from pathlib import Path

from .config import STORAGE_DIR


class PreferencesStore:
    """Stores lightweight GUI preferences as JSON."""

    DEFAULTS = {
        "voice_mode": "Full Voice",
        "notifications_enabled": True,
        "popup_notifications": True,
        "reminder_poll_seconds": 20,
    }

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or STORAGE_DIR / "preferences.json"

    def load(self) -> dict[str, object]:
        """Load preferences merged with defaults."""
        if not self.storage_path.exists():
            return dict(self.DEFAULTS)

        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        merged = dict(self.DEFAULTS)
        merged.update(payload)
        return merged

    def save(self, preferences: dict[str, object]) -> None:
        """Persist preferences to disk."""
        merged = dict(self.DEFAULTS)
        merged.update(preferences)
        self.storage_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
