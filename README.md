# Jarvis AI Voice Assistant

Production-oriented Python voice assistant with a `CustomTkinter` desktop GUI, modular speech I/O, NLP intent classification, API integrations, persistent reminders, in-app notifications, system automation, and usage analytics.

## Features

- Speech-to-text with `SpeechRecognition`
- Text-to-speech with `pyttsx3`
- Desktop GUI built with `CustomTkinter`
- Intent classification with scikit-learn
- Weather, news, and Google Calendar integrations
- SQLite-backed reminder storage with upcoming-task dashboard
- In-app settings and due-reminder popup notifications
- System tray mode and Windows startup integration
- System automation for applications, files, and web search
- Command analytics with pandas and NumPy
- SQLite-backed command memory for recent-history recall
- Graceful fallback handling for low-confidence or unsupported commands
- Local math calculation support

## Project Structure

```text
jarvis_ai_assistant/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   └── intents.json
└── src/
    └── jarvis_ai_assistant/
        ├── __init__.py
        ├── analytics.py
        ├── api_services.py
        ├── assistant.py
        ├── automation_module.py
        ├── calculator.py
        ├── config.py
        ├── desktop_integration.py
        ├── gui.py
        ├── main.py
        ├── memory_store.py
        ├── models.py
        ├── nlp_engine.py
        ├── preferences_store.py
        ├── reminder_store.py
        └── voice_module.py
```

## Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and add your API keys.
4. Run the assistant GUI:

```bash
python -m src.jarvis_ai_assistant.main
```

5. Optional: start hidden in background mode:

```bash
python -m src.jarvis_ai_assistant.main --minimized
```

6. Optional: run the terminal version instead:

```bash
python -m src.jarvis_ai_assistant.main --cli
```

7. Optional: build a Windows executable:

```powershell
.\scripts\build_exe.ps1 -Clean
```

## Environment Variables

- `OPENWEATHER_API_KEY`
- `NEWS_API_KEY`
- `GOOGLE_CALENDAR_CREDENTIALS`
- `GOOGLE_CALENDAR_TOKEN`
- `DEFAULT_CITY`
- `WAKE_WORD`
- `COMMAND_CONFIDENCE_THRESHOLD`
- `LISTEN_TIMEOUT`
- `PHRASE_TIME_LIMIT`

## How It Works

1. The Tkinter GUI accepts typed commands or triggers one-shot voice capture.
2. The voice module converts speech to text when microphone support is available.
3. The NLP engine classifies the text into an intent using a TF-IDF + Logistic Regression pipeline.
4. The assistant routes the intent to the correct handler.
5. API and automation modules execute the action.
6. Reminders are persisted in local SQLite storage, surfaced in the GUI dashboard, and promoted to popup notifications when due.
7. GUI preferences such as notification behavior and reminder polling are stored locally.
8. Analytics logs each interaction for later review and surfaces a usage summary in the GUI.

## Example Commands

- "Open Notepad"
- "What is the weather in Delhi"
- "Tell me the latest technology news"
- "Set a reminder to call John at 6 PM"
- "Schedule a meeting tomorrow at 3 PM"
- "Who is Ada Lovelace"

## Best Practices

- Keep training examples balanced across intents.
- Retrain the classifier when adding new skills.
- Use confidence thresholds to avoid over-triggering bad actions.
- Protect API secrets with environment variables, never hardcode them.
- Prefer explicit allowlists for executable applications in production.
- Use the built-in confirmation flow for commands that create files/folders or calendar events.

## Future Enhancements

- Replace bag-of-words classification with transformer embeddings.
- Add speaker verification and wake-word detection.
- Add PostgreSQL support for server-backed reminder sync.
- Add offline ASR with Vosk or Whisper.
- Add a plugin system for domain-specific skills.
- Expose metrics through Prometheus or structured logging.
