import unittest

from jarvis_os.core.voice.exceptions import SpeechRecognitionException
from jarvis_os.core.voice.models import SpeechResult
from jarvis_os.core.voice.speech_to_text import SpeechToText


class ConcreteSTT(SpeechToText):
    def __init__(self):
        self.listening = False

    def start_listening(self) -> None:
        self.listening = True

    def stop_listening(self) -> None:
        self.listening = False

    def transcribe(self, audio_data) -> SpeechResult:
        if audio_data == b"invalid":
            raise SpeechRecognitionException("Invalid audio signal")
        return SpeechResult(text="Mocked Text", confidence=0.95)


class TestSpeechToText(unittest.TestCase):
    def test_cannot_instantiate_abstract_class(self):
        with self.assertRaises(TypeError):
            SpeechToText()  # type: ignore

    def test_concrete_implementation_lifecycle(self):
        stt = ConcreteSTT()
        stt.start_listening()
        self.assertTrue(stt.listening)
        stt.stop_listening()
        self.assertFalse(stt.listening)

    def test_transcribe_behavior(self):
        stt = ConcreteSTT()
        result = stt.transcribe(b"raw_wave_bytes")
        self.assertEqual(result.text, "Mocked Text")
        self.assertEqual(result.confidence, 0.95)

    def test_transcribe_failure_raises_exception(self):
        stt = ConcreteSTT()
        with self.assertRaises(SpeechRecognitionException):
            stt.transcribe(b"invalid")
