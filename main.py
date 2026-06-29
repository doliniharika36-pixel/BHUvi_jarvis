"""
Bootstrap script to wire together the Jarvis OS architecture and launch the Voice Pipeline.
"""
from __future__ import annotations

import argparse
import logging
import queue
import sys
from datetime import datetime
from typing import AsyncIterator, List, Optional

from jarvis_os.core.context.context_builder import ContextBuilder
from jarvis_os.core.context.token_budget import ContextBudget
from jarvis_os.core.conversation.conversation_manager import ConversationManager
from jarvis_os.core.decision.decision_engine import DecisionEngine
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


def check_ollama_status(client: OllamaHTTPClient) -> bool:
    """Verifies if the local Ollama server is running and accessible."""
    try:
        client.list_models()
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis OS Voice Pipeline Bootstrapper")
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Force the use of Mock LLM Provider (no Ollama server connection required)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("           JARVIS OS VOICE PIPELINE BOOTSTRAPPER            ")
    print("=" * 60)

    # 1. Instantiate SQLite/In-Memory Persistence Layer
    print("[1/6] Initializing persistence repository...")
    repo = InMemoryMemoryRepository()

    # Seed initial memories
    seed_memory = MemoryRecord(
        id="sys_init",
        content="Jarvis OS voice system initialized.",
        memory_type=MemoryType.SYSTEM,
        created_at=datetime.now(),
    )
    repo.save(seed_memory)

    # 2. Instantiate Context, Memory and Decision Layers
    print("[2/6] Building context, memory, and decision engines...")
    memory_manager = MemoryManager(repo)
    retriever = Retriever(repo)
    context_budget = ContextBudget(max_prompt_tokens=2048)
    context_builder = ContextBuilder(
        system_prompt="You are Jarvis, a highly intelligent and polite AI assistant.",
        budget=context_budget,
    )
    decision_engine = DecisionEngine()

    # 3. Instantiate LLM Provider and Service Layer
    print("[3/6] Configuring LLM back-end provider...")
    ollama_config = OllamaHTTPConfig()
    ollama_client = OllamaHTTPClient(ollama_config)

    provider: LLMProvider
    if args.mock_llm:
        print("  -> Force Mock LLM option selected.")
        provider = MockLLMProvider()
    else:
        print("  -> Connecting to local Ollama server at http://localhost:11434...")
        if check_ollama_status(ollama_client):
            print("  -> Connection successful! Ollama is online.")
            provider = OllamaProvider(http_client=ollama_client, config=ollama_config)
        else:
            print("  [!] Warning: Local Ollama server is offline.")
            print("  -> Falling back to local offline Mock LLM Provider.")
            provider = MockLLMProvider()

    llm_service = LLMService(provider=provider)

    # 4. Instantiate Conversation Manager (Orchestrator)
    print("[4/6] Creating Conversation Orchestrator...")
    conversation_manager = ConversationManager(
        decision_engine=decision_engine,
        retriever=retriever,
        context_builder=context_builder,
        llm_service=llm_service,
        memory_manager=memory_manager,
    )

    # 5. Instantiate Voice Adapters (STT & TTS)
    print("[5/6] Loading vocal hardware adapters (STT & TTS)...")
    stt = GoogleSpeechAdapter()
    tts = Pyttsx3Adapter()

    # 6. Instantiate Voice Pipeline
    print("[6/6] Assembling Voice Pipeline...")
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


def run_keyboard_fallback(conversation_manager: ConversationManager) -> None:
    """Fallback terminal prompt loop if vocal hardware fails."""
    print("=" * 60)
    print("               JARVIS KEYBOARD FALLBACK MODE                ")
    print("=" * 60)
    print("Type your message and press Enter. Type 'exit' to quit.")
    print("-" * 60)
    
    session = conversation_manager.create_session()
    while True:
        try:
            user_text = input("\nYou: ").strip()
            if not user_text:
                continue
            if user_text.lower() in ("exit", "quit"):
                break

            from jarvis_os.core.conversation.models import ConversationMessage, ConversationRequest
            msg = ConversationMessage(role="user", content=user_text)
            req = ConversationRequest(session_id=session.session_id, message=msg)
            
            response = conversation_manager.handle_request(req)
            print(f"Jarvis: {response.message.content}")
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Error handling request: {exc}")


if __name__ == "__main__":
    main()
