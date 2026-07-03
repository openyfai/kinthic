import pytest
from unittest.mock import MagicMock, patch
import sys

# Create mocks for external modules to prevent ImportError on machines without optional voice packages
mock_whisper = MagicMock()
mock_sounddevice = MagicMock()
mock_pyttsx3 = MagicMock()

sys.modules["faster_whisper"] = mock_whisper
sys.modules["sounddevice"] = mock_sounddevice
sys.modules["pyttsx3"] = mock_pyttsx3

try:
    import numpy
except ImportError:
    mock_numpy = MagicMock()
    sys.modules["numpy"] = mock_numpy

from silex.voice.listener import VoiceListener
from silex.voice.speaker import VoiceSpeaker
from silex.voice.session import VoiceSession


def test_voice_listener_init():
    with patch("faster_whisper.WhisperModel") as mock_whisper_class:
        # Mock class instance
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        listener = VoiceListener(model_size="base")
        assert listener._model == mock_model
        mock_whisper_class.assert_called_once_with("base", device="cpu", compute_type="int8")


def test_voice_listener_listen():
    with patch("faster_whisper.WhisperModel") as mock_whisper_class:
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        # Setup transcription mock
        mock_segment = MagicMock()
        mock_segment.text = "Hello world"
        mock_model.transcribe.return_value = ([mock_segment], None)
        
        listener = VoiceListener(model_size="base")
        
        # Mock sounddevice input stream
        import numpy as np
        with patch("sounddevice.InputStream") as mock_input_stream:
            callback_func = None
            def mock_init(*args, **kwargs):
                nonlocal callback_func
                callback_func = kwargs.get("callback")
                return MagicMock()
            mock_input_stream.side_effect = mock_init
            
            def mock_sleep(ms):
                if callback_func:
                    # call callback multiple times with silent data to trigger break
                    for _ in range(20):
                        callback_func(np.zeros((1024, 1)), 1024, None, None)
            
            with patch("sounddevice.sleep", side_effect=mock_sleep):
                text = listener.listen()
                assert text == "Hello world"


def test_voice_speaker_init():
    # If OPENAI_API_KEY is not present, pyttsx3 is checked
    with patch("os.getenv", return_value=None):
        with patch("pyttsx3.init") as mock_pyttsx3_init:
            speaker = VoiceSpeaker()
            assert speaker._use_openai is False


def test_voice_speaker_speak_openai():
    # Mock OpenAI API key to use OpenAI TTS
    with patch("os.getenv", return_value="fake_key"):
        with patch("openai.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.audio.speech.create.return_value = MagicMock(content=b"audio data")
            
            speaker = VoiceSpeaker()
            assert speaker._use_openai is True
            
            with patch("tempfile.NamedTemporaryFile") as mock_tempfile, \
                 patch("os.startfile") as mock_startfile:
                
                # Mock context manager
                mock_file = MagicMock()
                mock_file.name = "temp.mp3"
                mock_tempfile.return_value.__enter__.return_value = mock_file
                
                speaker.speak("Hello there")
                mock_client.audio.speech.create.assert_called_once_with(
                    model="tts-1", voice="onyx", input="Hello there"
                )
                mock_startfile.assert_called_once_with("temp.mp3")


def test_voice_speaker_speak_offline():
    # Fallback to pyttsx3
    with patch("os.getenv", return_value=None):
        with patch("pyttsx3.init") as mock_pyttsx3_init:
            mock_engine = MagicMock()
            mock_pyttsx3_init.return_value = mock_engine
            
            speaker = VoiceSpeaker()
            speaker.speak("Fallback test")
            
            mock_engine.say.assert_called_once_with("Fallback test")
            mock_engine.runAndWait.assert_called_once()


@pytest.mark.asyncio
async def test_voice_session_speak():
    cognitive_loop = MagicMock()
    bridge = MagicMock()
    
    with patch("silex.voice.session.VoiceListener"), \
         patch("silex.voice.session.VoiceSpeaker") as mock_speaker_class:
        
        mock_speaker = MagicMock()
        mock_speaker_class.return_value = mock_speaker
        
        session = VoiceSession(cognitive_loop, bridge=bridge)
        session.start()
        assert session._active is True
        
        await session.speak("Speaking text")
        mock_speaker.speak.assert_called_once_with("Speaking text")
