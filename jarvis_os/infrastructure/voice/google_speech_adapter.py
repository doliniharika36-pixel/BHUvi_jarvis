"""
Google Speech Adapter for speech-to-text transcription.
"""
from __future__ import annotations

import logging
import queue
from typing import Any, Callable, Optional

import speech_recognition as sr

from jarvis_os.core.voice.exceptions import SpeechRecognitionException
from jarvis_os.core.voice.models import SpeechResult, VoiceMetadata
from jarvis_os.core.voice.speech_to_text import SpeechToText

logger = logging.getLogger(__name__)


class GoogleSpeechAdapter(SpeechToText):
    """Concrete implementation of SpeechToText using Python's speech_recognition.
    
    This adapter integrates Google Web Speech recognition with the Jarvis OS voice pipeline.
    """

    def __init__(
        self,
        recognizer: Optional[sr.Recognizer] = None,
        microphone: Optional[sr.Microphone] = None,
        language: str = "en-US",
        callback: Optional[Callable[[sr.Recognizer, sr.AudioData], None]] = None,
        sample_rate: int = 16000,
        sample_width: int = 2,
    ) -> None:
        """Initializes the adapter.
        
        Args:
            recognizer: An optional pre-configured Recognizer instance.
            microphone: An optional Microphone instance.
            language: Language code for transcription (default: "en-US").
            callback: Custom callback for background listening.
            sample_rate: Default sample rate for converting raw bytes (default: 16000).
            sample_width: Default sample width (in bytes) for converting raw bytes (default: 2).
        """
        self._recognizer = recognizer or sr.Recognizer()
        self._microphone = microphone
        self.language = language
        self._custom_callback = callback
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        
        self._stop_listening_fn: Optional[Callable[..., None]] = None
        self._audio_queue: queue.Queue[sr.AudioData] = queue.Queue()

    def start_listening(self) -> None:
        """Initiates background audio listening or stream capture."""
        if self._stop_listening_fn is not None:
            # Already listening
            return

        try:
            if self._microphone is None:
                self._microphone = sr.Microphone()

            # Ensure we calibrate the microphone for ambient noise
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source)

            self._stop_listening_fn = self._recognizer.listen_in_background(
                self._microphone,
                self._default_callback
            )
        except Exception as exc:
            raise SpeechRecognitionException(
                f"Failed to start background listening: {exc}"
            ) from exc

    def stop_listening(self) -> None:
        """Halts background listening and cleans up local audio stream resources."""
        if self._stop_listening_fn is not None:
            try:
                self._stop_listening_fn(wait_for_stop=False)
            except Exception as exc:
                raise SpeechRecognitionException(
                    f"Failed to cleanly stop background listening: {exc}"
                ) from exc
            finally:
                self._stop_listening_fn = None

    def transcribe(self, audio_data: Any) -> SpeechResult:
        """Converts raw audio data into transcript text.
        
        Args:
            audio_data: speech_recognition.AudioData or raw PCM bytes.
            
        Returns:
            SpeechResult: The transcript text and confidence score.
            
        Raises:
            SpeechRecognitionException: If transcription fails.
        """
        if audio_data is None:
            raise SpeechRecognitionException("Audio data cannot be None.")

        # Convert raw bytes to AudioData
        if isinstance(audio_data, (bytes, bytearray)):
            try:
                audio = sr.AudioData(
                    audio_data,
                    sample_rate=self.sample_rate,
                    sample_width=self.sample_width
                )
            except Exception as exc:
                raise SpeechRecognitionException(
                    f"Failed to parse raw bytes into AudioData: {exc}"
                ) from exc
        elif isinstance(audio_data, sr.AudioData):
            audio = audio_data
        else:
            raise SpeechRecognitionException(
                f"Unsupported audio data type: {type(audio_data)}. "
                f"Expected speech_recognition.AudioData or raw PCM bytes."
            )

        try:
            # Request Google Web Speech transcription.
            # show_all=True retrieves alternative transcriptions along with confidence scores.
            response = self._recognizer.recognize_google(
                audio,
                language=self.language,
                show_all=True
            )

            if not response or not isinstance(response, dict) or "alternative" not in response:
                raise sr.UnknownValueError("Google Web Speech returned empty or malformed result.")

            alternatives = response["alternative"]
            if not alternatives:
                raise sr.UnknownValueError("No transcription alternatives returned.")

            # Best alternative is the first item
            best_alt = alternatives[0]
            text = best_alt.get("transcript", "")
            confidence = best_alt.get("confidence", 0.0)

            return SpeechResult(
                text=text,
                confidence=confidence,
                metadata=VoiceMetadata(properties={"provider": "google"})
            )

        except sr.UnknownValueError as exc:
            raise SpeechRecognitionException(
                f"Speech was unintelligible or could not be recognized: {exc}"
            ) from exc
        except sr.RequestError as exc:
            raise SpeechRecognitionException(
                f"Google Web Speech API request failed: {exc}"
            ) from exc
        except Exception as exc:
            raise SpeechRecognitionException(
                f"Error during Google Web Speech transcription: {exc}"
            ) from exc

    def _default_callback(self, recognizer: sr.Recognizer, audio: sr.AudioData) -> None:
        """Internal callback passed to listen_in_background."""
        if self._custom_callback:
            try:
                self._custom_callback(recognizer, audio)
            except Exception as exc:
                logger.error("Custom callback error in GoogleSpeechAdapter: %s", exc)
        else:
            self._audio_queue.put(audio)

    @property
    def audio_queue(self) -> queue.Queue[sr.AudioData]:
        """Provides access to the queue of captured audio data when listening in background."""
        return self._audio_queue
