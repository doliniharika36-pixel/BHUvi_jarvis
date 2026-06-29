class VoiceException(Exception):
    """Base exception for all voice pipeline operations."""


class SpeechRecognitionException(VoiceException):
    """Raised when speech-to-text processing or transcription fails."""


class SpeechSynthesisException(VoiceException):
    """Raised when text-to-speech synthesis or speaker routing fails."""


class VoicePipelineException(VoiceException):
    """Raised when general orchestration faults prevent the loop from executing."""
