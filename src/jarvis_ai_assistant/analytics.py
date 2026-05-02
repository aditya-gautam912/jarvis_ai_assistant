"""Interaction logging and lightweight usage analysis."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import LOGS_DIR
from .models import InteractionRecord


class InteractionAnalytics:
    """Stores interaction history and produces simple aggregate metrics."""

    def __init__(self, csv_path: Path | None = None) -> None:
        self.csv_path = csv_path or LOGS_DIR / "interactions.csv"

    def log(self, record: InteractionRecord) -> None:
        """Append one interaction to the analytics CSV."""
        row = pd.DataFrame([asdict(record)])
        row.to_csv(
            self.csv_path,
            mode="a",
            index=False,
            header=not self.csv_path.exists(),
        )

    def usage_summary(self) -> dict[str, object]:
        """Return a compact summary of assistant usage patterns."""
        if not self.csv_path.exists():
            return {
                "total_commands": 0,
                "average_confidence": 0.0,
                "success_rate": 0.0,
                "top_intents": {},
                "failed_commands": 0,
                "commands_last_24h": 0,
                "top_actions": {},
            }

        frame = pd.read_csv(self.csv_path)
        if not frame.empty:
            success_series = frame["success"].astype(str).str.lower().map({"true": True, "false": False})
            success_series = success_series.fillna(False)
            success_rate = float(success_series.mean())
            failed_commands = int((~success_series).sum())
        else:
            success_rate = 0.0
            failed_commands = 0
        average_confidence = float(np.mean(frame["confidence"])) if not frame.empty else 0.0
        top_intents = frame["intent"].value_counts().head(5).to_dict()
        top_actions = (
            frame["action"].fillna("").replace("", "unspecified").value_counts().head(5).to_dict()
            if "action" in frame and not frame.empty
            else {}
        )
        commands_last_24h = 0
        if "timestamp" in frame and not frame.empty:
            parsed = pd.to_datetime(frame["timestamp"], errors="coerce")
            since = datetime.now() - timedelta(hours=24)
            commands_last_24h = int((parsed >= since).sum())

        return {
            "total_commands": int(len(frame)),
            "average_confidence": round(average_confidence, 3),
            "success_rate": round(success_rate, 3),
            "top_intents": top_intents,
            "failed_commands": failed_commands,
            "commands_last_24h": commands_last_24h,
            "top_actions": top_actions,
        }
