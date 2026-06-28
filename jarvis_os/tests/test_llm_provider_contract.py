"""
Contract Tests for LLMProvider Port — Milestone 6A.

Verifies the abstract interface, value objects, streaming contract,
exception hierarchy, async contract, and backward compatibility with
the frozen LLMPort.

No concrete providers are instantiated. All tests use minimal in-test
mock implementations that satisfy the abstract interface.
"""
from __future__ import annotations

import asyncio
import threading
import time
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import AsyncIterator, Iterator, List, Optional

from jarvis_os.core.domain.entities import LLMMessage, LLMResponse
from jarvis_os.core.domain.exceptions import LLMException
from jarvis_os.core.ports.llm import LLMPort
from jarvis_os.core.ports.llm_provider import (
    GenerationOptions,
    LLMCancelledError,
    LLMModelNotFoundError,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMRequestValidationError,
    LLMTimeoutError,
    ModelCapability,
    ModelInfo,
    StreamingResponse,
)


# ---------------------------------------------------------------------------
# Helpers — minimal mock implementations used only within this test module
# ---------------------------------------------------------------------------

def _make_message(content: str = "hello", role: str = "user") -> LLMMessage:
    return LLMMessage(role=role, content=content, timestamp=datetime.now())


def _make_request(
    model_id: str = "test-model",
    content: str = "hello",
    options: Optional[GenerationOptions] = None,
) -> LLMRequest:
    return LLMRequest(
        model_id=model_id,
        messages=[_make_message(content)],
        options=options or GenerationOptions(),
    )


class _FakeStreamingResponse(StreamingResponse):
    """Minimal streaming response for contract validation."""

    def __init__(self, tokens: List[str]) -> None:
        self._tokens = tokens
        self._cancelled = False
        self._complete = False

    def __iter__(self) -> Iterator[str]:
        for token in self._tokens:
            if self._cancelled:
                raise LLMCancelledError("Stream cancelled by caller.")
            yield token
        self._complete = True

    def cancel(self) -> None:
        self._cancelled = True

    def is_complete(self) -> bool:
        return self._complete


class _ConcreteProvider(LLMProvider):
    """Minimal concrete provider satisfying all abstract methods."""

    KNOWN_MODEL = ModelInfo(
        model_id="test-model",
        display_name="Test Model",
        context_window=4096,
        capabilities=[ModelCapability.CHAT_COMPLETION, ModelCapability.STREAMING],
        max_output_tokens=512,
    )

    @property
    def provider_name(self) -> str:
        return "TestProvider"

    def get_models(self) -> List[ModelInfo]:
        return [self.KNOWN_MODEL]

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.model_id not in [m.model_id for m in self.get_models()]:
            raise LLMModelNotFoundError(request.model_id, self.provider_name)
        return LLMResponse(
            content="generated response",
            token_usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            model_name=request.model_id,
            elapsed_seconds=0.1,
        )

    def generate_stream(self, request: LLMRequest) -> StreamingResponse:
        if request.model_id not in [m.model_id for m in self.get_models()]:
            raise LLMModelNotFoundError(request.model_id, self.provider_name)
        return _FakeStreamingResponse(["Hello", " World", "!"])

    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        await asyncio.sleep(0)  # yield control — simulates async I/O
        return self.generate(request)

    async def generate_stream_async(self, request: LLMRequest) -> AsyncIterator[str]:
        for token in ["Async", " token", " stream"]:
            await asyncio.sleep(0)
            yield token


class _TimeoutProvider(_ConcreteProvider):
    """Provider that always raises LLMTimeoutError."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMTimeoutError("Inference timed out after 30s")

    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        raise LLMTimeoutError("Async inference timed out")


class _ValidationFailProvider(_ConcreteProvider):
    """Provider that always raises LLMRequestValidationError."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMRequestValidationError("Model does not support text-only prompts")


class _UnreachableProvider(_ConcreteProvider):
    """Provider that is always unreachable."""

    def get_models(self) -> List[ModelInfo]:
        raise LLMProviderError("Connection refused — provider unreachable")

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderError("Provider unreachable")

    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderError("Provider unreachable (async)")


