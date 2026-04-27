"""Entry point for the Jarvis assistant."""

from __future__ import annotations

import argparse
import logging

from .assistant import JarvisAssistant
from .gui import JarvisGUI


def configure_logging() -> None:
    """Set a consistent log format for development and production debugging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


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
