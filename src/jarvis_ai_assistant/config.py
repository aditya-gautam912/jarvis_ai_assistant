"""Central configuration for the assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional in bare environments
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR.mkdir(exist_ok=True)
STORAGE_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True, slots=True)
class Settings:
    """Application settings loaded from environment variables."""

    weather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    google_credentials_file: str = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "credentials.json")
    google_token_file: str = os.getenv("GOOGLE_CALENDAR_TOKEN", "token.json")
    default_city: str = os.getenv("DEFAULT_CITY", "New Delhi")
    wake_word: str = os.getenv("WAKE_WORD", "jarvis").strip().lower()
    confidence_threshold: float = float(os.getenv("COMMAND_CONFIDENCE_THRESHOLD", "0.55"))
    listen_timeout: int = int(os.getenv("LISTEN_TIMEOUT", "5"))
    phrase_time_limit: int = int(os.getenv("PHRASE_TIME_LIMIT", "10"))


SETTINGS = Settings()


def integration_status() -> dict[str, bool]:
    """Report whether optional integrations appear configured."""
    credentials_path = BASE_DIR / SETTINGS.google_credentials_file
    token_path = BASE_DIR / SETTINGS.google_token_file
    return {
        "weather_api": bool(SETTINGS.weather_api_key),
        "news_api": bool(SETTINGS.news_api_key),
        "google_calendar_credentials": credentials_path.exists(),
        "google_calendar_token": token_path.exists(),
    }
