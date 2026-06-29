import threading
import unittest
from unittest.mock import MagicMock, Mock

from jarvis_os.core.voice.exceptions import (
    SpeechRecognitionException,
    SpeechSynthesisException,
    VoicePipelineException,
)
from jarvis_os.core.voice.models import SpeechResult, VoiceRequest
from jarvis_os.core.voice.voice_pipeline import VoicePipeline


class TestVoicePipeline(unittest.TestCase):
    def setUp(self):
        self.mock_stt = Mock()
        self.mock_tts = Mock()
        self.mock_conv_mgr = Mock()

        self.mock_stt.transcribe.return_value = SpeechResult(text="Tell me a joke", confidence=0.98)
        mock_response = MagicMock()
        mock_response.message.content = "Why did the processor cross the road? To reach the other pipeline."
        self.mock_conv_mgr.handle_request.return_value = mock_response

        self.pipeline = VoicePipeline(
            stt=self.mock_stt,
            tts=self.mock_tts,
            conversation_manager=self.mock_conv_mgr,
        )

    def test_pipeline_control_start_and_stop(self):
        self.pipeline.start_interaction_loop()
        self.mock_stt.start_listening.assert_called_once()
        self.assertTrue(self.pipeline._is_active)

        self.pipeline.stop_interaction_loop()
        self.mock_stt.stop_listening.assert_called_once()
        self.mock_tts.stop.assert_called_once()
        self.assertFalse(self.pipeline._is_active)

    def test_process_voice_input_success_path(self):
        response = self.pipeline.process_voice_input(VoiceRequest(audio_data=b"valid_pcm_wave"))

        self.assertEqual(response.input_text, "Tell me a joke")
        self.assertEqual(
            response.output_text,
            "Why did the processor cross the road? To reach the other pipeline.",
        )
        self.assertEqual(response.metadata.properties.get("confidence"), 0.98)
        self.mock_stt.transcribe.assert_called_once_with(b"valid_pcm_wave")
        self.mock_conv_mgr.handle_request.assert_called_once()
        self.mock_tts.speak.assert_called_once_with(
            "Why did the processor cross the road? To reach the other pipeline."
        )

    def test_empty_transcription_stops_pipeline_execution(self):
        self.mock_stt.transcribe.return_value = SpeechResult(text="   ", confidence=0.2)

        response = self.pipeline.process_voice_input(VoiceRequest(audio_data=b"silence"))

        self.assertEqual(response.input_text, "")
        self.assertEqual(response.output_text, "")
        self.mock_conv_mgr.handle_request.assert_not_called()
        self.mock_tts.speak.assert_not_called()

    def test_stt_failure_propagates(self):
        self.mock_stt.transcribe.side_effect = SpeechRecognitionException("Device lost connection")

        with self.assertRaises(SpeechRecognitionException):
            self.pipeline.process_voice_input(VoiceRequest(audio_data=b"corrupted"))

    def test_tts_failure_propagates(self):
        self.mock_tts.speak.side_effect = SpeechSynthesisException("Speakers unplugged")

        with self.assertRaises(SpeechSynthesisException):
            self.pipeline.process_voice_input(VoiceRequest(audio_data=b"voice_wave"))

    def test_missing_audio_data_raises_exception(self):
        with self.assertRaises(VoicePipelineException):
            self.pipeline.process_voice_input(None)  # type: ignore

    def test_thread_safety_during_loop_state_modification(self):
        errors = []

        def worker():
            try:
                self.pipeline.start_interaction_loop()
                self.pipeline.stop_interaction_loop()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(errors), 0, f"Encountered thread safety failures: {errors}")
