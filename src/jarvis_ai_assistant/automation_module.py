"""System automation primitives."""

from __future__ import annotations

import os
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

import requests

try:
    from yt_dlp import YoutubeDL
except ModuleNotFoundError:  # pragma: no cover - optional until installed
    YoutubeDL = None

from .models import AssistantResponse


class AutomationModule:
    """Executes local automation actions with simple allowlisted mappings."""

    SEARCH_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        )
    }

    APP_ALIASES = {
        "notepad": "notepad.exe",
        "notebook": "notepad.exe",
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
    UNSAFE_INPUT_PATTERN = re.compile(
        r"""[;&|`$<>]|(?:\b(?:powershell|start-process|cmd(?:\.exe)?\s*/c|bash|sh|rm|del|rmdir|format)\b)""",
        flags=re.IGNORECASE,
    )

    def open_application(self, application: str) -> AssistantResponse:
        """Open a local application or fallback to a web search."""
        requested = application.strip()
        if not requested:
            return AssistantResponse(
                message="Please specify an application to open.",
                success=False,
                action="open_application_invalid",
            )
        if self._contains_unsafe_input(requested):
            return AssistantResponse(
                message="I blocked that app request because it looked unsafe.",
                success=False,
                action="security_blocked",
                payload={"application": requested},
            )

        app_name = requested.lower()
        target = self.APP_ALIASES.get(app_name)
        if target is None:
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(requested)}")
            return AssistantResponse(
                message=(
                    f"I only launch allowlisted local apps for safety, so I opened a web search for {requested}."
                ),
                success=False,
                action="open_application_fallback",
                payload={"application": requested},
            )

        try:
            subprocess.Popen(target)  # noqa: S603
            return AssistantResponse(
                message=f"Opening {requested}.",
                action="open_application",
                payload={"application": requested},
            )
        except OSError:
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(requested)}")
            return AssistantResponse(
                message=f"I could not launch {requested} directly, so I opened a web search instead.",
                success=False,
                action="open_application_fallback",
                payload={"application": requested},
            )

    def search_web(self, query: str) -> AssistantResponse:
        """Open a browser search for the user's query."""
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
        return AssistantResponse(
            message=f"Searching the web for {query}.",
            action="search_web",
            payload={"query": query},
        )

    def play_music(self, song_query: str, platform: str = "youtube") -> AssistantResponse:
        """Open a music search on the requested platform."""
        normalized_platform = platform.strip().lower()
        query = song_query.strip() or "music"

        if normalized_platform == "spotify":
            url = f"https://open.spotify.com/search/{query.replace(' ', '%20')}"
            message = f"Playing {query} on Spotify."
            action = "play_music_spotify"
        else:
            resolved_url = self._resolve_youtube_video_url(query)
            url = self._with_youtube_autoplay(resolved_url) if resolved_url else (
                f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            )
            if "watch?v=" in url:
                message = f"Playing {query} on YouTube."
                action = "play_music_youtube"
            else:
                message = f"I could not resolve the exact YouTube video, so I opened search results for {query}."
                action = "play_music_youtube_search"

        webbrowser.open(url)
        return AssistantResponse(
            message=message,
            action=action,
            payload={"song_query": query, "platform": normalized_platform, "url": url},
        )

    @staticmethod
    def _resolve_youtube_video_url(query: str) -> str | None:
        """Resolve the top YouTube result to a direct watch URL."""
        resolved = AutomationModule._resolve_youtube_via_ytdlp(query)
        if resolved:
            return resolved
        return AutomationModule._resolve_youtube_via_html(query)

    @staticmethod
    def _with_youtube_autoplay(url: str) -> str:
        """Request autoplay when opening a resolved YouTube watch URL."""
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}autoplay=1"

    @staticmethod
    def _resolve_youtube_via_ytdlp(query: str) -> str | None:
        if YoutubeDL is None:
            return None

        options = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
        }
        try:
            with YoutubeDL(options) as ydl:
                result = ydl.extract_info(f"ytsearch1:{query}", download=False)
        except Exception:
            return None

        entries = result.get("entries") if isinstance(result, dict) else None
        if not entries:
            return None

        first = entries[0]
        video_id = first.get("id")
        if not video_id:
            return None
        return f"https://www.youtube.com/watch?v={video_id}"

    @staticmethod
    def _resolve_youtube_via_html(query: str) -> str | None:
        try:
            response = requests.get(
                "https://www.youtube.com/results",
                params={"search_query": query},
                headers=AutomationModule.SEARCH_HEADERS,
                timeout=10,
            )
            response.raise_for_status()
        except Exception:
            return None

        match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', response.text)
        if not match:
            match = re.search(r"/watch\?v=([a-zA-Z0-9_-]{11})", response.text)
        if not match:
            return None
        return f"https://www.youtube.com/watch?v={match.group(1)}"

    def handle_file_operation(self, query: str) -> AssistantResponse:
        """Process simple file and folder commands."""
        if self._contains_unsafe_input(query):
            return AssistantResponse(
                message="I blocked that file operation because it looked unsafe.",
                success=False,
                action="security_blocked",
                payload={"query": query},
            )

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

    @classmethod
    def _contains_unsafe_input(cls, text: str) -> bool:
        return bool(cls.UNSAFE_INPUT_PATTERN.search(text))
