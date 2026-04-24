"""Interaction logging and lightweight usage analysis."""

from __future__ import annotations

from dataclasses import asdict
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
            }

        frame = pd.read_csv(self.csv_path)
        success_rate = float(frame["success"].mean()) if not frame.empty else 0.0
        average_confidence = float(np.mean(frame["confidence"])) if not frame.empty else 0.0
        top_intents = frame["intent"].value_counts().head(5).to_dict()

        return {
            "total_commands": int(len(frame)),
            "average_confidence": round(average_confidence, 3),
            "success_rate": round(success_rate, 3),
            "top_intents": top_intents,
        }
