"""Intent classification and entity extraction."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score

from .config import DATA_DIR
from .models import IntentResult


class NLPEngine:
    """Classifies user text into intents with a lightweight ML pipeline."""

    def __init__(self, dataset_path: Path | None = None) -> None:
        self.dataset_path = dataset_path or DATA_DIR / "intents.json"
        self.pipeline: Pipeline = Pipeline(
            steps=[
                (
                    "tfidf",
                    TfidfVectorizer(
                        lowercase=True,
                        ngram_range=(1, 2),
                        strip_accents="unicode",
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                        solver="lbfgs",
                    ),
                ),
            ]
        )
        self._train()

    def _train(self) -> None:
        """Train the classifier from the bundled intent dataset."""
        training_data = self._load_training_data()

        texts: list[str] = []
        labels: list[str] = []
        for label, examples in training_data.items():
            texts.extend(examples)
            labels.extend([label] * len(examples))

        self.pipeline.fit(texts, labels)

    def evaluate(self, folds: int = 3) -> float:
        """Estimate classifier accuracy with cross-validation."""
        training_data = self._load_training_data()
        texts: list[str] = []
        labels: list[str] = []
        for label, examples in training_data.items():
            texts.extend(examples)
            labels.extend([label] * len(examples))

        scores = cross_val_score(self.pipeline, texts, labels, cv=folds)
        return float(np.mean(scores))

    def predict(self, text: str) -> IntentResult:
        """Predict the intent label and extract basic entities."""
        normalized_text = text.strip().lower()
        probabilities = self.pipeline.predict_proba([normalized_text])[0]
        classes = self.pipeline.classes_
        best_index = int(probabilities.argmax())
        intent = str(classes[best_index])
        confidence = float(probabilities[best_index])

        return IntentResult(
            intent=intent,
            confidence=confidence,
            normalized_text=normalized_text,
            entities=self.extract_entities(normalized_text, intent),
        )

    def extract_entities(self, text: str, intent: str) -> dict[str, str]:
        """Parse lightweight entities from commands without heavyweight NLP."""
        entities: dict[str, str] = {}

        if intent == "open_application":
            match = re.search(r"(?:open|launch|start|run)\s+(.+)", text)
            if match:
                entities["application"] = match.group(1).strip()

        if intent == "weather_query":
            match = re.search(r"(?:in|for)\s+([a-zA-Z\s]+)$", text)
            if match:
                entities["city"] = match.group(1).strip()

        if intent == "news_query":
            match = re.search(r"(?:about|on|for)\s+([a-zA-Z\s]+)$", text)
            if match:
                entities["topic"] = match.group(1).strip()

        if intent in {"set_reminder", "schedule_calendar"}:
            time_match = re.search(
                r"(today|tomorrow|next\s+\w+|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
                text,
            )
            if time_match:
                entities["when"] = time_match.group(1).strip()
            entities["subject"] = (
                text.replace("remind me to", "")
                .replace("set a reminder to", "")
                .replace("set reminder to", "")
                .replace("schedule", "")
                .replace("create a calendar event for", "")
                .replace("add appointment", "")
                .strip()
            )

        if intent in {"general_query", "file_operation"}:
            entities["query"] = text

        return entities

    def _load_training_data(self) -> dict[str, list[str]]:
        with self.dataset_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
