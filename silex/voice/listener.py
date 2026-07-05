"""
silex/voice/listener.py — Mic capture + Whisper transcription.

Uses faster-whisper (local, CPU) for transcription.
"""

from __future__ import annotations
import logging

log = logging.getLogger("silex.voice.listener")

SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.01  # RMS below this = silence
SILENCE_DURATION = 1.5  # seconds of silence = end of utterance
MAX_RECORD_SECS = 60  # hard cap


class VoiceListener:
    def __init__(self, model_size: str = "base"):
        """
        model_size: "tiny", "base", "small", "medium", "large-v3"
        tiny/base run on CPU in real-time. larger = more accurate but slower.
        """
        try:
            from faster_whisper import WhisperModel
            import sounddevice as sd
            import numpy as np

            # Instantiate model to verify it's working
            self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
            log.info("Whisper model '%s' loaded", model_size)
        except ImportError as e:
            raise RuntimeError(
                f'Voice listener dependencies not installed: {e}. Run: pip install "kinthic[voice]"'
            )

    def listen(self) -> str:
        """Block until user speaks and stops. Returns transcribed text."""
        import sounddevice as sd
        import numpy as np

        log.info("Listening for speech...")
        frames = []
        silent_frames = 0
        silence_limit = int(SILENCE_DURATION * SAMPLE_RATE / 1024)

        def callback(indata, frame_count, time_info, status):
            nonlocal silent_frames
            rms = np.sqrt(np.mean(indata**2))
            frames.append(indata.copy())
            if rms < SILENCE_THRESHOLD:
                silent_frames += 1
            else:
                silent_frames = 0

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=callback,
        ):
            while True:
                sd.sleep(100)
                total_secs = len(frames) * 1024 / SAMPLE_RATE
                if silent_frames >= silence_limit and total_secs > 0.5:
                    break
                if total_secs >= MAX_RECORD_SECS:
                    break

        if not frames:
            return ""

        audio = np.concatenate(frames, axis=0).flatten()
        segments, _ = self._model.transcribe(audio, language="en")
        text = " ".join(s.text for s in segments).strip()
        log.info("Transcribed: %r", text)
        return text
