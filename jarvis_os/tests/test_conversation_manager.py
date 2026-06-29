import threading
import unittest
from unittest.mock import Mock

from jarvis_os.core.conversation.conversation_manager import ConversationManager
from jarvis_os.core.conversation.exceptions import (
    ConversationOrchestrationException,
    SessionNotFoundException,
)
from jarvis_os.core.conversation.models import ConversationMessage, ConversationRequest


class TestConversationManager(unittest.TestCase):
    def setUp(self):
        self.mock_decision_engine = Mock()
        self.mock_retriever = Mock()
        self.mock_context_builder = Mock()
        self.mock_llm_service = Mock()
        self.mock_memory_manager = Mock()

        self.mock_decision_engine.decide.return_value = "proceed_to_llm"
        self.mock_retriever.retrieve.return_value = ["contextual_memory_1"]
        self.mock_context_builder.build_context.return_value = "Compiled context with memories"
        self.mock_llm_service.generate.return_value = "Hello, I am Jarvis."

        self.manager = ConversationManager(
            decision_engine=self.mock_decision_engine,
            retriever=self.mock_retriever,
            context_builder=self.mock_context_builder,
            llm_service=self.mock_llm_service,
            memory_manager=self.mock_memory_manager,
        )

    def test_create_and_get_session(self):
        session = self.manager.create_session(metadata={"source": "api"})
        retrieved = self.manager.get_session(session.session_id)

        self.assertIsNotNone(session.session_id)
        self.assertEqual(retrieved.session_id, session.session_id)
        self.assertEqual(retrieved.metadata.get("source"), "api")

    def test_get_invalid_session_raises_exception(self):
        with self.assertRaises(SessionNotFoundException):
            self.manager.get_session("invalid_session_id")

    def test_handle_request_lifecycle_new_session(self):
        user_msg = ConversationMessage(role="user", content="Help me schedule my day.")
        req = ConversationRequest(message=user_msg)

        response = self.manager.handle_request(req)

        self.assertIsNotNone(response.session_id)
        self.assertEqual(response.message.role, "assistant")
        self.assertEqual(response.message.content, "Hello, I am Jarvis.")
        self.mock_decision_engine.decide.assert_called_once()
        self.mock_retriever.retrieve.assert_called_once_with(query="Help me schedule my day.")
        self.mock_context_builder.build_context.assert_called_once()
        self.mock_llm_service.generate.assert_called_once_with(prompt="Compiled context with memories")
        self.assertEqual(self.mock_memory_manager.store_memory.call_count, 2)

        session = self.manager.get_session(response.session_id)
        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.messages[0].content, "Help me schedule my day.")
        self.assertEqual(session.messages[1].content, "Hello, I am Jarvis.")

    def test_handle_request_with_existing_session(self):
        session = self.manager.create_session()
        req = ConversationRequest(
            message=ConversationMessage(role="user", content="Ping"),
            session_id=session.session_id,
        )

        response = self.manager.handle_request(req)

        self.assertEqual(response.session_id, session.session_id)
        self.assertEqual(len(session.messages), 2)

    def test_handle_request_fails_when_llm_service_fails(self):
        self.mock_llm_service.generate.side_effect = Exception("Ollama disconnected")
        req = ConversationRequest(message=ConversationMessage(role="user", content="Fail check"))

        with self.assertRaises(ConversationOrchestrationException):
            self.manager.handle_request(req)

    def test_graceful_handling_of_non_critical_failures(self):
        self.mock_decision_engine.decide.side_effect = Exception("Decision service error")
        self.mock_retriever.retrieve.side_effect = Exception("DB connection timeout")
        self.mock_memory_manager.store_memory.side_effect = Exception("Cache write issue")
        req = ConversationRequest(message=ConversationMessage(role="user", content="Resilient test"))

        response = self.manager.handle_request(req)

        self.assertEqual(response.message.content, "Hello, I am Jarvis.")

    def test_thread_safety_concurrent_requests(self):
        session = self.manager.create_session()
        errors = []

        def request_worker(thread_idx):
            try:
                msg = ConversationMessage(role="user", content=f"Message from thread {thread_idx}")
                self.manager.handle_request(ConversationRequest(message=msg, session_id=session.session_id))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=request_worker, args=(i,)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(session.messages), 10)
