"""
silex/voice/session.py — Voice I/O mode orchestrator.

Replaces the text keyboard input loop with:
  listen() → transcribe → cognitive_loop.process() → speak(response)
"""
from __future__ import annotations
import asyncio
import logging
from silex.voice.listener import VoiceListener
from silex.voice.speaker import VoiceSpeaker

log = logging.getLogger("silex.voice.session")


class VoiceSession:
    def __init__(self, cognitive_loop, bridge=None, whisper_model: str = "base"):
        self.loop = cognitive_loop
        self.bridge = bridge
        self._listener = VoiceListener(whisper_model)
        self._speaker = VoiceSpeaker()
        self._active = False

    def start(self):
        self._active = True
        log.info("Voice session started")

    def stop(self):
        self._active = False
        log.info("Voice session stopped")

    async def speak(self, text: str):
        """Speak a response text."""
        if text:
            await asyncio.to_thread(self._speaker.speak, text)
