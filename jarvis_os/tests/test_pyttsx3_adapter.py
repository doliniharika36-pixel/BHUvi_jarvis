import unittest
from unittest.mock import MagicMock, patch

from jarvis_os.core.voice.exceptions import SpeechSynthesisException
from jarvis_os.infrastructure.voice.pyttsx3_adapter import Pyttsx3Adapter


class MockVoice:
    """Mock helper for pyttsx3 voice elements."""
    def __init__(self, voice_id: str) -> None:
        self.id = voice_id


class TestPyttsx3Adapter(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_engine = MagicMock()
        
        # Setup mock voices
        self.voices = [MockVoice("voice-1"), MockVoice("voice-2")]
        self.mock_engine.getProperty.side_effect = lambda prop: self.voices if prop == "voices" else None

        self.adapter = Pyttsx3Adapter(engine=self.mock_engine)

    def test_init_defaults(self) -> None:
        adapter = Pyttsx3Adapter()
        self.assertIsNone(adapter._engine)

    def test_lazy_initialization_success(self) -> None:
        adapter = Pyttsx3Adapter()
        mock_pyttsx3_engine = MagicMock()
        
        with patch("pyttsx3.init") as mock_init:
            mock_init.return_value = mock_pyttsx3_engine
            
            engine = adapter._get_engine()
            
            mock_init.assert_called_once()
            self.assertEqual(engine, mock_pyttsx3_engine)
            self.assertEqual(adapter._engine, mock_pyttsx3_engine)

    def test_lazy_initialization_failure_raises_exception(self) -> None:
        adapter = Pyttsx3Adapter()
        with patch("pyttsx3.init", side_effect=RuntimeError("DirectSound error")):
            with self.assertRaises(SpeechSynthesisException) as ctx:
                adapter._get_engine()
            self.assertIn("Failed to initialize pyttsx3 engine", str(ctx.exception))

    def test_speak_success(self) -> None:
        self.adapter.speak("Hello Jarvis")
        
        self.mock_engine.say.assert_called_once_with("Hello Jarvis")
        self.mock_engine.runAndWait.assert_called_once()

    def test_speak_empty_text_is_noop(self) -> None:
        self.adapter.speak("")
        self.adapter.speak(None)
        
        self.mock_engine.say.assert_not_called()
        self.mock_engine.runAndWait.assert_not_called()

    def test_speak_failure_raises_exception(self) -> None:
        self.mock_engine.say.side_effect = RuntimeError("Audio device lost")
        
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.speak("Fail me")
        self.assertIn("Failed to synthesize speech using pyttsx3", str(ctx.exception))

    def test_stop_success(self) -> None:
        self.adapter.stop()
        self.mock_engine.stop.assert_called_once()

    def test_stop_failure_raises_exception(self) -> None:
        self.mock_engine.stop.side_effect = RuntimeError("Could not stop")
        
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.stop()
        self.assertIn("Failed to stop pyttsx3 speech playback", str(ctx.exception))

    def test_set_voice_success(self) -> None:
        self.adapter.set_voice("voice-2")
        self.mock_engine.setProperty.assert_called_once_with("voice", "voice-2")

    def test_set_voice_not_found_raises_exception(self) -> None:
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.set_voice("nonexistent-voice")
        self.assertIn("not found", str(ctx.exception))
        self.mock_engine.setProperty.assert_not_called()

    def test_set_voice_empty_raises_exception(self) -> None:
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.set_voice("")
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_set_voice_generic_failure_raises_exception(self) -> None:
        self.mock_engine.setProperty.side_effect = RuntimeError("Invalid value")
        
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.set_voice("voice-1")
        self.assertIn("Failed to configure pyttsx3 voice", str(ctx.exception))

    def test_set_rate_success(self) -> None:
        self.adapter.set_rate(180)
        self.mock_engine.setProperty.assert_called_once_with("rate", 180)

    def test_set_rate_invalid_values_raises_exception(self) -> None:
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.set_rate(0)
        self.assertIn("must be a positive integer", str(ctx.exception))
        
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.set_rate(-10)
        self.assertIn("must be a positive integer", str(ctx.exception))
        
        self.mock_engine.setProperty.assert_not_called()

    def test_set_rate_generic_failure_raises_exception(self) -> None:
        self.mock_engine.setProperty.side_effect = RuntimeError("Property unsupported")
        
        with self.assertRaises(SpeechSynthesisException) as ctx:
            self.adapter.set_rate(150)
        self.assertIn("Failed to configure pyttsx3 speech rate", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
