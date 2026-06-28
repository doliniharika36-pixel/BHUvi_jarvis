"""
LLM Provider Port Contract for Jarvis OS.

Milestone 6A — Provider Abstraction Layer.

This module defines the model-agnostic provider interface used by all future
LLM back-end adapters (Ollama, OpenAI, Anthropic, LM Studio, llama.cpp, etc.).

IMPORTANT: This module does NOT replace or modify LLMPort.
           LLMPort (core/ports/llm.py) remains frozen and unchanged.
           LLMProvider is an independent, richer interface introduced alongside it.

Design invariants:
  - No provider-specific fields or imports.
  - No business logic.
  - No IO operations.
  - No concrete implementations.
  - Reuses LLMMessage and LLMResponse from core domain entities.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Iterator, List, Optional

from jarvis_os.core.domain.entities import LLMMessage, LLMResponse
from jarvis_os.core.domain.exceptions import LLMException


# ---------------------------------------------------------------------------
# Capability Enum
# ---------------------------------------------------------------------------

class ModelCapability(Enum):
    """Enumeration of capabilities a model may declare.

    Providers populate ModelInfo.capabilities so that consumers can select
    the appropriate model for a task without querying the provider at runtime.
    """
    CHAT_COMPLETION = "chat_completion"
    TEXT_COMPLETION = "text_completion"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    FUNCTION_CALLING = "function_calling"
    STREAMING = "streaming"
    CODE = "code"


# ---------------------------------------------------------------------------
# Value Objects (frozen dataclasses — immutable after construction)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelInfo:
    """Metadata describing a single model exposed by a provider.

    Fields:
        model_id:          Provider-unique model identifier (e.g. 'qwen2.5:1.5b').
        display_name:      Human-readable label.
        context_window:    Maximum number of tokens the model can process in one
                           call (prompt + completion combined).
        capabilities:      Set of declared ModelCapability values.
        max_output_tokens: Optional ceiling on generated tokens per response.
        description:       Optional free-text model description.
    """
    model_id: str
    display_name: str
    context_window: int
    capabilities: List[ModelCapability] = field(default_factory=list)
    max_output_tokens: Optional[int] = None
    description: str = ""


@dataclass(frozen=True)
class GenerationOptions:
    """Typed, validated generation parameters for a single inference call.

    All fields have sensible defaults. Consumers override only what they need.

    Fields:
        temperature:      Sampling randomness (0.0 = deterministic, 2.0 = maximum).
        top_p:            Nucleus sampling cumulative probability threshold.
        top_k:            Top-k token filtering.
        max_tokens:       Maximum number of tokens to generate.
        stop_sequences:   List of strings at which generation halts.
        timeout_seconds:  Wall-clock timeout for the entire call. Providers
                          MUST raise LLMTimeoutError if this is exceeded.
        seed:             Optional reproducibility seed.
    """
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 512
    stop_sequences: List[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    seed: Optional[int] = None


@dataclass(frozen=True)
class LLMRequest:
    """Structured, typed request sent to an LLMProvider.

    Wraps a list of domain LLMMessage objects and an optional typed options
    object. Reuses the existing LLMMessage domain entity without modification.

    Fields:
        model_id:  The provider-specific model identifier to use.
        messages:  Conversation history / prompt messages.
        options:   Generation tuning parameters.
    """
    model_id: str
    messages: List[LLMMessage]
    options: GenerationOptions = field(default_factory=GenerationOptions)

    def __post_init__(self) -> None:
        if not self.model_id or not self.model_id.strip():
            raise LLMRequestValidationError("LLMRequest.model_id must not be empty.")
        if not self.messages:
            raise LLMRequestValidationError("LLMRequest.messages must contain at least one message.")


# ---------------------------------------------------------------------------
# Streaming Contract
# ---------------------------------------------------------------------------

class StreamingResponse(ABC):
    """Abstract streaming interface returned by generate_stream().

    Implementations yield individual token strings progressively so that the
    caller can render output before the full response is available.

    The synchronous iterator form is used for simplicity; async streaming is
    handled by generate_stream_async() which returns AsyncIterator[str] directly.

    Lifecycle:
        - Iteration yields str tokens in order.
        - cancel() signals the provider to abort mid-stream.
        - is_complete() returns True only after the stream terminates normally.
    """

    @abstractmethod
    def __iter__(self) -> Iterator[str]:
        """Yield tokens one at a time until completion or cancellation."""
        ...

    @abstractmethod
    def cancel(self) -> None:
        """Signal the provider to abort generation.

        After calling cancel(), further iteration must stop immediately.
        Raises:
            LLMCancelledError: May be raised by the next iteration step.
        """
        ...

    @abstractmethod
    def is_complete(self) -> bool:
        """Return True if the stream terminated normally (not cancelled)."""
        ...


# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------

class LLMProviderError(LLMException):
    """Base class for all LLMProvider-specific errors.

    Inherits from LLMException so that all existing code catching LLMException
    continues to work without modification (backward-compatible extension).
    """
    pass


class LLMTimeoutError(LLMProviderError):
    """Raised when provider inference exceeds GenerationOptions.timeout_seconds.

    This error is recoverable. The orchestrator may retry with a shorter
    prompt or a different model.
    """
    pass


class LLMCancelledError(LLMProviderError):
    """Raised when the caller cancels an in-progress generation request.

    This is a clean, user-initiated abort — not a failure. The orchestrator
    must not retry cancelled requests automatically.
    """
    pass


class LLMRequestValidationError(LLMProviderError):
    """Raised when an LLMRequest fails structural validation before dispatch.

    This error is non-recoverable without fixing the request (e.g., empty
    model_id, empty messages list, out-of-range temperature).
    """
    pass


class LLMModelNotFoundError(LLMProviderError):
    """Raised when the requested model_id is not known to the provider.

    Callers should call get_models() to enumerate available models before
    constructing an LLMRequest.
    """

    def __init__(self, model_id: str, provider_name: str = "") -> None:
        msg = f"Model '{model_id}' not found"
        if provider_name:
            msg += f" on provider '{provider_name}'"
        super().__init__(msg)
        self.model_id = model_id
        self.provider_name = provider_name


# ---------------------------------------------------------------------------
# LLMProvider Interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Model-agnostic interface for all LLM back-end adapters.

    Every concrete adapter (Ollama, OpenAI, Anthropic, llama.cpp, etc.) must
    implement this interface. Consumers depend only on this interface — they
    never import concrete adapter classes directly.

    Design invariants:
      - Providers are stateless with respect to conversation history.
        History is the caller's responsibility via LLMRequest.messages.
      - Providers do not perform tool execution, memory lookup, or routing.
      - Providers expose only model inference capabilities.

    Error contract:
      - All provider errors must be instances of LLMProviderError (or a subclass).
      - Timeouts raise LLMTimeoutError.
      - Cancellations raise LLMCancelledError.
      - Invalid requests raise LLMRequestValidationError (raised before I/O).
      - Unknown models raise LLMModelNotFoundError.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g., 'Ollama', 'OpenAI').

        Must be stable across restarts; used for logging and diagnostics.
        """
        ...

    # ------------------------------------------------------------------
    # Model Discovery
    # ------------------------------------------------------------------

    @abstractmethod
    def get_models(self) -> List[ModelInfo]:
        """Return all models currently available on this provider.

        Returns:
            List of ModelInfo objects. May be empty if no models are loaded.

        Raises:
            LLMProviderError: If the provider cannot be reached.
        """
        ...

    # ------------------------------------------------------------------
    # Synchronous Generation
    # ------------------------------------------------------------------

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Execute a blocking inference call and return the full response.

        Reuses the existing domain LLMResponse so downstream consumers require
        no changes.

        Args:
            request: Fully-typed LLMRequest with messages and options.

        Returns:
            LLMResponse with content, token_usage, model_name, elapsed_seconds.

        Raises:
            LLMRequestValidationError: If the request fails pre-flight validation.
            LLMModelNotFoundError:     If model_id is not available.
            LLMTimeoutError:           If inference exceeds timeout_seconds.
            LLMProviderError:          For all other provider failures.
        """
        ...

    @abstractmethod
    def generate_stream(self, request: LLMRequest) -> StreamingResponse:
        """Start a streaming inference call and return a StreamingResponse.

        The returned object is an iterator that yields individual token strings.
        The caller is responsible for consuming the iterator fully or calling
        cancel() to abort early.

        Args:
            request: Fully-typed LLMRequest. The model must declare
                     ModelCapability.STREAMING; otherwise providers should raise
                     LLMRequestValidationError.

        Returns:
            StreamingResponse iterator.

        Raises:
            LLMRequestValidationError: If the model does not support streaming.
            LLMModelNotFoundError:     If model_id is not available.
            LLMTimeoutError:           If the first token exceeds timeout_seconds.
            LLMProviderError:          For all other provider failures.
        """
        ...

    # ------------------------------------------------------------------
    # Asynchronous Generation
    # ------------------------------------------------------------------

    @abstractmethod
    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        """Async equivalent of generate().

        Allows callers to await inference without blocking the event loop.

        Args:
            request: Fully-typed LLMRequest.

        Returns:
            LLMResponse (same structure as synchronous generate()).

        Raises:
            LLMRequestValidationError: If the request fails pre-flight validation.
            LLMModelNotFoundError:     If model_id is not available.
            LLMTimeoutError:           If inference exceeds timeout_seconds.
            LLMCancelledError:         If the asyncio task is cancelled.
            LLMProviderError:          For all other provider failures.
        """
        ...

    @abstractmethod
    async def generate_stream_async(
        self, request: LLMRequest
    ) -> AsyncIterator[str]:
        """Async streaming inference — yields token strings asynchronously.

        Designed for async event-loop contexts where blocking iteration is
        not acceptable.

        Args:
            request: Fully-typed LLMRequest.

        Returns:
            AsyncIterator yielding token strings.

        Raises:
            LLMRequestValidationError: If the model does not support streaming.
            LLMModelNotFoundError:     If model_id is not available.
            LLMTimeoutError:           If the first token exceeds timeout_seconds.
            LLMCancelledError:         If the asyncio task is cancelled.
            LLMProviderError:          For all other provider failures.
        """
        ...
