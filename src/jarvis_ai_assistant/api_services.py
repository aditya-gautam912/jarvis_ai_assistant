"""External API integrations for weather, news, and Google Calendar."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import dateparser
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import BASE_DIR, SETTINGS


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class APIServiceError(RuntimeError):
    """Raised when a remote service fails or is misconfigured."""


class APIService:
    """Thin wrapper over the assistant's third-party services."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Jarvis-AI-Assistant/1.0"})

    def get_weather(self, city: str | None = None) -> dict[str, Any]:
        """Fetch current weather from OpenWeatherMap."""
        if not SETTINGS.weather_api_key:
            raise APIServiceError("OpenWeatherMap API key is not configured.")

        query_city = city or SETTINGS.default_city
        response = self.session.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "q": query_city,
                "appid": SETTINGS.weather_api_key,
                "units": "metric",
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()

        return {
            "city": payload["name"],
            "temperature": payload["main"]["temp"],
            "description": payload["weather"][0]["description"],
            "humidity": payload["main"]["humidity"],
            "wind_speed": payload["wind"]["speed"],
        }

    def get_news(self, topic: str | None = None, limit: int = 5) -> list[dict[str, str]]:
        """Fetch top headlines from News API."""
        if not SETTINGS.news_api_key:
            raise APIServiceError("News API key is not configured.")

        params = {
            "apiKey": SETTINGS.news_api_key,
            "pageSize": limit,
            "language": "en",
        }
        if topic:
            params["q"] = topic
            endpoint = "https://newsapi.org/v2/everything"
        else:
            params["country"] = "us"
            endpoint = "https://newsapi.org/v2/top-headlines"

        response = self.session.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()

        return [
            {
                "title": article["title"],
                "source": article["source"]["name"],
                "url": article["url"],
            }
            for article in payload.get("articles", [])[:limit]
        ]

    def create_calendar_event(self, subject: str, when_text: str | None) -> dict[str, str]:
        """Create a one-hour Google Calendar event based on natural language time."""
        service = self._build_calendar_service()
        start_time = self._parse_datetime(when_text)
        end_time = start_time + timedelta(hours=1)

        event_body = {
            "summary": subject or "Jarvis reminder",
            "start": {"dateTime": start_time.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "Asia/Kolkata"},
        }

        created = (
            service.events()
            .insert(calendarId="primary", body=event_body)
            .execute()
        )

        return {
            "summary": created["summary"],
            "start": created["start"]["dateTime"],
            "htmlLink": created["htmlLink"],
        }

    def _build_calendar_service(self):
        token_path = BASE_DIR / SETTINGS.google_token_file
        credentials_path = BASE_DIR / SETTINGS.google_credentials_file
        creds: Credentials | None = None

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        elif not creds or not creds.valid:
            if not Path(credentials_path).exists():
                raise APIServiceError("Google Calendar credentials file was not found.")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("calendar", "v3", credentials=creds)

    @staticmethod
    def _parse_datetime(when_text: str | None) -> datetime:
        if when_text:
            parsed = dateparser.parse(
                when_text,
                settings={"PREFER_DATES_FROM": "future"},
            )
            if parsed:
                return parsed
        return datetime.now() + timedelta(minutes=30)
