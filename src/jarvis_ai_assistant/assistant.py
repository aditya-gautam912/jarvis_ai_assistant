"""Main assistant orchestration logic."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from .analytics import InteractionAnalytics
from .api_services import APIService, APIServiceError
from .automation_module import AutomationModule
from .config import SETTINGS
from .memory_store import MemoryStore
from .models import AssistantResponse, InteractionRecord
from .nlp_engine import NLPEngine
from .reminder_store import ReminderStore
from .voice_module import AudioLevelMonitor, VoiceModule

LOGGER = logging.getLogger(__name__)


class JarvisAssistant:
    """Coordinates voice, NLP, APIs, automation, and analytics."""

    INTENT_CONFIDENCE_FLOORS = {
        "greeting": 0.0,
        "exit": 0.0,
        "open_application": 0.25,
        "weather_query": 0.25,
        "news_query": 0.25,
        "play_music": 0.25,
        "set_reminder": 0.25,
        "schedule_calendar": 0.25,
        "file_operation": 0.25,
        "general_query": 0.20,
    }

    def __init__(self, enable_voice: bool = True, voice_device_index: int | None = None) -> None:
        self.voice = None
        self.voice_device_index = voice_device_index
        if enable_voice:
            try:
                self.voice = VoiceModule(device_index=voice_device_index)
            except OSError:
                LOGGER.warning("Voice module could not be initialized.", exc_info=True)
        self.nlp = NLPEngine()
        self.api = APIService()
        self.automation = AutomationModule()
        self.analytics = InteractionAnalytics()
        self.reminders = ReminderStore()
        self.memory_store = MemoryStore()
        self.memory: list[dict[str, str]] = self.memory_store.recent()

    def configure_voice(self, enabled: bool, device_index: int | None = None) -> bool:
        """Reinitialize voice support with the requested microphone."""
        self.voice_device_index = device_index
        if not enabled:
            self.voice = None
            return False

        try:
            self.voice = VoiceModule(device_index=device_index)
            return True
        except OSError:
            self.voice = None
            LOGGER.warning("Voice module reconfiguration failed.", exc_info=True)
            return False

    def test_microphone(self, device_index: int | None = None) -> tuple[bool, str]:
        """Capture one short utterance from the selected microphone for diagnostics."""
        try:
            voice = VoiceModule(device_index=device_index)
        except OSError as exc:
            return False, str(exc)

        heard = voice.listen()
        if not heard:
            return False, "No speech was detected from the selected microphone."
        return True, heard

    def create_audio_monitor(self, device_index: int | None = None) -> AudioLevelMonitor:
        """Create a live audio level monitor for the selected microphone."""
        return AudioLevelMonitor(device_index=device_index)

    def run(self) -> None:
        """Main voice loop."""
        if self.voice is None:
            raise OSError("Voice module is disabled.")

        self.voice.speak("Jarvis is online. Say a command when you are ready.")

        while True:
            spoken_text = self.voice.listen()
            if not spoken_text:
                self.voice.speak("I did not catch that. Please repeat.")
                continue

            response = self.handle_command(spoken_text)
            self.voice.speak(response.message)

            if response.action == "exit":
                break

    def listen_once(self) -> str | None:
        """Capture a single voice command when voice support is enabled."""
        if self.voice is None:
            raise OSError("Voice module is disabled.")
        return self.voice.listen()

    def preprocess_voice_command(self, heard_text: str, require_wake_word: bool) -> tuple[str | None, str | None]:
        """Apply wake-word gating to captured voice text."""
        normalized = heard_text.strip()
        if not normalized:
            return None, "I did not hear any command."
        if not require_wake_word:
            return normalized, None

        stripped = VoiceModule.strip_wake_word(normalized, SETTINGS.wake_word)
        if stripped is None:
            return None, f"Wake word '{SETTINGS.wake_word}' was not detected."
        if not stripped:
            return None, "Wake word detected. Please say a command after it."
        return stripped, None

    def speak(self, message: str) -> None:
        """Speak a response when voice support is available."""
        if self.voice is not None:
            self.voice.speak(message)

    def usage_summary(self) -> dict[str, object]:
        """Expose analytics summaries to UI layers."""
        return self.analytics.usage_summary()

    def upcoming_reminders(self) -> list[str]:
        """Expose upcoming reminders to UI layers."""
        return self.reminders.summary_lines()

    def due_reminders(self) -> list[dict[str, str]]:
        """Return due reminders in a GUI-friendly structure."""
        return [
            {
                "id": reminder.id,
                "subject": reminder.subject,
                "scheduled_for": reminder.scheduled_for.strftime("%d %b %I:%M %p"),
            }
            for reminder in self.reminders.due_reminders()
        ]

    def mark_reminder_notified(self, reminder_id: str) -> None:
        """Mark a reminder as already shown to the user."""
        self.reminders.mark_notified(reminder_id)

    def complete_next_reminder(self) -> AssistantResponse:
        """Complete the next upcoming reminder."""
        reminders = self.reminders.list_upcoming(limit=1)
        if not reminders:
            return AssistantResponse(message="There are no upcoming reminders to complete.", success=False)
        reminder = self.reminders.complete_reminder(reminders[0].id)
        return AssistantResponse(
            message=f"Completed reminder: {reminder.subject}.",
            action="complete_reminder",
            payload={"reminder_id": reminder.id},
        )

    def snooze_next_reminder(self, minutes: int = 15) -> AssistantResponse:
        """Snooze the next upcoming reminder."""
        reminders = self.reminders.list_upcoming(limit=1)
        if not reminders:
            return AssistantResponse(message="There are no upcoming reminders to snooze.", success=False)
        reminder = self.reminders.snooze_reminder(reminders[0].id, minutes=minutes)
        return AssistantResponse(
            message=(
                f"Snoozed reminder '{reminder.subject}' for {minutes} minutes until "
                f"{reminder.scheduled_for.strftime('%I:%M %p')}."
            ),
            action="snooze_reminder",
            payload={"reminder_id": reminder.id, "minutes": str(minutes)},
        )

    def complete_reminder(self, reminder_id: str) -> AssistantResponse:
        """Complete a specific reminder by identifier."""
        reminder = self.reminders.complete_reminder(reminder_id)
        if reminder is None:
            return AssistantResponse(message="I could not find that reminder to complete.", success=False)
        return AssistantResponse(
            message=f"Completed reminder: {reminder.subject}.",
            action="complete_reminder",
            payload={"reminder_id": reminder.id},
        )

    def snooze_reminder(self, reminder_id: str, minutes: int = 15) -> AssistantResponse:
        """Snooze a specific reminder by identifier."""
        reminder = self.reminders.snooze_reminder(reminder_id, minutes=minutes)
        if reminder is None:
            return AssistantResponse(message="I could not find that reminder to snooze.", success=False)
        return AssistantResponse(
            message=(
                f"Snoozed reminder '{reminder.subject}' for {minutes} minutes until "
                f"{reminder.scheduled_for.strftime('%I:%M %p')}."
            ),
            action="snooze_reminder",
            payload={"reminder_id": reminder.id, "minutes": str(minutes)},
        )

    def handle_command(self, command: str) -> AssistantResponse:
        """Handle a text command from voice or keyboard input."""
        command = command.strip()
        if not command:
            return AssistantResponse(message="Please say or type a command.", success=False)

        memory_response = self._handle_memory_or_rules(command)
        if memory_response is not None:
            self._record_memory(command, memory_response.message)
            return memory_response

        result = self.nlp.predict(command)

        if not self._meets_confidence_threshold(result.intent, result.confidence):
            response = self.automation.search_web(command)
            self._log_interaction(command, result.intent, result.confidence, response)
            self._record_memory(command, response.message)
            return AssistantResponse(
                message=(
                    "I was not confident about that command, so I opened a web search instead."
                ),
                success=False,
                action="low_confidence_fallback",
                payload={"predicted_intent": result.intent, "confidence": result.confidence},
            )

        response = self._dispatch(result.intent, result.entities, result.normalized_text)
        self._log_interaction(command, result.intent, result.confidence, response)
        self._record_memory(command, response.message)
        return response

    def _meets_confidence_threshold(self, intent: str, confidence: float) -> bool:
        """Apply realistic per-intent confidence floors instead of one global cutoff."""
        minimum = self.INTENT_CONFIDENCE_FLOORS.get(intent, SETTINGS.confidence_threshold)
        return confidence >= minimum

    def _handle_memory_or_rules(self, command: str) -> AssistantResponse | None:
        normalized = command.lower()

        if normalized in {"show reminders", "what reminders do i have", "list reminders"}:
            reminders = self.upcoming_reminders()
            return AssistantResponse(
                message="Upcoming reminders: " + "; ".join(reminders),
                action="show_reminders",
            )

        if normalized in {"complete reminder", "mark reminder done", "complete my reminder"}:
            return self.complete_next_reminder()

        if normalized in {"snooze reminder", "snooze my reminder"}:
            return self.snooze_next_reminder()

        snooze_match = re.search(r"snooze reminder for (\d+)\s+minutes?", normalized)
        if snooze_match:
            return self.snooze_next_reminder(int(snooze_match.group(1)))

        if normalized in {
            "what did i ask before",
            "what was my previous command",
            "what did i say before",
            "show recent commands",
        }:
            if not self.memory:
                return AssistantResponse(message="I do not have any recent commands in memory yet.", action="memory_query")
            recent = self.memory[-3:]
            summary = "; ".join(f"{item['command']}" for item in recent)
            return AssistantResponse(message=f"Your recent commands were: {summary}.", action="memory_query")

        search_match = re.search(r"(search history for|find in history)\s+(.+)", normalized)
        if search_match:
            entries = self.memory_store.search(search_match.group(2))
            if not entries:
                return AssistantResponse(
                    message=f"I could not find anything in memory matching {search_match.group(2)}.",
                    action="memory_query",
                    success=False,
                )
            summary = "; ".join(entry["command"] for entry in entries)
            return AssistantResponse(message=f"I found these related commands: {summary}.", action="memory_query")

        return None

    def _record_memory(self, command: str, response: str) -> None:
        self.memory = self.memory_store.append(command=command, response=response, timestamp=datetime.now())

    def _dispatch(self, intent: str, entities: dict[str, str], text: str) -> AssistantResponse:
        if intent == "greeting":
            hour = datetime.now().hour
            if hour < 12:
                greeting = "Good morning"
            elif hour < 18:
                greeting = "Good afternoon"
            else:
                greeting = "Good evening"
            return AssistantResponse(message=f"{greeting}. I am ready to help.", action="greeting")

        if intent == "exit":
            return AssistantResponse(message="Shutting down. Goodbye.", action="exit")

        if intent == "open_application":
            application = entities.get("application", text)
            return self.automation.open_application(application)

        if intent == "weather_query":
            return self._handle_weather(entities.get("city"))

        if intent == "news_query":
            return self._handle_news(entities.get("topic"))

        if intent == "play_music":
            return self.automation.play_music(
                song_query=entities.get("song_query", "music"),
                platform=entities.get("platform", "youtube"),
            )

        if intent == "set_reminder":
            return self._handle_reminder(entities)

        if intent == "schedule_calendar":
            return self._handle_calendar(entities)

        if intent == "file_operation":
            file_response = self.automation.handle_file_operation(text)
            if not file_response.success:
                return self.automation.search_web(text)
            return file_response

        if intent == "general_query":
            return self.automation.search_web(entities.get("query", text))

        return AssistantResponse(
            message="I do not know how to handle that yet.",
            success=False,
            action="unknown_intent",
        )

    def _handle_weather(self, city: str | None) -> AssistantResponse:
        try:
            weather = self.api.get_weather(city)
        except (APIServiceError, Exception) as exc:
            LOGGER.exception("Weather request failed: %s", exc)
            return AssistantResponse(
                message="I could not fetch the weather right now.",
                success=False,
                action="weather_error",
            )

        return AssistantResponse(
            message=(
                f"The weather in {weather['city']} is {weather['description']} "
                f"with a temperature of {weather['temperature']} degrees Celsius."
            ),
            action="weather_query",
            payload=weather,
        )

    def _handle_news(self, topic: str | None) -> AssistantResponse:
        try:
            articles = self.api.get_news(topic)
        except (APIServiceError, Exception) as exc:
            LOGGER.exception("News request failed: %s", exc)
            return AssistantResponse(
                message="I could not fetch the news right now.",
                success=False,
                action="news_error",
            )

        if not articles:
            return AssistantResponse(
                message="I could not find matching news articles.",
                success=False,
                action="news_query",
            )

        headlines = "; ".join(article["title"] for article in articles[:3])
        return AssistantResponse(
            message=f"Here are the top headlines: {headlines}",
            action="news_query",
            payload={"articles": articles},
        )

    def _handle_reminder(self, entities: dict[str, str]) -> AssistantResponse:
        subject = entities.get("subject", "your reminder").strip() or "your reminder"
        when_text = entities.get("when", "soon")
        reminder = self.reminders.add_reminder(subject=subject, when_text=when_text)
        return AssistantResponse(
            message=(
                f"Reminder saved for {reminder.scheduled_for.strftime('%d %b at %I:%M %p')}: "
                f"{subject}."
            ),
            action="set_reminder",
            payload={
                "subject": subject,
                "when": when_text,
                "scheduled_for": reminder.scheduled_for.isoformat(),
                "reminder_id": reminder.id,
            },
        )

    def _handle_calendar(self, entities: dict[str, str]) -> AssistantResponse:
        try:
            event = self.api.create_calendar_event(
                subject=entities.get("subject", "Jarvis event"),
                when_text=entities.get("when"),
            )
        except (APIServiceError, Exception) as exc:
            LOGGER.exception("Calendar request failed: %s", exc)
            return AssistantResponse(
                message="I could not create the calendar event right now.",
                success=False,
                action="calendar_error",
            )

        return AssistantResponse(
            message=f"Calendar event created for {event['summary']} at {event['start']}.",
            action="schedule_calendar",
            payload=event,
        )

    def _log_interaction(
        self,
        command: str,
        intent: str,
        confidence: float,
        response: AssistantResponse,
    ) -> None:
        self.analytics.log(
            InteractionRecord(
                timestamp=datetime.now(),
                command=command,
                intent=intent,
                confidence=confidence,
                success=response.success,
                response=response.message,
            )
        )