# ---------------------------------------------------------------------------
# 1. Abstract Enforcement Tests
# ---------------------------------------------------------------------------

class TestLLMProviderAbstractEnforcement(unittest.TestCase):
    """Verify the interface cannot be used without full implementation."""

    def test_cannot_instantiate_llm_provider_directly(self):
        with self.assertRaises(TypeError):
            LLMProvider()  # type: ignore

    def test_cannot_instantiate_streaming_response_directly(self):
        with self.assertRaises(TypeError):
            StreamingResponse()  # type: ignore

    def test_partial_implementation_raises_type_error(self):
        class PartialProvider(LLMProvider):
            @property
            def provider_name(self) -> str:
                return "partial"
            # Missing: get_models, generate, generate_stream, generate_async,
            #          generate_stream_async

        with self.assertRaises(TypeError):
            PartialProvider()  # type: ignore

    def test_full_implementation_can_be_instantiated(self):
        provider = _ConcreteProvider()
        self.assertIsInstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# 2. ModelCapability Tests
# ---------------------------------------------------------------------------

class TestModelCapability(unittest.TestCase):
    """Verify the capability enum values and iteration."""

    def test_all_expected_capabilities_present(self):
        names = {cap.value for cap in ModelCapability}
        self.assertIn("chat_completion", names)
        self.assertIn("text_completion", names)
        self.assertIn("embeddings", names)
        self.assertIn("vision", names)
        self.assertIn("function_calling", names)
        self.assertIn("streaming", names)
        self.assertIn("code", names)

    def test_capability_identity(self):
        self.assertEqual(ModelCapability.CHAT_COMPLETION, ModelCapability.CHAT_COMPLETION)
        self.assertNotEqual(ModelCapability.CHAT_COMPLETION, ModelCapability.EMBEDDINGS)


# ---------------------------------------------------------------------------
# 3. ModelInfo Tests
# ---------------------------------------------------------------------------

class TestModelInfo(unittest.TestCase):
    """Verify ModelInfo dataclass contract."""

    def test_minimal_construction(self):
        info = ModelInfo(
            model_id="llama3:8b",
            display_name="Llama 3 8B",
            context_window=8192,
        )
        self.assertEqual(info.model_id, "llama3:8b")
        self.assertEqual(info.context_window, 8192)
        self.assertEqual(info.capabilities, [])
        self.assertIsNone(info.max_output_tokens)
        self.assertEqual(info.description, "")

    def test_full_construction(self):
        info = ModelInfo(
            model_id="gpt-4",
            display_name="GPT-4",
            context_window=128_000,
            capabilities=[ModelCapability.CHAT_COMPLETION, ModelCapability.VISION],
            max_output_tokens=4096,
            description="OpenAI flagship model",
        )
        self.assertIn(ModelCapability.VISION, info.capabilities)
        self.assertEqual(info.max_output_tokens, 4096)

    def test_model_info_is_immutable(self):
        info = ModelInfo(
            model_id="m",
            display_name="M",
            context_window=1024,
        )
        with self.assertRaises(FrozenInstanceError):
            info.model_id = "mutated"  # type: ignore

    def test_model_info_equality(self):
        a = ModelInfo(model_id="x", display_name="X", context_window=512)
        b = ModelInfo(model_id="x", display_name="X", context_window=512)
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# 4. GenerationOptions Tests
# ---------------------------------------------------------------------------

class TestGenerationOptions(unittest.TestCase):
    """Verify GenerationOptions dataclass defaults and immutability."""

    def test_default_values(self):
        opts = GenerationOptions()
        self.assertAlmostEqual(opts.temperature, 0.7)
        self.assertAlmostEqual(opts.top_p, 0.9)
        self.assertEqual(opts.top_k, 40)
        self.assertEqual(opts.max_tokens, 512)
        self.assertEqual(opts.stop_sequences, [])
        self.assertAlmostEqual(opts.timeout_seconds, 30.0)
        self.assertIsNone(opts.seed)

    def test_custom_values(self):
        opts = GenerationOptions(
            temperature=0.2,
            top_p=0.95,
            top_k=10,
            max_tokens=256,
            stop_sequences=["<end>", "\n\n"],
            timeout_seconds=60.0,
            seed=42,
        )
        self.assertAlmostEqual(opts.temperature, 0.2)
        self.assertEqual(opts.stop_sequences, ["<end>", "\n\n"])
        self.assertEqual(opts.seed, 42)

    def test_generation_options_is_immutable(self):
        opts = GenerationOptions()
        with self.assertRaises(FrozenInstanceError):
            opts.temperature = 1.0  # type: ignore


