from __future__ import annotations

from abc import ABC, abstractmethod


class TextToSpeech(ABC):
    @abstractmethod
    def speak(self, text: str) -> None:
        """Synthesizes the given text string into audio output."""

    @abstractmethod
    def stop(self) -> None:
        """Abruptly stops current speech synthesis playback."""

    @abstractmethod
    def set_voice(self, voice_id: str) -> None:
        """Configures the current vocal identity."""

    @abstractmethod
    def set_rate(self, rate: int) -> None:
        """Configures the reading rate."""
