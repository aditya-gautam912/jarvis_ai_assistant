"""CustomTkinter desktop interface for the Jarvis assistant."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from .assistant import JarvisAssistant
from .config import SETTINGS
from .desktop_integration import StartupManager, TrayController
from .preferences_store import PreferencesStore
from .voice_module import VoiceModule


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class JarvisGUI:
    """Desktop UI that wraps the assistant's text and voice workflows."""

    def __init__(self, start_minimized: bool = False) -> None:
        self.assistant = JarvisAssistant(enable_voice=True)
        self.preferences_store = PreferencesStore()
        self.preferences = self.preferences_store.load()
        self.root = ctk.CTk()
        self.root.title("Jarvis AI Voice Assistant")
        self.root.geometry("1180x760")
        self.root.minsize(980, 680)
        self.root.configure(fg_color="#0b141b")

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        initial_voice_mode = str(self.preferences.get("voice_mode", "Full Voice"))
        if self.assistant.voice is None and initial_voice_mode != "Text Only":
            initial_voice_mode = "Text Only"
        self.voice_mode = tk.StringVar(value=initial_voice_mode)
        self.status_text = tk.StringVar(value="Ready for commands.")
        self.assistant_state_text = tk.StringVar(value="Idle")
        self.intent_text = tk.StringVar(value="Intent: waiting")
        self.confidence_text = tk.StringVar(value="Confidence: --")
        self.voice_status_text = tk.StringVar(value="")
        self.device_text = tk.StringVar(value="")
        self.reminder_text = tk.StringVar(value="No upcoming reminders.")
        self.selected_microphone = tk.StringVar(value="System Default")
        self.notifications_enabled = tk.BooleanVar(value=bool(self.preferences.get("notifications_enabled", True)))
        self.popup_notifications = tk.BooleanVar(value=bool(self.preferences.get("popup_notifications", True)))
        self.reminder_poll_seconds = tk.IntVar(value=int(self.preferences.get("reminder_poll_seconds", 20)))
        self.require_wake_word = tk.BooleanVar(value=bool(self.preferences.get("require_wake_word", True)))
        self.continuous_listening = tk.BooleanVar(value=bool(self.preferences.get("continuous_listening", False)))
        self.start_minimized = tk.BooleanVar(
            value=bool(start_minimized or self.preferences.get("start_minimized", False))
        )
        self.background_on_close = tk.BooleanVar(value=bool(self.preferences.get("background_on_close", True)))
        self.tray_enabled = tk.BooleanVar(value=bool(self.preferences.get("tray_enabled", True)))
        self.launch_on_startup = tk.BooleanVar(value=bool(self.preferences.get("launch_on_startup", False)))
        self.command_var = tk.StringVar()
        self.listening = False
        self.testing_microphone = False
        self.meter_running = False
        self.continuous_listener_running = False
        self.meter_level = tk.DoubleVar(value=0.0)
        self.voice_diagnostics = VoiceModule.describe_environment()
        self.settings_window: ctk.CTkToplevel | None = None
        self.background_window: ctk.CTkToplevel | None = None
        self.tray_controller = TrayController()
        self.startup_manager = StartupManager()

        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close_request)
        self._refresh_microphone_picker()
        self._refresh_analytics()
        self._refresh_integrations()
        self._refresh_reminders()
        self._refresh_voice_panel()
        self.root.after(150, self._drain_events)
        self.root.after(1000, self._check_due_reminders)
        if self.continuous_listening.get() and self._voice_input_enabled() and self.assistant.voice is not None:
            self.root.after(1200, self._toggle_continuous_listening)
        if self.start_minimized.get():
            self.root.after(800, self._hide_to_background)

    def run(self) -> None:
        """Start the desktop application."""
        self.root.mainloop()

    def _build_layout(self) -> None:
        container = ctk.CTkFrame(self.root, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=18, pady=18)
        container.grid_columnconfigure(0, weight=3)
        container.grid_columnconfigure(1, weight=2)
        container.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(container, fg_color="#12212d", corner_radius=18)
        header.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=0)
        header.grid_columnconfigure(3, weight=0)

        ctk.CTkLabel(
            header,
            text="JARVIS",
            font=ctk.CTkFont(family="Bahnschrift", size=30, weight="bold"),
            text_color="#f8c15c",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(
            header,
            text="CustomTkinter desktop assistant with voice, NLP, reminders, and automation",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#d8e5ed",
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))
        self.status_label = ctk.CTkLabel(
            header,
            textvariable=self.status_text,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#f8c15c",
        )
        self.status_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=(0, 14))
        ctk.CTkButton(
            header,
            text="Settings",
            width=110,
            fg_color="#23404f",
            hover_color="#2f5569",
            command=self._open_settings,
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(0, 22))
        ctk.CTkButton(
            header,
            text="Background",
            width=110,
            fg_color="#173a2d",
            hover_color="#20523a",
            command=self._hide_to_background,
        ).grid(row=0, column=3, rowspan=2, sticky="e", padx=(0, 12))

        left = ctk.CTkFrame(container, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        controls = ctk.CTkFrame(left, fg_color="#12212d", corner_radius=18)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        controls.grid_columnconfigure(0, weight=1)
        controls.grid_columnconfigure(1, weight=0)
        controls.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(
            controls,
            text="Command Center",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f8c15c",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(16, 10))

        self.command_entry = ctk.CTkEntry(
            controls,
            textvariable=self.command_var,
            height=42,
            corner_radius=12,
            fg_color="#0c1720",
            border_color="#274152",
            text_color="#eef6fb",
            placeholder_text="Ask Jarvis to do something...",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.command_entry.grid(row=1, column=0, columnspan=3, sticky="ew", padx=18, pady=(0, 12))
        self.command_entry.bind("<Return>", self._submit_command)

        ctk.CTkButton(
            controls,
            text="Send Command",
            height=38,
            fg_color="#1e5f74",
            hover_color="#277d97",
            command=self._submit_command,
        ).grid(row=2, column=0, sticky="ew", padx=(18, 8), pady=(0, 12))
        self.listen_button = ctk.CTkButton(
            controls,
            text="Voice Listen",
            height=38,
            fg_color="#23404f",
            hover_color="#2f5569",
            command=self._start_voice_capture,
        )
        self.listen_button.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(0, 12))
        self.continuous_button = ctk.CTkButton(
            controls,
            text="Start Continuous",
            height=38,
            fg_color="#3d2e5f",
            hover_color="#56427e",
            command=self._toggle_continuous_listening,
        )
        self.continuous_button.grid(row=2, column=2, sticky="ew", padx=(0, 18), pady=(0, 12))
        self.mode_selector = ctk.CTkComboBox(
            controls,
            variable=self.voice_mode,
            values=["Text Only", "Voice Input", "Full Voice"],
            command=self._on_mode_changed,
            button_color="#23404f",
            border_color="#274152",
            fg_color="#0c1720",
            dropdown_fg_color="#12212d",
            dropdown_hover_color="#1d3442",
        )
        self.mode_selector.grid(row=3, column=0, sticky="ew", padx=(18, 8), pady=(0, 12))

        self.intent_label = ctk.CTkLabel(
            controls,
            textvariable=self.intent_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d8e5ed",
        )
        self.intent_label.grid(row=4, column=0, sticky="w", padx=18, pady=(0, 16))
        self.confidence_label = ctk.CTkLabel(
            controls,
            textvariable=self.confidence_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d8e5ed",
        )
        self.confidence_label.grid(row=4, column=1, columnspan=2, sticky="e", padx=18, pady=(0, 16))
        ctk.CTkLabel(
            controls,
            text=f"Wake word: {SETTINGS.wake_word}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#9fb4c3",
        ).grid(row=3, column=1, columnspan=2, sticky="e", padx=18, pady=(0, 12))

        history_frame = ctk.CTkFrame(left, fg_color="#12212d", corner_radius=18)
        history_frame.grid(row=1, column=0, sticky="nsew")
        history_frame.grid_rowconfigure(1, weight=1)
        history_frame.grid_columnconfigure(0, weight=1)

        history_header = ctk.CTkFrame(history_frame, fg_color="#162a38", corner_radius=14)
        history_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        history_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            history_header,
            text="Live Conversation",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#f8c15c",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=10)
        self.state_badge = ctk.CTkLabel(
            history_header,
            textvariable=self.assistant_state_text,
            corner_radius=999,
            fg_color="#173a2d",
            text_color="#99f6b2",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            padx=14,
            pady=6,
        )
        self.state_badge.grid(row=0, column=1, sticky="e", padx=14, pady=10)

        self.history = ctk.CTkScrollableFrame(
            history_frame,
            fg_color="#0c1720",
            corner_radius=14,
            scrollbar_button_color="#23404f",
            scrollbar_button_hover_color="#2f5569",
        )
        self.history.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.history.grid_columnconfigure(0, weight=1)
        self._append_history("Jarvis", "GUI is ready.", "meta")

        right = ctk.CTkFrame(container, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_rowconfigure(4, weight=1)
        right.grid_columnconfigure(0, weight=1)

        voice_panel = ctk.CTkFrame(right, fg_color="#12212d", corner_radius=18)
        voice_panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        voice_panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            voice_panel,
            text="Voice Status",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f8c15c",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))
        self.voice_status_label = ctk.CTkLabel(
            voice_panel,
            textvariable=self.voice_status_text,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d8e5ed",
        )
        self.voice_status_label.grid(row=1, column=0, sticky="ew", padx=18)
        self.device_status_label = ctk.CTkLabel(
            voice_panel,
            textvariable=self.device_text,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#9fb4c3",
        )
        self.device_status_label.grid(row=2, column=0, sticky="ew", padx=18, pady=(8, 0))

        button_row = ctk.CTkFrame(voice_panel, fg_color="transparent")
        button_row.grid(row=3, column=0, sticky="ew", padx=18, pady=(14, 8))
        button_row.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(
            button_row,
            text="Refresh Devices",
            fg_color="#23404f",
            hover_color="#2f5569",
            command=self._refresh_voice_diagnostics,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.test_mic_button = ctk.CTkButton(
            button_row,
            text="Test Microphone",
            fg_color="#23404f",
            hover_color="#2f5569",
            command=self._start_microphone_test,
        )
        self.test_mic_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.meter_button = ctk.CTkButton(
            button_row,
            text="Start Meter",
            fg_color="#23404f",
            hover_color="#2f5569",
            command=self._toggle_audio_meter,
        )
        self.meter_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.microphone_picker = ctk.CTkComboBox(
            voice_panel,
            variable=self.selected_microphone,
            values=["System Default"],
            command=self._on_microphone_changed,
            button_color="#23404f",
            border_color="#274152",
            fg_color="#0c1720",
            dropdown_fg_color="#12212d",
            dropdown_hover_color="#1d3442",
        )
        self.microphone_picker.grid(row=4, column=0, sticky="ew", padx=18, pady=(6, 10))
        self.meter_bar = ctk.CTkProgressBar(
            voice_panel,
            progress_color="#f8c15c",
            fg_color="#203545",
        )
        self.meter_bar.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 16))
        self.meter_bar.set(0)

        reminder_panel = ctk.CTkFrame(right, fg_color="#12212d", corner_radius=18)
        reminder_panel.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            reminder_panel,
            text="Upcoming Reminders",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f8c15c",
        ).pack(anchor="w", padx=18, pady=(16, 8))
        self.reminder_label = ctk.CTkLabel(
            reminder_panel,
            textvariable=self.reminder_text,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d8e5ed",
        )
        self.reminder_label.pack(fill="x", padx=18, pady=(0, 16))
        reminder_actions = ctk.CTkFrame(reminder_panel, fg_color="transparent")
        reminder_actions.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(
            reminder_actions,
            text="Show",
            width=80,
            fg_color="#23404f",
            hover_color="#2f5569",
            command=self._show_reminders_in_chat,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            reminder_actions,
            text="Complete Next",
            width=120,
            fg_color="#20523a",
            hover_color="#2b6b4c",
            command=self._complete_next_reminder,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            reminder_actions,
            text="Snooze 15m",
            width=110,
            fg_color="#5b4318",
            hover_color="#7a5a21",
            command=self._snooze_next_reminder,
        ).pack(side="left", padx=8)

        analytics_panel = ctk.CTkFrame(right, fg_color="#12212d", corner_radius=18)
        analytics_panel.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            analytics_panel,
            text="Usage Summary",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f8c15c",
        ).pack(anchor="w", padx=18, pady=(16, 8))
        self.analytics_label = ctk.CTkLabel(
            analytics_panel,
            text="No interactions yet.",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d8e5ed",
        )
        self.analytics_label.pack(fill="x", padx=18, pady=(0, 16))

        integration_panel = ctk.CTkFrame(right, fg_color="#12212d", corner_radius=18)
        integration_panel.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            integration_panel,
            text="Integration Status",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f8c15c",
        ).pack(anchor="w", padx=18, pady=(16, 8))
        self.integration_label = ctk.CTkLabel(
            integration_panel,
            text="Checking integrations...",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d8e5ed",
        )
        self.integration_label.pack(fill="x", padx=18, pady=(0, 16))

        shortcuts = ctk.CTkFrame(right, fg_color="#12212d", corner_radius=18)
        shortcuts.grid(row=4, column=0, sticky="nsew")
        shortcuts.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            shortcuts,
            text="Quick Commands",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#f8c15c",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))
        commands = [
            "Open Notepad",
            "What is the weather in Delhi",
            "Tell me the latest technology news",
            "Open my downloads folder",
            "Schedule a meeting tomorrow at 3 pm",
            "Who is Alan Turing",
        ]
        for index, command in enumerate(commands, start=1):
            ctk.CTkButton(
                shortcuts,
                text=command,
                fg_color="#162a38",
                hover_color="#20394a",
                anchor="w",
                command=lambda value=command: self._queue_preset(value),
            ).grid(row=index, column=0, sticky="ew", padx=18, pady=5)

        self._apply_voice_mode()

    def _queue_preset(self, command: str) -> None:
        self.command_var.set(command)
        self._submit_command()

    def _submit_command(self, _event=None) -> None:
        command = self.command_var.get().strip()
        if not command:
            self.status_text.set("Enter a command first.")
            return

        self.command_var.set("")
        self._append_history("You", command, "user")
        self.status_text.set("Processing command...")
        self._set_assistant_state("Thinking")
        speak_enabled = self._spoken_replies_enabled()
        threading.Thread(
            target=self._process_command,
            args=(command, speak_enabled),
            daemon=True,
        ).start()

    def _process_command(self, command: str, speak_enabled: bool) -> None:
        result = self.assistant.nlp.predict(command)
        response = self.assistant.handle_command(command)
        self.events.put(("response", response.message))
        self.events.put(("intent", result.intent))
        self.events.put(("confidence", f"{result.confidence:.3f}"))
        self.events.put(("status", "Ready for commands."))
        self.events.put(("analytics", "refresh"))
        self.events.put(("reminders", "refresh"))
        self.events.put(("state", "Speaking" if speak_enabled and self.assistant.voice is not None else "Idle"))
        if speak_enabled and self.assistant.voice is not None:
            self.assistant.speak(response.message)
            self.events.put(("state", "Idle"))
        if response.action == "exit":
            self.events.put(("status", "Exit command received."))

    def _start_voice_capture(self) -> None:
        if self.listening:
            self.status_text.set("Already listening for a voice command.")
            return
        if self.testing_microphone:
            self.status_text.set("Wait for the microphone test to finish.")
            return
        if not self._voice_input_enabled():
            self.status_text.set("Voice mode is off. Switch mode to Voice Input or Full Voice.")
            return
        if self.assistant.voice is None:
            self.status_text.set("Voice input is unavailable on this machine. Check the Voice Status panel.")
            return

        self.listening = True
        self.status_text.set("Listening for voice input...")
        self._set_assistant_state("Listening")
        threading.Thread(target=self._capture_voice, daemon=True).start()

    def _capture_voice(self) -> None:
        try:
            heard = self.assistant.listen_once()
        except OSError:
            heard = None
        if heard:
            command, warning = self.assistant.preprocess_voice_command(
                heard,
                require_wake_word=bool(self.require_wake_word.get()),
            )
            if command:
                self.events.put(("heard", command))
            elif warning:
                self.events.put(("status", warning))
        else:
            self.events.put(("status", "No voice command captured. Check microphone permissions or try text mode."))
        self.events.put(("listening", "done"))

    def _toggle_continuous_listening(self) -> None:
        if self.continuous_listener_running:
            self.continuous_listener_running = False
            self.continuous_button.configure(text="Start Continuous")
            self.status_text.set("Continuous listening stopped.")
            return

        if not self._voice_input_enabled() or self.assistant.voice is None:
            self.status_text.set("Enable voice mode before starting continuous listening.")
            return

        self.continuous_listener_running = True
        self.continuous_button.configure(text="Stop Continuous")
        self.status_text.set("Continuous listening started.")
        threading.Thread(target=self._continuous_listener_loop, daemon=True).start()

    def _continuous_listener_loop(self) -> None:
        while self.continuous_listener_running:
            try:
                heard = self.assistant.listen_once()
            except OSError:
                heard = None
            if not self.continuous_listener_running:
                break
            if not heard:
                continue
            command, warning = self.assistant.preprocess_voice_command(
                heard,
                require_wake_word=bool(self.require_wake_word.get()),
            )
            if command:
                self.events.put(("heard", command))
            elif warning and "Wake word" not in warning:
                self.events.put(("status", warning))
            time.sleep(0.1)

    def _start_microphone_test(self) -> None:
        if self.listening:
            self.status_text.set("Finish the active voice capture before testing the microphone.")
            return
        if self.testing_microphone:
            self.status_text.set("Microphone test already in progress.")
            return
        if self.meter_running:
            self.status_text.set("Stop the live meter before starting a microphone test.")
            return
        if not self.voice_diagnostics.get("microphone_available"):
            self.status_text.set("No microphone devices are available to test.")
            return

        self.testing_microphone = True
        self.status_text.set("Testing selected microphone. Say a short phrase.")
        threading.Thread(target=self._run_microphone_test, daemon=True).start()

    def _run_microphone_test(self) -> None:
        device_index = self._selected_device_index()
        success, message = self.assistant.test_microphone(device_index=device_index)
        if success:
            self.events.put(("mic_test", f"Microphone test passed. Heard: {message}"))
        else:
            self.events.put(("mic_test", f"Microphone test failed. {message}"))
        self.events.put(("mic_test_done", "done"))

    def _toggle_audio_meter(self) -> None:
        if self.meter_running:
            self.meter_running = False
            self.meter_button.configure(text="Start Meter")
            self.meter_level.set(0.0)
            self.meter_bar.set(0)
            self.status_text.set("Live microphone meter stopped.")
            return

        if self.listening or self.testing_microphone:
            self.status_text.set("Wait for the active microphone action to finish.")
            return
        if not self.voice_diagnostics.get("meter_available"):
            self.status_text.set("Live microphone meter is unavailable because PyAudio is not installed.")
            return
        if not self.voice_diagnostics.get("microphone_available"):
            self.status_text.set("No microphone devices are available for the live meter.")
            return

        self.meter_running = True
        self.meter_button.configure(text="Stop Meter")
        self.status_text.set("Live microphone meter started.")
        threading.Thread(target=self._run_audio_meter, daemon=True).start()

    def _run_audio_meter(self) -> None:
        device_index = self._selected_device_index()
        try:
            monitor = self.assistant.create_audio_monitor(device_index=device_index)
        except OSError as exc:
            self.events.put(("meter_error", str(exc)))
            self.events.put(("meter_done", "done"))
            return

        try:
            while self.meter_running:
                level = monitor.read_level()
                self.events.put(("meter_level", f"{level * 100:.1f}"))
                time.sleep(0.05)
        except OSError as exc:
            self.events.put(("meter_error", str(exc)))
        finally:
            monitor.close()
            self.events.put(("meter_done", "done"))

    def _drain_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "response":
                self._append_history("Jarvis", payload, "jarvis")
            elif event == "heard":
                self.command_var.set(payload)
                self._append_history("You (voice)", payload, "user")
                self.status_text.set("Processing voice command...")
                self._set_assistant_state("Thinking")
                speak_enabled = self._spoken_replies_enabled()
                threading.Thread(
                    target=self._process_command,
                    args=(payload, speak_enabled),
                    daemon=True,
                ).start()
            elif event == "intent":
                self.intent_text.set(f"Intent: {payload}")
            elif event == "confidence":
                self.confidence_text.set(f"Confidence: {payload}")
            elif event == "status":
                self.status_text.set(payload)
            elif event == "analytics":
                self._refresh_analytics()
            elif event == "reminders":
                self._refresh_reminders()
            elif event == "state":
                self._set_assistant_state(payload)
            elif event == "listening":
                self.listening = False
                if self.assistant_state_text.get() == "Listening":
                    self._set_assistant_state("Listening" if self.continuous_listener_running else "Idle")
            elif event == "mic_test":
                self._append_history("System", payload, "meta")
                self.status_text.set(payload)
            elif event == "mic_test_done":
                self.testing_microphone = False
            elif event == "meter_level":
                numeric = float(payload)
                self.meter_level.set(numeric)
                self.meter_bar.set(numeric / 100)
            elif event == "meter_error":
                self.status_text.set(f"Live microphone meter failed. {payload}")
                self._append_history("System", f"Live microphone meter failed. {payload}", "meta")
                self.meter_running = False
                self.meter_button.configure(text="Start Meter")
                self.meter_level.set(0.0)
                self.meter_bar.set(0)
            elif event == "meter_done":
                self.meter_running = False
                self.meter_button.configure(text="Start Meter")
                if float(self.meter_level.get()) == 0.0:
                    self.status_text.set("Live microphone meter stopped.")

        self.root.after(150, self._drain_events)

    def _append_history(self, speaker: str, message: str, role: str) -> None:
        timestamp = time.strftime("%H:%M")
        palette = {
            "user": {"card": "#1a5c6e", "label": "#9fe8ff", "text": "#eefbff", "anchor": "e"},
            "jarvis": {"card": "#1a2d3a", "label": "#ffd27e", "text": "#eef4f7", "anchor": "w"},
            "meta": {"card": "#17232d", "label": "#b7c7d5", "text": "#dbe6ed", "anchor": "center"},
        }[role]

        outer = ctk.CTkFrame(self.history, fg_color="transparent")
        outer.pack(fill="x", padx=10, pady=6)
        label = ctk.CTkLabel(
            outer,
            text=f"{speaker}  {timestamp}",
            text_color=palette["label"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            anchor=palette["anchor"],
        )
        bubble = ctk.CTkFrame(outer, fg_color=palette["card"], corner_radius=16)
        body = ctk.CTkLabel(
            bubble,
            text=message,
            text_color=palette["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            justify="left",
            wraplength=520,
            anchor="w",
        )

        if role == "user":
            label.pack(anchor="e", padx=(140, 8))
            bubble.pack(anchor="e", padx=(140, 0))
        elif role == "jarvis":
            label.pack(anchor="w", padx=(8, 140))
            bubble.pack(anchor="w", padx=(0, 140))
        else:
            label.pack(anchor="center")
            bubble.pack(anchor="center", padx=70)

        body.pack(fill="both", expand=True, padx=14, pady=10)
        self.history._parent_canvas.yview_moveto(1.0)

    def _set_assistant_state(self, state: str) -> None:
        self.assistant_state_text.set(state)
        if state == "Listening":
            self.state_badge.configure(fg_color="#274c7a", text_color="#d2e6ff")
        elif state == "Thinking":
            self.state_badge.configure(fg_color="#5b4318", text_color="#ffd986")
        elif state == "Speaking":
            self.state_badge.configure(fg_color="#4e2448", text_color="#ffd3fb")
        else:
            self.state_badge.configure(fg_color="#173a2d", text_color="#99f6b2")

    def _refresh_analytics(self) -> None:
        summary = self.assistant.usage_summary()
        top_intents = summary.get("top_intents", {})
        top_text = ", ".join(f"{key}: {value}" for key, value in top_intents.items()) or "None"
        details = (
            f"Total commands: {summary.get('total_commands', 0)}\n"
            f"Average confidence: {summary.get('average_confidence', 0.0)}\n"
            f"Success rate: {summary.get('success_rate', 0.0)}\n"
            f"Top intents: {top_text}"
        )
        self.analytics_label.configure(text=details)

    def _refresh_integrations(self) -> None:
        status = self.assistant.configured_integrations()
        lines = [
            f"OpenWeather API: {'Configured' if status['weather_api'] else 'Missing key'}",
            f"News API: {'Configured' if status['news_api'] else 'Missing key'}",
            (
                "Google Calendar: Ready"
                if status["google_calendar_credentials"] and status["google_calendar_token"]
                else "Google Calendar: Needs credentials or token"
            ),
            f"System tray: {'Available' if self.tray_controller.is_available() else 'Needs pystray/Pillow install'}",
        ]
        self.integration_label.configure(text="\n".join(lines))

    def _refresh_reminders(self) -> None:
        reminders = self.assistant.upcoming_reminders()
        self.reminder_text.set("\n".join(f"- {line}" for line in reminders))

    def _show_reminders_in_chat(self) -> None:
        self._append_history("Jarvis", "Upcoming reminders: " + "; ".join(self.assistant.upcoming_reminders()), "jarvis")

    def _complete_next_reminder(self) -> None:
        response = self.assistant.complete_next_reminder()
        self._append_history("Jarvis", response.message, "jarvis")
        self._refresh_reminders()

    def _snooze_next_reminder(self) -> None:
        response = self.assistant.snooze_next_reminder()
        self._append_history("Jarvis", response.message, "jarvis")
        self._refresh_reminders()

    def _refresh_voice_diagnostics(self) -> None:
        self.voice_diagnostics = VoiceModule.describe_environment()
        self._refresh_microphone_picker()
        self._reconfigure_voice_for_selection()
        self._apply_voice_mode()

    def _refresh_voice_panel(self) -> None:
        diagnostics = self.voice_diagnostics
        status_lines = [
            f"Voice mode: {self.voice_mode.get()}",
            f"Microphone available: {'Yes' if diagnostics['microphone_available'] else 'No'}",
            f"Speech output available: {'Yes' if diagnostics['tts_available'] else 'No'}",
            f"Live meter available: {'Yes' if diagnostics['meter_available'] else 'No'}",
            f"Detected devices: {diagnostics['device_count']}",
            f"Selected input: {self.selected_microphone.get()}",
        ]
        if diagnostics.get("error"):
            status_lines.append(f"Issue: {diagnostics['error']}")
        self.voice_status_text.set("\n".join(status_lines))

        devices = diagnostics.get("devices", [])
        if devices:
            preview = "\n".join(f"- {device}" for device in devices[:4])
            if len(devices) > 4:
                preview += f"\n... and {len(devices) - 4} more"
            self.device_text.set(preview)
        else:
            self.device_text.set("No input devices detected.")

    def _on_mode_changed(self, _choice=None) -> None:
        self._reconfigure_voice_for_selection()
        self.preferences["voice_mode"] = self.voice_mode.get()
        self.preferences_store.save(self.preferences)
        self._apply_voice_mode()

    def _on_microphone_changed(self, _choice=None) -> None:
        if self.meter_running:
            self.meter_running = False
            self.meter_button.configure(text="Start Meter")
            self.meter_level.set(0.0)
            self.meter_bar.set(0)
        self._reconfigure_voice_for_selection()
        self._apply_voice_mode()

    def _apply_voice_mode(self) -> None:
        voice_input = self._voice_input_enabled()
        if voice_input and self.assistant.voice is None:
            self.voice_mode.set("Text Only")
            self.mode_selector.set("Text Only")
            self.status_text.set("Voice mode requested, but no microphone stack is available. Falling back to text mode.")
            voice_input = False

        self.listen_button.configure(state="normal" if voice_input else "disabled")
        self.continuous_button.configure(state="normal" if voice_input else "disabled")
        self.test_mic_button.configure(
            state="normal" if self.voice_diagnostics.get("microphone_available") else "disabled"
        )
        self.meter_button.configure(
            state="normal"
            if self.voice_diagnostics.get("meter_available") and self.voice_diagnostics.get("microphone_available")
            else "disabled"
        )
        self._refresh_voice_panel()

    def _voice_input_enabled(self) -> bool:
        return self.voice_mode.get() in {"Voice Input", "Full Voice"}

    def _spoken_replies_enabled(self) -> bool:
        return self.voice_mode.get() == "Full Voice" and self.assistant.voice is not None

    def _refresh_microphone_picker(self) -> None:
        options = ["System Default"]
        for option in self.voice_diagnostics.get("device_options", []):
            options.append(f"[{option['index']}] {option['name']}")
        self.microphone_picker.configure(values=options)

        current = self.selected_microphone.get()
        if current not in options:
            self.selected_microphone.set("System Default")
            self.microphone_picker.set("System Default")

    def _selected_device_index(self) -> int | None:
        selected = self.selected_microphone.get()
        if not selected or selected == "System Default":
            return None
        if selected.startswith("[") and "]" in selected:
            index_text = selected[1:selected.index("]")]
            try:
                return int(index_text)
            except ValueError:
                return None
        return None

    def _reconfigure_voice_for_selection(self) -> None:
        if not self.voice_diagnostics.get("microphone_available"):
            self.assistant.configure_voice(enabled=False)
            self._refresh_voice_panel()
            return

        device_index = self._selected_device_index()
        enabled = self.voice_mode.get() != "Text Only"
        configured = self.assistant.configure_voice(enabled=enabled, device_index=device_index)
        if enabled and not configured:
            self.status_text.set("Selected microphone could not be opened. Try another input device.")
        self._refresh_voice_panel()

    def _open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        window = ctk.CTkToplevel(self.root)
        window.title("Jarvis Settings")
        window.geometry("460x420")
        window.resizable(False, False)
        window.configure(fg_color="#0b141b")
        self.settings_window = window

        frame = ctk.CTkFrame(window, fg_color="#12212d", corner_radius=18)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame,
            text="Desktop Preferences",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f8c15c",
        ).pack(anchor="w", padx=18, pady=(18, 10))

        ctk.CTkCheckBox(frame, text="Enable reminder notifications", variable=self.notifications_enabled).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkCheckBox(frame, text="Require wake word for voice commands", variable=self.require_wake_word).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkCheckBox(frame, text="Start in continuous listening mode", variable=self.continuous_listening).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkCheckBox(frame, text="Start minimized in background mode", variable=self.start_minimized).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkCheckBox(frame, text="Use system tray when hidden", variable=self.tray_enabled).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkCheckBox(frame, text="Launch Jarvis on Windows startup", variable=self.launch_on_startup).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkCheckBox(frame, text="Send Close button to background", variable=self.background_on_close).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkCheckBox(frame, text="Show popup reminder alerts", variable=self.popup_notifications).pack(
            anchor="w",
            padx=18,
            pady=8,
        )
        ctk.CTkLabel(
            frame,
            text="Reminder polling interval (seconds)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#d8e5ed",
        ).pack(anchor="w", padx=18, pady=(18, 8))
        ctk.CTkComboBox(
            frame,
            variable=self.reminder_poll_seconds,
            values=["10", "20", "30", "60", "120"],
            button_color="#23404f",
            border_color="#274152",
            fg_color="#0c1720",
            dropdown_fg_color="#12212d",
            dropdown_hover_color="#1d3442",
        ).pack(fill="x", padx=18)

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(24, 18))
        ctk.CTkButton(
            buttons,
            text="Save",
            fg_color="#1e5f74",
            hover_color="#277d97",
            command=self._save_settings,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            buttons,
            text="Close",
            fg_color="#23404f",
            hover_color="#2f5569",
            command=window.destroy,
        ).pack(side="right")

    def _save_settings(self) -> None:
        self.preferences.update(
            {
                "voice_mode": self.voice_mode.get(),
                "notifications_enabled": bool(self.notifications_enabled.get()),
                "popup_notifications": bool(self.popup_notifications.get()),
                "reminder_poll_seconds": int(self.reminder_poll_seconds.get()),
                "require_wake_word": bool(self.require_wake_word.get()),
                "continuous_listening": bool(self.continuous_listening.get()),
                "start_minimized": bool(self.start_minimized.get()),
                "background_on_close": bool(self.background_on_close.get()),
                "tray_enabled": bool(self.tray_enabled.get()),
                "launch_on_startup": bool(self.launch_on_startup.get()),
            }
        )
        self.preferences_store.save(self.preferences)
        startup_status = self._apply_startup_preference()
        self.status_text.set(startup_status or "Settings saved.")
        self._refresh_integrations()
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()

    def _check_due_reminders(self) -> None:
        if self.notifications_enabled.get():
            for reminder in self.assistant.due_reminders():
                notice = f"Reminder due now: {reminder['subject']} ({reminder['scheduled_for']})"
                self._append_history("System", notice, "meta")
                self.status_text.set(notice)
                if self.popup_notifications.get():
                    self._show_notification_popup("Reminder", notice, reminder["id"])
                self.assistant.mark_reminder_notified(reminder["id"])
            self._refresh_reminders()

        interval_ms = max(int(self.reminder_poll_seconds.get()), 5) * 1000
        self.root.after(interval_ms, self._check_due_reminders)

    def _show_notification_popup(self, title: str, message: str, reminder_id: str | None = None) -> None:
        popup = ctk.CTkToplevel(self.root)
        popup.title(title)
        popup.geometry("380x220")
        popup.configure(fg_color="#12212d")
        popup.attributes("-topmost", True)
        ctk.CTkLabel(
            popup,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f8c15c",
        ).pack(anchor="w", padx=18, pady=(18, 8))
        ctk.CTkLabel(
            popup,
            text=message,
            justify="left",
            wraplength=330,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#eef4f7",
        ).pack(anchor="w", padx=18, pady=(0, 14))
        buttons = ctk.CTkFrame(popup, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(
            buttons,
            text="Dismiss",
            width=90,
            fg_color="#23404f",
            hover_color="#2f5569",
            command=popup.destroy,
        ).pack(side="right", padx=(8, 0))
        if reminder_id:
            ctk.CTkButton(
                buttons,
                text="Snooze 15m",
                width=110,
                fg_color="#5b4318",
                hover_color="#7a5a21",
                command=lambda: self._handle_popup_reminder_action(popup, reminder_id, "snooze"),
            ).pack(side="left")
            ctk.CTkButton(
                buttons,
                text="Complete",
                width=100,
                fg_color="#20523a",
                hover_color="#2b6b4c",
                command=lambda: self._handle_popup_reminder_action(popup, reminder_id, "complete"),
            ).pack(side="left", padx=(0, 8))
        popup.after(12000, lambda: popup.winfo_exists() and popup.destroy())

    def _handle_popup_reminder_action(self, popup: ctk.CTkToplevel, reminder_id: str, action: str) -> None:
        if action == "complete":
            response = self.assistant.complete_reminder(reminder_id)
        else:
            response = self.assistant.snooze_reminder(reminder_id, minutes=15)
        self._append_history("Jarvis", response.message, "jarvis")
        self.status_text.set(response.message)
        self._refresh_reminders()
        if popup.winfo_exists():
            popup.destroy()

    def _handle_close_request(self) -> None:
        if self.background_on_close.get():
            self._hide_to_background()
            return
        self._shutdown()

    def _apply_startup_preference(self) -> str | None:
        if not self.startup_manager.is_available():
            return "Startup integration is unavailable on this machine."

        try:
            if self.launch_on_startup.get():
                self.startup_manager.enable(
                    target=self._startup_target(),
                    arguments="-m src.jarvis_ai_assistant.main --minimized",
                    working_directory=str(Path(__file__).resolve().parents[2]),
                )
                return "Settings saved. Jarvis will launch at Windows startup."
            self.startup_manager.disable()
            return "Settings saved. Windows startup launch is disabled."
        except (OSError, subprocess.SubprocessError):
            return "Settings saved, but Windows startup integration could not be updated."

    def _startup_target(self) -> str:
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        return str(pythonw if pythonw.exists() else executable)

    def _hide_to_background(self) -> None:
        if self.tray_enabled.get() and self.tray_controller.start(
            "Jarvis AI Voice Assistant",
            on_restore=lambda: self.root.after(0, self._restore_from_background),
            on_exit=lambda: self.root.after(0, self._shutdown),
        ):
            if self.background_window is not None and self.background_window.winfo_exists():
                self.background_window.destroy()
                self.background_window = None
            self.root.withdraw()
            self.status_text.set("Jarvis is running from the system tray.")
            return

        if self.background_window is not None and self.background_window.winfo_exists():
            self.background_window.lift()
            self.root.withdraw()
            self.status_text.set("Jarvis is running in background mode.")
            return

        self.root.withdraw()
        window = ctk.CTkToplevel(self.root)
        window.title("Jarvis Background")
        window.geometry("320x170")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.configure(fg_color="#0b141b")
        self.background_window = window
        window.protocol("WM_DELETE_WINDOW", self._shutdown)

        frame = ctk.CTkFrame(window, fg_color="#12212d", corner_radius=18)
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            frame,
            text="Jarvis Is Running",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f8c15c",
        ).pack(anchor="w", padx=18, pady=(18, 8))
        ctk.CTkLabel(
            frame,
            text="Voice commands, reminders, and background checks stay active while the main window is hidden.",
            justify="left",
            wraplength=260,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#eef4f7",
        ).pack(anchor="w", padx=18, pady=(0, 12))
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(
            buttons,
            text="Restore",
            fg_color="#1e5f74",
            hover_color="#277d97",
            command=self._restore_from_background,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="Exit",
            fg_color="#5f2a2a",
            hover_color="#7d3939",
            command=self._shutdown,
        ).pack(side="right")
        self.status_text.set("Jarvis is running in background mode.")

    def _restore_from_background(self) -> None:
        self.tray_controller.stop()
        if self.background_window is not None and self.background_window.winfo_exists():
            self.background_window.destroy()
        self.background_window = None
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.status_text.set("Jarvis window restored.")

    def _shutdown(self) -> None:
        self.continuous_listener_running = False
        self.meter_running = False
        self.tray_controller.stop()
        if self.background_window is not None and self.background_window.winfo_exists():
            self.background_window.destroy()
        self.root.destroy()