# ---------------------------------------------------------------------------
# 5. LLMRequest Tests
# ---------------------------------------------------------------------------

class TestLLMRequest(unittest.TestCase):
    """Verify LLMRequest construction and validation."""

    def test_valid_request(self):
        req = _make_request()
        self.assertEqual(req.model_id, "test-model")
        self.assertEqual(len(req.messages), 1)
        self.assertIsInstance(req.options, GenerationOptions)

    def test_empty_model_id_raises_validation_error(self):
        with self.assertRaises(LLMRequestValidationError):
            LLMRequest(model_id="", messages=[_make_message()])

    def test_whitespace_model_id_raises_validation_error(self):
        with self.assertRaises(LLMRequestValidationError):
            LLMRequest(model_id="   ", messages=[_make_message()])

    def test_empty_messages_raises_validation_error(self):
        with self.assertRaises(LLMRequestValidationError):
            LLMRequest(model_id="test-model", messages=[])

    def test_llm_request_is_immutable(self):
        req = _make_request()
        with self.assertRaises(FrozenInstanceError):
            req.model_id = "mutated"  # type: ignore

    def test_request_reuses_existing_llm_message(self):
        """LLMRequest must accept the existing domain LLMMessage entity."""
        msg = LLMMessage(role="system", content="You are Jarvis.")
        req = LLMRequest(model_id="test-model", messages=[msg])
        self.assertIsInstance(req.messages[0], LLMMessage)

    def test_request_with_custom_options(self):
        opts = GenerationOptions(temperature=0.1, max_tokens=100)
        req = LLMRequest(
            model_id="test-model",
            messages=[_make_message()],
            options=opts,
        )
        self.assertAlmostEqual(req.options.temperature, 0.1)

    def test_multi_message_conversation(self):
        messages = [
            LLMMessage(role="system", content="You are Jarvis."),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi, I am Jarvis."),
            LLMMessage(role="user", content="What can you do?"),
        ]
        req = LLMRequest(model_id="test-model", messages=messages)
        self.assertEqual(len(req.messages), 4)


# ---------------------------------------------------------------------------
# 6. Provider Metadata Tests
# ---------------------------------------------------------------------------

class TestProviderMetadata(unittest.TestCase):
    """Verify provider identity and model discovery contracts."""

    def setUp(self):
        self.provider = _ConcreteProvider()

    def test_provider_name_is_string(self):
        self.assertIsInstance(self.provider.provider_name, str)
        self.assertGreater(len(self.provider.provider_name), 0)

    def test_get_models_returns_list(self):
        models = self.provider.get_models()
        self.assertIsInstance(models, list)

    def test_get_models_contains_model_info_instances(self):
        models = self.provider.get_models()
        for model in models:
            self.assertIsInstance(model, ModelInfo)

    def test_unreachable_provider_get_models_raises_provider_error(self):
        provider = _UnreachableProvider()
        with self.assertRaises(LLMProviderError):
            provider.get_models()

    def test_model_info_context_window_positive(self):
        for model in self.provider.get_models():
            self.assertGreater(model.context_window, 0)


# ---------------------------------------------------------------------------
# 7. Synchronous Generation Tests
# ---------------------------------------------------------------------------

