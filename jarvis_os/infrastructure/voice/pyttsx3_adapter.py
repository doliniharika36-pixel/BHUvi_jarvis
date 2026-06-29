"""
Pyttsx3 Adapter for text-to-speech synthesis.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from jarvis_os.core.voice.exceptions import SpeechSynthesisException
from jarvis_os.core.voice.text_to_speech import TextToSpeech

logger = logging.getLogger(__name__)


class Pyttsx3Adapter(TextToSpeech):
    """Concrete implementation of TextToSpeech using pyttsx3.
    
    This adapter integrates pyttsx3 vocal synthesis with the Jarvis OS voice pipeline.
    """

    def __init__(self, engine: Optional[Any] = None) -> None:
        """Initializes the adapter.
        
        Args:
            engine: An optional pre-configured pyttsx3 engine instance (for testing/DI).
        """
        self._engine = engine

    def _get_engine(self) -> Any:
        """Lazily initializes the pyttsx3 engine with COM support if needed."""
        if self._engine is None:
            try:
                import pyttsx3
                # On Windows, we might need to initialize COM in case of multithreading
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except ImportError:
                    pass
                self._engine = pyttsx3.init()
            except Exception as exc:
                raise SpeechSynthesisException(
                    f"Failed to initialize pyttsx3 engine: {exc}"
                ) from exc
        return self._engine

    def speak(self, text: str) -> None:
        """Synthesizes the given text string into audio output.
        
        Args:
            text: The text string to synthesize.
            
        Raises:
            SpeechSynthesisException: If synthesis fails.
        """
        if not text:
            return  # Empty or null text is a no-op

        engine = self._get_engine()
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            raise SpeechSynthesisException(
                f"Failed to synthesize speech using pyttsx3: {exc}"
            ) from exc

    def stop(self) -> None:
        """Abruptly stops current speech synthesis playback.
        
        Raises:
            SpeechSynthesisException: If stopping fails.
        """
        engine = self._get_engine()
        try:
            engine.stop()
        except Exception as exc:
            raise SpeechSynthesisException(
                f"Failed to stop pyttsx3 speech playback: {exc}"
            ) from exc

    def set_voice(self, voice_id: str) -> None:
        """Configures the current vocal identity.
        
        Args:
            voice_id: The identifier of the desired voice.
            
        Raises:
            SpeechSynthesisException: If the voice_id is invalid or cannot be set.
        """
        if not voice_id:
            raise SpeechSynthesisException("Voice ID cannot be empty.")

        engine = self._get_engine()
        try:
            # Verify the voice_id exists in available voices
            voices = engine.getProperty("voices")
            voice_ids = [v.id for v in voices]
            if voice_id not in voice_ids:
                raise SpeechSynthesisException(
                    f"Voice ID '{voice_id}' not found. Available voices: {voice_ids}"
                )

            engine.setProperty("voice", voice_id)
        except SpeechSynthesisException:
            raise
        except Exception as exc:
            raise SpeechSynthesisException(
                f"Failed to configure pyttsx3 voice: {exc}"
            ) from exc

    def set_rate(self, rate: int) -> None:
        """Configures the reading rate.
        
        Args:
            rate: Speech rate (words per minute). Must be a positive integer.
            
        Raises:
            SpeechSynthesisException: If the rate is invalid or cannot be set.
        """
        if rate <= 0:
            raise SpeechSynthesisException("Speech rate must be a positive integer.")

        engine = self._get_engine()
        try:
            engine.setProperty("rate", rate)
        except Exception as exc:
            raise SpeechSynthesisException(
                f"Failed to configure pyttsx3 speech rate: {exc}"
            ) from exc
