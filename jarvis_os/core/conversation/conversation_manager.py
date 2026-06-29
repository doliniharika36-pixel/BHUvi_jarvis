from __future__ import annotations

import logging
from datetime import datetime
from threading import RLock
from typing import Any, Dict, Optional

from .exceptions import (
    ConversationException,
    ConversationOrchestrationException,
    SessionExpiredException,
    SessionNotFoundException,
)
from .models import ConversationMessage, ConversationMetadata, ConversationRequest, ConversationResponse
from .session import ConversationSession

logger = logging.getLogger(__name__)


class ConversationManager:
    """Thread-safe orchestration layer for a Jarvis conversation session."""

    def __init__(
        self,
        decision_engine: Any,
        retriever: Any,
        context_builder: Any,
        llm_service: Any,
        memory_manager: Any,
    ) -> None:
        self._lock = RLock()
        self._sessions: Dict[str, ConversationSession] = {}
        self.decision_engine = decision_engine
        self.retriever = retriever
        self.context_builder = context_builder
        self.llm_service = llm_service
        self.memory_manager = memory_manager

    def create_session(
        self,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationSession:
        with self._lock:
            session = ConversationSession(
                session_id=session_id,
                conversation_id=conversation_id,
                metadata=metadata,
            )
            self._sessions[session.session_id] = session
            return session

    def get_session(self, session_id: str) -> ConversationSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundException(f"Session with ID {session_id} not found.")
            return session

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                session.close()

    def handle_request(self, request: ConversationRequest) -> ConversationResponse:
        try:
            session = self.get_session(request.session_id) if request.session_id else self.create_session()
            if not session.is_active:
                raise SessionExpiredException(f"Session {session.session_id} is inactive.")

            session.add_message(request.message)
            history = session.messages
            decision = self._decide(request.message, history)
            retrieved_memories = self._retrieve(request.message.content)
            prompt = self._build_context(request.message, history, retrieved_memories)
            reply_text = self._generate(prompt)

            assistant_message = ConversationMessage(
                role="assistant",
                content=reply_text,
                timestamp=datetime.utcnow(),
            )
            session.add_message(assistant_message)
            self._store_memory(session.session_id, request.message)
            self._store_memory(session.session_id, assistant_message)

            return ConversationResponse(
                session_id=session.session_id,
                message=assistant_message,
                metadata=ConversationMetadata(properties={"decision": decision}),
            )
        except ConversationException:
            raise
        except Exception as exc:
            logger.error("Conversation orchestration failed internally: %s", exc)
            raise ConversationOrchestrationException(
                f"Orchestration pipeline execution error: {exc}"
            ) from exc

    def _decide(self, message: ConversationMessage, history: list[ConversationMessage]) -> Any:
        if self.decision_engine is None:
            return None
        try:
            return self.decision_engine.decide(message=message, history=history)
        except TypeError:
            try:
                return self.decision_engine.decide(message.content)
            except TypeError:
                logger.warning("Decision engine signature was not compatible; continuing.")
                return None
        except Exception as exc:
            logger.warning("Decision engine failed; continuing with fallback: %s", exc)
            return None

    def _retrieve(self, query: str) -> Any:
        if self.retriever is None:
            return []
        try:
            return self.retriever.retrieve(query=query)
        except TypeError:
            try:
                return self.retriever.retrieve(query)
            except TypeError:
                logger.warning("Retriever signature was not compatible; continuing.")
                return []
        except Exception as exc:
            logger.warning("Retriever failed; continuing with fallback: %s", exc)
            return []

    def _build_context(
        self,
        message: ConversationMessage,
        history: list[ConversationMessage],
        memories: Any,
    ) -> Any:
        if self.context_builder is None:
            return message.content
        try:
            return self.context_builder.build_context(history=history, memories=memories)
        except AttributeError:
            try:
                return self.context_builder.build(
                    user_request=message.content,
                    conversation_history=history,
                    retrieved_memories=memories,
                )
            except Exception as exc:
                logger.error("Context builder failed: %s", exc)
                raise ConversationOrchestrationException("Failed to assemble message context.") from exc
        except Exception as exc:
            logger.error("Context builder failed: %s", exc)
            raise ConversationOrchestrationException("Failed to assemble message context.") from exc

    def _generate(self, prompt: Any) -> str:
        if self.llm_service is None:
            raise ConversationOrchestrationException("LLM service interface missing.")
        try:
            return str(self.llm_service.generate(prompt=prompt))
        except AttributeError:
            try:
                response = self.llm_service.complete(str(prompt))
                return str(getattr(response, "content", response))
            except Exception as exc:
                logger.error("LLM generation failed: %s", exc)
                raise ConversationOrchestrationException("LLM generation execution error.") from exc
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
            raise ConversationOrchestrationException("LLM generation execution error.") from exc

    def _store_memory(self, session_id: str, message: ConversationMessage) -> None:
        if self.memory_manager is None:
            return
        try:
            self.memory_manager.store_memory(session_id=session_id, message=message)
        except AttributeError:
            logger.warning("Memory manager has no store_memory method; skipping persistence.")
        except Exception as exc:
            logger.warning("Memory manager failed to save memory point: %s", exc)
