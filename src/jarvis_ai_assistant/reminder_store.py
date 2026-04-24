"""Persistent reminder storage for the assistant."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import dateparser

from .config import STORAGE_DIR
from .models import ReminderRecord


class ReminderStore:
    """Stores reminders as JSON and returns upcoming tasks for the UI."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or STORAGE_DIR / "reminders.json"

    def add_reminder(self, subject: str, when_text: str | None) -> ReminderRecord:
        """Create and persist a reminder."""
        scheduled_for = self._parse_datetime(when_text)
        reminder = ReminderRecord(
            id=str(uuid4()),
            subject=subject.strip() or "Untitled reminder",
            scheduled_for=scheduled_for,
            original_when=(when_text or "soon").strip(),
            created_at=datetime.now(),
        )
        reminders = self._load_reminders()
        reminders.append(reminder)
        self._save_reminders(reminders)
        return reminder

    def list_upcoming(self, limit: int = 8) -> list[ReminderRecord]:
        """Return incomplete reminders sorted by scheduled time."""
        reminders = [reminder for reminder in self._load_reminders() if not reminder.completed]
        reminders.sort(key=lambda item: item.scheduled_for)
        return reminders[:limit]

    def due_reminders(self, reference_time: datetime | None = None) -> list[ReminderRecord]:
        """Return uncompleted reminders that are due and not yet notified."""
        now = reference_time or datetime.now()
        return [
            reminder
            for reminder in self._load_reminders()
            if not reminder.completed and reminder.notified_at is None and reminder.scheduled_for <= now
        ]

    def mark_notified(self, reminder_id: str, notified_at: datetime | None = None) -> None:
        """Mark a reminder as already surfaced to the user."""
        reminders = self._load_reminders()
        for reminder in reminders:
            if reminder.id == reminder_id:
                reminder.notified_at = notified_at or datetime.now()
                break
        self._save_reminders(reminders)

    def summary_lines(self, limit: int = 6) -> list[str]:
        """Format reminder summaries for the GUI."""
        reminders = self.list_upcoming(limit=limit)
        if not reminders:
            return ["No upcoming reminders."]
        return [
            f"{reminder.scheduled_for.strftime('%d %b %I:%M %p')}  {reminder.subject}"
            for reminder in reminders
        ]

    def _load_reminders(self) -> list[ReminderRecord]:
        if not self.storage_path.exists():
            return []

        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        return [
            ReminderRecord(
                id=item["id"],
                subject=item["subject"],
                scheduled_for=datetime.fromisoformat(item["scheduled_for"]),
                original_when=item["original_when"],
                created_at=datetime.fromisoformat(item["created_at"]),
                completed=item.get("completed", False),
                notified_at=(
                    datetime.fromisoformat(item["notified_at"])
                    if item.get("notified_at")
                    else None
                ),
            )
            for item in payload
        ]

    def _save_reminders(self, reminders: list[ReminderRecord]) -> None:
        serializable = []
        for reminder in reminders:
            item = asdict(reminder)
            item["scheduled_for"] = reminder.scheduled_for.isoformat()
            item["created_at"] = reminder.created_at.isoformat()
            item["notified_at"] = reminder.notified_at.isoformat() if reminder.notified_at else None
            serializable.append(item)
        self.storage_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    @staticmethod
    def _parse_datetime(when_text: str | None) -> datetime:
        if when_text:
            parsed = dateparser.parse(
                when_text,
                settings={"PREFER_DATES_FROM": "future"},
            )
            if parsed:
                return parsed
        return datetime.now()
