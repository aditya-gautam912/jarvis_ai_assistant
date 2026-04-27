"""Shared data models used across the assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class IntentResult:
    """Result returned by the NLP engine for a user utterance."""

    intent: str
    confidence: float
    normalized_text: str
    entities: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AssistantResponse:
    """Represents the text that should be spoken and its metadata."""

    message: str
    success: bool = True
    action: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    should_speak: bool = True


@dataclass(slots=True)
class InteractionRecord:
    """Analytics row for one user interaction."""

    timestamp: datetime
    command: str
    intent: str
    confidence: float
    success: bool
    response: str


@dataclass(slots=True)
class ReminderRecord:
    """Persistent reminder model stored on disk."""

    id: str
    subject: str
    scheduled_for: datetime
    original_when: str
    created_at: datetime
    completed: bool = False
    notified_at: datetime | None = None
