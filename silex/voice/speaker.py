"""
silex/voice/speaker.py — Text-to-speech output.

Provider priority:
  1. OpenAI TTS API (if OPENAI_API_KEY available) — highest quality
  2. pyttsx3 (offline, no API needed) — fallback
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger("silex.voice.speaker")


class VoiceSpeaker:
    def __init__(self):
        self._use_openai = bool(os.getenv("OPENAI_API_KEY"))
        if not self._use_openai:
            try:
                import pyttsx3
            except ImportError as e:
                raise RuntimeError(
                    f"Voice speaker offline dependencies not installed: {e}. "
                    f"Set OPENAI_API_KEY or run: pip install \"kinthic[voice]\""
                )

    def speak(self, text: str) -> None:
        """Speak text aloud. Blocks until finished."""
        if self._use_openai:
            try:
                self._speak_openai(text)
                return
            except Exception as exc:
                log.warning("OpenAI TTS failed, falling back to pyttsx3: %s", exc)
        self._speak_pyttsx3(text)

    def _speak_openai(self, text: str) -> None:
        from openai import OpenAI
        import tempfile
        import subprocess
        
        client = OpenAI()
        response = client.audio.speech.create(model="tts-1", voice="onyx", input=text)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(response.content)
            tmp = f.name
        
        # Play with system default player or command line player
        if os.name == "nt":
            os.startfile(tmp)
        else:
            subprocess.run(["ffplay", "-nodisp", "-autoexit", tmp],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _speak_pyttsx3(self, text: str) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except ImportError:
            log.error("pyttsx3 not installed. Run: pip install 'kinthic[voice]'")
            raise RuntimeError("pyttsx3 not installed. Run: pip install 'kinthic[voice]'")
