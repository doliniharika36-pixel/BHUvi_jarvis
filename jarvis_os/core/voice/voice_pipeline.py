from __future__ import annotations

import logging
from threading import RLock
from typing import Any

from .exceptions import (
    SpeechRecognitionException,
    SpeechSynthesisException,
    VoicePipelineException,
)
from .models import SpeechResult, VoiceMetadata, VoiceRequest, VoiceResponse
from .speech_to_text import SpeechToText
from .text_to_speech import TextToSpeech

logger = logging.getLogger(__name__)


class VoicePipeline:
    def __init__(
        self,
        stt: SpeechToText,
        tts: TextToSpeech,
        conversation_manager: Any,
    ) -> None:
        self._lock = RLock()
        self.stt = stt
        self.tts = tts
        self.conversation_manager = conversation_manager
        self._is_active = False

    def start_interaction_loop(self) -> None:
        with self._lock:
            try:
                self.stt.start_listening()
                self._is_active = True
                logger.info("Voice Pipeline interaction loop started.")
            except Exception as exc:
                raise VoicePipelineException(f"Failed to start voice listening: {exc}") from exc

    def stop_interaction_loop(self) -> None:
        with self._lock:
            try:
                self.stt.stop_listening()
                self.tts.stop()
                self._is_active = False
                logger.info("Voice Pipeline interaction loop stopped.")
            except Exception as exc:
                raise VoicePipelineException(f"Failed to cleanly stop voice pipeline: {exc}") from exc

    def process_voice_input(self, request: VoiceRequest) -> VoiceResponse:
        if not request or request.audio_data is None:
            raise VoicePipelineException("Invalid VoiceRequest or missing audio data.")

        try:
            speech_result: SpeechResult = self.stt.transcribe(request.audio_data)
        except SpeechRecognitionException:
            raise
        except Exception as exc:
            raise SpeechRecognitionException(f"Transcription layer failed: {exc}") from exc

        if not speech_result.text.strip():
            logger.warning("Empty transcription generated. Halting pipeline loop.")
            return VoiceResponse(
                input_text="",
                output_text="",
                metadata=VoiceMetadata(properties={"status": "empty_input"}),
            )

        try:
            from jarvis_os.core.conversation.models import ConversationMessage, ConversationRequest

            conv_message = ConversationMessage(role="user", content=speech_result.text)
            conv_request = ConversationRequest(message=conv_message)
            conv_response = self.conversation_manager.handle_request(conv_request)
            output_text = conv_response.message.content
        except Exception as exc:
            logger.error("Downstream Conversation Manager processing failed: %s", exc)
            raise VoicePipelineException(
                f"Conversation execution failed during voice pipeline: {exc}"
            ) from exc

        try:
            if output_text:
                self.tts.speak(output_text)
        except SpeechSynthesisException:
            raise
        except Exception as exc:
            raise SpeechSynthesisException(f"Audio output rendering failed: {exc}") from exc

        return VoiceResponse(
            input_text=speech_result.text,
            output_text=output_text,
            metadata=VoiceMetadata(properties={"confidence": speech_result.confidence}),
        )
