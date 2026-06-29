from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import SpeechResult


class SpeechToText(ABC):
    @abstractmethod
    def start_listening(self) -> None:
        """Initiates background audio listening or stream capture."""

    @abstractmethod
    def stop_listening(self) -> None:
        """Halts background listening and cleans up local audio stream resources."""

    @abstractmethod
    def transcribe(self, audio_data: Any) -> SpeechResult:
        """Converts raw audio data into transcript text."""
