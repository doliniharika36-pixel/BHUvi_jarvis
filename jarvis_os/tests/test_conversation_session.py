import threading
import unittest
from datetime import datetime

from jarvis_os.core.conversation.exceptions import SessionExpiredException
from jarvis_os.core.conversation.models import ConversationMessage
from jarvis_os.core.conversation.session import ConversationSession


class TestConversationSession(unittest.TestCase):
    def test_session_initialization(self):
        session = ConversationSession(metadata={"user_tier": "premium"})

        self.assertIsNotNone(session.session_id)
        self.assertIsNotNone(session.conversation_id)
        self.assertTrue(session.is_active)
        self.assertEqual(len(session.messages), 0)
        self.assertEqual(session.metadata.get("user_tier"), "premium")
        self.assertIsInstance(session.created_at, datetime)
        self.assertIsInstance(session.last_activity_at, datetime)

    def test_add_message(self):
        session = ConversationSession()
        msg = ConversationMessage(role="user", content="Hello, Jarvis!")

        session.add_message(msg)

        self.assertEqual(len(session.messages), 1)
        self.assertEqual(session.messages[0].content, "Hello, Jarvis!")
        self.assertEqual(session.messages[0].role, "user")

    def test_update_metadata(self):
        session = ConversationSession()
        session.update_metadata("theme", "dark")

        self.assertEqual(session.metadata.get("theme"), "dark")

    def test_inactive_session_raises_exception(self):
        session = ConversationSession()
        session.close()
        msg = ConversationMessage(role="user", content="Hello?")

        self.assertFalse(session.is_active)
        with self.assertRaises(SessionExpiredException):
            session.add_message(msg)
        with self.assertRaises(SessionExpiredException):
            session.update_metadata("key", "value")

    def test_thread_safety_concurrency(self):
        session = ConversationSession()
        num_threads = 10
        messages_per_thread = 20

        def worker():
            for i in range(messages_per_thread):
                session.add_message(ConversationMessage(role="user", content=f"Msg {i}"))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(session.messages), num_threads * messages_per_thread)
