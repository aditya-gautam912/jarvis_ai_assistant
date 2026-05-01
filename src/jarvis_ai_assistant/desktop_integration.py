"""Windows desktop integration helpers for tray mode and startup shortcuts."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
except ModuleNotFoundError:  # pragma: no cover - optional desktop dependency
    pystray = None
    Image = None
    ImageDraw = None


class StartupManager:
    """Creates or removes a startup shortcut for Jarvis on Windows."""

    def __init__(self, shortcut_name: str = "Jarvis AI Assistant.lnk") -> None:
        self.shortcut_name = shortcut_name

    def is_available(self) -> bool:
        return self._startup_dir() is not None

    def is_enabled(self) -> bool:
        shortcut = self._shortcut_path()
        return shortcut is not None and shortcut.exists()

    def enable(self, target: str, arguments: str = "", working_directory: str | None = None) -> None:
        shortcut = self._shortcut_path(required=True)
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        working_dir = working_directory or str(Path(target).resolve().parent)
        command = (
            "$WshShell = New-Object -ComObject WScript.Shell; "
            f"$Shortcut = $WshShell.CreateShortcut('{shortcut.as_posix()}'); "
            f"$Shortcut.TargetPath = '{target}'; "
            f"$Shortcut.Arguments = '{arguments}'; "
            f"$Shortcut.WorkingDirectory = '{Path(working_dir).resolve().as_posix()}'; "
            "$Shortcut.IconLocation = $Shortcut.TargetPath; "
            "$Shortcut.Save()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
        )

    def disable(self) -> None:
        shortcut = self._shortcut_path()
        if shortcut is not None and shortcut.exists():
            shortcut.unlink()

    def _shortcut_path(self, required: bool = False) -> Path | None:
        startup_dir = self._startup_dir()
        if startup_dir is None:
            if required:
                raise OSError("Windows startup folder is unavailable on this machine.")
            return None
        return startup_dir / self.shortcut_name

    @staticmethod
    def _startup_dir() -> Path | None:
        appdata = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return appdata if appdata.parent.exists() else None


class TrayController:
    """Owns a system tray icon when pystray is available."""

    def __init__(self) -> None:
        self._icon = None
        self._thread: threading.Thread | None = None

    @staticmethod
    def is_available() -> bool:
        return pystray is not None and Image is not None and ImageDraw is not None

    def is_running(self) -> bool:
        return self._icon is not None

    def start(self, title: str, on_restore, on_exit) -> bool:
        if not self.is_available():
            return False
        if self._icon is not None:
            return True

        menu = pystray.Menu(
            pystray.MenuItem("Restore", lambda icon, item: on_restore()),
            pystray.MenuItem("Exit", lambda icon, item: on_exit()),
        )
        self._icon = pystray.Icon("jarvis_ai_assistant", self._build_icon(), title, menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._icon is None:
            return
        self._icon.stop()
        self._icon = None
        self._thread = None

    @staticmethod
    def _build_icon():
        image = Image.new("RGB", (64, 64), "#12212d")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill="#1e5f74", outline="#f8c15c", width=3)
        draw.text((19, 14), "J", fill="#f8c15c")
        return image
