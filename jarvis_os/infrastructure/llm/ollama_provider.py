"""Ollama adapter implementing the LLMProvider contract (Milestone 6B)."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterator, List, Optional


from jarvis_os.core.domain.entities import LLMMessage, LLMResponse
from jarvis_os.core.ports.llm_provider import (
    GenerationOptions,
    LLMProvider,
    LLMRequest,
    LLMRequestValidationError,
    LLMModelNotFoundError,
    LLMTimeoutError,
    ModelCapability,
    ModelInfo,
    StreamingResponse,
)

from jarvis_os.core.domain.exceptions import LLMException

from .error_mapping import map_ollama_error
from .ollama_http_client import OllamaHTTPClient, OllamaHTTPConfig
from .streaming_response import SyncStreamingResponse


# NOTE: We reuse SyncStreamingResponse from streaming_response.py



class OllamaProvider(LLMProvider):
    def __init__(
        self,
        http_client: Optional[OllamaHTTPClient] = None,
        config: Optional[OllamaHTTPConfig] = None,
        provider_name: str = "Ollama",
    ) -> None:
        self._provider_name = provider_name
        self._config = config or OllamaHTTPConfig()
        self._http = http_client or OllamaHTTPClient(self._config)

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def get_models(self) -> List[ModelInfo]:
        try:
            raw = self._http.list_models()
        except BaseException as exc:
            raise map_ollama_error(exc)

        models: List[ModelInfo] = []
        tags = raw.get("models") or []
        for t in tags:
            model_id = t.get("name") or t.get("model") or ""
            if not model_id:
                continue

            # Ollama capabilities are inferred based on known endpoints.
            caps = [
                ModelCapability.TEXT_COMPLETION,
                ModelCapability.CHAT_COMPLETION,
                ModelCapability.STREAMING,
            ]
            # Embeddings support if server exposes embeddings endpoint.
            caps.append(ModelCapability.EMBEDDINGS)

            models.append(
                ModelInfo(
                    model_id=model_id,
                    display_name=model_id,
                    context_window=int(t.get("details", {}).get("parameter_size", 4096))
                    if isinstance(t.get("details", {}), dict)
                    else 4096,
                    capabilities=caps,
                    max_output_tokens=None,
                    description=t.get("description", ""),
                )
            )
        return models

    def _validate_request(self, request: LLMRequest, require_streaming: bool = False) -> None:
        if not request.messages:
            raise LLMRequestValidationError("LLMRequest.messages must not be empty")

        models = {m.model_id: m for m in self.get_models()}
        if request.model_id not in models:
            raise LLMModelNotFoundError(request.model_id, self.provider_name)

        if require_streaming and ModelCapability.STREAMING not in models[request.model_id].capabilities:
            raise LLMRequestValidationError("Model does not support streaming")

    def _to_ollama_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        # Ollama expects list of {role, content}
        out: List[Dict[str, Any]] = []
        for m in messages:
            if not m.content:
                continue
            out.append({"role": m.role, "content": m.content})
        if not out:
            raise LLMRequestValidationError("All messages are empty")
        return out

    def generate(self, request: LLMRequest) -> LLMResponse:
        self._validate_request(request, require_streaming=False)
        opts = request.options or GenerationOptions()

        payload: Dict[str, Any] = {
            "model": request.model_id,
            "messages": self._to_ollama_messages(request.messages),
            "stream": False,
            "options": {
                "temperature": opts.temperature,
                "top_p": opts.top_p,
                "top_k": opts.top_k,
                "num_predict": opts.max_tokens,
            },
        }
        if opts.stop_sequences:
            payload["options"]["stop"] = opts.stop_sequences
        if opts.seed is not None:
            payload["options"]["seed"] = opts.seed

        start = time.time()
        try:
            raw = self._http.generate(payload, stream=False)
        except BaseException as exc:
            mapped = map_ollama_error(exc)
            raise mapped

        content = raw.get("response") or ""
        if content is None:
            content = ""

        token_usage = raw.get("context") and raw.get("eval_count")
        # Ollama may provide token counts under different keys; best-effort mapping.
        token_usage_dict: Dict[str, int] = {}
        for key, out_key in [
            ("prompt_eval_count", "prompt_tokens"),
            ("eval_count", "completion_tokens"),
        ]:
            if key in raw and isinstance(raw[key], int):
                token_usage_dict[out_key] = raw[key]
        if "prompt_tokens" in token_usage_dict and "completion_tokens" in token_usage_dict:
            token_usage_dict["total_tokens"] = (
                token_usage_dict["prompt_tokens"] + token_usage_dict["completion_tokens"]
            )

        return LLMResponse(
            content=str(content),
            token_usage=token_usage_dict,
            model_name=request.model_id,
            elapsed_seconds=max(0.0, time.time() - start),
        )

    def generate_stream(self, request: LLMRequest) -> StreamingResponse:
        self._validate_request(request, require_streaming=True)
        opts = request.options or GenerationOptions()

        payload: Dict[str, Any] = {
            "model": request.model_id,
            "messages": self._to_ollama_messages(request.messages),
            "stream": True,
            "options": {
                "temperature": opts.temperature,
                "top_p": opts.top_p,
                "top_k": opts.top_k,
                "num_predict": opts.max_tokens,
            },
        }
        if opts.stop_sequences:
            payload["options"]["stop"] = opts.stop_sequences
        if opts.seed is not None:
            payload["options"]["seed"] = opts.seed

        def iter_factory(cancel_event) -> Iterator[str]:
            # Implement cancellation by breaking once cancel_event is set.
            # Ollama streaming iterator does not support HTTP cancellation here,
            # so we stop yielding when cancelled.
            try:
                for chunk in self._http.generate(payload, stream=True):
                    if cancel_event.is_set():
                        break
                    if not isinstance(chunk, dict):
                        continue
                    if "response" in chunk and chunk["response"] is not None:
                        yield str(chunk["response"])
            except BaseException as exc:
                raise map_ollama_error(exc)

        # timeout handling: rely on http client timeout.
        return SyncStreamingResponse(iter_factory)


    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        # Keep it simple: delegate to sync method in a thread.
        # No additional dependency (async http).
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate, request)

    async def generate_stream_async(self, request: LLMRequest):
        import asyncio

        # Use sync streaming iterator in a thread, then yield tokens.
        stream = self.generate_stream(request)

        async def gen():
            for token in stream:
                yield token
                await asyncio.sleep(0)  # cooperative scheduling

        return gen()

