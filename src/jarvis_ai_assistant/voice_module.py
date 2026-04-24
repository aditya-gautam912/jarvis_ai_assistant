"""Speech input and output helpers."""

from __future__ import annotations

import logging
import math
import struct
from typing import Any

import pyttsx3
import speech_recognition as sr
try:
    import pyaudio
except ModuleNotFoundError:  # pragma: no cover - optional at runtime
    pyaudio = None

from .config import SETTINGS

LOGGER = logging.getLogger(__name__)


class VoiceModule:
    """Wraps speech recognition and text-to-speech behavior."""

    def __init__(self, device_index: int | None = None) -> None:
        diagnostics = self.describe_environment()
        if not diagnostics["microphone_available"]:
            raise OSError(diagnostics["error"] or "No microphone devices were detected.")

        self.recognizer = sr.Recognizer()
        self.device_index = device_index
        self.microphone = sr.Microphone(device_index=device_index)
        self.tts_engine = pyttsx3.init()
        self._configure_tts()

    def _configure_tts(self) -> None:
        """Apply stable TTS defaults for desktop usage."""
        self.tts_engine.setProperty("rate", 180)
        self.tts_engine.setProperty("volume", 0.9)

    def speak(self, text: str) -> None:
        """Speak a response and mirror it to stdout for debugging."""
        print(f"Jarvis: {text}")
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

    def listen(self) -> str | None:
        """Capture and transcribe one spoken utterance."""
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
            print("Listening...")
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=SETTINGS.listen_timeout,
                    phrase_time_limit=SETTINGS.phrase_time_limit,
                )
            except sr.WaitTimeoutError:
                LOGGER.info("No speech detected before timeout.")
                return None

        try:
            text = self.recognizer.recognize_google(audio)
            print(f"You: {text}")
            return text
        except sr.UnknownValueError:
            LOGGER.warning("Speech recognition could not understand audio.")
            return None
        except sr.RequestError as exc:
            LOGGER.exception("Speech recognition request failed: %s", exc)
            return None

    @classmethod
    def describe_environment(cls) -> dict[str, Any]:
        """Report microphone and speech-stack availability for UI diagnostics."""
        diagnostics: dict[str, Any] = {
            "microphone_available": False,
            "device_count": 0,
            "devices": [],
            "device_options": [],
            "tts_available": False,
            "meter_available": pyaudio is not None,
            "error": "",
        }

        try:
            devices = sr.Microphone.list_microphone_names()
            diagnostics["devices"] = devices
            diagnostics["device_count"] = len(devices)
            diagnostics["device_options"] = [
                {"index": index, "name": name}
                for index, name in enumerate(devices)
            ]
            diagnostics["microphone_available"] = bool(devices)
            if not devices:
                diagnostics["error"] = "No microphone input devices were detected."
        except Exception as exc:
            diagnostics["error"] = f"Microphone detection failed: {exc}"

        try:
            engine = pyttsx3.init()
            diagnostics["tts_available"] = True
            engine.stop()
        except Exception as exc:
            diagnostics["tts_available"] = False
            if not diagnostics["error"]:
                diagnostics["error"] = f"Text-to-speech initialization failed: {exc}"

        return diagnostics


class AudioLevelMonitor:
    """Streams microphone audio and returns normalized input levels."""

    def __init__(
        self,
        device_index: int | None = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
    ) -> None:
        if pyaudio is None:
            raise OSError("PyAudio is not installed, so the live microphone meter is unavailable.")

        self.device_index = device_index
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self._audio = pyaudio.PyAudio()
        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=chunk_size,
        )

    def read_level(self) -> float:
        """Read one chunk and return a 0..1 normalized RMS level."""
        data = self._stream.read(self.chunk_size, exception_on_overflow=False)
        samples = struct.unpack("<" + "h" * (len(data) // 2), data)
        if not samples:
            return 0.0

        mean_square = sum(sample * sample for sample in samples) / len(samples)
        rms = math.sqrt(mean_square)
        return min(rms / 32768.0, 1.0)

    def close(self) -> None:
        """Release the audio stream cleanly."""
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        finally:
            self._audio.terminate()
