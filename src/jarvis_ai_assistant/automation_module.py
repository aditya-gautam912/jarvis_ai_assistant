"""System automation primitives."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from .models import AssistantResponse


class AutomationModule:
    """Executes local automation actions with simple allowlisted mappings."""

    APP_ALIASES = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "edge browser": "msedge.exe",
        "edge": "msedge.exe",
        "vscode": "code",
        "visual studio code": "code",
        "terminal": "wt.exe",
        "command prompt": "cmd.exe",
        "file explorer": "explorer.exe",
    }

    def open_application(self, application: str) -> AssistantResponse:
        """Open a local application or fallback to a web search."""
        app_name = application.strip().lower()
        target = self.APP_ALIASES.get(app_name, app_name)
        try:
            subprocess.Popen(target)  # noqa: S603
            return AssistantResponse(
                message=f"Opening {application}.",
                action="open_application",
                payload={"application": application},
            )
        except OSError:
            webbrowser.open(f"https://www.google.com/search?q={application}")
            return AssistantResponse(
                message=f"I could not launch {application} directly, so I opened a web search instead.",
                success=False,
                action="open_application_fallback",
                payload={"application": application},
            )

    def search_web(self, query: str) -> AssistantResponse:
        """Open a browser search for the user's query."""
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return AssistantResponse(
            message=f"Searching the web for {query}.",
            action="search_web",
            payload={"query": query},
        )

    def handle_file_operation(self, query: str) -> AssistantResponse:
        """Process simple file and folder commands."""
        normalized = query.lower()

        if "downloads" in normalized:
            return self._open_path(Path.home() / "Downloads", "downloads folder")
        if "documents" in normalized:
            return self._open_path(Path.home() / "Documents", "documents folder")
        if "desktop" in normalized:
            return self._open_path(Path.home() / "Desktop", "desktop folder")
        if "pictures" in normalized:
            return self._open_path(Path.home() / "Pictures", "pictures folder")
        if "create a file" in normalized or "new text file" in normalized:
            file_path = Path.home() / "Desktop" / "jarvis_note.txt"
            file_path.write_text("Created by Jarvis.\n", encoding="utf-8")
            return AssistantResponse(
                message=f"I created {file_path.name} on your desktop.",
                action="create_file",
                payload={"path": str(file_path)},
            )
        if "create a folder" in normalized:
            folder_path = Path.home() / "Desktop" / "JarvisFolder"
            folder_path.mkdir(exist_ok=True)
            return AssistantResponse(
                message="I created a new folder on your desktop.",
                action="create_folder",
                payload={"path": str(folder_path)},
            )

        return AssistantResponse(
            message="I did not find a safe local file action, so I will search the web instead.",
            success=False,
            action="file_operation_fallback",
            payload={"query": query},
        )

    @staticmethod
    def _open_path(path: Path, label: str) -> AssistantResponse:
        os.startfile(path)  # type: ignore[attr-defined]
        return AssistantResponse(
            message=f"Opening your {label}.",
            action="open_path",
            payload={"path": str(path)},
        )
