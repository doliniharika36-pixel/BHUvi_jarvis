"""
Bootstrap script to wire together the Jarvis OS architecture and launch the Voice Pipeline.
"""
from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
from datetime import datetime
from typing import Any, AsyncIterator, List, Optional
from uuid import uuid4

from jarvis_os.core.context.context_builder import ContextBuilder
from jarvis_os.core.context.models import ContextPriority, ContextSection
from jarvis_os.core.context.token_budget import ContextBudget
from jarvis_os.core.conversation.conversation_manager import ConversationManager
from jarvis_os.core.decision.decision_engine import DecisionEngine
from jarvis_os.core.decision.models import DecisionContext
from jarvis_os.core.domain.entities import LLMMessage, LLMResponse
from jarvis_os.core.memory.memory_manager import MemoryManager
from jarvis_os.core.memory.models import MemoryRecord, MemoryType
from jarvis_os.core.ports.llm_provider import (
    LLMProvider,
    LLMRequest,
    ModelCapability,
    ModelInfo,
    StreamingResponse,
)
from jarvis_os.core.ports.repository import RepositoryPort
from jarvis_os.core.retrieval.models import RetrievalRequest
from jarvis_os.core.retrieval.retriever import Retriever
from jarvis_os.core.services.llm_service import LLMService
from jarvis_os.core.voice.exceptions import SpeechRecognitionException
from jarvis_os.core.voice.models import VoiceRequest
from jarvis_os.core.voice.voice_pipeline import VoicePipeline
from jarvis_os.infrastructure.llm.ollama_http_client import OllamaHTTPClient, OllamaHTTPConfig
from jarvis_os.infrastructure.llm.ollama_provider import OllamaProvider
from jarvis_os.infrastructure.voice.google_speech_adapter import GoogleSpeechAdapter
from jarvis_os.infrastructure.voice.pyttsx3_adapter import Pyttsx3Adapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("jarvis_bootstrap")


MENU_WIDTH = 60


class InMemoryMemoryRepository(RepositoryPort[MemoryRecord]):
    """Clean in-memory implementation of the MemoryRecord repository port."""

    def __init__(self) -> None:
        self._store = {}

    def save(self, entity: MemoryRecord) -> None:
        self._store[entity.id] = entity

    def get_by_id(self, entity_id: str) -> Optional[MemoryRecord]:
        return self._store.get(entity_id)

    def delete(self, entity_id: str) -> None:
        self._store.pop(entity_id, None)

    def list_all(self) -> List[MemoryRecord]:
        return list(self._store.values())


