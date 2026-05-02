"""Entry point for the Jarvis assistant."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime

from .config import LOGS_DIR

from .assistant import JarvisAssistant
from .gui import JarvisGUI


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter for file-based observability logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        obs_event = getattr(record, "obs_event", None)
        if obs_event is not None:
            payload["event"] = obs_event
        obs_payload = getattr(record, "obs_payload", None)
        if obs_payload is not None:
            payload["payload"] = obs_payload
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    """Configure console logging and structured JSON file logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root_logger.addHandler(console_handler)

    json_handler = logging.FileHandler(LOGS_DIR / "jarvis.jsonl", encoding="utf-8")
    json_handler.setLevel(logging.INFO)
    json_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(json_handler)


def run_cli() -> None:
    """Run the original terminal interface."""
    configure_logging()

    try:
        assistant = JarvisAssistant(enable_voice=True)
        assistant.run()
    except OSError:
        print("Voice stack is unavailable. Switching to text mode.")
        assistant = JarvisAssistant(enable_voice=False)
        while True:
            command = input("You: ").strip()
            if not command:
                continue
            response = assistant.handle_command(command)
            print(f"Jarvis: {response.message}")
            if response.action == "exit":
                break


def main() -> None:
    """Start the assistant GUI by default, with an optional CLI mode."""
    parser = argparse.ArgumentParser(description="Jarvis AI assistant")
    parser.add_argument("--cli", action="store_true", help="Run the terminal interface instead of the GUI.")
    parser.add_argument("--minimized", action="store_true", help="Start the GUI hidden in background mode.")
    args = parser.parse_args()

    configure_logging()

    if args.cli:
        run_cli()
        return

    JarvisGUI(start_minimized=args.minimized).run()


if __name__ == "__main__":
    main()
