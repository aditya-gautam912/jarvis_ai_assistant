"""Smoke tests for the Jarvis assistant project."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.jarvis_ai_assistant.analytics import InteractionAnalytics
from src.jarvis_ai_assistant.api_services import APIService
from src.jarvis_ai_assistant.assistant import JarvisAssistant
from src.jarvis_ai_assistant.automation_module import AutomationModule
from src.jarvis_ai_assistant.calculator import Calculator
from src.jarvis_ai_assistant.desktop_integration import StartupManager
from src.jarvis_ai_assistant.models import AssistantResponse, InteractionRecord
from src.jarvis_ai_assistant.memory_store import MemoryStore
from src.jarvis_ai_assistant.nlp_engine import NLPEngine
from src.jarvis_ai_assistant.preferences_store import PreferencesStore
from src.jarvis_ai_assistant.reminder_store import ReminderStore
from src.jarvis_ai_assistant.voice_module import VoiceModule


class NLPEngineTests(unittest.TestCase):
    def test_intent_accuracy_target_is_met(self) -> None:
        engine = NLPEngine()
        self.assertGreaterEqual(engine.evaluate(), 0.85)

    def test_predicts_expected_intents_for_known_commands(self) -> None:
        engine = NLPEngine()
        self.assertEqual(engine.predict("open notepad").intent, "open_application")
        self.assertEqual(engine.predict("tell me the weather in delhi").intent, "weather_query")
        self.assertEqual(engine.predict("tell me the latest news").intent, "news_query")
        self.assertEqual(engine.predict("play believer on youtube").intent, "play_music")


class APIServiceTests(unittest.TestCase):
    def test_get_weather_parses_response(self) -> None:
        service = APIService()
        fake_response = mock.Mock()
        fake_response.json.return_value = {
            "name": "Delhi",
            "main": {"temp": 30.5, "humidity": 40},
            "weather": [{"description": "clear sky"}],
            "wind": {"speed": 2.5},
        }

        with mock.patch("src.jarvis_ai_assistant.api_services.SETTINGS", SimpleNamespace(weather_api_key="key", default_city="Delhi")), \
             mock.patch.object(service.session, "get", return_value=fake_response) as get_mock:
            weather = service.get_weather()

        self.assertEqual(weather["city"], "Delhi")
        self.assertEqual(weather["description"], "clear sky")
        get_mock.assert_called_once()

    def test_get_news_parses_articles(self) -> None:
        service = APIService()
        fake_response = mock.Mock()
        fake_response.json.return_value = {
            "articles": [
                {"title": "A", "source": {"name": "S1"}, "url": "https://a"},
                {"title": "B", "source": {"name": "S2"}, "url": "https://b"},
            ]
        }

        with mock.patch("src.jarvis_ai_assistant.api_services.SETTINGS", SimpleNamespace(news_api_key="key")), \
             mock.patch.object(service.session, "get", return_value=fake_response):
            articles = service.get_news("technology", limit=2)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["title"], "A")

    def test_create_calendar_event_builds_expected_payload(self) -> None:
        service = APIService()
        when = datetime(2026, 4, 24, 18, 0, 0)
        execute_mock = mock.Mock(return_value={
            "summary": "demo",
            "start": {"dateTime": "2026-04-24T18:00:00"},
            "htmlLink": "https://calendar.example",
        })
        insert_mock = mock.Mock(return_value=SimpleNamespace(execute=execute_mock))
        events_mock = mock.Mock(return_value=SimpleNamespace(insert=insert_mock))
        calendar_service = SimpleNamespace(events=events_mock)

        with mock.patch.object(service, "_build_calendar_service", return_value=calendar_service), \
             mock.patch.object(service, "_parse_datetime", return_value=when):
            event = service.create_calendar_event("demo", "today 6 pm")

        self.assertEqual(event["summary"], "demo")
        insert_mock.assert_called_once()


class AutomationModuleTests(unittest.TestCase):
    def test_open_application_uses_subprocess(self) -> None:
        module = AutomationModule()
        with mock.patch("src.jarvis_ai_assistant.automation_module.subprocess.Popen") as popen_mock:
            response = module.open_application("notepad")
        self.assertTrue(response.success)
        popen_mock.assert_called_once()

    def test_open_application_maps_notebook_to_notepad(self) -> None:
        module = AutomationModule()
        with mock.patch("src.jarvis_ai_assistant.automation_module.subprocess.Popen") as popen_mock:
            response = module.open_application("notebook")
        self.assertTrue(response.success)
        popen_mock.assert_called_once_with("notepad.exe")

    def test_open_application_falls_back_to_web_search(self) -> None:
        module = AutomationModule()
        with mock.patch("src.jarvis_ai_assistant.automation_module.subprocess.Popen", side_effect=OSError), \
             mock.patch("src.jarvis_ai_assistant.automation_module.webbrowser.open") as web_open:
            response = module.open_application("unknownapp")
        self.assertFalse(response.success)
        web_open.assert_called_once()

    def test_file_operations_create_file_and_folder_in_home(self) -> None:
        module = AutomationModule()
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_home = Path(temp_dir)
            (fake_home / "Desktop").mkdir()
            with mock.patch("src.jarvis_ai_assistant.automation_module.Path.home", return_value=fake_home), \
                 mock.patch("src.jarvis_ai_assistant.automation_module.os.startfile"):
                file_response = module.handle_file_operation("create a file named notes")
                folder_response = module.handle_file_operation("create a folder for reports")

            self.assertEqual(file_response.action, "create_file")
            self.assertTrue((fake_home / "Desktop" / "jarvis_note.txt").exists())
            self.assertEqual(folder_response.action, "create_folder")
            self.assertTrue((fake_home / "Desktop" / "JarvisFolder").exists())

    def test_play_music_opens_platform_search(self) -> None:
        module = AutomationModule()
        with mock.patch.object(module, "_resolve_youtube_video_url", return_value="https://www.youtube.com/watch?v=abc123"), \
             mock.patch("src.jarvis_ai_assistant.automation_module.webbrowser.open") as web_open:
            response = module.play_music("believer", "youtube")
        self.assertEqual(response.action, "play_music_youtube")
        self.assertIn("autoplay=1", response.payload["url"])
        web_open.assert_called_once()

    def test_play_music_falls_back_to_youtube_search_when_direct_resolution_fails(self) -> None:
        module = AutomationModule()
        with mock.patch.object(module, "_resolve_youtube_video_url", return_value=None), \
             mock.patch("src.jarvis_ai_assistant.automation_module.webbrowser.open") as web_open:
            response = module.play_music("believer", "youtube")
        self.assertEqual(response.action, "play_music_youtube_search")
        web_open.assert_called_once()

    def test_resolve_youtube_via_html_parses_first_video(self) -> None:
        fake_response = mock.Mock()
        fake_response.text = '"videoId":"abc123def45"'
        module = AutomationModule()
        with mock.patch("src.jarvis_ai_assistant.automation_module.requests.get", return_value=fake_response):
            url = module._resolve_youtube_via_html("believer")
        self.assertEqual(url, "https://www.youtube.com/watch?v=abc123def45")


class CalculatorTests(unittest.TestCase):
    def test_evaluates_natural_language_math(self) -> None:
        calculator = Calculator()
        expression, result = calculator.evaluate("what is 25 divided by 5 plus 3")
        self.assertEqual(expression, "25/5+3")
        self.assertEqual(result, 8.0)

    def test_detects_percent_and_square_root(self) -> None:
        calculator = Calculator()
        self.assertTrue(calculator.can_handle("20 percent of 50"))
        self.assertEqual(calculator.evaluate("20 percent of 50")[1], 10.0)
        self.assertEqual(calculator.evaluate("square root of 81")[1], 9.0)


class DesktopIntegrationTests(unittest.TestCase):
    def test_startup_manager_enable_invokes_powershell_shortcut_creation(self) -> None:
        manager = StartupManager()
        shortcut_path = Path("C:/Users/ag950/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/Jarvis.lnk")
        with mock.patch.object(manager, "_shortcut_path", return_value=shortcut_path), \
             mock.patch("src.jarvis_ai_assistant.desktop_integration.subprocess.run") as run_mock:
            manager.enable(
                target="C:/Python/pythonw.exe",
                arguments="-m src.jarvis_ai_assistant.main --minimized",
                working_directory="C:/Users/ag950/jarvis_ai_assistant",
            )

        run_mock.assert_called_once()
        self.assertIn("CreateShortcut", run_mock.call_args.args[0][-1])


class AnalyticsTests(unittest.TestCase):
    def test_usage_summary_reports_expected_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analytics = InteractionAnalytics(csv_path=Path(temp_dir) / "interactions.csv")
            analytics.log(
                InteractionRecord(
                    timestamp=datetime(2026, 4, 24, 12, 0, 0),
                    command="open notepad",
                    intent="open_application",
                    confidence=0.91,
                    success=True,
                    response="Opening notepad.",
                )
            )
            analytics.log(
                InteractionRecord(
                    timestamp=datetime(2026, 4, 24, 12, 5, 0),
                    command="latest news",
                    intent="news_query",
                    confidence=0.85,
                    success=False,
                    response="I could not fetch the news right now.",
                )
            )
            summary = analytics.usage_summary()

        self.assertEqual(summary["total_commands"], 2)
        self.assertEqual(summary["average_confidence"], 0.88)
        self.assertEqual(summary["success_rate"], 0.5)


class ReminderStoreTests(unittest.TestCase):
    def test_add_reminder_persists_and_lists_upcoming(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ReminderStore(storage_path=Path(temp_dir) / "reminders.json")
            reminder = store.add_reminder("pay rent", "tomorrow 9 am")
            upcoming = store.list_upcoming()

        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0].subject, "pay rent")
        self.assertEqual(reminder.subject, "pay rent")

    def test_due_reminders_can_be_marked_notified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ReminderStore(storage_path=Path(temp_dir) / "reminders.json")
            reminder = store.add_reminder("submit report", None)
            due_before = store.due_reminders(reference_time=datetime.now())
            store.mark_notified(reminder.id, notified_at=datetime.now())
            due_after = store.due_reminders(reference_time=datetime.now())

        self.assertEqual(len(due_before), 1)
        self.assertEqual(len(due_after), 0)

    def test_complete_and_snooze_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ReminderStore(storage_path=Path(temp_dir) / "reminders.json")
            reminder = store.add_reminder("team meeting", "tomorrow 9 am")
            snoozed = store.snooze_reminder(reminder.id, minutes=10)
            completed = store.complete_reminder(reminder.id)
            upcoming = store.list_upcoming()

        self.assertIsNotNone(snoozed)
        self.assertTrue(completed.completed)
        self.assertEqual(upcoming, [])


class PreferencesStoreTests(unittest.TestCase):
    def test_preferences_persist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PreferencesStore(storage_path=Path(temp_dir) / "preferences.json")
            store.save(
                {
                    "voice_mode": "Voice Input",
                    "notifications_enabled": False,
                    "popup_notifications": False,
                    "reminder_poll_seconds": 60,
                }
            )
            payload = store.load()

        self.assertEqual(payload["voice_mode"], "Voice Input")
        self.assertFalse(payload["notifications_enabled"])
        self.assertEqual(payload["reminder_poll_seconds"], 60)


class MemoryStoreTests(unittest.TestCase):
    def test_memory_persists_and_searches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(storage_path=Path(temp_dir) / "memory.json", limit=10)
            store.append("open notepad", "Opening notepad.")
            store.append("play believer", "Playing believer.")
            recent = store.recent()
            search = store.search("believer")

        self.assertEqual(len(recent), 2)
        self.assertEqual(search[0]["command"], "play believer")


class AssistantTests(unittest.TestCase):
    def test_calendar_and_file_creation_require_confirmation(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.nlp = mock.Mock()
        assistant.nlp.predict.side_effect = [
            SimpleNamespace(
                intent="schedule_calendar",
                confidence=0.9,
                normalized_text="schedule a meeting tomorrow at 3 pm",
                entities={"subject": "meeting", "when": "tomorrow at 3 pm"},
            ),
            SimpleNamespace(
                intent="file_operation",
                confidence=0.9,
                normalized_text="create a file named notes",
                entities={"query": "create a file named notes"},
            ),
        ]

        calendar_response = assistant.handle_command("schedule a meeting tomorrow at 3 pm")
        assistant.pending_confirmation = None
        file_response = assistant.handle_command("create a file named notes")

        self.assertTrue(calendar_response.requires_confirmation)
        self.assertEqual(calendar_response.action, "confirmation_required")
        self.assertTrue(file_response.requires_confirmation)

    def test_yes_confirms_pending_action(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.pending_confirmation = {
            "intent": "schedule_calendar",
            "entities": {"subject": "meeting", "when": "today 6 pm"},
            "text": "schedule a meeting today at 6 pm",
            "original_command": "schedule a meeting today at 6 pm",
        }
        assistant.api = mock.Mock()
        assistant.api.create_calendar_event.return_value = {
            "summary": "meeting",
            "start": "2026-04-24T18:00:00",
            "htmlLink": "https://calendar.example",
        }

        response = assistant.handle_command("yes")

        self.assertEqual(response.action, "schedule_calendar")
        self.assertIsNone(assistant.pending_confirmation)

    def test_math_commands_are_answered_locally(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.automation = mock.Mock()

        response = assistant.handle_command("what is 12 * (3 + 1)")

        self.assertEqual(response.action, "math_calculation")
        self.assertIn("48", response.message)
        assistant.automation.search_web.assert_not_called()

    def test_memory_rules_return_recent_commands(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.automation = mock.Mock()
        assistant.automation.open_application.return_value = AssistantResponse(
            message="Opening notepad.",
            action="open_application",
        )
        assistant.handle_command("open notepad")
        response = assistant.handle_command("show recent commands")
        self.assertEqual(response.action, "memory_query")
        self.assertIn("open notepad", response.message)

    def test_reminder_rule_actions(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.reminders = mock.Mock()
        assistant.reminders.list_upcoming.return_value = [SimpleNamespace(id="r1", subject="pay rent")]
        assistant.reminders.complete_reminder.return_value = SimpleNamespace(id="r1", subject="pay rent")
        assistant.reminders.snooze_reminder.return_value = SimpleNamespace(
            id="r1",
            subject="pay rent",
            scheduled_for=datetime(2026, 4, 27, 12, 15, 0),
        )

        completed = assistant.handle_command("complete reminder")
        snoozed = assistant.handle_command("snooze reminder for 15 minutes")

        self.assertEqual(completed.action, "complete_reminder")
        self.assertEqual(snoozed.action, "snooze_reminder")

    def test_play_music_dispatch_uses_automation(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.automation = mock.Mock()
        assistant.automation.play_music.return_value = AssistantResponse(
            message="Playing believer on YouTube.",
            action="play_music_youtube",
        )

        response = assistant._dispatch(
            "play_music",
            {"song_query": "believer", "platform": "youtube"},
            "play believer on youtube",
        )

        self.assertEqual(response.action, "play_music_youtube")
        assistant.automation.play_music.assert_called_once_with(
            song_query="believer",
            platform="youtube",
        )

    def test_supported_low_confidence_intent_still_dispatches(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.nlp = mock.Mock()
        assistant.automation = mock.Mock()
        assistant.nlp.predict.return_value = SimpleNamespace(
            intent="open_application",
            confidence=0.40,
            normalized_text="open notepad",
            entities={"application": "notepad"},
        )
        assistant.automation.open_application.return_value = AssistantResponse(
            message="Opening notepad.",
            action="open_application",
        )

        response = assistant.handle_command("open notepad")

        self.assertEqual(response.action, "open_application")
        assistant.automation.open_application.assert_called_once_with("notepad")

    def test_low_confidence_commands_fall_back_to_search(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.nlp = mock.Mock()
        assistant.automation = mock.Mock()
        assistant.nlp.predict.return_value = SimpleNamespace(
            intent="general_query",
            confidence=0.1,
            normalized_text="tell me something obscure",
            entities={},
        )
        assistant.automation.search_web.return_value = AssistantResponse(
            message="Searching the web for tell me something obscure.",
            action="search_web",
        )

        response = assistant.handle_command("tell me something obscure")

        self.assertFalse(response.success)
        self.assertEqual(response.action, "low_confidence_fallback")
        assistant.automation.search_web.assert_called_once()

    def test_weather_dispatch_uses_api_service(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.api = mock.Mock()
        assistant.api.get_weather.return_value = {
            "city": "Delhi",
            "description": "clear sky",
            "temperature": 30,
        }

        response = assistant._dispatch("weather_query", {"city": "Delhi"}, "weather in delhi")

        self.assertEqual(response.action, "weather_query")
        self.assertIn("Delhi", response.message)

    def test_calendar_dispatch_returns_created_event_message(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.api = mock.Mock()
        assistant.api.create_calendar_event.return_value = {
            "summary": "meeting",
            "start": "2026-04-24T18:00:00",
            "htmlLink": "https://calendar.example",
        }

        response = assistant._dispatch(
            "schedule_calendar",
            {"subject": "meeting", "when": "today 6 pm"},
            "schedule a meeting today at 6 pm",
        )

        self.assertEqual(response.action, "schedule_calendar")
        self.assertIn("meeting", response.message)

    def test_reminder_dispatch_persists_and_returns_formatted_response(self) -> None:
        assistant = JarvisAssistant(enable_voice=False)
        assistant.reminders = mock.Mock()
        assistant.reminders.add_reminder.return_value = SimpleNamespace(
            id="r1",
            scheduled_for=datetime(2026, 4, 25, 9, 0, 0),
        )

        response = assistant._dispatch(
            "set_reminder",
            {"subject": "pay rent", "when": "tomorrow 9 am"},
            "remind me to pay rent tomorrow 9 am",
        )

        self.assertEqual(response.action, "set_reminder")
        self.assertIn("25 Apr", response.message)
        self.assertEqual(response.payload["reminder_id"], "r1")


class GUISmokeTests(unittest.TestCase):
    def test_gui_initializes_core_controls(self) -> None:
        from src.jarvis_ai_assistant.gui import JarvisGUI

        fake_assistant = SimpleNamespace(
            voice=None,
            usage_summary=lambda: {
                "total_commands": 0,
                "average_confidence": 0.0,
                "success_rate": 0.0,
                "top_intents": {},
            },
            configured_integrations=lambda: {
                "weather_api": False,
                "news_api": False,
                "google_calendar_credentials": False,
                "google_calendar_token": False,
            },
            upcoming_reminders=lambda: ["No upcoming reminders."],
            due_reminders=lambda: [],
            mark_reminder_notified=lambda _id: None,
            complete_next_reminder=lambda: AssistantResponse(message="Completed reminder."),
            snooze_next_reminder=lambda minutes=15: AssistantResponse(message="Snoozed reminder."),
            complete_reminder=lambda reminder_id: AssistantResponse(message=f"Completed {reminder_id}."),
            snooze_reminder=lambda reminder_id, minutes=15: AssistantResponse(message=f"Snoozed {reminder_id}."),
            preprocess_voice_command=lambda heard_text, require_wake_word: (heard_text, None),
            configure_voice=lambda enabled, device_index=None: False,
            nlp=mock.Mock(),
            handle_command=mock.Mock(return_value=AssistantResponse(message="ok")),
            test_microphone=mock.Mock(return_value=(False, "No speech")),
            create_audio_monitor=mock.Mock(),
            listen_once=mock.Mock(return_value=None),
            speak=mock.Mock(),
        )
        fake_diagnostics = {
            "microphone_available": False,
            "device_count": 0,
            "devices": [],
            "device_options": [],
            "tts_available": False,
            "meter_available": False,
            "error": "No microphone input devices were detected.",
        }

        with mock.patch("src.jarvis_ai_assistant.gui.JarvisAssistant", return_value=fake_assistant), \
             mock.patch("src.jarvis_ai_assistant.gui.VoiceModule.describe_environment", return_value=fake_diagnostics):
            app = JarvisGUI()
            try:
                self.assertEqual(app.voice_mode.get(), "Text Only")
                self.assertEqual(app.selected_microphone.get(), "System Default")
                self.assertIsNotNone(app.listen_button)
                self.assertIsNotNone(app.meter_button)
            finally:
                app.root.destroy()

    def test_gui_applies_startup_preference(self) -> None:
        from src.jarvis_ai_assistant.gui import JarvisGUI

        fake_assistant = SimpleNamespace(
            voice=None,
            usage_summary=lambda: {"total_commands": 0, "average_confidence": 0.0, "success_rate": 0.0, "top_intents": {}},
            configured_integrations=lambda: {
                "weather_api": False,
                "news_api": False,
                "google_calendar_credentials": False,
                "google_calendar_token": False,
            },
            upcoming_reminders=lambda: ["No upcoming reminders."],
            due_reminders=lambda: [],
            mark_reminder_notified=lambda _id: None,
            complete_next_reminder=lambda: AssistantResponse(message="Completed reminder."),
            snooze_next_reminder=lambda minutes=15: AssistantResponse(message="Snoozed reminder."),
            complete_reminder=lambda reminder_id: AssistantResponse(message=f"Completed {reminder_id}."),
            snooze_reminder=lambda reminder_id, minutes=15: AssistantResponse(message=f"Snoozed {reminder_id}."),
            preprocess_voice_command=lambda heard_text, require_wake_word: (heard_text, None),
            configure_voice=lambda enabled, device_index=None: False,
            nlp=mock.Mock(),
            handle_command=mock.Mock(return_value=AssistantResponse(message="ok")),
            test_microphone=mock.Mock(return_value=(False, "No speech")),
            create_audio_monitor=mock.Mock(),
            listen_once=mock.Mock(return_value=None),
            speak=mock.Mock(),
        )
        fake_diagnostics = {
            "microphone_available": False,
            "device_count": 0,
            "devices": [],
            "device_options": [],
            "tts_available": False,
            "meter_available": False,
            "error": "No microphone input devices were detected.",
        }

        with mock.patch("src.jarvis_ai_assistant.gui.JarvisAssistant", return_value=fake_assistant), \
             mock.patch("src.jarvis_ai_assistant.gui.VoiceModule.describe_environment", return_value=fake_diagnostics):
            app = JarvisGUI()
            try:
                app.startup_manager = mock.Mock()
                app.startup_manager.is_available.return_value = True
                app.launch_on_startup.set(True)
                message = app._apply_startup_preference()
                self.assertIn("Windows startup", message)
                app.startup_manager.enable.assert_called_once()
            finally:
                app.root.destroy()


class VoiceModuleTests(unittest.TestCase):
    def test_strip_wake_word(self) -> None:
        self.assertEqual(VoiceModule.strip_wake_word("jarvis open notepad", "jarvis"), "open notepad")
        self.assertEqual(VoiceModule.strip_wake_word("jarvis, play believer", "jarvis"), "play believer")
        self.assertIsNone(VoiceModule.strip_wake_word("open notepad", "jarvis"))


if __name__ == "__main__":
    unittest.main()