class MockLLMProvider(LLMProvider):
    """Fallback LLMProvider used if Ollama is unavailable or mock mode is requested."""

    @property
    def provider_name(self) -> str:
        return "MockLLM"

    def get_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(
                model_id="mock-llama-3",
                display_name="Mock Llama 3 Model",
                context_window=4096,
                capabilities=[ModelCapability.CHAT_COMPLETION, ModelCapability.STREAMING],
            )
        ]

    def generate(self, request: LLMRequest) -> LLMResponse:
        user_message = request.messages[-1].content.lower()
        if "hello" in user_message or "hi" in user_message:
            reply = "Hello! I am Jarvis, your voice assistant. How can I help you today?"
        elif "joke" in user_message:
            reply = "Why did the compiler catch a cold? Because it had too many open windows!"
        elif "your name" in user_message:
            reply = "My name is Jarvis OS."
        else:
            reply = f"I am running in offline demonstration mode. You said: '{request.messages[-1].content}'"

        return LLMResponse(
            content=reply,
            model_name="mock-llama-3",
            elapsed_seconds=0.05,
        )

    def generate_stream(self, request: LLMRequest) -> StreamingResponse:
        raise NotImplementedError()

    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        return self.generate(request)

    async def generate_stream_async(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError()


class BootstrapDecisionAdapter:
    """Adapts ConversationManager bootstrap calls to DecisionEngine's typed contract."""

    def __init__(self, decision_engine: DecisionEngine) -> None:
        self._decision_engine = decision_engine

    def decide(self, message: Any, history: list[Any]) -> Any:
        request_text = getattr(message, "content", str(message))
        return self._decision_engine.decide(DecisionContext(request_text=request_text))


class BootstrapRetrieverAdapter:
    """Adapts text queries into RetrievalRequest and prompt-ready context sections."""

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    def retrieve(self, query: str) -> tuple[ContextSection, ...]:
        result = self._retriever.retrieve(RetrievalRequest(query_text=query))
        return tuple(
            ContextSection(
                name=f"memory:{record.id}",
                priority=ContextPriority.MEMORY,
                content=record.content,
                metadata=record.metadata,
            )
            for record in result.records
        )


class BootstrapLLMServiceAdapter:
    """Exposes the generate(prompt=...) shape expected by the bootstrap conversation path."""

    def __init__(self, llm_service: LLMService) -> None:
        self._llm_service = llm_service

    def generate(self, prompt: Any) -> str:
        if hasattr(prompt, "prompt_messages"):
            prompt_text = "\n".join(content for _, content in prompt.prompt_messages)
        else:
            prompt_text = str(prompt)
        return self._llm_service.complete(prompt_text).content


class BootstrapMemoryAdapter:
    """Exposes store_memory while preserving MemoryManager's existing create contract."""

    def __init__(self, memory_manager: MemoryManager) -> None:
        self._memory_manager = memory_manager

    def store_memory(self, session_id: str, message: Any) -> None:
        self._memory_manager.create(
            MemoryRecord(
                id=f"{session_id}:{uuid4()}",
                content=getattr(message, "content", str(message)),
                memory_type=MemoryType.CONVERSATION,
                created_at=getattr(message, "timestamp", datetime.now()),
                metadata={"session_id": session_id, "role": getattr(message, "role", "")},
            )
        )


def check_ollama_status(client: OllamaHTTPClient) -> bool:
    """Verifies if the local Ollama server is running and accessible."""
    try:
        client.list_models()
        return True
    except Exception:
        return False


def print_startup_menu() -> None:
    print("=" * 60)
    print("                BHUvi Personal AI Assistant")
    print("=" * 60)
    print()
    print("Select interaction mode:")
    print()
    print("1. Voice Mode")
    print("2. Text Mode")
    print("3. Exit")
    print()


def build_conversation_manager(provider: LLMProvider) -> ConversationManager:
    repo = InMemoryMemoryRepository()

    seed_memory = MemoryRecord(
        id="sys_init",
        content="Jarvis OS voice system initialized.",
        memory_type=MemoryType.SYSTEM,
        created_at=datetime.now(),
    )
    repo.save(seed_memory)

    memory_manager = BootstrapMemoryAdapter(MemoryManager(repo))
    retriever = BootstrapRetrieverAdapter(Retriever(repo))
    context_budget = ContextBudget(max_prompt_tokens=2048)
    context_builder = ContextBuilder(
        system_prompt="You are Jarvis, a highly intelligent and polite AI assistant.",
        budget=context_budget,
    )
    decision_engine = BootstrapDecisionAdapter(DecisionEngine())
    llm_service = BootstrapLLMServiceAdapter(LLMService(provider=provider))

    return ConversationManager(
        decision_engine=decision_engine,
        retriever=retriever,
        context_builder=context_builder,
        llm_service=llm_service,
        memory_manager=memory_manager,
    )


def resolve_llm_provider(args: argparse.Namespace) -> Optional[LLMProvider]:
    ollama_config = OllamaHTTPConfig()
    ollama_client = OllamaHTTPClient(ollama_config)

    if args.mock_llm:
        return MockLLMProvider()

    if not check_ollama_status(ollama_client):
        print("[ERROR] Ollama server is unavailable.")
        return None

    return OllamaProvider(http_client=ollama_client, config=ollama_config)


def run_voice_mode(conversation_manager: ConversationManager) -> None:
    print("[1/2] Loading vocal hardware adapters (STT & TTS)...")
    stt = GoogleSpeechAdapter()
    tts = Pyttsx3Adapter()

    print("[2/2] Assembling Voice Pipeline...")
    voice_pipeline = VoicePipeline(
        stt=stt,
        tts=tts,
        conversation_manager=conversation_manager,
    )

    print("-" * 60)
    print("System setup complete. Starting interaction loop...")
    print("-" * 60)

    try:
        voice_pipeline.start_interaction_loop()
        print("Voice listening initialized. Speak into your microphone.")
        print("Press Ctrl+C to stop the pipeline.")
        print("=" * 60)

        # Run background listening capture loop
        while True:
            try:
                # Retrieve audio from Google STT adapter queue
                audio_data = stt.audio_queue.get(timeout=1.0)
                print("\n[Vocal Input Detected] Transcribing...")
                
                req = VoiceRequest(audio_data=audio_data)
                response = voice_pipeline.process_voice_input(req)
                
                print(f"  User:   {response.input_text}")
                print(f"  Jarvis: {response.output_text}")
                
            except queue.Empty:
                continue
            except SpeechRecognitionException as exc:
                print(f"\n[STT Error] {exc}")
            except Exception as exc:
                print(f"\n[Pipeline Error] {exc}")

    except KeyboardInterrupt:
        print("\n\nExiting interaction loop (User KeyboardInterrupt)...")
    except SpeechRecognitionException as exc:
        print(f"\n[Fatal STT Setup Error] {exc}")
        print("  -> Make sure a default input device is configured and PyAudio is active.")
        print("  -> Switching to Keyboard Text input fallback mode.")
        run_keyboard_fallback(conversation_manager)
    except Exception as exc:
        print(f"\n[Fatal Initialization Error] {exc}")
    finally:
        print("Shutting down Voice Pipeline...")
        try:
            voice_pipeline.stop_interaction_loop()
        except Exception:
            pass
        print("Done.")


def clear_terminal() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def run_text_mode(
    conversation_manager: ConversationManager,
    input_func=input,
    output_func=print,
    clear_func=clear_terminal,
) -> None:
    session = conversation_manager.create_session()
    while True:
        try:
            user_text = input_func("\nYou > ").strip()
            if not user_text:
                continue
            command = user_text.lower()
            if command in ("exit", "quit", "back"):
                output_func("Returning to main menu...")
                break
            if command == "clear":
                clear_func()
                continue

            from jarvis_os.core.conversation.models import ConversationMessage, ConversationRequest
            msg = ConversationMessage(role="user", content=user_text)
            req = ConversationRequest(session_id=session.session_id, message=msg)

            response = conversation_manager.handle_request(req)
            output_func(f"\nBHUvi > {response.message.content}")
        except KeyboardInterrupt:
            output_func("\nReturning to main menu...")
            break
        except Exception as exc:
            output_func(f"[ERROR] {exc}")


def run_keyboard_fallback(conversation_manager: ConversationManager) -> None:
    """Fallback terminal prompt loop if vocal hardware fails."""
    print("=" * 60)
    print("               JARVIS KEYBOARD FALLBACK MODE                ")
    print("=" * 60)
    print("Type your message and press Enter. Type 'exit' to quit.")
    print("-" * 60)
    run_text_mode(conversation_manager)


def main() -> None:
    parser = argparse.ArgumentParser(description="BHUvi Personal AI Assistant")
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Force the use of Mock LLM Provider (no Ollama server connection required)",
    )
    args = parser.parse_args()

    while True:
        print_startup_menu()
        selection = input("> ").strip()

        if selection == "1":
            provider = resolve_llm_provider(args)
            if provider is None:
                continue
            conversation_manager = build_conversation_manager(provider)
            run_voice_mode(conversation_manager)
        elif selection == "2":
            provider = resolve_llm_provider(args)
            if provider is None:
                continue
            conversation_manager = build_conversation_manager(provider)
            run_text_mode(conversation_manager)
        elif selection == "3":
            break
        else:
            print("Please select 1, 2, or 3.")


if __name__ == "__main__":
    main()
