class ConversationException(Exception):
    """Base exception for conversation orchestration."""


class SessionNotFoundException(ConversationException):
    """Raised when a session id is unknown."""


class SessionExpiredException(ConversationException):
    """Raised when an inactive session is used."""


class ConversationOrchestrationException(ConversationException):
    """Raised when the conversation pipeline cannot complete."""
