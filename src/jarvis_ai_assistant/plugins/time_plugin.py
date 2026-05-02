"""Built-in plugin for current date and time queries."""

from __future__ import annotations

from datetime import datetime

from ..models import AssistantResponse


class TimeSkillPlugin:
    """Answers simple date and time questions without NLP intent updates."""

    name = "time_info"

    _TIME_TRIGGERS = {
        "what time is it",
        "tell me the time",
        "current time",
        "time now",
    }
    _DATE_TRIGGERS = {
        "what is today's date",
        "what is todays date",
        "today's date",
        "todays date",
        "what date is it",
        "current date",
    }
    _BOTH_TRIGGERS = {
        "date and time",
        "current date and time",
        "what is the date and time",
    }

    def handle(self, command: str, *, assistant) -> AssistantResponse | None:
        normalized = command.strip().lower()
        now = datetime.now()

        if normalized in self._BOTH_TRIGGERS:
            return AssistantResponse(
                message=(
                    f"It is {now.strftime('%I:%M %p')} on {now.strftime('%A, %d %B %Y')}."
                ),
                action="plugin_time_info",
                payload={"plugin": self.name, "mode": "date_time"},
            )

        if normalized in self._TIME_TRIGGERS:
            return AssistantResponse(
                message=f"It is {now.strftime('%I:%M %p')}.",
                action="plugin_time_info",
                payload={"plugin": self.name, "mode": "time"},
            )

        if normalized in self._DATE_TRIGGERS:
            return AssistantResponse(
                message=f"Today is {now.strftime('%A, %d %B %Y')}.",
                action="plugin_time_info",
                payload={"plugin": self.name, "mode": "date"},
            )

        return None


def register() -> TimeSkillPlugin:
    """Register the built-in time skill plugin."""
    return TimeSkillPlugin()

