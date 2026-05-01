"""Persistent reminder storage for the assistant."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import dateparser

from .config import STORAGE_DIR
from .models import ReminderRecord


class ReminderStore:
    """Stores reminders in SQLite and returns upcoming tasks for the UI."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or STORAGE_DIR / "assistant.db"
        self._initialize_schema()
        self._migrate_legacy_json()

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
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reminders (
                    id, subject, scheduled_for, original_when, created_at, completed, notified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reminder.id,
                    reminder.subject,
                    reminder.scheduled_for.isoformat(),
                    reminder.original_when,
                    reminder.created_at.isoformat(),
                    int(reminder.completed),
                    None,
                ),
            )
            connection.commit()
        return reminder

    def list_upcoming(self, limit: int = 8) -> list[ReminderRecord]:
        """Return incomplete reminders sorted by scheduled time."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, subject, scheduled_for, original_when, created_at, completed, notified_at
                FROM reminders
                WHERE completed = 0
                ORDER BY scheduled_for ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def due_reminders(self, reference_time: datetime | None = None) -> list[ReminderRecord]:
        """Return uncompleted reminders that are due and not yet notified."""
        now = reference_time or datetime.now()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, subject, scheduled_for, original_when, created_at, completed, notified_at
                FROM reminders
                WHERE completed = 0 AND notified_at IS NULL AND scheduled_for <= ?
                ORDER BY scheduled_for ASC
                """,
                (now.isoformat(),),
            ).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def mark_notified(self, reminder_id: str, notified_at: datetime | None = None) -> None:
        """Mark a reminder as already surfaced to the user."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE reminders SET notified_at = ? WHERE id = ?",
                ((notified_at or datetime.now()).isoformat(), reminder_id),
            )
            connection.commit()

    def complete_reminder(self, reminder_id: str) -> ReminderRecord | None:
        """Mark a reminder as completed."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE reminders SET completed = 1 WHERE id = ?",
                (reminder_id,),
            )
            connection.commit()
        return self._get_by_id(reminder_id)

    def snooze_reminder(self, reminder_id: str, minutes: int = 15) -> ReminderRecord | None:
        """Push a reminder into the future and clear any notification marker."""
        updated_schedule = datetime.now() + timedelta(minutes=minutes)
        with self._connect() as connection:
            connection.execute(
                "UPDATE reminders SET scheduled_for = ?, notified_at = NULL WHERE id = ?",
                (updated_schedule.isoformat(), reminder_id),
            )
            connection.commit()
        return self._get_by_id(reminder_id)

    def summary_lines(self, limit: int = 6) -> list[str]:
        """Format reminder summaries for the GUI."""
        reminders = self.list_upcoming(limit=limit)
        if not reminders:
            return ["No upcoming reminders."]
        return [
            f"{reminder.scheduled_for.strftime('%d %b %I:%M %p')}  {reminder.subject}"
            for reminder in reminders
        ]

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    original_when TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    notified_at TEXT
                )
                """
            )
            connection.commit()

    def _migrate_legacy_json(self) -> None:
        legacy_path = self.storage_path.with_name("reminders.json")
        if self.storage_path.name == "reminders.json" or not legacy_path.exists():
            return

        with self._connect() as connection:
            has_data = connection.execute("SELECT 1 FROM reminders LIMIT 1").fetchone()
            if has_data is not None:
                return

        import json

        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return

        rows: list[tuple[str, str, str, str, str, int, str | None]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            row = (
                str(item.get("id", str(uuid4()))),
                str(item.get("subject", "Untitled reminder")).strip() or "Untitled reminder",
                str(item.get("scheduled_for", datetime.now().isoformat())),
                str(item.get("original_when", "soon")),
                str(item.get("created_at", datetime.now().isoformat())),
                int(bool(item.get("completed", False))),
                str(item["notified_at"]) if item.get("notified_at") else None,
            )
            rows.append(row)

        if not rows:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO reminders (
                    id, subject, scheduled_for, original_when, created_at, completed, notified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()

    def _get_by_id(self, reminder_id: str) -> ReminderRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, subject, scheduled_for, original_when, created_at, completed, notified_at
                FROM reminders
                WHERE id = ?
                """,
                (reminder_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_reminder(row)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.storage_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _row_to_reminder(row: sqlite3.Row) -> ReminderRecord:
        return ReminderRecord(
            id=str(row["id"]),
            subject=str(row["subject"]),
            scheduled_for=datetime.fromisoformat(str(row["scheduled_for"])),
            original_when=str(row["original_when"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            completed=bool(row["completed"]),
            notified_at=(
                datetime.fromisoformat(str(row["notified_at"]))
                if row["notified_at"]
                else None
            ),
        )

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