class TestSynchronousGeneration(unittest.TestCase):
    """Verify generate() method contract."""

    def setUp(self):
        self.provider = _ConcreteProvider()

    def test_generate_returns_llm_response(self):
        """generate() must return the existing domain LLMResponse entity."""
        req = _make_request()
        result = self.provider.generate(req)
        self.assertIsInstance(result, LLMResponse)

    def test_generate_response_has_content(self):
        req = _make_request()
        result = self.provider.generate(req)
        self.assertIsInstance(result.content, str)
        self.assertGreater(len(result.content), 0)

    def test_generate_response_has_model_name(self):
        req = _make_request()
        result = self.provider.generate(req)
        self.assertEqual(result.model_name, req.model_id)

    def test_generate_response_has_token_usage(self):
        req = _make_request()
        result = self.provider.generate(req)
        self.assertIsInstance(result.token_usage, dict)

    def test_generate_response_has_elapsed_seconds(self):
        req = _make_request()
        result = self.provider.generate(req)
        self.assertGreaterEqual(result.elapsed_seconds, 0.0)

    def test_generate_unknown_model_raises_model_not_found(self):
        req = _make_request(model_id="nonexistent-model")
        with self.assertRaises(LLMModelNotFoundError) as ctx:
            self.provider.generate(req)
        self.assertIn("nonexistent-model", str(ctx.exception))

    def test_generate_timeout_raises_timeout_error(self):
        provider = _TimeoutProvider()
        req = _make_request()
        with self.assertRaises(LLMTimeoutError):
            provider.generate(req)

    def test_generate_validation_failure_raises_validation_error(self):
        provider = _ValidationFailProvider()
        req = _make_request()
        with self.assertRaises(LLMRequestValidationError):
            provider.generate(req)

    def test_provider_error_is_subclass_of_llm_exception(self):
        """Backward-compatibility: existing code catching LLMException still works."""
        provider = _UnreachableProvider()
        req = _make_request()
        with self.assertRaises(LLMException):  # intentionally broad catch
            provider.generate(req)

    def test_timeout_error_is_subclass_of_provider_error(self):
        self.assertTrue(issubclass(LLMTimeoutError, LLMProviderError))

    def test_cancelled_error_is_subclass_of_provider_error(self):
        self.assertTrue(issubclass(LLMCancelledError, LLMProviderError))

    def test_validation_error_is_subclass_of_provider_error(self):
        self.assertTrue(issubclass(LLMRequestValidationError, LLMProviderError))

    def test_model_not_found_error_is_subclass_of_provider_error(self):
        self.assertTrue(issubclass(LLMModelNotFoundError, LLMProviderError))

    def test_all_provider_errors_are_subclass_of_llm_exception(self):
        """All new errors must be catchable by code catching the original LLMException."""
        for cls in (
            LLMProviderError,
            LLMTimeoutError,
            LLMCancelledError,
            LLMRequestValidationError,
            LLMModelNotFoundError,
        ):
            self.assertTrue(issubclass(cls, LLMException), f"{cls.__name__} not subclass of LLMException")


# ---------------------------------------------------------------------------
# 8. Streaming Generation Tests
# ---------------------------------------------------------------------------

class TestStreamingGeneration(unittest.TestCase):
    """Verify generate_stream() and StreamingResponse contract."""

    def setUp(self):
        self.provider = _ConcreteProvider()

    def test_generate_stream_returns_streaming_response(self):
        req = _make_request()
        result = self.provider.generate_stream(req)
        self.assertIsInstance(result, StreamingResponse)

    def test_streaming_response_is_iterable(self):
        req = _make_request()
        stream = self.provider.generate_stream(req)
        tokens = list(stream)
        self.assertGreater(len(tokens), 0)
        for token in tokens:
            self.assertIsInstance(token, str)

    def test_streaming_response_complete_after_full_iteration(self):
        req = _make_request()
        stream = self.provider.generate_stream(req)
        _ = list(stream)
        self.assertTrue(stream.is_complete())

    def test_streaming_response_not_complete_before_iteration(self):
        req = _make_request()
        stream = self.provider.generate_stream(req)
        self.assertFalse(stream.is_complete())

    def test_streaming_cancel_stops_iteration(self):
        req = _make_request()
        stream = self.provider.generate_stream(req)
        iterator = iter(stream)
        next(iterator)          # consume first token
        stream.cancel()
        with self.assertRaises(LLMCancelledError):
            next(iterator)      # next call must raise after cancel

    def test_streaming_unknown_model_raises_model_not_found(self):
        req = _make_request(model_id="unknown-stream-model")
        with self.assertRaises(LLMModelNotFoundError):
            self.provider.generate_stream(req)

    def test_streaming_concatenated_tokens_form_coherent_output(self):
        req = _make_request()
        stream = self.provider.generate_stream(req)
        combined = "".join(stream)
        self.assertEqual(combined, "Hello World!")


