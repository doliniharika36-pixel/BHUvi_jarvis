import unittest

from jarvis_os.core.voice.exceptions import SpeechSynthesisException
from jarvis_os.core.voice.text_to_speech import TextToSpeech


class ConcreteTTS(TextToSpeech):
    def __init__(self):
        self.voice_id = "default"
        self.rate = 150
        self.speaking = False

    def speak(self, text: str) -> None:
        if text == "error":
            raise SpeechSynthesisException("Output stream blocked")
        self.speaking = True

    def stop(self) -> None:
        self.speaking = False

    def set_voice(self, voice_id: str) -> None:
        self.voice_id = voice_id

    def set_rate(self, rate: int) -> None:
        self.rate = rate


class TestTextToSpeech(unittest.TestCase):
    def test_cannot_instantiate_abstract_class(self):
        with self.assertRaises(TypeError):
            TextToSpeech()  # type: ignore

    def test_concrete_implementation_properties(self):
        tts = ConcreteTTS()
        tts.set_voice("male_english")
        tts.set_rate(180)
        self.assertEqual(tts.voice_id, "male_english")
        self.assertEqual(tts.rate, 180)

    def test_speak_and_stop_lifecycle(self):
        tts = ConcreteTTS()
        tts.speak("Testing sound systems")
        self.assertTrue(tts.speaking)
        tts.stop()
        self.assertFalse(tts.speaking)

    def test_speak_error_propagation(self):
        tts = ConcreteTTS()
        with self.assertRaises(SpeechSynthesisException):
            tts.speak("error")
