"""Map Ollama/HTTP errors to LLMProviderError hierarchy."""

from __future__ import annotations

import json
import urllib.error
from typing import Any, Optional

from jarvis_os.core.domain.exceptions import LLMException
from jarvis_os.core.ports.llm_provider import (
    LLMModelNotFoundError,
    LLMProviderError,
    LLMRequestValidationError,
    LLMTimeoutError,
)


def map_ollama_error(exc: BaseException) -> LLMProviderError:
    """Convert arbitrary HTTP/runtime errors into provider contract errors."""

    msg = str(exc)

    # Timeout
    if "timed out" in msg.lower() or "timeout" in msg.lower():
        return LLMTimeoutError(msg)

    # Model not found patterns (Ollama typically includes 404)
    if isinstance(exc, urllib.error.HTTPError) and getattr(exc, "code", None) == 404:
        # model id might not be in message; best-effort.
        return LLMModelNotFoundError(model_id="unknown", provider_name="Ollama")

    if "model" in msg.lower() and "not found" in msg.lower():
        return LLMModelNotFoundError(model_id="unknown", provider_name="Ollama")

    # Basic validation patterns
    if "400" in msg or "bad request" in msg.lower():
        return LLMRequestValidationError(msg)

    # Fallback
    if isinstance(exc, LLMException):
        # Already in our hierarchy.
        if isinstance(exc, LLMProviderError):
            return exc
        return LLMProviderError(msg)

    return LLMProviderError(msg)

