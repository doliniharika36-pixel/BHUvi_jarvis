from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class VoiceMetadata:
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechResult:
    text: str
    confidence: float
    metadata: Optional[VoiceMetadata] = None


@dataclass(frozen=True)
class VoiceRequest:
    audio_data: Any
    metadata: Optional[VoiceMetadata] = None


@dataclass(frozen=True)
class VoiceResponse:
    input_text: str
    output_text: str
    metadata: Optional[VoiceMetadata] = None