# ---------------------------------------------------------------------------
# 9. Async Generation Tests
# ---------------------------------------------------------------------------

class TestAsyncGeneration(unittest.TestCase):
    """Verify async generate contracts via asyncio.run()."""

    def setUp(self):
        self.provider = _ConcreteProvider()

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_generate_async_returns_llm_response(self):
        req = _make_request()
        result = self._run(self.provider.generate_async(req))
        self.assertIsInstance(result, LLMResponse)

    def test_generate_async_content_non_empty(self):
        req = _make_request()
        result = self._run(self.provider.generate_async(req))
        self.assertGreater(len(result.content), 0)

    def test_generate_async_timeout_raises_timeout_error(self):
        provider = _TimeoutProvider()
        req = _make_request()
        with self.assertRaises(LLMTimeoutError):
            self._run(provider.generate_async(req))

    def test_generate_async_unreachable_raises_provider_error(self):
        provider = _UnreachableProvider()
        req = _make_request()
        with self.assertRaises(LLMProviderError):
            self._run(provider.generate_async(req))

    def test_generate_stream_async_yields_strings(self):
        req = _make_request()

        async def collect():
            tokens = []
            async for token in self.provider.generate_stream_async(req):
                tokens.append(token)
            return tokens

        tokens = self._run(collect())
        self.assertGreater(len(tokens), 0)
        for token in tokens:
            self.assertIsInstance(token, str)

    def test_generate_stream_async_produces_coherent_output(self):
        req = _make_request()

        async def collect():
            parts = []
            async for token in self.provider.generate_stream_async(req):
                parts.append(token)
            return "".join(parts)

        result = self._run(collect())
        self.assertEqual(result, "Async token stream")


# ---------------------------------------------------------------------------
# 10. LLMModelNotFoundError Tests
# ---------------------------------------------------------------------------

class TestLLMModelNotFoundError(unittest.TestCase):
    """Verify the structured model-not-found error contract."""

    def test_error_stores_model_id(self):
        err = LLMModelNotFoundError("llama3:70b")
        self.assertEqual(err.model_id, "llama3:70b")

    def test_error_stores_provider_name(self):
        err = LLMModelNotFoundError("llama3:70b", "Ollama")
        self.assertEqual(err.provider_name, "Ollama")

    def test_error_message_contains_model_id(self):
        err = LLMModelNotFoundError("some-model", "TestProvider")
        self.assertIn("some-model", str(err))
        self.assertIn("TestProvider", str(err))

    def test_error_without_provider_name(self):
        err = LLMModelNotFoundError("my-model")
        self.assertIn("my-model", str(err))
        self.assertEqual(err.provider_name, "")


# ---------------------------------------------------------------------------
# 11. Backward Compatibility Tests
# ---------------------------------------------------------------------------

