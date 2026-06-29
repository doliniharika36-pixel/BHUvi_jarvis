import unittest
import queue
from unittest.mock import MagicMock, patch

import speech_recognition as sr

from jarvis_os.core.voice.exceptions import SpeechRecognitionException
from jarvis_os.core.voice.models import SpeechResult
from jarvis_os.infrastructure.voice.google_speech_adapter import GoogleSpeechAdapter


class TestGoogleSpeechAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_recognizer = MagicMock(spec=sr.Recognizer)
        self.mock_microphone = MagicMock(spec=sr.Microphone)
        
        # Configure microphone context manager mock
        self.mock_microphone.__enter__.return_value = MagicMock()
        self.mock_microphone.__exit__.return_value = False

        self.adapter = GoogleSpeechAdapter(
            recognizer=self.mock_recognizer,
            microphone=self.mock_microphone,
            language="en-US"
        )

    def test_init_defaults(self) -> None:
        adapter = GoogleSpeechAdapter()
        self.assertIsInstance(adapter._recognizer, sr.Recognizer)
        self.assertIsNone(adapter._microphone)
        self.assertEqual(adapter.language, "en-US")
        self.assertEqual(adapter.sample_rate, 16000)
        self.assertEqual(adapter.sample_width, 2)
        self.assertIsNone(adapter._stop_listening_fn)
        self.assertIsInstance(adapter.audio_queue, queue.Queue)

    def test_init_custom_params(self) -> None:
        custom_cb = lambda r, a: None
        adapter = GoogleSpeechAdapter(
            recognizer=self.mock_recognizer,
            microphone=self.mock_microphone,
            language="fr-FR",
            callback=custom_cb,
            sample_rate=44100,
            sample_width=4
        )
        self.assertEqual(adapter._recognizer, self.mock_recognizer)
        self.assertEqual(adapter._microphone, self.mock_microphone)
        self.assertEqual(adapter.language, "fr-FR")
        self.assertEqual(adapter._custom_callback, custom_cb)
        self.assertEqual(adapter.sample_rate, 44100)
        self.assertEqual(adapter.sample_width, 4)

    def test_transcribe_success_with_audiodata(self) -> None:
        # Mock recognize_google to return dict format when show_all=True
        self.mock_recognizer.recognize_google.return_value = {
            "alternative": [
                {"transcript": "hello world", "confidence": 0.98},
                {"transcript": "hello word", "confidence": 0.50}
            ]
        }

        audio = MagicMock(spec=sr.AudioData)
        result = self.adapter.transcribe(audio)

        self.assertIsInstance(result, SpeechResult)
        self.assertEqual(result.text, "hello world")
        self.assertEqual(result.confidence, 0.98)
        self.assertEqual(result.metadata.properties.get("provider"), "google")
        
        self.mock_recognizer.recognize_google.assert_called_once_with(
            audio,
            language="en-US",
            show_all=True
        )

    def test_transcribe_success_with_bytes(self) -> None:
        self.mock_recognizer.recognize_google.return_value = {
            "alternative": [
                {"transcript": "test text", "confidence": 0.85}
            ]
        }

        raw_bytes = b"\x00\x00\x10\x10"
        mock_audio_instance = MagicMock(spec=sr.AudioData)
        with patch("speech_recognition.AudioData") as mock_audio_class:
            mock_audio_class.return_value = mock_audio_instance

            result = self.adapter.transcribe(raw_bytes)

            mock_audio_class.assert_called_once_with(
                raw_bytes,
                sample_rate=16000,
                sample_width=2
            )
            self.assertEqual(result.text, "test text")
            self.assertEqual(result.confidence, 0.85)

    def test_transcribe_invalid_audio_type_raises_exception(self) -> None:
        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.transcribe([1, 2, 3])
        self.assertIn("Unsupported audio data type", str(ctx.exception))

    def test_transcribe_none_raises_exception(self) -> None:
        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.transcribe(None)
        self.assertIn("Audio data cannot be None", str(ctx.exception))

    def test_transcribe_google_unknown_value_error_raises_exception(self) -> None:
        self.mock_recognizer.recognize_google.side_effect = sr.UnknownValueError("unintelligible")

        audio = MagicMock(spec=sr.AudioData)
        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.transcribe(audio)
        self.assertIn("unintelligible or could not be recognized", str(ctx.exception))

    def test_transcribe_google_request_error_raises_exception(self) -> None:
        self.mock_recognizer.recognize_google.side_effect = sr.RequestError("API rate limit exceeded")

        audio = MagicMock(spec=sr.AudioData)
        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.transcribe(audio)
        self.assertIn("request failed", str(ctx.exception))

    def test_transcribe_generic_error_raises_exception(self) -> None:
        self.mock_recognizer.recognize_google.side_effect = RuntimeError("Something bad happened")

        audio = MagicMock(spec=sr.AudioData)
        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.transcribe(audio)
        self.assertIn("Error during Google Web Speech transcription", str(ctx.exception))

    def test_transcribe_empty_google_alternatives_raises_exception(self) -> None:
        self.mock_recognizer.recognize_google.return_value = {"alternative": []}

        audio = MagicMock(spec=sr.AudioData)
        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.transcribe(audio)
        self.assertIn("No transcription alternatives returned", str(ctx.exception))

    def test_transcribe_malformed_google_response_raises_exception(self) -> None:
        self.mock_recognizer.recognize_google.return_value = "raw string response instead of dict"

        audio = MagicMock(spec=sr.AudioData)
        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.transcribe(audio)
        self.assertIn("Google Web Speech returned empty or malformed result", str(ctx.exception))

    def test_start_listening_success(self) -> None:
        mock_stop_fn = MagicMock()
        self.mock_recognizer.listen_in_background.return_value = mock_stop_fn

        self.adapter.start_listening()

        self.mock_recognizer.adjust_for_ambient_noise.assert_called_once()
        self.mock_recognizer.listen_in_background.assert_called_once_with(
            self.mock_microphone,
            self.adapter._default_callback
        )
        self.assertEqual(self.adapter._stop_listening_fn, mock_stop_fn)

    def test_start_listening_when_already_listening(self) -> None:
        mock_stop_fn = MagicMock()
        self.adapter._stop_listening_fn = mock_stop_fn

        self.adapter.start_listening()

        # Should not call listen_in_background again
        self.mock_recognizer.listen_in_background.assert_not_called()

    def test_start_listening_failure_raises_exception(self) -> None:
        self.mock_recognizer.listen_in_background.side_effect = RuntimeError("Microphone unavailable")

        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.start_listening()
        self.assertIn("Failed to start background listening", str(ctx.exception))

    def test_stop_listening_success(self) -> None:
        mock_stop_fn = MagicMock()
        self.adapter._stop_listening_fn = mock_stop_fn

        self.adapter.stop_listening()

        mock_stop_fn.assert_called_once_with(wait_for_stop=False)
        self.assertIsNone(self.adapter._stop_listening_fn)

    def test_stop_listening_when_not_listening(self) -> None:
        self.adapter.stop_listening()
        # Should not throw or crash

    def test_stop_listening_failure_raises_exception(self) -> None:
        mock_stop_fn = MagicMock(side_effect=RuntimeError("Thread join failed"))
        self.adapter._stop_listening_fn = mock_stop_fn

        with self.assertRaises(SpeechRecognitionException) as ctx:
            self.adapter.stop_listening()
        self.assertIn("Failed to cleanly stop background listening", str(ctx.exception))
        # Ensure cleanup is done even if stop call failed
        self.assertIsNone(self.adapter._stop_listening_fn)

    def test_default_callback_appends_to_queue(self) -> None:
        audio = MagicMock(spec=sr.AudioData)
        self.adapter._default_callback(self.mock_recognizer, audio)

        self.assertEqual(self.adapter.audio_queue.qsize(), 1)
        self.assertEqual(self.adapter.audio_queue.get(), audio)

    def test_custom_callback_called(self) -> None:
        custom_cb = MagicMock()
        self.adapter._custom_callback = custom_cb

        audio = MagicMock(spec=sr.AudioData)
        self.adapter._default_callback(self.mock_recognizer, audio)

        custom_cb.assert_called_once_with(self.mock_recognizer, audio)
        self.assertEqual(self.adapter.audio_queue.qsize(), 0)

    def test_custom_callback_failure_does_not_crash(self) -> None:
        custom_cb = MagicMock(side_effect=RuntimeError("Callback crashed"))
        self.adapter._custom_callback = custom_cb

        audio = MagicMock(spec=sr.AudioData)
        
        # This call should not raise an exception
        self.adapter._default_callback(self.mock_recognizer, audio)
        
        custom_cb.assert_called_once_with(self.mock_recognizer, audio)


if __name__ == "__main__":
    unittest.main()
