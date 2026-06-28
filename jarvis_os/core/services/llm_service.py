"""LLMService orchestrates access to an injected LLMProvider.

Milestone 6C — LLM Service
- Consumes only LLMProvider
- No direct Ollama dependencies
- Provides request validation, response normalization,
  streaming orchestration, cancellation bridging, provider selection,
  and capability checks.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from jarvis_os.core.domain.entities import LLMMessage, LLMResponse
from jarvis_os.core.domain.exceptions import LLMException
from jarvis_os.core.ports.llm_provider import (
    GenerationOptions,
    LLMProvider,
    LLMRequest,
    LLMRequestValidationError,
    LLMProviderError,
    LLMCancelledError,
    LLMModelNotFoundError,
    ModelCapability,
    ModelInfo,
    StreamingResponse,
)


@dataclass(frozen=True)
class LLMCompletionResult:
    """Normalized completion result."""

    response: LLMResponse


class LLMService:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    def _validate(self, request: LLMRequest, require_streaming: bool = False) -> None:
        if not request.model_id or not request.model_id.strip():
            raise LLMRequestValidationError("model_id must not be empty")
        if not request.messages:
            raise LLMRequestValidationError("messages must not be empty")
        if require_streaming:
            # Capability check via get_models()
            models = {m.model_id: m for m in self._provider.get_models()}
            if request.model_id not in models:
                raise LLMModelNotFoundError(request.model_id, self.provider_name)
            if ModelCapability.STREAMING not in models[request.model_id].capabilities:
                raise LLMRequestValidationError("Selected model does not support streaming")

    def _normalize_stream(self, stream: StreamingResponse) -> Iterator[str]:
        # LLMService doesn’t alter tokens; it orchestrates cancellation.
        for token in stream:
            yield token

    def complete(self, prompt: str, options: Optional[GenerationOptions] = None) -> LLMResponse:
        """Text completion using chat provider capabilities.

        (LLMPort includes generate/chat, but Milestone 6C is only specified
        to consume LLMProvider; we use a minimal message mapping.)
        """
        opts = options or GenerationOptions()
        messages = [LLMMessage(role="user", content=prompt)]
        req = LLMRequest(model_id=self._select_model_id(), messages=messages, options=opts)
        self._validate(req, require_streaming=False)
        return self._provider.generate(req)

    def chat_stream(self, messages: List[LLMMessage], options: Optional[GenerationOptions] = None) -> StreamingResponse:
        opts = options or GenerationOptions()
        model_id = self._select_model_id(messages=messages)
        req = LLMRequest(model_id=model_id, messages=messages, options=opts)
        self._validate(req, require_streaming=True)
        return self._provider.generate_stream(req)

    def chat(self, messages: List[LLMMessage], options: Optional[GenerationOptions] = None) -> LLMResponse:
        opts = options or GenerationOptions()
        model_id = self._select_model_id(messages=messages)
        req = LLMRequest(model_id=model_id, messages=messages, options=opts)
        self._validate(req, require_streaming=False)
        return self._provider.generate(req)

    async def chat_async(self, messages: List[LLMMessage], options: Optional[GenerationOptions] = None) -> LLMResponse:
        opts = options or GenerationOptions()
        model_id = self._select_model_id(messages=messages)
        req = LLMRequest(model_id=model_id, messages=messages, options=opts)
        self._validate(req, require_streaming=False)
        return await self._provider.generate_async(req)

    async def chat_stream_async(
        self,
        messages: List[LLMMessage],
        options: Optional[GenerationOptions] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[str]:
        opts = options or GenerationOptions()
        model_id = self._select_model_id(messages=messages)
        req = LLMRequest(model_id=model_id, messages=messages, options=opts)
        self._validate(req, require_streaming=True)

        # Provider-level async stream
        async_iter = await self._provider.generate_stream_async(req)

        try:
            async for token in async_iter:
                if cancel_event is not None and cancel_event.is_set():
                    break
                yield token
        except LLMCancelledError:
            raise


    def _select_model_id(self, messages: Optional[List[LLMMessage]] = None) -> str:
        models = self._provider.get_models()
        if not models:
            raise LLMProviderError("No models available from provider")

        # Prefer streaming-capable model when it exists.
        streaming = [m for m in models if ModelCapability.STREAMING in m.capabilities]
        chosen = streaming[0] if streaming else models[0]
        return chosen.model_id