class TestBackwardCompatibility(unittest.TestCase):
    """Verify Milestone 6A does not break any existing frozen contracts."""

    def test_llm_port_is_still_importable(self):
        from jarvis_os.core.ports.llm import LLMPort
        self.assertTrue(issubclass(LLMPort, object))

    def test_llm_port_generate_signature_preserved(self):
        import inspect
        from jarvis_os.core.ports.llm import LLMPort
        sig = inspect.signature(LLMPort.generate)
        params = list(sig.parameters.keys())
        self.assertIn("prompt", params)
        self.assertIn("options", params)

    def test_llm_port_chat_signature_preserved(self):
        import inspect
        from jarvis_os.core.ports.llm import LLMPort
        sig = inspect.signature(LLMPort.chat)
        params = list(sig.parameters.keys())
        self.assertIn("messages", params)
        self.assertIn("options", params)

    def test_llm_port_embed_signature_preserved(self):
        import inspect
        from jarvis_os.core.ports.llm import LLMPort
        sig = inspect.signature(LLMPort.embed)
        params = list(sig.parameters.keys())
        self.assertIn("text", params)

    def test_llm_response_fields_unchanged(self):
        resp = LLMResponse(
            content="hello",
            token_usage={"total": 5},
            model_name="test",
            elapsed_seconds=0.5,
        )
        self.assertEqual(resp.content, "hello")
        self.assertEqual(resp.model_name, "test")

    def test_llm_message_fields_unchanged(self):
        msg = LLMMessage(role="user", content="hi")
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "hi")

    def test_llm_exception_still_catchable(self):
        """LLMException from exceptions.py must not be shadowed."""
        with self.assertRaises(LLMException):
            raise LLMProviderError("test")

    def test_llm_port_and_llm_provider_are_independent(self):
        """The two interfaces must not share an inheritance relationship."""
        self.assertFalse(issubclass(LLMProvider, LLMPort))
        self.assertFalse(issubclass(LLMPort, LLMProvider))


# ---------------------------------------------------------------------------
# 12. Thread Safety Tests
# ---------------------------------------------------------------------------

class TestLLMProviderThreadSafety(unittest.TestCase):
    """Verify that multiple threads can safely call a provider concurrently."""

    def test_concurrent_generate_calls(self):
        provider = _ConcreteProvider()
        results = []
        errors = []

        def worker():
            try:
                req = _make_request(content=f"thread-{threading.current_thread().name}")
                result = provider.generate(req)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 20)

    def test_concurrent_get_models_calls(self):
        provider = _ConcreteProvider()
        results = []

        def worker():
            results.append(provider.get_models())

        threads = [threading.Thread(target=worker) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 15)
        for models in results:
            self.assertIsInstance(models, list)


# ---------------------------------------------------------------------------
# 13. Ports Package Export Tests
# ---------------------------------------------------------------------------

class TestPortsPackageExports(unittest.TestCase):
    """Verify all Milestone 6A symbols are exported from the ports package."""

    def test_model_capability_exported(self):
        from jarvis_os.core.ports import ModelCapability
        self.assertTrue(issubclass(ModelCapability, object))

    def test_model_info_exported(self):
        from jarvis_os.core.ports import ModelInfo
        self.assertTrue(issubclass(ModelInfo, object))

    def test_generation_options_exported(self):
        from jarvis_os.core.ports import GenerationOptions
        self.assertTrue(issubclass(GenerationOptions, object))

    def test_llm_request_exported(self):
        from jarvis_os.core.ports import LLMRequest
        self.assertTrue(issubclass(LLMRequest, object))

    def test_streaming_response_exported(self):
        from jarvis_os.core.ports import StreamingResponse
        self.assertTrue(issubclass(StreamingResponse, object))

    def test_llm_provider_exported(self):
        from jarvis_os.core.ports import LLMProvider
        self.assertTrue(issubclass(LLMProvider, object))

    def test_llm_provider_error_exported(self):
        from jarvis_os.core.ports import LLMProviderError
        self.assertTrue(issubclass(LLMProviderError, LLMException))

    def test_llm_timeout_error_exported(self):
        from jarvis_os.core.ports import LLMTimeoutError
        self.assertTrue(issubclass(LLMTimeoutError, LLMException))

    def test_llm_cancelled_error_exported(self):
        from jarvis_os.core.ports import LLMCancelledError
        self.assertTrue(issubclass(LLMCancelledError, LLMException))

    def test_llm_request_validation_error_exported(self):
        from jarvis_os.core.ports import LLMRequestValidationError
        self.assertTrue(issubclass(LLMRequestValidationError, LLMException))

    def test_llm_model_not_found_error_exported(self):
        from jarvis_os.core.ports import LLMModelNotFoundError
        self.assertTrue(issubclass(LLMModelNotFoundError, LLMException))

    def test_frozen_llm_port_still_exported(self):
        """The frozen LLMPort must remain accessible from the ports package."""
        from jarvis_os.core.ports import LLMPort
        self.assertTrue(issubclass(LLMPort, object))


if __name__ == "__main__":
    unittest.main()
