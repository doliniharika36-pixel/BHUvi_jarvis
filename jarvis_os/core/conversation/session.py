from __future__ import annotations

import uuid
from datetime import datetime
from threading import RLock
from typing import Any, Dict, List, Optional

from .exceptions import SessionExpiredException
from .models import ConversationMessage


class ConversationSession:
    def __init__(
        self,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._lock = RLock()
        self.session_id = session_id or str(uuid.uuid4())
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.metadata = dict(metadata or {})
        self.created_at = datetime.utcnow()
        self.last_activity_at = self.created_at
        self.is_active = True
        self._messages: List[ConversationMessage] = []

    @property
    def messages(self) -> List[ConversationMessage]:
        with self._lock:
            return list(self._messages)

    def add_message(self, message: ConversationMessage) -> None:
        with self._lock:
            self._ensure_active()
            self._messages.append(message)
            self.last_activity_at = datetime.utcnow()

    def update_metadata(self, key: str, value: Any) -> None:
        with self._lock:
            self._ensure_active()
            self.metadata[key] = value
            self.last_activity_at = datetime.utcnow()

    def close(self) -> None:
        with self._lock:
            self.is_active = False
            self.last_activity_at = datetime.utcnow()

    def _ensure_active(self) -> None:
        if not self.is_active:
            raise SessionExpiredException(f"Session {self.session_id} is no longer active.")
